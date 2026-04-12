# pre_tool_enforcer/policies/read_opt.py
# Level 3.6: BLOCK Read on large files without offset/limit.
# Windows-safe: ASCII only, no Unicode characters.

import os


def check_read_opt(tool_name, tool_input):
    """Level 3.6: BLOCK Read on large files without offset/limit.

    Checks actual file size on disk. Files larger than 50KB (~500+ lines)
    are BLOCKED unless offset or limit is provided. Smaller files pass.
    Also blocks if limit exceeds the max allowed (500 lines).

    Args:
        tool_name (str): Name of the tool (must be 'Read' to trigger).
        tool_input (dict): Tool parameters from the Read call.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name != "Read":
        return False, ""

    limit = tool_input.get("limit")
    offset = tool_input.get("offset")

    if not limit and not offset:
        file_path = tool_input.get("file_path", "")
        if file_path:
            try:
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    file_size_kb = file_size // 1024
                    if file_size > 50 * 1024:  # >50KB = likely >500 lines
                        return True, (
                            "[TOOL-OPT BLOCKED] Read: file is " + str(file_size_kb) + "KB (>50KB limit). "
                            "CHOOSE ONE:\n"
                            "1. Add limit=200 and offset=0 to read in chunks. "
                            "Rule: Use offset+limit for files >500 lines."
                        )
            except Exception:
                pass
        return False, ""

    # ADDITIONAL ENFORCEMENT: Check if limit exceeds max allowed
    if limit:
        try:
            max_limit = 500
            if int(limit) > max_limit:
                return True, (
                    "[TOOL-OPT BLOCKED] Read: limit=" + str(limit) + " exceeds max " + str(max_limit) + ". "
                    "Use limit=" + str(max_limit) + " and offset to read large files in chunks. "
                    "Rule: Maximum " + str(max_limit) + " lines per Read call."
                )
        except (ValueError, TypeError):
            pass

    return False, ""
