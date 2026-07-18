"""Backward-compat shim -- canonical location is langgraph_engine.level3_execution.test_generator."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.test_generator is deprecated. "
    "Use langgraph_engine.level3_execution.test_generator instead.",
    DeprecationWarning,
    stacklevel=2,
)
from langgraph_engine.level3_execution.test_generator import *  # noqa: E402,F401,F403
