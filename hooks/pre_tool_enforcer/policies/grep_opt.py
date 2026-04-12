# pre_tool_enforcer/policies/grep_opt.py
# Level 3.6: BLOCK Grep content-mode calls without head_limit.
# Windows-safe: ASCII only, no Unicode characters.

from ..loaders import _load_flow_trace_context


def check_grep_opt(tool_name, tool_input):
    """Level 3.6: BLOCK Grep content-mode calls without head_limit.

    When output_mode is 'content', Grep can return thousands of lines and
    waste the context window. This check BLOCKS such calls until head_limit
    is set. For 'files_with_matches' and 'count' modes, no block is raised
    (those modes are already compact).

    Also blocks if head_limit exceeds the max allowed (100).

    Args:
        tool_name (str): Name of the tool (must be 'Grep' to trigger).
        tool_input (dict): Tool parameters from the Grep call.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name != "Grep":
        return False, ""

    head_limit = tool_input.get("head_limit", 0)
    output_mode = tool_input.get("output_mode", "files_with_matches")

    if not head_limit:
        ctx = _load_flow_trace_context()
        complexity = ctx.get("complexity", 0)
        suggested = 50 if (complexity and complexity >= 10) else 100

        if output_mode == "content":
            return True, (
                '[TOOL-OPT BLOCKED] Grep output_mode="content" requires head_limit. '
                "CHOOSE ONE:\n"
                "1. Add head_limit=" + str(suggested) + " to prevent context overflow. "
                "Rule: ALWAYS set head_limit on Grep content-mode calls."
            )
        # Non-content mode without head_limit: not blocked (hint only in core)
        return False, ""

    # ADDITIONAL ENFORCEMENT: Check if head_limit exceeds max allowed
    try:
        max_head_limit = 100
        if int(head_limit) > max_head_limit:
            return True, (
                "[TOOL-OPT BLOCKED] Grep: head_limit=" + str(head_limit) + " exceeds max " + str(max_head_limit) + ". "
                "Use head_limit=" + str(max_head_limit) + " to prevent context overflow. "
                "Rule: Maximum " + str(max_head_limit) + " matches per Grep call (output_mode=content)."
            )
    except (ValueError, TypeError):
        pass

    return False, ""
