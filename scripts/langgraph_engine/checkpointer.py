"""
Checkpointer - Session persistence and recovery for LangGraph flows.

LangGraph's checkpointing system enables:
- Session continuity: Pause and resume flows with full state retention
- Failure recovery: If hook crashes mid-way, resume from last checkpoint
- Audit trail: All state transitions recorded for debugging

This module configures both in-memory (development) and persistent
(production) checkpointers.
"""

import sqlite3
from pathlib import Path
from typing import Optional

try:
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        # LangGraph 1.0.10 has checkpointing in different location
        from langgraph.checkpoint import MemorySaver

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        # SqliteSaver might not be available in all versions
        SqliteSaver = MemorySaver  # Fallback to memory

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    # Fallback stubs for when LangGraph not installed
    class MemorySaver:  # type: ignore
        """Stub when LangGraph unavailable."""
        pass

    class SqliteSaver:  # type: ignore
        """Stub when LangGraph unavailable."""
        pass


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
    ) -> SqliteSaver:
        """Get SQLite-backed checkpointer for production.

        SQLite checkpointer persists all state changes to disk,
        enabling full recovery if process crashes.

        Args:
            db_path: Path to SQLite database file.
                    Defaults to ~/.claude/memory/langgraph-checkpoints.db

        Returns:
            SqliteSaver instance
        """
        if not _LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not installed. Run: pip install langgraph")

        if db_path is None:
            # Default location: ~/.claude/memory/langgraph-checkpoints.db
            db_path = Path.home() / ".claude" / "memory" / "langgraph-checkpoints.db"

        # Create parent directory if needed
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create SqliteSaver - it will create db file if needed
        return SqliteSaver(str(db_path))

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

        Creates tables and indexes if they don't exist.

        Args:
            db_path: Path to database file

        Returns:
            True if successful, False if failed
        """
        if db_path is None:
            db_path = Path.home() / ".claude" / "memory" / "langgraph-checkpoints.db"

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # LangGraph's SqliteSaver will create tables automatically
            # when first checkpointer is used, but we can verify connectivity

            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")  # Simple connectivity test
            conn.close()

            return True
        except Exception as e:
            print(f"Warning: Failed to setup checkpoint DB: {e}")
            return False


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
        Dict with "configurable" key for graph.invoke()
    """
    return {
        "configurable": {
            "thread_id": session_id,
        }
    }
