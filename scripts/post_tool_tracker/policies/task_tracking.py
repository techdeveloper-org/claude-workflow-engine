"""
post_tool_tracker/policies/task_tracking.py - Task-update frequency / warning policy.

Policy: task-progress-tracking-policy.md
Rule: Warn if more than 5 tool calls occur without a TaskUpdate.
      Recommend updating every 2-3 tool calls.
"""

import sys


def enforce_task_update_frequency(tool_name, flow_ctx, state, debug_log=None):
    """Enforce task-update frequency and emit a warning to stderr when exceeded.

    Mutates state['tools_since_last_update'] in place; callers must save
    session progress after this function returns.

    Args:
        tool_name (str):     Current tool name.
        flow_ctx (dict):     Flow-trace context with 'complexity' key.
        state (dict):        Session progress dict (mutated in place).
        debug_log (callable): Optional debug logging function.

    Returns:
        None
    """
    if debug_log is None:
        debug_log = lambda msg: None  # noqa: E731

    debug_log("  [GRANULAR] Step 3.1.12: Enforcing task progress update frequency policy")
    try:
        if tool_name in ("TaskUpdate", "TaskCreate"):
            state["tools_since_last_update"] = 0
            debug_log("  [GRANULAR] Step 3.1.12: ? Reset tools_since_last_update for TaskCreate/TaskUpdate")
        else:
            tools_since = state.get("tools_since_last_update", 0) + 1
            state["tools_since_last_update"] = tools_since
            debug_log("  [GRANULAR] Step 3.1.12: ? Incremented tools_since_last_update to " + str(tools_since))

            # Only warn for file-modifying tools (not reads/searches)
            if tools_since > 5 and tool_name in ("Write", "Edit", "Bash", "NotebookEdit"):
                complexity = flow_ctx.get("complexity", 0)
                if complexity >= 3:
                    sys.stderr.write(
                        "[POLICY] task-progress-tracking: " + str(tools_since) + " tool calls since last TaskUpdate!\n"
                        "  Policy says: Update every 2-3 tool calls (max 5).\n"
                        "  ACTION: Call TaskUpdate with metadata to track progress.\n"
                        '  Example: TaskUpdate(id, metadata={"progress": "step X/Y complete"})\n'
                    )
                    sys.stderr.flush()
                    debug_log("  [GRANULAR] Step 3.1.12: ? Wrote task-progress-tracking policy warning")
    except Exception as e:
        debug_log(
            "  [GRANULAR] Step 3.1.12: ? EXCEPTION in task-progress-tracking policy: "
            + type(e).__name__
            + ": "
            + str(e)[:200]
        )
        raise
