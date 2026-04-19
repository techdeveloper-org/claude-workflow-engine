"""
Logging Setup - Structured logging with Loguru and Rich terminal output.

Provides:
1. Loguru structured JSON logging to session folder
2. Rich terminal output with progress bars
3. Unified logger for all Level 3 execution
4. Session-specific logs with automatic rotation

# v1.15.2: removed log_toon_saved() method (TOON removed in v1.15.0).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn


class LoggingSetup:
    """Manages Loguru + Rich logging configuration for Level 3 execution."""

    def __init__(self, session_dir: Path, console: Optional[Console] = None):
        """
        Initialize logging for a session.

        Args:
            session_dir: Path to session folder (~/.claude/logs/sessions/{session_id}/)
            console: Optional Rich Console instance (created if None)
        """
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.console = console or Console()

        # Setup Loguru
        self._setup_loguru()

        # Setup Rich console logging
        self._setup_rich_logging()

        logger.info(f"Logging initialized for session: {self.session_dir.name}")

    def _setup_loguru(self):
        """Configure Loguru with structured JSON output and file rotation."""
        # Remove default handler
        logger.remove()

        # Execution log (human-readable)
        log_file = self.session_dir / "execution.log"
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="100 MB",
            retention="7 days",
            level="DEBUG",
        )

        # Structured JSON log (machine-readable)
        json_log_file = self.session_dir / "execution.jsonl"
        logger.add(
            str(json_log_file),
            format="{message}",
            rotation="100 MB",
            retention="7 days",
            serialize=True,  # JSON serialization
            level="INFO",
        )

        logger.info(f"Execution logs: {log_file}")
        logger.info(f"Structured logs: {json_log_file}")

    def _setup_rich_logging(self):
        """Configure Rich handler for beautiful console output."""
        # Remove default Python logging handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        # Add Rich handler
        handler = RichHandler(console=self.console, markup=True, rich_tracebacks=True, show_time=True, show_level=True)

        # Configure Python logging to use Rich
        logging.basicConfig(level="INFO", format="%(message)s", handlers=[handler])

        logger.info("[green][x][/green] Rich logging configured")

    def get_progress(self, total_tasks: int, description: str = "Executing") -> Progress:
        """
        Create a Rich progress bar for task tracking.

        Args:
            total_tasks: Number of tasks to track
            description: Progress bar description

        Returns:
            Rich Progress instance (context manager)

        Usage:
            with logging_setup.get_progress(14, "Level 3") as progress:
                task_id = progress.add_task(f"Step {i}...", total=1)
                progress.update(task_id, advance=1)
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console,
            transient=False,  # Keep progress bar after completion
        )

    def log_step_start(self, step_number: int, step_name: str, description: str = ""):
        """Log the start of an execution step."""
        logger.info(f"[STEP {step_number}] {step_name}")
        if description:
            logger.debug(f"  Description: {description}")

    def log_step_complete(self, step_number: int, step_name: str, duration_ms: float):
        """Log successful step completion."""
        logger.info(f"[STEP {step_number}] {step_name} ({duration_ms:.0f}ms)")

    def log_step_error(self, step_number: int, step_name: str, error: str):
        """Log step failure."""
        logger.error(f"[STEP {step_number}] FAILED {step_name}: {error}")

    def log_github_event(self, event_type: str, details: str):
        """Log GitHub integration event."""
        logger.info(f"[GITHUB] {event_type}: {details}")

    def log_tool_call(self, tool_name: str, args: dict, result: str = ""):
        """Log tool execution."""
        logger.debug(f"[TOOL] {tool_name} called with {len(args)} args")
        if result:
            logger.debug(f"[TOOL] {tool_name} result: {result[:100]}...")

    def get_session_summary(self) -> dict:
        """Generate summary of logged session."""
        return {
            "session_dir": str(self.session_dir),
            "execution_log": str(self.session_dir / "execution.log"),
            "structured_log": str(self.session_dir / "execution.jsonl"),
            "timestamp": datetime.now().isoformat(),
        }


class ExecutionLogger:
    """
    High-level execution logger for LEVEL 3 steps.

    Provides consistent logging interface across all active steps (Step 0, Steps 8-14).
    """

    def __init__(self, session_dir: Path):
        self.setup = LoggingSetup(session_dir)
        self.steps_log = []

    def log_execution_step(
        self,
        step_number: int,
        step_name: str,
        status: str,  # "running", "success", "failed", "skipped"
        message: str = "",
        duration_ms: float = 0,
        error: str = None,
    ):
        """
        Log a complete execution step.

        Args:
            step_number: Step number (0, 8-14)
            step_name: Step name (e.g., "GitHub Issue Creation")
            status: "running", "success", "failed", "skipped"
            message: Additional context
            duration_ms: Time taken
            error: Error message if failed
        """
        log_entry = {
            "step": step_number,
            "name": step_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "message": message,
            "error": error,
        }

        self.steps_log.append(log_entry)

        # Log to loguru
        if status == "success":
            self.setup.log_step_complete(step_number, step_name, duration_ms)
        elif status == "failed":
            self.setup.log_step_error(step_number, step_name, error or message)
        elif status == "running":
            self.setup.log_step_start(step_number, step_name, message)
        else:
            logger.info(f"[STEP {step_number}] {status.upper()}: {step_name}")

    def save_execution_log(self, file_path: Optional[Path] = None):
        """
        Save execution log to JSON file.

        Args:
            file_path: Path to save to (default: session_dir/steps.json)
        """
        if file_path is None:
            file_path = self.setup.session_dir / "steps.json"

        import json

        with open(file_path, "w") as f:
            json.dump(self.steps_log, f, indent=2)

        logger.info(f"Execution log saved: {file_path}")

    def get_execution_summary(self) -> dict:
        """Get summary of all executed steps."""
        successful = sum(1 for s in self.steps_log if s["status"] == "success")
        failed = sum(1 for s in self.steps_log if s["status"] == "failed")
        total_time = sum(s.get("duration_ms", 0) for s in self.steps_log)

        return {
            "total_steps": len(self.steps_log),
            "successful": successful,
            "failed": failed,
            "total_time_ms": total_time,
            "steps": self.steps_log,
        }


def setup_logger(session_dir: Path, session_id: str) -> ExecutionLogger:
    """
    Quick setup function for Level 3 execution.

    Returns ready-to-use ExecutionLogger instance.

    Usage:
        exec_logger = setup_logger(session_dir, session_id)
        exec_logger.log_execution_step(8, "GitHub Issue Creation", "running")
        exec_logger.log_execution_step(8, "GitHub Issue Creation", "success", duration_ms=1234)
    """
    return ExecutionLogger(session_dir)
