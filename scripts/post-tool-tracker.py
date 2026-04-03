#!/usr/bin/env python
"""
BACKWARD-COMPAT SHIM for post-tool-tracker.py

Post-tool tracking logic has been refactored into scripts/post_tool_tracker/
package. This file delegates to that package while preserving the original
script invocation contract (Claude Code hooks call this file directly).

All public symbols are re-exported so that tests and other consumers that
load this file via importlib continue to find every attribute they expect.
"""
import importlib.util as _ilu
import os
import sys
from pathlib import Path as _Path

# Guard: skip entirely when running inside the pipeline itself
if os.environ.get("CLAUDE_WORKFLOW_RUNNING") == "1":

    def main():
        """No-op main when running inside the workflow pipeline."""
        sys.exit(0)

else:
    # ------------------------------------------------------------------
    # Load core.py by file path to avoid sys.modules["post_tool_tracker"]
    # collision when tests register this shim under that name.
    # ------------------------------------------------------------------
    _PACKAGE_DIR = _Path(__file__).resolve().parent / "post_tool_tracker"
    _CORE_PATH = _PACKAGE_DIR / "core.py"

    _core_spec = _ilu.spec_from_file_location(
        "_post_tool_tracker_core",
        str(_CORE_PATH),
        submodule_search_locations=[str(_PACKAGE_DIR)],
    )
    _core_mod = _ilu.module_from_spec(_core_spec)
    _core_spec.loader.exec_module(_core_mod)

    # Re-export main and every public/private name from core
    main = _core_mod.main

    for _name in dir(_core_mod):
        if _name.startswith("__") and _name.endswith("__"):
            continue
        globals()[_name] = getattr(_core_mod, _name)

    # ------------------------------------------------------------------
    # BACKWARD-COMPAT WRAPPERS
    # Original functions used module-level SESSION_STATE_FILE, TRACKER_LOG,
    # FLAG_DIR globals. New functions take these as explicit parameters.
    # Tests patch these globals on pte, so wrappers must be defined HERE.
    # ------------------------------------------------------------------

    # Path constants (tests mock ide_paths before import)
    try:
        from ide_paths import FLAG_DIR, SESSION_STATE_FILE, TRACKER_LOG
    except ImportError:
        SESSION_STATE_FILE = _Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"
        TRACKER_LOG = _Path.home() / ".claude" / "memory" / "logs" / "tool-tracker.jsonl"
        FLAG_DIR = _Path.home() / ".claude"

    # Get the parameterized functions from core
    _param_load_session = _core_mod.load_session_progress
    _param_save_session = _core_mod.save_session_progress
    _param_log_tool = _core_mod.log_tool_entry
    _param_clear_flags = _core_mod._clear_session_flags

    def load_session_progress():
        """Backward-compat: no-arg wrapper using module-level SESSION_STATE_FILE."""
        return _param_load_session(SESSION_STATE_FILE)

    def save_session_progress(state):
        """Backward-compat: single-arg wrapper using module-level SESSION_STATE_FILE."""
        return _param_save_session(state, SESSION_STATE_FILE)

    def log_tool_entry(entry):
        """Backward-compat: single-arg wrapper using module-level TRACKER_LOG."""
        return _param_log_tool(entry, TRACKER_LOG)

    def _clear_session_flags(pattern_prefix, session_id):
        """Backward-compat: 2-arg wrapper using module-level FLAG_DIR."""
        return _param_clear_flags(pattern_prefix, session_id, FLAG_DIR)

    # _failure_detector: tests patch this directly on the shim module
    _failure_detector = getattr(_core_mod, "_failure_detector", None)

    def _detect_result_failure(tool_response):
        """Backward-compat: defined here so tests can patch _failure_detector on this module."""
        if not _failure_detector or not tool_response:
            return None
        try:
            result_str = str(tool_response)[:2000]
            return _failure_detector.detect_failure_in_message(result_str)
        except Exception:
            return None


if __name__ == "__main__":
    main()
