"""Per-project session file resolution for multi-window isolation.

When multiple Claude Code windows work on different projects simultaneously,
each window needs its own session file to avoid cross-window contamination.

This module provides a single function that returns the project-specific
session file path based on CWD hash:
    ~/.claude/memory/.current-session-{cwd_hash}.json

All hooks within one window share the same CWD (project directory),
so they all resolve to the same file. Different projects get different files.

Usage:
    from project_session import get_project_session_file
    session_file = get_project_session_file()
"""

import os
import hashlib
from pathlib import Path

MEMORY_BASE = Path.home() / '.claude' / 'memory'


def _cwd_hash():
    """Return 8-char hex hash of normalized CWD for project isolation."""
    cwd = os.path.normpath(os.getcwd())
    return hashlib.md5(cwd.encode('utf-8')).hexdigest()[:8]


def get_project_session_file():
    """Return per-project session file path.

    Returns:
        Path: ~/.claude/memory/.current-session-{cwd_hash}.json
    """
    return MEMORY_BASE / f'.current-session-{_cwd_hash()}.json'


def get_legacy_session_file():
    """Return the legacy global session file path (backward compat).

    Returns:
        Path: ~/.claude/memory/.current-session.json
    """
    return MEMORY_BASE / '.current-session.json'


def read_session_id():
    """Read session ID from per-project file, falling back to legacy global.

    Returns:
        str: Session ID or empty string if not found.
    """
    for session_file in [get_project_session_file(), get_legacy_session_file()]:
        try:
            if session_file.exists():
                import json
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sid = data.get('current_session_id', '')
                if sid and sid.startswith('SESSION-'):
                    return sid
        except Exception:
            pass
    return ''
