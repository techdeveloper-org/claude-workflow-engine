"""standards package -- project type detection, standards loading, and integration hooks.

Re-exports all public symbols from sub-modules so callers can use:
    from langgraph_engine.standards import select_standards, detect_project_type
    from langgraph_engine.standards import apply_standards_at_step
"""

from .integration import STANDARDS_INTEGRATION_POINTS, apply_standards_at_step, load_standards  # noqa: F401
from .selector import (  # noqa: F401
    PRIORITY_CUSTOM,
    PRIORITY_FRAMEWORK,
    PRIORITY_LANGUAGE,
    PRIORITY_TEAM,
    compare_standards,
    detect_conflicts,
    detect_framework,
    detect_project_type,
    load_custom_standards,
    load_framework_standards,
    load_language_standards,
    load_team_standards,
    resolve_conflicts,
    select_standards,
)
