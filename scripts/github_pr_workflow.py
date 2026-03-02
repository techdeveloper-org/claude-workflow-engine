#!/usr/bin/env python
# Script Name: github_pr_workflow.py
# Version: 1.0.0
# Last Modified: 2026-02-28
# Description: GitHub PR lifecycle orchestrator. Creates commit, push, PR,
#              auto-review comment, merge, and switches back to main.
#              Called from stop-notifier.py when .session-work-done flag exists.
#              Non-blocking - never fails the stop hook.
# Author: Claude Memory System
#
# Safety:
#   - 30s timeout on all gh CLI calls
#   - All functions wrapped in try/except (never raises)
#   - If any step fails, logs and continues (PR stays open for manual handling)
#   - Never force-pushes or deletes branches

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import SESSION_STATE_FILE
except ImportError:
    SESSION_STATE_FILE = Path.home() / '.claude' / 'memory' / 'logs' / 'session-progress.json'

MEMORY_BASE = Path.home() / '.claude' / 'memory'
GH_TIMEOUT = 30  # seconds


def _log(msg):
    """Log to stop-notifier log (shared log file)."""
    log_file = MEMORY_BASE / 'logs' / 'stop-notifier.log'
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | [PR-WORKFLOW] {msg}\n")
    except Exception:
        pass


def _get_repo_root():
    """Get the git repo root from CWD, or None."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_current_branch(repo_root):
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=repo_root
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
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('session_id', '')
    except Exception:
        pass
    return ''


def _load_issues_mapping():
    """Load the github-issues.json mapping for current session."""
    session_id = _get_session_id()
    mapping_file = None
    if session_id:
        mapping_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'github-issues.json'
    if not mapping_file or not mapping_file.exists():
        mapping_file = MEMORY_BASE / 'logs' / 'github-issues.json'
    try:
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'task_to_issue': {}, 'ops_count': 0}


def _save_issues_mapping(mapping):
    """Persist the github-issues.json mapping."""
    session_id = _get_session_id()
    if session_id:
        mapping_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'github-issues.json'
    else:
        mapping_file = MEMORY_BASE / 'logs' / 'github-issues.json'
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def _load_session_summary():
    """Load session summary data for PR body and review."""
    session_id = _get_session_id()
    if not session_id:
        return {}
    summary_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'session-summary.json'
    try:
        if summary_file.exists():
            with open(summary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_issue_numbers():
    """Get all issue numbers created in this session."""
    mapping = _load_issues_mapping()
    numbers = []
    for task_key, issue_data in mapping.get('task_to_issue', {}).items():
        num = issue_data.get('issue_number')
        if num:
            numbers.append(num)
    return numbers


def _has_changes(repo_root):
    """Check if there are uncommitted changes (staged or unstaged)."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except Exception:
        pass
    return False


def _commit_session_changes(repo_root, session_summary):
    """
    Stage and commit all changes with a meaningful message from session summary.
    Returns True if commit succeeded (or no changes to commit).
    """
    try:
        if not _has_changes(repo_root):
            _log("No uncommitted changes to commit")
            return True

        # Stage all changes
        result = subprocess.run(
            ['git', 'add', '-A'],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"git add failed: {result.stderr[:200]}")
            return False

        # Build commit message from session summary
        commit_title = "Session work"
        commit_body = ""

        if session_summary:
            # Use task types and skills for a descriptive title
            types = session_summary.get('task_types', [])
            if types:
                commit_title = ', '.join(types[:3])

            # Build body from requests
            requests = session_summary.get('requests', [])
            if requests:
                body_lines = []
                for req in requests:
                    prompt = req.get('prompt', '')[:100]
                    if prompt:
                        body_lines.append(f"- {prompt}")
                if body_lines:
                    commit_body = '\n'.join(body_lines[:10])

        commit_msg = commit_title
        if commit_body:
            commit_msg = commit_title + '\n\n' + commit_body

        result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root
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


def _push_branch(repo_root, branch_name):
    """Push the branch to remote. Returns True on success."""
    try:
        result = subprocess.run(
            ['git', 'push', '-u', 'origin', branch_name],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
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
            types = session_summary.get('task_types', [])
            skills = session_summary.get('skills_used', [])
            if types:
                pr_title = ', '.join(types[:3])
            elif skills:
                pr_title = 'Work with ' + ', '.join(skills[:2])

        # Truncate title
        if len(pr_title) > 70:
            pr_title = pr_title[:67] + '...'

        # Build PR body
        body_parts = ['## Summary\n']

        # Add work stories from session summary
        if session_summary:
            requests = session_summary.get('requests', [])
            if requests:
                for req in requests[:10]:
                    prompt = req.get('prompt', '')[:120]
                    task_type = req.get('task_type', '')
                    if prompt:
                        line = f"- {prompt}"
                        if task_type:
                            line += f" ({task_type})"
                        body_parts.append(line)
                body_parts.append('')

            # Stats
            req_count = session_summary.get('request_count', 0)
            max_complexity = session_summary.get('max_complexity', 0)
            skills = session_summary.get('skills_used', [])
            if req_count or max_complexity or skills:
                body_parts.append('## Session Stats\n')
                if req_count:
                    body_parts.append(f"- **Requests:** {req_count}")
                if max_complexity:
                    body_parts.append(f"- **Max Complexity:** {max_complexity}/25")
                if skills:
                    body_parts.append(f"- **Skills:** {', '.join(skills)}")
                body_parts.append('')

        # Close issues
        if issue_numbers:
            body_parts.append('## Issues\n')
            for num in issue_numbers:
                body_parts.append(f"Closes #{num}")
            body_parts.append('')

        body_parts.append('---')
        body_parts.append('_Auto-created by Claude Memory System (GitHub PR Workflow)_')

        pr_body = '\n'.join(body_parts)

        # Create PR via gh CLI
        cmd = [
            'gh', 'pr', 'create',
            '--title', pr_title,
            '--body', pr_body,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )

        if result.returncode == 0 and result.stdout.strip():
            pr_url = result.stdout.strip()
            _log(f"PR created: {pr_url}")

            # Extract PR number from URL
            pr_number = None
            if '/pull/' in pr_url:
                num_str = pr_url.rsplit('/pull/', 1)[1].strip()
                if num_str.isdigit():
                    pr_number = int(num_str)

            # Save PR info to mapping
            mapping = _load_issues_mapping()
            mapping['pr_number'] = pr_number
            mapping['pr_url'] = pr_url
            mapping['pr_created_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
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


def _auto_review_pr(repo_root, pr_number, session_summary, build_result=None):
    """
    Post an auto-review comment on the PR with session metrics and build status.
    Uses gh pr comment (not gh pr review --approve to avoid branch protection issues).
    """
    try:
        if not pr_number:
            return

        # Build review comment
        comment_parts = ['## Auto-Review (Claude Memory System)\n']

        if session_summary:
            req_count = session_summary.get('request_count', 0)
            max_complexity = session_summary.get('max_complexity', 0)
            avg_complexity = session_summary.get('avg_complexity', 0)
            skills = session_summary.get('skills_used', [])
            task_types = session_summary.get('task_types', [])
            projects = session_summary.get('projects_touched', [])

            comment_parts.append('### Session Metrics\n')
            comment_parts.append(f"| Metric | Value |")
            comment_parts.append(f"|--------|-------|")
            if req_count:
                comment_parts.append(f"| Requests | {req_count} |")
            if task_types:
                comment_parts.append(f"| Task Types | {', '.join(task_types)} |")
            if max_complexity:
                comment_parts.append(f"| Max Complexity | {max_complexity}/25 |")
            if avg_complexity:
                comment_parts.append(f"| Avg Complexity | {avg_complexity:.1f}/25 |")
            if skills:
                comment_parts.append(f"| Skills Used | {', '.join(skills)} |")
            if projects:
                comment_parts.append(f"| Projects | {', '.join(projects)} |")
            comment_parts.append('')

            # Work stories
            requests = session_summary.get('requests', [])
            if requests:
                comment_parts.append('### Work Done\n')
                for req in requests[:10]:
                    prompt = req.get('prompt', '')[:120]
                    task_type = req.get('task_type', '')
                    model = req.get('model', '')
                    if prompt:
                        line = f"- {prompt}"
                        if task_type:
                            line += f" [{task_type}]"
                        if model:
                            line += f" (model: {model})"
                        comment_parts.append(line)
                comment_parts.append('')

        # Load tool stats from session progress
        try:
            if SESSION_STATE_FILE.exists():
                with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                tool_counts = progress.get('tool_counts', {})
                tasks_completed = progress.get('tasks_completed', 0)
                if tool_counts:
                    total_tools = sum(tool_counts.values())
                    comment_parts.append('### Tool Usage\n')
                    comment_parts.append(f"- **Total tool calls:** {total_tools}")
                    comment_parts.append(f"- **Tasks completed:** {tasks_completed}")
                    top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    for tool, count in top_tools:
                        comment_parts.append(f"- {tool}: {count}")
                    comment_parts.append('')
        except Exception:
            pass

        # Build validation results
        if build_result:
            comment_parts.append('### Build Status\n')
            if build_result.get('all_passed'):
                comment_parts.append('**Status:** PASSED')
            else:
                comment_parts.append('**Status:** FAILED')
            for r in build_result.get('results', []):
                status = 'PASS' if r['passed'] else 'FAIL'
                if r.get('skipped'):
                    status = 'SKIP'
                comment_parts.append(f"- {r['label']}: **{status}**")
                if not r['passed'] and r.get('output'):
                    # Include first 500 chars of error in review
                    error_preview = r['output'][:500].replace('\n', '\n  > ')
                    comment_parts.append(f"  > {error_preview}")
            comment_parts.append('')

        comment_parts.append('---')
        comment_parts.append('_Auto-review by Claude Memory System_')

        comment_body = '\n'.join(comment_parts)

        result = subprocess.run(
            ['gh', 'pr', 'comment', str(pr_number), '--body', comment_body],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )

        if result.returncode == 0:
            _log(f"Auto-review comment posted on PR #{pr_number}")
            sys.stdout.write(f"[GH] Auto-review posted on PR #{pr_number}\n")
            sys.stdout.flush()
        else:
            _log(f"Review comment failed: {result.stderr[:200]}")

    except Exception as e:
        _log(f"Auto-review error: {e}")


def _bump_version_and_changelog(repo_root, session_summary, issue_numbers):
    """
    Auto-bump VERSION (patch) and add CHANGELOG entry.
    Enforces version-release-policy.md requirement that every code push
    must update VERSION and CHANGELOG.
    Returns True if files were modified.
    """
    try:
        version_file = Path(repo_root) / 'VERSION'
        changelog_file = Path(repo_root) / 'docs' / 'CHANGELOG-SYSTEM.md'

        if not version_file.exists():
            _log("No VERSION file found - skipping version bump")
            return False

        # Read current version
        current_version = version_file.read_text(encoding='utf-8').strip()
        parts = current_version.split('.')
        if len(parts) != 3:
            _log(f"Invalid version format: {current_version}")
            return False

        # Patch increment
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        new_version = f"{major}.{minor}.{patch + 1}"

        # Write new VERSION
        version_file.write_text(new_version + '\n', encoding='utf-8')
        _log(f"VERSION bumped: {current_version} -> {new_version}")

        # Build changelog entry from session summary
        today = datetime.now().strftime('%Y-%m-%d')
        entry_lines = [f"- v{new_version} ({today}): "]

        if session_summary:
            types = session_summary.get('task_types', [])
            if types:
                entry_lines[0] += ', '.join(types[:3])
            else:
                entry_lines[0] += 'Session updates'

            requests = session_summary.get('requests', [])
            for req in requests[:5]:
                prompt = req.get('prompt', '')[:100]
                if prompt:
                    entry_lines.append(f"  - {prompt}")
        else:
            entry_lines[0] += 'Session updates'

        if issue_numbers:
            closes_str = ', '.join(f"#{n}" for n in issue_numbers)
            entry_lines.append(f"  - Closes: {closes_str}")

        entry_text = '\n'.join(entry_lines) + '\n'

        # Prepend to CHANGELOG (after header)
        if changelog_file.exists():
            content = changelog_file.read_text(encoding='utf-8')
            # Insert after the "---" separator (after the header)
            sep_idx = content.find('---\n')
            if sep_idx >= 0:
                insert_pos = sep_idx + 4  # After "---\n"
                new_content = content[:insert_pos] + '\n' + entry_text + content[insert_pos:]
                changelog_file.write_text(new_content, encoding='utf-8')
                _log(f"CHANGELOG updated with v{new_version} entry")
            else:
                # No separator, just prepend after first line
                new_content = content.split('\n', 1)
                if len(new_content) == 2:
                    changelog_file.write_text(
                        new_content[0] + '\n' + entry_text + new_content[1],
                        encoding='utf-8'
                    )
        else:
            _log("No CHANGELOG file found - skipping changelog update")

        return True

    except Exception as e:
        _log(f"Version bump error: {e}")
        return False


def _merge_pr(repo_root, pr_number):
    """
    Merge the PR via gh CLI. Falls back to leaving PR open if merge fails.
    Returns True if merged successfully.
    """
    try:
        if not pr_number:
            return False

        result = subprocess.run(
            ['gh', 'pr', 'merge', str(pr_number), '--merge', '--delete-branch'],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )

        if result.returncode == 0:
            _log(f"PR #{pr_number} merged successfully")
            sys.stdout.write(f"[GH] PR #{pr_number} merged\n")
            sys.stdout.flush()

            # Update mapping
            mapping = _load_issues_mapping()
            mapping['pr_merged'] = True
            mapping['pr_merged_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            _save_issues_mapping(mapping)

            return True
        else:
            _log(f"PR merge failed (branch protection?): {result.stderr[:200]}")
            sys.stdout.write(f"[GH] PR #{pr_number} left open (merge blocked, needs manual review)\n")
            sys.stdout.flush()
            return False

    except Exception as e:
        _log(f"Merge error: {e}")
        return False


def _switch_to_main(repo_root):
    """Switch back to main/master branch and pull latest."""
    try:
        # Detect default branch
        default_branch = 'main'
        result = subprocess.run(
            ['git', 'remote', 'show', 'origin'],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('HEAD branch:'):
                    default_branch = line.split(':', 1)[1].strip()
                    break

        # Checkout default branch
        result = subprocess.run(
            ['git', 'checkout', default_branch],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"Checkout {default_branch} failed: {result.stderr[:200]}")
            return

        # Pull latest
        subprocess.run(
            ['git', 'pull', '--ff-only'],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root
        )

        _log(f"Switched to {default_branch} and pulled latest")

    except Exception as e:
        _log(f"Switch to main error: {e}")


def run_pr_workflow(session_id=None):
    """
    Main PR workflow orchestrator. Runs the full flow:
      0. Build validation
      0.5. Version bump + CHANGELOG update (enforces version-release-policy)
      1. Commit any uncommitted changes (includes version bump)
      2. Push branch to remote
      3. Create PR with session summary body + Closes #N
      4. Post auto-review comment with session metrics
      5. Merge PR (fallback: leave open)
      6. Switch back to main

    Called from stop-notifier.py when .session-work-done flag exists.
    Non-blocking: all steps wrapped in try/except, never raises.
    Returns True if PR was merged successfully, False otherwise.
    """
    _log("=== PR Workflow Starting ===")

    try:
        # Check prerequisites
        repo_root = _get_repo_root()
        if not repo_root:
            _log("Not in a git repo - skipping PR workflow")
            return False

        branch_name = _get_current_branch(repo_root)
        if not branch_name:
            _log("Could not determine current branch - skipping")
            return False

        # Only proceed if on an issue branch (not main/master)
        if branch_name in ('main', 'master'):
            _log(f"On {branch_name} branch - no PR workflow needed")
            return False

        _log(f"Branch: {branch_name}")

        # Check if gh CLI is available
        try:
            result = subprocess.run(
                ['gh', 'auth', 'status'],
                capture_output=True, text=True, timeout=GH_TIMEOUT
            )
            if result.returncode != 0:
                _log("gh CLI not authenticated - skipping PR workflow")
                return
        except Exception:
            _log("gh CLI not available - skipping PR workflow")
            return

        # Load session data
        session_summary = _load_session_summary()
        issue_numbers = _get_issue_numbers()

        # Step 0: Build validation (before commit)
        build_result = None
        _log("Step 0: Build validation...")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            import auto_build_validator
            build_result = auto_build_validator.validate_build(repo_root)
            if build_result['all_passed']:
                _log("Build OK: " + build_result['summary'])
                sys.stdout.write("[BUILD] " + build_result['summary'] + "\n")
                sys.stdout.flush()
            else:
                _log("Build FAILED: " + build_result['summary'])
                sys.stdout.write("[BUILD FAILED] " + build_result['summary'] + "\n")
                sys.stdout.flush()
                # Log errors but don't stop the workflow - PR will show build status
                for r in build_result['results']:
                    if not r['passed']:
                        _log("  " + r['label'] + ": " + r.get('output', '')[:300])
        except Exception as e:
            _log(f"Build validation error (non-fatal): {e}")

        # Step 0.5: Version bump + CHANGELOG update (enforces version-release-policy)
        _log("Step 0.5: Version bump + CHANGELOG...")
        _bump_version_and_changelog(repo_root, session_summary, issue_numbers)

        # Step 1: Commit changes (includes version bump if successful)
        _log("Step 1: Committing changes...")
        _commit_session_changes(repo_root, session_summary)

        # Step 2: Push branch
        _log("Step 2: Pushing branch...")
        pushed = _push_branch(repo_root, branch_name)
        if not pushed:
            _log("Push failed - cannot create PR without remote branch")
            return

        # Step 3: Create PR
        _log("Step 3: Creating PR...")
        pr_number = _create_pull_request(repo_root, branch_name, issue_numbers, session_summary)
        if not pr_number:
            _log("PR creation failed - stopping workflow")
            return

        # Step 4: Auto-review comment (includes build status)
        _log("Step 4: Posting auto-review...")
        _auto_review_pr(repo_root, pr_number, session_summary, build_result)

        # Step 5: Merge PR
        _log("Step 5: Merging PR...")
        merged = _merge_pr(repo_root, pr_number)

        # Step 6: Switch back to main (only if merged)
        if merged:
            _log("Step 6: Switching to main...")
            _switch_to_main(repo_root)
            _log("=== PR Workflow Complete (MERGED) ===")
            return True
        else:
            _log("Step 6: Skipped (PR not merged, staying on branch)")
            _log("=== PR Workflow Complete (NOT MERGED) ===")
            return False

    except Exception as e:
        _log(f"PR Workflow error: {e}")
        return False


if __name__ == '__main__':
    run_pr_workflow()
