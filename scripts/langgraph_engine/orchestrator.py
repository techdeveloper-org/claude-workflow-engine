"""
Orchestrator - Main StateGraph for 3-level flow execution.

LangGraph 1.0.10 Implementation: Flattened graph (no subgraph nesting)

This StateGraph wires together all 3 levels with conditional routing:
1. Level -1 (auto-fix) - blocking checkpoint
2. Level 1 (sync, 4 parallel context tasks)
3. Level 2 (standards, conditional Java routing)
4. Level 3 (12-step execution)
5. Output node - writes flow-trace.json

Note: LangGraph 1.0.10 doesn't support add_graph() nesting, so we flatten
all nodes into one graph. This works fine - the graph structure is still clear
via node naming (level_minus1_*, level1_*, etc.)
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _ORCHESTRATOR_CLAUDE_HOME = get_claude_home()
except ImportError:
    _ORCHESTRATOR_CLAUDE_HOME = Path.home() / ".claude"

try:
    from langgraph.graph import END, START, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .checkpointer import CheckpointerManager
from .flow_state import FlowState, StepKeys, WorkflowContextOptimizer
from .level1_sync import (
    cleanup_level1_memory,
    level1_merge_node,
    node_complexity_calculation,
    node_context_loader,
    node_session_loader,
    node_toon_compression,
)
from .level2_standards import (
    detect_project_type,
    level2_merge_node,
    node_common_standards,
    node_java_standards,
    node_mcp_plugin_discovery,
    node_tool_optimization_standards,
)
from .level3_execution.subgraph import level3_init_node
from .level3_execution.subgraph import level3_merge_node as level3_v2_merge_node
from .level3_execution.subgraph import (
    orchestration_pre_analysis_node,
    route_pre_analysis,
    step0_0_project_context_node,
    step0_1_initial_callgraph_node,
    step0_task_analysis_node,
    step1_plan_mode_decision_node,
    step2_plan_execution_node,
    step3_task_breakdown_node,
    step4_toon_refinement_node,
    step5_skill_selection_node,
    step6_skill_validation_node,
    step7_final_prompt_node,
    step8_github_issue_node,
    step9_branch_creation_node,
    step10_implementation_note,
    step11_pull_request_node,
    step12_issue_closure_node,
    step13_docs_update_node,
    step14_final_summary_node,
)
from .level_minus1 import (
    ask_level_minus1_fix,
    fix_level_minus1_issues,
    level_minus1_merge_node,
    node_encoding_validation,
    node_unicode_fix,
    node_windows_path_check,
)

# Level -1 routing functions (canonical definitions live in routing/)
from .routing import route_after_level_minus1, route_after_level_minus1_user_choice
from .standard_selector import select_standards
from .standards_integration import apply_standards_at_step


def route_context_threshold(state: FlowState) -> Literal["level2_emergency_archive", "level2_common_standards"]:
    """Route based on context usage threshold."""
    if state.get(StepKeys.CONTEXT_THRESHOLD_EXCEEDED):
        return "level2_emergency_archive"
    return "level2_common_standards"


def route_standards_loading(state: FlowState) -> Literal["level2_java_standards", "level2_merge"]:
    """Route based on project type (Java detection)."""
    detect_project_type(state)
    if state.get(StepKeys.IS_JAVA_PROJECT):
        return "level2_java_standards"
    return "level2_merge"


def route_after_step1_decision(state: FlowState) -> Literal["level3_step2", "level3_step3"]:
    """Conditional routing: if plan required, execute Step 2; else skip to Step 3."""
    if state.get(StepKeys.PLAN_REQUIRED, True):
        return "level3_step2"
    return "level3_step3"


def route_after_step11_review(state: FlowState) -> Literal["level3_step12", "level3_step11_retry"]:
    """Conditional routing after PR review: if failed and retries < 3, retry; else continue to closure."""
    review_passed = state.get(StepKeys.REVIEW_PASSED, False)
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)

    if review_passed or retry_count >= 3:
        return "level3_step12"
    else:
        # Route to retry node (which will increment count via proper state return)
        return "level3_step11_retry"


def step11_retry_increment_node(state: FlowState) -> dict:
    """Increment retry count before re-routing to Step 10.

    State mutations must happen in nodes, not routing functions (LangGraph anti-pattern).
    """
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)
    return {StepKeys.RETRY_COUNT: retry_count + 1}


# ============================================================================
# SIMPLE HELPER NODES
# ============================================================================


def emergency_archive(state: FlowState) -> dict:
    """Emergency archival when context threshold exceeded.

    Runs as part of the Level 1 -> Level 2 transition. If context usage
    is below threshold, this is a no-op pass-through. If above 95%,
    triggers aggressive cleanup and logs a warning.
    """
    updates = {}
    context_pct = state.get(StepKeys.CONTEXT_PERCENTAGE, 0)

    if context_pct >= 95:
        existing_warnings = state.get(StepKeys.WARNINGS) or []
        warnings = list(existing_warnings) + [
            "EMERGENCY: Context usage at %.1f%% - archiving old sessions to free memory" % context_pct
        ]
        updates[StepKeys.WARNINGS] = warnings
        updates["emergency_archive_triggered"] = True

        # Best-effort: trigger session pruning
        try:
            import sys as _sys_ea

            _sys_ea.path.insert(0, str(Path(__file__).resolve().parent.parent / "architecture"))
            from importlib import import_module

            _pruner_spec = import_module("session-pruner") if False else None
        except Exception:
            pass

        print("[EMERGENCY ARCHIVE] Context at %.1f%% - archive triggered" % context_pct, file=sys.stderr)
    else:
        updates["emergency_archive_triggered"] = False

    return updates


# ============================================================================
# CONTEXT OPTIMIZATION NODES - Smart context compression between levels
# ============================================================================


def optimize_context_after_level1(state: FlowState) -> dict:
    """Optimize context after Level 1 completes before passing to Level 2.

    Stores full Level 1 output in workflow_memory, passes only summary to Level 2.
    This keeps context clean while preserving full data for fallback/debugging.
    """
    # Store full level 1 output
    level1_output = {
        StepKeys.CONTEXT_LOADED: state.get(StepKeys.CONTEXT_LOADED),
        StepKeys.CONTEXT_PERCENTAGE: state.get(StepKeys.CONTEXT_PERCENTAGE),
        StepKeys.SESSION_CHAIN_LOADED: state.get(StepKeys.SESSION_CHAIN_LOADED),
        StepKeys.PATTERNS_DETECTED: state.get(StepKeys.PATTERNS_DETECTED, []),
        StepKeys.PREFERENCES_DATA: state.get(StepKeys.PREFERENCES_DATA, {}),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level1_output", level1_output)

    # Build optimized context for Level 2
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_after_level2(state: FlowState) -> dict:
    """Optimize context after Level 2 before Level 3 execution.

    Stores standards info in memory, passes only summary to Level 3.
    """
    # Store full level 2 output
    level2_output = {
        StepKeys.STANDARDS_LOADED: state.get(StepKeys.STANDARDS_LOADED),
        StepKeys.STANDARDS_COUNT: state.get(StepKeys.STANDARDS_COUNT),
        StepKeys.JAVA_STANDARDS_LOADED: state.get(StepKeys.JAVA_STANDARDS_LOADED),
        StepKeys.SPRING_BOOT_PATTERNS: state.get(StepKeys.SPRING_BOOT_PATTERNS, {}),
        StepKeys.TOOL_OPTIMIZATION_RULES: state.get(StepKeys.TOOL_OPTIMIZATION_RULES, {}),
        StepKeys.TOOL_OPTIMIZATION_LOADED: state.get(StepKeys.TOOL_OPTIMIZATION_LOADED, False),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level2_output", level2_output)

    # Build optimized context for Level 3
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_for_level3_step(state: FlowState, step_name: str) -> dict:
    """Optimize context before each Level 3 step.

    For Level 3, only pass data specific to current step.
    All previous step outputs stay in workflow_memory.
    """
    # Store current step's inputs/outputs
    current_data = {k: v for k, v in state.items() if k.startswith("step") and isinstance(v, dict)}

    state = WorkflowContextOptimizer.store_step_output(state, step_name, current_data)

    return state


def save_workflow_memory(state: FlowState) -> dict:
    """Save workflow memory to disk for session persistence."""
    try:
        import json

        session_id = state.get(StepKeys.SESSION_ID, "unknown")
        memory = state.get(StepKeys.WORKFLOW_MEMORY, {})

        if memory and session_id != "unknown":
            # Save to ~/.claude/memory/sessions/{session_id}/workflow-memory.json
            memory_dir = _ORCHESTRATOR_CLAUDE_HOME / "memory" / "logs" / "sessions" / session_id
            memory_dir.mkdir(parents=True, exist_ok=True)

            memory_file = memory_dir / "workflow-memory.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "timestamp": state.get(StepKeys.TIMESTAMP),
                        "workflow_memory": memory,
                        "context_optimization_stats": state.get(StepKeys.STEP_OPTIMIZATION_STATS, {}),
                        "memory_size_kb": state.get(StepKeys.WORKFLOW_MEMORY_SIZE_KB, 0),
                    },
                    f,
                    indent=2,
                )

            return {"workflow_memory_file": str(memory_file)}
    except Exception:
        # Don't fail if memory save fails - it's non-critical
        pass

    return {}


# ============================================================================
# LEVEL 2: STANDARDS SELECTOR NODE
# Runs after common/Java standards are loaded, before context optimization.
# Uses standard_selector.py to auto-detect project type + framework and load
# all applicable standards (custom > team > framework > language priority).
# ============================================================================


def level2_select_standards_node(state: FlowState) -> dict:
    """Level 2 node: auto-select and load all applicable project standards.

    Runs select_standards() which detects project type/framework and loads
    standards from all sources in priority order (custom=4 > team=3 > framework=2
    > language=1), resolving conflicts so the highest-priority source wins.

    Outputs written to FlowState:
      standards_selection       - full selection result including traceability
      standards_merged_rules    - conflict-resolved merged rules dict
      detected_framework        - framework name for downstream routing
      standards_selection_error - error string (non-fatal, execution continues)

    Integration hooks (standards_hook_step1/2/5/10/13) consume the standards_selection
    data to inject step-specific context/constraints/checklists.
    """
    updates: dict = {}

    try:
        project_root = state.get(StepKeys.PROJECT_ROOT, ".")
        session_id = state.get(StepKeys.SESSION_ID, "unknown")

        # select_standards() internally calls detect_project_type() + detect_framework()
        # and loads all sources with conflict resolution
        full_selection = select_standards(project_root, session_id)

        updates["standards_selection"] = {
            "project_type": full_selection["project_type"],
            "framework": full_selection["framework"],
            "total_loaded": full_selection["total_loaded"],
            "conflicts_detected": len(full_selection["conflicts"]),
            "merged_rules": full_selection["merged_rules"],
            "traceability": full_selection.get("traceability", {}),
            "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
        }

        # Make merged rules available at top-level for quick access by integration hooks
        merged = full_selection.get("merged_rules", {})
        if merged:
            updates["standards_merged_rules"] = merged

        # Expose detected framework for downstream nodes
        updates["detected_framework"] = full_selection["framework"]

        existing_pipeline = state.get(StepKeys.PIPELINE) or []
        updates[StepKeys.PIPELINE] = list(existing_pipeline) + [
            {
                "node": "level2_select_standards",
                "project_type": full_selection["project_type"],
                "framework": full_selection["framework"],
                "standards_loaded": full_selection["total_loaded"],
                "conflicts": len(full_selection["conflicts"]),
                "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
                "traceability_keys": list(full_selection.get("traceability", {}).keys()),
            }
        ]

    except Exception as exc:
        updates["standards_selection_error"] = str(exc)
        existing_pipeline = state.get(StepKeys.PIPELINE) or []
        updates[StepKeys.PIPELINE] = list(existing_pipeline) + [
            {
                "node": "level2_select_standards",
                "error": str(exc),
            }
        ]

    return updates


def apply_integration_step1(state: FlowState) -> dict:
    """Apply standards integration point at Step 1 (plan mode decision)."""
    updated = apply_standards_at_step(1, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step2(state: FlowState) -> dict:
    """Apply standards integration point at Step 2 (plan execution)."""
    updated = apply_standards_at_step(2, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step3(state: FlowState) -> dict:
    """Apply standards integration point at Step 3 (task breakdown)."""
    updated = apply_standards_at_step(3, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step4(state: FlowState) -> dict:
    """Apply standards integration point at Step 4 (TOON refinement)."""
    updated = apply_standards_at_step(4, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step5(state: FlowState) -> dict:
    """Apply standards integration point at Step 5 (skill selection)."""
    updated = apply_standards_at_step(5, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step6(state: FlowState) -> dict:
    """Apply standards integration point at Step 6 (skill validation)."""
    updated = apply_standards_at_step(6, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step7(state: FlowState) -> dict:
    """Apply standards integration point at Step 7 (final prompt generation)."""
    updated = apply_standards_at_step(7, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step10(state: FlowState) -> dict:
    """Apply standards integration point at Step 10 (code review)."""
    updated = apply_standards_at_step(10, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step13(state: FlowState) -> dict:
    """Apply standards integration point at Step 13 (documentation)."""
    updated = apply_standards_at_step(13, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def verify_prompt_integrity(state: FlowState) -> bool:
    """Verify that original user prompt was never modified during flow.

    CRITICAL: user_message must equal user_message_original
    If modified, that's a bug in the flow design.
    """
    original = state.get(StepKeys.USER_MESSAGE_ORIGINAL, "")
    current = state.get(StepKeys.USER_MESSAGE, "")

    if original != current:
        print("[WARNING] PROMPT INTEGRITY VIOLATION!", file=sys.stderr)
        print(f"  Original: {original[:50]}...", file=sys.stderr)
        print(f"  Current:  {current[:50]}...", file=sys.stderr)
        return False

    return True


def synthesize_prompt_with_flow_data(state: FlowState) -> dict:
    """Synthesize comprehensive prompt using all collected 3-level flow data.

    SYNTHESIS PROCESS:
    1. Collect data from all levels
    2. Call PromptGenerator.synthesize_with_flow_data()
    3. Create comprehensive prompt
    4. Return synthesized prompt for actual work
    """
    try:
        import importlib.util
        import sys
        from pathlib import Path

        # Import PromptGenerator from prompt-generation-policy.py
        scripts_path = Path(__file__).parent.parent / "architecture" / "03-execution-system" / "00-prompt-generation"
        spec = importlib.util.spec_from_file_location(
            "prompt_generation_policy", scripts_path / "prompt-generation-policy.py"
        )
        pg_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pg_module)

        generator = pg_module.PromptGenerator()

        # Prepare flow data for synthesis - use ACTUAL pipeline results
        # Collect validated tasks for TodoList
        validated_tasks = state.get(StepKeys.TASKS_VALIDATED, [])
        raw_tasks = state.get(StepKeys.TASKS, {}).get("tasks", [])
        all_tasks = validated_tasks if validated_tasks else raw_tasks

        # Collect plan phases
        plan_exec = state.get(StepKeys.PLAN_EXECUTION, {})
        plan_phases = plan_exec.get("phases", []) if isinstance(plan_exec, dict) else []

        flow_data = {
            "level_minus1": {
                "unicode_check": state.get(StepKeys.UNICODE_CHECK, False),
                "encoding_check": state.get(StepKeys.ENCODING_CHECK, False),
                "windows_path_check": state.get(StepKeys.WINDOWS_PATH_CHECK, False),
            },
            "level1": {
                "context_percentage": state.get(StepKeys.CONTEXT_PERCENTAGE, 0),
                "session_chain_loaded": state.get(StepKeys.SESSION_CHAIN_LOADED, False),
                "patterns_detected": state.get(StepKeys.PATTERNS_DETECTED, []),
                "project_type": state.get(StepKeys.DETECTED_FRAMEWORK, "Unknown"),
            },
            "level2": {
                "standards_count": state.get(StepKeys.STANDARDS_COUNT, 0),
                "is_java_project": state.get(StepKeys.IS_JAVA_PROJECT, False),
                "java_standards_loaded": state.get(StepKeys.JAVA_STANDARDS_LOADED, False),
            },
            "level3": {
                "task_type": state.get(StepKeys.TASK_TYPE, "General"),
                "complexity": state.get(StepKeys.COMPLEXITY, 5),
                "suggested_model": state.get(StepKeys.SELECTED_MODEL, "complex_reasoning"),
                "plan_mode_suggested": state.get(StepKeys.PLAN_REQUIRED, False),
                "reasoning": state.get(StepKeys.REASONING, ""),
                "tasks": all_tasks,
                "task_count": len(all_tasks),
                "plan_phases": plan_phases,
                "selected_skill": state.get(StepKeys.SKILL, ""),
                "selected_agent": state.get(StepKeys.AGENT, ""),
                "selected_skills": state.get(StepKeys.SKILLS, []),
                "selected_agents": state.get(StepKeys.AGENTS, []),
                "skill_definition": state.get(StepKeys.SKILL_DEFINITION, ""),
                "agent_definition": state.get(StepKeys.AGENT_DEFINITION, ""),
            },
        }

        # SYNTHESIS: Create comprehensive prompt
        # Priority: user_message > user_message_original > env var CURRENT_USER_MESSAGE
        import os

        user_msg = (
            state.get(StepKeys.USER_MESSAGE)
            or state.get(StepKeys.USER_MESSAGE_ORIGINAL)
            or os.environ.get("CURRENT_USER_MESSAGE", "")
        )
        synthesis_result = generator.synthesize_with_flow_data(user_msg, flow_data)

        return {
            "synthesized_prompt": synthesis_result.get("synthesized_prompt", ""),
            "synthesis_metadata": {
                "original_message": synthesis_result.get("original_message"),
                "context_level": synthesis_result.get("context_level"),
                "data_used": synthesis_result.get("data_used"),
            },
        }

    except Exception as e:
        import sys

        print(f"[WARNING] Prompt synthesis failed: {e}", file=sys.stderr)
        # Fallback: return original message
        return {
            "synthesized_prompt": state.get(StepKeys.USER_MESSAGE, ""),
            "synthesis_metadata": {"status": "fallback"},
        }


def output_node(state: FlowState) -> dict:
    """Final output node - determines completion status and synthesizes final prompt."""
    # Verify prompt integrity before finishing
    if not verify_prompt_integrity(state):
        # Log but don't block - prompt should never be modified
        pass

    # Write session-start voice flag so Stop hook speaks a greeting
    # Use LEGACY flag (no PID) because pipeline runs in a separate process
    # from Claude Code. Stop-notifier's _resolve_flag checks PID first, then legacy.
    try:
        flag_dir = _ORCHESTRATOR_CLAUDE_HOME
        start_flag = flag_dir / ".session-start-voice"
        if not start_flag.exists():
            task_type = state.get(StepKeys.TASK_TYPE, "task")
            complexity = state.get(StepKeys.COMPLEXITY, 5)
            skill = state.get(StepKeys.SKILL, "")
            msg = f"Starting {task_type} task, complexity {complexity} out of 10."
            if skill:
                msg += f" Using {skill} skill."
            start_flag.write_text(msg, encoding="utf-8")
    except Exception:
        pass

    # SYNTHESIS: Create comprehensive prompt from all flow data
    synthesis = synthesize_prompt_with_flow_data(state)

    # Save workflow memory before finishing
    save_workflow_memory(state)

    # Determine final status based on actual step results (not just errors list)
    if state.get(StepKeys.LEVEL_MINUS1_STATUS) == "BLOCKED":
        final_status = "BLOCKED"
    else:
        step_failures = []
        for key, val in state.items():
            if key.endswith("_status") and isinstance(val, str) and val == "ERROR":
                step_failures.append(key)
        if step_failures:
            final_status = "FAILED"
        elif state.get(StepKeys.WARNINGS):
            final_status = "PARTIAL"
        else:
            final_status = "OK"

    # Save detailed pipeline execution log to session folder
    _save_pipeline_execution_log(state, final_status)

    # In hook_mode, Step 14 doesn't run. Save a quick summary anyway.
    if not state.get(StepKeys.SUMMARY_SAVED):
        session_dir = state.get(StepKeys.SESSION_DIR) or state.get(StepKeys.SESSION_PATH, "")
        if session_dir:
            try:
                from datetime import datetime

                quick_summary = (
                    f"Pipeline: {final_status} | "
                    f"Task: {state.get(StepKeys.TASK_TYPE, '?')} | "
                    f"Complexity: {state.get(StepKeys.COMPLEXITY, '?')}/10 | "
                    f"Skill: {state.get(StepKeys.SKILL, 'none')} | "
                    f"Agent: {state.get(StepKeys.AGENT, 'none')} | "
                    f"Framework: {state.get(StepKeys.DETECTED_FRAMEWORK, '?')} | "
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
                summary_file = Path(session_dir) / "execution-summary.txt"
                summary_file.write_text(quick_summary, encoding="utf-8")
            except Exception:
                pass

    # VECTOR DB RAG - Store session summary for cross-session learning
    try:
        from .rag_integration import get_rag_layer

        rag = get_rag_layer(
            session_id=state.get(StepKeys.SESSION_ID, ""),
            project_root=state.get(StepKeys.PROJECT_ROOT, ""),
        )
        rag.store_session_summary(
            summary=state.get(StepKeys.USER_MESSAGE, "")[:500],
            task_type=state.get(StepKeys.TASK_TYPE, ""),
            skill=state.get(StepKeys.SKILL, ""),
            agent=state.get(StepKeys.AGENT, ""),
            final_status=final_status,
            steps_completed=14 if state.get("step14_status") else 9,
        )
        # Store flow traces for each level
        for level_name, level_status_key in [
            ("level_minus1", StepKeys.LEVEL_MINUS1_STATUS),
            ("level1", "level1_status"),
            ("level2", "level2_status"),
        ]:
            rag.store_flow_trace(
                level=level_name,
                step="merge",
                status=state.get(level_status_key, "OK"),
                description=f"{level_name} completed for {state.get(StepKeys.TASK_TYPE, 'task')}",
            )
        # Log RAG stats
        stats = rag.get_stats()
        if stats.get("stores", 0) > 0 or stats.get("hits", 0) > 0:
            print(
                f"[RAG] Stats: {stats.get('stores', 0)} stored, "
                f"{stats.get('hits', 0)} hits, {stats.get('misses', 0)} misses, "
                f"{rag.get_hit_rate()}% hit rate",
                file=sys.stderr,
            )
    except Exception:
        pass  # RAG storage is non-blocking

    # SESSION ACCUMULATE - Record this request's data via MCP session tools
    try:
        _src_mcp_dir = Path(__file__).resolve().parent.parent.parent / "src" / "mcp"
        if str(_src_mcp_dir) not in sys.path:
            sys.path.insert(0, str(_src_mcp_dir))
        from session_hooks import accumulate_request

        accumulate_request(
            session_id=state.get(StepKeys.SESSION_ID, ""),
            prompt=state.get(StepKeys.USER_MESSAGE, "")[:300],
            task_type=state.get(StepKeys.TASK_TYPE, ""),
            skill=state.get(StepKeys.SKILL, ""),
            complexity=int(state.get(StepKeys.COMPLEXITY, 0)),
            model=state.get(StepKeys.SELECTED_MODEL, ""),
            cwd=state.get(StepKeys.PROJECT_ROOT, ""),
            plan_mode=bool(state.get(StepKeys.PLAN_REQUIRED)),
            context_pct=int(state.get("context_pct", 0)),
            supplementary_skills=",".join(state.get(StepKeys.SKILLS, []) or []),
        )
    except Exception:
        pass  # Accumulation is non-blocking, never fail the pipeline

    # Return synthesis result with proper status
    return {
        "final_status": final_status,
        "synthesized_prompt": synthesis.get("synthesized_prompt", ""),
        "synthesis_metadata": synthesis.get("synthesis_metadata", {}),
    }


def _save_pipeline_execution_log(state: FlowState, final_status: str) -> None:
    """Save a detailed pipeline execution log to session folder.

    Creates a human-readable execution-log.md in the session directory showing:
    - Each step's status, duration, decisions
    - What came in, what went out
    - Total pipeline timing
    - Skills/agents selected
    """
    from datetime import datetime

    session_dir = state.get(StepKeys.SESSION_DIR) or state.get(StepKeys.SESSION_PATH, "")
    if not session_dir:
        return

    try:
        log_lines = []
        log_lines.append("# Pipeline Execution Log")
        log_lines.append(f"\n**Session**: {state.get(StepKeys.SESSION_ID, 'unknown')}")
        log_lines.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"**Project**: {state.get(StepKeys.PROJECT_ROOT, '.')}")
        log_lines.append(f"**Final Status**: {final_status}")
        log_lines.append(f"**Framework**: {state.get(StepKeys.DETECTED_FRAMEWORK, 'unknown')}")
        log_lines.append("")

        # Level -1
        log_lines.append("## Level -1: Auto-Fix")
        log_lines.append(f"- Unicode: {'PASS' if state.get(StepKeys.UNICODE_CHECK) else 'FAIL'}")
        log_lines.append(f"- Encoding: {'PASS' if state.get(StepKeys.ENCODING_CHECK) else 'FAIL'}")
        log_lines.append(f"- Paths: {'PASS' if state.get(StepKeys.WINDOWS_PATH_CHECK) else 'FAIL'}")
        log_lines.append(f"- Status: {state.get(StepKeys.LEVEL_MINUS1_STATUS, 'unknown')}")
        log_lines.append("")

        # Level 1
        log_lines.append("## Level 1: Context Sync")
        log_lines.append(f"- Session: {state.get(StepKeys.SESSION_ID, 'none')}")
        log_lines.append(f"- Complexity: {state.get(StepKeys.COMPLEXITY_SCORE, '?')}/10")
        graph_score = state.get(StepKeys.GRAPH_COMPLEXITY_SCORE)
        if graph_score:
            log_lines.append(f"- Graph Complexity: {graph_score}/25")
            combined = state.get(StepKeys.COMBINED_COMPLEXITY_SCORE)
            if combined:
                log_lines.append(f"- Combined Score: {combined}/25")
        log_lines.append(f"- Context Files: {state.get(StepKeys.FILES_LOADED_COUNT, 0)}")
        log_lines.append(f"- Cache Hit: {state.get(StepKeys.CONTEXT_CACHE_HIT, False)}")
        log_lines.append(f"- TOON: {'OK' if state.get(StepKeys.TOON_SAVED) else 'FAILED'}")
        log_lines.append("")

        # Level 2
        log_lines.append("## Level 2: Standards")
        log_lines.append(f"- Standards Loaded: {state.get(StepKeys.STANDARDS_COUNT, 0)}")
        log_lines.append(f"- Framework Detected: {state.get(StepKeys.DETECTED_FRAMEWORK, 'unknown')}")
        log_lines.append(f"- MCP Discovered: {state.get(StepKeys.MCP_DISCOVERED_COUNT, 0)}")
        log_lines.append(f"- Tool Rules: {'Loaded' if state.get(StepKeys.TOOL_OPTIMIZATION_LOADED) else 'Missing'}")
        log_lines.append(f"- Status: {state.get(StepKeys.LEVEL2_STATUS, 'unknown')}")
        log_lines.append("")

        # Level 3 Steps
        log_lines.append("## Level 3: Execution Steps")
        log_lines.append("")
        log_lines.append("| Step | Name | Status | Duration | Details |")
        log_lines.append("|------|------|--------|----------|---------|")

        step_info = [
            (0, "Task Analysis", "step0_task_type", "step0_complexity"),
            (1, "Plan Mode Decision", "step1_plan_required", "step1_reasoning"),
            (2, "Plan Execution", "step2_plan_status", "step2_phases"),
            (3, "Task Breakdown", "step3_validation_status", "step3_task_count"),
            (4, "TOON Refinement", "step4_refinement_status", "step4_complexity_adjusted"),
            (5, "Skill & Agent Selection", "step5_skill", "step5_agent"),
            (6, "Skill Validation", "step6_validation_status", "step6_skill_ready"),
            (7, "Final Prompt Generation", "step7_prompt_saved", "step7_prompt_size"),
            (8, "GitHub Issue Creation", "step8_status", "step8_issue_url"),
            (9, "Branch Creation", "step9_status", "step9_branch_name"),
            (10, "Implementation", "step10_implementation_status", "step10_llm_invoked"),
            (11, "PR & Code Review", "step11_status", "step11_pr_url"),
            (12, "Issue Closure", "step12_status", "step12_issue_closed"),
            (13, "Documentation", "step13_documentation_status", "step13_update_count"),
            (14, "Final Summary", "step14_status", "step14_voice_sent"),
        ]

        for step_num, name, status_key, detail_key in step_info:
            time_key = f"step{step_num}_execution_time_ms"
            duration_ms = state.get(time_key, 0)
            duration_str = f"{duration_ms:.0f}ms" if duration_ms else "-"

            status_val = state.get(status_key, "")
            detail_val = state.get(detail_key, "")

            # Format detail value
            if isinstance(detail_val, (list, dict)):
                detail_str = f"{len(detail_val)} items" if isinstance(detail_val, list) else f"{len(detail_val)} keys"
            elif isinstance(detail_val, bool):
                detail_str = "Yes" if detail_val else "No"
            elif detail_val is not None:
                detail_str = str(detail_val)[:60]
            else:
                detail_str = "-"

            status_str = str(status_val)[:30] if status_val else "-"
            log_lines.append(f"| {step_num:2d} | {name} | {status_str} | {duration_str} | {detail_str} |")

        log_lines.append("")

        # Selected resources
        log_lines.append("## Selected Resources")
        skills = state.get(StepKeys.SKILLS) or []
        skill = state.get(StepKeys.SKILL, "")
        if skill and skill not in skills:
            skills = [skill] + skills
        agents = state.get(StepKeys.AGENTS) or []
        agent = state.get(StepKeys.AGENT, "")
        if agent and agent not in agents:
            agents = [agent] + agents

        if skills:
            log_lines.append(f"- **Skills**: {', '.join(skills)}")
        if agents:
            log_lines.append(f"- **Agents**: {', '.join(agents)}")
        log_lines.append("")

        # Errors
        errors = state.get(StepKeys.ERRORS) or []
        if errors:
            log_lines.append("## Errors")
            for err in errors[:10]:
                log_lines.append(f"- {err}")
            log_lines.append("")

        # Write to session folder
        log_path = Path(session_dir) / "execution-log.md"
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

    except Exception:
        pass  # Never crash on logging


# ============================================================================
# GRAPH FACTORY
# ============================================================================


def create_flow_graph(hook_mode: bool = False):
    """Create and return the main StateGraph for 3-level flow.

    LangGraph 1.0.10: All nodes flattened into single graph.
    Parallel execution: Multiple edges from START or same source
    achieve automatic parallelization.

    Args:
        hook_mode: If True, skip Steps 8-14 (GitHub workflow) for fast
                   UserPromptSubmit hook execution. Only runs Levels -1/1/2
                   and Steps 0-7 (analysis + prompt generation).
                   Steps 8-14 can be triggered separately after Claude has context.

    Returns:
        Compiled StateGraph instance

    Raises:
        RuntimeError: If LangGraph not installed
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "LangGraph not installed. Install with: " "pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    import sys

    DEBUG = sys.stderr.isatty() or __import__("os").getenv("CLAUDE_DEBUG") == "1"

    # Create graph
    graph = StateGraph(FlowState)

    if DEBUG:
        print("[DEBUG] Creating StateGraph...", file=sys.stderr)

    # ========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT (3 checks, sequential)
    # ========================================================================
    graph.add_node("level_minus1_unicode", node_unicode_fix)
    graph.add_node("level_minus1_encoding", node_encoding_validation)
    graph.add_node("level_minus1_windows", node_windows_path_check)
    graph.add_node("level_minus1_merge", level_minus1_merge_node)

    # Sequential: START -> unicode -> encoding -> windows -> merge
    graph.add_edge(START, "level_minus1_unicode")
    graph.add_edge("level_minus1_unicode", "level_minus1_encoding")
    graph.add_edge("level_minus1_encoding", "level_minus1_windows")
    graph.add_edge("level_minus1_windows", "level_minus1_merge")

    # Add interactive nodes for Level -1 failure handling
    graph.add_node("ask_level_minus1_fix", ask_level_minus1_fix)
    graph.add_node("fix_level_minus1", fix_level_minus1_issues)

    # Route based on Level -1 status
    graph.add_conditional_edges(
        "level_minus1_merge",
        route_after_level_minus1,
        {
            "ask_level_minus1_fix": "ask_level_minus1_fix",
            "level1_session": "level1_session",  # Session loader is first Level 1 node
        },
    )

    # After user choice, route to fix or continue to Level 1
    graph.add_conditional_edges(
        "ask_level_minus1_fix",
        route_after_level_minus1_user_choice,
        {
            "fix_level_minus1": "fix_level_minus1",
            "level1_session": "level1_session",  # Go to Level 1 session loader
        },
    )

    # After fix attempt, always retry Level -1 checks from start
    graph.add_edge("fix_level_minus1", "level_minus1_unicode")

    # ========================================================================
    # LEVEL 1: CONTEXT SYNC (CORRECTED FLOW)
    # ========================================================================
    # Step 1: Session loader MUST be first (creates session container)
    graph.add_node("level1_session", node_session_loader)

    # Step 2: Parallel - Complexity calculation + Context loader
    graph.add_node("level1_complexity", node_complexity_calculation)
    graph.add_node("level1_context", node_context_loader)

    # Both can run after session is created
    graph.add_edge("level1_session", "level1_complexity")
    graph.add_edge("level1_session", "level1_context")

    # Step 3: TOON compression (after both complexity and context complete)
    graph.add_node("level1_toon_compression", node_toon_compression)
    graph.add_edge("level1_complexity", "level1_toon_compression")
    graph.add_edge("level1_context", "level1_toon_compression")

    # Step 4: Merge Level 1 results
    graph.add_node("level1_merge", level1_merge_node)
    graph.add_edge("level1_toon_compression", "level1_merge")

    # Step 5: Memory cleanup (clear verbose variables)
    graph.add_node("level1_cleanup", cleanup_level1_memory)
    graph.add_edge("level1_merge", "level1_cleanup")

    # ========================================================================
    # LEVEL 2: STANDARDS SYSTEM (conditional Java routing)
    # ========================================================================
    graph.add_node("level2_emergency_archive", emergency_archive)
    graph.add_node("level2_common_standards", node_common_standards)
    graph.add_node("level2_java_standards", node_java_standards)
    graph.add_node("level2_tool_optimization", node_tool_optimization_standards)
    graph.add_node("level2_mcp_discovery", node_mcp_plugin_discovery)
    graph.add_node("level2_merge", level2_merge_node)

    # Route from Level 1 cleanup to Level 2
    # Emergency archive check happens inside common_standards node start
    # Tool optimization and MCP discovery run in parallel
    graph.add_edge("level1_cleanup", "level2_emergency_archive")
    graph.add_edge("level1_cleanup", "level2_tool_optimization")
    graph.add_edge("level1_cleanup", "level2_mcp_discovery")

    # Emergency archive always routes to common standards
    # (archive is a no-op if context usage is below threshold)
    graph.add_edge("level2_emergency_archive", "level2_common_standards")

    # Common standards check for Java
    graph.add_conditional_edges(
        "level2_common_standards",
        route_standards_loading,
        {
            "level2_java_standards": "level2_java_standards",
            "level2_merge": "level2_merge",
        },
    )

    # Java standards, tool optimization, and MCP discovery all merge
    graph.add_edge("level2_java_standards", "level2_merge")
    graph.add_edge("level2_tool_optimization", "level2_merge")
    graph.add_edge("level2_mcp_discovery", "level2_merge")

    # Standards selector: auto-detect project type + framework, load all standards
    graph.add_node("level2_select_standards", level2_select_standards_node)
    graph.add_edge("level2_merge", "level2_select_standards")

    # Optimize context after Level 2 (compress for Level 3 consumption)
    graph.add_node("level2_optimize_context", optimize_context_after_level2)
    graph.add_edge("level2_select_standards", "level2_optimize_context")

    # ========================================================================
    # LEVEL 3: EXECUTION SYSTEM - 14-STEP PIPELINE (v2 WORKFLOW.MD COMPLIANT)
    # ========================================================================

    # Bridge node: session_path -> session_dir
    graph.add_node("level3_init", level3_init_node)
    graph.add_edge("level2_optimize_context", "level3_init")

    # Pre-analysis gate: call graph scan + RAG orchestration lookup
    # On template fast-path (--orchestration-template): jumps to level3_step6, skipping steps 0-5
    # On RAG hit (confidence >= 0.85): jumps to level3_step5, skipping steps 0-4
    # On miss: falls through to level3_step0_0 (normal pre-flight flow)
    graph.add_node("level3_pre_analysis", orchestration_pre_analysis_node)
    graph.add_edge("level3_init", "level3_pre_analysis")
    graph.add_conditional_edges(
        "level3_pre_analysis",
        route_pre_analysis,
        {
            "level3_step0_0": "level3_step0_0",
            "level3_step5": "level3_step5",
            "level3_step6": "level3_step6",
        },
    )

    # Step 0.0: Pre-flight - Project Context (README, CHANGELOG, etc.)
    graph.add_node("level3_step0_0", step0_0_project_context_node)

    # Step 0.1: Pre-flight - Initial CallGraph Snapshot (baseline for Step 11 diff)
    graph.add_node("level3_step0_1", step0_1_initial_callgraph_node)
    graph.add_edge("level3_step0_0", "level3_step0_1")

    # Step 0: Task Analysis (MUST run before Step 1 - provides task_type, complexity, tasks)
    graph.add_node("level3_step0", step0_task_analysis_node)
    graph.add_edge("level3_step0_1", "level3_step0")

    # Standards integration hook: Step 1 - before plan mode decision
    graph.add_node("level3_standards_hook_step1", apply_integration_step1)
    graph.add_edge("level3_step0", "level3_standards_hook_step1")

    # Step 1: Plan Mode Decision (LOCAL LLM - Ollama)
    graph.add_node("level3_step1", step1_plan_mode_decision_node)
    graph.add_edge("level3_standards_hook_step1", "level3_step1")

    # CONDITIONAL: plan_required → step2 | direct → step3
    graph.add_conditional_edges(
        "level3_step1",
        route_after_step1_decision,
        {
            "level3_step2": "level3_step2",
            "level3_step3": "level3_step3",
        },
    )

    # Standards integration hook: Step 2 - during plan execution
    graph.add_node("level3_standards_hook_step2", apply_integration_step2)

    # Step 2: Plan Execution (only when plan_required=True)
    graph.add_node("level3_step2", step2_plan_execution_node)
    graph.add_edge("level3_step2", "level3_standards_hook_step2")
    graph.add_edge("level3_standards_hook_step2", "level3_step3")

    # Step 3: Task Breakdown
    graph.add_node("level3_step3", step3_task_breakdown_node)

    # Standards integration hook: Step 3 - validate task breakdown against standards
    graph.add_node("level3_standards_hook_step3", apply_integration_step3)
    graph.add_edge("level3_step3", "level3_standards_hook_step3")

    # Step 4: TOON Refinement
    graph.add_node("level3_step4", step4_toon_refinement_node)
    graph.add_edge("level3_standards_hook_step3", "level3_step4")

    # Standards integration hook: Step 4 - validate TOON context against standards
    graph.add_node("level3_standards_hook_step4", apply_integration_step4)
    graph.add_edge("level3_step4", "level3_standards_hook_step4")

    # Step 5: Skill & Agent Selection (LOCAL LLM + filesystem scan)
    graph.add_node("level3_step5", step5_skill_selection_node)
    graph.add_edge("level3_standards_hook_step4", "level3_step5")

    # Standards integration hook: Step 5 - after skill selection (validates skill vs project)
    graph.add_node("level3_standards_hook_step5", apply_integration_step5)
    graph.add_edge("level3_step5", "level3_standards_hook_step5")

    # Step 6: Skill Validation & Download (RESTORED)
    graph.add_node("level3_step6", step6_skill_validation_node)
    graph.add_edge("level3_standards_hook_step5", "level3_step6")

    # Standards integration hook: Step 6 - validate downloaded skill compatibility
    graph.add_node("level3_standards_hook_step6", apply_integration_step6)
    graph.add_edge("level3_step6", "level3_standards_hook_step6")

    # Step 7: Final Prompt Generation (LOCAL LLM)
    graph.add_node("level3_step7", step7_final_prompt_node)
    graph.add_edge("level3_standards_hook_step6", "level3_step7")

    # Standards integration hook: Step 7 - validate prompt includes standards context
    graph.add_node("level3_standards_hook_step7", apply_integration_step7)
    graph.add_edge("level3_step7", "level3_standards_hook_step7")

    # ========================================================================
    # STEPS 8-9: Issue + Branch Creation (runs in BOTH hook and full mode)
    # These create the GitHub issue and feature branch BEFORE Claude works
    # ========================================================================

    # Step 8: GitHub Issue Creation
    graph.add_node("level3_step8", step8_github_issue_node)
    graph.add_edge("level3_standards_hook_step7", "level3_step8")

    # Step 9: Branch Creation (issue-42-bug format)
    graph.add_node("level3_step9", step9_branch_creation_node)
    graph.add_edge("level3_step8", "level3_step9")

    # ========================================================================
    # HOOK MODE: After Steps 8-9, go to output
    # Step 10 = Claude Code itself (the LLM reading this prompt and working)
    # Steps 11-14 = run in Stop hook after Claude finishes working
    # ========================================================================
    if hook_mode:
        graph.add_node("level3_merge", level3_v2_merge_node)
        graph.add_edge("level3_step9", "level3_merge")

        graph.add_node("level3_output", output_node)
        graph.add_edge("level3_merge", "level3_output")
        graph.add_edge("level3_output", END)

        try:
            checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
            compiled_graph = graph.compile(checkpointer=checkpointer)
        except Exception:
            compiled_graph = graph.compile()
        return compiled_graph

    # ========================================================================
    # FULL MODE: Steps 10-14 (implementation + PR + merge + close)
    # Only used when running pipeline standalone (not as hook)
    # ========================================================================

    # Step 10: Implementation (in full mode, calls hybrid_inference)
    graph.add_node("level3_step10", step10_implementation_note)
    graph.add_edge("level3_step9", "level3_step10")

    # Standards integration hook: Step 10 (code review) - builds compliance checklist
    # Runs after step10, before step11, so PR review has the checklist available
    graph.add_node("level3_standards_hook_step10", apply_integration_step10)
    graph.add_edge("level3_step10", "level3_standards_hook_step10")

    # Step 11: PR Creation & Merge
    graph.add_node("level3_step11", step11_pull_request_node)
    graph.add_edge("level3_standards_hook_step10", "level3_step11")

    # Step 11 → Conditional Routing (retry loop or continue to closure)
    # Retry goes through increment node first (state mutations only in nodes)
    graph.add_node("level3_step11_retry", step11_retry_increment_node)
    graph.add_edge("level3_step11_retry", "level3_step10")

    graph.add_conditional_edges(
        "level3_step11",
        route_after_step11_review,
        {
            "level3_step12": "level3_step12",  # Review passed or max retries reached
            "level3_step11_retry": "level3_step11_retry",  # Review failed, increment then retry
        },
    )

    # Step 12: Issue Closure
    graph.add_node("level3_step12", step12_issue_closure_node)

    # Step 13: Documentation Update
    graph.add_node("level3_step13", step13_docs_update_node)
    graph.add_edge("level3_step12", "level3_step13")

    # Standards integration hook: Step 13 - documentation requirements from standards
    graph.add_node("level3_standards_hook_step13", apply_integration_step13)
    graph.add_edge("level3_step13", "level3_standards_hook_step13")

    # Step 14: Final Summary + Voice Notification
    graph.add_node("level3_step14", step14_final_summary_node)
    graph.add_edge("level3_standards_hook_step13", "level3_step14")

    # Merge node
    graph.add_node("level3_merge", level3_v2_merge_node)
    graph.add_edge("level3_step14", "level3_merge")

    # ========================================================================
    # OUTPUT
    # ========================================================================
    graph.add_node("level3_output", output_node)
    graph.add_edge("level3_merge", "level3_output")
    graph.add_edge("level3_output", END)

    # Compile graph with SqliteSaver checkpointer for state persistence
    # Enables resume from any step if pipeline is interrupted
    try:
        checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
        compiled_graph = graph.compile(checkpointer=checkpointer)
    except Exception:
        # Fallback to no checkpointer if SQLite setup fails
        compiled_graph = graph.compile()
    return compiled_graph


def create_initial_state(session_id: str = "", project_root: str = "", user_message: str = "") -> FlowState:
    """Create initial FlowState for a new execution.

    CRITICAL DESIGN RULE - PROMPT INTEGRITY:
    - user_message is ORIGINAL user prompt - NEVER modify or regenerate
    - All analysis steps (Steps 0-11) work on COPIES of user_message
    - Original user_message sent to Claude AS-IS without any modification
    - No prompt enhancement, no regeneration, no intermediate LLM processing

    Args:
        session_id: Session identifier (auto-generated if empty)
        project_root: Project directory path
        user_message: User's actual task/request (IMMUTABLE)

    Returns:
        Initialized FlowState with UNMODIFIED user message for Claude
    """
    # **CRITICAL FIX**: Set project_root FIRST (before any immutable field is created)
    # project_root is Annotated[_keep_first_value] so once set, it can't change
    # We must set it to the correct value BEFORE creating the state
    import os
    import sys

    print(f"[CREATE_INITIAL_STATE] Input project_root: '{project_root}'", file=sys.stderr)
    if not project_root:
        # Use cwd from hook event or actual cwd - NOT hardcoded path
        project_root = os.environ.get("CLAUDE_CWD", str(Path.cwd()))
        print(f"[CREATE_INITIAL_STATE] Set project_root from cwd: {project_root}", file=sys.stderr)
    print(f"[CREATE_INITIAL_STATE] Final project_root before state creation: {project_root}", file=sys.stderr)

    # session_id is set by node_session_loader (Level 1) - NOT here
    # It's immutable (_keep_first_value), so if set here it blocks Level 1 from setting it
    # Only set here if explicitly passed (e.g., from CLI --session-id=)

    # ONLY initialize immutable fields (with _keep_first_value reducer)
    # All other fields will be created/updated by nodes
    initial_state = FlowState(
        # Immutable session info - session_id left for node_session_loader unless provided
        **({"session_id": session_id} if session_id else {}),
        timestamp=datetime.now().isoformat(),
        project_root=project_root,
        # User input - NEVER MODIFIED - this is the original prompt for Claude
        user_message=user_message,
        user_message_original=user_message,  # Backup of original - for integrity verification
        user_message_length=len(user_message) if user_message else 0,
        # Other fields will be added by nodes as needed
    )

    # Verify project_root was set correctly
    print(
        f"[CREATE_INITIAL_STATE] After FlowState creation: project_root='{initial_state.get('project_root', 'MISSING')}'",
        file=sys.stderr,
    )

    return initial_state


def invoke_flow(
    session_id: str = "",
    project_root: str = "",
    user_message: str = "",
) -> FlowState:
    """Convenience function to create and invoke flow in one call.

    Args:
        session_id: Session identifier
        project_root: Project directory
        user_message: User's actual task/request

    Returns:
        Final FlowState after execution
    """
    initial_state = create_initial_state(session_id, project_root, user_message)
    graph = create_flow_graph()

    from .checkpointer import get_invoke_config

    config = get_invoke_config(initial_state["session_id"])
    # Set very high recursion limit to debug infinite loops
    config["recursion_limit"] = 1000

    result = graph.invoke(initial_state, config=config)
    return result


def resume_flow(
    session_id: str,
    checkpoint_id: Optional[str] = None,
) -> bool:
    """
    Resume an interrupted pipeline execution from a saved checkpoint.

    Loads the checkpoint state, installs signal handlers, and replays
    remaining steps (step_number+1 through 14) using the LangGraph graph.

    Usage:
        # Resume from last checkpoint
        resume_flow(session_id="flow-abc12345")

        # Resume from specific step checkpoint
        resume_flow(session_id="flow-abc12345", checkpoint_id="flow-abc12345:step-05")

    Args:
        session_id:    Session to resume.
        checkpoint_id: Optional specific checkpoint ID.  When None, the most
                       recent checkpoint for the session is used.

    Returns:
        True if resumed successfully.
    """
    from .recovery_handler import resume_from_checkpoint

    print(f"[Resume] Loading checkpoint for session: {session_id}", file=sys.stderr)
    if checkpoint_id:
        print(f"[Resume] Using checkpoint: {checkpoint_id}", file=sys.stderr)

    # RecoveryHandler.resume_session() handles loading + replaying steps.
    # We pass None as step_executor; the RecoveryHandler will use
    # its checkpoint_manager to iterate remaining steps.
    # For full LangGraph re-invocation, the caller should invoke the graph
    # manually with the loaded state.  This path uses the simple sequential
    # step executor (adequate for most recovery scenarios).
    success = resume_from_checkpoint(
        session_id=session_id,
        step_executor=None,  # No-op executor (returns loaded state only)
        checkpoint_id=checkpoint_id,
    )
    return success


# ---------------------------------------------------------------------------
# Optional type import (avoid polluting namespace at top level)
# ---------------------------------------------------------------------------
from typing import Optional  # noqa: E402 - placed after functions intentionally
