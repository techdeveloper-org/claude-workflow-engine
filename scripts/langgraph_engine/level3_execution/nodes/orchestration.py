# ruff: noqa: F821
"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.
"""
import sys
from pathlib import Path
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


def orchestration_pre_analysis_node(state: FlowState) -> Dict[str, Any]:
    """Pre-analysis gate: call graph context + RAG orchestration lookup.

    Executes BEFORE Step 0.0 (project context). Two responsibilities:

    1. Call graph scan: identify hot nodes (5+ callers) and leaf nodes
       (0 callers). Results are stored as call_graph_metrics so Step 0
       can adjust its complexity score without an extra LLM call.

    2. RAG orchestration lookup: check if a similar past task's agent
       roster and phase plan can be reused (threshold 0.85).  On hit,
       skip_architecture and skip_consensus flags are set so route_pre_analysis
       can bypass Steps 0-4 and jump directly to Step 5 (skill selection).

    Always fail-open: any exception returns empty metrics without blocking
    the pipeline.
    """
    import time as _t

    _start = _t.time()

    result: Dict[str, Any] = {
        "pre_analysis_result": {},
        "call_graph_metrics": {},
        "rag_orchestration_hit": False,
        "rag_orchestration_confidence": 0.0,
        "rag_orchestration_cached_plan": {},
        "skip_architecture": False,
        "skip_consensus": False,
        "template_fast_path": False,
    }

    # --- 0. Orchestration Template Fast-Path (highest priority) ---
    # If user provided --orchestration-template, bypass ALL LLM analysis (Steps 0-5)
    # and jump directly to Step 6 (skill validation + download).
    template = state.get("orchestration_template") or {}
    if template:
        try:
            # Map template fields -> FlowState step outputs
            result["step0_task_type"] = template.get("task_type", "General Task")
            result["step0_complexity"] = int(template.get("complexity", 5))
            result["step0_reasoning"] = template.get("reasoning", "Pre-filled via orchestration template")
            result["step0_tasks"] = {
                "count": len(template.get("tasks", [])),
                "tasks": template.get("tasks", []),
            }
            result["step0_task_count"] = len(template.get("tasks", []))
            result["step1_plan_required"] = bool(template.get("plan_required", False))
            result["step3_tasks_validated"] = template.get("tasks", [])
            # Single skill/agent (primary) + multi lists
            result["step5_skill"] = template.get("skill") or (template.get("skills") or [""])[0]
            result["step5_agent"] = template.get("agent") or (template.get("agents") or [""])[0]
            result["step5_skills"] = template.get("skills") or ([template["skill"]] if template.get("skill") else [])
            result["step5_agents"] = template.get("agents") or ([template["agent"]] if template.get("agent") else [])
            # If system_prompt provided, write it to session dir so Step 10 can use it directly
            system_prompt_text = template.get("system_prompt", "")
            if system_prompt_text:
                try:
                    session_dir = state.get("session_dir", "")
                    if session_dir:
                        sp_file = Path(session_dir) / "system_prompt.txt"
                        sp_file.parent.mkdir(parents=True, exist_ok=True)
                        sp_file.write_text(system_prompt_text, encoding="utf-8")
                        result["step7_system_prompt_file"] = str(sp_file)
                        result["step7_system_prompt_loaded"] = True
                        logger.info("[v2] Template system_prompt written to %s", sp_file)
                except Exception as sp_err:
                    logger.debug("[v2] Template system_prompt write skipped: %s", sp_err)
            # Mark fast-path active
            result["template_fast_path"] = True
            result["skip_architecture"] = True
            result["skip_consensus"] = True
            elapsed = (_t.time() - _start) * 1000
            result["pre_analysis_execution_time_ms"] = round(elapsed, 1)
            print(
                "[PRE-ANALYSIS] TEMPLATE FAST-PATH: task_type=%s complexity=%d skill=%s agent=%s -> jumping to Step 6"
                % (result["step0_task_type"], result["step0_complexity"], result["step5_skill"], result["step5_agent"]),
                file=sys.stderr,
            )
            logger.info(
                "[v2] Template fast-path active: %s complexity=%d -> level3_step6",
                result["step0_task_type"],
                result["step0_complexity"],
            )
            return result
        except Exception as tmpl_exc:
            logger.warning("[v2] Template fast-path failed, falling back to normal flow: %s", tmpl_exc)
            result["template_fast_path"] = False

    # --- 1. Call Graph Scan ---
    try:
        from ..call_graph_analyzer import get_orchestration_context

        project_root = state.get("project_root", ".")
        task_desc = state.get("user_message", "")
        graph_ctx = get_orchestration_context(
            task_description=task_desc,
            project_root=project_root,
        )
        result["call_graph_metrics"] = graph_ctx
        result["pre_analysis_result"] = graph_ctx
        if graph_ctx.get("call_graph_available"):
            hot_count = len(graph_ctx.get("hot_nodes", []))
            leaf_count = len(graph_ctx.get("leaf_nodes", []))
            boost = graph_ctx.get("complexity_boost", 0)
            logger.info(
                "[v2] Pre-analysis CallGraph: hot=%d leaf=%d boost=%+d",
                hot_count,
                leaf_count,
                boost,
            )
            print(
                "[PRE-ANALYSIS] CallGraph: hot=%d leaf=%d complexity_boost=%+d" % (hot_count, leaf_count, boost),
                file=sys.stderr,
            )
    except Exception as cg_exc:
        logger.debug("[v2] Pre-analysis call graph scan skipped: %s", cg_exc)

    # --- 2. RAG Orchestration Lookup ---
    try:
        from ..rag_integration import rag_lookup_orchestration

        task_desc = state.get("user_message", "")
        # Simple project name from path tail
        proj_root = state.get("project_root", "") or ""
        proj_name = proj_root.replace("\\", "/").rstrip("/").split("/")[-1]

        # Lightweight structural fingerprint to prevent cross-project RAG false positives.
        # Two tasks with identical text (e.g. "Add login to dashboard") in different
        # projects would otherwise get a 0.95 RAG score and inject the wrong blueprint.
        try:
            from ..rag_integration import _compute_codebase_hash as _cbh

            _codebase_hash = _cbh(proj_root)
        except Exception:
            _codebase_hash = ""

        context = {
            "project": proj_name,
            "task_hash": str(hash(task_desc[:100]) & 0xFFFFFF),
            "framework": state.get("detected_framework", ""),
            "codebase_hash": _codebase_hash,
        }
        rag_result = rag_lookup_orchestration(
            task=task_desc,
            context=context,
            state=dict(state),
        )
        if rag_result.get("hit"):
            confidence = rag_result.get("confidence", 0.0)
            cached = rag_result.get("cached_plan", {})
            result["rag_orchestration_hit"] = True
            result["rag_orchestration_confidence"] = confidence
            result["rag_orchestration_cached_plan"] = cached
            result["skip_architecture"] = True
            result["skip_consensus"] = True
            # Inject cached step0 data so downstream steps receive correct context
            for key in (
                "step0_task_type",
                "step0_complexity",
                "step0_reasoning",
                "step1_plan_required",
                "step3_tasks_validated",
                "step5_skill",
                "step5_agent",
            ):
                if cached.get(key) is not None:
                    result[key] = cached[key]
            print(
                "[PRE-ANALYSIS] RAG HIT (confidence=%.2f) - skipping architecture phases" % confidence,
                file=sys.stderr,
            )
            logger.info(
                "[v2] Pre-analysis RAG HIT confidence=%.2f source_session=%s",
                confidence,
                rag_result.get("session_id", ""),
            )
        else:
            print("[PRE-ANALYSIS] RAG MISS - running full pipeline", file=sys.stderr)
    except Exception as rag_exc:
        logger.debug("[v2] Pre-analysis RAG lookup skipped: %s", rag_exc)

    elapsed = (_t.time() - _start) * 1000
    result["pre_analysis_execution_time_ms"] = round(elapsed, 1)
    return result


def route_pre_analysis(state: FlowState) -> str:
    """Route after orchestration_pre_analysis_node.

    TEMPLATE FAST-PATH (highest priority, template_fast_path=True):
        -> "level3_step6"  (skill validation, bypassing steps 0-5 entirely)

    RAG HIT (confidence >= 0.85, skip_architecture set):
        -> "level3_step5"  (skill selection, bypassing steps 0-4)

    RAG MISS or call graph unavailable:
        -> "level3_step0_0"  (normal pre-flight flow)
    """
    if state.get("template_fast_path"):
        logger.info("[v2] Pre-analysis route: TEMPLATE FAST-PATH -> level3_step6")
        return "level3_step6"
    if state.get("rag_orchestration_hit") and state.get("skip_architecture"):
        logger.info("[v2] Pre-analysis route: RAG HIT -> level3_step5")
        return "level3_step5"
    return "level3_step0_0"


# ============================================================================
# ROUTING FUNCTIONS - Pass-through to core routing logic
# ============================================================================


def route_to_plan_or_breakdown(state: FlowState) -> str:
    """Route after Step 1 plan decision."""
    from ..routing import route_after_step1_plan_decision

    return route_after_step1_plan_decision(state)


def route_to_closure_or_retry(state: FlowState) -> str:
    """Route after Step 11 PR review."""
    from ..routing import route_after_step11_review

    return route_after_step11_review(state)


# ============================================================================
# MERGE NODE - Final status determination
# ============================================================================


def level3_v2_merge_node(state):
    """Re-export merge node from routing module."""
    from ..routing import level3_merge_node

    return level3_merge_node(state)
