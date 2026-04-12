"""Backward-compat shim -- moved to level3_execution/documentation_generator.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.documentation_generator is deprecated. "
    "Use langgraph_engine.level3_execution.documentation_generator instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.documentation_generator import *  # noqa: E402,F401,F403
