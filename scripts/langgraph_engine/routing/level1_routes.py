"""Level 1 routing functions - Context sync conditional edges.

Extracted from orchestrator.py. Controls routing from Level 1 to Level 2
based on context threshold.
"""

from typing import Literal

from ..flow_state import FlowState, StepKeys


def route_context_threshold(state: FlowState) -> Literal["level2_emergency_archive", "level2_common_standards"]:
    """Route based on context usage threshold."""
    if state.get(StepKeys.CONTEXT_THRESHOLD_EXCEEDED):
        return "level2_emergency_archive"
    return "level2_common_standards"
