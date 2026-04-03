# pre_tool_enforcer/policies/checkpoint.py
# Level 3.3: Block code-changing tools if review checkpoint is pending.
# Windows-safe: ASCII only, no Unicode characters.

from ..loaders import find_session_flag, get_current_session_id

# Tools that are BLOCKED while checkpoint is pending (file-modification tools ONLY)
BLOCKED_WHILE_CHECKPOINT_PENDING = {"Write", "Edit", "NotebookEdit"}


def check_checkpoint_pending(tool_name, tool_input):
    """Level 3.3: Block code-changing tools if review checkpoint is pending.

    User must say 'ok'/'proceed' before coding can start.
    SESSION-AWARE (Loophole #11): Uses session-specific flag files.
    Each window has its own flag file. No cross-window interference.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters (unused by this check).

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return False, ""

    current_session_id = get_current_session_id()
    if not current_session_id:
        return False, ""

    flag_path, flag_data = find_session_flag(".checkpoint-pending", current_session_id)
    if flag_path is None:
        return False, ""

    session_id = flag_data.get("session_id", "unknown")
    prompt_preview = flag_data.get("prompt_preview", "")[:80]

    msg = (
        "[PRE-TOOL BLOCKED] Review checkpoint is pending!\n"
        "  Session  : " + session_id + "\n"
        "  Task     : " + prompt_preview + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until user confirms.\n"
        '  Required : User must reply with "ok" or "proceed" first.\n'
        "  Reason   : CLAUDE.md policy - no coding before checkpoint review.\n"
        "  Action   : Show the [REVIEW CHECKPOINT] to user and WAIT."
    )
    return True, msg
