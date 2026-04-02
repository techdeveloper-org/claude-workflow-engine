"""Level -1 routing functions - Auto-fix enforcement conditional edges.

Extracted from orchestrator.py. Controls flow through Level -1 checks
and the user choice / retry loop.
"""

from typing import Literal

from ..flow_state import FlowState, StepKeys

# Must match MAX_LEVEL_MINUS1_ATTEMPTS in subgraphs/level_minus1.py
_MAX_LEVEL_MINUS1_ATTEMPTS = 3


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
        # Check retry count to prevent infinite loops (max 3 attempts: counts 0,1,2 allowed)
        retry_count = state.get(StepKeys.LEVEL_MINUS1_RETRY_COUNT, 0)
        if retry_count < _MAX_LEVEL_MINUS1_ATTEMPTS:
            return "fix_level_minus1"
        # Max attempts reached: ask node set choice="force_continue"; fall through below

    # "force_continue": max-attempts path (ask node sets this when retry_count >= 3)
    # "skip": user explicitly chose to proceed without fixing
    # default/unknown: continue safely to Level 1
    return "level1_session"
