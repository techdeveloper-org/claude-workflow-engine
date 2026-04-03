# pre_tool_enforcer/policies/failure_kb.py
# Level 3.7: Consult failure-kb.json for known failure patterns.
# Non-blocking: returns hints only, never blocks.
# Windows-safe: ASCII only, no Unicode characters.

import re

from ..loaders import _load_failure_kb


def check_failure_kb_hints(tool_name, tool_input):
    """Level 3.7: Consult failure-kb.json for known failure patterns.

    Non-blocking: emits hint messages based on known failure patterns for this
    tool. Never blocks - the returned 'blocked' is always False.

    The hints are collected by core.py and printed to stdout.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters dict.

    Returns:
        tuple: (blocked: bool, message: str) - blocked is always False.
               message contains newline-joined hints (empty string if none).
    """
    hints = []
    kb = _load_failure_kb()
    if not kb:
        return False, ""

    tool_patterns = kb.get(tool_name, [])
    for pattern in tool_patterns:
        pattern_id = pattern.get("pattern_id", "")
        solution = pattern.get("solution", {})
        sol_type = solution.get("type", "")

        if tool_name == "Edit" and pattern_id == "edit_line_number_prefix":
            old_str = tool_input.get("old_string", "")
            if old_str:
                if re.match(r"^\s*\d+", old_str):
                    hints.append(
                        "[FAILURE-KB] Edit: old_string may contain line number prefix. "
                        "Strip line numbers before Edit (pattern from failure-kb.json)."
                    )

        elif tool_name == "Edit" and pattern_id == "edit_without_read":
            hints.append(
                "[FAILURE-KB] Edit: Ensure file was Read before Edit " "(known failure pattern from failure-kb.json)."
            )

        elif tool_name == "Bash" and sol_type == "translate":
            cmd = tool_input.get("command", "").strip().lower()
            mapping = solution.get("mapping", {})
            for win_cmd, unix_cmd in mapping.items():
                if cmd.startswith(win_cmd.lower()):
                    hints.append(
                        '[FAILURE-KB] Bash: Translate "' + win_cmd + '" -> "' + unix_cmd + '" '
                        "(known failure from failure-kb.json, confidence: " + str(pattern.get("confidence", 0)) + ")"
                    )

    if hints:
        return False, "\n".join(hints)
    return False, ""
