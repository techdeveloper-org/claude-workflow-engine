"""
Progress Display - Real-time step progress visualization for the 15-step pipeline (Step 0-14).

Provides:
- ASCII progress bars with completion percentage
- Per-step status display (PENDING / RUNNING / DONE / SKIPPED / FAILED)
- ETA calculation based on historical step timing data
- Real-time updates written to stderr so stdout stays clean for JSON output
- Thread-safe update mechanism for async contexts

Usage:
    from .progress_display import ProgressDisplay

    display = ProgressDisplay(session_id="abc-123", total_steps=14)
    display.start()

    display.update_step(step=1, status="RUNNING", label="Plan Mode Decision")
    time.sleep(2)
    display.update_step(step=1, status="DONE", duration_ms=1850)

    display.update_step(step=2, status="SKIPPED", label="Plan Execution")
    display.update_step(step=3, status="RUNNING", label="Task Breakdown")

    display.finish(final_status="SUCCESS")
"""

import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step metadata - human-readable labels for all 14 pipeline steps
# ---------------------------------------------------------------------------

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
    14: "Final Summary",
}

# Historical average durations in milliseconds (used for initial ETA estimation)
# These values are seeded from observed pipeline runs and updated at runtime.
HISTORICAL_STEP_DURATIONS_MS: Dict[int, float] = {
    1:  1200.0,
    2:  8500.0,
    3:  2800.0,
    4:  1500.0,
    5:  3200.0,
    6:  4500.0,
    7:  2100.0,
    8:  1800.0,
    9:  1400.0,
    10: 12000.0,
    11: 5500.0,
    12: 1200.0,
    13: 3000.0,
    14: 1800.0,
}

# Status display tokens
STATUS_ICONS: Dict[str, str] = {
    "PENDING":  "[ ]",
    "RUNNING":  "[>]",
    "DONE":     "[x]",
    "SKIPPED":  "[~]",
    "FAILED":   "[!]",
    "PARTIAL":  "[/]",
}

STATUS_LABELS: Dict[str, str] = {
    "PENDING":  "Pending",
    "RUNNING":  "Running",
    "DONE":     "Done",
    "SKIPPED":  "Skipped",
    "FAILED":   "Failed",
    "PARTIAL":  "Partial",
}


# ---------------------------------------------------------------------------
# StepRecord - tracks a single step's execution state
# ---------------------------------------------------------------------------

class StepRecord:
    """Tracks state of a single pipeline step."""

    def __init__(self, step_number: int):
        self.step_number = step_number
        self.label: str = STEP_LABELS.get(step_number, f"Step {step_number}")
        self.status: str = "PENDING"
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.detail: Optional[str] = None

    def start(self, label: Optional[str] = None) -> None:
        """Mark step as running."""
        if label:
            self.label = label
        self.status = "RUNNING"
        self.started_at = time.time()

    def complete(
        self,
        status: str = "DONE",
        duration_ms: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Mark step as finished."""
        self.status = status
        self.finished_at = time.time()
        if duration_ms is not None:
            self.duration_ms = duration_ms
        elif self.started_at is not None:
            self.duration_ms = (self.finished_at - self.started_at) * 1000
        if detail:
            self.detail = detail

    @property
    def elapsed_ms(self) -> Optional[float]:
        """Return elapsed milliseconds for running steps."""
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at else time.time()
        return (end - self.started_at) * 1000

    def format_duration(self) -> str:
        """Format duration for display."""
        ms = self.duration_ms or self.elapsed_ms
        if ms is None:
            return ""
        if ms < 1000:
            return f"{ms:.0f}ms"
        return f"{ms / 1000:.1f}s"


# ---------------------------------------------------------------------------
# ProgressDisplay - main display controller
# ---------------------------------------------------------------------------

class ProgressDisplay:
    """Real-time step progress visualization for the 15-step pipeline (Step 0-14).

    Thread-safe: update_step() can be called from any thread. A background
    refresh thread redraws the display every ``refresh_interval`` seconds.

    The display is written entirely to sys.stderr so the structured JSON
    output on stdout remains unpolluted.
    """

    def __init__(
        self,
        session_id: str = "",
        total_steps: int = 14,
        refresh_interval: float = 5.0,
        output_stream=None,
        enable_refresh_thread: bool = True,
    ):
        """
        Initialise the progress display.

        Args:
            session_id:            Pipeline session identifier for log linking.
            total_steps:           Total number of pipeline steps (default 14).
            refresh_interval:      Seconds between automatic redraws.
            output_stream:         Stream to write to (defaults to sys.stderr).
            enable_refresh_thread: Set False to disable background redraw thread
                                   (useful in tests or non-interactive environments).
        """
        self.session_id = session_id
        self.total_steps = total_steps
        self.refresh_interval = refresh_interval
        self.stream = output_stream or sys.stderr
        self.enable_refresh_thread = enable_refresh_thread

        # Step records keyed by step number
        self._steps: Dict[int, StepRecord] = {
            n: StepRecord(n) for n in range(1, total_steps + 1)
        }

        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._finished: bool = False
        self._final_status: str = "RUNNING"
        self._current_step: int = 0
        self._refresh_thread: Optional[threading.Thread] = None

        # Historical duration data (mutable copy - updated as steps complete)
        self._history: Dict[int, float] = dict(HISTORICAL_STEP_DURATIONS_MS)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start(self) -> None:
        """Begin displaying progress. Must be called before update_step()."""
        self._started_at = time.time()
        self._render()

        if self.enable_refresh_thread:
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop,
                daemon=True,
                name="ProgressRefresh",
            )
            self._refresh_thread.start()

    def update_step(
        self,
        step: int,
        status: str,
        label: Optional[str] = None,
        duration_ms: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        Update the state of a pipeline step.

        Args:
            step:        Step number (1-14).
            status:      One of PENDING / RUNNING / DONE / SKIPPED / FAILED / PARTIAL.
            label:       Optional human-readable label override.
            duration_ms: Elapsed milliseconds (auto-calculated if omitted).
            detail:      Short detail string shown next to the step.
        """
        with self._lock:
            if step not in self._steps:
                return

            record = self._steps[step]
            if status == "RUNNING" and record.status == "PENDING":
                record.start(label=label)
                self._current_step = step
            elif status in ("DONE", "SKIPPED", "FAILED", "PARTIAL"):
                if record.status == "PENDING":
                    record.start(label=label)
                record.complete(
                    status=status,
                    duration_ms=duration_ms,
                    detail=detail,
                )
                # Update historical data for better future ETA estimates
                if status == "DONE" and record.duration_ms:
                    self._history[step] = record.duration_ms

            elif status == "PENDING":
                record.status = "PENDING"
                if label:
                    record.label = label

        self._render()

    def finish(self, final_status: str = "SUCCESS") -> None:
        """Mark the pipeline as finished and render the final state."""
        with self._lock:
            self._finished = True
            self._final_status = final_status

        self._render()

    def get_eta(self) -> Optional[str]:
        """
        Calculate estimated remaining time.

        Returns:
            Human-readable ETA string e.g. "~42s remaining", or None if
            insufficient data.
        """
        with self._lock:
            return self._compute_eta()

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary dict of current progress state."""
        with self._lock:
            done = sum(1 for r in self._steps.values() if r.status == "DONE")
            skipped = sum(1 for r in self._steps.values() if r.status == "SKIPPED")
            failed = sum(1 for r in self._steps.values() if r.status == "FAILED")
            running = sum(1 for r in self._steps.values() if r.status == "RUNNING")
            elapsed = time.time() - self._started_at if self._started_at else 0
            return {
                "session_id": self.session_id,
                "total_steps": self.total_steps,
                "current_step": self._current_step,
                "done": done,
                "skipped": skipped,
                "failed": failed,
                "running": running,
                "elapsed_seconds": round(elapsed, 1),
                "eta": self._compute_eta(),
                "final_status": self._final_status,
            }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _compute_eta(self) -> Optional[str]:
        """Compute ETA string - must be called with lock held."""
        if self._finished or not self._started_at:
            return None

        remaining_ms = 0.0
        for step_num, record in self._steps.items():
            if record.status in ("PENDING", "RUNNING"):
                remaining_ms += self._history.get(step_num, 3000.0)
            elif record.status == "RUNNING" and record.elapsed_ms:
                # Only the remaining portion of a running step
                elapsed_for_step = record.elapsed_ms
                expected = self._history.get(step_num, 3000.0)
                remaining_ms += max(0, expected - elapsed_for_step)

        if remaining_ms <= 0:
            return "almost done"

        remaining_s = remaining_ms / 1000
        if remaining_s < 60:
            return f"~{remaining_s:.0f}s remaining"
        minutes = int(remaining_s // 60)
        seconds = int(remaining_s % 60)
        return f"~{minutes}m {seconds:02d}s remaining"

    def _build_progress_bar(self, width: int = 40) -> str:
        """Build a text progress bar for completed / total steps."""
        total = self.total_steps
        done = sum(1 for r in self._steps.values() if r.status in ("DONE", "SKIPPED"))
        filled = int(round((done / total) * width)) if total > 0 else 0
        bar = "#" * filled + "-" * (width - filled)
        pct = (done / total * 100) if total > 0 else 0
        return f"[{bar}] {done}/{total} ({pct:.0f}%)"

    def _format_step_line(self, record: StepRecord) -> str:
        """Format a single step line for display."""
        icon = STATUS_ICONS.get(record.status, "[ ]")
        label = record.label
        duration = record.format_duration()
        detail = f"  {record.detail}" if record.detail else ""
        dur_str = f" ({duration})" if duration else ""
        return f"  {icon} Step {record.step_number:02d}: {label}{dur_str}{detail}"

    def _render(self) -> None:
        """Render the current progress state to the output stream."""
        try:
            lines = self._build_display()
            self.stream.write("\n".join(lines) + "\n")
            self.stream.flush()
        except Exception:
            pass  # Never crash the pipeline due to display issues

    def _build_display(self) -> List[str]:
        """Build display lines (no I/O side effects)."""
        with self._lock:
            lines = []
            elapsed = time.time() - self._started_at if self._started_at else 0
            elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"

            # Header
            lines.append("")
            lines.append("=" * 60)
            if self._finished:
                lines.append(f"  Pipeline {self._final_status} | Elapsed: {elapsed_str}")
            else:
                eta = self._compute_eta() or ""
                eta_str = f" | ETA: {eta}" if eta else ""
                lines.append(
                    f"  Pipeline Running | Step {self._current_step}/{self.total_steps}"
                    f" | Elapsed: {elapsed_str}{eta_str}"
                )
            lines.append("=" * 60)

            # Progress bar
            lines.append(f"  {self._build_progress_bar()}")
            lines.append("")

            # Step list
            for step_num in range(1, self.total_steps + 1):
                record = self._steps[step_num]
                # Only show completed, running, and the next pending step
                if record.status != "PENDING" or step_num == self._current_step + 1:
                    lines.append(self._format_step_line(record))

            lines.append("=" * 60)
            return lines

    def _refresh_loop(self) -> None:
        """Background thread that redraws the display every refresh_interval seconds."""
        while not self._finished:
            time.sleep(self.refresh_interval)
            if not self._finished:
                self._render()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def create_display(session_id: str = "", total_steps: int = 14) -> ProgressDisplay:
    """Create and start a ProgressDisplay instance."""
    display = ProgressDisplay(session_id=session_id, total_steps=total_steps)
    display.start()
    return display


def format_step_status(step: int, total: int, label: str, status: str) -> str:
    """Return a single formatted status line - useful for simple logging."""
    icon = STATUS_ICONS.get(status, "[ ]")
    return f"{icon} Step {step}/{total}: {label} [{status}]"
