# pre_tool_enforcer/policies/task_breakdown.py
# Level 3.1: Block code-changing tools if task breakdown is pending.
# Windows-safe: ASCII only, no Unicode characters.

from datetime import datetime

from ..loaders import find_session_flag, get_current_session_id

BLOCKED_WHILE_TASK_PENDING = {"Write", "Edit", "NotebookEdit"}


def check_task_breakdown_pending(tool_name, tool_input):
    """Level 3.1: Block code-changing tools if task breakdown is pending.

    Claude MUST call TaskCreate before any Write/Edit/Bash/Task.
    SESSION-AWARE (Loophole #11): Uses session-specific flag files.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters (unused by this check).

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in BLOCKED_WHILE_TASK_PENDING:
        return False, ""

    current_session_id = get_current_session_id()
    if not current_session_id:
        return False, ""

    flag_path, flag_data = find_session_flag(".task-breakdown-pending", current_session_id)
    if flag_path is None:
        return False, ""

    # TTL: auto-expire flag after 90 seconds (prevents permanent blocking)
    flag_created = flag_data.get("created_at", "")
    if flag_created:
        try:
            created_dt = datetime.fromisoformat(flag_created)
            age_seconds = (datetime.now() - created_dt).total_seconds()
            if age_seconds > 90:
                try:
                    flag_path.unlink()
                except Exception:
                    pass
                # Expired - hint but do not block
                return False, ""
        except Exception:
            pass

    session_id = flag_data.get("session_id", "unknown")
    prompt_preview = flag_data.get("prompt_preview", "")[:80]

    msg = (
        "[PRE-TOOL BLOCKED] Step 3.1 Task Breakdown is pending!\n"
        "  Session  : " + session_id + "\n"
        "  Task     : " + prompt_preview + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until TaskCreate is called.\n"
        "  Required : Call TaskCreate tool FIRST to create task(s) for this request.\n"
        "  Reason   : CLAUDE.md Step 3.1 - TaskCreate MANDATORY before any coding.\n"
        "  Action   : Call TaskCreate with subject and description, then continue."
    )
    return True, msg
