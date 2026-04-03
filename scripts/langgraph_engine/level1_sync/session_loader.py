"""Level 1 Sync - Session Loader node.

Canonical location: langgraph_engine/level1_sync/session_loader.py
Windows-safe: ASCII only, no Unicode characters.
"""

import json
import sys
from pathlib import Path

try:
    from ..flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

from .helpers import (
    _LEVEL1_SESSION_LOGS_DIR,
    _LEVEL1_TELEMETRY_DIR,
    _load_architecture_script,
    _time_mod,
    datetime,
    write_level_log,
)


def node_session_loader(state):
    """Create and load session in ~/.claude/logs/sessions/{session_id}/.

    This MUST run first - creates the session container for this execution.
    """
    import uuid

    _step_start = _time_mod.time()
    try:
        # Debug: Check project_root before doing anything (ASCII-safe for Windows cp1252 terminals)
        _root_repr = str(state.get("project_root", "MISSING")).encode("ascii", errors="replace").decode("ascii")
        print("[LEVEL 1 SESSION_LOADER] state['project_root'] at entry: '{}'".format(_root_repr), file=sys.stderr)

        # Generate unique session ID
        session_id = "session-{}-{}".format(datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])

        # Create session folder: ~/.claude/logs/sessions/{session_id}/
        session_path = _LEVEL1_SESSION_LOGS_DIR / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        # user_message: try state first, then env var fallback (set by run_langgraph_engine)
        import os

        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

        session_meta = {
            "metadata": {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
            },
            "user_message": user_msg,
        }

        meta_file = session_path / "session.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2)

        # Set env var so Level 3 infra can find session_id
        os.environ["CURRENT_SESSION_ID"] = session_id

        result = {
            "session_id": session_id,
            "session_path": str(session_path),
            "session_loaded": True,
        }

        # ---- Best-effort: session chaining (link to previous session) ----
        try:
            prev_session_id = os.environ.get("PREVIOUS_SESSION_ID", "")
            if prev_session_id and prev_session_id != session_id:
                try:
                    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src" / "mcp"))
                    from session_hooks import link_sessions, tag_session  # noqa: F811

                    link_sessions(session_id, prev_session_id)
                    result["session_parent_id"] = prev_session_id
                except Exception:
                    pass  # Fail-open: chaining is best-effort

            # Auto-tag from user_message keywords
            _auto_tags = []
            _msg_lower = user_msg.lower() if user_msg else ""
            _tag_keywords = {
                "bugfix": ["bug", "fix", "error", "crash", "broken"],
                "feature": ["feature", "add", "new", "implement", "create"],
                "refactor": ["refactor", "clean", "reorganize", "restructure"],
                "docs": ["doc", "readme", "documentation", "comment"],
                "test": ["test", "spec", "coverage", "assert"],
                "config": ["config", "setup", "install", "deploy"],
            }
            for tag, keywords in _tag_keywords.items():
                if any(kw in _msg_lower for kw in keywords):
                    _auto_tags.append(tag)
            if _auto_tags:
                result["session_tags"] = _auto_tags
                try:
                    from session_hooks import tag_session

                    tag_session(session_id, ",".join(_auto_tags))
                except Exception:
                    pass  # Best-effort tagging

            # Set PREVIOUS_SESSION_ID for next session
            os.environ["PREVIOUS_SESSION_ID"] = session_id
        except Exception as _chain_exc:
            result["session_chaining_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Session chaining skipped: {}".format(_chain_exc),
                file=sys.stderr,
            )

        # ---- Best-effort: prune old sessions (optional enhancement) ----
        try:
            _pruner = _load_architecture_script("session-pruner.py")
            if _pruner is not None and hasattr(_pruner, "prune_sessions"):
                _sessions_dir = _LEVEL1_SESSION_LOGS_DIR
                _prune_result = _pruner.prune_sessions(_sessions_dir)
                result["session_pruning_done"] = True
                result["session_pruning_archived"] = _prune_result.get("archived", 0)
                # Capture pruning errors
                _prune_errors = _prune_result.get("errors", [])
                if _prune_errors:
                    result["session_pruning_errors"] = _prune_errors
                    print(
                        "[LEVEL 1 SESSION_LOADER] Session pruning had {} errors".format(len(_prune_errors)),
                        file=sys.stderr,
                    )
        except Exception as _prune_exc:
            result["session_pruning_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Session pruning skipped: {}".format(_prune_exc),
                file=sys.stderr,
            )

        # ---- Best-effort: track user preferences from session history ----
        try:
            _pref_tracker = _load_architecture_script("preference-tracker.py")
            if _pref_tracker is not None and hasattr(_pref_tracker, "track_preferences"):
                _sessions_dir = _LEVEL1_SESSION_LOGS_DIR
                if not state.get("preferences_data"):
                    _prefs = _pref_tracker.track_preferences(_sessions_dir)
                    result["preferences_data"] = _prefs
        except Exception as _pref_exc:
            result["preference_tracking_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Preference tracking skipped: {}".format(_pref_exc),
                file=sys.stderr,
            )

        write_level_log(result, "level1", "session-loader", "OK", _time_mod.time() - _step_start, result)
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_session_loader",
                    "status": "OK" if not result.get("error") else "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result
    except Exception as e:
        result = {
            "session_loaded": False,
            "session_error": str(e),
        }
        write_level_log(state, "level1", "session-loader", "FAILED", _time_mod.time() - _step_start, None, str(e))
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_session_loader",
                    "status": "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result
