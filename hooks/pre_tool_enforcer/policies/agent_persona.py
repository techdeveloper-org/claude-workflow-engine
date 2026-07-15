# pre_tool_enforcer/policies/agent_persona.py
# PreToolUse policy: block general-purpose subagent spawns lacking a library persona.
# Windows-safe: ASCII only, no Unicode characters.

_GENERIC_TYPES = ("general-purpose", "claude", "")
_PERSONA_MARKER = "---persona---"
_ESCAPE_HATCH = "[GENERIC-OK]"

_BLOCK_MSG = (
    "[PRE-TOOL BLOCKED] Generic subagent spawned without a library persona!\n"
    "  Tool       : Agent/Task spawn with subagent_type=general-purpose (or unset)\n"
    "  Problem    : No agents/{name}/agent.md persona was injected into the prompt.\n"
    "  Required   : Route to a library agent, read its Skill Dependencies, then\n"
    "               inject its persona as a '---persona---' YAML block at the top\n"
    "               of the prompt (see ORCHESTRATION_TEMPLATE.md STEP 0.05,\n"
    "               Subagent Dispatch Contract).\n"
    "  Escape hatch: prefix the prompt/description with [GENERIC-OK] for a\n"
    "               genuinely generic one-off task with no matching persona.\n"
    "  Note       : Local code exploration should use the built-in 'Explore'\n"
    "               subagent_type instead -- it is not gated by this policy.\n"
    "  Action     : Add subagent_type of a named library agent, or inject the\n"
    "               '---persona---' block, or prefix with [GENERIC-OK]."
)


def check_agent_persona(tool_name, tool_input):
    """PreToolUse policy: block general-purpose subagent spawns lacking a persona.

    A general-purpose (or unset) subagent_type must carry a library agent
    persona injected as a '---persona---' YAML block at the top of its
    prompt, per the Subagent Dispatch Contract. Named built-in subagent
    types (e.g. Explore, Plan) are never gated. An explicit '[GENERIC-OK]'
    marker in the prompt/description is an escape hatch for genuinely
    generic one-off tasks.

    Args:
        tool_name (str): Name of the tool (must be 'Agent' or 'Task' to trigger).
        tool_input (dict): Tool parameters dict with 'subagent_type' and
            'prompt' (or 'description') keys. Any non-dict value (None,
            malformed payload) is treated as fail-open, never as a block.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in ("Agent", "Task"):
        return False, ""

    if not isinstance(tool_input, dict):
        return False, ""

    subagent_type = str(tool_input.get("subagent_type") or "").strip().lower()
    if subagent_type not in _GENERIC_TYPES:
        return False, ""

    prompt = str(tool_input.get("prompt") or tool_input.get("description") or "")
    if _PERSONA_MARKER in prompt or _ESCAPE_HATCH in prompt:
        return False, ""

    return True, _BLOCK_MSG
