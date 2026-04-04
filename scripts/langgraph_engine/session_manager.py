"""
Session Manager - File-based persistence for Level 3 execution.

Manages session folders, TOON versioning, logs, and state.
Session structure: ~/.claude/logs/sessions/{session_id}/
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_session_logs_dir

    _SESSION_LOGS_DIR = get_session_logs_dir()
except ImportError:
    _SESSION_LOGS_DIR = Path.home() / ".claude" / "logs" / "sessions"

from .toon_models import ExecutionBlueprint, ExecutionLog, SessionMetadata, ToonAnalysis, ToonWithSkills, serialize_toon


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

    def save_session_metadata(self, metadata: SessionMetadata) -> Path:
        """Save session metadata."""
        file_path = self.session_dir / "session.json"
        content = json.dumps(json.loads(serialize_toon(metadata)), indent=2)
        file_path.write_text(content)
        logger.info(f"Session metadata saved: {file_path}")
        return file_path

    def save_toon_analysis(self, toon: ToonAnalysis) -> Path:
        """Save Level 1 analysis TOON."""
        timestamp = datetime.now().isoformat().replace(":", "-")
        file_path = self.session_dir / f"toon_v1_analysis_{timestamp}.json"
        content = json.dumps(json.loads(serialize_toon(toon)), indent=2)
        file_path.write_text(content)
        logger.info(f"TOON v1 (analysis) saved: {file_path}")
        return file_path

    def save_execution_blueprint(self, blueprint: ExecutionBlueprint) -> Path:
        """Save Level 3 execution blueprint (after planning)."""
        timestamp = datetime.now().isoformat().replace(":", "-")
        file_path = self.session_dir / f"toon_blueprint_{timestamp}.json"
        content = json.dumps(json.loads(serialize_toon(blueprint)), indent=2)
        file_path.write_text(content)
        logger.info(f"TOON blueprint saved: {file_path}")
        return file_path

    def save_toon_with_skills(self, toon: ToonWithSkills) -> Path:
        """Save TOON with skill mappings (after Step 5)."""
        timestamp = datetime.now().isoformat().replace(":", "-")
        file_path = self.session_dir / f"toon_v3_skills_{timestamp}.json"
        content = json.dumps(json.loads(serialize_toon(toon)), indent=2)
        file_path.write_text(content)
        logger.info(f"TOON v3 (skills) saved: {file_path}")
        return file_path

    def save_prompt(self, prompt_text: str) -> Path:
        """Save final execution prompt (Step 7)."""
        file_path = self.session_dir / "prompt.txt"
        file_path.write_text(prompt_text)
        logger.info(f"Execution prompt saved: {file_path}")
        return file_path

    def save_task_breakdown(self, tasks: Dict[str, Any]) -> Path:
        """Save task breakdown from Step 3."""
        file_path = self.session_dir / "tasks.json"
        content = json.dumps(tasks, indent=2)
        file_path.write_text(content)
        logger.info(f"Task breakdown saved: {file_path}")
        return file_path

    def save_github_details(self, details: Dict[str, Any]) -> Path:
        """Save GitHub issue/PR details (Step 8, 11)."""
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

    def load_latest_toon(self, version: int = 1) -> Optional[Dict]:
        """Load latest TOON of given version."""
        if version == 1:
            pattern = "toon_v1_analysis_*.json"
        elif version == 2:
            pattern = "toon_blueprint_*.json"
        elif version == 3:
            pattern = "toon_v3_skills_*.json"
        else:
            return None

        files = list(self.session_dir.glob(pattern))
        if not files:
            logger.warning(f"No TOON v{version} files found")
            return None

        latest = sorted(files)[-1]
        content = latest.read_text()
        logger.info(f"Loaded TOON v{version} from {latest}")
        return json.loads(content)

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

    def add_execution_log(self, log: ExecutionLog) -> None:
        """Add execution log entry."""
        logs_file = self.session_dir / "logs.json"

        logs = []
        if logs_file.exists():
            logs = json.loads(logs_file.read_text())

        logs.append(json.loads(serialize_toon(log)))
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

    def cleanup_old_toots(self, keep_latest: int = 2) -> None:
        """Keep only latest N TOON versions of each type."""
        for version in [1, 2, 3]:
            if version == 1:
                pattern = "toon_v1_analysis_*.json"
            elif version == 2:
                pattern = "toon_blueprint_*.json"
            else:
                pattern = "toon_v3_skills_*.json"

            files = sorted(self.session_dir.glob(pattern))
            if len(files) > keep_latest:
                for old_file in files[:-keep_latest]:
                    old_file.unlink()
                    logger.info(f"Deleted old TOON: {old_file.name}")
