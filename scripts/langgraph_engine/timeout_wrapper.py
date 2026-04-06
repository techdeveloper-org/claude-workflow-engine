"""
Timeout Wrapper - Enforces per-step timeout limits for Level 3 pipeline.

Provides:
1. StepTimeout class - Wraps any callable with a configurable timeout
2. STEP_TIMEOUTS dict - Canonical timeout values for each Level 3 step
3. run_with_timeout() - Top-level function for direct use in node wrappers
4. TimeoutError fallback results - Graceful degradation with detailed logging

All timeouts use threading.Thread (Windows-compatible, no SIGALRM).
On timeout, the thread is marked as daemon and abandoned - execution
continues on the main thread with a fallback result.

Usage:
    from .timeout_wrapper import run_with_timeout, STEP_TIMEOUTS

    result = run_with_timeout(
        fn=planner.execute,
        step_number=8,
        args=(user_requirement,),
        fallback={"issue_created": False, "source": "timeout_fallback"}
    )

# v1.15.2: removed fallback_step1, fallback_step2, fallback_step5, fallback_step7
#           (Steps 1,2,3,4,5,6,7 removed from pipeline in v1.13.0).
#           Removed timeout/label entries for dead steps 1-7 from STEP_TIMEOUTS/STEP_LABELS.
"""

import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Canonical timeout values (seconds) per Level 3 step
# Active steps only: Pre-0 (0), Step 0, Steps 8-14
# v1.15.2: removed dead entries for steps 1,2,3,4,5,6,7
# ---------------------------------------------------------------------------

STEP_TIMEOUTS: Dict[int, int] = {
    0: 900,  # Task Analysis (LLM - let it take its time)
    8: 900,  # GitHub Issue Creation (LLM title gen + GitHub API)
    9: 120,  # Branch Creation (git operations)
    10: 900,  # Implementation Execution (Claude heavy lifting)
    11: 900,  # Pull Request & Code Review (network + possible LLM)
    12: 120,  # Issue Closure (network I/O)
    13: 120,  # Project Documentation Update (file writes)
    14: 120,  # Final Summary & Voice Notification (local)
}

# Human-readable step labels for log messages
# v1.15.2: removed dead entries for steps 1,2,3,4,5,6,7
STEP_LABELS: Dict[int, str] = {
    8: "GitHub Issue Creation",
    9: "Branch Creation",
    10: "Implementation Execution",
    11: "Pull Request & Code Review",
    12: "Issue Closure",
    13: "Project Documentation Update",
    14: "Final Summary & Voice Notification",
}


# ---------------------------------------------------------------------------
# Internal result container for thread-safe value passing
# ---------------------------------------------------------------------------


class _StepResult:
    """Thread-safe container to pass result/error from worker thread."""

    def __init__(self):
        self.value: Optional[Dict[str, Any]] = None
        self.error: Optional[Exception] = None
        self.completed: bool = False


# ---------------------------------------------------------------------------
# Core timeout execution engine
# ---------------------------------------------------------------------------


class StepTimeout:
    """
    Wraps a callable with timeout enforcement using a background thread.

    The callable runs in a daemon thread. If it does not finish within
    `timeout_seconds`, the main thread returns a fallback result and logs
    a detailed timeout warning. The daemon thread is abandoned (Python
    does not support forceful thread termination, but daemon threads are
    killed when the process exits).

    Example:
        wrapper = StepTimeout(timeout_seconds=30)
        result = wrapper.run(
            fn=my_function,
            args=(arg1, arg2),
            kwargs={"key": "value"},
            fallback={"success": False, "error": "timeout"}
        )
    """

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        fn: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        fallback: Optional[Dict[str, Any]] = None,
        step_label: str = "Unknown Step",
    ) -> Dict[str, Any]:
        """
        Execute fn(*args, **kwargs) with timeout enforcement.

        Args:
            fn:           Callable to execute.
            args:         Positional arguments for fn.
            kwargs:       Keyword arguments for fn.
            fallback:     Dict returned if timeout or exception occurs.
                          If None, a minimal error dict is returned.
            step_label:   Label for log messages (e.g. "STEP 8: GitHub Issue Creation").

        Returns:
            Result dict from fn, or fallback dict on timeout/error.
        """
        if kwargs is None:
            kwargs = {}

        container = _StepResult()
        start_time = time.time()

        def _worker():
            try:
                container.value = fn(*args, **kwargs)
                container.completed = True
            except Exception as exc:
                container.error = exc
                container.completed = True

        thread = threading.Thread(target=_worker, daemon=True, name=f"timeout_{step_label}")
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        elapsed_ms = (time.time() - start_time) * 1000

        # --- Thread finished within timeout ---
        if container.completed:
            if container.error is not None:
                logger.error(
                    f"[TimeoutWrapper] {step_label} raised exception: {container.error} "
                    f"(elapsed={elapsed_ms:.0f}ms)"
                )
                return self._build_error_result(
                    step_label=step_label,
                    reason=f"Exception: {container.error}",
                    elapsed_ms=elapsed_ms,
                    fallback=fallback,
                )

            logger.debug(
                f"[TimeoutWrapper] {step_label} completed in {elapsed_ms:.0f}ms " f"(limit={self.timeout_seconds}s)"
            )
            result = container.value or {}
            # Inject timing metadata
            if isinstance(result, dict):
                result.setdefault("_timeout_enforced", True)
                result.setdefault("_elapsed_ms", round(elapsed_ms, 1))
                result.setdefault("_timeout_limit_s", self.timeout_seconds)
            return result

        # --- Thread did NOT finish (timeout) ---
        logger.warning(
            f"[TimeoutWrapper] TIMEOUT: {step_label} exceeded {self.timeout_seconds}s "
            f"(elapsed={elapsed_ms:.0f}ms). Abandoning thread and returning fallback."
        )
        logger.warning(
            f"[TimeoutWrapper] Thread '{thread.name}' is alive={thread.is_alive()} "
            f"- will be abandoned (daemon=True)."
        )

        return self._build_error_result(
            step_label=step_label,
            reason=f"Timeout after {self.timeout_seconds}s",
            elapsed_ms=elapsed_ms,
            fallback=fallback,
            timed_out=True,
        )

    @staticmethod
    def _build_error_result(
        step_label: str,
        reason: str,
        elapsed_ms: float,
        fallback: Optional[Dict[str, Any]] = None,
        timed_out: bool = False,
    ) -> Dict[str, Any]:
        """Build standardised error/timeout result dict."""
        base = {
            "success": False,
            "error": reason,
            "timed_out": timed_out,
            "_timeout_enforced": True,
            "_elapsed_ms": round(elapsed_ms, 1),
            "timestamp": datetime.now().isoformat(),
            "step_label": step_label,
        }
        if fallback:
            # Fallback values take precedence for domain keys, but base metadata wins
            merged = {**fallback, **base}
            return merged
        return base


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------


def run_with_timeout(
    fn: Callable,
    step_number: int,
    args: Tuple = (),
    kwargs: Optional[Dict[str, Any]] = None,
    fallback: Optional[Dict[str, Any]] = None,
    custom_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute fn with the canonical timeout for step_number.

    Looks up the timeout from STEP_TIMEOUTS. If step_number is not in the
    table, uses 60 seconds as a safe default.

    Args:
        fn:             Callable to execute.
        step_number:    Level 3 step number (8-14). Used for timeout lookup.
        args:           Positional arguments passed to fn.
        kwargs:         Keyword arguments passed to fn.
        fallback:       Return value if fn times out or raises. Should contain
                        safe default values for the step's output contract.
        custom_timeout: Override STEP_TIMEOUTS for this call (seconds).

    Returns:
        Result dict from fn on success, or fallback dict on timeout/error.

    Example:
        result = run_with_timeout(
            fn=github_ops.create_issue,
            step_number=8,
            args=(user_requirement,),
            fallback={"issue_created": False, "source": "timeout_fallback", "risk_level": "high"}
        )
    """
    timeout_s = custom_timeout if custom_timeout is not None else STEP_TIMEOUTS.get(step_number, 60)
    step_label = STEP_LABELS.get(step_number, f"Step {step_number}")

    logger.info(f"[TimeoutWrapper] Starting STEP {step_number}: {step_label} " f"(timeout={timeout_s}s)")

    wrapper = StepTimeout(timeout_seconds=timeout_s)
    return wrapper.run(
        fn=fn,
        args=args,
        kwargs=kwargs,
        fallback=fallback,
        step_label=f"STEP {step_number}: {step_label}",
    )
