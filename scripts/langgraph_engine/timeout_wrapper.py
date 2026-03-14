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
        step_number=1,
        args=(toon, user_requirement),
        fallback={"plan_required": True, "source": "timeout_fallback"}
    )
"""

import time
import threading
from typing import Any, Callable, Dict, Optional, Tuple
from datetime import datetime
from loguru import logger


# ---------------------------------------------------------------------------
# Canonical timeout values (seconds) per Level 3 step
# ---------------------------------------------------------------------------

STEP_TIMEOUTS: Dict[int, int] = {
    0:  60,   # Task Analysis (Ollama LLM call with 16K context)
    1:  45,   # Plan Mode Decision (Ollama classification)
    2: 120,   # Plan Execution (convergence loop with LLM)
    3:  60,   # Task Breakdown (parsing + validation)
    4:  30,   # TOON Refinement (local computation)
    5:  90,   # Skill & Agent Selection (filesystem scan + Ollama 16K ctx)
    6:  45,   # Skill Validation & Download (network I/O possible)
    7:  30,   # Final Prompt Generation (local formatting)
    8:  60,   # GitHub Issue Creation (Ollama title gen + network I/O)
    9:  30,   # Branch Creation (git operations)
    10: 300,  # Implementation Execution (Claude does heavy lifting)
    11: 60,   # Pull Request & Code Review (network + LLM)
    12: 30,   # Issue Closure (network I/O)
    13: 45,   # Project Documentation Update (file writes)
    14: 30,   # Final Summary & Voice Notification (local)
}

# Human-readable step labels for log messages
STEP_LABELS: Dict[int, str] = {
    1:  "Plan Mode Decision",
    2:  "Plan Execution",
    3:  "Task Breakdown",
    4:  "TOON Refinement",
    5:  "Skill & Agent Selection",
    6:  "Skill Validation & Download",
    7:  "Final Prompt Generation",
    8:  "GitHub Issue Creation",
    9:  "Branch Creation",
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
            step_label:   Label for log messages (e.g. "STEP 1: Plan Mode Decision").

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
                f"[TimeoutWrapper] {step_label} completed in {elapsed_ms:.0f}ms "
                f"(limit={self.timeout_seconds}s)"
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
        step_number:    Level 3 step number (1-14). Used for timeout lookup.
        args:           Positional arguments passed to fn.
        kwargs:         Keyword arguments passed to fn.
        fallback:       Return value if fn times out or raises. Should contain
                        safe default values for the step's output contract.
        custom_timeout: Override STEP_TIMEOUTS for this call (seconds).

    Returns:
        Result dict from fn on success, or fallback dict on timeout/error.

    Example:
        result = run_with_timeout(
            fn=planner.execute,
            step_number=1,
            args=(toon, user_requirement),
            fallback={"plan_required": True, "source": "timeout_fallback", "risk_level": "high"}
        )
    """
    timeout_s = custom_timeout if custom_timeout is not None else STEP_TIMEOUTS.get(step_number, 60)
    step_label = STEP_LABELS.get(step_number, f"Step {step_number}")

    logger.info(
        f"[TimeoutWrapper] Starting STEP {step_number}: {step_label} "
        f"(timeout={timeout_s}s)"
    )

    wrapper = StepTimeout(timeout_seconds=timeout_s)
    return wrapper.run(
        fn=fn,
        args=args,
        kwargs=kwargs,
        fallback=fallback,
        step_label=f"STEP {step_number}: {step_label}",
    )


# ---------------------------------------------------------------------------
# Fallback result builders for each critical step
# ---------------------------------------------------------------------------

def fallback_step1() -> Dict[str, Any]:
    """Safe fallback for Step 1 (Plan Mode Decision)."""
    return {
        "plan_required": True,
        "reasoning": "Timeout fallback - defaulting to plan mode for safety",
        "risk_level": "high",
        "decision_reasoning": "Timeout occurred, defaulting to plan mode",
        "source": "timeout_fallback",
        "fallback": True,
    }


def fallback_step2() -> Dict[str, Any]:
    """Safe fallback for Step 2 (Plan Execution)."""
    return {
        "success": False,
        "plan": "Timeout during plan execution - proceed with minimal plan",
        "files_affected": [],
        "phases": [{"phase_number": 1, "title": "Implementation", "description": "Execute task", "tasks": []}],
        "risks": {"risk_level": "high", "factors": ["Timeout during planning"], "mitigation": []},
        "source": "timeout_fallback",
    }


def fallback_step5() -> Dict[str, Any]:
    """Safe fallback for Step 5 (Skill & Agent Selection)."""
    return {
        "success": False,
        "selected_skills": [],
        "selected_agents": [],
        "skill_count": 0,
        "agent_count": 0,
        "source": "timeout_fallback",
        "reasoning": "Timeout during skill selection - no skills selected",
    }


def fallback_step7() -> Dict[str, Any]:
    """Safe fallback for Step 7 (Final Prompt Generation)."""
    return {
        "success": False,
        "prompt": "",
        "prompt_length": 0,
        "source": "timeout_fallback",
        "reasoning": "Timeout during prompt generation",
    }
