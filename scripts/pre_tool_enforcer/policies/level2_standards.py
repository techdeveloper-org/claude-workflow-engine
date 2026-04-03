# pre_tool_enforcer/policies/level2_standards.py
# Level 2 Standards System enforcement: Block Write/Edit/NotebookEdit if Level 2
# pipeline step has not completed for the current session.
# Windows-safe: ASCII only, no Unicode characters.

import os
from datetime import datetime
from pathlib import Path

from ..loaders import _load_raw_flow_trace, _pipeline_step_present, get_current_session_id

BLOCKED_TOOLS = {"Write", "Edit", "NotebookEdit"}

# All known step name variants emitted by different versions of 3-level-flow.py
L2_STEP_NAMES = {"LEVEL_2_STANDARDS", "LEVEL_2_1_COMMON", "LEVEL_2_2_MICROSERVICES"}


def check_level2_standards_complete(tool_name, tool_input):
    """Level 2 Standards System enforcement.

    Blocks Write/Edit/NotebookEdit if the Level 2 Standards System (coding
    standards loader) has NOT been completed by 3-level-flow.py for the
    current session.

    Completion is detected by the presence of any LEVEL_2_* step in the
    flow-trace.json pipeline array.

    Fail-open: same as check_level1_sync_complete - if trace is unavailable
    the check is skipped to avoid blocking legitimate first-prompt tool calls.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters (unused by this check).

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in BLOCKED_TOOLS:
        return False, ""

    current_session_id = get_current_session_id()
    if not current_session_id:
        return False, ""

    raw_trace = _load_raw_flow_trace()
    if raw_trace is None:
        # Fail-open: trace not available yet, do not block
        return False, ""

    # TTL: auto-expire blocking after 90 seconds if flow-trace is stale
    try:
        _trace_path_l2 = (
            Path.home() / ".claude" / "memory" / "logs" / "sessions" / current_session_id / "flow-trace.json"
        )
        if _trace_path_l2.exists():
            _trace_age_l2 = (
                datetime.now() - datetime.fromtimestamp(os.path.getmtime(str(_trace_path_l2)))
            ).total_seconds()
            if _trace_age_l2 > 90:
                return False, ""
    except Exception:
        pass

    if any(_pipeline_step_present(raw_trace, name) for name in L2_STEP_NAMES):
        return False, ""

    msg = (
        "[PRE-TOOL BLOCKED] Level 2 Standards System not complete yet!\n"
        "  Session  : " + current_session_id + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until Level 2 finishes.\n"
        "  Required : Need to load 65 coding standards.\n"
        "  Reason   : 3-level-flow.py Level 2 must complete before code changes.\n"
        "  Action   : Wait for 3-level-flow.py to finish Level 2 Standards System."
    )
    return True, msg
