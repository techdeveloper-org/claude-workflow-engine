"""Level -1 routing functions - Auto-fix enforcement conditional edges.

Extracted from orchestrator.py. Controls flow through Level -1 checks
and the user choice / retry loop.
"""

from typing import Literal

from ..flow_state import FlowState, StepKeys


def route_after_level_minus1(state: FlowState) -> Literal["ask_level_minus1_fix", "level1_session"]:
    """Route based on Level -1 status.

    - If OK: go to Level 1 session loader (level1_session)
    - If FAILED: ask user for recovery (ask_level_minus1_fix)
    """
    status = state.get(StepKeys.LEVEL_MINUS1_STATUS, "FAILED")
    if status == "OK":
        return "level1_session"
    else:
        return "ask_level_minus1_fix"


def route_after_level_minus1_user_choice(state: FlowState) -> Literal["fix_level_minus1", "level1_session"]:
    """Route based on user choice for Level -1 failures.

    - 'auto-fix': Attempt fixes and retry Level -1
    - 'skip': Continue to Level 1 (session_loader) anyway
    - default: Skip (user will fix manually)
    """
    choice = state.get(StepKeys.LEVEL_MINUS1_USER_CHOICE, "skip")

    if choice == "auto-fix":
        # Check retry count to prevent infinite loops (max 3 attempts)
        retry_count = state.get(StepKeys.LEVEL_MINUS1_RETRY_COUNT, 0)
        if retry_count < 3:
            return "fix_level_minus1"

    # Default: continue to Level 1 (start with session loader)
    return "level1_session"


def route_after_level_minus1_fix(state: FlowState) -> Literal["level_minus1_unicode", "ask_level_minus1_fix"]:
    """Route after fix attempt - retry Level -1 or ask again.

    After applying fixes, rerun Level -1 checks.
    If still fails, ask user again (with attempt number).
    """
    # Always retry checks after fix
    return "level_minus1_unicode"
