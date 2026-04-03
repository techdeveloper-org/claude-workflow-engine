"""Session and issue-mapping persistence helpers.

Provides functions to read the current session ID, locate and
load/save the per-session github-issues.json mapping file, and
track per-session operations counts.
"""

import json
from pathlib import Path

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import SESSION_STATE_FILE
except ImportError:
    SESSION_STATE_FILE = Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"


def _get_session_id():
    """Read the current session ID from the session-progress.json state file.

    Returns:
        str: The session_id value from the file, or an empty string if the
            file does not exist, cannot be parsed, or lacks the key.
    """
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("session_id", "")
    except Exception:
        pass
    return ""


def _get_current_session_id():
    """Get the current session ID by finding the latest session folder.

    Returns:
        str: Session ID string like 'SESSION-20260308-234215-WLOD', or empty
            string if not found.
    """
    try:
        sessions_dir = Path.home() / ".claude" / "memory" / "logs" / "sessions"
        if not sessions_dir.exists():
            return ""

        # Get all session folders, find the most recent one (by modification time)
        session_folders = [f for f in sessions_dir.iterdir() if f.is_dir() and f.name.startswith("SESSION-")]
        if not session_folders:
            return ""

        # Sort by modification time, get the latest
        latest = max(session_folders, key=lambda f: f.stat().st_mtime)
        return latest.name
    except Exception:
        return ""


def _get_mapping_file():
    """Return the Path to the github-issues.json mapping file for the current session.

    If a session ID is available the file is placed under the per-session log
    directory; otherwise a shared fallback path is used.

    Returns:
        Path: Resolved path to the github-issues.json mapping file.
    """
    session_id = _get_session_id()
    if session_id:
        session_dir = Path.home() / ".claude" / "memory" / "logs" / "sessions" / session_id
        return session_dir / "github-issues.json"
    # Fallback: use a general mapping file
    return Path.home() / ".claude" / "memory" / "logs" / "github-issues.json"


def _load_issues_mapping():
    """Load the task-to-issue mapping dict from the session mapping file.

    Returns:
        dict: Parsed mapping with at minimum the keys ``task_to_issue`` (dict),
            ``ops_count`` (int), and ``session_id`` (str). Returns this default
            structure if the file is missing or unreadable.
    """
    mapping_file = _get_mapping_file()
    try:
        if mapping_file.exists():
            with open(mapping_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    # Initialize with per-session ops_count support (not global)
    return {
        "task_to_issue": {},
        "ops_count": 0,  # Keep for backwards compatibility (deprecated)
        "session_id": _get_session_id(),
        "session_ops_count": {},  # New: per-session ops tracking
    }


def _save_issues_mapping(mapping):
    """Write the task-to-issue mapping dict to the session mapping file.

    Creates parent directories as needed. Failures are silently ignored so
    that a write error never interrupts the main workflow.

    Args:
        mapping (dict): Mapping data to serialise and persist.
    """
    mapping_file = _get_mapping_file()
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def _get_ops_count():
    """Return the number of GitHub operations already performed in CURRENT SESSION.

    Tracks ops_count per-session (not global) so each session gets its own limit.

    Returns:
        int: Value of ops_count for current session, or 0 if not set.
    """
    try:
        current_session_id = _get_current_session_id()
        mapping = _load_issues_mapping()

        # Use per-session ops count (not global)
        session_ops = mapping.get("session_ops_count", {})
        return session_ops.get(current_session_id, 0)
    except Exception:
        return 0


def _increment_ops_count(mapping=None):
    """Increment the CURRENT SESSION's GitHub operations counter.

    Args:
        mapping (dict, optional): If provided, updates this mapping.
            If None, loads from file.

    Returns:
        dict: Updated mapping with incremented session ops_count (does NOT
            save to disk). Each session gets its own ops_count limit, so
            moving to a new session resets the counter.
    """
    try:
        current_session_id = _get_current_session_id()
        if mapping is None:
            mapping = _load_issues_mapping()

        # Initialize session_ops_count if missing
        if "session_ops_count" not in mapping:
            mapping["session_ops_count"] = {}

        # Increment current session's ops_count
        mapping["session_ops_count"][current_session_id] = mapping["session_ops_count"].get(current_session_id, 0) + 1

        return mapping  # Return updated mapping for caller to save
    except Exception:
        # If anything fails, return mapping unchanged (never block)
        return mapping if mapping else _load_issues_mapping()
