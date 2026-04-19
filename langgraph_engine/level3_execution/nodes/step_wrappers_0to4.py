"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.

CHANGE LOG (v1.13.0):
  Removed Steps 1, 3, 4 node wrappers -- collapsed into Step 0 template call.
  Step 0 now injects combined_complexity_score (1-25 from Level 1) and
  CallGraph analysis into the template context before the subprocess calls.
  Step 0 output populates the fields that Steps 1,3,4,5,6,7 previously provided.

CHANGE LOG (v1.14.0):
  Step 0 caller scripts now use claude CLI subprocess (not direct llm_call API).
  Step 2 (plan execution) removed from pipeline -- orchestrator subprocess
  already produces a comprehensive plan. step2_plan_execution_node kept as
  deprecated no-op for backward compatibility with test imports.
"""

import os
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

from ..helpers import call_streaming_script


def step0_task_analysis_node(state: FlowState) -> Dict[str, Any]:
    """Step 0 v2: prompt_gen_expert -> orchestrator_agent chain.

    Phase 1: calls prompt_gen_expert_caller (fast, captured stdout) to build
    an orchestration prompt enriched with combined_complexity_score and
    CallGraph risk data. Uses claude CLI subprocess internally.

    Phase 2: calls orchestrator_agent_caller (long-running, stderr streamed
    live) with the orchestration prompt written to a temp file so the user
    sees real-time agent progress. Uses claude CLI subprocess internally.

    Post-call: populates migration fields so Steps 8-14 receive correct data.
    """
    import json as _json
    import tempfile

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"

    # --- PRE-INJECTION A: combined_complexity_score from Level 1 (1-25 scale) ---
    # Do NOT re-compute; read directly from state. Scale is 1-25, not 1-10.
    complexity_score = state.get("combined_complexity_score", 5)

    # --- PRE-INJECTION B: CallGraph impact analysis ---
    call_graph_risk_level = "LOW"
    call_graph_danger_zones = []
    call_graph_affected_methods = []
    try:
        from ..call_graph_analyzer import analyze_impact_before_change

        project_root = state.get("project_root", ".")
        target_files = state.get("step0_target_files", [])
        task_desc = state.get("user_message", "")
        cg_result = analyze_impact_before_change(project_root, target_files, task_desc)
        if cg_result.get("call_graph_available"):
            call_graph_risk_level = cg_result.get("risk_level", "LOW")
            call_graph_danger_zones = cg_result.get("danger_zones", [])
            call_graph_affected_methods = cg_result.get("affected_methods", [])
            logger.info(
                "[v2] Step 0 CallGraph pre-injection: risk=%s danger_zones=%d affected=%d",
                call_graph_risk_level,
                len(call_graph_danger_zones),
                len(call_graph_affected_methods),
            )
    except Exception as _cg_exc:
        logger.debug("[v2] Step 0 CallGraph pre-injection skipped (fail-open): %s", _cg_exc)

    user_message = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

    # --- PHASE 1: prompt_gen_expert_caller (claude CLI subprocess) ---
    os.environ.setdefault("STEP0_PROMPT_GEN_TIMEOUT", "60")
    prompt_gen_args = [
        user_message,
        "--complexity=%s" % complexity_score,
        "--call-graph-risk=%s" % call_graph_risk_level,
        "--danger-zones=%s" % _json.dumps(call_graph_danger_zones),
        "--affected-methods=%s" % _json.dumps(call_graph_affected_methods),
    ]

    # call_execution_script does not have __func__; use it directly but override timeout via env
    _orig_timeout_env = os.environ.get("STEP0_PROMPT_GEN_TIMEOUT")
    try:
        # Re-import to avoid circular; helpers module already imported at top
        import importlib as _il

        _helpers_mod = _il.import_module("langgraph_engine.level3_execution.helpers")
        _call_execution_script = _helpers_mod.call_execution_script
    except Exception:
        from ..helpers import call_execution_script as _call_execution_script  # noqa: PLC0415

    prompt_gen_raw = _call_execution_script(
        "prompt_gen_expert_caller",
        prompt_gen_args,
        model_tier="fast",
    )

    orchestration_prompt = prompt_gen_raw.get("orchestration_prompt", "")
    if not orchestration_prompt:
        # Fallback: use user_message directly
        orchestration_prompt = user_message
        logger.warning("[v2] Step 0 prompt_gen_expert_caller returned no orchestration_prompt; using raw task")
    else:
        logger.info("[v2] Step 0 prompt_gen_expert_caller: orchestration_prompt length=%d", len(orchestration_prompt))

    # --- PHASE 2: orchestrator_agent_caller (claude CLI subprocess, streaming stderr) ---
    _EXECUTION_WRAPPER = (
        "You are orchestrator-agent. Below is a fully generated orchestration prompt "
        "with a MULTI-AGENT PROMPT BUNDLE containing per-agent execution prompts.\n\n"
        "YOUR EXECUTION PROTOCOL:\n"
        "1. Break down the task into multiple TODOs from the orchestration plan below.\n"
        "2. Each TODO must carry its full context from this prompt -- do not lose detail.\n"
        "3. Execute TODOs in parallel where the plan allows (respect Parallel Groups "
        "and Sequential Chain from the EXECUTION SUMMARY).\n"
        "4. For each TODO, use the corresponding agent's prompt from the "
        "MULTI-AGENT PROMPT BUNDLE verbatim -- do not rewrite or summarize it.\n"
        "5. Apply MODEL FALLBACK PROTOCOL: sonnet -> opus -> escalate to user on rate limits.\n\n"
        "--- BEGIN ORCHESTRATION PROMPT ---\n\n"
    )
    _full_prompt = _EXECUTION_WRAPPER + orchestration_prompt + "\n\n--- END ORCHESTRATION PROMPT ---"

    orch_result: Dict[str, Any] = {}
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as _tf:
            _tf.write(_full_prompt)
            _prompt_file = _tf.name

        if DEBUG:
            logger.debug("[v2] Step 0 orchestration prompt written to %s", _prompt_file)

        orch_args = [
            "--orchestration-prompt-file=%s" % _prompt_file,
            "--session-dir=%s" % state.get("session_dir", ""),
            "--project-root=%s" % state.get("project_root", "."),
        ]

        orch_result = call_streaming_script("orchestrator_agent_caller", orch_args)

        if not orch_result.get("success", True):
            logger.warning(
                "[v2] Step 0 orchestrator_agent_caller non-success: %s",
                orch_result.get("error", "unknown"),
            )
    except Exception as _orch_exc:
        logger.warning("[v2] Step 0 orchestrator_agent_caller failed (fail-open): %s", _orch_exc)
        orch_result = {"success": False, "error": str(_orch_exc)}
    finally:
        try:
            Path(_prompt_file).unlink(missing_ok=True)
        except Exception:
            pass

    # --- Build result from orchestrator output + migration fields ---
    result = _map_step0_result_to_state(state, orchestration_prompt, orch_result)

    # Store the injected context for observability
    result["step0_call_graph_risk_level"] = call_graph_risk_level
    result["step0_call_graph_danger_zones_count"] = len(call_graph_danger_zones)
    result["step0_call_graph_affected_methods_count"] = len(call_graph_affected_methods)
    result["step0_complexity_injected"] = complexity_score
    result["orchestration_prompt"] = orchestration_prompt
    result["orchestrator_result"] = orch_result

    # Apply call graph complexity boost from orchestration_pre_analysis_node
    # (legacy boost path -- pre_analysis uses 1-10 scale boost on top of step0_complexity)
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


def _map_step0_result_to_state(
    state: FlowState,
    orchestration_prompt: str,
    orch_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Map orchestrator_agent_caller output to FlowState migration fields.

    Populates all fields that Steps 1, 3, 4, 5, 6, 7 previously wrote so that
    Steps 8-14 continue to receive the correct state keys regardless of which
    orchestration path produced the data.

    Args:
        state: Current pipeline state (read-only reference for fallback values).
        orchestration_prompt: The prompt text produced by prompt_gen_expert_caller.
        orch_result: Parsed JSON dict returned by orchestrator_agent_caller.

    Returns:
        A flat dict of state updates ready to merge into FlowState.
    """
    result: Dict[str, Any] = {}

    # Core Step 0 fields
    result["step0_task_type"] = orch_result.get("task_type", "General Task")
    result["step0_complexity"] = orch_result.get("complexity", 5)
    result["step0_reasoning"] = orch_result.get("reasoning", "")
    raw_tasks = orch_result.get("tasks", {})
    result["step0_tasks"] = raw_tasks if isinstance(raw_tasks, dict) else {"count": 1, "tasks": []}
    result["step0_task_count"] = orch_result.get("task_count", 1)
    result["step0_error"] = orch_result.get("error") if not orch_result.get("success", True) else None

    # From Step 1: plan_required decision (always False -- Step 2 removed in v1.14.0)
    result.setdefault("step1_plan_required", False)

    # From Step 3: validated task list
    if isinstance(raw_tasks, dict):
        task_list = raw_tasks.get("tasks", [])
    else:
        task_list = []
    result.setdefault("step3_tasks_validated", task_list)

    # From Step 4: model selection
    result.setdefault("step4_model", orch_result.get("model_recommendation", "complex_reasoning"))

    # From Step 5: skill and agent selection
    result.setdefault("step5_skill", orch_result.get("selected_skill", ""))
    result.setdefault("step5_agent", orch_result.get("selected_agent", ""))
    result.setdefault("step5_skills", orch_result.get("skills", []))
    result.setdefault("step5_agents", orch_result.get("agents", []))
    result.setdefault("step5_skill_definition", orch_result.get("skill_definition", ""))
    result.setdefault("step5_agent_definition", orch_result.get("agent_definition", ""))

    # From Step 6: skill readiness (always True -- orchestrator already validated)
    result.setdefault("step6_skill_ready", True)
    result.setdefault("step6_agent_ready", True)
    result.setdefault("step6_validation_status", "OK")

    # From Step 7: execution prompt
    execution_prompt = orch_result.get("execution_prompt", "") or orchestration_prompt
    result.setdefault("step7_execution_prompt", execution_prompt)
    result.setdefault("step7_prompt_saved", bool(execution_prompt))

    # Write execution prompt to disk (what Step 7 used to do)
    try:
        session_dir = state.get("session_dir", "")
        if session_dir and execution_prompt:
            sp_file = Path(session_dir) / "system_prompt.txt"
            sp_file.parent.mkdir(parents=True, exist_ok=True)
            sp_file.write_text(execution_prompt, encoding="utf-8")
            result["step7_system_prompt_file"] = str(sp_file)
            result["step7_system_prompt_loaded"] = True
            logger.info("[v2] Step 0 wrote execution prompt to %s", sp_file)
    except Exception as _sp_exc:
        logger.debug("[v2] Step 0 prompt file write skipped: %s", _sp_exc)

    return result


def step2_plan_execution_node(state: FlowState) -> Dict[str, Any]:
    """Step 2: Plan Execution -- DEPRECATED (v1.14.0).

    This node is no longer part of the active pipeline graph.
    The orchestrator subprocess in Step 0 already produces a comprehensive plan,
    making a separate plan execution step redundant.

    Kept as a no-op stub for backward compatibility with test imports.
    """
    logger.warning("[v2] step2_plan_execution_node called but Step 2 is deprecated (v1.14.0)")
    return {
        "step2_plan_status": "DEPRECATED",
        "step2_plan_execution": {"phases": [], "note": "Step 2 removed in v1.14.0"},
        "step2_phases": 0,
        "step2_total_estimated_steps": 0,
    }


# REMOVED: step1_plan_mode_decision_node -- collapsed into Step 0 template (v1.13.0)
# REMOVED: step3_task_breakdown_node -- collapsed into Step 0 template (v1.13.0)
# REMOVED: step4_toon_refinement_node -- collapsed into Step 0 template (v1.13.0)
# REMOVED: step2_plan_execution_node active code -- deprecated in v1.14.0 (stub above)
#
# These functions are intentionally absent or stubbed. Their FlowState outputs are now
# populated by step0_task_analysis_node after the orchestration subprocess calls.
