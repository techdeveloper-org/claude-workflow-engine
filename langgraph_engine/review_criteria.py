"""Backward-compat shim -- moved to level3_execution/review_criteria.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.review_criteria is deprecated. "
    "Use langgraph_engine.level3_execution.review_criteria instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.review_criteria import *  # noqa: E402,F401,F403
