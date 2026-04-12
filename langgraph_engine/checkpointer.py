"""
Checkpointer - Session persistence and recovery for LangGraph flows.

LangGraph's checkpointing system enables:
- Session continuity: Pause and resume flows with full state retention
- Failure recovery: If hook crashes mid-way, resume from last checkpoint
- Audit trail: All state transitions recorded for debugging

This module configures both in-memory (development) and persistent
(production) checkpointers using SqliteSaver for disk-based persistence.
"""

import sqlite3
from pathlib import Path
from typing import Optional

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _CHECKPOINTER_DATA_DIR = get_claude_home() / "memory"
except ImportError:
    _CHECKPOINTER_DATA_DIR = Path.home() / ".claude" / "memory"

try:
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        from langgraph.checkpoint import MemorySaver

    _MEMORY_SAVER_AVAILABLE = True
except ImportError:
    _MEMORY_SAVER_AVAILABLE = False

    class MemorySaver:  # type: ignore
        """Stub when LangGraph unavailable."""

        pass


# Try multiple import paths for SqliteSaver (API changed across versions)
_SQLITE_SAVER_AVAILABLE = False
_SqliteSaverClass = None

try:
    from langgraph.checkpoint.sqlite import SqliteSaver as _SqliteSaverImport

    _SqliteSaverClass = _SqliteSaverImport
    _SQLITE_SAVER_AVAILABLE = True
except ImportError:
    pass

if not _SQLITE_SAVER_AVAILABLE:
    try:
        from langgraph_checkpoint_sqlite import SqliteSaver as _SqliteSaverImport2

        _SqliteSaverClass = _SqliteSaverImport2
        _SQLITE_SAVER_AVAILABLE = True
    except ImportError:
        pass

_LANGGRAPH_AVAILABLE = _MEMORY_SAVER_AVAILABLE


def _create_sqlite_saver(db_path: str):
    """Create SqliteSaver with correct API for installed version."""
    if not _SQLITE_SAVER_AVAILABLE or _SqliteSaverClass is None:
        raise ImportError("langgraph-checkpoint-sqlite not installed")

    # Try from_conn_string first (newer API), then direct constructor
    if hasattr(_SqliteSaverClass, "from_conn_string"):
        return _SqliteSaverClass.from_conn_string(db_path)
    else:
        return _SqliteSaverClass(db_path)


class CheckpointerManager:
    """Manager for selecting and configuring checkpointers.

    Provides a factory pattern to get appropriate checkpointer based on
    environment and configuration.
    """

    @staticmethod
    def get_memory_checkpointer() -> MemorySaver:
        """Get in-memory checkpointer for development.

        In-memory checkpointing is fast but not persistent.
        State is lost if process terminates.

        Returns:
            MemorySaver instance
        """
        if not _LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not installed. Run: pip install langgraph")
        return MemorySaver()

    @staticmethod
    def get_sqlite_checkpointer(
        db_path: Optional[Path] = None,
    ):
        """Get SQLite-backed checkpointer for production.

        SQLite checkpointer persists all state changes to disk,
        enabling full recovery if process crashes.

        Args:
            db_path: Path to SQLite database file.
                    Defaults to ~/.claude/memory/langgraph-checkpoints.db

        Returns:
            SqliteSaver instance (or MemorySaver as fallback)
        """
        if not _LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not installed. Run: pip install langgraph")

        if db_path is None:
            db_path = _CHECKPOINTER_DATA_DIR / "langgraph-checkpoints.db"

        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            return _create_sqlite_saver(str(db_path))
        except (ImportError, Exception):
            # Fallback to MemorySaver if SqliteSaver unavailable
            return MemorySaver()

    @staticmethod
    def get_default_checkpointer(
        use_sqlite: bool = True,
        db_path: Optional[Path] = None,
    ):
        """Get default checkpointer based on configuration.

        Args:
            use_sqlite: If True, use SQLite (persistent). If False, use MemorySaver.
            db_path: Path to SQLite db (only used if use_sqlite=True)

        Returns:
            Checkpointer instance (MemorySaver or SqliteSaver)
        """
        if not _LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not installed. Run: pip install langgraph")

        if use_sqlite:
            return CheckpointerManager.get_sqlite_checkpointer(db_path)
        else:
            return CheckpointerManager.get_memory_checkpointer()

    @staticmethod
    def setup_checkpoint_db(
        db_path: Optional[Path] = None,
    ) -> bool:
        """Set up and verify SQLite checkpoint database.

        Args:
            db_path: Path to database file

        Returns:
            True if successful, False if failed
        """
        if db_path is None:
            db_path = _CHECKPOINTER_DATA_DIR / "langgraph-checkpoints.db"

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            print(f"Warning: Failed to setup checkpoint DB: {e}")
            return False

    @staticmethod
    def get_checkpoint_info(db_path: Optional[Path] = None) -> dict:
        """Get info about stored checkpoints.

        Args:
            db_path: Path to database file

        Returns:
            Dict with checkpoint statistics
        """
        if db_path is None:
            db_path = _CHECKPOINTER_DATA_DIR / "langgraph-checkpoints.db"

        try:
            if not db_path.exists():
                return {"exists": False, "threads": 0, "checkpoints": 0}

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Count checkpoints (table name varies by version)
            checkpoint_count = 0
            thread_count = 0
            for table in ["checkpoints", "checkpoint"]:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    checkpoint_count = cursor.fetchone()[0]
                    cursor.execute(f"SELECT COUNT(DISTINCT thread_id) FROM {table}")
                    thread_count = cursor.fetchone()[0]
                    break
                except sqlite3.OperationalError:
                    continue

            db_size = db_path.stat().st_size
            conn.close()

            return {
                "exists": True,
                "db_path": str(db_path),
                "db_size_kb": round(db_size / 1024, 1),
                "threads": thread_count,
                "checkpoints": checkpoint_count,
                "sqlite_available": _SQLITE_SAVER_AVAILABLE,
            }
        except Exception as e:
            return {"exists": False, "error": str(e)}


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================


def get_checkpointer_config() -> dict:
    """Get checkpointer configuration for StateGraph.

    Returns dict suitable for passing to graph.compile(checkpointer=...).

    Returns:
        Dict with "checkpointer" key
    """
    checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
    return {"checkpointer": checkpointer}


def get_invoke_config(session_id: str) -> dict:
    """Get invoke configuration for running graph.

    Args:
        session_id: Unique session identifier

    Returns:
        Dict with "configurable" and "recursion_limit" keys for graph.invoke()
    """
    return {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 1000,  # High limit for complex 3-level graph
    }
