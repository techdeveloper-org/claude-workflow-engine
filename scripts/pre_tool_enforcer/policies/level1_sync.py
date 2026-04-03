# pre_tool_enforcer/policies/level1_sync.py
# Level 1 Sync System enforcement: Block Write/Edit/NotebookEdit if Level 1
# pipeline steps have not completed for the current session.
# Windows-safe: ASCII only, no Unicode characters.

import os
from datetime import datetime
from pathlib import Path

from ..loaders import _load_raw_flow_trace, _pipeline_step_present, get_current_session_id

BLOCKED_TOOLS = {"Write", "Edit", "NotebookEdit"}


def check_level1_sync_complete(tool_name, tool_input):
    """Level 1 Sync System enforcement.

    Blocks Write/Edit/NotebookEdit if the Level 1 Sync System (context reading,
    session init, pattern detection) has NOT been completed by 3-level-flow.py
    for the current session.

    Completion is detected by the presence of LEVEL_1_CONTEXT and
    LEVEL_1_SESSION entries in the flow-trace.json pipeline array.

    Fail-open: if flow-trace.json cannot be read (e.g. first prompt of session
    before 3-level-flow has written the file), the check is skipped and the
    tool is allowed through.

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
        _trace_path_l1 = (
            Path.home() / ".claude" / "memory" / "logs" / "sessions" / current_session_id / "flow-trace.json"
        )
        if _trace_path_l1.exists():
            _trace_age_l1 = (
                datetime.now() - datetime.fromtimestamp(os.path.getmtime(str(_trace_path_l1)))
            ).total_seconds()
            if _trace_age_l1 > 90:
                return False, ""
    except Exception:
        pass

    level1_context_done = _pipeline_step_present(raw_trace, "LEVEL_1_CONTEXT")
    level1_session_done = _pipeline_step_present(raw_trace, "LEVEL_1_SESSION")

    if level1_context_done and level1_session_done:
        return False, ""

    missing = []
    if not level1_context_done:
        missing.append("LEVEL_1_CONTEXT (context reading)")
    if not level1_session_done:
        missing.append("LEVEL_1_SESSION (session init)")

    msg = (
        "[PRE-TOOL BLOCKED] Level 1 Sync System not complete yet!\n"
        "  Session  : " + current_session_id + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until Level 1 finishes.\n"
        "  Missing  : " + ", ".join(missing) + "\n"
        "  Required : Need context reading, session init, pattern detection.\n"
        "  Reason   : 3-level-flow.py Level 1 must complete before code changes.\n"
        "  Action   : Wait for 3-level-flow.py to finish Level 1 Sync System."
    )
    return True, msg
