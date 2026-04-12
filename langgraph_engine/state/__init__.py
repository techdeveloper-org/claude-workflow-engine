"""FlowState package - Modular state management for 3-level pipeline.

Backward-compatible re-exports. Existing code continues to work unchanged:
    from .flow_state import FlowState, StepKeys, WorkflowContextOptimizer
"""

from .context_optimizer import WorkflowContextOptimizer
from .reducers import _keep_first_value, _merge_dicts, _merge_lists
from .state_definition import FlowState
from .step_keys import StepKeys

__all__ = [
    "FlowState",
    "StepKeys",
    "WorkflowContextOptimizer",
    "_keep_first_value",
    "_merge_lists",
    "_merge_dicts",
]
