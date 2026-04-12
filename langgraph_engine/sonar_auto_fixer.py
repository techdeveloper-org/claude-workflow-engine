"""Backward-compat shim -- moved to level3_execution/sonar_auto_fixer.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.sonar_auto_fixer is deprecated. "
    "Use langgraph_engine.level3_execution.sonar_auto_fixer instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.sonar_auto_fixer import *  # noqa: E402,F401,F403
