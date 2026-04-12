"""
Session Manager - File-based persistence for Level 3 execution.

Manages session folders, logs, and state.
Session structure: ~/.claude/logs/sessions/{session_id}/

# v1.15.2: removed TOON persistence methods (save_toon_analysis, save_execution_blueprint,
#           save_toon_with_skills, load_latest_toon, cleanup_old_toots) and the fatal
#           `from .toon_models import ...` that caused ImportError after toon_models.py
#           was deleted in v1.15.2.  save_session_metadata and add_execution_log now
#           accept plain dicts and use json.dumps directly (no Pydantic dependency).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from utils.path_resolver import get_session_logs_dir

    _SESSION_LOGS_DIR = get_session_logs_dir()
except ImportError:
    _SESSION_LOGS_DIR = Path.home() / ".claude" / "logs" / "sessions"


class SessionManager:
    """Manages file-based session persistence."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = _SESSION_LOGS_DIR / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        log_file = self.session_dir / "execution.log"
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="100 MB",
            retention="7 days",
        )

        logger.info(f"Session {session_id} initialized at {self.session_dir}")

    def save_session_metadata(self, metadata: Dict[str, Any]) -> Path:
        """Save session metadata as JSON."""
        file_path = self.session_dir / "session.json"
        content = json.dumps(metadata, indent=2, default=str)
        file_path.write_text(content)
        logger.info(f"Session metadata saved: {file_path}")
        return file_path

    def save_prompt(self, prompt_text: str) -> Path:
        """Save execution prompt (Step 0 output)."""
        file_path = self.session_dir / "prompt.txt"
        file_path.write_text(prompt_text)
        logger.info(f"Execution prompt saved: {file_path}")
        return file_path

    def save_task_breakdown(self, tasks: Dict[str, Any]) -> Path:
        """Save task breakdown."""
        file_path = self.session_dir / "tasks.json"
        content = json.dumps(tasks, indent=2)
        file_path.write_text(content)
        logger.info(f"Task breakdown saved: {file_path}")
        return file_path

    def save_github_details(self, details: Dict[str, Any]) -> Path:
        """Save GitHub issue/PR details (Steps 8, 11)."""
        file_path = self.session_dir / "github.json"
        content = json.dumps(details, indent=2)
        file_path.write_text(content)
        logger.info(f"GitHub details saved: {file_path}")
        return file_path

    def save_execution_logs(self, logs: list) -> Path:
        """Save structured execution logs."""
        file_path = self.session_dir / "logs.json"
        content = json.dumps(logs, indent=2, default=str)
        file_path.write_text(content)
        logger.info(f"Execution logs saved: {file_path}")
        return file_path

    def load_prompt(self) -> Optional[str]:
        """Load execution prompt."""
        file_path = self.session_dir / "prompt.txt"
        if not file_path.exists():
            logger.warning("No prompt.txt found")
            return None
        return file_path.read_text()

    def load_task_breakdown(self) -> Optional[Dict]:
        """Load task breakdown."""
        file_path = self.session_dir / "tasks.json"
        if not file_path.exists():
            logger.warning("No tasks.json found")
            return None
        return json.loads(file_path.read_text())

    def load_github_details(self) -> Optional[Dict]:
        """Load GitHub details."""
        file_path = self.session_dir / "github.json"
        if not file_path.exists():
            logger.warning("No github.json found")
            return None
        return json.loads(file_path.read_text())

    def add_execution_log(self, log: Dict[str, Any]) -> None:
        """Add execution log entry (plain dict, no Pydantic dependency)."""
        logs_file = self.session_dir / "logs.json"

        logs = []
        if logs_file.exists():
            logs = json.loads(logs_file.read_text())

        logs.append(log)
        self.save_execution_logs(logs)

    def get_session_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            "session_id": self.session_id,
            "session_dir": str(self.session_dir),
            "created_at": self.session_dir.stat().st_ctime,
            "files": [f.name for f in self.session_dir.glob("*")],
            "has_prompt": (self.session_dir / "prompt.txt").exists(),
            "has_tasks": (self.session_dir / "tasks.json").exists(),
            "has_github": (self.session_dir / "github.json").exists(),
        }
