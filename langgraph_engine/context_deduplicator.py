"""Backward-compat shim -- moved to langgraph_engine.context.deduplicator (via level1_sync)."""

import warnings as _w

_w.warn(
    "Import from langgraph_engine.context_deduplicator is deprecated. "
    "Use langgraph_engine.context.deduplicator or langgraph_engine.level1_sync.context_deduplicator instead.",
    DeprecationWarning,
    stacklevel=2,
)
from langgraph_engine.level1_sync.context_deduplicator import *  # noqa: E402, F401, F403
