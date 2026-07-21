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


def _env_int(name: str, default: int) -> int:
    """Return int(os.environ[name]), or `default` when the var is unset or non-numeric."""
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def step0_task_analysis_node(state: FlowState) -> Dict[str, Any]:
    """Step 0 v2: prompt_gen_expert -> orchestrator_agent chain.

    Phase 1: calls prompt_gen_expert_caller (fast, captured stdout) to build
    an orchestration prompt enriched with combined_complexity_score and
    CallGraph risk data. Uses claude CLI subprocess internally.

    Phase 2: decomposes the orchestration prompt into a TODO list
    (todo_decomposer) and executes each TODO via orchestrator_agent_caller
    (todo_executor), capturing stdout per TODO. Uses claude CLI subprocess
    internally.

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
                "[v2] Step 0 CallGraph pre-injection: risk={} danger_zones={} affected={}",
                call_graph_risk_level,
                len(call_graph_danger_zones),
                len(call_graph_affected_methods),
            )
    except Exception as _cg_exc:
        logger.debug("[v2] Step 0 CallGraph pre-injection skipped (fail-open): {}", _cg_exc)

    user_message = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

    # --- PRE-INJECTION C: KG-based deterministic routing (FR-3, ADR-3) ---
    kg_routing_result: Dict[str, Any] = {"status": "unresolved", "notes": "kg routing not attempted"}
    try:
        from ..routing.kg_router import route_task as _kg_route_task

        kg_routing_result = _kg_route_task(user_message)
        logger.info(
            "[v2] Step 0 KG routing pre-injection: status={} domain={} pattern={}",
            kg_routing_result.get("status"),
            kg_routing_result.get("domain"),
            kg_routing_result.get("pattern_id"),
        )
    except Exception as _kg_exc:
        logger.debug("[v2] Step 0 KG routing pre-injection skipped (fail-open): {}", _kg_exc)
        kg_routing_result = {"status": "unresolved", "notes": f"kg routing pre-injection failed: {_kg_exc}"}

    # --- PHASE 1: prompt_gen_expert_caller (claude CLI subprocess) ---
    _pg_inner_timeout = _env_int("STEP0_PROMPT_GEN_TIMEOUT", 60)
    _call_graph_json = _json.dumps(
        {
            "risk_level": call_graph_risk_level,
            "danger_zones": call_graph_danger_zones,
            "affected_methods": call_graph_affected_methods,
        }
    )
    _kg_routing_json = _json.dumps(kg_routing_result)
    prompt_gen_args = [
        "--task-description",
        user_message,
        "--complexity-score",
        str(complexity_score),
        "--call-graph-json",
        _call_graph_json,
        "--kg-routing-json",
        _kg_routing_json,
    ]

    try:
        import importlib as _il

        _helpers_mod = _il.import_module("langgraph_engine.level3_execution.helpers")
        _call_execution_script = _helpers_mod.call_execution_script
    except ImportError:
        from ..helpers import call_execution_script as _call_execution_script  # noqa: PLC0415

    prompt_gen_raw = _call_execution_script(
        "prompt_gen_expert_caller",
        prompt_gen_args,
        model_tier="fast",
        timeout=_pg_inner_timeout + 15,
    )

    _pg_status = prompt_gen_raw.get("status", "")
    if _pg_status == "ERROR":
        # On ERROR the caller's 'prompt' field is only a truncated copy of the INPUT
        # template, not a usable orchestration prompt, so fall back to the raw task.
        logger.error(
            f"[v2] Step 0 prompt_gen_expert_caller ERROR: {prompt_gen_raw.get('error', 'unknown')} -- falling back to raw task"
        )
        orchestration_prompt = user_message
    else:
        orchestration_prompt = prompt_gen_raw.get("llm_response", "") or prompt_gen_raw.get("prompt", "")
        if not orchestration_prompt:
            orchestration_prompt = user_message
            logger.warning("[v2] Step 0 prompt_gen_expert_caller returned no llm_response/prompt; using raw task")
        else:
            logger.info(
                f"[v2] Step 0 prompt_gen_expert_caller: orchestration_prompt length={len(orchestration_prompt)}"
            )

    # --- PHASE 2: todo_decomposer -> execute_todo_list (per-TODO orchestrator calls) ---
    _full_prompt = (
        "You are orchestrator-agent. Below is a fully generated orchestration prompt "
        "with a MULTI-AGENT PROMPT BUNDLE containing per-agent execution prompts.\n\n"
        "--- BEGIN ORCHESTRATION PROMPT ---\n\n" + orchestration_prompt + "\n\n--- END ORCHESTRATION PROMPT ---"
    )

    orch_result: Dict[str, Any] = {}
    _prompt_file = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as _tf:
            _tf.write(_full_prompt)
            _prompt_file = _tf.name

        if DEBUG:
            logger.debug("[v2] Step 0 orchestration prompt written to {}", _prompt_file)

        # Step 2a: decompose orchestration prompt into TODO list
        _decomp_args = [
            "--orchestration-prompt-file=%s" % _prompt_file,
            "--complexity-score=%s" % complexity_score,
        ]
        _decomp_raw: Dict[str, Any] = {}
        try:
            import importlib as _il2

            _helpers_mod2 = _il2.import_module("langgraph_engine.level3_execution.helpers")
            _call_exec = _helpers_mod2.call_execution_script
        except Exception:
            from ..helpers import call_execution_script as _call_exec  # noqa: PLC0415

        try:
            _decomp_raw = _call_exec(
                "todo_decomposer",
                _decomp_args,
                model_tier="fast",
                timeout=_env_int("STEP0_TODO_DECOMPOSER_TIMEOUT", 90) + 15,
            )
        except Exception as _decomp_exc:
            logger.warning("[v2] Step 0 todo_decomposer failed (fail-open): {}", _decomp_exc)
            _decomp_raw = {"status": "FALLBACK", "todo_list": []}

        _todo_list = _decomp_raw.get("todo_list", [])
        logger.info("[v2] Step 0 todo_decomposer: {} todos", len(_todo_list))

        # Step 2b: execute each TODO via orchestrator_agent_caller
        _todo_results = []
        if _todo_list:
            try:
                from ..architecture.todo_executor import execute_todo_list as _exec_todos  # noqa: PLC0415

                _todo_results = _exec_todos(state, _todo_list, step_number=0)
            except Exception as _exec_exc:
                logger.warning("[v2] Step 0 execute_todo_list failed (fail-open): {}", _exec_exc)
                _todo_results = []

        # Step 2c: merge todo results into orch_result
        _merged_output = "\n\n".join(
            str(r.get("result", {}).get("llm_response", "") or r.get("error", "")) for r in _todo_results
        )
        orch_result = {
            "success": True,
            "todo_list": _todo_list,
            "todo_results": _todo_results,
            "llm_response": _merged_output,
            "agent_output": {"merged_from_todos": len(_todo_results)},
        }
        _lifted = _lift_todo_agent_output(_todo_results)
        if _lifted:
            orch_result.update(_lifted)

    except Exception as _orch_exc:
        logger.warning("[v2] Step 0 orchestrator block failed (fail-open): {}", _orch_exc)
        orch_result = {"success": False, "error": str(_orch_exc)}
    finally:
        if _prompt_file:
            try:
                Path(_prompt_file).unlink(missing_ok=True)
            except OSError as exc:
                logger.debug(f"[step0] temp prompt file cleanup skipped: {exc}")

    # --- Build result from orchestrator output + migration fields ---
    result = _map_step0_result_to_state(state, orchestration_prompt, orch_result)

    # Store the injected context for observability
    result["step0_call_graph_risk_level"] = call_graph_risk_level
    result["step0_call_graph_danger_zones_count"] = len(call_graph_danger_zones)
    result["step0_call_graph_affected_methods_count"] = len(call_graph_affected_methods)
    result["step0_complexity_injected"] = complexity_score
    result["routing"] = kg_routing_result
    result["orchestration_prompt"] = orchestration_prompt
    result["orchestrator_result"] = orch_result
    result["todo_list"] = orch_result.get("todo_list", [])
    result["todo_results"] = orch_result.get("todo_results", [])

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
                    "[v2] Step 0 complexity adjusted by call graph: {} -> {} (boost={:+})",
                    current,
                    boosted,
                    boost,
                )
    except Exception as exc:
        logger.debug(f"[step0] call-graph complexity boost skipped: {exc}")

    return result


def _lift_todo_agent_output(todo_results):
    """Promote structured task-analysis fields from per-TODO orchestrator output.

    The TODO-decomposition path nests each orchestrator result under
    ``todo_results[i]['result']`` and any structured payload under its
    ``agent_output`` key. This lifts recognized analysis fields to a flat
    dict so _map_step0_result_to_state can populate the Step 0 migration
    fields instead of falling back to constant defaults. Returns an empty
    dict when no structured fields are present (the common case for pure
    execution TODOs), leaving the defaults in place.
    """
    recognized = (
        "task_type",
        "reasoning",
        "tasks",
        "task_count",
        "model_recommendation",
        "selected_skill",
        "selected_agent",
        "skills",
        "agents",
        "skill_definition",
        "agent_definition",
        "execution_prompt",
    )
    lifted = {}
    for entry in todo_results or []:
        result = entry.get("result") if isinstance(entry, dict) else None
        if not isinstance(result, dict):
            continue
        sources = [result]
        nested = result.get("agent_output")
        if isinstance(nested, dict):
            sources.append(nested)
        for source in sources:
            for key in recognized:
                if key in source and key not in lifted:
                    lifted[key] = source[key]
    return lifted


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
    _combined = state.get("combined_complexity_score", 0)
    _complexity_1to10 = max(1, min(10, round(_combined / 2.5))) if _combined else 5
    try:
        result["step0_complexity"] = max(1, min(10, int(orch_result.get("complexity", _complexity_1to10))))
    except (TypeError, ValueError):
        result["step0_complexity"] = _complexity_1to10
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
            logger.info("[v2] Step 0 wrote execution prompt to {}", sp_file)
    except Exception as _sp_exc:
        logger.debug("[v2] Step 0 prompt file write skipped: {}", _sp_exc)

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
