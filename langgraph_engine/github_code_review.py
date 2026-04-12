"""Backward-compat shim -- moved to level3_execution/github_code_review.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.github_code_review is deprecated. "
    "Use langgraph_engine.level3_execution.github_code_review instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.github_code_review import *  # noqa: E402,F401,F403
