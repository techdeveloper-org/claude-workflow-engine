# ruff: noqa: F821
"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.

CHANGE LOG (v1.13.0):
  route_pre_analysis: template_fast_path now routes to "level3_step8"
  (previously routed to "level3_step6" and "level3_step5").
  Steps 5-7 no longer exist in the graph; Step 8 is the new post-Step-0 target.
  route_to_plan_or_breakdown removed (Step 1 no longer exists in graph).
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
    """Pre-analysis gate: call graph context scan.

    Executes BEFORE Step 0.0 (project context). Responsibilities:

    1. Call graph scan: identify hot nodes (5+ callers) and leaf nodes
       (0 callers). Results are stored as call_graph_metrics so Step 0
       can adjust its complexity score without an extra LLM call.

    2. Orchestration Template Fast-Path: if user provided
       --orchestration-template, inject pre-filled fields and route
       directly to Step 8 (GitHub issue creation), bypassing Step 0.

    Always fail-open: any exception returns empty metrics without blocking
    the pipeline.
    """
    import time as _t

    _start = _t.time()

    result: Dict[str, Any] = {
        "pre_analysis_result": {},
        "call_graph_metrics": {},
        "template_fast_path": False,
    }

    # --- 0. Orchestration Template Fast-Path (highest priority) ---
    # If user provided --orchestration-template, bypass ALL LLM analysis (Step 0)
    # and jump directly to Step 8 (GitHub issue creation).
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
            # Skill/agent ready defaults (Steps 6 collapsed)
            result["step6_skill_ready"] = True
            result["step6_agent_ready"] = True
            result["step6_validation_status"] = "OK"
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
                        result["step7_execution_prompt"] = system_prompt_text
                        result["step7_prompt_saved"] = True
                        logger.info("[v2] Template system_prompt written to %s", sp_file)
                except Exception as sp_err:
                    logger.debug("[v2] Template system_prompt write skipped: %s", sp_err)
            # Mark fast-path active
            result["template_fast_path"] = True
            elapsed = (_t.time() - _start) * 1000
            result["pre_analysis_execution_time_ms"] = round(elapsed, 1)
            print(
                "[PRE-ANALYSIS] TEMPLATE FAST-PATH: task_type=%s complexity=%d skill=%s agent=%s -> jumping to Step 8"
                % (result["step0_task_type"], result["step0_complexity"], result["step5_skill"], result["step5_agent"]),
                file=sys.stderr,
            )
            logger.info(
                "[v2] Template fast-path active: %s complexity=%d -> level3_step8",
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

    print("[PRE-ANALYSIS] running full pipeline", file=sys.stderr)

    elapsed = (_t.time() - _start) * 1000
    result["pre_analysis_execution_time_ms"] = round(elapsed, 1)
    return result


def route_pre_analysis(state: FlowState) -> str:
    """Route after orchestration_pre_analysis_node.

    TEMPLATE FAST-PATH (highest priority, template_fast_path=True):
        -> "level3_step8"  (GitHub issue creation, bypassing Step 0 entirely)

    Normal path:
        -> "level3_step0_0"  (pre-flight flow through Step 0)
    """
    if state.get("template_fast_path"):
        logger.info("[v2] Pre-analysis route: TEMPLATE FAST-PATH -> level3_step8")
        return "level3_step8"
    return "level3_step0_0"


# ============================================================================
# ROUTING FUNCTIONS - Pass-through to core routing logic
# ============================================================================


# REMOVED: route_to_plan_or_breakdown (v1.13.0)
# This routing function was used by Step 1 (Plan Mode Decision) to choose between
# Step 2 and Step 3. Since Step 1 is removed from the graph, this routing function
# is no longer needed. Kept as a stub to avoid breaking any test imports.


def route_to_plan_or_breakdown(state: FlowState) -> str:
    """DEPRECATED (v1.13.0): Step 1 no longer exists in the graph.

    Returns "level3_step8" as a safe no-op default.
    This stub preserves backward compatibility for any tests that import it.
    """
    logger.warning("[v2] route_to_plan_or_breakdown called but Step 1 no longer exists (v1.13.0)")
    return "level3_step8"


def route_to_closure_or_retry(state: FlowState) -> str:
    """Route after Step 11 PR review."""
    from ..routing import route_after_step11_review

    return route_after_step11_review(state)


# ============================================================================
# MERGE NODE - Final status determination
# ============================================================================


def level3_merge_node(state):
    """Re-export merge node from routing module."""
    from ..routing import level3_merge_node

    return level3_merge_node(state)
