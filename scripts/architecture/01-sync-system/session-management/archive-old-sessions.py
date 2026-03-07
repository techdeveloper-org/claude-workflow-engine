#!/usr/bin/env python3
"""
Long-term Session Memory Pruning System
Archives old session files to keep memory clean and fast.

Strategy:
- Keep last 10 sessions active (always)
- Archive sessions older than 30 days (except last 10)
- Compress archived sessions by month
- Never archive project-summary.md (always kept)

Usage:
  python archive-old-sessions.py                    # Archive all projects
  python archive-old-sessions.py <project_name>     # Archive specific project
  python archive-old-sessions.py --dry-run          # Preview without archiving
  python archive-old-sessions.py --stats            # Show statistics only

Examples:
  python archive-old-sessions.py
  python archive-old-sessions.py techdeveloper-ui
  python archive-old-sessions.py --dry-run
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


import json
import os
import sys
import io
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Fix Windows console encoding

SESSIONS_DIR = Path.home() / ".claude" / "memory" / "sessions"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
ARCHIVE_AGE_DAYS = 30
KEEP_RECENT_COUNT = 10


def log_action(action, context):
    """Append a timestamped archival action entry to the policy hits log.

    Args:
        action (str): Action identifier (e.g., 'archived', 'archived-all').
        context (str): Additional context string describing the action.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] session-pruning | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def parse_session_date(filename):
    """
    Extract date from session filename.
    Format: session-YYYY-MM-DD-HH-MM.md
    Returns: datetime object or None
    """
    try:
        # Remove 'session-' prefix and '.md' suffix
        date_str = filename.replace('session-', '').replace('.md', '')
        # Parse: YYYY-MM-DD-HH-MM
        return datetime.strptime(date_str, '%Y-%m-%d-%H-%M')
    except (ValueError, AttributeError):
        return None


def get_session_files(project_dir):
    """Get all session-*.md files in a project directory."""
    if not project_dir.exists():
        return []

    session_files = []
    for file_path in project_dir.glob('session-*.md'):
        session_date = parse_session_date(file_path.name)
        if session_date:
            session_files.append({
                'path': file_path,
                'name': file_path.name,
                'date': session_date,
                'age_days': (datetime.now() - session_date).days
            })

    # Sort by date (newest first)
    session_files.sort(key=lambda x: x['date'], reverse=True)
    return session_files


def identify_sessions_to_archive(session_files):
    """
    Identify which sessions should be archived.

    Rules:
    1. Always keep last 10 sessions (regardless of age)
    2. Archive sessions older than 30 days (except last 10)
    """
    if len(session_files) <= KEEP_RECENT_COUNT:
        # Too few sessions, keep all
        return []

    # Keep recent sessions (last 10)
    recent_sessions = session_files[:KEEP_RECENT_COUNT]
    older_sessions = session_files[KEEP_RECENT_COUNT:]

    # From older sessions, archive those past threshold
    sessions_to_archive = [
        s for s in older_sessions
        if s['age_days'] > ARCHIVE_AGE_DAYS
    ]

    return sessions_to_archive


def create_archive(project_dir, sessions_to_archive, dry_run=False):
    """
    Create compressed archives organized by month.

    Structure:
    project/
    +-- session-2026-01-26-14-30.md  (active)
    +-- session-2026-01-25-10-15.md  (active)
    +-- archive/
        +-- 2025-12/
        |   +-- sessions.tar.gz  (compressed)
        +-- 2025-11/
            +-- sessions.tar.gz  (compressed)
    """
    if not sessions_to_archive:
        return 0

    # Group sessions by month
    sessions_by_month = defaultdict(list)
    for session in sessions_to_archive:
        month_key = session['date'].strftime('%Y-%m')
        sessions_by_month[month_key].append(session)

    archived_count = 0

    for month_key, month_sessions in sessions_by_month.items():
        archive_dir = project_dir / 'archive' / month_key
        archive_file = archive_dir / 'sessions.tar.gz'

        if dry_run:
            print(f"  [DRY RUN] Would archive {len(month_sessions)} sessions to {archive_dir.relative_to(SESSIONS_DIR)}/")
            for session in month_sessions:
                print(f"    - {session['name']} (age: {session['age_days']} days)")
            archived_count += len(month_sessions)
            continue

        # Create archive directory
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create or append to tar.gz archive
        mode = 'a' if archive_file.exists() else 'w'

        with tarfile.open(archive_file, f'{mode}:gz') as tar:
            for session in month_sessions:
                # Add file to archive
                tar.add(session['path'], arcname=session['name'])
                print(f"  [CHECK] Archived: {session['name']} -> {month_key}/sessions.tar.gz (age: {session['age_days']} days)")
                archived_count += 1

        # Delete original files after successful archival
        for session in month_sessions:
            session['path'].unlink()

    return archived_count


def get_project_stats(project_dir):
    """Get statistics for a project."""
    session_files = get_session_files(project_dir)
    sessions_to_archive = identify_sessions_to_archive(session_files)

    # Check archive size
    archive_dir = project_dir / 'archive'
    archive_size = 0
    archive_count = 0

    if archive_dir.exists():
        for archive_file in archive_dir.rglob('sessions.tar.gz'):
            archive_size += archive_file.stat().st_size
            # Count files in archive
            try:
                with tarfile.open(archive_file, 'r:gz') as tar:
                    archive_count += len(tar.getmembers())
            except:
                pass

    return {
        'active_sessions': len(session_files),
        'archivable_sessions': len(sessions_to_archive),
        'archived_sessions': archive_count,
        'archive_size_mb': archive_size / (1024 * 1024),
        'oldest_active': session_files[-1]['date'] if session_files else None,
        'newest_active': session_files[0]['date'] if session_files else None,
    }


def show_statistics():
    """Show statistics for all projects."""
    if not SESSIONS_DIR.exists():
        print("[CROSS] No sessions directory found")
        return

    print("[CHART] Session Memory Statistics")
    print("=" * 70)

    projects = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]
    total_active = 0
    total_archivable = 0
    total_archived = 0
    total_archive_size = 0

    for project_dir in sorted(projects):
        project_name = project_dir.name
        stats = get_project_stats(project_dir)

        if stats['active_sessions'] == 0:
            continue

        print(f"\n[U+1F4C1] {project_name}")
        print(f"   Active sessions: {stats['active_sessions']}")
        print(f"   Archivable (>30d, beyond last 10): {stats['archivable_sessions']}")

        if stats['archived_sessions'] > 0:
            print(f"   Already archived: {stats['archived_sessions']} ({stats['archive_size_mb']:.2f} MB)")

        if stats['oldest_active']:
            age = (datetime.now() - stats['oldest_active']).days
            print(f"   Oldest active session: {stats['oldest_active'].strftime('%Y-%m-%d')} ({age} days old)")

        total_active += stats['active_sessions']
        total_archivable += stats['archivable_sessions']
        total_archived += stats['archived_sessions']
        total_archive_size += stats['archive_size_mb']

    print("\n" + "=" * 70)
    print(f"[CHART] Total:")
    print(f"   Active sessions: {total_active}")
    print(f"   Archivable sessions: {total_archivable}")
    print(f"   Archived sessions: {total_archived} ({total_archive_size:.2f} MB)")


def archive_project(project_name, dry_run=False):
    """Archive old sessions for a specific project."""
    project_dir = SESSIONS_DIR / project_name

    if not project_dir.exists():
        print(f"[CROSS] Project not found: {project_name}")
        return 0

    session_files = get_session_files(project_dir)

    if not session_files:
        print(f"[U+1F4ED] No sessions found for: {project_name}")
        return 0

    sessions_to_archive = identify_sessions_to_archive(session_files)

    if not sessions_to_archive:
        print(f"[CHECK] {project_name}: All sessions are recent (last {len(session_files)} sessions kept)")
        return 0

    print(f"\n[U+1F4E6] {project_name}:")
    print(f"   Total sessions: {len(session_files)}")
    print(f"   Keeping active: {len(session_files) - len(sessions_to_archive)}")
    print(f"   Archiving: {len(sessions_to_archive)}")

    archived_count = create_archive(project_dir, sessions_to_archive, dry_run)

    if not dry_run and archived_count > 0:
        log_action('archived', f'{project_name} | {archived_count} sessions')

    return archived_count


def archive_all_projects(dry_run=False):
    """Archive old sessions for all projects."""
    if not SESSIONS_DIR.exists():
        print("[CROSS] No sessions directory found")
        return

    projects = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]

    if not projects:
        print("[U+1F4ED] No projects found")
        return

    mode_str = "[DRY RUN] " if dry_run else ""
    print(f"[U+1F5C2]️  {mode_str}Archiving sessions for {len(projects)} projects...")
    print(f"   Rules: Keep last {KEEP_RECENT_COUNT} sessions, archive older than {ARCHIVE_AGE_DAYS} days")
    print()

    total_archived = 0

    for project_dir in sorted(projects):
        archived_count = archive_project(project_dir.name, dry_run)
        total_archived += archived_count

    print()
    print("=" * 70)
    if total_archived > 0:
        if dry_run:
            print(f"[CHART] Would archive {total_archived} sessions")
        else:
            print(f"[CHECK] Archived {total_archived} sessions successfully!")
            log_action('archived-all', f'{total_archived} total sessions')
    else:
        print("[CHECK] No sessions need archiving (all are recent)")


def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    if '--stats' in sys.argv:
        show_statistics()
        return

    dry_run = '--dry-run' in sys.argv

    if len(sys.argv) >= 2 and not sys.argv[1].startswith('--'):
        # Archive specific project
        project_name = sys.argv[1]
        archive_project(project_name, dry_run)
    else:
        # Archive all projects
        archive_all_projects(dry_run)


if __name__ == "__main__":
    main()
