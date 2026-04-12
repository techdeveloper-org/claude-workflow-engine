"""
FlowState TypedDict - Single source of truth for 3-level flow execution state.

Backward-compatibility shim. All symbols are re-exported from the state/ package.
Existing imports continue to work unchanged:
    from .flow_state import FlowState, StepKeys, WorkflowContextOptimizer
    from .flow_state import _keep_first_value, _merge_lists, _merge_dicts
"""

from .state import FlowState, StepKeys, WorkflowContextOptimizer, _keep_first_value, _merge_dicts, _merge_lists

__all__ = [
    "FlowState",
    "StepKeys",
    "WorkflowContextOptimizer",
    "_keep_first_value",
    "_merge_lists",
    "_merge_dicts",
]
