"""
Level 3 Execution - Routing functions and merge node.
"""

from ...flow_state import FlowState

# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================


def route_after_step1_plan_decision(state: FlowState) -> str:
    """Route after Step 1: Plan Mode Decision.

    - If plan_required=true: Go to step2_plan_execution
    - If plan_required=false: Skip to step3_task_breakdown
    """
    plan_required = state.get("step1_plan_required", False)
    if plan_required:
        return "step2_execution"
    else:
        return "step3_breakdown"


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
    """Determine final status based on all 15 steps (Step 0-14)."""
    error_steps = [k for k in state if k.endswith("_error") and state.get(k)]

    updates = {}
    if error_steps:
        updates["final_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + [f"Level 3: {len(error_steps)} steps had errors"]
    else:
        updates["final_status"] = "OK"

    return updates
