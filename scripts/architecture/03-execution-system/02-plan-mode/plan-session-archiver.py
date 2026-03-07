#!/usr/bin/env python3
"""
Plan Session Archiver - Archive plans to session folder

Script Name: plan-session-archiver.py
Version: 1.0.0
Last Modified: 2026-03-05

Description:
    When a user enters plan mode and creates a plan, this script automatically
    archives the plan from ~/.claude/plans/ to the session folder at:
    ~/.claude/memory/logs/sessions/{SESSION_ID}/plan.md

    This ensures plans are:
    - Linked to their session permanently
    - Available for context continuity
    - Accessible by smart review (Step 4.5)
    - Part of the session archive

Usage:
    python plan-session-archiver.py --archive {SESSION_ID}
    python plan-session-archiver.py --check {SESSION_ID}

Hook Type: Utility (called by stop-notifier.py at session end)
Windows-Safe: Yes - ASCII only, cp1252 compatible
"""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


# ============================================================================
# PATHS
# ============================================================================

def get_plans_dir():
    """Get directory where plans are stored by Claude Code IDE."""
    return Path.home() / '.claude' / 'plans'


def get_session_logs_dir(session_id):
    """Get the session logs directory."""
    return Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id


def get_session_plan_path(session_id):
    """Get the path where session plan should be archived."""
    return get_session_logs_dir(session_id) / 'plan.md'


def get_session_summary_path(session_id):
    """Get the path to session-summary.json."""
    return get_session_logs_dir(session_id) / 'session-summary.json'


def get_plan_metadata_path(session_id):
    """Get the path to plan archival metadata."""
    return get_session_logs_dir(session_id) / 'plan-archival-metadata.json'


# ============================================================================
# PLAN DETECTION
# ============================================================================

def find_latest_plan_file():
    """
    Find the most recently created/modified plan file in ~/.claude/plans/.

    Returns:
        Path or None: Path to latest plan file, or None if no plans found
    """
    plans_dir = get_plans_dir()

    if not plans_dir.exists():
        return None

    # Get all .md files, sorted by modification time (newest first)
    plan_files = sorted(
        plans_dir.glob('*.md'),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    return plan_files[0] if plan_files else None


def get_plan_info(plan_path):
    """
    Extract basic info from plan file.

    Args:
        plan_path (Path): Path to plan file

    Returns:
        dict: {
            'filename': str,
            'size_bytes': int,
            'modified_time': float (timestamp),
            'first_line': str (title)
        }
    """
    try:
        stat = plan_path.stat()
        with open(plan_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()[:100]  # First 100 chars
        return {
            'filename': plan_path.name,
            'size_bytes': stat.st_size,
            'modified_time': stat.st_mtime,
            'first_line': first_line
        }
    except Exception as e:
        return {
            'filename': plan_path.name,
            'size_bytes': 0,
            'modified_time': 0,
            'first_line': '',
            'error': str(e)
        }


# ============================================================================
# ARCHIVAL
# ============================================================================

def archive_plan_to_session(session_id):
    """
    Archive the most recent plan from ~/.claude/plans/ to session folder.

    This function:
    1. Finds the latest plan file
    2. Copies it to the session folder
    3. Creates metadata record
    4. Updates session-summary.json

    Args:
        session_id (str): Current session ID (e.g., SESSION-20260305-113248-W5K4)

    Returns:
        dict: {
            'success': bool,
            'plan_file': str (original path),
            'archived_to': str (session path),
            'plan_name': str (original random name),
            'size_bytes': int,
            'timestamp': str (ISO format),
            'message': str,
            'error': str (if failed)
        }

    Example:
        result = archive_plan_to_session('SESSION-20260305-113248-W5K4')
        if result['success']:
            print(f"Plan archived: {result['archived_to']}")
        else:
            print(f"Archive failed: {result['error']}")
    """
    result = {
        'success': False,
        'plan_file': None,
        'archived_to': None,
        'plan_name': None,
        'size_bytes': 0,
        'timestamp': datetime.now().isoformat(),
        'message': '',
        'error': None
    }

    # Step 1: Find latest plan file
    plan_file = find_latest_plan_file()
    if not plan_file:
        result['message'] = 'No plan file found in ~/.claude/plans/ - plan mode may not have been used'
        return result

    # Step 2: Verify session directory exists
    session_dir = get_session_logs_dir(session_id)
    if not session_dir.exists():
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            result['error'] = f'Failed to create session directory: {e}'
            return result

    # Step 3: Copy plan file to session folder
    try:
        plan_archive_path = get_session_plan_path(session_id)
        plan_info = get_plan_info(plan_file)

        # Copy the file
        shutil.copy2(plan_file, str(plan_archive_path))

        result['plan_file'] = str(plan_file)
        result['archived_to'] = str(plan_archive_path)
        result['plan_name'] = plan_file.name
        result['size_bytes'] = plan_info['size_bytes']

    except Exception as e:
        result['error'] = f'Failed to copy plan file: {e}'
        return result

    # Step 4: Create archival metadata
    try:
        metadata = {
            'session_id': session_id,
            'plan_created': True,
            'plan_filename': plan_file.name,
            'plan_archived_at': datetime.now().isoformat(),
            'plan_location': str(get_session_plan_path(session_id)),
            'plan_size_bytes': result['size_bytes'],
            'plan_status': 'archived',
            'original_location': str(plan_file)
        }

        metadata_path = get_plan_metadata_path(session_id)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        result['error'] = f'Failed to create metadata: {e}'
        return result

    # Step 5: Update session-summary.json with plan_info
    try:
        summary_path = get_session_summary_path(session_id)
        if summary_path.exists():
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
        else:
            summary = {}

        # Add plan_info block
        summary['plan_info'] = {
            'plan_created': True,
            'plan_mode_required': True,
            'plan_filename': plan_file.name,
            'plan_archived_at': datetime.now().isoformat(),
            'plan_location': str(get_session_plan_path(session_id)),
            'plan_size_bytes': result['size_bytes'],
            'plan_status': 'archived'
        }

        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

    except Exception as e:
        # Non-fatal error - plan is already archived, just metadata failed
        result['error'] = f'Warning: Plan archived but metadata update failed: {e}'

    # Success!
    result['success'] = True
    result['message'] = f"Plan archived successfully: {plan_file.name}"

    return result


# ============================================================================
# CHECKING
# ============================================================================

def check_plan_archived(session_id):
    """
    Check if a plan has been archived for a session.

    Args:
        session_id (str): Session ID to check

    Returns:
        dict: {
            'plan_exists': bool,
            'plan_path': str (if exists),
            'plan_size': int (if exists),
            'plan_age_seconds': float (if exists)
        }
    """
    plan_path = get_session_plan_path(session_id)

    if not plan_path.exists():
        return {
            'plan_exists': False,
            'plan_path': None,
            'plan_size': 0,
            'plan_age_seconds': None
        }

    try:
        stat = plan_path.stat()
        age = (datetime.now().timestamp() - stat.st_mtime)
        return {
            'plan_exists': True,
            'plan_path': str(plan_path),
            'plan_size': stat.st_size,
            'plan_age_seconds': age
        }
    except Exception as e:
        return {
            'plan_exists': False,
            'plan_path': str(plan_path),
            'error': str(e)
        }


# ============================================================================
# CLI
# ============================================================================

def main():
    """Command-line interface."""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python plan-session-archiver.py --archive {SESSION_ID}")
        print("  python plan-session-archiver.py --check {SESSION_ID}")
        print()
        print("Examples:")
        print("  python plan-session-archiver.py --archive SESSION-20260305-113248-W5K4")
        print("  python plan-session-archiver.py --check SESSION-20260305-113248-W5K4")
        sys.exit(0)

    command = sys.argv[1]
    session_id = sys.argv[2] if len(sys.argv) > 2 else None

    if not session_id:
        print("[ERROR] Session ID required")
        sys.exit(1)

    if command == '--archive':
        result = archive_plan_to_session(session_id)
        print(json.dumps(result, indent=2))
        # Only exit 1 if there was a real error (not just "no plan found")
        if not result['success'] and result.get('error'):
            sys.exit(1)
        sys.exit(0)

    elif command == '--check':
        result = check_plan_archived(session_id)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    else:
        print(f"[ERROR] Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
