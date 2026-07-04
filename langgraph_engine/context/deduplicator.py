"""context/deduplicator.py -- re-exports from langgraph_engine.level1_sync.context_deduplicator.

All context deduplication logic lives in level1_sync/context_deduplicator.py.
This module is part of the context/ domain package.

Windows-safe: ASCII only (cp1252 compatible).
"""

from langgraph_engine.level1_sync.context_deduplicator import *  # noqa: F401, F403
from langgraph_engine.level1_sync.context_deduplicator import (  # noqa: F401
    MIN_SAVINGS_RATIO,
    PRIORITY_ORDER,
    dedup_savings_estimate,
    deduplicate_context,
)
