"""Backward-compat shim -- moved to level3_execution/sonarqube/."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.sonarqube is deprecated. " "Use langgraph_engine.level3_execution.sonarqube instead.",
    DeprecationWarning,
    stacklevel=2,
)
from ..level3_execution.sonarqube import *  # noqa: E402,F401,F403
