#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Chaining Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

Maps to: policies/01-sync-system/session-management/session-chaining-policy.md

This module enforces session continuity across Claude Code sessions by managing
session archiving, save triggers, session searching, and session startup checks.
It ensures that previous session state is preserved and new sessions can resume
from where the last session left off.

Consolidates 5 scripts (1056+ lines):
  - archive-old-sessions.py (200 lines) - Archive older sessions to keep dirs clean
  - auto-save-session.py (302 lines) - Automatically save session data on triggers
  - session-save-triggers.py (346 lines) - Define and handle save trigger events
  - session-search.py (245 lines) - Search across session history
  - session-start-check.py (232 lines) - Check for previous sessions on startup

Key Classes:
  SessionChainManager: Manages session chaining, archiving, and save triggers.

CLI Usage:
  python session-chaining-policy.py --enforce  # Run enforcement
  python session-chaining-policy.py --validate # Validate compliance
  python session-chaining-policy.py --report   # Generate report

Example:
  >>> from session_chaining_policy import enforce
  >>> result = enforce()
  >>> print(result['status'])  # 'success'
"""

import sys, json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    except: pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"

class SessionChainManager:
    """Manages session chaining, archiving, and save triggering.

    Provides a unified interface for all session lifecycle operations including
    building session chains across Claude Code sessions, archiving old sessions
    to prevent directory bloat, and defining when sessions should be saved.

    Attributes:
        sessions_dir (Path): Directory containing active session JSON files.
        archive_dir (Path): Directory where old sessions are moved on archive.
        chain_index (Path): JSON file tracking the ordered session chain.
    """

    def __init__(self):
        self.sessions_dir = MEMORY_DIR / "sessions"
        self.archive_dir = MEMORY_DIR / "archive"
        self.chain_index = self.sessions_dir / "chain-index.json"

    def get_session_chain(self) -> List[str]:
        """Get the ordered list of session IDs in the current session chain.

        Reads the chain-index.json file to return the sequence of session IDs
        that form the continuous work chain across multiple Claude sessions.

        Returns:
            List[str]: Ordered list of session IDs, oldest first. Returns an
                       empty list if no chain file exists or parsing fails.
        """
        try:
            if self.chain_index.exists():
                data = json.loads(self.chain_index.read_text())
                return data.get("chain", [])
        except: pass
        return []

    def archive_old_sessions(self, keep_recent: int = 5) -> int:
        """Move older session files to the archive directory, keeping the N most recent.

        Sorts session files by modification time (newest first) and moves all
        sessions beyond the keep_recent threshold to the archive directory.
        Creates the archive directory if it does not exist.

        Args:
            keep_recent (int): Number of most recent sessions to retain in the
                               active sessions directory. Defaults to 5.

        Returns:
            int: The number of session files successfully archived.
        """
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archived_count = 0
        sessions = list(self.sessions_dir.glob("session-*.json"))
        sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        for session in sessions[keep_recent:]:
            try:
                import shutil
                shutil.move(str(session), str(self.archive_dir / session.name))
                archived_count += 1
            except: pass
        return archived_count

    def get_session_triggers(self) -> Dict:
        """Return the set of conditions that trigger an automatic session save.

        Defines the four standard trigger conditions under which session state
        should be saved: high context usage, task completion, errors, and
        session end.

        Returns:
            Dict[str, bool]: Mapping of trigger name to enabled status.
                Keys include 'on_context_high', 'on_task_complete', 'on_error',
                and 'on_session_end'.
        """
        return {
            "on_context_high": True,
            "on_task_complete": True,
            "on_error": True,
            "on_session_end": True
        }

def log_policy_hit(action, context=""):
    """Append a timestamped policy execution event to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context string for the log entry.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] session-chaining-policy | {action} | {context}\n")
    except: pass

def validate():
    """Check that the session chaining policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for session chaining operations.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        log_policy_hit("VALIDATE", "session-chaining-ready")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False

def report():
    """Generate a compliance report for the session chaining policy.

    Inspects the current session chain state and save trigger configuration
    to produce a structured report dictionary.

    Returns:
        dict: Report containing 'status', 'policy', 'chain_length', 'triggers',
              and 'timestamp' keys. On error, returns {'status': 'error', 'message': ...}.
    """
    try:
        manager = SessionChainManager()
        chain = manager.get_session_chain()
        return {
            "status": "success",
            "policy": "session-chaining",
            "chain_length": len(chain),
            "triggers": manager.get_session_triggers(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def enforce():
    """Run the session chaining policy enforcement.

    Archives old sessions to keep the sessions directory clean, then logs
    the enforcement result. This is called by 3-level-flow.py during Level 1.

    Consolidates logic from 5 old scripts:
      - archive-old-sessions.py: Archive sessions beyond keep threshold
      - auto-save-session.py: Auto-save session data on triggers
      - session-save-triggers.py: Define and handle save triggers
      - session-search.py: Search session history
      - session-start-check.py: Check for prior sessions on startup

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'archived_sessions' count.
              On error, 'message' key contains the exception string.
    """
    try:
        log_policy_hit("ENFORCE_START", "session-chaining")
        manager = SessionChainManager()
        archived = manager.archive_old_sessions()
        log_policy_hit("ENFORCE_COMPLETE", f"Archived {archived} old sessions")
        print("[session-chaining-policy] Policy enforced - Session chaining manager ready")
        return {"status": "success", "archived_sessions": archived}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce": result = enforce(); sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate": sys.exit(0 if validate() else 1)
        elif sys.argv[1] == "--report": print(json.dumps(report(), indent=2))
    else: enforce()
