"""
Level 3 Execution - Routing functions and merge node.
"""

from ..flow_state import FlowState

# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================


# REMOVED (v1.14.0): route_after_step1_plan_decision -- Step 1 removed in v1.13.0
# REMOVED (v1.14.0): route_after_step0_to_step2 -- Step 2 removed from pipeline.
#   Step 0 now always routes directly to Step 8. The orchestrator subprocess
#   produces a comprehensive plan, making Step 2 plan execution redundant.


def route_after_step11_review(state: FlowState) -> str:
    """Route after Step 11: Pull Request Review.

    - If review passed OR retries >= 3: Go to step12_closure
    - If review failed AND retries < 3: Go back to step10_implementation for retry
    """
    review_passed = state.get("step11_review_passed", False)
    retry_count = state.get("step11_retry_count", 0)

    if review_passed or retry_count >= 3:
        return "step12_closure"
    else:
        return "step10_implementation"


# ============================================================================
# MERGE NODE
# ============================================================================


def level3_merge_node(state: FlowState) -> dict:
    """Determine final status based on all steps (Step 0, Steps 8-14)."""
    error_steps = [k for k in state if k.endswith("_error") and state.get(k)]

    updates = {}
    if error_steps:
        updates["final_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + [f"Level 3: {len(error_steps)} steps had errors"]
    else:
        updates["final_status"] = "OK"

    return updates
