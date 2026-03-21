"""Step helper nodes - Per-step utility nodes for Level 3 execution.

Extracted from orchestrator.py. Contains nodes that manage step-level
state transitions (e.g., retry counter increments).
"""

from ..flow_state import FlowState, StepKeys


def step11_retry_increment_node(state: FlowState) -> dict:
    """Increment retry count before re-routing to Step 10.

    State mutations must happen in nodes, not routing functions (LangGraph anti-pattern).
    """
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)
    return {StepKeys.RETRY_COUNT: retry_count + 1}
