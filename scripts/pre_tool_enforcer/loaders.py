# pre_tool_enforcer/loaders.py
# Shared data-loading helpers used by multiple policy modules.
# Windows-safe: ASCII only, no Unicode characters.

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution for ide_paths / project_session
# ---------------------------------------------------------------------------
try:
    from ide_paths import CURRENT_SESSION_FILE, FLAG_DIR
except ImportError:
    FLAG_DIR = Path.home() / ".claude"
    try:
        _pe_dir = os.path.dirname(os.path.abspath(__file__))
        _scripts_dir = os.path.dirname(_pe_dir)
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        from project_session import get_project_session_file

        CURRENT_SESSION_FILE = get_project_session_file()
    except ImportError:
        CURRENT_SESSION_FILE = Path.home() / ".claude" / "memory" / ".current-session.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Max age for enforcement flags - auto-expire after 60 minutes (stale flag safety)
CHECKPOINT_MAX_AGE_MINUTES = 60

# ---------------------------------------------------------------------------
# Module-level caches (populated once per hook invocation)
# ---------------------------------------------------------------------------
_flow_trace_cache = None
_failure_kb_cache = None


def get_current_session_id():
    """Read the active session ID from .current-session.json or session-progress.json.

    Falls back to session-progress.json if .current-session.json is missing
    (which happens after /clear or fresh sessions).
    Returns empty string if not available (fail open - don't block on missing data).
    """
    try:
        if CURRENT_SESSION_FILE.exists():
            with open(CURRENT_SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            sid = data.get("current_session_id", "")
            if sid:
                return sid
    except Exception:
        pass
    # Fallback: read from session-progress.json (written by 3-level-flow.py)
    try:
        progress_file = Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"
        if progress_file.exists():
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            sid = data.get("session_id", "")
            if sid and sid.startswith("SESSION-"):
                return sid
    except Exception:
        pass
    return ""


def _load_flow_trace_context():
    """Load flow-trace.json from the current session to chain context from 3-level-flow.

    Returns dict with task_type, complexity, model, skill, plan_mode, user_input,
    tech_stack, and supplementary_skills.
    Cached per invocation (module-level).
    """
    global _flow_trace_cache
    if _flow_trace_cache is not None:
        return _flow_trace_cache

    _flow_trace_cache = {}
    try:
        session_id = get_current_session_id()
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
                "plan_mode": final_decision.get("plan_mode", False),
                "user_input": data.get("user_input", {}).get("prompt", "")[:200],
                "tech_stack": final_decision.get("tech_stack", []),
                "supplementary_skills": final_decision.get("supplementary_skills", []),
            }
    except Exception:
        pass
    return _flow_trace_cache


def _load_raw_flow_trace():
    """Load the LATEST flow-trace entry from flow-trace.json for the current session.

    Returns the parsed dict, or None if unavailable.
    Handles both array format (v4.4.0+) and legacy single-dict format.
    Used by Level 1/2 completion checks which need the pipeline array,
    not just the final_decision summary extracted by _load_flow_trace_context().
    """
    try:
        session_id = get_current_session_id()
        if not session_id:
            return None
        memory_base = Path.home() / ".claude" / "memory"
        trace_file = memory_base / "logs" / "sessions" / session_id / "flow-trace.json"
        if not trace_file.exists():
            return None
        with open(trace_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # v4.4.0+: array of traces - return the latest one
        if isinstance(data, list) and data:
            return data[-1]
        # Legacy: single dict
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def _load_failure_kb():
    """Load failure-kb.json from architecture/03-execution-system/failure-prevention/.

    Returns dict keyed by tool name, each containing a list of known failure patterns.
    Cached per invocation (module-level).
    """
    global _failure_kb_cache
    if _failure_kb_cache is not None:
        return _failure_kb_cache

    _failure_kb_cache = {}
    try:
        # __file__ is scripts/pre_tool_enforcer/loaders.py
        # go up one level to scripts/
        script_dir = Path(__file__).parent.parent
        kb_path = script_dir / "architecture" / "03-execution-system" / "failure-prevention" / "failure-kb.json"
        if kb_path.exists():
            with open(kb_path, "r", encoding="utf-8") as f:
                _failure_kb_cache = json.load(f)
    except Exception:
        pass
    return _failure_kb_cache


def find_session_flag(pattern_prefix, current_session_id):
    """Find session-specific flag file matching the current session ID.

    Returns (flag_path, flag_data) or (None, None) if not found.
    Auto-cleans stale flags (>60 min).

    v4.4.0: Flags now live inside the session folder:
      ~/.claude/memory/logs/sessions/{SESSION_ID}/flags/{name}.json
    Also checks legacy ~/.claude/ location for backward compat.

    Args:
        pattern_prefix (str): Flag name prefix (e.g. '.task-breakdown-pending').
        current_session_id (str): Active session ID string.

    Returns:
        (flag_path, flag_data) or (None, None) if not found/expired.
    """
    # v4.4.0: Check session folder first (new location)
    flag_name = pattern_prefix.lstrip(".") + ".json"
    memory_base = Path.home() / ".claude" / "memory"
    session_flag_path = memory_base / "logs" / "sessions" / current_session_id / "flags" / flag_name

    if session_flag_path.exists():
        try:
            with open(session_flag_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            created_at_str = data.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age = datetime.now() - created_at
                    if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                        session_flag_path.unlink(missing_ok=True)
                        return (None, None)
                except Exception:
                    pass

            return (session_flag_path, data)
        except Exception:
            pass

    # Legacy fallback: check ~/.claude/ for old-format flags
    legacy_path = FLAG_DIR / "{}-{}.json".format(pattern_prefix, current_session_id)
    if legacy_path.exists():
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            created_at_str = data.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age = datetime.now() - created_at
                    if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                        legacy_path.unlink(missing_ok=True)
                        return (None, None)
                except Exception:
                    pass

            return (legacy_path, data)
        except Exception:
            pass

    # Legacy fallback: PID-based flags
    import glob as _flag_glob

    legacy_pattern = str(FLAG_DIR / "{}-{}-*.json".format(pattern_prefix, current_session_id))
    legacy_files = _flag_glob.glob(legacy_pattern)
    if legacy_files:
        legacy_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        for lf in legacy_files:
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return (Path(lf), data)
            except Exception:
                pass

    return (None, None)


def _pipeline_step_present(raw_trace, step_name):
    """Return True if the named pipeline step exists in flow-trace pipeline array."""
    if not raw_trace:
        return False
    for entry in raw_trace.get("pipeline", []):
        if entry.get("step") == step_name:
            return True
    return False
