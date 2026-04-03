#!/usr/bin/env python
"""GitHub PR lifecycle orchestrator for the Claude Memory System.

Executes a 7-step PR workflow automatically at the end of a coding session
when the ``.session-work-done`` flag file is present. Called from
``stop-notifier.py``; never blocks the stop hook on failure.

Workflow steps
--------------
0. Build validation        -- Run ``auto_build_validator.validate_build()``.
1. Commit changes          -- Stage all changes; build a commit message from
                              the session summary; append ``Closes #N``.
2. Push branch             -- Push the current feature branch to ``origin``.
3. Create PR               -- Open a PR with session summary body via ``gh``.
4. Auto-review comment     -- Post a metrics table comment on the new PR.
5. Merge PR                -- Merge with ``--delete-branch``; falls back to
                              leaving the PR open if branch protection blocks.
6. Switch to main          -- ``git checkout main && git pull --ff-only``.
7. Version bump on main    -- Increment patch version, update CHANGELOG,
                              commit and push to main.

Safety constraints
------------------
- 30 s timeout on all ``gh`` CLI calls.
- All public and private functions wrapped in try/except (never raises).
- Never force-pushes or deletes branches without a preceding merge.
- Skipped entirely when not on a feature branch (main/master are ignored).
- Requires ``gh auth status`` to succeed; skipped if gh is unavailable.

Version: 1.0.0
Last Modified: 2026-02-28
Author: Claude Memory System
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import SESSION_STATE_FILE
except ImportError:
    SESSION_STATE_FILE = Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"

MEMORY_BASE = Path.home() / ".claude" / "memory"
GH_TIMEOUT = 30  # seconds


def _log(msg):
    """Log to stop-notifier log (shared log file)."""
    log_file = MEMORY_BASE / "logs" / "stop-notifier.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{ts} | [PR-WORKFLOW] {msg}\n")
    except Exception:
        pass


def _get_repo_root():
    """Get the git repo root from CWD, or None."""
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_current_branch(repo_root):
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, cwd=repo_root
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_session_id():
    """Get current session ID from session-progress.json."""
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("session_id", "")
    except Exception:
        pass
    return ""


def _load_issues_mapping():
    """Load the github-issues.json mapping for current session."""
    session_id = _get_session_id()
    mapping_file = None
    if session_id:
        mapping_file = MEMORY_BASE / "logs" / "sessions" / session_id / "github-issues.json"
    if not mapping_file or not mapping_file.exists():
        mapping_file = MEMORY_BASE / "logs" / "github-issues.json"
    try:
        if mapping_file.exists():
            with open(mapping_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"task_to_issue": {}, "ops_count": 0}


def _save_issues_mapping(mapping):
    """Persist the github-issues.json mapping."""
    session_id = _get_session_id()
    if session_id:
        mapping_file = MEMORY_BASE / "logs" / "sessions" / session_id / "github-issues.json"
    else:
        mapping_file = MEMORY_BASE / "logs" / "github-issues.json"
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def _load_session_summary():
    """Load session summary data for PR body and review."""
    session_id = _get_session_id()
    if not session_id:
        return {}
    summary_file = MEMORY_BASE / "logs" / "sessions" / session_id / "session-summary.json"
    try:
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _extract_issue_from_branch(branch_name):
    """
    Extract issue number from branch name.
    Supports: fix/42, feature/123, refactor/99, docs/55, enhancement/78, test/34
    Also supports legacy: issue-42
    Returns int or None.
    """
    if not branch_name:
        return None
    try:
        # Format: {label}/{issueId}
        if "/" in branch_name:
            parts = branch_name.rsplit("/", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        # Legacy: issue-{N}
        if branch_name.startswith("issue-"):
            num_str = branch_name[6:]
            if num_str.isdigit():
                return int(num_str)
    except Exception:
        pass
    return None


def _query_open_auto_issues(repo_root):
    """
    Query GitHub for open issues with 'task-auto-created' label.
    Returns list of issue numbers.
    Fallback mechanism when github-issues.json mapping is missing.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--label",
                "task-auto-created",
                "--state",
                "open",
                "--json",
                "number",
                "--limit",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=repo_root,
        )
        if result.returncode == 0 and result.stdout.strip():
            issues = json.loads(result.stdout.strip())
            return [i["number"] for i in issues if "number" in i]
    except Exception:
        pass
    return []


def _get_issue_numbers():
    """
    Get all issue numbers to close in this PR.
    Uses 3 sources (in priority order):
      1. Session mapping (github-issues.json) - most reliable
      2. Branch name extraction (fix/42 -> #42) - always available
      3. Open auto-created issues query (gh issue list) - fallback
    Deduplicates and returns sorted list.
    """
    numbers = set()

    # Source 1: Session mapping
    mapping = _load_issues_mapping()
    for task_key, issue_data in mapping.get("task_to_issue", {}).items():
        num = issue_data.get("issue_number")
        if num:
            numbers.add(num)

    # Source 2: Branch name extraction
    branch = mapping.get("session_branch", "") or mapping.get("branch", "")
    if not branch:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
        except Exception:
            pass
    branch_issue = _extract_issue_from_branch(branch)
    if branch_issue:
        numbers.add(branch_issue)

    # Source 3: Query open auto-created issues (only if no numbers found yet)
    if not numbers:
        repo_root = _get_repo_root()
        if repo_root:
            auto_issues = _query_open_auto_issues(repo_root)
            for num in auto_issues:
                numbers.add(num)

    return sorted(numbers)
