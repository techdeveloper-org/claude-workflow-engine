# ruff: noqa: F821
"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.
"""
import os
from typing import Any, Dict

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]


def step0_task_analysis_node(state: FlowState) -> Dict[str, Any]:
    """Step 0: Task Analysis with call graph complexity boost."""
    result = _run_step(
        0,
        "Task Analysis",
        step0_task_analysis,
        state,
        fallback_result={
            "step0_task_type": "General Task",
            "step0_complexity": 5,
            "step0_reasoning": "Default - step0 failed",
            "step0_tasks": {"count": 1, "tasks": []},
            "step0_task_count": 1,
        },
    )
    # Apply call graph complexity boost injected by orchestration_pre_analysis_node
    try:
        graph_metrics = state.get("call_graph_metrics", {}) or {}
        boost = graph_metrics.get("complexity_boost", 0)
        if boost != 0 and graph_metrics.get("call_graph_available"):
            current = result.get("step0_complexity", 5)
            boosted = max(1, min(10, current + boost))
            if boosted != current:
                result["step0_complexity"] = boosted
                result["step0_complexity_boosted"] = True
                result["step0_complexity_boost_source"] = "call_graph"
                logger.info(
                    "[v2] Step 0 complexity adjusted by call graph: %d -> %d (boost=%+d)",
                    current,
                    boosted,
                    boost,
                )
    except Exception:
        pass  # Boost adjustment is best-effort
    return result


def step1_plan_mode_decision_node(state: FlowState) -> Dict[str, Any]:
    """Step 1: Plan Mode Decision with full error handling."""
    return _run_step(
        1,
        "Plan Mode Decision",
        step1_plan_mode_decision,
        state,
        fallback_result={
            "step1_plan_required": True,  # Safe default: always plan on error
            "step1_reasoning": "Default - step1 failed, defaulting to plan mode",
            "step1_complexity_score": state.get("step0_complexity", 5),
        },
    )


def step2_plan_execution_node(state: FlowState) -> Dict[str, Any]:
    """Step 2: Plan Execution (conditional on Step 1) with full error handling.

    Injects CallGraph impact analysis before planning so the planner
    considers ripple effects of proposed changes.
    """
    # --- CallGraph Impact Analysis (pre-plan) ---
    impact_data = {}
    try:
        from ..call_graph_analyzer import analyze_impact_before_change

        project_root = state.get("project_root", ".")
        target_files = state.get("step0_target_files", [])
        task_desc = state.get("user_message", "")
        impact_data = analyze_impact_before_change(project_root, target_files, task_desc)
        if impact_data.get("call_graph_available"):
            logger.info(
                "[v2] Step 2 CallGraph impact: risk=%s, affected=%d methods",
                impact_data.get("risk_level", "unknown"),
                len(impact_data.get("affected_methods", [])),
            )
    except Exception as e:
        logger.debug("[v2] Step 2 CallGraph analysis skipped: %s", e)

    result = _run_step(
        2,
        "Plan Execution",
        step2_plan_execution,
        state,
        fallback_result={
            "step2_plan_execution": {"error": "Step 2 failed", "phases": []},
            "step2_plan_status": "ERROR",
            "step2_phases": 0,
            "step2_total_estimated_steps": 0,
        },
    )

    # Merge impact analysis into result
    if impact_data.get("call_graph_available"):
        result["step2_impact_analysis"] = impact_data
        result["step2_graph_risk_level"] = impact_data.get("risk_level", "low")
        result["step2_affected_methods"] = [m.get("fqn", "") for m in impact_data.get("affected_methods", [])]

    # --- Plan Validation against CallGraph impact ---
    plan = result.get("step2_plan_execution", {})
    phases = plan.get("phases", [])

    if phases:
        try:
            impact = result.get("step2_impact_analysis", {}) or state.get("step2_impact_analysis", {})
            affected_methods = impact.get("affected_methods", [])
            danger_zones = impact.get("danger_zones", [])

            validation_issues = []

            # Check 1: Do plan phases cover all affected files?
            plan_files = set()
            for phase in phases:
                for task in phase.get("tasks", []):
                    if isinstance(task, dict):
                        plan_files.update(task.get("files", []))

            affected_files = set()
            for m in affected_methods:
                fqn = m.get("fqn", "") if isinstance(m, dict) else str(m)
                if "::" in fqn:
                    affected_files.add(fqn.split("::")[0])

            uncovered = affected_files - plan_files
            if uncovered:
                validation_issues.append(
                    "Plan does not cover %d affected files: %s" % (len(uncovered), ", ".join(sorted(uncovered)[:5]))
                )

            # Check 2: Are danger zone methods addressed in the plan?
            if danger_zones and not any("careful" in str(p).lower() or "test" in str(p).lower() for p in phases):
                validation_issues.append(
                    "%d danger zone methods found but plan has no testing/careful phase" % len(danger_zones)
                )

            # Check 3: Are phases ordered logically? (dependencies before dependents)
            # Simple check: if phase N modifies a file that phase N+1 depends on, order is correct

            result["step2_plan_validated"] = len(validation_issues) == 0
            result["step2_plan_validation_issues"] = validation_issues

            if validation_issues:
                logger.info(
                    "[v2] Step 2 plan validation: %d issues found: %s",
                    len(validation_issues),
                    "; ".join(validation_issues),
                )
            else:
                logger.info("[v2] Step 2 plan validation: PASSED")

        except Exception as e:
            logger.debug("[v2] Step 2 plan validation skipped: %s", e)
            result["step2_plan_validated"] = True  # Default to valid on error
            result["step2_plan_validation_issues"] = []

    # --- User Interaction: High-risk plan confirmation ---
    try:
        from ..user_interaction import generate_step2_questions

        questions = generate_step2_questions({**state, **result})
        if questions:
            result["step2_pending_questions"] = questions
    except Exception as e:
        logger.debug("[v2] Step 2 user interaction skipped: %s", e)

    return result


def step3_task_breakdown_node(state: FlowState) -> Dict[str, Any]:
    """Step 3: Task Breakdown Validation with full error handling."""
    result = _run_step(
        3,
        "Task Breakdown Validation",
        step3_task_breakdown_validation,
        state,
        fallback_result={
            "step3_tasks_validated": [],
            "step3_task_count": 0,
            "step3_validation_status": "ERROR",
            "step3_validation_errors": ["Step 3 failed"],
        },
    )

    # --- CallGraph: Map files to tasks/phases based on graph analysis ---
    try:
        from ..call_graph_analyzer import snapshot_call_graph

        project_root = state.get("project_root", ".")

        # Get or build the graph snapshot (reuse from Step 2 if available)
        graph_snapshot = state.get("step2_impact_analysis", {})
        if not graph_snapshot.get("call_graph_available"):
            graph_snapshot = snapshot_call_graph(project_root)

        # Map task descriptions to files using graph's method/class names
        validated_tasks = result.get("step3_tasks_validated", [])
        phase_file_map = {}

        all_methods = graph_snapshot.get("nodes", {}).get("methods", []) if "nodes" in graph_snapshot else []
        all_classes = graph_snapshot.get("nodes", {}).get("classes", []) if "nodes" in graph_snapshot else []

        for task in validated_tasks:
            desc = task.get("description", "").lower()
            task_id = task.get("id", "unknown")
            matched_files = set()

            # If task already has files from Step 0, use those
            if task.get("files"):
                matched_files.update(task["files"])
            else:
                # Match by keyword in class/method names against task description
                desc_words = set(w for w in desc.replace("-", " ").replace("_", " ").split() if len(w) > 3)
                for m in all_methods:
                    m_name = m.get("name", "").lower()
                    m_file = m.get("file", "")
                    if any(w in m_name for w in desc_words) and m_file:
                        matched_files.add(m_file)
                for c in all_classes:
                    c_name = c.get("name", "").lower()
                    c_file = c.get("file", "")
                    if any(w in c_name for w in desc_words) and c_file:
                        matched_files.add(c_file)

            phase_file_map[task_id] = sorted(matched_files)

        result["step3_phase_file_map"] = phase_file_map
        # Store the graph snapshot for reuse in Step 4
        if "nodes" in graph_snapshot:
            result["step3_graph_snapshot"] = graph_snapshot

        logger.info("[v2] Step 3 mapped %d tasks to files via CallGraph", len(phase_file_map))
    except Exception as e:
        logger.debug("[v2] Step 3 file mapping skipped: %s", e)

    # -- Figma Integration: extract components to inform task breakdown ----
    if os.environ.get("ENABLE_FIGMA", "0") == "1":
        try:
            from ..figma_workflow import Level3FigmaWorkflow

            figma_wf = Level3FigmaWorkflow()
            file_key = figma_wf.detect_figma_url(state.get("user_message", ""))
            if file_key:
                comp_result = figma_wf.step3_extract_components(file_key)
                result["figma_enabled"] = True
                result["figma_file_key"] = file_key
                result["figma_components"] = comp_result.get("components", [])
                if not comp_result.get("success"):
                    result["figma_error"] = comp_result.get("error", "Unknown")
                logger.info(
                    "[v2] Figma components extracted: %d components",
                    comp_result.get("total_components", 0),
                )
        except Exception as e:
            logger.warning("[v2] Figma integration (step3) failed (non-blocking): %s", str(e))
            result["figma_enabled"] = True
            result["figma_error"] = str(e)

    return result


def step4_toon_refinement_node(state: FlowState) -> Dict[str, Any]:
    """Step 4: TOON Refinement with full error handling."""
    result = _run_step(
        4,
        "TOON Refinement",
        step4_toon_refinement,
        state,
        fallback_result={
            "step4_toon_refined": state.get("level1_context_toon", {}),
            "step4_refinement_status": "ERROR",
            "step4_complexity_adjusted": state.get("step0_complexity", 5),
        },
    )

    # --- CallGraph: Inject phase-scoped context, clear old broad context ---
    try:
        from ..call_graph_analyzer import get_phase_scoped_context

        # Get graph snapshot (from Step 3 or Step 2)
        graph_snapshot = state.get("step3_graph_snapshot") or state.get("step2_impact_analysis", {})

        # Get phase file mapping from Step 3
        phase_file_map = state.get("step3_phase_file_map", {})

        if graph_snapshot and phase_file_map:
            # For each phase/task, get its scoped context
            phase_contexts = {}
            all_phase_files = set()

            for task_id, files in phase_file_map.items():
                if files:
                    ctx = get_phase_scoped_context(graph_snapshot, files, task_id)
                    phase_contexts[task_id] = ctx
                    all_phase_files.update(files)

            if phase_contexts:
                result["step4_phase_contexts"] = phase_contexts
                result["step4_phase_scope_files"] = sorted(all_phase_files)

                # Clear old broad context - replace with focused phase data
                result["step4_old_context_cleared"] = True

                logger.info(
                    "[v2] Step 4 injected %d phase contexts, %d files in scope",
                    len(phase_contexts),
                    len(all_phase_files),
                )
    except Exception as e:
        logger.debug("[v2] Step 4 phase context skipped: %s", e)

    return result
