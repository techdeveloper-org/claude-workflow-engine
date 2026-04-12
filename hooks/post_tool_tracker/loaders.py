"""
post_tool_tracker/loaders.py - Shared data loading helpers.

Provides cached flow-trace context loading and raw flow-trace loading
so all modules read from the same source without re-parsing files.
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Session ID helper (shared dependency - defined here, imported by other mods)
# ---------------------------------------------------------------------------


def _get_session_id_from_progress(session_state_file=None, flag_dir=None):
    """Get the current session ID with multiple fallback sources.

    Checks in order:
    1. Per-project session file (multi-window isolation)
    2. Legacy global .current-session.json (backward compat)
    3. session-progress.json (may be stale or have session_broken=true)

    Args:
        session_state_file: Path to SESSION_STATE_FILE (injected to avoid circular import).
        flag_dir: Path to FLAG_DIR (not used directly here, kept for signature compat).

    Returns:
        str: Active session ID (e.g. "SESSION-20260307-115241-GQQQ"), or
             empty string when no valid session ID can be found.
    """
    # Primary: use project_session helper (per-project + legacy fallback)
    try:
        _pt_dir = os.path.dirname(os.path.abspath(__file__))
        hooks_dir = str(Path(_pt_dir).parent)
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        from project_session import read_session_id

        sid = read_session_id()
        if sid:
            return sid
    except ImportError:
        # Fallback if project_session not available: read legacy global file
        try:
            legacy = Path.home() / ".claude" / "memory" / ".current-session.json"
            if legacy.exists():
                with open(legacy, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("current_session_id", "")
                if sid and sid.startswith("SESSION-"):
                    return sid
        except Exception:
            pass
    except Exception:
        pass
    # Final fallback: session-progress.json
    if session_state_file is not None:
        try:
            sf = Path(session_state_file)
            if sf.exists():
                with open(sf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("session_id", "")
                if sid and sid.startswith("SESSION-"):
                    return sid
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
# Flow-trace loader (module-level cache, reset per process invocation)
# ---------------------------------------------------------------------------

_flow_trace_cache = None


def _load_flow_trace_context(session_state_file=None):
    """
    Load flow-trace.json from the current session to chain context from 3-level-flow.
    Returns dict with task_type, complexity, model, skill.
    Cached per invocation (module-level).

    Context chain: 3-level-flow.py -> flow-trace.json -> post-tool-tracker
    This enables:
    - Enriching tool-tracker.jsonl entries with task context
    - Better progress estimation weighted by complexity
    - Task-aware git commit messages

    Args:
        session_state_file: Path to SESSION_STATE_FILE for session ID lookup.

    Returns:
        dict: Keys task_type, complexity, model, skill.  Empty dict on failure.
    """
    global _flow_trace_cache
    if _flow_trace_cache is not None:
        return _flow_trace_cache

    _flow_trace_cache = {}
    try:
        session_id = _get_session_id_from_progress(session_state_file)
        if not session_id:
            return _flow_trace_cache

        memory_base = Path.home() / ".claude" / "memory"
        trace_file = memory_base / "logs" / "sessions" / session_id / "flow-trace.json"
        if trace_file.exists():
            with open(trace_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # v4.4.0+: array of traces - use latest entry
            if isinstance(raw, list) and raw:
                data = raw[-1]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
            final_decision = data.get("final_decision", {})
            _flow_trace_cache = {
                "task_type": final_decision.get("task_type", ""),
                "complexity": final_decision.get("complexity", 0),
                "model": final_decision.get("model_selected", ""),
                "skill": final_decision.get("skill_or_agent", ""),
            }
    except Exception:
        pass
    return _flow_trace_cache


def _load_raw_flow_trace(session_state_file=None):
    """
    Load and return the raw flow-trace.json dict for the current session.

    Returns the latest entry if the file contains a list, or the dict
    directly.  Returns an empty dict on any failure.

    Args:
        session_state_file: Path to SESSION_STATE_FILE for session ID lookup.

    Returns:
        dict: Raw flow-trace data or empty dict.
    """
    try:
        session_id = _get_session_id_from_progress(session_state_file)
        if not session_id:
            return {}
        memory_base = Path.home() / ".claude" / "memory"
        trace_file = memory_base / "logs" / "sessions" / session_id / "flow-trace.json"
        if not trace_file.exists():
            return {}
        with open(trace_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list) and raw:
            return raw[-1]
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}
