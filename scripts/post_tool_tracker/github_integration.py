"""
post_tool_tracker/github_integration.py - GitHub issue manager integration.

Provides lazy loading of the github_issue_manager module and the
close_github_issues_on_completion() non-blocking check used in main().
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Lazy-loaded GitHub issue manager
# ---------------------------------------------------------------------------

_github_issue_manager = None


def _get_github_issue_manager():
    """Lazy import of github_issue_manager module. Returns module or None."""
    global _github_issue_manager
    if _github_issue_manager is None:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # github_issue_manager lives in the scripts/ directory (parent of this package)
            scripts_dir = str(Path(script_dir).parent)
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import github_issue_manager

            _github_issue_manager = github_issue_manager
        except ImportError:
            _github_issue_manager = False
    return _github_issue_manager if _github_issue_manager is not False else None


# ---------------------------------------------------------------------------
# Non-blocking GitHub issue close on task completion (Level 3.12)
# ---------------------------------------------------------------------------


def close_github_issues_on_completion(tool_name, tool_input, tool_response, is_error, state):
    """Level 3.12: Close GitHub issues when a task is marked completed (non-blocking).

    Policy: github-integration-policy.md
    Rule: On TaskUpdate(status=completed), close the linked GitHub issue.
    This is informational only - never exits 2, always returns False.

    Args:
        tool_name (str):     Current tool being invoked.
        tool_input (dict):   Input dict for the tool call.
        tool_response:       Tool response (used to extract task ID).
        is_error (bool):     Whether the tool call errored.
        state (dict):        Session progress dict.

    Returns:
        (bool, str): Always (False, '') - this check is non-blocking.
    """
    if tool_name != "TaskUpdate" or is_error:
        return False, ""
    task_status = (tool_input or {}).get("status", "")
    if task_status != "completed":
        return False, ""
    try:
        gim = _get_github_issue_manager()
        if gim:
            closed_task_id = (tool_input or {}).get("taskId", "")
            if closed_task_id:
                closed = gim.close_github_issue(closed_task_id)
                if closed:
                    sys.stderr.write("[GH L3.12] Issue closed for task " + str(closed_task_id) + "\n")
                    sys.stderr.flush()
    except Exception:
        pass  # Non-blocking: GitHub errors never fail the hook
    return False, ""
