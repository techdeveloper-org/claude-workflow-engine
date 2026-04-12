"""
Recovery Handler - Graceful interrupt handling and execution resume.

Installs a SIGINT handler that saves an emergency checkpoint on Ctrl+C,
cleans up open resources, and prints resume instructions.

Also provides resume_from_checkpoint() to restart an interrupted session
from the last saved state.

Resume supports:
- Resume from last checkpoint:  resume_from_checkpoint(session_id="abc-123")
- Resume from specific step:    resume_from_checkpoint(session_id="abc-123",
                                    checkpoint_id="abc-123:step-05")
- CLI: python -m ... recovery_handler resume <session_id> [<checkpoint_id>]

Retry behaviour during resume uses exponential backoff:
    Delays: 1s, 2s, 4s, 8s (max) between step retries on transient failure.
    Max 3 retry attempts per step before giving up.

Usage (install once at process start):
    from .recovery_handler import RecoveryHandler

    handler = RecoveryHandler(session_id=sid, step_executor=my_executor)
    handler.install_signal_handlers()

Resume an interrupted session:
    from .recovery_handler import resume_from_checkpoint
    resume_from_checkpoint(session_id="abc-123")
    resume_from_checkpoint(session_id="abc-123", checkpoint_id="abc-123:step-05")
"""

import signal
import sys
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from .checkpoint_manager import CheckpointManager
    from .error_logger import ErrorLogger
except ImportError:
    # Standalone execution (python recovery_handler.py ...)
    import os as _os
    import sys as _sys

    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from checkpoint_manager import CheckpointManager  # type: ignore
    from error_logger import ErrorLogger  # type: ignore


# ---------------------------------------------------------------------------
# Exponential backoff configuration
# ---------------------------------------------------------------------------

# Delays in seconds for retry attempts (1s, 2s, 4s, 8s max)
_BACKOFF_DELAYS: List[float] = [1.0, 2.0, 4.0, 8.0]
# Maximum retry attempts per step during resume
_MAX_STEP_RETRIES: int = 3


def _backoff_delay(attempt: int) -> float:
    """Return backoff delay (seconds) for the given attempt index (0-indexed)."""
    idx = min(attempt, len(_BACKOFF_DELAYS) - 1)
    return _BACKOFF_DELAYS[idx]


def _is_transient_error(exc: Exception) -> bool:
    """
    Heuristic: decide if an exception is likely transient and worth retrying.

    Transient errors: network timeouts, connection errors, rate-limit responses.
    Non-transient: validation errors, missing files, programming errors.
    """
    err_lower = str(exc).lower()
    transient_keywords = (
        "timeout",
        "connection",
        "rate limit",
        "overloaded",
        "503",
        "502",
        "too many requests",
        "retry",
        "network",
        "unavailable",
        "refused",
    )
    return any(kw in err_lower for kw in transient_keywords)


# ---------------------------------------------------------------------------
# Module-level interrupt state (shared across nested calls)
# ---------------------------------------------------------------------------

_current_step: int = 0
_current_state: Dict[str, Any] = {}
_checkpoint_manager: Optional[CheckpointManager] = None
_error_logger: Optional[ErrorLogger] = None
_cleanup_callbacks: list = []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _register_globals(
    step: int,
    state: Dict[str, Any],
    cp: CheckpointManager,
    el: ErrorLogger,
) -> None:
    """Update module-level state so the signal handler can access it."""
    global _current_step, _current_state, _checkpoint_manager, _error_logger
    _current_step = step
    _current_state = state
    _checkpoint_manager = cp
    _error_logger = el


def _run_cleanup_callbacks() -> None:
    """Execute registered cleanup callbacks, swallowing individual failures."""
    for cb in _cleanup_callbacks:
        try:
            cb()
        except Exception as e:
            logger.warning(f"[Recovery] Cleanup callback failed: {e}")


# ---------------------------------------------------------------------------
# Signal handler (module-level, required by signal.signal)
# ---------------------------------------------------------------------------


def _sigint_handler(signum: int, frame: Any) -> None:
    """
    Handle Ctrl+C (SIGINT) gracefully.

    1. Log the interruption.
    2. Save an emergency checkpoint (with success_status=False).
    3. Run cleanup callbacks.
    4. Print resume instructions including the checkpoint_id.
    5. Exit with code 130 (standard SIGINT exit code).
    """
    print("\n", file=sys.stderr)

    if _error_logger:
        _error_logger.log_error(
            step=f"Step {_current_step}",
            error_message="Execution interrupted by user (Ctrl+C / SIGINT)",
            severity="WARNING",
            error_type="UserInterrupt",
            recovery_action="Emergency checkpoint saved",
        )

    checkpoint_path = "N/A"
    checkpoint_id = "N/A"
    if _checkpoint_manager and _current_state:
        try:
            _checkpoint_manager.save_checkpoint(
                _current_step,
                _current_state,
                success_status=False,
                error_message="Interrupted by user (SIGINT)",
            )
            checkpoint_path = str(_checkpoint_manager.checkpoint_dir / f"step-{_current_step:02d}.json")
            checkpoint_id = _checkpoint_manager._make_checkpoint_id(_current_step)
        except Exception as e:
            print(f"[Recovery] Failed to save emergency checkpoint: {e}", file=sys.stderr)

    _run_cleanup_callbacks()

    session_id = _current_state.get("session_id", "unknown") if _current_state else "unknown"

    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("[WARNING] Process interrupted", file=sys.stderr)
    print(f"  Last step:     {_current_step}", file=sys.stderr)
    print(f"  Checkpoint ID: {checkpoint_id}", file=sys.stderr)
    print(f"  Checkpoint:    {checkpoint_path}", file=sys.stderr)
    print(f"  Session ID:    {session_id}", file=sys.stderr)
    print("", file=sys.stderr)
    print("To resume execution run:", file=sys.stderr)
    print(f"  python -m langgraph_engine.recovery_handler " f"resume {session_id} {checkpoint_id}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    sys.exit(130)


# ---------------------------------------------------------------------------
# RecoveryHandler class
# ---------------------------------------------------------------------------


class RecoveryHandler:
    """
    Manages interrupt handling and step-tracking for an execution session.

    Register this once before the pipeline starts; then call update_state()
    at the beginning of every step so the emergency handler always has the
    latest state.
    """

    def __init__(
        self,
        session_id: str,
        step_executor: Optional[Callable] = None,
        base_log_dir: str = "~/.claude/logs",
    ):
        """
        Initialise the recovery handler.

        Args:
            session_id:    Current session identifier.
            step_executor: Optional callable(step, state) -> dict|None.
                           Used by resume_session() to replay steps.
            base_log_dir:  Base directory for checkpoints and error logs.
        """
        self.session_id = session_id
        self.step_executor = step_executor

        self.checkpoint_manager = CheckpointManager(session_id, base_dir=base_log_dir)
        self.error_logger = ErrorLogger(
            session_id=session_id,
            log_base_dir=base_log_dir,
        )

        self._start_time = time.time()
        self._cleanup_fns: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install_signal_handlers(self) -> None:
        """
        Install SIGINT (Ctrl+C) and SIGTERM handlers.

        Windows does not support SIGTERM reliably, so SIGTERM registration
        is attempted but silently skipped on failure.
        Signal handlers can only be registered from the main thread.
        """
        import threading

        if threading.current_thread() is not threading.main_thread():
            logger.warning(
                "[Recovery] install_signal_handlers() called outside main thread " "- SIGINT handler NOT installed"
            )
            return

        signal.signal(signal.SIGINT, _sigint_handler)

        # Register SIGTERM on non-Windows platforms
        if hasattr(signal, "SIGTERM"):
            try:
                signal.signal(signal.SIGTERM, _sigint_handler)
            except (OSError, ValueError):
                pass  # May fail inside subprocesses

        logger.info("[Recovery] Signal handlers installed (SIGINT/SIGTERM)")

    def register_cleanup(self, callback: Callable) -> None:
        """
        Register a no-arg cleanup callback invoked on interrupt.

        Args:
            callback: Callable() executed before process exits on SIGINT.
        """
        self._cleanup_fns.append(callback)
        _cleanup_callbacks.append(callback)

    def update_state(self, step: int, state: Dict[str, Any]) -> None:
        """
        Update the module-level globals so the signal handler has current state.

        Call this at the START of every step node so emergency saves always
        capture the most recent FlowState.

        Args:
            step:  Current step number.
            state: Current FlowState dict.
        """
        _register_globals(step, state, self.checkpoint_manager, self.error_logger)

    def save_step_checkpoint(
        self,
        step: int,
        state: Dict[str, Any],
        success_status: bool = True,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Save a checkpoint after a step completes.

        Wraps CheckpointManager.save_checkpoint() with error logging.

        Args:
            step:           Completed step number.
            state:          Post-step FlowState dict.
            success_status: True if step succeeded.
            error_message:  Optional error description for failed steps.

        Returns:
            True on success.
        """
        ok = self.checkpoint_manager.save_checkpoint(
            step,
            state,
            success_status=success_status,
            error_message=error_message,
        )
        if ok:
            self.error_logger.log_decision(
                step=f"Step {step}",
                decision="Checkpoint saved",
                reasoning=(
                    f"Step {step} completed "
                    f"({'successfully' if success_status else 'with error'}); "
                    "state persisted to disk"
                ),
            )
        else:
            self.error_logger.log_error(
                step=f"Step {step}",
                error_message="Failed to save checkpoint",
                severity="WARNING",
                error_type="IOError",
                recovery_action="Execution will continue but resume may fail",
            )
        return ok

    def resume_session(self, checkpoint_id: Optional[str] = None) -> bool:
        """
        Resume execution from a checkpoint.

        If checkpoint_id is provided, loads that specific checkpoint.
        Otherwise loads the last saved checkpoint and resumes from there.

        Each step is attempted up to _MAX_STEP_RETRIES times on transient
        failure, with exponential backoff between retries (1s, 2s, 4s, 8s).

        Requires self.step_executor to be set with signature:
            executor(step: int, state: dict) -> dict | None

        Args:
            checkpoint_id: Optional specific checkpoint to resume from,
                           e.g. "my-session:step-05".

        Returns:
            True if all remaining steps executed successfully.
        """
        if not self.step_executor:
            logger.error("[Recovery] Cannot resume: no step_executor registered")
            return False

        # Load the appropriate starting checkpoint
        if checkpoint_id:
            logger.info(f"[Recovery] Resuming from checkpoint_id={checkpoint_id}")
            state = self.checkpoint_manager.load_checkpoint_by_id(checkpoint_id)
            if state is None:
                logger.error(f"[Recovery] Checkpoint not found: {checkpoint_id}")
                print(f"Checkpoint not found: {checkpoint_id}", file=sys.stderr)
                return False
            # Determine starting step from checkpoint_id
            try:
                step_part = checkpoint_id.split(":")[-1]  # "step-05"
                if step_part.startswith("step-"):
                    last_step = int(step_part[5:])
                else:
                    last_step = int(step_part)
            except (ValueError, IndexError):
                last_step, state = self.checkpoint_manager.get_last_checkpoint()
        else:
            last_step, state = self.checkpoint_manager.get_last_checkpoint()

        if state is None:
            logger.warning(f"[Recovery] No checkpoint found for session {self.session_id}")
            print(f"No checkpoint found for session {self.session_id}", file=sys.stderr)
            return False

        next_step = (last_step or 0) + 1
        logger.info(
            f"[Recovery] Resuming session {self.session_id} "
            f"from step {next_step} (last completed: step {last_step})"
        )
        self.error_logger.log_decision(
            step=f"Step {next_step}",
            decision=f"Resuming from checkpoint (last completed: step {last_step})",
            reasoning="Previous session was interrupted; loaded persisted state",
        )

        print(f"Resuming session {self.session_id} from step {next_step}...", file=sys.stderr)

        for step in range(next_step, 15):  # Steps 1-14
            self.update_state(step, state)
            step_success = False
            last_exc: Optional[Exception] = None

            for attempt in range(_MAX_STEP_RETRIES):
                try:
                    result = self.step_executor(step, state)
                    if result:
                        state.update(result)
                    self.save_step_checkpoint(step, state, success_status=True)
                    step_success = True
                    last_exc = None
                    break  # Step succeeded

                except Exception as e:
                    last_exc = e
                    is_transient = _is_transient_error(e)

                    self.error_logger.log_error(
                        step=f"Step {step}",
                        error_message=str(e),
                        severity="WARNING" if is_transient else "ERROR",
                        error_type=type(e).__name__,
                        recovery_action=(
                            f"Retry {attempt + 1}/{_MAX_STEP_RETRIES} " f"with {_backoff_delay(attempt):.0f}s backoff"
                            if is_transient and attempt < _MAX_STEP_RETRIES - 1
                            else "Execution halted at failed step"
                        ),
                    )

                    if is_transient and attempt < _MAX_STEP_RETRIES - 1:
                        delay = _backoff_delay(attempt)
                        logger.warning(
                            f"[Recovery] Step {step} transient error "
                            f"(attempt {attempt + 1}/{_MAX_STEP_RETRIES}) - "
                            f"retrying in {delay:.0f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        # Non-transient or last retry - save failed checkpoint and stop
                        self.save_step_checkpoint(
                            step,
                            state,
                            success_status=False,
                            error_message=str(e),
                        )
                        break

            if not step_success:
                logger.error(f"[Recovery] Step {step} failed after {_MAX_STEP_RETRIES} attempts: " f"{last_exc}")
                return False

        logger.info("[Recovery] Session resume complete")
        return True


# ---------------------------------------------------------------------------
# Module-level convenience function (matches task spec)
# ---------------------------------------------------------------------------


def resume_from_checkpoint(
    session_id: str,
    step_executor: Optional[Callable] = None,
    checkpoint_id: Optional[str] = None,
) -> bool:
    """
    Resume execution from the last (or specified) checkpoint of the given session.

    This is the public entry-point used by the CLI and orchestrator.

    Args:
        session_id:    Session to resume.
        step_executor: Optional callable(step, state) -> dict|None.
        checkpoint_id: Optional specific checkpoint ID to resume from,
                       e.g. "my-session:step-05".  When None, resumes from
                       the last saved checkpoint.

    Returns:
        True if all remaining steps executed successfully.
    """
    handler = RecoveryHandler(
        session_id=session_id,
        step_executor=step_executor,
    )
    return handler.resume_session(checkpoint_id=checkpoint_id)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Usage:
        python -m langgraph_engine.recovery_handler resume <session_id>
        python -m langgraph_engine.recovery_handler resume <session_id> <checkpoint_id>
        python -m langgraph_engine.recovery_handler list   <session_id>
    """
    args = sys.argv[1:]

    if not args:
        print("Usage: recovery_handler <resume|list> <session_id> [<checkpoint_id>]")
        sys.exit(1)

    command = args[0]
    sid = args[1] if len(args) > 1 else "unknown"
    cp_id = args[2] if len(args) > 2 else None

    if command == "resume":
        print(f"[Recovery] Resuming session: {sid}", file=sys.stderr)
        if cp_id:
            print(f"[Recovery] Starting from checkpoint: {cp_id}", file=sys.stderr)
        success = resume_from_checkpoint(
            session_id=sid,
            checkpoint_id=cp_id,
        )
        sys.exit(0 if success else 1)

    elif command == "list":
        mgr = CheckpointManager(sid)
        checkpoints = mgr.list_checkpoints()
        if not checkpoints:
            print(f"No checkpoints found for session: {sid}")
        else:
            print(f"Checkpoints for session {sid}:")
            for cp in checkpoints:
                status = "OK" if cp.get("success_status", True) else "FAILED"
                err = cp.get("error_message") or ""
                err_suffix = f"  [{err[:60]}]" if err else ""
                print(
                    f"  Step {cp['step']:02d}  {status:<6}  {cp['timestamp']}  " f"id={cp['checkpoint_id']}{err_suffix}"
                )

    else:
        print(f"Unknown command: {command}")
        print("Commands: resume, list")
        sys.exit(1)
