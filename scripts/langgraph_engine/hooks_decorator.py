"""
with_hooks Decorator - Add pre/post hooks to LangGraph nodes.

This decorator enables nested enforcement by allowing any node to have
custom validation, logging, or state transformation before/after execution.

Example:
    @with_hooks(
        pre_hook=validate_context_loaded,
        post_hook=track_node_completion
    )
    def step4_model_selection(state: FlowState) -> FlowState:
        ...
"""

from typing import Callable, Optional, Dict, Any
from functools import wraps
from .flow_state import FlowState


HookFunction = Callable[[FlowState], FlowState]


def with_hooks(
    pre_hook: Optional[HookFunction] = None,
    post_hook: Optional[HookFunction] = None,
) -> Callable:
    """Decorator to add pre/post hooks to a LangGraph node.

    Hooks are called before and after the main node function.
    If a hook raises an exception, the node execution is aborted
    and the exception propagates.

    Args:
        pre_hook: Optional function(state) -> state, called before node
        post_hook: Optional function(state) -> state, called after node

    Returns:
        Decorator function
    """

    def decorator(node_fn: Callable[[FlowState], FlowState]) -> Callable[[FlowState], FlowState]:
        @wraps(node_fn)
        def wrapped(state: FlowState) -> FlowState:
            # Pre-execution hook
            if pre_hook:
                state = pre_hook(state)

            # Execute main node
            state = node_fn(state)

            # Post-execution hook
            if post_hook:
                state = post_hook(state)

            return state

        return wrapped

    return decorator


# ============================================================================
# COMMON PRE-HOOKS (Validation & State Checks)
# ============================================================================


def validate_context_loaded(state: FlowState) -> FlowState:
    """Validate that context has been loaded before proceeding.

    Used before steps that depend on context (e.g., model selection).
    """
    if not state.get("context_loaded"):
        if "errors" not in state:
            state["errors"] = []
        state["errors"].append("Context not loaded before context-dependent step")

    return state


def validate_level1_complete(state: FlowState) -> FlowState:
    """Validate that all Level 1 tasks have completed."""
    required_fields = [
        "context_loaded",
        "session_chain_loaded",
        "preferences_loaded",
    ]

    missing = [f for f in required_fields if not state.get(f)]
    if missing:
        if "warnings" not in state:
            state["warnings"] = []
        state["warnings"].append(
            f"Level 1 incomplete: missing {', '.join(missing)}"
        )

    return state


def validate_standards_loaded(state: FlowState) -> FlowState:
    """Validate that standards have been loaded before Level 3."""
    if not state.get("standards_loaded"):
        if "warnings" not in state:
            state["warnings"] = []
        state["warnings"].append("Standards not loaded before Level 3 execution")

    return state


def validate_java_project_consistency(state: FlowState) -> FlowState:
    """Validate consistency between is_java_project and java_standards_loaded."""
    is_java = state.get("is_java_project")
    java_standards = state.get("java_standards_loaded")

    if is_java and not java_standards:
        if "warnings" not in state:
            state["warnings"] = []
        state["warnings"].append(
            "Java project detected but Java standards not loaded"
        )

    return state


# ============================================================================
# COMMON POST-HOOKS (Tracking & State Recording)
# ============================================================================


def track_node_completion(node_name: str) -> HookFunction:
    """Return a post-hook that tracks when a node completes.

    Args:
        node_name: Name of the node (e.g., "step4_model_selection")

    Returns:
        Post-hook function
    """

    def _track(state: FlowState) -> FlowState:
        if "pipeline" not in state:
            state["pipeline"] = []

        # Record node completion in pipeline
        state["pipeline"].append(
            {
                "node": node_name,
                "timestamp": str(datetime.now().isoformat()),
                "status": "completed",
            }
        )

        return state

    return _track


def track_node_error(error: str, node_name: str) -> HookFunction:
    """Return a post-hook that tracks errors for a node.

    Args:
        error: Error message
        node_name: Name of the node

    Returns:
        Post-hook function
    """

    def _track(state: FlowState) -> FlowState:
        if "errors" not in state:
            state["errors"] = []

        state["errors"].append(f"{node_name}: {error}")

        if "pipeline" not in state:
            state["pipeline"] = []

        state["pipeline"].append(
            {
                "node": node_name,
                "status": "error",
                "error": error,
            }
        )

        return state

    return _track


def validate_state_field(
    field_name: str,
    required: bool = True,
    allowed_values: Optional[list] = None,
) -> HookFunction:
    """Return a pre-hook that validates a state field exists and is valid.

    Args:
        field_name: Name of state field to validate
        required: If True, field must exist and be non-empty
        allowed_values: If provided, field must be one of these values

    Returns:
        Pre-hook function
    """

    def _validate(state: FlowState) -> FlowState:
        value = state.get(field_name)

        if required and not value:
            if "errors" not in state:
                state["errors"] = []
            state["errors"].append(f"Required field missing: {field_name}")
            return state

        if allowed_values and value not in allowed_values:
            if "errors" not in state:
                state["errors"] = []
            state["errors"].append(
                f"Field '{field_name}' value '{value}' not in allowed: {allowed_values}"
            )

        return state

    return _validate


# ============================================================================
# COMPOUND HOOKS
# ============================================================================


def safe_hook(
    main_hook: HookFunction,
    error_message: Optional[str] = None,
) -> HookFunction:
    """Wrap a hook in try/except to prevent failures from aborting execution.

    Args:
        main_hook: The hook function to safely wrap
        error_message: Custom error message if hook fails

    Returns:
        Safe hook function
    """

    def _safe(state: FlowState) -> FlowState:
        try:
            return main_hook(state)
        except Exception as e:
            if "warnings" not in state:
                state["warnings"] = []
            msg = error_message or f"Hook error: {str(e)}"
            state["warnings"].append(msg)
            return state

    return _safe


# Import datetime for timestamp in track_node_completion
from datetime import datetime
