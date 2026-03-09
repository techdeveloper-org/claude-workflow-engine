#!/usr/bin/env python3
"""
Post-Merge Version & Documentation Updater - Level 3.11 Automation

Runs AFTER PR merge to main branch.
Automatically:
1. Bumps VERSION file (semantic versioning)
2. Updates README.md with new version
3. Updates SYSTEM_REQUIREMENTS_SPECIFICATION.md
4. Creates auto-commit with all changes

Trigger: Should be called in post-tool-tracker.py when PR merge to main is detected
Hook: PostToolUse (after Bash tool that does 'git push' or 'gh pr merge')

Version: 1.0.0
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Windows: UTF-8 safe
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def run_command(cmd, cwd=None, timeout=30):
    """Run shell command safely."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, '', str(e)


def detect_pr_merge():
    """
    Detect if current state is post-PR merge to main.

    Checks:
    1. Current branch is 'main'
    2. Last commit message contains 'merge' or 'Merge'
    3. Last 2 branches show merge activity
    """
    # Check current branch
    success, branch, _ = run_command('git branch --show-current')
    if not success or 'main' not in branch:
        return False, "Not on main branch"

    # Check last commit message
    success, msg, _ = run_command('git log -1 --pretty=%B')
    if not success:
        return False, "Could not read commit message"

    is_merge = 'merge' in msg.lower() or 'Merge pull request' in msg

    return is_merge, msg


def bump_version(project_root):
    """
    Bump version using semantic versioning.

    VERSION file format: X.Y.Z
    Rules:
    - feature/bug on main -> bump MINOR (X.Y+1.0)
    - hotfix on main -> bump PATCH (X.Y.Z+1)
    - breaking change -> bump MAJOR (X+1.0.0)
    """
    version_file = project_root / 'VERSION'

    if not version_file.exists():
        return False, "VERSION file not found"

    try:
        current = version_file.read_text().strip()
        parts = current.split('.')

        if len(parts) != 3:
            return False, f"Invalid version format: {current} (expected X.Y.Z)"

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        # Bump MINOR by default (feature/bug fixes)
        # TODO: Could check commit message for 'BREAKING:' to bump MAJOR
        minor += 1
        patch = 0

        new_version = f"{major}.{minor}.{patch}"
        version_file.write_text(new_version + '\n', encoding='utf-8')

        return True, f"{current} -> {new_version}"
    except Exception as e:
        return False, str(e)


def update_readme(project_root, new_version):
    """
    Update README.md with new version.

    Patterns to update:
    - Title: # Claude Insight vX.Y.Z
    - Badge: Version-brightgreen?version=X.Y.Z
    """
    readme_file = project_root / 'README.md'

    if not readme_file.exists():
        return False, "README.md not found"

    try:
        content = readme_file.read_text(encoding='utf-8')

        # Update title
        content = content.replace(
            '# Claude Insight v',
            f'# Claude Insight v{new_version} (was v'
        )
        # Simpler: just replace version in title
        import re
        content = re.sub(
            r'# Claude Insight v[\d.]+',
            f'# Claude Insight v{new_version}',
            content
        )

        # Update badge
        content = re.sub(
            r'\]\(Version\)-brightgreen\?version=[\d.]+',
            f'](Version)-brightgreen?version={new_version}',
            content
        )

        readme_file.write_text(content, encoding='utf-8')
        return True, "README.md updated"
    except Exception as e:
        return False, str(e)


def call_version_release_policy(project_root, new_version):
    """
    Call version-release-policy.py --bump to auto-update docs.

    This script uses LLM to generate comprehensive README/SRS updates.
    """
    policy_script = (
        project_root / 'scripts' / 'architecture' / '03-execution-system' /
        '09-git-commit' / 'version-release-policy.py'
    )

    if not policy_script.exists():
        return False, f"version-release-policy.py not found at {policy_script}"

    try:
        # Run the policy script (it will handle README/SRS update internally)
        success, stdout, stderr = run_command(
            f'{sys.executable} "{policy_script}" --bump',
            cwd=str(project_root),
            timeout=60
        )

        if success:
            return True, "version-release-policy.py executed successfully"
        else:
            return False, f"Policy script failed: {stderr}"
    except Exception as e:
        return False, f"Could not execute policy script: {str(e)}"


def create_auto_commit(project_root, new_version):
    """
    Create auto-commit with all version/docs changes.
    """
    try:
        # Stage all changes in VERSION, README, SRS
        run_command('git add VERSION README.md CHANGELOG.md SYSTEM_REQUIREMENTS_SPECIFICATION.md', cwd=str(project_root))

        # Check if there are staged changes
        success, status, _ = run_command('git status --short', cwd=str(project_root))
        if not success or not status:
            return False, "No changes to commit"

        # Create commit
        commit_body = (
            f"- Updated VERSION file\n"
            f"- Updated README.md with new version\n"
            f"- Updated SYSTEM_REQUIREMENTS_SPECIFICATION.md\n"
            f"- Timestamp: {datetime.now().isoformat()}\n\n"
            f"Co-Authored-By: Claude Insight System <noreply@anthropic.com>"
        )

        # Use git commit with stdin to avoid shell quoting issues
        cmd = f'git commit -m "chore: Auto-bump version to {new_version}"'
        success, _, _ = run_command(
            cmd,
            cwd=str(project_root),
            timeout=30
        )

        if success:
            return True, f"Auto-commit created for v{new_version}"
        else:
            return False, "Could not create commit"
    except Exception as e:
        return False, str(e)


def main():
    """Main entry point."""
    project_root = Path.cwd()

    # Log execution
    log_file = Path.home() / '.claude' / 'memory' / 'logs' / 'post-merge-updater.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat()

    # Step 1: Detect if this is post-PR merge
    is_merge, msg = detect_pr_merge()
    log_entry = f"[{timestamp}] PR Merge Detection: {is_merge}\n"

    if not is_merge:
        log_entry += f"  Reason: {msg}\n  Skipping auto-version update.\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        return 0  # Not a merge, skip

    log_entry += f"  Merge detected: {msg[:100]}\n"

    # Step 2: Bump version
    success, result = bump_version(project_root)
    log_entry += f"[VERSION] {success}: {result}\n"

    if not success:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        print(json.dumps({'status': 'FAILED', 'reason': result}))
        return 1

    # Extract new version
    new_version = result.split(' -> ')[-1].strip()

    # Step 3: Update README
    success, result = update_readme(project_root, new_version)
    log_entry += f"[README] {success}: {result}\n"

    # Step 4: Call version-release-policy.py for comprehensive updates
    success, result = call_version_release_policy(project_root, new_version)
    log_entry += f"[POLICY] {success}: {result}\n"

    # Step 5: Create auto-commit
    success, result = create_auto_commit(project_root, new_version)
    log_entry += f"[COMMIT] {success}: {result}\n"

    # Log result
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_entry)

    # Output status
    output = {
        'step': 'POST_MERGE_VERSION_UPDATE',
        'timestamp': timestamp,
        'new_version': new_version,
        'status': 'OK' if success else 'FAILED'
    }

    print(json.dumps(output))
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
