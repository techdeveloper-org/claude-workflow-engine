"""Backward-compat shim -- moved to langgraph_engine.standards.selector."""

from langgraph_engine.standards.selector import *  # noqa: F401, F403
from langgraph_engine.standards.selector import (  # noqa: F401
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
