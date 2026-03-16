"""
UI Components - Unified UX layer for the 15-step pipeline (Step 0-14).

This module is the single entry point for all user experience concerns:
- Progress visibility (delegates to ProgressDisplay)
- Decision explanations (delegates to DecisionExplainer)
- Error message formatting (delegates to ErrorMessages)
- Pipeline session summary rendering
- Help and onboarding text

All output goes to sys.stderr (or a configured stream) so JSON output
on stdout is never polluted.

Usage:
    from .ui_components import PipelineUI

    ui = PipelineUI(session_id="abc-123")
    ui.start_pipeline(total_steps=14)

    ui.step_started(step=1, label="Plan Mode Decision")
    # ... run step 1 ...
    ui.step_done(step=1, duration_ms=1200, detail="Planning skipped")

    ui.explain_decision("plan", state=flow_state)

    try:
        raise ConnectionRefusedError("port 11434 refused")
    except Exception as e:
        ui.show_error(e, step=1)

    ui.finish_pipeline(final_status="SUCCESS")
"""

import sys
import time
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .progress_display import ProgressDisplay, STEP_LABELS, format_step_status
from .decision_explainer import DecisionExplainer, DecisionExplanation
from .error_messages import ErrorMessages, FormattedError, format_error


# ---------------------------------------------------------------------------
# Terminal width helper
# ---------------------------------------------------------------------------

def _terminal_width(default: int = 72) -> int:
    """Return the current terminal width, falling back to default."""
    try:
        import shutil
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:
        return default


# ---------------------------------------------------------------------------
# PipelineUI - unified UX controller
# ---------------------------------------------------------------------------

class PipelineUI:
    """
    Unified user experience controller for the 15-step pipeline (Step 0-14).

    Coordinates progress display, decision explanations, and error messages
    into a single coherent interface that all pipeline nodes can use.

    Thread-safe: all public methods acquire an internal lock before writing.
    """

    def __init__(
        self,
        session_id: str = "",
        total_steps: int = 14,
        output_stream=None,
        enable_progress_thread: bool = True,
        verbose: bool = False,
    ):
        """
        Initialise the UI controller.

        Args:
            session_id:             Pipeline session identifier.
            total_steps:            Total pipeline steps (default 14).
            output_stream:          Output stream (defaults to sys.stderr).
            enable_progress_thread: Enable background refresh thread.
            verbose:                If True, print extra details for each decision.
        """
        self.session_id = session_id
        self.total_steps = total_steps
        self.stream = output_stream or sys.stderr
        self.verbose = verbose

        self._progress: Optional[ProgressDisplay] = None
        self._explainer = DecisionExplainer()
        self._error_formatter = ErrorMessages()

        self._enable_progress_thread = enable_progress_thread
        self._started_at: Optional[float] = None
        self._step_errors: Dict[int, List[str]] = {}

    # -----------------------------------------------------------------------
    # Pipeline lifecycle
    # -----------------------------------------------------------------------

    def start_pipeline(self, total_steps: Optional[int] = None) -> None:
        """
        Begin the pipeline UX session.

        Creates the progress display and prints the session header.
        Must be called before any step_ methods.

        Args:
            total_steps: Override total step count if different from init value.
        """
        if total_steps:
            self.total_steps = total_steps

        self._started_at = time.time()
        self._progress = ProgressDisplay(
            session_id=self.session_id,
            total_steps=self.total_steps,
            refresh_interval=5.0,
            output_stream=self.stream,
            enable_refresh_thread=self._enable_progress_thread,
        )

        self._print_header()
        self._progress.start()

    def finish_pipeline(self, final_status: str = "SUCCESS") -> None:
        """
        Mark the pipeline as finished and render the final summary.

        Args:
            final_status: SUCCESS / FAILED / PARTIAL.
        """
        if self._progress:
            self._progress.finish(final_status=final_status)

        elapsed = time.time() - self._started_at if self._started_at else 0
        self._print_footer(final_status=final_status, elapsed=elapsed)

    # -----------------------------------------------------------------------
    # Step lifecycle
    # -----------------------------------------------------------------------

    def step_started(self, step: int, label: Optional[str] = None) -> None:
        """
        Mark a pipeline step as running.

        Args:
            step:  Step number (1-14).
            label: Optional label override.
        """
        if self._progress:
            self._progress.update_step(
                step=step, status="RUNNING", label=label
            )
        effective_label = label or STEP_LABELS.get(step, f"Step {step}")
        self._write(format_step_status(step, self.total_steps, effective_label, "RUNNING"))

    def step_done(
        self,
        step: int,
        duration_ms: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        Mark a pipeline step as successfully completed.

        Args:
            step:        Step number.
            duration_ms: Step execution time in milliseconds.
            detail:      Optional short detail string.
        """
        if self._progress:
            self._progress.update_step(
                step=step, status="DONE", duration_ms=duration_ms, detail=detail
            )
        label = STEP_LABELS.get(step, f"Step {step}")
        dur_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
        self._write(
            format_step_status(step, self.total_steps, label + dur_str, "DONE")
        )

    def step_skipped(self, step: int, reason: str = "") -> None:
        """
        Mark a pipeline step as skipped (intentionally not executed).

        Args:
            step:   Step number.
            reason: Short reason why step was skipped.
        """
        if self._progress:
            self._progress.update_step(
                step=step, status="SKIPPED", detail=reason if reason else None
            )
        label = STEP_LABELS.get(step, f"Step {step}")
        reason_str = f" - {reason}" if reason else ""
        self._write(
            format_step_status(step, self.total_steps, label + reason_str, "SKIPPED")
        )

    def step_failed(
        self,
        step: int,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """
        Mark a pipeline step as failed.

        Args:
            step:        Step number.
            error:       Short error description.
            duration_ms: Step execution time before failure.
        """
        if self._progress:
            self._progress.update_step(
                step=step, status="FAILED", duration_ms=duration_ms, detail=error
            )
        label = STEP_LABELS.get(step, f"Step {step}")
        error_str = f" - {error}" if error else ""
        self._write(
            format_step_status(step, self.total_steps, label + error_str, "FAILED")
        )

    # -----------------------------------------------------------------------
    # Decision explanations
    # -----------------------------------------------------------------------

    def explain_decision(
        self,
        decision_type: str,
        state: Optional[Dict[str, Any]] = None,
        explanation: Optional[DecisionExplanation] = None,
    ) -> None:
        """
        Display a human-readable explanation for a pipeline decision.

        Args:
            decision_type: "plan" / "skill" / "approach"
            state:         FlowState dict (auto-generates explanation if provided).
            explanation:   Pre-built DecisionExplanation (used if state is None).
        """
        if explanation is None and state is not None:
            all_explanations = self._explainer.explain_from_state(state)
            explanation = all_explanations.get(decision_type)

        if explanation is None:
            return

        self._write("")
        self._write(_separator("Decision: " + explanation.decision_made))
        self._write(explanation.summary)
        self._write(_separator())

    def explain_plan_decision(
        self,
        plan_required: bool,
        task_complexity: int = 5,
        task_count: int = 1,
        files_affected: int = 0,
        reasoning: str = "",
        model_used: str = "",
    ) -> None:
        """Display plan decision explanation inline."""
        exp = self._explainer.explain_plan_decision(
            plan_required=plan_required,
            task_complexity=task_complexity,
            task_count=task_count,
            files_affected=files_affected,
            reasoning=reasoning,
            model_used=model_used,
        )
        self.explain_decision("plan", explanation=exp)

    def explain_skill_selection(
        self,
        selected_skill: str,
        task_description: str = "",
        candidate_skills: Optional[List[str]] = None,
        capability_scores: Optional[Dict[str, int]] = None,
        selection_reasoning: str = "",
    ) -> None:
        """Display skill selection explanation inline."""
        exp = self._explainer.explain_skill_selection(
            selected_skill=selected_skill,
            task_description=task_description,
            candidate_skills=candidate_skills or [],
            capability_scores=capability_scores or {},
            selection_reasoning=selection_reasoning,
        )
        self.explain_decision("skill", explanation=exp)

    def explain_approach(
        self,
        approach: str,
        task_description: str = "",
        framework: str = "",
        standards_applied: bool = False,
        files_to_modify: Optional[List[str]] = None,
        reasoning: str = "",
        risk_level: str = "LOW",
    ) -> None:
        """Display implementation approach explanation inline."""
        exp = self._explainer.explain_approach_decision(
            approach=approach,
            task_description=task_description,
            framework=framework,
            standards_applied=standards_applied,
            files_to_modify=files_to_modify or [],
            reasoning=reasoning,
            risk_level=risk_level,
        )
        self.explain_decision("approach", explanation=exp)

    # -----------------------------------------------------------------------
    # Error display
    # -----------------------------------------------------------------------

    def show_error(
        self,
        error: Any,
        step: Optional[int] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Display a user-friendly error message.

        Accepts either an Exception instance or a string error type + detail.

        Args:
            error:      Exception instance, or a detail string if error_type provided.
            step:       Step number where the error occurred.
            error_type: Error category (auto-detected from exception type if omitted).
        """
        ctx: Dict[str, Any] = {}
        if step is not None:
            ctx["step"] = step
        if self.session_id:
            ctx["session_id"] = self.session_id

        if isinstance(error, Exception):
            formatted = self._error_formatter.format_from_exception(
                error, step=step, session_id=self.session_id
            )
        else:
            etype = error_type or "GENERIC"
            formatted = self._error_formatter.format(
                etype, detail=str(error), context=ctx
            )

        self._write(formatted.full_text)

        # Track errors per step
        if step is not None:
            self._step_errors.setdefault(step, []).append(formatted.user_message)

    def show_warning(self, message: str, step: Optional[int] = None) -> None:
        """Display a non-fatal warning message."""
        step_str = f" [Step {step}]" if step else ""
        self._write(f"[WARNING]{step_str} {message}")

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        self._write(f"[INFO] {message}")

    def show_help(self, topic: str = "") -> None:
        """Display help text for a given topic."""
        text = self._error_formatter.format_help(topic=topic)
        self._write(text)

    # -----------------------------------------------------------------------
    # ETA and progress queries
    # -----------------------------------------------------------------------

    def get_eta(self) -> Optional[str]:
        """Return current ETA string, or None if progress not started."""
        if self._progress:
            return self._progress.get_eta()
        return None

    def get_progress_summary(self) -> Dict[str, Any]:
        """Return a progress summary dict."""
        if self._progress:
            return self._progress.get_summary()
        return {"session_id": self.session_id, "status": "not_started"}

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _write(self, text: str) -> None:
        """Write a line to the output stream (never raises)."""
        try:
            self.stream.write(text + "\n")
            self.stream.flush()
        except Exception:
            pass

    def _print_header(self) -> None:
        """Print the pipeline session start header."""
        width = min(_terminal_width(), 72)
        lines = [
            "",
            "=" * width,
            f"  Claude Workflow Engine Pipeline  |  Session: {self.session_id or 'N/A'}",
            f"  Steps: {self.total_steps}  |  Started: {_now_str()}",
            "=" * width,
        ]
        for line in lines:
            self._write(line)

    def _print_footer(self, final_status: str, elapsed: float) -> None:
        """Print the pipeline session end footer."""
        width = min(_terminal_width(), 72)
        elapsed_str = (
            f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
        )
        errors_count = sum(len(v) for v in self._step_errors.values())

        lines = [
            "",
            "=" * width,
            f"  Pipeline {final_status}  |  Duration: {elapsed_str}",
        ]
        if errors_count:
            lines.append(f"  Errors encountered: {errors_count} (see log for details)")
        lines.append("=" * width)
        lines.append("")

        for line in lines:
            self._write(line)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def create_ui(session_id: str = "", total_steps: int = 14) -> PipelineUI:
    """Create a PipelineUI instance (does not start it)."""
    return PipelineUI(session_id=session_id, total_steps=total_steps)


def render_step_banner(step: int, label: str, total: int = 14) -> str:
    """Return a formatted step banner string."""
    width = 60
    title = f" Step {step}/{total}: {label} "
    padding = max(0, width - len(title) - 2)
    left = padding // 2
    right = padding - left
    return f"\n{'=' * width}\n{' ' * left}{title}{' ' * right}\n{'=' * width}"


def render_session_summary(
    session_id: str,
    steps_done: int,
    steps_total: int,
    elapsed_seconds: float,
    final_status: str,
    errors: Optional[List[str]] = None,
) -> str:
    """Return a formatted session summary string."""
    errors = errors or []
    elapsed_str = (
        f"{elapsed_seconds:.0f}s"
        if elapsed_seconds < 60
        else f"{elapsed_seconds / 60:.1f}m"
    )
    lines = [
        "",
        "Session Summary",
        "-" * 40,
        f"Session ID : {session_id}",
        f"Status     : {final_status}",
        f"Steps done : {steps_done}/{steps_total}",
        f"Duration   : {elapsed_str}",
    ]
    if errors:
        lines.append(f"Errors     : {len(errors)}")
        for err in errors[:3]:
            lines.append(f"  - {err[:80]}")
        if len(errors) > 3:
            lines.append(f"  ... and {len(errors) - 3} more")
    lines.append("-" * 40)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _separator(title: str = "") -> str:
    """Return a separator line with optional centered title."""
    width = min(_terminal_width(), 72)
    if not title:
        return "-" * width
    pad = width - len(title) - 4
    left = pad // 2
    right = pad - left
    return f"{'- ' * (left // 2)}{title}{'- ' * (right // 2)}"


def _now_str() -> str:
    """Return current datetime as a short string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
