"""Backward-compat shim -- canonical location is langgraph_engine.github.merge_validation."""

from langgraph_engine.github.merge_validation import *  # noqa: F401, F403
from langgraph_engine.github.merge_validation import (  # noqa: F401
    check_merge_conflicts_bulletproof,
    detect_git_conflict_markers,
    detect_project_type_for_validation,
    test_merge_locally,
    validate_project_after_merge,
)
