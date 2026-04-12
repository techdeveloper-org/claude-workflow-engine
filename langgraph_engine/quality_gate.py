"""Backward-compat shim -- moved to level3_execution/quality_gate.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.quality_gate is deprecated. "
    "Use langgraph_engine.level3_execution.quality_gate instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.quality_gate import *  # noqa: E402,F401,F403
