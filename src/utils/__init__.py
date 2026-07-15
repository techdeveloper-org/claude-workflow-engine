"""Utils Package - Helper utilities.

Shared helper modules used across the src package. Utilities here are
framework-agnostic and contain no Flask or SocketIO dependencies so they
can be imported freely by services, routes, and scripts alike.

Modules:
    import_manager   -- Loads skills and agents from GitHub repositories
                        (claude-global-library) or from the local cache.
                        Provides ``ImportManager.get_skill()`` and
                        ``ImportManager.get_agent()`` class methods.
    path_resolver    -- Cross-platform path resolution for the memory system
                        directories. Handles Windows/Unix differences and
                        respects the ``CLAUDE_WORKFLOW_ENGINE_DATA_DIR`` env override.
    history_tracker  -- Records activity history (tool calls, sessions,
                        policy hits) into a rolling JSON log for the activity
                        feed widget.

Usage::

    from src.utils.path_resolver import PathResolver
    from src.utils.import_manager import ImportManager

    skill_content = ImportManager.get_skill('docker')
    memory_dir = PathResolver.get_memory_dir()
"""
