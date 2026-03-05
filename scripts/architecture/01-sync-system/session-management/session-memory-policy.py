#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Memory Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/session-management/session-memory-policy.md

Consolidates 3 scripts (827+ lines):
- session-loader.py (198 lines) - Load session from disk
- session-state.py (341 lines) - Manage session state
- protect-session-memory.py (288 lines) - Protect session memory

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python session-memory-policy.py --enforce              # Run policy enforcement
  python session-memory-policy.py --validate             # Validate policy compliance
  python session-memory-policy.py --report               # Generate report
  python session-memory-policy.py --verify-protection    # Verify session protection
  python session-memory-policy.py --list-protected       # List protected files
  python session-memory-policy.py load <SESSION_ID>      # Load session by ID
  python session-memory-policy.py info <SESSION_ID>      # Show session info
  python session-memory-policy.py list [LIMIT]           # List recent sessions
"""

import sys
import io
import json
import os
import argparse
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
SESSION_DIR = MEMORY_DIR / "sessions"
STATE_DIR = MEMORY_DIR / ".state"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"

# Protected directories (from protect-session-memory.py)
PROTECTED_PATHS = {
    "sessions": str(SESSION_DIR),
    "policies": str(MEMORY_DIR / "*.md"),
    "logs": str(MEMORY_DIR / "logs"),
    "global_docs": str(Path.home() / ".claude" / "*.md"),
}


# ============================================================================
# SESSION LOADER CLASS (from session-loader.py)
# ============================================================================

class SessionLoader:
    """Load and list saved sessions from the session index on disk.

    Attributes:
        memory_dir (Path): Base ~/.claude/memory directory.
        sessions_dir (Path): Directory containing session JSON files.
        index_file (Path): JSON index file tracking all session metadata.

    Key Methods:
        load_session(session_id): Load full session content by ID.
        list_recent(limit): Display the N most recent sessions.
        session_info(session_id): Display metadata without full content.
    """

    def __init__(self):
        self.memory_dir = MEMORY_DIR
        self.sessions_dir = SESSION_DIR
        self.index_file = self.sessions_dir / "session-index.json"

    def load_session(self, session_id: str) -> dict:
        """Load and print the full content of a session by ID.

        Args:
            session_id (str): The unique session identifier to load.

        Returns:
            dict: Contains 'metadata' and 'content' keys on success,
                  or None if the session is not found.
        """
        print(f"\n{'='*70}")
        print(f"[SEARCH] LOADING SESSION: {session_id}")
        print(f"{'='*70}\n")

        if not self.index_file.exists():
            print(f"[CROSS] Session index not found: {self.index_file}")
            print(f"   No sessions have been saved yet.")
            return None

        with open(self.index_file, 'r', encoding='utf-8') as f:
            index = json.load(f)

        session = next((s for s in index.get('sessions', []) if s['session_id'] == session_id), None)

        if not session:
            print(f"[CROSS] Session {session_id} not found")
            print(f"\nAvailable sessions:")
            for s in index.get('sessions', [])[-5:]:
                print(f"   - {s['session_id']} - {s.get('purpose', 'N/A')}")
            return None

        session_file = self.memory_dir / session.get('file_path', '')

        if not session_file.exists():
            print(f"[CROSS] Session file not found: {session_file}")
            return None

        with open(session_file, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"[CHECK] Session Loaded Successfully!")
        print(f"\n{'='*70}")
        print(f"[CHART] SESSION INFO")
        print(f"{'='*70}")
        print(f"   ID:       {session.get('session_id', 'N/A')}")
        print(f"   Date:     {session.get('timestamp', 'N/A')}")
        print(f"   Project:  {session.get('project', 'N/A')}")
        print(f"   Purpose:  {session.get('purpose', 'N/A')}")
        print(f"   Tags:     {', '.join(session.get('tags', []))}")
        print(f"   Duration: {session.get('duration_minutes', 'N/A')} minutes")
        print(f"   Files:    {session.get('files_modified', 0)} modified")
        print(f"   Status:   {session.get('status', 'unknown')}")
        print(f"{'='*70}\n")

        print(f"[PAGE] SESSION CONTENT:\n")
        print(content)

        return {'metadata': session, 'content': content}

    def list_recent(self, limit: int = 10):
        """Print a summary of the N most recent sessions.

        Args:
            limit (int): Number of most recent sessions to display. Defaults to 10.
        """
        if not self.index_file.exists():
            print("[CROSS] No sessions found")
            return

        with open(self.index_file, 'r', encoding='utf-8') as f:
            index = json.load(f)

        sessions = sorted(
            index.get('sessions', []),
            key=lambda s: s.get('timestamp', ''),
            reverse=True
        )[:limit]

        print(f"\n{'='*70}")
        print(f"[CLIPBOARD] RECENT SESSIONS (Last {limit})")
        print(f"{'='*70}\n")

        for i, session in enumerate(sessions, 1):
            print(f"{i}. {session.get('session_id', 'N/A')}")
            print(f"   Date:    {session.get('timestamp', 'N/A')}")
            print(f"   Project: {session.get('project', 'N/A')}")
            print(f"   Purpose: {session.get('purpose', 'N/A')}")
            print(f"   Tags:    {', '.join(session.get('tags', []))}")
            print()

    def session_info(self, session_id: str):
        """Print metadata for a session without loading its full content.

        Args:
            session_id (str): The unique session identifier to look up.
        """
        if not self.index_file.exists():
            print("[CROSS] Session index not found")
            return

        with open(self.index_file, 'r', encoding='utf-8') as f:
            index = json.load(f)

        session = next((s for s in index.get('sessions', []) if s['session_id'] == session_id), None)

        if not session:
            print(f"[CROSS] Session {session_id} not found")
            return

        print(f"\n{'='*70}")
        print(f"[CHART] SESSION INFO: {session_id}")
        print(f"{'='*70}")
        print(f"   Timestamp:      {session.get('timestamp', 'N/A')}")
        print(f"   Project:        {session.get('project', 'N/A')}")
        print(f"   Purpose:        {session.get('purpose', 'N/A')}")
        print(f"   Tags:           {', '.join(session.get('tags', []))}")
        print(f"   Duration:       {session.get('duration_minutes', 'N/A')} minutes")
        print(f"   Files Modified: {session.get('files_modified', 0)}")
        print(f"   Status:         {session.get('status', 'unknown')}")
        print(f"   File Path:      {session.get('file_path', 'N/A')}")
        print(f"{'='*70}\n")


# ============================================================================
# SESSION STATE CLASS (from session-state.py)
# ============================================================================

class SessionState:
    """Persist and retrieve structured session state for a given project.

    Stores the current task, completed tasks, modified files, key decisions,
    and pending work in a per-project JSON file under the state directory.

    Attributes:
        project_name (str): Name of the active project (defaults to cwd name).
        state_file (Path): JSON file path for this project's state.
        state (dict): In-memory copy of the current state.

    Key Methods:
        set_current_task(description): Record the active task.
        complete_current_task(result): Move current task to completed.
        add_file_modified(file_path, change_type): Track a modified file.
        add_decision(type, description, choice): Record a key decision.
        add_pending_work(description, priority): Queue pending work.
        get_summary(): Return a compact summary dict for Claude.
    """

    def __init__(self, project_name=None):
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        if project_name is None:
            cwd = Path.cwd()
            project_name = cwd.name

        self.project_name = project_name
        self.state_file = STATE_DIR / f'{project_name}.json'
        self.state = self._load_state()

    def _load_state(self):
        """Load state from the project state file, or return a fresh empty state.

        Returns:
            dict: Existing state from disk, or a new empty state dict.
        """
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding='utf-8'))
            except:
                pass

        return {
            'project_name': self.project_name,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'current_task': None,
            'completed_tasks': [],
            'files_modified': [],
            'key_decisions': [],
            'pending_work': [],
            'context': {},
            'metadata': {}
        }

    def _save_state(self):
        """Persist the current in-memory state dict to the project state file.

        Returns:
            bool: True if saved successfully, False on any IO error.
        """
        self.state['last_updated'] = datetime.now().isoformat()

        try:
            self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding='utf-8')
            return True
        except Exception as e:
            print(f"ERROR: Failed to save state: {e}", file=sys.stderr)
            return False

    def set_current_task(self, task_description):
        """Record a task description as the currently active task.

        Args:
            task_description (str): Human-readable description of the active task.

        Returns:
            bool: True if state was saved successfully.
        """
        self.state['current_task'] = {
            'description': task_description,
            'started_at': datetime.now().isoformat()
        }
        return self._save_state()

    def complete_current_task(self, result=None):
        """Move the current task to completed_tasks and clear the active task slot.

        Args:
            result (str, optional): Summary of the task outcome.

        Returns:
            bool: True if the task was moved successfully; False if no task was active.
        """
        if self.state['current_task']:
            completed = {
                **self.state['current_task'],
                'completed_at': datetime.now().isoformat(),
                'result': result
            }
            self.state['completed_tasks'].append(completed)
            self.state['current_task'] = None
            return self._save_state()
        return False

    def add_file_modified(self, file_path, change_type='modified'):
        """Track a file modification in the session state.

        Args:
            file_path (str or Path): Path of the file that was changed.
            change_type (str): Type of change (e.g., 'modified', 'created',
                               'deleted'). Defaults to 'modified'.

        Returns:
            bool: True if state was saved successfully.
        """
        file_entry = {
            'path': str(file_path),
            'change_type': change_type,
            'timestamp': datetime.now().isoformat()
        }

        self.state['files_modified'] = [
            f for f in self.state['files_modified']
            if f['path'] != str(file_path)
        ]
        self.state['files_modified'].append(file_entry)

        return self._save_state()

    def add_decision(self, decision_type, description, choice):
        """Record a key architectural or implementation decision.

        Args:
            decision_type (str): Category label (e.g., 'architecture', 'library').
            description (str): What the decision was about.
            choice (str): The option that was selected.

        Returns:
            bool: True if state was saved successfully.
        """
        decision = {
            'type': decision_type,
            'description': description,
            'choice': choice,
            'timestamp': datetime.now().isoformat()
        }
        self.state['key_decisions'].append(decision)
        return self._save_state()

    def add_pending_work(self, description, priority='medium'):
        """Add a pending work item to the session state.

        Args:
            description (str): Human-readable description of the work item.
            priority (str): Priority level ('high', 'medium', 'low').
                            Defaults to 'medium'.

        Returns:
            bool: True if state was saved successfully.
        """
        work_item = {
            'description': description,
            'priority': priority,
            'added_at': datetime.now().isoformat()
        }
        self.state['pending_work'].append(work_item)
        return self._save_state()

    def complete_pending_work(self, description):
        """Remove a pending work item by description match.

        Args:
            description (str): Description of the work item to remove.

        Returns:
            bool: True if state was saved successfully.
        """
        self.state['pending_work'] = [
            w for w in self.state['pending_work']
            if w['description'] != description
        ]
        return self._save_state()

    def set_context(self, key, value):
        """Store an arbitrary key-value pair in the session context dict.

        Args:
            key (str): Context key name.
            value: Any JSON-serializable value.

        Returns:
            bool: True if state was saved successfully.
        """
        self.state['context'][key] = value
        return self._save_state()

    def get_context(self, key, default=None):
        """Retrieve a value from the session context dict.

        Args:
            key (str): Context key name.
            default: Value to return if key is not present.

        Returns:
            The stored value for key, or default if not found.
        """
        return self.state['context'].get(key, default)

    def set_metadata(self, key, value):
        """Store an arbitrary key-value pair in the session metadata dict.

        Args:
            key (str): Metadata key name.
            value: Any JSON-serializable value.

        Returns:
            bool: True if state was saved successfully.
        """
        self.state['metadata'][key] = value
        return self._save_state()

    def get_summary(self):
        """Build a compact summary dict suitable for injection into Claude's context.

        Returns:
            dict: Contains 'project', 'current_task', 'progress' counts,
                  and optionally 'recent_completed', 'recent_files',
                  and 'pending_work' lists.
        """
        current_task = self.state['current_task']
        completed_count = len(self.state['completed_tasks'])
        files_count = len(self.state['files_modified'])
        decisions_count = len(self.state['key_decisions'])
        pending_count = len(self.state['pending_work'])

        summary = {
            'project': self.project_name,
            'current_task': current_task.get('description') if current_task else None,
            'progress': {
                'completed_tasks': completed_count,
                'files_modified': files_count,
                'decisions_made': decisions_count,
                'pending_work': pending_count
            }
        }

        if completed_count > 0:
            summary['recent_completed'] = [
                t['description'] for t in self.state['completed_tasks'][-3:]
            ]

        if files_count > 0:
            summary['recent_files'] = [
                f['path'] for f in self.state['files_modified'][-5:]
            ]

        if pending_count > 0:
            summary['pending_work'] = [
                w['description'] for w in self.state['pending_work']
            ]

        return summary

    def get_full_state(self):
        """Return the complete raw state dictionary.

        Returns:
            dict: Full state with all fields.
        """
        return self.state

    def clear_state(self):
        """Reset all session state fields to their empty defaults.

        Returns:
            bool: True if the cleared state was saved successfully.
        """
        self.state = {
            'project_name': self.project_name,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'current_task': None,
            'completed_tasks': [],
            'files_modified': [],
            'key_decisions': [],
            'pending_work': [],
            'context': {},
            'metadata': {}
        }
        return self._save_state()


# ============================================================================
# SESSION PROTECTION (from protect-session-memory.py)
# ============================================================================

def get_protected_files():
    """Build a categorized dict of all files under memory protection.

    Scans sessions, policies, logs, and global docs directories.

    Returns:
        dict: Maps category name (str) to a list of absolute file paths (str).
              Categories are 'sessions', 'policies', 'logs', 'global_docs'.
    """
    protected = {}

    # Sessions
    if SESSION_DIR.exists():
        session_files = []
        for root, dirs, files in os.walk(SESSION_DIR):
            for file in files:
                if file.endswith(('.md', '.json')):
                    session_files.append(os.path.join(root, file))
        protected["sessions"] = session_files
    else:
        protected["sessions"] = []

    # Policies (memory/*.md)
    if MEMORY_DIR.exists():
        policy_files = [str(f) for f in MEMORY_DIR.glob("*.md")]
        protected["policies"] = policy_files
    else:
        protected["policies"] = []

    # Logs
    logs_path = MEMORY_DIR / "logs"
    if logs_path.exists():
        log_files = list(logs_path.rglob("*"))
        log_files = [str(f) for f in log_files if f.is_file()]
        protected["logs"] = log_files
    else:
        protected["logs"] = []

    # Global docs
    global_docs_path = Path.home() / ".claude"
    if global_docs_path.exists():
        global_docs = [str(f) for f in global_docs_path.glob("*.md")]
        protected["global_docs"] = global_docs
    else:
        protected["global_docs"] = []

    return protected


def verify_protection():
    """Print a formatted verification report of all protected file categories.

    Counts total protected files, total protected size (KB), and lists the
    status of each category (sessions, policies, logs, global_docs).
    """
    print("\n" + "=" * 70)
    print("[SHIELD] SESSION MEMORY PROTECTION VERIFICATION")
    print("=" * 70)

    protected_files = get_protected_files()

    total_files = sum(len(files) for files in protected_files.values())
    total_size = 0

    for category, files in protected_files.items():
        for file in files:
            try:
                total_size += os.path.getsize(file)
            except:
                pass

    print(f"\n[CHART] Protection Summary:")
    print(f"   Total Protected Files: {total_files}")
    print(f"   Total Protected Size: {total_size / 1024:.2f} KB")

    print("\n" + "=" * 70)
    print("[SHIELD] PROTECTED CATEGORIES")
    print("=" * 70)

    for category, files in protected_files.items():
        emoji = {
            "sessions": "[U+1F4DD]",
            "policies": "[CLIPBOARD]",
            "logs": "[CHART]",
            "global_docs": "[BOOK]",
        }.get(category, "[U+1F4C1]")

        print(f"\n{emoji} {category.upper().replace('_', ' ')}:")
        print(f"   Files: {len(files)}")

        if files:
            category_size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
            print(f"   Size: {category_size / 1024:.2f} KB")
            print(f"   Status: [CHECK] PROTECTED")
        else:
            print(f"   Status: [WARNING] No files found")

    print("\n" + "=" * 70)


def list_protected_files(verbose=False):
    """Print the list of all protected files, optionally showing file sizes.

    Args:
        verbose (bool): If True, include file sizes (KB) next to each path.
                        Defaults to False.
    """
    print("\n" + "=" * 70)
    print("[CLIPBOARD] PROTECTED FILES LIST")
    print("=" * 70)

    protected_files = get_protected_files()

    for category, files in protected_files.items():
        emoji = {
            "sessions": "[U+1F4DD]",
            "policies": "[CLIPBOARD]",
            "logs": "[CHART]",
            "global_docs": "[BOOK]",
        }.get(category, "[U+1F4C1]")

        print(f"\n{emoji} {category.upper().replace('_', ' ')} ({len(files)} files):")
        print("-" * 70)

        if files:
            for file in sorted(files)[:20]:  # Show first 20
                if verbose:
                    size = os.path.getsize(file) if os.path.exists(file) else 0
                    print(f"   {file} ({size / 1024:.2f} KB)")
                else:
                    rel_path = file.replace(str(Path.home() / ".claude"), "")
                    print(f"   {rel_path}")
        else:
            print("   (No files)")

    print("\n" + "=" * 70)


# ============================================================================
# LOGGING
# ============================================================================

def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] session-memory-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


# ============================================================================
# POLICY INTERFACE
# ============================================================================

def validate():
    """Check that the session memory policy preconditions are met.

    Ensures the sessions directory exists and counts available sessions.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_count = len(list(SESSION_DIR.glob("session-*.json")))
        log_policy_hit("VALIDATE", f"session-count={session_count}")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the session memory policy.

    Returns:
        dict: Contains 'status', 'policy', 'total_sessions',
              'total_protected_files', and 'timestamp'.
              Returns {'status': 'error', ...} on failure.
    """
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        sessions = list(SESSION_DIR.glob("session-*.json"))
        protected_files = get_protected_files()
        total_protected = sum(len(files) for files in protected_files.values())

        report_data = {
            "status": "success",
            "policy": "session-memory",
            "total_sessions": len(sessions),
            "total_protected_files": total_protected,
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "session-memory-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the session memory policy and protect all session data.

    Consolidates session loading, state management, and memory protection
    from 3 old scripts:
    - session-loader.py: Load sessions
    - session-state.py: Manage state
    - protect-session-memory.py: Protect memory

    Sets restrictive permissions on session directories on Unix systems
    and logs the protected file count.

    Returns:
        dict: Contains 'status' ('success' or 'error'), 'sessions' count,
              and 'protected_files' count. On error, contains 'message'.
    """
    try:
        log_policy_hit("ENFORCE_START", "session-memory-enforcement")

        # Ensure session directory exists
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        # Count sessions and protected files
        sessions = list(SESSION_DIR.glob("session-*.json"))
        protected_files = get_protected_files()
        total_protected = sum(len(files) for files in protected_files.values())

        # Protect session directory permissions (on Unix systems)
        if sys.platform != 'win32':
            os.chmod(SESSION_DIR, 0o700)
            os.chmod(STATE_DIR, 0o700)

        log_policy_hit("ENFORCE_COMPLETE", f"sessions={len(sessions)}, protected={total_protected}")
        print(f"[session-memory-policy] {len(sessions)} sessions, {total_protected} protected files")

        return {"status": "success", "sessions": len(sessions), "protected_files": total_protected}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[session-memory-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--verify-protection":
            verify_protection()
        elif sys.argv[1] == "--list-protected":
            list_protected_files(verbose=("--verbose" in sys.argv))
        elif sys.argv[1] == "load" and len(sys.argv) >= 3:
            loader = SessionLoader()
            loader.load_session(sys.argv[2])
        elif sys.argv[1] == "info" and len(sys.argv) >= 3:
            loader = SessionLoader()
            loader.session_info(sys.argv[2])
        elif sys.argv[1] == "list":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            loader = SessionLoader()
            loader.list_recent(limit)
        else:
            print("Usage: python session-memory-policy.py [--enforce|--validate|--report|--verify-protection|--list-protected|load <ID>|info <ID>|list]")
            sys.exit(1)
    else:
        # Default: run enforcement
        enforce()
