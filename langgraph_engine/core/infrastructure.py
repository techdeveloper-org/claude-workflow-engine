"""Shared per-session infrastructure cache.

Extracted from langgraph_engine/level3_execution/subgraph.py where
the same pattern (_infra_cache dict + _get_infra function) existed as a
module-level private.  Moving it here makes the cache reusable across all
pipeline levels (Level -1, 1, 2, 3) without duplication.

Purpose
-------
Infrastructure objects (CheckpointManager, MetricsCollector, ErrorLogger,
BackupManager) are expensive to create and must be shared across the many node
functions that execute for a single pipeline session.  This module maintains a
module-level dict keyed by session_id so that each session gets exactly one
set of infrastructure objects.

Session ID resolution chain
---------------------------
1. state["session_id"]
2. os.environ["CURRENT_SESSION_ID"]
3. Path(state["session_path"]).name  (extracts name from the path)
4. "unknown" (fallback; avoids hard failure)

When a real session_id arrives after the cache was populated with "unknown",
the cache is upgraded so that subsequent calls use the correct infrastructure.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .lazy_loader import LazyLoader
from .logger_factory import get_logger

logger = get_logger(__name__)

# Module-level cache: session_id -> {checkpoint, metrics, error_logger, backup}
_infra_cache: Dict[str, Dict[str, Any]] = {}

# Pipeline-level timing: maps session_id -> pipeline start time (float).
# Populated by _run_step when step_number == 0 and consumed at step_number == 14
# to compute the total pipeline wall-clock duration.
_pipeline_start_times: Dict[str, float] = {}


def _create_infra_objects(session_id: str) -> Dict[str, Any]:
    """Instantiate and return a fresh set of infrastructure objects.

    All four objects are created via LazyLoader so that missing dependencies
    result in None rather than an ImportError propagating into the pipeline.

    Args:
        session_id: The pipeline session identifier passed to each constructor.

    Returns:
        Dict with keys: checkpoint, metrics, error_logger, backup.
        Any value may be None when the corresponding module is unavailable.
    """
    return {
        "checkpoint": LazyLoader.load(
            "langgraph_engine.checkpoint_manager",
            "CheckpointManager",
            session_id,
        ),
        "metrics": LazyLoader.load(
            "langgraph_engine.metrics_collector",
            "MetricsCollector",
            session_id,
        ),
        "error_logger": LazyLoader.load(
            "langgraph_engine.error_logger",
            "ErrorLogger",
            session_id=session_id,
        ),
        "backup": LazyLoader.load(
            "langgraph_engine.backup_manager",
            "BackupManager",
            session_id=session_id,
        ),
    }


def get_infra(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return (and cache) infrastructure objects for the current session.

    On the first call for a given session_id the infrastructure objects are
    created and stored in the module-level cache.  Subsequent calls for the
    same session_id return the cached objects immediately.

    The function also persists the resolved session_id to the environment
    variable CURRENT_SESSION_ID so that other pipeline components that read
    that variable stay in sync.

    Args:
        state: The current LangGraph FlowState dict.

    Returns:
        Dict with keys: checkpoint, metrics, error_logger, backup.
        Missing objects are None (degraded but non-fatal).
    """
    session_id = state.get("session_id") or os.environ.get("CURRENT_SESSION_ID", "") or ""

    # Attempt to resolve session_id from the session path when not set directly.
    if not session_id:
        session_path = state.get("session_path", "") or state.get("session_dir", "")
        if session_path:
            session_id = Path(session_path).name

    if not session_id:
        session_id = "unknown"

    # Allow upgrade from the placeholder "unknown" key to a real session_id.
    # This handles the case where get_infra() was called before Level 1 ran
    # and populated state["session_id"].
    if session_id != "unknown" and "unknown" in _infra_cache and session_id not in _infra_cache:
        _infra_cache[session_id] = _create_infra_objects(session_id)
        os.environ["CURRENT_SESSION_ID"] = session_id

    if session_id not in _infra_cache:
        _infra_cache[session_id] = _create_infra_objects(session_id)
        if session_id != "unknown":
            os.environ["CURRENT_SESSION_ID"] = session_id

    return _infra_cache[session_id]


def clear_infra_cache(session_id: Optional[str] = None) -> None:
    """Remove cached infrastructure objects.

    When session_id is provided only that session's entry is removed.
    When session_id is None the entire cache is cleared.

    Intended for use in tests and for explicit clean-up after a session
    completes to allow the infrastructure objects to be garbage-collected.

    Args:
        session_id: Session to remove, or None to clear everything.
    """
    if session_id is not None:
        _infra_cache.pop(session_id, None)
    else:
        _infra_cache.clear()
