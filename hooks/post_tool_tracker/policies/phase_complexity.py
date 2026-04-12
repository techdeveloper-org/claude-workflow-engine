"""
post_tool_tracker/policies/phase_complexity.py - Phase-complexity enforcement.

Covers two checks:
  1. check_level_3_8_phase_requirement() - BLOCKING: Write/Edit requires TaskCreate
     when complexity >= 6.
  2. warn_phase_complexity() - Non-blocking stderr warning when Write/Edit is
     called without any TaskCreate at complexity >= 6.

Policy: task-phase-enforcement-policy.md
"""

import sys


def check_level_3_8_phase_requirement(tool_name, flow_ctx, state):
    """Level 3.8: BLOCK Write/Edit if complexity >= 6 and 0 TaskCreate calls.

    Policy: task-phase-enforcement-policy.md
    Rule: High-complexity tasks MUST use phased execution via TaskCreate.
    This converts the previous warn-only behaviour into a hard block.

    Args:
        tool_name (str):  Current tool being invoked.
        flow_ctx (dict):  Flow-trace context dict with 'complexity' key.
        state (dict):     Session progress dict with 'tasks_created' key.

    Returns:
        (bool, str): (True, message) if blocked, (False, '') otherwise.
    """
    BLOCKED_TOOLS = {"Write", "Edit", "NotebookEdit"}
    if tool_name not in BLOCKED_TOOLS:
        return False, ""
    complexity = flow_ctx.get("complexity", 0)
    tasks_created = state.get("tasks_created", 0)
    if complexity >= 6 and tasks_created == 0:
        msg = (
            "[BLOCKED L3.8] Phased execution required!\n"
            "  Complexity : " + str(complexity) + " (>= 6 threshold)\n"
            "  TaskCreate : 0 calls recorded this session\n"
            "  Policy     : task-phase-enforcement-policy.md\n"
            "  Action     : Call TaskCreate to define tasks BEFORE writing code.\n"
            "  Rule       : Complexity >= 6 REQUIRES phased execution via TaskCreate.\n"
            "  Tool       : " + tool_name + " is BLOCKED until tasks are created."
        )
        return True, msg
    return False, ""


def warn_phase_complexity(tool_name, flow_ctx, state, debug_log=None):
    """Emit a stderr warning when Write/Edit is called without TaskCreate at complexity >= 6.

    Non-blocking - does not return a block tuple.  Callers should call this
    in addition to check_level_3_8_phase_requirement() for the warning path.

    Args:
        tool_name (str):     Current tool name.
        flow_ctx (dict):     Flow-trace context with 'complexity' key.
        state (dict):        Session progress dict with 'tasks_created' key.
        debug_log (callable): Optional debug logging function.
    """
    if debug_log is None:
        debug_log = lambda msg: None  # noqa: E731

    debug_log("  [GRANULAR] Step 3.1.13: Enforcing complexity-aware phase reminder")
    try:
        complexity = flow_ctx.get("complexity", 0)
        tasks_created = state.get("tasks_created", 0)
        if complexity >= 6 and tasks_created == 0 and tool_name in ("Write", "Edit", "NotebookEdit"):
            sys.stderr.write(
                "[POLICY] task-phase-enforcement: Complexity=" + str(complexity) + " but 0 tasks created!\n"
                "  Policy says: Complexity >= 6 REQUIRES phased execution.\n"
                "  ACTION: Call TaskCreate to define tasks BEFORE writing code.\n"
            )
            sys.stderr.flush()
            debug_log("  [GRANULAR] Step 3.1.13: ? Wrote phase-enforcement policy warning")
        else:
            debug_log(
                "  [GRANULAR] Step 3.1.13: ? No phase-enforcement warning needed"
                " (complexity=" + str(complexity) + ", tasks_created=" + str(tasks_created) + ")"
            )
    except Exception as e:
        debug_log(
            "  [GRANULAR] Step 3.1.13: ? EXCEPTION in complexity-aware-phase-reminder: "
            + type(e).__name__
            + ": "
            + str(e)[:200]
        )
        raise
