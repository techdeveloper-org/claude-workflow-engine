"""Level 3 routing functions - Execution pipeline conditional edges.

Extracted from orchestrator.py. Controls routing within Level 3 steps:
- Step 1 decision: plan mode vs direct execution
- Step 11 review: pass/retry conditional loop
"""

from typing import Literal

from ..flow_state import FlowState, StepKeys


def route_after_step1_decision(state: FlowState) -> Literal["level3_step2", "level3_step3"]:
    """Conditional routing: if plan required, execute Step 2; else skip to Step 3."""
    if state.get(StepKeys.PLAN_REQUIRED, True):
        return "level3_step2"
    return "level3_step3"


def route_after_step11_review(state: FlowState) -> Literal["level3_step12", "level3_step11_retry"]:
    """Conditional routing after PR review: if failed and retries < 3, retry; else continue to closure."""
    review_passed = state.get(StepKeys.REVIEW_PASSED, False)
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)

    if review_passed or retry_count >= 3:
        return "level3_step12"
    else:
        # Route to retry node (which will increment count via proper state return)
        return "level3_step11_retry"
