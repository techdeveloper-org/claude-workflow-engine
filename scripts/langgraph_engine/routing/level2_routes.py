"""Level 2 routing functions - Standards loading conditional edges.

Extracted from orchestrator.py. Controls routing within Level 2
based on detected project type (Java vs non-Java).
"""

from typing import Literal

from ..flow_state import FlowState, StepKeys
from ..level2_standards import detect_project_type


def route_standards_loading(state: FlowState) -> Literal["level2_java_standards", "level2_merge"]:
    """Route based on project type (Java detection)."""
    detect_project_type(state)
    if state.get(StepKeys.IS_JAVA_PROJECT):
        return "level2_java_standards"
    return "level2_merge"
