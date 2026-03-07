#!/usr/bin/env python
"""Session ID generator and session lifecycle manager.

Generates unique, human-readable session IDs used to correlate log entries,
policy enforcement events, and work items across a single Claude Code session.

ID format::

    TYPE-YYYYMMDD-HHMMSS-XXXX

    Examples:
        SESSION-20260216-143055-A7B3
        TASK-20260216-143100-Z9Q2

Components:
    TYPE     -- Caller-supplied prefix (e.g. 'SESSION', 'TASK', 'WORK').
    YYYYMMDD -- Date stamp for rapid visual identification.
    HHMMSS   -- Time stamp for ordering within a day.
    XXXX     -- 4-character random alphanumeric suffix to avoid collisions
                when multiple IDs are generated within the same second.

Session state is persisted to JSON files under ``~/.claude/memory/sessions/``
and the active session is tracked via ``~/.claude/memory/.current-session.json``.

CLI usage::

    python session-id-generator.py create --type SESSION --description "My session"
    python session-id-generator.py current
    python session-id-generator.py list --limit 5
    python session-id-generator.py stats --session-id SESSION-20260216-143055-A7B3
    python session-id-generator.py end

Windows-safe: reconfigures stdout/stderr to UTF-8 on startup.

Version: 1.0.0
Last Modified: 2026-02-16
Author: Claude Memory System
"""

import os
import sys
import json
import hashlib
import random
import string
from datetime import datetime
from pathlib import Path

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False
    print("[WARN] Policy tracking not available - continuing without tracking")

class SessionIDGenerator:
    """Generates and manages Claude Code session IDs and lifecycle state.

    Persists session metadata as JSON files under ``~/.claude/memory/sessions/``
    and maintains a pointer to the currently active session in
    ``~/.claude/memory/.current-session.json``.

    Attributes:
        memory_path: Base path to the Claude memory directory.
        sessions_dir: Directory containing per-session JSON files.
        current_session_file: JSON file tracking the active session ID.
        sessions_log: Append-only log of session lifecycle events.

    Example::

        gen = SessionIDGenerator()
        sid, data = gen.create_session('SESSION', 'Fixing login bug')
        work_id = gen.add_work_item(sid, 'TASK', 'Update auth module')
        gen.complete_work_item(sid, work_id)
        gen.end_session(sid)
    """

    def __init__(self):
        """Initialise paths and create required directories if absent."""
        self.memory_path = Path.home() / '.claude' / 'memory'
        self.sessions_dir = self.memory_path / 'sessions'
        # Per-project session file for multi-window isolation
        try:
            from project_session import get_project_session_file
            self.current_session_file = get_project_session_file()
        except ImportError:
            self.current_session_file = self.memory_path / '.current-session.json'
        self.sessions_log = self.memory_path / 'logs' / 'sessions.log'

        # Ensure directories exist
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_log.parent.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self, session_type: str = 'SESSION') -> str:
        """Generate a unique session ID with the given type prefix.

        Args:
            session_type: Prefix for the ID (e.g. 'SESSION', 'TASK').
                Defaults to 'SESSION'.

        Returns:
            ID string in the format ``TYPE-YYYYMMDD-HHMMSS-XXXX``.
        """
        now = datetime.now()

        # Format: TYPE-YYYYMMDD-HHMMSS-XXXX
        date_part = now.strftime('%Y%m%d')
        time_part = now.strftime('%H%M%S')

        # Random 4-char hash
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

        session_id = f"{session_type}-{date_part}-{time_part}-{random_chars}"

        return session_id

    def create_session(self, session_type: str = 'SESSION',
                       description: str = '', metadata: dict = None) -> tuple:
        """Create a new session, persist it, and set it as current.

        Args:
            session_type: Prefix for the generated ID. Defaults to 'SESSION'.
            description: Human-readable description of the session purpose.
            metadata: Optional dict of additional fields to store with the
                session (e.g. project name, branch, git hash).

        Returns:
            Tuple of ``(session_id, session_data)`` where ``session_data``
            is the full dict written to disk.
        """
        # ===================================================================
        # TRACKING: Record start time
        # ===================================================================
        _track_start_time = datetime.now()

        session_id = self.generate_session_id(session_type)

        session_data = {
            'session_id': session_id,
            'type': session_type,
            'description': description,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'status': 'ACTIVE',
            'metadata': metadata or {},
            'tasks': [],
            'work_items': []
        }

        try:
            # Save session data
            session_file = self.sessions_dir / f'{session_id}.json'
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)

            # Update current session
            with open(self.current_session_file, 'w') as f:
                json.dump({
                    'current_session_id': session_id,
                    'started_at': datetime.now().isoformat()
                }, f, indent=2)

            # Log session
            self._log_session(session_id, 'CREATED', description)

            # ===================================================================
            # TRACKING: Record execution
            # ===================================================================
            if HAS_TRACKING:
                _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
                record_policy_execution(
                    session_id=session_id,
                    policy_name="session-id-generator",
                    policy_script="session-id-generator.py",
                    policy_type="Utility Hook",
                    input_params={
                        "session_type": session_type,
                        "description": description,
                        "metadata": metadata or {}
                    },
                    output_results={
                        "session_id": session_id,
                        "session_is_new": True,
                        "status": "ACTIVE"
                    },
                    decision=f"Created new session {session_type}",
                    duration_ms=_duration_ms
                )

            return session_id, session_data

        except Exception as e:
            # ===================================================================
            # TRACKING: Record error
            # ===================================================================
            if HAS_TRACKING:
                _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
                record_policy_execution(
                    session_id="unknown",
                    policy_name="session-id-generator",
                    policy_script="session-id-generator.py",
                    policy_type="Utility Hook",
                    input_params={
                        "session_type": session_type,
                        "description": description
                    },
                    output_results={"status": "ERROR", "error": str(e)},
                    decision=f"Failed to create session: {e}",
                    duration_ms=_duration_ms
                )
            raise

    def get_current_session(self) -> str:
        """Return the ID of the currently active session, or None.

        Returns:
            Session ID string if a current session file exists and is
            readable, otherwise ``None``.
        """
        if not self.current_session_file.exists():
            return None

        try:
            with open(self.current_session_file, 'r') as f:
                data = json.load(f)
                return data.get('current_session_id')
        except:
            return None

    def get_session_data(self, session_id: str) -> dict:
        """Load and return session data for the given session ID.

        Args:
            session_id: The session ID string to look up.

        Returns:
            Session data dict loaded from disk, or ``None`` if the session
            file does not exist or cannot be parsed.
        """
        session_file = self.sessions_dir / f'{session_id}.json'
        if not session_file.exists():
            return None

        try:
            with open(session_file, 'r') as f:
                return json.load(f)
        except:
            return None

    def add_work_item(self, session_id: str, work_type: str,
                      description: str, metadata: dict = None) -> str:
        """Add a work item to an existing session and return its ID.

        Args:
            session_id: ID of the session to add the work item to.
            work_type: Prefix for the work item ID (e.g. 'TASK', 'WORK').
            description: Human-readable description of the work item.
            metadata: Optional dict of additional fields for the work item.

        Returns:
            Generated work item ID string, or empty string if the session
            was not found.
        """
        work_id = self.generate_session_id(work_type)

        work_item = {
            'work_id': work_id,
            'type': work_type,
            'description': description,
            'started_at': datetime.now().isoformat(),
            'completed_at': None,
            'status': 'IN_PROGRESS',
            'metadata': metadata or {}
        }

        # Update session
        session_data = self.get_session_data(session_id)
        if session_data:
            session_data['work_items'].append(work_item)

            session_file = self.sessions_dir / f'{session_id}.json'
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)

            self._log_session(session_id, 'WORK_ADDED', f'{work_type}: {description}')

        return work_id

    def complete_work_item(self, session_id: str, work_id: str,
                           status: str = 'COMPLETED') -> bool:
        """Mark a work item as completed and persist the change.

        Args:
            session_id: ID of the parent session.
            work_id: ID of the work item to update.
            status: Completion status string. Defaults to 'COMPLETED'.

        Returns:
            ``True`` if the work item was found and updated, ``False``
            if the session or work item was not found.
        """
        session_data = self.get_session_data(session_id)
        if not session_data:
            return False

        for item in session_data['work_items']:
            if item['work_id'] == work_id:
                item['completed_at'] = datetime.now().isoformat()
                item['status'] = status
                break

        session_file = self.sessions_dir / f'{session_id}.json'
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)

        self._log_session(session_id, 'WORK_COMPLETED', work_id)
        return True

    def end_session(self, session_id: str, status: str = 'COMPLETED') -> bool:
        """End a session, persist its end time, and clear the current session pointer.

        Args:
            session_id: ID of the session to end.
            status: Final status string. Defaults to 'COMPLETED'.

        Returns:
            ``True`` if the session was found and updated, ``False`` if
            the session file was not found.
        """
        session_data = self.get_session_data(session_id)
        if not session_data:
            return False

        session_data['end_time'] = datetime.now().isoformat()
        session_data['status'] = status

        session_file = self.sessions_dir / f'{session_id}.json'
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)

        # Clear current session if it matches
        current = self.get_current_session()
        if current == session_id:
            if self.current_session_file.exists():
                self.current_session_file.unlink()

        self._log_session(session_id, 'ENDED', status)
        return True

    def display_session_banner(self, session_id: str,
                               session_data: dict = None) -> None:
        """Print a formatted session summary banner to stdout.

        Args:
            session_id: Session ID to display.
            session_data: Optional pre-loaded session data dict. If not
                provided the data is loaded from disk automatically.
        """
        if not session_data:
            session_data = self.get_session_data(session_id)

        print("\n" + "="*80)
        print("[CLIPBOARD] SESSION ID FOR TRACKING")
        print("="*80)
        print(f"\n[U+1F194] Session ID: {session_id}")

        if session_data:
            print(f"[U+1F4C5] Started: {session_data['start_time'][:19]}")
            print(f"[CHART] Status: {session_data['status']}")
            if session_data.get('description'):
                print(f"[U+1F4DD] Description: {session_data['description']}")
            if session_data.get('work_items'):
                print(f"[WRENCH] Work Items: {len(session_data['work_items'])}")

        print("\n[BULB] Use this ID to track this session in logs and reports")
        print("="*80 + "\n")

    def list_recent_sessions(self, limit: int = 10) -> list:
        """Return a list of recent session data dicts, newest first.

        Args:
            limit: Maximum number of sessions to return. Defaults to 10.

        Returns:
            List of session data dicts ordered by most-recently-modified
            session file. Unreadable files are silently skipped.
        """
        session_files = sorted(
            self.sessions_dir.glob('SESSION-*.json'),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        sessions = []
        for session_file in session_files[:limit]:
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                    sessions.append(data)
            except:
                continue

        return sessions

    def get_session_stats(self, session_id: str) -> dict:
        """Compute summary statistics for a session.

        Args:
            session_id: ID of the session to analyse.

        Returns:
            Dict with keys:
                ``session_id``              -- The queried session ID.
                ``duration_seconds``        -- Total elapsed time in seconds.
                ``duration_formatted``      -- Human-readable duration string.
                ``total_work_items``        -- Count of all work items.
                ``completed_work_items``    -- Count of completed work items.
                ``in_progress_work_items``  -- Count of items not yet done.
                ``status``                  -- Current session status string.
            Returns ``None`` if the session is not found.
        """
        session_data = self.get_session_data(session_id)
        if not session_data:
            return None

        start_time = datetime.fromisoformat(session_data['start_time'])
        end_time = datetime.fromisoformat(session_data['end_time']) if session_data.get('end_time') else datetime.now()

        duration = end_time - start_time

        work_items = session_data.get('work_items', [])
        completed_items = [w for w in work_items if w['status'] == 'COMPLETED']

        return {
            'session_id': session_id,
            'duration_seconds': duration.total_seconds(),
            'duration_formatted': str(duration).split('.')[0],
            'total_work_items': len(work_items),
            'completed_work_items': len(completed_items),
            'in_progress_work_items': len(work_items) - len(completed_items),
            'status': session_data['status']
        }

    def _log_session(self, session_id: str, event: str,
                     details: str = '') -> None:
        """Append a session lifecycle event to the sessions log file.

        Args:
            session_id: ID of the session the event belongs to.
            event: Event type string (e.g. 'CREATED', 'ENDED', 'WORK_ADDED').
            details: Optional free-text details string for the log entry.
        """
        timestamp = datetime.now().isoformat()
        log_line = f"{timestamp} | {session_id} | {event} | {details}\n"

        with open(self.sessions_log, 'a') as f:
            f.write(log_line)


def main() -> None:
    """CLI entry point for the session ID generator.

    Parses command-line arguments and dispatches to the appropriate
    ``SessionIDGenerator`` method. Prints results to stdout and exits
    with code 1 on error.

    Available actions:
        create   -- Create a new session and print its ID.
        current  -- Show the currently active session.
        display  -- Print a banner for a specific or current session.
        list     -- List recent sessions.
        stats    -- Show statistics for a specific or current session.
        end      -- End a specific or current session.
    """
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Session ID Generator')
    parser.add_argument('action', choices=['create', 'current', 'display', 'list', 'stats', 'end'],
                       help='Action to perform')
    parser.add_argument('--type', default='SESSION', help='Session type')
    parser.add_argument('--description', default='', help='Session description')
    parser.add_argument('--session-id', help='Session ID (for display/stats/end)')
    parser.add_argument('--limit', type=int, default=10, help='Limit for list')

    args = parser.parse_args()

    generator = SessionIDGenerator()

    if args.action == 'create':
        session_id, session_data = generator.create_session(
            session_type=args.type,
            description=args.description
        )
        generator.display_session_banner(session_id, session_data)
        print(session_id)  # For easy capturing in scripts

    elif args.action == 'current':
        session_id = generator.get_current_session()
        if session_id:
            print(f"Current Session: {session_id}")
            generator.display_session_banner(session_id)
        else:
            print("No active session")
            sys.exit(1)

    elif args.action == 'display':
        session_id = args.session_id or generator.get_current_session()
        if session_id:
            generator.display_session_banner(session_id)
        else:
            print("No session ID provided and no active session")
            sys.exit(1)

    elif args.action == 'list':
        sessions = generator.list_recent_sessions(args.limit)
        print(f"\n[CLIPBOARD] Recent Sessions (last {args.limit}):\n")
        for session in sessions:
            status_icon = "[CHECK]" if session['status'] == 'COMPLETED' else "[CYCLE]"
            print(f"{status_icon} {session['session_id']}")
            print(f"   Started: {session['start_time'][:19]}")
            print(f"   Status: {session['status']}")
            if session.get('description'):
                print(f"   Description: {session['description']}")
            print()

    elif args.action == 'stats':
        session_id = args.session_id or generator.get_current_session()
        if not session_id:
            print("No session ID provided and no active session")
            sys.exit(1)

        stats = generator.get_session_stats(session_id)
        if stats:
            print(f"\n[CHART] Session Statistics: {session_id}\n")
            print(f"Duration: {stats['duration_formatted']}")
            print(f"Total Work Items: {stats['total_work_items']}")
            print(f"Completed: {stats['completed_work_items']}")
            print(f"In Progress: {stats['in_progress_work_items']}")
            print(f"Status: {stats['status']}")
        else:
            print(f"Session not found: {session_id}")
            sys.exit(1)

    elif args.action == 'end':
        session_id = args.session_id or generator.get_current_session()
        if not session_id:
            print("No session ID provided and no active session")
            sys.exit(1)

        if generator.end_session(session_id):
            print(f"[CHECK] Session ended: {session_id}")
        else:
            print(f"[CROSS] Failed to end session: {session_id}")
            sys.exit(1)


if __name__ == '__main__':
    main()
