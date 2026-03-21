"""FlowState package - Modular state management for 3-level pipeline.

Backward-compatible re-exports. Existing code continues to work unchanged:
    from .flow_state import FlowState, StepKeys, WorkflowContextOptimizer
"""

from .reducers import _keep_first_value, _merge_lists, _merge_dicts
from .state_definition import FlowState
from .step_keys import StepKeys
from .context_optimizer import WorkflowContextOptimizer
from .toon_format import ToonObject

__all__ = [
    "FlowState",
    "StepKeys",
    "WorkflowContextOptimizer",
    "ToonObject",
    "_keep_first_value",
    "_merge_lists",
    "_merge_dicts",
]
