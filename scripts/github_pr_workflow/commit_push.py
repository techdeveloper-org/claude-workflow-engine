"""github_pr_workflow/commit_push.py - Commit, push, and PR creation.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .git_ops import _load_issues_mapping, _log, _save_issues_mapping


def _has_changes(repo_root: str) -> bool:
    """Return True if the working tree has staged or unstaged changes.

    Args:
        repo_root: Absolute path to the git repository root.

    Returns:
        ``True`` if ``git status --porcelain`` produces any output,
        ``False`` if the working tree is clean or on error.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10, cwd=repo_root
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except Exception:
        pass
    return False


def _commit_session_changes(repo_root: str, session_summary: dict, issue_numbers: list = None) -> bool:
    """Stage all changes and create a commit with a session-derived message.

    Builds the commit title from ``session_summary['task_types']`` and the
    body from ``session_summary['requests']``. Appends ``Closes #N`` lines
    for each issue number so GitHub auto-closes them on merge.

    Args:
        repo_root: Absolute path to the git repository root.
        session_summary: Session summary dict loaded from session-summary.json.
        issue_numbers: Optional list of GitHub issue numbers to close.

    Returns:
        ``True`` if the commit succeeded or there were no changes to commit.
        ``False`` if ``git add`` or ``git commit`` exited with a non-zero code.
    """
    try:
        if not _has_changes(repo_root):
            _log("No uncommitted changes to commit")
            return True

        # Stage all changes
        result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, timeout=15, cwd=repo_root)
        if result.returncode != 0:
            _log(f"git add failed: {result.stderr[:200]}")
            return False

        # Build commit message from LLM (preferred) or session summary fallback
        commit_title = ""
        commit_body = ""

        # Get staged file info for context
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, timeout=10, cwd=repo_root
        )
        changed_files = [f for f in diff_result.stdout.strip().splitlines() if f] if diff_result.returncode == 0 else []

        # Try LLM-powered commit message (shared function in llm_call.py)
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            from langgraph_engine.llm_call import generate_llm_commit_title

            commit_title = generate_llm_commit_title(cwd=repo_root) or ""
            if commit_title:
                _log(f"LLM commit title: {commit_title}")
        except Exception as llm_err:
            _log(f"LLM commit message skipped: {llm_err}")

        # Fallback: session summary or file-based title
        if not commit_title:
            if session_summary:
                types = session_summary.get("task_types", [])
                if types:
                    commit_title = ", ".join(types[:3])

            if not commit_title and changed_files:
                stems = [Path(f).stem for f in changed_files[:3]]
                if len(changed_files) <= 3:
                    commit_title = f"update {', '.join(stems)}"
                else:
                    dirs = set(str(Path(f).parent) for f in changed_files)
                    if len(dirs) == 1:
                        dirname = Path(list(dirs)[0]).name
                        commit_title = f"update {len(changed_files)} {dirname} modules"
                    else:
                        commit_title = f"update {', '.join(stems)} and {len(changed_files) - 3} more"
            elif not commit_title:
                commit_title = "update implementation"

        # Build body from session requests or file list
        if session_summary:
            requests = session_summary.get("requests", [])
            if requests:
                body_lines = [f"- {req.get('prompt', '')[:100]}" for req in requests if req.get("prompt")]
                if body_lines:
                    commit_body = "\n".join(body_lines[:10])

        if changed_files and not commit_body:
            commit_body = "Modified files ({}):\n{}".format(
                len(changed_files), "\n".join(f"  - {f}" for f in changed_files[:10])
            )

        # Append Closes #N for auto-closing GitHub issues (policy requirement)
        if issue_numbers:
            closes_lines = "\n".join(f"Closes #{n}" for n in issue_numbers)
            if commit_body:
                commit_body = commit_body + "\n\n" + closes_lines
            else:
                commit_body = closes_lines

        commit_msg = commit_title
        if commit_body:
            commit_msg = commit_title + "\n\n" + commit_body

        result = subprocess.run(
            ["git", "commit", "-m", commit_msg], capture_output=True, text=True, timeout=15, cwd=repo_root
        )
        if result.returncode == 0:
            _log(f"Committed: {commit_title[:80]}")
            return True
        else:
            _log(f"git commit failed: {result.stderr[:200]}")
            return False

    except Exception as e:
        _log(f"Commit error: {e}")
        return False


def _push_branch(repo_root: str, branch_name: str) -> bool:
    """Push the local branch to the remote origin and set upstream tracking.

    Args:
        repo_root: Absolute path to the git repository root.
        branch_name: Name of the branch to push.

    Returns:
        ``True`` if the push succeeded, ``False`` on failure or error.
    """
    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=repo_root,
        )
        if result.returncode == 0:
            _log(f"Pushed branch: {branch_name}")
            return True
        else:
            _log(f"Push failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        _log(f"Push error: {e}")
        return False


def _create_pull_request(repo_root, branch_name, issue_numbers, session_summary):
    """
    Create a PR via gh CLI.
    Returns PR number (int) on success, None on failure.
    """
    try:
        # Build PR title
        pr_title = "Session work"
        if session_summary:
            types = session_summary.get("task_types", [])
            skills = session_summary.get("skills_used", [])
            if types:
                pr_title = ", ".join(types[:3])
            elif skills:
                pr_title = "Work with " + ", ".join(skills[:2])

        # Truncate title
        if len(pr_title) > 70:
            pr_title = pr_title[:67] + "..."

        # Build PR body
        body_parts = ["## Summary\n"]

        # Add work stories from session summary
        if session_summary:
            requests = session_summary.get("requests", [])
            if requests:
                for req in requests[:10]:
                    prompt = req.get("prompt", "")[:120]
                    task_type = req.get("task_type", "")
                    if prompt:
                        line = f"- {prompt}"
                        if task_type:
                            line += f" ({task_type})"
                        body_parts.append(line)
                body_parts.append("")

            # Stats
            req_count = session_summary.get("request_count", 0)
            max_complexity = session_summary.get("max_complexity", 0)
            skills = session_summary.get("skills_used", [])
            if req_count or max_complexity or skills:
                body_parts.append("## Session Stats\n")
                if req_count:
                    body_parts.append(f"- **Requests:** {req_count}")
                if max_complexity:
                    body_parts.append(f"- **Max Complexity:** {max_complexity}/25")
                if skills:
                    body_parts.append(f"- **Skills:** {', '.join(skills)}")
                body_parts.append("")

        # Close issues
        if issue_numbers:
            body_parts.append("## Issues\n")
            for num in issue_numbers:
                body_parts.append(f"Closes #{num}")
            body_parts.append("")

        body_parts.append("---")
        body_parts.append("_Auto-created by Claude Memory System (GitHub PR Workflow)_")

        pr_body = "\n".join(body_parts)

        # Create PR via gh CLI
        cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            pr_title,
            "--body",
            pr_body,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=repo_root)

        if result.returncode == 0 and result.stdout.strip():
            pr_url = result.stdout.strip()
            _log(f"PR created: {pr_url}")

            # Extract PR number from URL
            pr_number = None
            if "/pull/" in pr_url:
                num_str = pr_url.rsplit("/pull/", 1)[1].strip()
                if num_str.isdigit():
                    pr_number = int(num_str)

            # Save PR info to mapping
            mapping = _load_issues_mapping()
            mapping["pr_number"] = pr_number
            mapping["pr_url"] = pr_url
            mapping["pr_created_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            _save_issues_mapping(mapping)

            sys.stdout.write(f"[GH] PR #{pr_number} created: {pr_url}\n")
            sys.stdout.flush()

            return pr_number
        else:
            _log(f"PR creation failed: {result.stderr[:200]}")
            return None

    except Exception as e:
        _log(f"PR creation error: {e}")
        return None
