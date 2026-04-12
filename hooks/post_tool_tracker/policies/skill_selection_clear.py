"""
post_tool_tracker/policies/skill_selection_clear.py - Level 3.5 flag-clearing logic.

Clears the .skill-selection-pending flag when Skill or Task is called
and the invoked skill matches the required skill in the flag file.
"""

import json
from pathlib import Path


def handle_skill_selection(
    tool_name,
    tool_input,
    is_error,
    session_id,
    flag_dir,
    clear_session_flags,
    emit_flag_lifecycle,
    debug_log=None,
):
    """Level 3.5: Clear skill-selection flag when Skill or Task is called.

    Loophole #16 fix: verifies the invoked skill/agent matches the required
    skill stored in the flag file before clearing the flag.

    Args:
        tool_name (str):           Current tool name.
        tool_input (dict):         Tool input dict.
        is_error (bool):           Whether the tool call errored.
        session_id (str):          Current session ID.
        flag_dir:                  Path-like FLAG_DIR.
        clear_session_flags:       Callable(pattern_prefix, session_id, flag_dir).
        emit_flag_lifecycle:       Callable for metrics emission.
        debug_log (callable):      Optional debug logging function.
    """
    if debug_log is None:
        debug_log = lambda msg: None  # noqa: E731

    if tool_name not in ("Skill", "Task") or is_error:
        return

    try:
        should_clear = True
        if session_id:
            # v4.4.0: Check session folder first, then legacy
            _mem = Path.home() / ".claude" / "memory"
            flag_path = _mem / "logs" / "sessions" / session_id / "flags" / "skill-selection-pending.json"
            if not flag_path.exists():
                flag_path = Path(flag_dir) / (".skill-selection-pending-" + session_id + ".json")
            if flag_path.exists():
                with open(flag_path, "r", encoding="utf-8") as f:
                    flag_data = json.load(f)
                required = flag_data.get("required_skill", "")
                if required:
                    actual = ""
                    if tool_name == "Skill":
                        actual = (tool_input or {}).get("skill", "")
                    elif tool_name == "Task":
                        actual = (tool_input or {}).get("subagent_type", "")
                    if actual and required and actual != required:
                        should_clear = False  # wrong skill invoked
        if should_clear:
            clear_session_flags(".skill-selection-pending", session_id, flag_dir)
            try:
                emit_flag_lifecycle(
                    "skill_selection", "clear", session_id=session_id or "", reason="Skill/Task tool invoked"
                )
            except Exception:
                pass
    except Exception:
        pass
