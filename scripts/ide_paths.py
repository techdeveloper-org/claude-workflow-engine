#!/usr/bin/env python3
"""
ide_paths.py - Central Path Resolver for IDE Self-Contained Installations

This module provides a single source of truth for all path references used by
hook scripts, policies, and other components. It respects environment variables
set by the IDE installation system, enabling truly self-contained installations
without polluting the user's ~/.claude/ directory.

Environment Variables (set by IDE):
  CLAUDE_IDE_INSTALL_DIR  - Base directory where scripts/policies/skills/agents are stored
  CLAUDE_IDE_DATA_DIR     - Base directory where memory/logs/config are stored (optional)

Modes:
  IDE Mode (CLAUDE_IDE_INSTALL_DIR set)      -> Use IDE-specific directories
  Standalone Mode (env vars not set)         -> Use ~/.claude/ (backward compatible)

Author: Claude IDE System
Version: 1.0.0
"""

import os
from pathlib import Path

# Environment variable sources
_INSTALL_DIR_ENV = os.environ.get('CLAUDE_IDE_INSTALL_DIR', '').strip()
_DATA_DIR_ENV = os.environ.get('CLAUDE_IDE_DATA_DIR', '').strip()

# Determine mode and base directories
if _INSTALL_DIR_ENV:
    # IDE Mode: Use custom installation directories
    _INSTALL_BASE = Path(_INSTALL_DIR_ENV)
    _DATA_BASE = Path(_DATA_DIR_ENV) if _DATA_DIR_ENV else _INSTALL_BASE / 'data'
    IDE_MODE = True
else:
    # Standalone Mode: Use ~/.claude/ (backward compatible)
    _INSTALL_BASE = Path.home() / '.claude'
    _DATA_BASE = Path.home() / '.claude'
    IDE_MODE = False

# Content directories (scripts, policies, skills, agents)
SCRIPTS_DIR = _INSTALL_BASE / 'scripts'
POLICIES_DIR = _INSTALL_BASE / 'policies'
SKILLS_DIR = _INSTALL_BASE / 'skills'
AGENTS_DIR = _INSTALL_BASE / 'agents'

# Data directories (memory, logs, config, flags)
MEMORY_BASE = _DATA_BASE / 'memory'
FLAG_DIR = _DATA_BASE
CONFIG_DIR = _DATA_BASE / 'config'

# Common file paths (for session management and flags)
# Per-project session file for multi-window isolation
try:
    from project_session import get_project_session_file
    CURRENT_SESSION_FILE = get_project_session_file()
except ImportError:
    CURRENT_SESSION_FILE = MEMORY_BASE / '.current-session.json'
SESSION_STATE_FILE = MEMORY_BASE / 'logs' / 'session-progress.json'
TRACKER_LOG = MEMORY_BASE / 'logs' / 'tool-tracker.jsonl'

# Session-specific flags
SESSION_START_FLAG = FLAG_DIR / '.session-start-voice'
TASK_COMPLETE_FLAG = FLAG_DIR / '.task-complete-voice'
WORK_DONE_FLAG = FLAG_DIR / '.session-work-done'
STOP_LOG = MEMORY_BASE / 'logs' / 'stop-notifier.log'

# Current working directory (scripts directory or fallback)
CURRENT_DIR = SCRIPTS_DIR if SCRIPTS_DIR.exists() else (MEMORY_BASE / 'current')

# Policy subdirectories
POLICY_LEVELS = {
    '01-sync-system': POLICIES_DIR / '01-sync-system',
    '02-standards-system': POLICIES_DIR / '02-standards-system',
    '03-execution-system': POLICIES_DIR / '03-execution-system'
}


def create_necessary_dirs():
    """Ensure all necessary directories exist.

    This should be called early in hook script execution to ensure
    directory structure is ready for file operations.

    Returns:
        bool: True if all directories created successfully, False otherwise
    """
    try:
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        POLICIES_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_BASE.mkdir(parents=True, exist_ok=True)
        (MEMORY_BASE / 'logs').mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        FLAG_DIR.mkdir(parents=True, exist_ok=True)

        # Ensure policy subdirectories exist
        for policy_dir in POLICY_LEVELS.values():
            policy_dir.mkdir(parents=True, exist_ok=True)

        return True
    except Exception as e:
        print(f"[ERROR] Failed to create necessary directories: {e}", file=__import__('sys').stderr)
        return False


def get_install_base() -> 'Path':
    """Return the base installation directory for content files.

    In IDE mode this is the directory set by ``CLAUDE_IDE_INSTALL_DIR``.
    In standalone mode it is ``~/.claude``.

    Returns:
        ``pathlib.Path`` object for the installation base directory.
    """
    return _INSTALL_BASE


def get_data_base() -> 'Path':
    """Return the base data directory for memory and log files.

    In IDE mode this is the directory set by ``CLAUDE_IDE_DATA_DIR``
    (or ``<install_base>/data`` when that variable is unset).
    In standalone mode it is ``~/.claude``.

    Returns:
        ``pathlib.Path`` object for the data base directory.
    """
    return _DATA_BASE


def is_ide_mode() -> bool:
    """Return True if the module is running inside a Claude Code IDE installation.

    IDE mode is active when the ``CLAUDE_IDE_INSTALL_DIR`` environment
    variable is set to a non-empty value. In this mode all paths use the
    IDE-specific directories instead of ``~/.claude``.

    Returns:
        ``True`` when ``CLAUDE_IDE_INSTALL_DIR`` is set, ``False`` otherwise.
    """
    return IDE_MODE


if __name__ == '__main__':
    # Debug: print path information
    import sys
    print("ide_paths.py Path Configuration", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"IDE Mode: {IDE_MODE}", file=sys.stderr)
    print(f"Install Base: {_INSTALL_BASE}", file=sys.stderr)
    print(f"Data Base: {_DATA_BASE}", file=sys.stderr)
    print(f"Scripts Dir: {SCRIPTS_DIR}", file=sys.stderr)
    print(f"Policies Dir: {POLICIES_DIR}", file=sys.stderr)
    print(f"Memory Base: {MEMORY_BASE}", file=sys.stderr)
    print(f"Flag Dir: {FLAG_DIR}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
