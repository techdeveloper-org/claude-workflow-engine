"""
post_tool_tracker/policies/task_breakdown_clear.py - Level 3.1 flag-clearing logic.

Clears the .task-breakdown-pending flag when TaskCreate is called with
a meaningful subject (>= 3 chars) and description (>= 3 chars).

Also handles GitHub issue creation for the new task.
"""

import sys
from pathlib import Path


def handle_task_create(
    tool_name,
    tool_input,
    tool_response,
    is_error,
    state,
    session_id,
    flag_dir,
    get_github_issue_manager,
    clear_session_flags,
    save_session_progress,
    session_state_file,
    emit_flag_lifecycle,
    debug_log=None,
):
    """Level 3.1: Clear task-breakdown flag and create GitHub issue on TaskCreate.

    Args:
        tool_name (str):               Current tool name.
        tool_input (dict):             Tool input dict.
        tool_response:                 Tool response (for extracting task ID).
        is_error (bool):               Whether the tool call errored.
        state (dict):                  Session progress dict (mutated in place).
        session_id (str):              Current session ID.
        flag_dir:                      Path-like FLAG_DIR.
        get_github_issue_manager:      Callable returning github_issue_manager or None.
        clear_session_flags:           Callable(pattern_prefix, session_id, flag_dir).
        save_session_progress:         Callable(state, session_state_file).
        session_state_file:            Path-like SESSION_STATE_FILE.
        emit_flag_lifecycle:           Callable for metrics emission.
        debug_log (callable):          Optional debug logging function.
    """
    if debug_log is None:
        debug_log = lambda msg: None  # noqa: E731

    if tool_name != "TaskCreate" or is_error:
        return

    debug_log(
        "  [GRANULAR] Step 3.1.14: REACHED TaskCreate check block! tool_name="
        + tool_name
        + ", is_error="
        + str(is_error)
    )
    debug_log("TaskCreate check: tool_name=" + tool_name + ", is_error=" + str(is_error))

    debug_log("  ? TaskCreate detected and no error - proceeding with issue creation")
    debug_log("  [GH-START] ========== BEGIN GITHUB WORKFLOW FOR TaskCreate ==========")

    tc_subject = (tool_input or {}).get("subject", "")
    tc_desc = (tool_input or {}).get("description", "")

    try:
        if len(tc_subject) >= 3 and len(tc_desc) >= 3:
            clear_session_flags(".task-breakdown-pending", session_id, flag_dir)
            try:
                emit_flag_lifecycle(
                    "task_breakdown",
                    "clear",
                    session_id=session_id or "",
                    reason="TaskCreate called with valid subject+desc",
                )
            except Exception:
                pass
            # Track total tasks created for auto work-done detection
            state["tasks_created"] = state.get("tasks_created", 0) + 1
            save_session_progress(state, session_state_file)
        else:
            reasons = []
            if len(tc_subject) < 3:
                reasons.append("subject too short (" + str(len(tc_subject)) + " chars, need 3+)")
            if len(tc_desc) < 3:
                reasons.append("description too short (" + str(len(tc_desc)) + " chars, need 3+)")
            sys.stderr.write(
                "[POST-TOOL WARN] TaskCreate validation FAILED - task-breakdown flag NOT cleared!\n"
                "  Reason: " + ", ".join(reasons) + "\n"
                "  Fix: Call TaskCreate again with a meaningful subject (10+ chars) and description (10+ chars).\n"
            )
            sys.stderr.flush()
    except Exception:
        pass

    # GitHub Issues: Create issue for new task
    debug_log("  GitHub issue creation block: attempting to load github_issue_manager")
    try:
        gim = get_github_issue_manager()
        debug_log("  github_issue_manager loaded: " + str(gim is not None))
        if not gim:
            debug_log("  [GH-GRANULAR] github_issue_manager is None, skipping")
            sys.stderr.write("[GH-WORKFLOW] ?? GitHub issue manager not available\n")
            sys.stderr.flush()
        else:
            debug_log("  [GH-GRANULAR] github_issue_manager loaded successfully, proceeding")
            debug_log("  [GH-GRANULAR] Extracting task ID from response...")
            task_id = gim.extract_task_id_from_response(tool_response)
            debug_log("  [GH-GRANULAR] extract_task_id_from_response() returned: " + str(task_id))
            if not task_id:
                task_id = str(state.get("tasks_created", 1))
                debug_log("  [GH-GRANULAR] No task ID in response, using fallback: " + str(task_id))

            debug_log(
                "  [GH-GRANULAR] Task info: subject_len=" + str(len(tc_subject)) + ", desc_len=" + str(len(tc_desc))
            )

            if not tc_subject:
                debug_log("  [GH-GRANULAR] No subject, skipping issue creation")
                sys.stderr.write("[GH-WORKFLOW] ?? No task subject - skipping GitHub issue\n")
                sys.stderr.flush()
            elif len(tc_subject) < 5:
                debug_log("  [GH-GRANULAR] Subject too short (" + str(len(tc_subject)) + " chars), skipping")
                sys.stderr.write("[GH-WORKFLOW] ?? Subject too short (" + str(len(tc_subject)) + " chars, need 5+)\n")
                sys.stderr.flush()
            else:
                debug_log(
                    "  [GH-GRANULAR] About to call create_github_issue(task_id="
                    + str(task_id)
                    + ", subject='"
                    + tc_subject[:30]
                    + "')"
                )
                sys.stderr.write('[GH-WORKFLOW] Creating GitHub issue for task "' + tc_subject[:50] + '"...\n')
                sys.stderr.flush()

                debug_log("  [GH-GRANULAR] Calling gim.create_github_issue()...")
                issue_num = gim.create_github_issue(task_id, tc_subject, tc_desc)
                debug_log("  [GH-GRANULAR] create_github_issue() returned: " + str(issue_num))

                if issue_num:
                    sys.stderr.write(
                        "[GH-WORKFLOW] ? Issue #" + str(issue_num) + " created (branch created automatically)\n"
                    )
                    sys.stderr.flush()
                    debug_log("  [GH-GRANULAR] ? Issue #" + str(issue_num) + " creation reported success")
                else:
                    sys.stderr.write("[GH-WORKFLOW] ? Issue creation returned None - check logs\n")
                    sys.stderr.flush()
                    debug_log("  [GH-GRANULAR] ? Issue creation returned None")
    except Exception as e:
        debug_log("  [GH-GRANULAR] ? EXCEPTION in GitHub block: " + type(e).__name__ + ": " + str(e)[:150])
        sys.stderr.write("[GH-WORKFLOW] ? EXCEPTION: " + type(e).__name__ + ": " + str(e)[:150] + "\n")
        sys.stderr.flush()
        try:
            log_file = Path.home() / ".claude" / "memory" / "logs" / "github-workflow-errors.log"
            with open(log_file, "a", encoding="utf-8") as f:
                from datetime import datetime

                f.write("\n[" + datetime.now().isoformat() + "] TaskCreate GitHub issue error\n")
                f.write("  Error: " + type(e).__name__ + ": " + str(e) + "\n")
                f.write("  Subject: " + tc_subject + "\n")
        except Exception:
            pass

    debug_log("  [GH-END] ========== END GITHUB WORKFLOW FOR TaskCreate ==========")
