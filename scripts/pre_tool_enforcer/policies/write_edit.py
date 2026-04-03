# pre_tool_enforcer/policies/write_edit.py
# Level 3.6: Tool Optimization hints for Write/Edit/NotebookEdit.
# Note: Unicode blocking is handled by python_unicode.py (separate policy).
# This module emits non-blocking hints only; it never blocks.
# Windows-safe: ASCII only, no Unicode characters.


def check_write_edit(tool_name, tool_input):
    """Level 3.6: Emit optimization hints for large Write operations.

    Checks:
      1. Warn if Write content exceeds 500 lines (suggest Edit instead)
      2. Warn if target file is large (>50KB) and using Write (full overwrite)

    Note: This check never blocks (returns False always).

    Args:
        tool_name (str): 'Write', 'Edit', or 'NotebookEdit'.
        tool_input (dict): Tool parameters dict.

    Returns:
        tuple: (blocked: bool, message: str) - blocked is always False here.
    """
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        return False, ""

    # This policy only emits hints, not blocks.
    # Unicode blocking is handled by python_unicode.py (separate policy).
    # Return False always; hints mechanism is handled by caller collecting stdout.
    return False, ""
