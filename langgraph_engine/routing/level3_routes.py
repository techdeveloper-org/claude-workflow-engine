"""Level 3 routing functions - Execution pipeline conditional edges.

Extracted from orchestrator.py. Controls routing within Level 3 steps:
- Step 11 review: pass/retry conditional loop

CHANGE LOG (v1.13.0):
  route_after_step1_decision removed -- Step 1 no longer exists in the graph.
  Stub kept for backward-compat test imports.
"""

from typing import Literal

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from ..flow_state import FlowState, StepKeys


def route_after_step1_decision(state: FlowState) -> str:
    """DEPRECATED (v1.13.0): Step 1 no longer exists in the graph.

    Returns 'level3_step2' as a safe no-op default.
    This stub preserves backward compatibility for any tests that import it.
    """
    logger.warning("[routing] route_after_step1_decision called but Step 1 no longer exists (v1.13.0)")
    return "level3_step2"


def route_after_step11_review(state: FlowState) -> Literal["level3_step12", "level3_step11_retry"]:
    """Conditional routing after PR review: if failed and retries < 3, retry; else continue to closure."""
    review_passed = state.get(StepKeys.REVIEW_PASSED, False)
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)

    if review_passed or retry_count >= 3:
        return "level3_step12"
    else:
        # Route to retry node (which will increment count via proper state return)
        return "level3_step11_retry"
