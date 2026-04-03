# pre_tool_enforcer/policies/skill_selection.py
# Level 3.5: Block code-changing tools if skill/agent selection is pending.
# Windows-safe: ASCII only, no Unicode characters.

from datetime import datetime

from ..loaders import find_session_flag, get_current_session_id

BLOCKED_WHILE_SKILL_PENDING = {"Write", "Edit", "NotebookEdit"}


def check_skill_selection_pending(tool_name, tool_input):
    """Level 3.5: Block code-changing tools if skill/agent selection is pending.

    Claude MUST invoke Skill tool or Task(agent) before any Write/Edit.
    Note: Task/Bash NOT blocked - Task IS how Step 3.5 is done, Bash needed for git/tests.
    SESSION-AWARE (Loophole #11): Uses session-specific flag files.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters (unused by this check).

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in BLOCKED_WHILE_SKILL_PENDING:
        return False, ""

    current_session_id = get_current_session_id()
    if not current_session_id:
        return False, ""

    flag_path, flag_data = find_session_flag(".skill-selection-pending", current_session_id)
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
                return False, ""
        except Exception:
            pass

    session_id = flag_data.get("session_id", "unknown")
    required_skill = flag_data.get("required_skill", "unknown")
    required_type = flag_data.get("required_type", "skill")

    if required_type == "agent":
        action_required = 'Launch agent via Task tool: Task(subagent_type="' + required_skill + '")'
    else:
        action_required = 'Invoke skill via Skill tool: Skill(skill="' + required_skill + '")'

    msg = (
        "[PRE-TOOL BLOCKED] Step 3.5 Skill/Agent Selection is pending!\n"
        "  Session  : " + session_id + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until Skill/Agent is invoked.\n"
        "  Required : " + action_required + "\n"
        "  Reason   : CLAUDE.md Step 3.5 - Skill/Agent MUST be invoked before coding.\n"
        "  Action   : Invoke the skill/agent first, then continue coding."
    )
    return True, msg
