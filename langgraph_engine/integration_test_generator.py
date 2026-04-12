"""Backward-compat shim -- moved to level3_execution/integration_test_generator.py."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.integration_test_generator is deprecated. "
    "Use langgraph_engine.level3_execution.integration_test_generator instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .level3_execution.integration_test_generator import *  # noqa: E402,F401,F403
