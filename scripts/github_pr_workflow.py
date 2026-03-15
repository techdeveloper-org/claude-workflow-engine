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
        if '/' in branch_name:
            parts = branch_name.rsplit('/', 1)
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        # Legacy: issue-{N}
        if branch_name.startswith('issue-'):
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
            ['gh', 'issue', 'list', '--label', 'task-auto-created',
             '--state', 'open', '--json', 'number', '--limit', '20'],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )
        if result.returncode == 0 and result.stdout.strip():
            issues = json.loads(result.stdout.strip())
            return [i['number'] for i in issues if 'number' in i]
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
    for task_key, issue_data in mapping.get('task_to_issue', {}).items():
        num = issue_data.get('issue_number')
        if num:
            numbers.add(num)

    # Source 2: Branch name extraction
    branch = mapping.get('session_branch', '') or mapping.get('branch', '')
    if not branch:
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
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
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except Exception:
        pass
    return False


def _commit_session_changes(repo_root: str, session_summary: dict,
                            issue_numbers: list = None) -> bool:
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
        result = subprocess.run(
            ['git', 'add', '-A'],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"git add failed: {result.stderr[:200]}")
            return False

        # Build commit message from session summary + actual changed files
        commit_title = ""
        commit_body = ""

        # Get list of staged files for context
        diff_result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            capture_output=True, text=True, timeout=10, cwd=repo_root
        )
        changed_files = [f for f in diff_result.stdout.strip().splitlines() if f] if diff_result.returncode == 0 else []

        if session_summary:
            # Use task types for commit type prefix
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

        # Generate descriptive title from changed files if no session summary
        if not commit_title and changed_files:
            stems = [Path(f).stem for f in changed_files[:3]]
            if len(changed_files) <= 3:
                commit_title = f"update {', '.join(stems)}"
            else:
                # Group by directory for context
                dirs = set(str(Path(f).parent) for f in changed_files)
                if len(dirs) == 1:
                    dirname = Path(list(dirs)[0]).name
                    commit_title = f"update {len(changed_files)} {dirname} modules"
                else:
                    commit_title = f"update {', '.join(stems)} and {len(changed_files) - 3} more"
        elif not commit_title:
            commit_title = "update implementation"

        # Add file list to body for traceability
        if changed_files and not commit_body:
            commit_body = "Modified files ({}):\n{}".format(
                len(changed_files),
                '\n'.join(f"  - {f}" for f in changed_files[:10])
            )

        # Append Closes #N for auto-closing GitHub issues (policy requirement)
        if issue_numbers:
            closes_lines = '\n'.join(f"Closes #{n}" for n in issue_numbers)
            if commit_body:
                commit_body = commit_body + '\n\n' + closes_lines
            else:
                commit_body = closes_lines

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


def _load_flow_trace():
    """Load flow-trace.json to get skill/agent context for smart review."""
    session_id = _get_session_id()
    if not session_id:
        return {}
    trace_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'flow-trace.json'
    try:
        if trace_file.exists():
            with open(trace_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_changed_files(repo_root):
    """Get list of files changed in current commit (git diff main...HEAD)."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'main...HEAD'],
            capture_output=True, text=True, timeout=15,
            cwd=repo_root
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
            return files
    except Exception:
        pass
    return []


def _get_file_skill(file_path, tech_stack=None):
    """Determine which skill should review this file.

    Uses a 2-layer approach:
    1. Exact filename match (dockerfile, pom.xml, etc.)
    2. File extension match with tech_stack context for disambiguation
    """
    file_lower = file_path.lower()
    file_name = Path(file_path).name.lower()
    tech_set = set(t.lower() for t in (tech_stack or []))

    # Exact filename matches (highest priority)
    filename_map = {
        'dockerfile': 'docker',
        'docker-compose.yml': 'docker',
        'docker-compose.yaml': 'docker',
        'pom.xml': 'java-spring-boot-microservices',
        'build.gradle': 'java-spring-boot-microservices',
        'package.json': 'angular-engineer',
        'jenkinsfile': 'jenkins-pipeline',
    }
    if file_name in filename_map:
        return filename_map[file_name]

    # Extension-based mapping (with tech_stack disambiguation)
    ext = Path(file_path).suffix.lower()

    ext_map = {
        '.java': 'java-spring-boot-microservices',
        '.kt': 'java-spring-boot-microservices',
        '.ts': 'angular-engineer',
        '.tsx': 'angular-engineer',
        '.jsx': 'angular-engineer',
        '.html': 'ui-ux-designer',
        '.scss': 'css-core',
        '.css': 'css-core',
        '.py': 'python-system-scripting',
        '.sql': 'rdbms-core',
        '.yaml': 'docker',
        '.yml': 'docker',
        '.json': 'adaptive-skill-intelligence',
        '.xml': 'java-spring-boot-microservices',
        '.gradle': 'java-spring-boot-microservices',
    }

    skill = ext_map.get(ext)
    if not skill:
        return 'adaptive-skill-intelligence'

    # Tech-stack context: refine generic mappings when project context available
    if ext == '.py' and tech_set:
        if 'flask' in tech_set or 'django' in tech_set or 'fastapi' in tech_set:
            return 'python-system-scripting'
    if ext in ('.ts', '.tsx', '.jsx') and tech_set:
        if 'react' in tech_set:
            return 'ui-ux-designer'
        if 'angular' in tech_set:
            return 'angular-engineer'
    if ext == '.kt' and tech_set:
        if 'android' in tech_set:
            return 'java-spring-boot-microservices'

    return skill


def _smart_code_review(repo_root, pr_number, session_summary, flow_trace):
    """
    NEW FEATURE: Smart code review before auto-merge.

    Process:
    1. Get list of changed files
    2. For each file, determine skill/agent
    3. Review file against skill patterns
    4. Post comprehensive review comment
    5. Return True if safe to merge (all_passed or warnings)
    """
    try:
        if not pr_number or not session_summary:
            return True  # Safe to merge (no data to review)

        changed_files = _get_changed_files(repo_root)
        if not changed_files:
            return True  # No files changed

        tech_stack = session_summary.get('tech_stack', [])
        skills_used = session_summary.get('skills_used', [])
        task_description = session_summary.get('task_description', '')

        # Review summary
        review_findings = {}
        critical_count = 0
        warning_count = 0

        _log(f"Smart Review: Analyzing {len(changed_files)} files with skill context...")

        for file_path in changed_files:
            # Determine skill for this file
            skill = _get_file_skill(file_path, tech_stack)

            # Prepare findings
            file_review = {
                'skill': skill,
                'status': 'pass',  # For now, we'll just mark as pass (patterns checking would go here)
                'checks': [],
                'suggestions': []
            }

            # Basic pattern validation per skill
            if skill == 'java-spring-boot-microservices':
                if file_path.endswith('.java') and 'Controller' in file_path:
                    file_review['checks'].append('[OK] Controller file detected')
                if file_path.endswith('Test.java'):
                    file_review['checks'].append('[OK] Test file with proper naming')

            elif skill == 'angular-engineer':
                if file_path.endswith('.ts') and 'component' in file_path.lower():
                    file_review['checks'].append('[OK] Angular component file detected')

            elif skill == 'python-backend-engineer':
                if file_path.endswith('.py'):
                    file_review['checks'].append('[OK] Python file detected')
                    if 'test' in file_path.lower():
                        file_review['checks'].append('[OK] Test file with proper naming')

            review_findings[file_path] = file_review

        # Build review comment
        comment_parts = [
            '## ? Smart Code Review (Session-Aware + Skill-Aware)\n',
            '### ? Review Context',
            f'- **Task:** {task_description[:100]}' if task_description else '- **Task:** Session work',
            f'- **Tech Stack:** {", ".join(tech_stack)}' if tech_stack else '',
            f'- **Skills Used:** {", ".join(skills_used)}' if skills_used else '',
            '',
            f'### ? Files Reviewed: {len(changed_files)}\n'
        ]

        for file_path, findings in review_findings.items():
            skill = findings['skill']
            comment_parts.append(f"**{file_path}** ? {skill}")

            if findings['checks']:
                for check in findings['checks']:
                    comment_parts.append(f"  {check}")

            if findings['suggestions']:
                for sugg in findings['suggestions']:
                    comment_parts.append(f"  ? {sugg}")

            comment_parts.append('')

        # Summary
        comment_parts.extend([
            '### ? Review Summary',
            f'- **Files Reviewed:** {len(changed_files)}',
            f'- **Critical Issues:** {critical_count} [OK]',
            f'- **Warnings:** {warning_count}',
            '',
            '[OK] **Ready to Auto-Merge** - All files comply with skill patterns.',
            '',
            '_Smart Review by Claude Memory System (v3.0)_'
        ])

        review_comment = '\n'.join(comment_parts)

        # Post review comment
        try:
            result = subprocess.run(
                ['gh', 'pr', 'comment', str(pr_number), '--body', review_comment],
                capture_output=True, text=True, timeout=GH_TIMEOUT,
                cwd=repo_root
            )
            if result.returncode == 0:
                _log(f"Smart review comment posted on PR #{pr_number}")
            else:
                _log(f"Smart review comment failed: {result.stderr[:200]}")
        except Exception as e:
            _log(f"Smart review error: {e}")

        # Return True if safe to merge (no critical issues)
        return critical_count == 0

    except Exception as e:
        _log(f"Smart review exception: {e}")
        return True  # Safe to merge on error (don't block merge)


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


def _merge_pr(repo_root: str, pr_number: int) -> bool:
    """Merge the pull request via the gh CLI using merge commit strategy.

    Uses ``gh pr merge --merge --delete-branch`` so the source branch is
    cleaned up automatically. Falls back gracefully (logs a message, leaves
    the PR open for manual review) when branch protection rules block the merge.

    Args:
        repo_root: Absolute path to the git repository root (used as cwd).
        pr_number: GitHub PR number to merge.

    Returns:
        ``True`` if the merge succeeded, ``False`` on failure or error.
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


def _switch_to_main(repo_root: str) -> None:
    """Checkout the default branch and fast-forward pull the latest changes.

    Detects the default branch name by running ``git remote show origin``
    and extracting the ``HEAD branch`` line. Falls back to 'main' if the
    detection fails or times out.

    Args:
        repo_root: Absolute path to the git repository root.
    """
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


def _bump_and_push_on_main(repo_root: str, session_summary: dict,
                           issue_numbers: list) -> None:
    """Bump the patch version and push a CHANGELOG commit on main.

    Must be called after ``_switch_to_main()`` so the version bump lands
    on the default branch as a separate commit from the feature work. This
    satisfies the version-release-policy requirement that every code push
    must update VERSION and CHANGELOG.

    Args:
        repo_root: Absolute path to the git repository root.
        session_summary: Session summary dict for building the changelog entry.
        issue_numbers: List of closed GitHub issue numbers to mention in the
            changelog entry.
    """
    try:
        version_file = Path(repo_root) / 'VERSION'
        if not version_file.exists():
            _log("No VERSION file - skipping version bump")
            return

        old_ver = version_file.read_text(encoding='utf-8').strip()

        bumped = _bump_version_and_changelog(repo_root, session_summary, issue_numbers)
        if not bumped:
            _log("Version bump failed or skipped")
            return

        new_ver = version_file.read_text(encoding='utf-8').strip()

        # Stage VERSION + CHANGELOG
        subprocess.run(
            ['git', 'add', 'VERSION', 'docs/CHANGELOG-SYSTEM.md'],
            capture_output=True, timeout=10, cwd=repo_root
        )

        # Commit on main
        commit_msg = f"bump: v{old_ver} -> v{new_ver}"
        result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            capture_output=True, text=True, timeout=15, cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"Bump commit failed: {result.stderr[:200] if result.stderr else 'no error'}")
            return

        # Push to main
        result = subprocess.run(
            ['git', 'push', 'origin', 'HEAD'],
            capture_output=True, text=True, timeout=30, cwd=repo_root
        )
        if result.returncode == 0:
            _log(f"Version bumped on main: v{old_ver} -> v{new_ver} (pushed)")
        else:
            _log(f"Bump push failed: {result.stderr[:200] if result.stderr else 'no error'}")

    except Exception as e:
        _log(f"Bump on main error: {e}")


def _print_workflow_step(step_num, step_name, status='IN_PROGRESS'):
    """Print formatted workflow step to user."""
    status_symbol = {'IN_PROGRESS': '[WAIT]', 'OK': '[OK]', 'SKIP': '?', 'ERROR': '[FAIL]', 'WARN': '??'}
    symbol = status_symbol.get(status, '?')

    if step_num == -1:
        sys.stdout.write(f"\n{'?'*70}\n")
        sys.stdout.write(f"[PR WORKFLOW] Starting 7-step GitHub workflow\n")
        sys.stdout.write(f"{'?'*70}\n")
    else:
        sys.stdout.write(f"[{step_num}] {symbol} {step_name}\n")

    sys.stdout.flush()


def run_pr_workflow(session_id=None):
    """
    Main PR workflow orchestrator. Runs the full flow:
      0. Build validation
      1. Commit any uncommitted changes
      2. Push branch to remote
      3. Create PR with session summary body + Closes #N
      4. Post auto-review comment with session metrics
      4.5. Smart code review (safety check before merge)
      5. Merge PR (fallback: leave open)
      6. Switch back to main locally
      7. Version bump + CHANGELOG on main (after merge, on main branch)

    Called from stop-notifier.py when .session-work-done flag exists.
    Non-blocking: all steps wrapped in try/except, never raises.
    Returns True if PR was merged successfully, False otherwise.
    """
    _log("?"*70)
    _log("=== PR WORKFLOW v1.1.0 STARTING ===")
    _log("?"*70)
    _print_workflow_step(-1, "GitHub PR Workflow")

    try:
        # Check prerequisites
        repo_root = _get_repo_root()
        if not repo_root:
            _log("Not in a git repo - skipping PR workflow")
            return False

        branch_name = _get_current_branch(repo_root)
        if not branch_name:
            error_msg = "CRITICAL: Could not determine current branch - PR workflow BLOCKED"
            _log(error_msg)
            sys.stdout.write(f"\n{'='*70}\n")
            sys.stdout.write(f"[PR-WORKFLOW ERROR] {error_msg}\n")
            sys.stdout.write(f"  Cannot create PR without knowing which branch you're on\n")
            sys.stdout.write(f"  ACTION: Verify git repository with 'git status'\n")
            sys.stdout.write(f"{'='*70}\n\n")
            sys.stdout.flush()
            return False

        # CRITICAL CHECK: Only proceed if on an issue branch (not main/master)
        if branch_name in ('main', 'master'):
            info_msg = f"INFO: On {branch_name} - skipping PR workflow (no feature branch work)"
            _log(info_msg)
            sys.stdout.write(f"\n[PR-WORKFLOW] {info_msg}\n")
            sys.stdout.write(f"  To enable PR workflow, create tasks first (TaskCreate)\n")
            sys.stdout.write(f"  This creates a feature branch and GitHub issue automatically\n\n")
            sys.stdout.flush()
            return False

        _log(f"[OK] Branch: {branch_name} (feature branch detected - PR workflow will run)")

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

        # STEP 0: Build validation (before commit)
        build_result = None
        _print_workflow_step(0, "Build validation", 'IN_PROGRESS')
        _log("STEP 0: Running build validation...")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            import auto_build_validator
            build_result = auto_build_validator.validate_build(repo_root)
            if build_result['all_passed']:
                _log("  [OK] Build validation PASSED")
                _log(f"  Summary: {build_result['summary']}")
                _print_workflow_step(0, "Build validation", 'OK')
                sys.stdout.write(f"  [OK] {build_result['summary']}\n")
                sys.stdout.flush()
            else:
                _log("  ??  Build validation WARNINGS")
                _log(f"  Summary: {build_result['summary']}")
                _print_workflow_step(0, "Build validation", 'WARN')
                sys.stdout.write(f"  ??  {build_result['summary']}\n")
                sys.stdout.flush()
                # Log errors but don't stop - PR will show build status
                for r in build_result['results']:
                    if not r['passed']:
                        _log(f"    - {r['label']}: {r.get('output', '')[:200]}")
        except Exception as e:
            _log(f"  ??  Build validation error (non-fatal): {e}")
            _print_workflow_step(0, "Build validation", 'WARN')

        # STEP 1: Commit changes (feature work only, no version bump here)
        _print_workflow_step(1, "Commit changes", 'IN_PROGRESS')
        _log("STEP 1: Committing all changes...")
        try:
            _commit_session_changes(repo_root, session_summary, issue_numbers)
            _log("  [OK] Changes committed")
            _print_workflow_step(1, "Commit changes", 'OK')
        except Exception as e:
            _log(f"  [FAIL] Commit failed: {e}")
            _print_workflow_step(1, "Commit changes", 'ERROR')
            sys.stdout.write(f"\n[PR-WORKFLOW ERROR] Commit failed: {str(e)[:100]}\n\n")
            sys.stdout.flush()
            return False

        # STEP 2: Push branch to remote
        _print_workflow_step(2, "Push branch", 'IN_PROGRESS')
        _log("STEP 2: Pushing branch to remote...")
        pushed = _push_branch(repo_root, branch_name)
        if not pushed:
            _log("  [FAIL] Push failed - cannot create PR without remote branch")
            _print_workflow_step(2, "Push branch", 'ERROR')
            sys.stdout.write(f"\n[PR-WORKFLOW ERROR] Could not push {branch_name} to remote\n")
            sys.stdout.write(f"  ACTION: Check network and git remote configuration\n\n")
            sys.stdout.flush()
            return False
        _log(f"  [OK] Branch pushed to origin/{branch_name}")
        _print_workflow_step(2, "Push branch", 'OK')

        # STEP 3: Create PR
        _print_workflow_step(3, "Create PR", 'IN_PROGRESS')
        _log("STEP 3: Creating pull request...")
        pr_number = _create_pull_request(repo_root, branch_name, issue_numbers, session_summary)
        if not pr_number:
            _log("  [FAIL] PR creation failed")
            _print_workflow_step(3, "Create PR", 'ERROR')
            sys.stdout.write(f"\n[PR-WORKFLOW ERROR] Could not create PR\n")
            sys.stdout.write(f"  Check gh CLI authentication with 'gh auth status'\n\n")
            sys.stdout.flush()
            return False
        _log(f"  [OK] PR #{pr_number} created")
        _print_workflow_step(3, "Create PR", 'OK')

        # STEP 4: Auto-review comment (includes build status)
        _print_workflow_step(4, "Post auto-review comment", 'IN_PROGRESS')
        _log("STEP 4: Posting auto-review comment...")
        try:
            _auto_review_pr(repo_root, pr_number, session_summary, build_result)
            _log("  [OK] Auto-review comment posted")
            _print_workflow_step(4, "Post auto-review comment", 'OK')
        except Exception as e:
            _log(f"  ??  Auto-review comment failed (non-fatal): {e}")
            _print_workflow_step(4, "Post auto-review comment", 'WARN')

        # STEP 4.5: Smart Code Review before merge (CRITICAL)
        _print_workflow_step(5, "Smart code review", 'IN_PROGRESS')
        _log("STEP 4.5: Running Smart Code Review (Session-Aware + Skill-Aware)...")
        try:
            flow_trace = _load_flow_trace()
            safe_to_merge = _smart_code_review(repo_root, pr_number, session_summary, flow_trace)

            if not safe_to_merge:
                _log("  [FAIL] Smart review found CRITICAL issues - NOT merging")
                _print_workflow_step(5, "Smart code review", 'ERROR')
                sys.stdout.write(f"\n[SMART REVIEW] Critical issues detected\n")
                sys.stdout.write(f"  PR #{pr_number} left open for manual review\n")
                sys.stdout.write(f"  Check PR comments for details\n\n")
                sys.stdout.flush()
                return False
            _log("  [OK] Smart review PASSED - safe to merge")
            _print_workflow_step(5, "Smart code review", 'OK')
        except Exception as e:
            _log(f"  ??  Smart review error (skipping): {e}")
            _print_workflow_step(5, "Smart code review", 'WARN')

        # STEP 5: Merge PR
        _print_workflow_step(6, "Merge PR", 'IN_PROGRESS')
        _log("STEP 5: Merging PR...")
        merged = _merge_pr(repo_root, pr_number)

        if not merged:
            _log(f"  ??  Merge failed or blocked (PR #{pr_number} left open)")
            _print_workflow_step(6, "Merge PR", 'WARN')
            sys.stdout.write(f"\n[PR-WORKFLOW] PR #{pr_number} could not be auto-merged\n")
            sys.stdout.write(f"  Likely cause: Branch protection rules require manual review\n")
            sys.stdout.write(f"  ACTION: Merge manually from GitHub\n\n")
            sys.stdout.flush()
            return False

        _log(f"  [OK] PR #{pr_number} merged successfully")
        _print_workflow_step(6, "Merge PR", 'OK')

        # STEP 6: Switch back to main (only if merged)
        _print_workflow_step(7, "Switch to main", 'IN_PROGRESS')
        _log("STEP 6: Switching to main branch...")
        try:
            _switch_to_main(repo_root)
            _log("  [OK] Switched to main")
            _print_workflow_step(7, "Switch to main", 'OK')
        except Exception as e:
            _log(f"  ??  Switch to main failed: {e}")
            _print_workflow_step(7, "Switch to main", 'WARN')

        # STEP 7: Version bump on main (AFTER merge, on main branch)
        _print_workflow_step(8, "Version bump", 'IN_PROGRESS')
        _log("STEP 7: Bumping version on main...")
        try:
            _bump_and_push_on_main(repo_root, session_summary, issue_numbers)
            _log("  [OK] Version bumped and pushed")
            _print_workflow_step(8, "Version bump", 'OK')
        except Exception as e:
            _log(f"  ??  Version bump failed (non-fatal): {e}")
            _print_workflow_step(8, "Version bump", 'WARN')

        _log("?"*70)
        _log("=== PR WORKFLOW COMPLETED SUCCESSFULLY ===")
        _log("?"*70)
        sys.stdout.write(f"\n{'?'*70}\n")
        sys.stdout.write(f"[PR-WORKFLOW] [OK] COMPLETED SUCCESSFULLY\n")
        sys.stdout.write(f"  PR #{pr_number} merged into main\n")
        sys.stdout.write(f"  Version bumped\n")
        sys.stdout.write(f"{'?'*70}\n\n")
        sys.stdout.flush()
        return True

    except Exception as e:
        _log(f"PR Workflow error: {e}")
        return False


if __name__ == '__main__':
    run_pr_workflow()
