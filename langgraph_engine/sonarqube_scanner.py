"""Backward-compat shim -- moved to level3_execution/sonarqube_scanner.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.sonarqube_scanner is deprecated. "
    "Use langgraph_engine.level3_execution.sonarqube_scanner instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.sonarqube_scanner import *  # noqa: E402,F401,F403
