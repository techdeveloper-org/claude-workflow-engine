#!/usr/bin/env python3
"""Lazy Loading Session API - Keep all data, load only what needed.

Phase 2: Session metadata management + archival for old sessions.
- Load session index (metadata only)
- Archive sessions older than 7 days
- Cleanup session folder
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta

try:
    from ide_paths import MEMORY_BASE
except ImportError:
    MEMORY_BASE = Path.home() / '.claude' / 'memory'


class SessionIndex:
    """In-memory index of all sessions (NOT full data)."""

    def __init__(self):
        self.sessions_dir = MEMORY_BASE / 'sessions'
        self.index_file = MEMORY_BASE / 'logs' / 'session-index.json'
        self.projects = {}
        self._load_index()

    def _load_index(self):
        """Load session index from file."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.projects = data.get('projects', {})
                    return
            except Exception:
                pass
        self._build_index()

    def _build_index(self):
        """Build index from session folder structure."""
        if not self.sessions_dir.exists():
            return

        self.projects = {}
        for project_dir in self.sessions_dir.iterdir():
            if not project_dir.is_dir():
                continue

            project_name = project_dir.name
            session_files = list(project_dir.glob('SESSION-*.json'))
            total_size_kb = sum(f.stat().st_size for f in session_files) // 1024

            self.projects[project_name] = {
                'sessions': len(session_files),
                'total_size_kb': total_size_kb,
                'last_session': session_files[-1].name if session_files else None,
                'created': project_dir.stat().st_mtime
            }

        self._save_index()

    def _save_index(self):
        """Save index to file."""
        try:
            self.index_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': '1.0',
                    'projects': self.projects,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
        except Exception:
            pass


class SessionAPI:
    """Query API for session management."""

    def __init__(self):
        self.index = SessionIndex()
        self.sessions_dir = MEMORY_BASE / 'sessions'
        self.archive_dir = MEMORY_BASE / 'logs' / 'archive'

    def get_session_info(self, project_name):
        """Get info about a project's sessions."""
        return self.index.projects.get(project_name, {})

    def get_all_sessions(self):
        """Get all session information."""
        return self.index.projects

    def archive_old_sessions(self, days=7):
        """Archive sessions older than N days."""
        if not self.sessions_dir.exists():
            return 0

        cutoff_time = (datetime.now() - timedelta(days=days)).timestamp()
        archived_count = 0

        for project_dir in self.sessions_dir.iterdir():
            if not project_dir.is_dir():
                continue

            for session_file in project_dir.glob('SESSION-*.json'):
                if session_file.stat().st_mtime < cutoff_time:
                    self._archive_session(session_file)
                    archived_count += 1

        return archived_count

    def _archive_session(self, session_file):
        """Move session file to archive."""
        try:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = self.archive_dir / session_file.name
            session_file.rename(archive_path)
        except Exception:
            pass

    def cleanup_project_summaries(self, max_lines=100):
        """Truncate project-summary.md files to keep only last N lines."""
        if not self.sessions_dir.exists():
            return 0

        cleaned_count = 0
        for summary_file in self.sessions_dir.glob('*/project-summary.md'):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if len(lines) > max_lines:
                    # Keep last N lines only
                    with open(summary_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines[-max_lines:])
                    cleaned_count += 1
            except Exception:
                pass

        return cleaned_count


if __name__ == '__main__':
    api = SessionAPI()
    print("Sessions by project:")
    for proj, info in api.get_all_sessions().items():
        print(f"  {proj}: {info['sessions']} sessions, {info['total_size_kb']} KB")
