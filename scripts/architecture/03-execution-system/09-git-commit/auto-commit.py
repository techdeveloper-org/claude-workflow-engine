#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Commit Executor
Automatically commits changes when triggers are met

This script:
1. Uses auto-commit-detector.py to check triggers
2. Generates smart commit messages
3. Stages relevant files
4. Creates commits with co-author tag
5. Optional auto-push

Usage:
    python auto-commit.py [--project-dir DIR] [--push] [--dry-run]

Examples:
    python auto-commit.py
    python auto-commit.py --push
    python auto-commit.py --dry-run --project-dir /path/to/repo
"""

import sys
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude" / "memory"


def run_git_command(args, timeout=30, cwd=None):
    """Run a git command and return the result"""
    try:
        return subprocess.run(
            ['git'] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd
        )
    except Exception as e:
        class _R:
            returncode = 1
            stdout = ''
            stderr = str(e)
        return _R()


def run_system_command(cmd, timeout=30):
    """Run a system command and return the result"""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=True
        )
    except Exception as e:
        class _R:
            returncode = 1
            stdout = ''
            stderr = str(e)
        return _R()

# Fix Windows encoding issues
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def log_policy_hit(action, context):
    """Log policy execution"""
    log_file = os.path.expanduser("~/.claude/memory/logs/policy-hits.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] auto-commit | {action} | {context}\n"

    try:
        with open(log_file, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log: {e}", file=sys.stderr)

def check_git_repo(project_dir):
    """Check if directory is a git repo"""
    try:
        result = run_git_command(["rev-parse", "--git-dir"], cwd=project_dir, timeout=5)
        return result.returncode == 0
    except:
        return False

def get_commit_message_style(project_dir):
    """Analyze recent commits to match style"""
    try:
        result = run_git_command(["log", "-10", "--pretty=format:%s"], cwd=project_dir, timeout=5)

        if result.returncode == 0 and result.stdout.strip():
            messages = result.stdout.strip().split('\n')

            # Detect style patterns
            has_type_prefix = any(':' in msg[:20] for msg in messages)
            has_emoji = any(any(ord(c) > 127 for c in msg[:10]) for msg in messages)
            avg_length = sum(len(msg) for msg in messages) / len(messages)

            return {
                "type_prefix": has_type_prefix,  # feat:, fix:, etc.
                "emoji": has_emoji,
                "length": "short" if avg_length < 50 else "medium" if avg_length < 80 else "long"
            }

        return None

    except Exception as e:
        return None

def _load_task_context():
    """Load actual task context from session data (flow-trace + session-progress + tool-tracker).
    Returns dict with task_subject, task_description, task_type, files_changed, edits_made."""
    ctx = {'task_subject': '', 'task_description': '', 'task_type': '', 'edits_summary': []}
    try:
        # 1. Get session ID from session-progress
        progress_file = MEMORY_DIR / 'logs' / 'session-progress.json'
        session_id = ''
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            session_id = prog.get('session_id', '')

        # 2. Get task type + complexity from flow-trace
        if session_id:
            trace_file = MEMORY_DIR / 'logs' / 'sessions' / session_id / 'flow-trace.json'
            if trace_file.exists():
                with open(trace_file, 'r', encoding='utf-8') as f:
                    trace = json.load(f)
                fd = trace.get('final_decision', {})
                ctx['task_type'] = fd.get('task_type', '')

        # 3. Get last task subject + edits from tool-tracker.jsonl (most recent data)
        tracker_file = MEMORY_DIR / 'logs' / 'tool-tracker.jsonl'
        if tracker_file.exists():
            with open(tracker_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # Scan from end: find latest TaskCreate subject, and collect recent edits
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                tool = entry.get('tool', '')
                if tool == 'TaskCreate' and not ctx['task_subject']:
                    ctx['task_subject'] = entry.get('task_subject', '')
                if tool == 'Edit' and len(ctx['edits_summary']) < 5:
                    f_path = entry.get('file', '')
                    hint = entry.get('new_hint', '')
                    if f_path:
                        ctx['edits_summary'].append(f_path)
                if tool == 'Write' and len(ctx['edits_summary']) < 5:
                    f_path = entry.get('file', '')
                    if f_path:
                        ctx['edits_summary'].append(f_path)
    except Exception:
        pass
    return ctx


def generate_commit_message(git_status, triggers, style=None):
    """Generate smart commit message using actual task context from session data."""

    staged_files = git_status.get("staged", [])

    # Load REAL task context from session chain
    task_ctx = _load_task_context()
    task_subject = task_ctx.get('task_subject', '')
    task_type_raw = task_ctx.get('task_type', '')

    # Determine change_type from task context first, then fallback to file analysis
    change_type = "update"
    summary = ""

    # Priority 1: Use actual task subject as commit summary
    if task_subject:
        subject_lower = task_subject.lower()
        # Detect type from task subject
        if any(w in subject_lower for w in ['fix', 'bug', 'error', 'broken', 'crash', 'resolve']):
            change_type = "fix"
        elif any(w in subject_lower for w in ['refactor', 'cleanup', 'reorganize', 'simplify']):
            change_type = "refactor"
        elif any(w in subject_lower for w in ['doc', 'readme', 'documentation']):
            change_type = "docs"
        elif any(w in subject_lower for w in ['test', 'spec', 'coverage']):
            change_type = "test"
        elif any(w in subject_lower for w in ['update', 'enhance', 'improve', 'optimize']):
            change_type = "update"
        else:
            change_type = "feat"
        summary = task_subject
    # Priority 2: Infer from file types if no task context
    else:
        if any(f.endswith('.test.js') or f.endswith('.spec.ts') or 'test' in f for f in staged_files):
            change_type = "test"
            summary = "Add/update tests"
        elif any('readme' in f.lower() or f.endswith('.md') for f in staged_files):
            change_type = "docs"
            summary = "Update documentation"
        elif any(f.endswith('.css') or f.endswith('.scss') for f in staged_files):
            change_type = "style"
            summary = "Update styling"
        elif len(staged_files) >= 10:
            change_type = "feat"
            summary = "Implement major changes across " + str(len(staged_files)) + " files"
        else:
            change_type = "update"
            # Use file names as context
            file_names = [os.path.basename(f) for f in staged_files[:3]]
            summary = "Update " + ", ".join(file_names)

    # Build message with type prefix (matching repo style)
    if style and style.get("type_prefix"):
        message = f"{change_type}: {summary}"
    else:
        message = summary.capitalize() if summary else "Update implementation"

    # Only add file count for large changesets (no "Files:" noise for small ones)
    if len(staged_files) > 5:
        message += f"\n\n{len(staged_files)} files modified"

    return message

def stage_files(project_dir, git_status):
    """Stage relevant files for commit"""
    modified_files = git_status.get("modified", [])

    if not modified_files:
        # All changes already staged
        return True

    # Stage modified files (not untracked)
    try:
        result = run_git_command(["add", "-u"], cwd=project_dir, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"Error staging files: {e}", file=sys.stderr)
        return False

def create_commit(project_dir, message, dry_run=False):
    """Create git commit"""
    if dry_run:
        print("\n[DRY RUN] Would create commit with message:")
        print("=" * 70)
        print(message)
        print("=" * 70)
        return True

    try:
        result = run_git_command(["commit", "-m", message], cwd=project_dir, timeout=30)

        if result.returncode == 0:
            print("\n[CHECK] Commit created successfully!")
            print(result.stdout)
            return True
        else:
            print(f"\n[CROSS] Commit failed: {result.stderr}", file=sys.stderr)
            return False

    except Exception as e:
        print(f"Error creating commit: {e}", file=sys.stderr)
        return False

def push_changes(project_dir, dry_run=False):
    """Push commits to remote"""
    if dry_run:
        print("\n[DRY RUN] Would push to remote")
        return True

    try:
        result = run_git_command(["push"], cwd=project_dir, timeout=60)

        if result.returncode == 0:
            print("\n[CHECK] Pushed to remote!")
            print(result.stdout)
            return True
        else:
            print(f"\n[WARNING]️ Push failed: {result.stderr}", file=sys.stderr)
            return False

    except Exception as e:
        print(f"Error pushing: {e}", file=sys.stderr)
        return False

def auto_commit(project_dir, push=False, dry_run=False):
    """Execute auto-commit process"""

    print("\n" + "=" * 70)
    print("[CYCLE] AUTO-COMMIT EXECUTOR")
    print("=" * 70)
    print(f"\nProject: {project_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("")

    # Step 1: Check if git repo
    if not check_git_repo(project_dir):
        print("[CROSS] Not a git repository")
        return False

    # Step 2: Run detector
    print("Step 1: Checking commit triggers...")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        detector_path = os.path.join(script_dir, "auto-commit-detector.py")
        if not os.path.exists(detector_path):
            detector_path = os.path.expanduser("~/.claude/scripts/architecture/03-execution-system/09-git-commit/auto-commit-detector.py")
        result = subprocess.run(
            [sys.executable, detector_path,
             "--project-dir", project_dir, "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print("[PAUSE]️  No commit needed")
            return False

        detection = json.loads(result.stdout)

        if not detection.get("should_commit"):
            print("[PAUSE]️  No triggers met")
            return False

        print(f"[CHECK] {detection['trigger_count']} triggers met")
        for trigger in detection['triggers_met']:
            details = detection['details'].get(trigger, {})
            reason = details.get('reason', 'N/A')
            print(f"   [CHECK] {trigger.replace('_', ' ').title()}: {reason}")

    except Exception as e:
        print(f"[CROSS] Error checking triggers: {e}", file=sys.stderr)
        return False

    git_status = detection.get("git_status", {})
    triggers = detection.get("details", {})

    # Step 3: Stage files
    print("\nStep 2: Staging files...")
    if not stage_files(project_dir, git_status):
        print("[CROSS] Failed to stage files")
        return False
    print("[CHECK] Files staged")

    # Step 4: Generate commit message
    print("\nStep 3: Generating commit message...")
    style = get_commit_message_style(project_dir)
    message = generate_commit_message(git_status, triggers, style)
    print("[CHECK] Message generated")

    # Step 5: Create commit
    print("\nStep 4: Creating commit...")
    if not create_commit(project_dir, message, dry_run):
        return False

    log_policy_hit("commit-created", f"triggers={detection['trigger_count']}, files={git_status['staged_count']}")

    # Step 6: Push (optional)
    if push:
        print("\nStep 5: Pushing to remote...")
        push_changes(project_dir, dry_run)

    print("\n" + "=" * 70)
    print("[CHECK] AUTO-COMMIT COMPLETE")
    print("=" * 70)

    return True

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Auto-commit changes when triggers are met"
    )
    parser.add_argument(
        '--project-dir',
        type=str,
        default=None,
        help='Project directory (default: current directory)'
    )
    parser.add_argument(
        '--push',
        action='store_true',
        help='Push to remote after commit'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run (show what would happen)'
    )

    args = parser.parse_args()

    # Default to current directory
    if not args.project_dir:
        args.project_dir = os.getcwd()

    # Execute auto-commit
    success = auto_commit(args.project_dir, args.push, args.dry_run)

    # Exit code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
