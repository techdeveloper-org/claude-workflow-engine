"""
post_tool_tracker/progress_tracker.py - Progress delta dict, session file I/O,
file-locking, and session flag management.

Handles:
- PROGRESS_DELTA constant
- load_session_progress() / save_session_progress()
- log_tool_entry()
- _lock_file() / _unlock_file()
- _clear_session_flags()
- estimate_context_pct() / get_response_content_length()
- is_error_response()
"""

import json
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Progress delta per tool call (approximate % contribution)
# ---------------------------------------------------------------------------

PROGRESS_DELTA = {
    "Read": 10,
    "Write": 40,
    "Edit": 30,
    "NotebookEdit": 25,
    "Bash": 15,
    "Task": 20,
    "Grep": 5,
    "Glob": 5,
    "WebFetch": 8,
    "WebSearch": 8,
}


# ---------------------------------------------------------------------------
# Windows file locking
# ---------------------------------------------------------------------------

try:
    import msvcrt as _msvcrt

    HAS_MSVCRT = True
except ImportError:
    _msvcrt = None
    HAS_MSVCRT = False


def _lock_file(f):
    """Lock file for exclusive access (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT and _msvcrt is not None:
        try:
            _msvcrt.locking(f.fileno(), _msvcrt.LK_NBLCK, 1)
        except (IOError, OSError):
            pass  # lock failed - proceed without lock (better than crash)


def _unlock_file(f):
    """Unlock file (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT and _msvcrt is not None:
        try:
            f.seek(0)
            _msvcrt.locking(f.fileno(), _msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass


# ---------------------------------------------------------------------------
# Session progress persistence
# ---------------------------------------------------------------------------


def load_session_progress(session_state_file):
    """Load the current session progress dict from SESSION_STATE_FILE.

    Uses _lock_file/_unlock_file so parallel PostToolUse hook invocations do
    not observe a partially written state file.  Returns a fresh default
    progress structure when the file is missing, unreadable, or has an
    incompatible schema.

    Args:
        session_state_file: Path-like pointing to session-progress.json.

    Returns:
        dict: Progress state containing at minimum 'total_progress',
              'tool_counts', 'started_at', 'tasks_completed', and
              'errors_seen'.
    """
    REQUIRED_KEYS = {"total_progress", "tool_counts", "started_at", "tasks_completed", "errors_seen"}
    sf = Path(session_state_file)
    try:
        if sf.exists():
            with open(sf, "r", encoding="utf-8") as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
            if isinstance(data, dict) and REQUIRED_KEYS.issubset(data.keys()):
                return data
    except Exception:
        pass
    return {
        "total_progress": 0,
        "tool_counts": {},
        "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tasks_completed": 0,
        "errors_seen": 0,
    }


def save_session_progress(state, session_state_file):
    """Persist the session progress dict to SESSION_STATE_FILE with file locking.

    Creates parent directories if they do not exist.  Uses _lock_file/_unlock_file
    to prevent data corruption from concurrent PostToolUse hook invocations.
    Errors are silently swallowed so this function never disrupts the hook flow.

    Args:
        state (dict): Progress state to persist (must be JSON-serialisable).
        session_state_file: Path-like pointing to session-progress.json.
    """
    try:
        sf = Path(session_state_file)
        sf.parent.mkdir(parents=True, exist_ok=True)
        with open(sf, "w", encoding="utf-8") as f:
            _lock_file(f)
            json.dump(state, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass


def log_tool_entry(entry, tracker_log):
    """Append a tool usage entry as a JSONL line to TRACKER_LOG.

    Creates parent directories automatically.  Errors are silently swallowed.

    Args:
        entry (dict): Tool tracking record to serialise and append.
        tracker_log: Path-like pointing to tool-tracker.jsonl.
    """
    try:
        tl = Path(tracker_log)
        tl.parent.mkdir(parents=True, exist_ok=True)
        with open(tl, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session flag management
# ---------------------------------------------------------------------------


def _clear_session_flags(pattern_prefix, session_id, flag_dir):
    """
    Clear session-specific flag file(s) for the given session.

    v4.4.0: Flags now live in session folder. Also cleans legacy locations.

    Args:
        pattern_prefix (str): Flag type prefix (e.g., '.task-breakdown-pending').
        session_id (str): Session ID.
        flag_dir: Path-like pointing to the legacy FLAG_DIR (~/.claude).
    """
    if not session_id:
        return
    # v4.4.0: Clear from session folder (new location)
    flag_name = pattern_prefix.lstrip(".") + ".json"
    memory_base = Path.home() / ".claude" / "memory"
    session_flag = memory_base / "logs" / "sessions" / session_id / "flags" / flag_name
    if session_flag.exists():
        try:
            session_flag.unlink()
        except Exception:
            pass

    # Legacy cleanup: old-style flags in ~/.claude/
    fd = Path(flag_dir)
    legacy_path = fd / (pattern_prefix + "-" + session_id + ".json")
    if legacy_path.exists():
        try:
            legacy_path.unlink()
        except Exception:
            pass
    import glob as _flag_glob

    for old_flag in _flag_glob.glob(str(fd / (pattern_prefix + "-" + session_id + "-*.json"))):
        try:
            Path(old_flag).unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Context estimation helpers
# ---------------------------------------------------------------------------


def get_response_content_length(tool_response):
    """Extract the approximate character count from a tool response payload.

    Measures actual content size so context-usage estimates are based on real
    data rather than flat per-tool heuristics.  Handles three payload shapes:
      - dict with 'content' string
      - dict with 'content' as a list of text items
      - bare string

    Args:
        tool_response: Raw tool response from Claude Code hook stdin.  May be
                       a dict, a list, or a plain string.

    Returns:
        int: Total character count of the textual content, or 0 if the
             response is empty or has an unrecognised structure.
    """
    if not tool_response:
        return 0
    if isinstance(tool_response, dict):
        content = tool_response.get("content", "")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    total += len(str(item.get("text", "")))
                elif isinstance(item, str):
                    total += len(item)
            return total
    if isinstance(tool_response, str):
        return len(tool_response)
    return 0


def estimate_context_pct(tool_counts, content_chars=0):
    """Estimate context-window usage as a percentage of the 200k-token limit.

    v2.0.0 accuracy model (from /context analysis):
      Fixed overhead (system prompt + tools + agents + memory + autocompact):
        ~44.5% of the context window is always consumed.
      Dynamic content (messages + tool responses) is estimated from
        tracked content_chars using a 3.5x multiplier, because hooks only
        see ~28% of all conversation content (tool responses only).

    Args:
        tool_counts (dict): Per-tool call counts from session-progress.json,
                            used as a fallback when content_chars is 0.
        content_chars (int): Total character count of all tracked tool
                             responses accumulated this session.

    Returns:
        int: Estimated context usage percentage capped at 95 (never 100).
    """
    CONTEXT_WINDOW = 200000
    FIXED_OVERHEAD_PCT = 44.5

    message_pct = 0.0
    if content_chars > 0:
        content_tokens = content_chars / 4.0
        message_pct = (content_tokens / CONTEXT_WINDOW) * 100.0 * 3.5
    else:
        message_pct = (
            tool_counts.get("Read", 0) * 5
            + tool_counts.get("Write", 0) * 3
            + tool_counts.get("Edit", 0) * 3
            + tool_counts.get("Bash", 0) * 3
            + tool_counts.get("Grep", 0) * 2
            + tool_counts.get("Glob", 0) * 1
            + tool_counts.get("Task", 0) * 6
            + tool_counts.get("WebFetch", 0) * 5
            + tool_counts.get("WebSearch", 0) * 4
        )

    return min(95, int(FIXED_OVERHEAD_PCT + message_pct))


# ---------------------------------------------------------------------------
# Error response detection
# ---------------------------------------------------------------------------


def is_error_response(tool_response):
    """Determine whether a tool call returned an error response.

    Checks the 'is_error' flag in the response dict and, as a fallback,
    inspects whether the content string starts with 'error:' or 'failed:'.

    Args:
        tool_response: Raw tool response from Claude Code hook stdin.

    Returns:
        bool: True if the response signals an error, False otherwise.
    """
    if isinstance(tool_response, dict):
        if tool_response.get("is_error", False):
            return True
        content = tool_response.get("content", "")
        if isinstance(content, str):
            lower = content.lower()
            if lower.startswith("error:") or lower.startswith("failed:"):
                return True
    return False
