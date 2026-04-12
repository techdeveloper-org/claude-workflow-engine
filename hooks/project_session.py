"""Session file resolution for per-window session isolation.

Each Claude Code window generates its own unique session ID at startup.
Session data is stored in a single shared pointer file since only one
window is active at a time. Each session's data goes to its own folder
under ~/.claude/memory/logs/sessions/{SESSION_ID}/ -- no overrides.

Usage:
    from project_session import get_project_session_file
    session_file = get_project_session_file()
"""

from pathlib import Path

MEMORY_BASE = Path.home() / ".claude" / "memory"


def get_project_session_file():
    """Return the session pointer file path.

    Returns:
        Path: ~/.claude/memory/.current-session.json
    """
    return MEMORY_BASE / ".current-session.json"


def get_legacy_session_file():
    """Return the legacy global session file path (backward compat).

    Returns:
        Path: ~/.claude/memory/.current-session.json
    """
    return MEMORY_BASE / ".current-session.json"


def read_session_id():
    """Read session ID from the current session pointer file.

    Returns:
        str: Session ID or empty string if not found.
    """
    session_file = get_project_session_file()
    try:
        if session_file.exists():
            import json

            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            sid = data.get("current_session_id", "")
            if sid and sid.startswith("SESSION-"):
                return sid
    except Exception:
        pass
    return ""
