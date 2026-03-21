"""Standards integration hook factory.

Before this module existed, orchestrator.py contained 9 nearly identical
functions:

    def apply_integration_step1(state): ...
    def apply_integration_step2(state): ...
    ...
    def apply_integration_step13(state): ...

Each function had identical logic; only the step number differed.

create_integration_hook() is a Factory Method (GoF) that generates those
functions on demand from a single template, eliminating the duplication.

Usage in orchestrator.py graph construction::

    from scripts.langgraph_engine.core.integration_hook import create_integration_hook

    graph.add_node("level3_standards_hook_step1",  create_integration_hook(1))
    graph.add_node("level3_standards_hook_step5",  create_integration_hook(5))
    graph.add_node("level3_standards_hook_step13", create_integration_hook(13))
"""

from typing import Any, Callable, Dict


def create_integration_hook(step_number: int) -> Callable:
    """Return a LangGraph-compatible node function for the given pipeline step.

    The generated function calls standards_integration.apply_standards_at_step
    with the supplied step_number and returns only the FlowState fields that
    changed, avoiding an unnecessary full-state copy back into LangGraph.

    The import of apply_standards_at_step is deferred to call time (lazy
    import) so that this factory can be invoked safely during module
    initialisation before all pipeline modules have been loaded.

    Args:
        step_number: Pipeline step number in the range 0-14.

    Returns:
        A node function with the signature (state) -> Dict[str, Any].
        The function's __name__ and __doc__ are set to descriptive values
        that appear in LangGraph debug output and logs.
    """
    def integration_hook(state: Any) -> Dict[str, Any]:
        try:
            from ..standards_integration import apply_standards_at_step
            updated = apply_standards_at_step(step_number, dict(state))
            # Return only keys that were actually modified to keep the state
            # update minimal and avoid clobbering unrelated fields.
            return {
                k: updated[k]
                for k in updated
                if k not in state or updated[k] != state.get(k)
            }
        except Exception:
            return {}

    integration_hook.__name__ = "apply_integration_step%d" % step_number
    integration_hook.__doc__ = (
        "Apply standards integration at Step %d." % step_number
    )
    return integration_hook
