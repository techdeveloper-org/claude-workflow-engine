"""Backward-compat shim -- moved to langgraph_engine.context.cache (via level1_sync)."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.context_cache is deprecated. "
    "Use langgraph_engine.context.cache or langgraph_engine.level1_sync.context_cache instead.",
    DeprecationWarning,
    stacklevel=2,
)
from langgraph_engine.level1_sync.context_cache import *  # noqa: E402, F401, F403
