"""
Level 3 SubGraph v2 - Integrated Execution Pipeline (Steps 0, 8-14)

Bridge module that wraps the WORKFLOW.md-compliant level3_execution.py functions
with proper orchestrator integration and logging.

CHANGE LOG (v1.13.0):
  Removed Steps 1, 3, 4, 5, 6, 7 from the pipeline. These were collapsed into
  Step 0's orchestration template call. The new pipeline is:
    Pre-0 -> Step 0 -> Step 8 -> Step 9 -> Steps 10-14

  Step count: 15 steps -> 9 meaningful steps (Pre-0, Step 0, Steps 8-14)
  Planning calls: ~6 -> ~2 (~70% reduction in planning phase cost)

CHANGE LOG (v1.14.0):
  Step 0 caller scripts now use claude CLI subprocess (not direct llm_call API).
  Step 2 (plan execution) removed from pipeline -- orchestrator subprocess
  already produces a comprehensive plan.
  Active steps: Pre-0, 0.0, 0.1, 0, 8, 9, [10-14] = 8 active steps.

Remaining steps (0, 8-14) implemented with:
- Proper logging via loguru
- Time tracking
- Session management
- LangGraph routing support
- Global error handling with try/catch on every critical path
- Checkpointing after each completed step
- Metrics collection (duration, status, tokens) per step
- RecoveryHandler for signal handling (Ctrl+C)
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_session_logs_dir, get_telemetry_dir

    _LEVEL3_TELEMETRY_DIR = get_telemetry_dir()
    _LEVEL3_SESSION_LOGS_DIR = get_session_logs_dir()
except ImportError:
    _LEVEL3_TELEMETRY_DIR = Path.home() / ".claude" / "logs" / "telemetry"
    _LEVEL3_SESSION_LOGS_DIR = Path.home() / ".claude" / "logs" / "sessions"


# Lazy import: avoid import-time side effects from timeout_wrapper
def _get_timeout_wrapper():
    """Lazy-load timeout_wrapper to avoid import-time side effects."""
    try:
        from ..timeout_wrapper import STEP_TIMEOUTS, StepTimeout

        return STEP_TIMEOUTS, StepTimeout
    except Exception as _e:
        return {}, None


try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from ..core.infrastructure import (  # noqa: E402,F401
    _create_infra_objects,
    _infra_cache,
    _pipeline_start_times,
    get_infra,
)


# Backward-compat aliases for tests that patch individual getters
def _get_checkpoint_manager():
    """Backward-compat: returns checkpoint_manager from infra."""
    infra = _create_infra_objects("unknown")
    return infra.get("checkpoint_manager")


def _get_metrics_collector():
    """Backward-compat: returns metrics_collector from infra."""
    infra = _create_infra_objects("unknown")
    return infra.get("metrics_collector")


def _get_error_logger():
    """Backward-compat: returns error_logger from infra."""
    infra = _create_infra_objects("unknown")
    return infra.get("error_logger")


def _get_backup_manager():
    """Backward-compat: returns backup_manager from infra."""
    infra = _create_infra_objects("unknown")
    return infra.get("backup_manager")


from ..flow_state import FlowState  # noqa: E402
from ..step_logger import write_level_log  # noqa: E402

# ---------------------------------------------------------------------------
# Per-step session logging
# ---------------------------------------------------------------------------


def _write_step_log(
    state: FlowState,
    step_number: int,
    step_label: str,
    status: str,
    duration: float,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Write per-step log entry to session directory.

    Delegates to the shared write_level_log utility for the level3 step-logs
    directory, AND writes a backward-compatible step-{NN}.json file.

    Args:
        state: Current flow state (for session_dir)
        step_number: Step number (0-14)
        step_label: Human-readable step label
        status: OK / FAILED / TIMEOUT
        duration: Duration in seconds
        result: Step result dict (keys only, not full values to save space)
        error: Error message if failed
    """
    # Write to shared level3-logs/{step_name}.json
    step_name = f"step-{step_number:02d}-{step_label.lower().replace(' ', '-')}"
    write_level_log(state, "level3", step_name, status, duration, result, error)

    # Also write backward-compatible step-logs/step-{NN}.json
    import json as _json

    session_dir = state.get("session_dir") or state.get("session_path", "")
    if not session_dir:
        return

    try:
        log_dir = Path(session_dir) / "step-logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "step": step_number,
            "label": step_label,
            "status": status,
            "duration_ms": round(duration * 1000, 1),
            "timestamp": datetime.now().isoformat(),
            "session_id": state.get("session_id", ""),
        }

        if error:
            log_entry["error"] = error

        if result:
            from ..step_logger import _summarize_result

            log_entry["result_summary"] = _summarize_result(result)

        log_file = log_dir / f"step-{step_number:02d}.json"
        with open(log_file, "w", encoding="utf-8") as f:
            _json.dump(log_entry, f, indent=2)

    except Exception:
        pass  # Logging failure is never fatal


# ---------------------------------------------------------------------------
# Telemetry writer - appends one JSONL line per step to ~/.claude/logs/telemetry/
# ---------------------------------------------------------------------------


def _write_telemetry(
    state: FlowState,
    step_number: int,
    step_name: str,
    status: str,
    duration_ms: float,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one telemetry entry for the completed step to a JSONL file.

    File path: ~/.claude/logs/telemetry/{session_id}.jsonl
    Non-blocking: all errors are silently swallowed.
    ASCII-only strings used throughout for cp1252 compatibility.
    """
    try:
        session_id = state.get("session_id", "") or "unknown"
        telemetry_entry = {
            "session_id": session_id,
            "step": step_number,
            "step_name": step_name,
            "status": status,
            "duration_ms": round(duration_ms, 1),
            "timestamp": datetime.now().isoformat(),
            "llm_called": bool(result.get("step%d_llm_invoked" % step_number, False) if result else False),
            "modified_files_count": len(result.get("step%d_modified_files" % step_number, []) if result else []),
        }
        telemetry_dir = _LEVEL3_TELEMETRY_DIR
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        telemetry_file = telemetry_dir / ("%s.jsonl" % session_id)
        with open(telemetry_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(telemetry_entry) + "\n")
    except Exception:
        pass  # Non-blocking


# ---------------------------------------------------------------------------
# Core step execution wrapper
# ---------------------------------------------------------------------------


def _run_step(
    step_number: int,
    step_label: str,
    step_fn,
    state: FlowState,
    *,
    fallback_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a single step function with full error handling infrastructure.

    Responsibilities:
    1. Log step entry.
    2. Update RecoveryHandler with current step (for Ctrl+C).
    3. Execute step_fn(state) inside a timeout-enforced wrapper.
    4. On success: record metric, save checkpoint.
    5. On timeout/failure: log error, record metric, return fallback_result.

    Timeouts are loaded from timeout_wrapper.STEP_TIMEOUTS (lazy import).
    Steps without a configured timeout run without a time limit.

    Args:
        step_number:    Numeric step (0-14), used for checkpoint naming.
        step_label:     Human label for logging (e.g. "STEP 3").
        step_fn:        Callable(state) -> dict.
        state:          Current FlowState.
        fallback_result: Dict to return on unrecoverable error.

    Returns:
        Result dict from step_fn, or fallback_result on timeout/failure.
    """
    import os as _os

    # Dry-run: skip Steps 8-14 (GitHub, implementation, PR, review, docs)
    if step_number >= 8 and _os.environ.get("CLAUDE_DRY_RUN") == "1":
        logger.info(f"[v2] Step {step_number} skipped (dry-run mode)")
        print(f"[STEP {step_number:02d}] {step_label} - SKIPPED (dry-run)", file=sys.stderr)
        return {**(fallback_result or {}), f"step{step_number}_status": "DRY_RUN_SKIPPED"}

    infra = get_infra(state)
    # Use module-level getter functions so tests can mock them individually
    cp = _get_checkpoint_manager() or infra.get("checkpoint")
    metrics = _get_metrics_collector() or infra.get("metrics")
    error_logger = infra.get("error_logger")

    # Update recovery handler's view of current step
    try:
        from ..recovery_handler import _register_globals

        if cp and error_logger:
            _register_globals(step_number, dict(state), cp, error_logger)
    except Exception:
        pass  # Recovery handler update is best-effort

    # Log step start to stderr for real-time visibility
    print(f"\n[STEP {step_number:02d}] {step_label} - START", file=sys.stderr)
    logger.info(f"\n[STEP {step_number:02d}] {step_label} - START")
    step_start = time.time()

    # Track pipeline-level start time when Step 0 begins
    if step_number == 0:
        try:
            _session_id_for_pipeline = state.get("session_id", "") or "unknown"
            _pipeline_start_times[_session_id_for_pipeline] = step_start
        except Exception:
            pass  # Non-blocking

    # --- Failure Prevention KB check (informational, non-blocking) ---
    # Only for steps that run external commands/tools (Steps 0, 8, 9, 10)
    if step_number in {0, 8, 9, 10}:
        try:
            kb_suggestions = state.get("failure_kb_suggestions") or []
            user_msg = state.get("user_message", "")
            if kb_suggestions and user_msg:
                for entry in kb_suggestions:
                    sig = entry.get("signature", "")
                    sig_words = [w for w in sig.lower().split() if len(w) > 3]
                    if any(w in user_msg.lower() for w in sig_words):
                        print(
                            "[STEP %02d] KB WARNING: %s -> %s"
                            % (
                                step_number,
                                sig[:60],
                                entry.get("prevention", "")[:80],
                            ),
                            file=sys.stderr,
                        )
        except Exception:
            pass  # Fail-open: KB check never blocks

    # --- Timeout enforcement ---
    # Load timeout table; gracefully degrade if module unavailable
    _timeouts, _StepTimeout = _get_timeout_wrapper()
    timeout_s = _timeouts.get(step_number) if _timeouts else None

    try:
        if timeout_s is not None and _StepTimeout is not None:
            tw = _StepTimeout(timeout_seconds=timeout_s)
            result = tw.run(
                fn=step_fn,
                args=(state,),
                fallback=fallback_result or {},
                step_label=f"STEP {step_number:02d}: {step_label}",
            )
            # Check if timeout_wrapper returned its own error result
            if result.get("timed_out"):
                logger.warning(f"[STEP {step_number:02d}] {step_label} - TIMED OUT after {timeout_s}s")
                duration = time.time() - step_start
                if metrics:
                    try:
                        metrics.record_step(step=step_number, duration=duration, status="TIMEOUT")
                    except Exception:
                        pass
                if error_logger:
                    try:
                        error_logger.log_error(
                            step=f"Step {step_number}",
                            error_message=f"Timeout after {timeout_s}s",
                            severity="ERROR",
                            error_type="TimeoutError",
                            recovery_action="Returning fallback result",
                        )
                    except Exception:
                        pass
                # Build full fallback with timing info
                base = {
                    f"step{step_number}_error": f"Timeout after {timeout_s}s",
                    f"step{step_number}_execution_time_ms": duration * 1000,
                }
                # Write telemetry entry (non-blocking)
                _write_telemetry(state, step_number, step_label, "ERROR", duration * 1000, None)
                return {**(fallback_result or {}), **base}
        else:
            result = step_fn(state)

        duration = time.time() - step_start

        # Record SUCCESS metric
        if metrics:
            try:
                metrics.record_step(
                    step=step_number,
                    duration=duration,
                    status="SUCCESS",
                )
            except Exception as me:
                logger.warning(f"[v2] Metrics record failed: {me}")

        # Checkpoint: merge state + result then save (success_status=True)
        if cp:
            try:
                merged = {**dict(state), **(result or {})}
                cp.save_checkpoint(
                    step_number,
                    merged,
                    success_status=True,
                )
            except Exception as ce:
                logger.warning(f"[v2] Checkpoint save failed: {ce}")

        print(f"[STEP {step_number:02d}] {step_label} - OK ({duration*1000:.0f}ms)", file=sys.stderr)
        logger.info(f"[STEP {step_number:02d}] {step_label} - OK ({duration*1000:.0f}ms)")

        # Write step log to session directory
        _write_step_log(state, step_number, step_label, "OK", duration, result)

        # Write telemetry entry (non-blocking)
        _write_telemetry(state, step_number, step_label, "OK", duration * 1000, result)

        # Save workflow memory for resume support (non-blocking)
        try:
            import json as _json

            session_dir = state.get("session_dir", "")
            if session_dir:
                mem_path = Path(session_dir) / "workflow-memory.json"
                mem_data = {
                    "last_step": step_number,
                    "last_step_label": step_label,
                    "last_step_status": "SUCCESS",
                    "timestamp": datetime.now().isoformat(),
                    "session_id": state.get("session_id", ""),
                }
                mem_path.write_text(_json.dumps(mem_data, indent=2), encoding="utf-8")
        except Exception:
            pass  # Workflow memory is best-effort

        if result is not None:
            result[f"step{step_number}_execution_time_ms"] = duration * 1000

        # Add total pipeline execution time when Step 14 completes
        if step_number == 14 and result is not None:
            try:
                _session_id_for_total = state.get("session_id", "") or "unknown"
                _pipeline_start = _pipeline_start_times.get(_session_id_for_total)
                if _pipeline_start is not None:
                    total_time = (time.time() - _pipeline_start) * 1000
                    result["level3_total_execution_time_ms"] = round(total_time, 1)
                    # Clean up to avoid memory growth across sessions
                    _pipeline_start_times.pop(_session_id_for_total, None)
            except Exception:
                pass  # Non-blocking

        return result or {}

    except Exception as exc:
        duration = time.time() - step_start

        # Log structured error
        if error_logger:
            try:
                error_logger.log_error(
                    step=f"Step {step_number}",
                    error_message=str(exc),
                    severity="ERROR",
                    error_type=type(exc).__name__,
                    recovery_action=(
                        "Returning fallback result" if fallback_result is not None else "Step returning empty result"
                    ),
                )
            except Exception:
                pass

        # Record FAILED metric
        if metrics:
            try:
                metrics.record_step(
                    step=step_number,
                    duration=duration,
                    status="FAILED",
                )
                metrics.record_error(
                    step=step_number,
                    error_type=type(exc).__name__,
                    recovery="Fallback result returned",
                    message=str(exc),
                )
            except Exception:
                pass

        # Save failed checkpoint (success_status=False, include error message)
        if cp:
            try:
                merged = {**dict(state), **(fallback_result or {})}
                cp.save_checkpoint(
                    step_number,
                    merged,
                    success_status=False,
                    error_message=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            except Exception as ce:
                logger.warning(f"[v2] Failed checkpoint save after error: {ce}")

        print(f"[STEP {step_number:02d}] {step_label} - FAILED: {exc}", file=sys.stderr)
        logger.error(f"[STEP {step_number:02d}] {step_label} - FAILED: {exc}")

        # Write step error log to session directory
        _write_step_log(state, step_number, step_label, "FAILED", duration, None, str(exc))

        # Write telemetry entry (non-blocking)
        _write_telemetry(state, step_number, step_label, "ERROR", duration * 1000, None)

        error_key = f"step{step_number}_error"
        base: Dict[str, Any] = {
            error_key: str(exc),
            f"step{step_number}_execution_time_ms": duration * 1000,
        }

        if fallback_result:
            return {**fallback_result, **base}

        return base


# ============================================================================
# STEP NODE WRAPPERS - Extracted to level3_v2_nodes/ package
# ============================================================================
from .nodes import (  # noqa: F401,E402
    _build_retry_history_context,
    level3_init_node,
    orchestration_pre_analysis_node,
    route_pre_analysis,
    route_to_closure_or_retry,
    step0_0_project_context_node,
    step0_1_initial_callgraph_node,
    step0_task_analysis_node,
    step2_plan_execution_node,
    step8_github_issue_node,
    step9_branch_creation_node,
    step10_implementation_note,
    step11_pull_request_node,
    step12_issue_closure_node,
    step13_docs_update_node,
    step14_final_summary_node,
)

# ============================================================================
# MERGE NODE - Final status determination
# ============================================================================

# level3_merge_node is the canonical name (v1.14: removed level3_v2_merge_node alias)
