"""Level 1 Sync - Merge and routing nodes.

Canonical location: langgraph_engine/level1_sync/routing.py
Windows-safe: ASCII only, no Unicode characters.
"""

import os
import sys
from pathlib import Path

try:
    from ..flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

from .helpers import _LEVEL1_TELEMETRY_DIR, _load_architecture_script, _time_mod, write_level_log

# ============================================================================
# MERGE NODE - Final Level 1 output
# ============================================================================


def level1_merge_node(state):
    """Merge all Level 1 data and prepare for Level 2.

    OUTPUT: Only TOON object (contains session_id, complexity_score, files_loaded_count + context)
    CLEARED: All verbose variables from memory

    NOTE on level1_complete=True for PARTIAL status:
    Even when level1_status=="PARTIAL" (e.g. context failed to load but complexity
    succeeded), level1_complete is INTENTIONALLY set to True.  This ensures the
    pipeline does not deadlock at the Level 1 gate.  Downstream steps receive
    level1_status=="PARTIAL" so they can adapt accordingly.  Do NOT change
    level1_complete to False on PARTIAL -- that would halt the entire pipeline.
    """
    _step_start = _time_mod.time()
    # Determine Level 1 completion status based on both parallel branch results
    _complexity_ok = bool(state.get("complexity_calculated", False))
    _context_ok = bool(state.get("context_loaded", False))
    _level1_status = "OK" if (_complexity_ok and _context_ok) else "PARTIAL"

    # Gap1 fix: emit observable warning when PARTIAL so operators can detect degraded state
    if _level1_status == "PARTIAL":
        print(
            "[LEVEL 1 MERGE] PARTIAL: complexity_ok={} context_ok={}".format(_complexity_ok, _context_ok),
            file=sys.stderr,
        )

    # Build final Level 1 output
    updates = {
        "level1_complete": True,
        "level1_status": _level1_status,
        "level1_context_toon": state.get("toon_object", {}),  # TOON has everything inside
    }

    # Signal memory cleanup - these variables should be cleared from memory
    # (not from disk, just from RAM variables)
    cleanup_signals = {
        "clear_memory": [
            "context_data",  # Full context dict
            "srs",  # Raw SRS content
            "readme",  # Raw README content
            "claude_md",  # Raw CLAUDE.md content
            # Note: complexity_score is intentionally RETAINED in state for Level 3 access
            "files_loaded_count",  # Summarised in TOON
            "project_graph",  # Large graph object
            "architecture",  # Large architecture object
        ]
    }

    updates.update(cleanup_signals)

    write_level_log(
        state,
        "level1",
        "merge",
        "OK",
        _time_mod.time() - _step_start,
        {
            "level1_complete": True,
            "toon_present": bool(state.get("toon_object")),
            "context_percentage": state.get("context_percentage", 0),
        },
    )
    # Telemetry
    try:
        import json as _json_tel
        import time as _time_tel

        _sid_tel = state.get("session_id", updates.get("session_id", ""))
        if _sid_tel:
            _tdir_tel = _LEVEL1_TELEMETRY_DIR
            _tdir_tel.mkdir(parents=True, exist_ok=True)
            _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
            _entry_tel = {
                "level": 1,
                "node": "level1_merge_node",
                "status": "OK" if not updates.get("error") else "ERROR",
                "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
    except Exception:
        pass  # Non-blocking
    return updates


# ============================================================================
# HELPER: Actual memory cleanup function (called separately)
# ============================================================================


def cleanup_level1_memory(state):
    """Actually remove verbose variables from state.

    This is called AFTER level1_merge to free up RAM.

    VERIFICATION: Log memory usage before/after cleanup to confirm clearing.
    """

    # Collect size information before cleanup (for verification)
    cleanup_summary = {
        "fields_cleared": [
            "context_data",
            "srs",
            "readme",
            "claude_md",
            "project_graph",
            "architecture",
        ],
        "toon_preserved": True,  # Confirm TOON is NOT cleared
    }

    # Calculate approximate sizes for verification
    for field in cleanup_summary["fields_cleared"]:
        value = state.get(field)
        if value:
            if isinstance(value, dict):
                cleanup_summary["{}_size_bytes".format(field)] = len(str(value).encode("utf-8"))
            elif isinstance(value, (str, bytes)):
                cleanup_summary["{}_size_bytes".format(field)] = len(
                    str(value).encode("utf-8") if isinstance(value, str) else value
                )

    # Verify TOON object is in state and has required fields
    toon = state.get("level1_context_toon", {})
    if toon:
        cleanup_summary["toon_fields"] = list(toon.keys())
        cleanup_summary["toon_has_session_id"] = "session_id" in toon
        cleanup_summary["toon_has_complexity_score"] = "complexity_score" in toon
        cleanup_summary["toon_has_files_loaded_count"] = "files_loaded_count" in toon

    # Log cleanup status (ASCII-safe prints for Windows cp1252 terminals)
    if os.getenv("CLAUDE_DEBUG") == "1":
        print("\n[LEVEL 1 CLEANUP]", file=sys.stderr)
        print("  Clearing {} verbose fields...".format(len(cleanup_summary["fields_cleared"])), file=sys.stderr)
        for field in cleanup_summary["fields_cleared"]:
            if "{}_size_bytes".format(field) in cleanup_summary:
                size_kb = cleanup_summary["{}_size_bytes".format(field)] / 1024
                print("    {} {:.1f}KB freed".format(field, size_kb), file=sys.stderr)
        print("  TOON object preserved: {}".format(list(toon.keys())), file=sys.stderr)
        print("  Memory cleanup complete\n", file=sys.stderr)

    # ---- Best-effort: estimate context window usage after cleanup ----
    _context_monitor_result = {}
    try:
        _monitor_mod = _load_architecture_script("context-monitor.py")
        if _monitor_mod is not None and hasattr(_monitor_mod, "estimate_context_usage"):
            _session_path_val = state.get("session_path", "")
            _session_dir = Path(_session_path_val) if _session_path_val else None
            _usage = _monitor_mod.estimate_context_usage(_session_dir)
            _context_monitor_result = {
                "context_percentage": _usage.get("percentage", 0.0),
                "context_percentage_display": _usage.get("percentage_display", ""),
                "context_threshold_zone": _usage.get("threshold_zone", ""),
                "context_estimated_tokens": _usage.get("estimated_tokens", 0),
                "context_recommendation": _usage.get("recommendation", ""),
            }
    except Exception as _mon_exc:
        print(
            "[LEVEL 1 CLEANUP] Context monitor skipped: {}".format(_mon_exc),
            file=sys.stderr,
        )

    # Return cleanup updates
    # In Python, we just set these to None/empty
    # LangGraph will update the state
    cleanup = {
        "context_data": None,
        "srs": None,
        "readme": None,
        "claude_md": None,
        "project_graph": None,
        "architecture": None,
        # Store cleanup summary for logging
        "level1_cleanup_summary": cleanup_summary,
    }
    cleanup.update(_context_monitor_result)
    return cleanup
