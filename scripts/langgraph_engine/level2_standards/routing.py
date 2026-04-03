"""Level 2 Standards System - Merge node and routing.

Canonical location: langgraph_engine/level2_standards/routing.py
Windows-safe: ASCII only, no Unicode characters.
"""

import time

from .helpers import write_level_log

# ============================================================================
# MERGE NODE
# ============================================================================


def level2_merge_node(state):
    """Merge Level 2 results."""
    _step_start = time.time()
    updates = {}
    if state.get("standards_loaded"):
        updates["level2_status"] = "OK"
    else:
        updates["level2_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + ["Level 2: Standards loading failed"]

    write_level_log(
        state,
        "level2",
        "merge",
        updates["level2_status"],
        time.time() - _step_start,
        {
            "level2_status": updates["level2_status"],
            "total_standards": state.get("standards_count", 0),
        },
    )
    return updates


# ============================================================================
# ROUTING
# ============================================================================


def route_java_standards(state):
    """Route based on project type."""
    if state.get("is_java_project"):
        return "level2_java_standards"
    return "level2_merge"
