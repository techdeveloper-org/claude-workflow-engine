"""Step execution decorator and factory for Level 3 pipeline steps.

Replaces the repetitive _run_step() wrapper pattern in level3_execution/subgraph.py
where each step node is a thin wrapper around _run_step() with step-specific
parameters.  Moving the wrapper logic here lets callers register new step nodes
with a single function call instead of duplicating ~300 lines of
try/except/metrics/checkpoint boilerplate per step.

Design patterns used
--------------------
Decorator Pattern (GoF):
    create_step_node wraps step functions with cross-cutting concerns (dry-run
    guard, timing, metrics, checkpointing, telemetry, workflow memory) without
    modifying the wrapped function itself.

Template Method Pattern (GoF):
    The standard step execution workflow is fixed in _execute_step_with_infra().
    Individual step functions customise only the business logic; all
    infrastructure steps run in the same order for every step.

Factory Pattern (GoF):
    create_step_node is a factory that produces LangGraph-compatible node
    callables (state -> dict) from lightweight configuration parameters.

Class design
------------
StepExecutionContext encapsulates the mutable per-step execution state (timing,
infrastructure references) that is passed between the helper methods inside
_execute_step_with_infra().  This keeps the factory function itself free of
local variable soup and makes unit testing straightforward: callers can
construct a StepExecutionContext with mock objects and call its methods directly.
"""

import functools
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .infrastructure import get_infra
from .logger_factory import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Telemetry directory under the user home (mirrors level3_execution/subgraph.py).
_TELEMETRY_DIR = Path.home() / ".claude" / "logs" / "telemetry"


# ---------------------------------------------------------------------------
# StepExecutionContext
# ---------------------------------------------------------------------------


class StepExecutionContext:
    """Per-step execution context encapsulating infrastructure and timing.

    An instance is created at the start of each _execute_step_with_infra()
    call and passed through the helper methods so that state does not leak
    between steps and individual concerns can be exercised in isolation.

    Attributes
    ----------
    step_number:    0-14 pipeline step index.
    step_label:     Human-readable label used in log messages.
    state:          The LangGraph FlowState dict for the current invocation.
    start_time:     wall-clock time.time() when execution began.
    infra:          Dict returned by get_infra(state) with keys:
                    checkpoint, metrics, error_logger, backup.
    """

    def __init__(
        self,
        step_number: int,
        step_label: str,
        state: Dict[str, Any],
    ) -> None:
        self.step_number = step_number
        self.step_label = step_label
        self.state = state
        self.start_time: float = time.time()
        self.infra: Dict[str, Any] = get_infra(state)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def checkpoint(self) -> Any:
        """CheckpointManager or None."""
        return self.infra.get("checkpoint")

    @property
    def metrics(self) -> Any:
        """MetricsCollector or None."""
        return self.infra.get("metrics")

    @property
    def error_logger(self) -> Any:
        """ErrorLogger or None."""
        return self.infra.get("error_logger")

    @property
    def elapsed_ms(self) -> float:
        """Milliseconds elapsed since context was created."""
        return (time.time() - self.start_time) * 1000.0

    @property
    def elapsed_s(self) -> float:
        """Seconds elapsed since context was created."""
        return time.time() - self.start_time

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def record_success(self, duration_s: float) -> None:
        """Record a SUCCESS metric for this step."""
        if self.metrics:
            try:
                self.metrics.record_step(
                    step=self.step_number,
                    duration=duration_s,
                    status="SUCCESS",
                )
            except Exception as exc:
                logger.warning("[step_decorator] Metrics record_step failed: %s" % exc)

    def record_failure(self, duration_s: float, exc: Exception) -> None:
        """Record FAILED metric and error detail for this step."""
        if self.metrics:
            try:
                self.metrics.record_step(
                    step=self.step_number,
                    duration=duration_s,
                    status="FAILED",
                )
                self.metrics.record_error(
                    step=self.step_number,
                    error_type=type(exc).__name__,
                    recovery="Fallback result returned",
                    message=str(exc),
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def save_success_checkpoint(self, result: Dict[str, Any]) -> None:
        """Merge state + result and save a success checkpoint."""
        if self.checkpoint:
            try:
                merged = {**dict(self.state), **(result or {})}
                self.checkpoint.save_checkpoint(
                    self.step_number,
                    merged,
                    success_status=True,
                )
            except Exception as exc:
                logger.warning("[step_decorator] Checkpoint save failed: %s" % exc)

    def save_failure_checkpoint(
        self,
        fallback: Optional[Dict[str, Any]],
        exc: Exception,
    ) -> None:
        """Save a failure checkpoint with error metadata."""
        if self.checkpoint:
            try:
                merged = {**dict(self.state), **(fallback or {})}
                self.checkpoint.save_checkpoint(
                    self.step_number,
                    merged,
                    success_status=False,
                    error_message="%s: %s" % (type(exc).__name__, str(exc)[:200]),
                )
            except Exception as ce:
                logger.warning("[step_decorator] Failed checkpoint save after error: %s" % ce)

    # ------------------------------------------------------------------
    # Error logger helper
    # ------------------------------------------------------------------

    def log_structured_error(
        self,
        exc: Exception,
        fallback: Optional[Dict[str, Any]],
    ) -> None:
        """Write a structured error entry via ErrorLogger."""
        if self.error_logger:
            try:
                self.error_logger.log_error(
                    step="Step %d" % self.step_number,
                    error_message=str(exc),
                    severity="ERROR",
                    error_type=type(exc).__name__,
                    recovery_action=(
                        "Returning fallback result" if fallback is not None else "Step returning empty result"
                    ),
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Telemetry helper
    # ------------------------------------------------------------------

    def write_telemetry(
        self,
        status: str,
        duration_ms: float,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one JSONL telemetry line for the step.

        Non-blocking: all errors are silently swallowed.
        ASCII-only strings used throughout for cp1252 compatibility.
        """
        try:
            session_id = self.state.get("session_id", "") or "unknown"
            n = self.step_number
            entry = {
                "session_id": session_id,
                "step": n,
                "step_name": self.step_label,
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "timestamp": datetime.now().isoformat(),
                "llm_called": bool(result.get("step%d_llm_invoked" % n, False) if result else False),
                "modified_files_count": len(result.get("step%d_modified_files" % n, []) if result else []),
            }
            _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
            telemetry_file = _TELEMETRY_DIR / ("%s.jsonl" % session_id)
            with open(str(telemetry_file), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Non-blocking

    # ------------------------------------------------------------------
    # Workflow memory helper
    # ------------------------------------------------------------------

    def save_workflow_memory(self, status: str) -> None:
        """Write workflow-memory.json to the session directory.

        Used for resume support.  Non-blocking.
        """
        try:
            session_dir = self.state.get("session_dir", "") or ""
            if not session_dir:
                return
            mem = {
                "last_step": self.step_number,
                "last_step_label": self.step_label,
                "last_step_status": status,
                "timestamp": datetime.now().isoformat(),
                "session_id": self.state.get("session_id", ""),
            }
            mem_path = Path(session_dir) / "workflow-memory.json"
            mem_path.write_text(
                json.dumps(mem, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # Workflow memory is best-effort


# ---------------------------------------------------------------------------
# Internal execution helper
# ---------------------------------------------------------------------------


def _execute_step_with_infra(
    ctx: StepExecutionContext,
    step_fn: Callable,
    fallback_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run step_fn inside the full infrastructure wrapper.

    This is the Template Method: the execution workflow is fixed; individual
    steps provide only the business logic via step_fn.

    Workflow
    --------
    1. Dry-run guard (steps >= 8 when CLAUDE_DRY_RUN=1).
    2. Invoke step_fn(state).
    3. On success: record metric, save checkpoint, write telemetry,
       save workflow memory.
    4. On failure: log error, record metric, save failure checkpoint, write
       telemetry, return fallback.

    Args:
        ctx:            Populated StepExecutionContext for this invocation.
        step_fn:        The step implementation callable (state -> dict).
        fallback_result: Optional dict merged with error metadata on failure.

    Returns:
        A plain dict suitable for returning from a LangGraph node function.
    """
    n = ctx.step_number
    label = ctx.step_label

    # 1. Dry-run guard
    if n >= 8 and os.environ.get("CLAUDE_DRY_RUN") == "1":
        logger.info("[step_decorator] Step %d skipped (dry-run mode)" % n)
        print(
            "[STEP %02d] %s - SKIPPED (dry-run)" % (n, label),
            file=sys.stderr,
        )
        result: Dict[str, Any] = dict(fallback_result or {})
        result["step%d_status" % n] = "DRY_RUN_SKIPPED"
        return result

    # Log step start
    print("\n[STEP %02d] %s - START" % (n, label), file=sys.stderr)
    logger.info("\n[STEP %02d] %s - START" % (n, label))

    # 2. Execute step function
    try:
        result = step_fn(ctx.state)
        duration_s = ctx.elapsed_s

        # 3a. Record success metric
        ctx.record_success(duration_s)

        # 3b. Save checkpoint
        ctx.save_success_checkpoint(result or {})

        print(
            "[STEP %02d] %s - OK (%.0fms)" % (n, label, duration_s * 1000),
            file=sys.stderr,
        )
        logger.info("[STEP %02d] %s - OK (%.0fms)" % (n, label, duration_s * 1000))

        # 3c. Write telemetry
        ctx.write_telemetry("OK", duration_s * 1000, result)

        # 3d. Save workflow memory
        ctx.save_workflow_memory("SUCCESS")

        # Inject execution time into result
        if result is None:
            result = {}
        result["step%d_execution_time_ms" % n] = duration_s * 1000

        return result

    except Exception as exc:
        duration_s = ctx.elapsed_s

        # 4a. Structured error log
        ctx.log_structured_error(exc, fallback_result)

        # 4b. Record failure metric
        ctx.record_failure(duration_s, exc)

        # 4c. Save failure checkpoint
        ctx.save_failure_checkpoint(fallback_result, exc)

        print(
            "[STEP %02d] %s - FAILED: %s" % (n, label, exc),
            file=sys.stderr,
        )
        logger.error("[STEP %02d] %s - FAILED: %s" % (n, label, exc))

        # 4d. Write telemetry
        ctx.write_telemetry("ERROR", duration_s * 1000, None)

        # Build error return
        base: Dict[str, Any] = {
            "step%d_error" % n: str(exc),
            "step%d_execution_time_ms" % n: duration_s * 1000,
        }
        if fallback_result:
            return {**fallback_result, **base}
        return base


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_step_node(
    step_number: int,
    step_label: str,
    step_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    fallback_result: Optional[Dict[str, Any]] = None,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Factory function that creates a LangGraph-compatible step node callable.

    The returned callable accepts a FlowState dict and returns a dict of
    FlowState updates, satisfying the LangGraph node function contract.

    The created node includes:
    - Dry-run guard (skips steps >= 8 when CLAUDE_DRY_RUN=1)
    - Execution timing
    - Success/failure metrics via MetricsCollector
    - Checkpoint persistence via CheckpointManager
    - Structured error logging via ErrorLogger
    - JSONL telemetry append
    - Workflow memory write for resume support

    Args:
        step_number:     Numeric step index (0-14).  Used for checkpoint
                         naming, dry-run guard, and state key construction
                         (e.g. ``step3_error``).
        step_label:      Human-readable label for log messages
                         (e.g. ``"STEP 3 - Task Breakdown"``).
        step_fn:         The step implementation.  Signature:
                         ``(state: FlowState) -> Dict[str, Any]``
                         Must be a pure function of state; side-effect-free
                         with respect to the returned dict.
        fallback_result: Optional dict merged with error metadata when
                         step_fn raises.  When None only the error key is
                         returned.

    Returns:
        A callable ``(state: Dict[str, Any]) -> Dict[str, Any]`` suitable
        for use as a LangGraph node.

    Usage::

        def _my_step_impl(state: FlowState) -> dict:
            ...

        my_step_node = create_step_node(
            step_number=3,
            step_label="STEP 3 - Task Breakdown",
            step_fn=_my_step_impl,
            fallback_result={"step3_breakdown": []},
        )

        # Register with StateGraph
        graph.add_node("step3_task_breakdown", my_step_node)
    """

    @functools.wraps(step_fn)
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        ctx = StepExecutionContext(
            step_number=step_number,
            step_label=step_label,
            state=state,
        )
        return _execute_step_with_infra(ctx, step_fn, fallback_result)

    # Attach metadata so callers can introspect without running the node.
    _node.step_number = step_number  # type: ignore[attr-defined]
    _node.step_label = step_label  # type: ignore[attr-defined]
    _node.__name__ = "step%d_node" % step_number
    _node.__qualname__ = "step%d_node" % step_number

    return _node
