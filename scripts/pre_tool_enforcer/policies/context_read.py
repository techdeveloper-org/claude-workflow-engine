# pre_tool_enforcer/policies/context_read.py
# Level 3.0: Block Write/Edit/NotebookEdit/Bash if context files have not been read.
# Windows-safe: ASCII only, no Unicode characters.

import json
import os
from pathlib import Path

from ..loaders import get_current_session_id

BLOCKED_IF_NO_CONTEXT = {"Write", "Edit", "NotebookEdit", "Bash"}


def check_context_read_complete(tool_name, tool_input):
    """ENFORCEMENT: Block Write/Edit/NotebookEdit/Bash if context files have NOT been read.

    Context-read enforcement: The policy states "read SRS, README, CLAUDE.md before
    coding". The context-reader.py (Level 3.0) creates a .context-read-SESSION-PID.json
    flag when it completes. This function checks for that flag.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters (unused by this check).

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in BLOCKED_IF_NO_CONTEXT:
        return False, ""

    current_session_id = get_current_session_id()
    if not current_session_id:
        return False, ""

    try:
        flag_dir = Path.home() / ".claude" / "memory" / "flags"
        pid = os.getpid()
        flag_pattern = ".context-read-" + current_session_id + "-" + str(pid) + ".json"

        flag_files = list(flag_dir.glob(flag_pattern)) if flag_dir.exists() else []
        if not flag_files:
            # Flag doesn't exist yet - fail-open (context-reader runs on UserPromptSubmit)
            return False, ""

        flag_file = flag_files[0]
        flag_data = json.loads(flag_file.read_text(encoding="utf-8"))

        is_new_project = flag_data.get("is_new_project", True)
        enforcement_applies = flag_data.get("enforcement_applies", False)

        if is_new_project:
            # Fresh project - no context files to read, skip enforcement
            return False, ""

        if not enforcement_applies:
            # Existing project but context was read
            return False, ""

        # Existing project AND enforcement applies - check flow-trace
        try:
            trace_path = Path.home() / ".claude" / "logs" / "flow-trace.json"
            if trace_path.exists():
                trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
                pipeline = trace_data.get("pipeline", [])
                for entry in pipeline:
                    if entry.get("step") == "LEVEL_1_CONTEXT":
                        return False, ""
            # Context not read - block
            return True, ("Context not yet read for this session. " "Wait for Level 1 sync to complete before writing.")
        except Exception:
            pass  # fail-open on parse errors

    except Exception:
        pass  # fail-open on any error

    return False, ""
