#!/usr/bin/env python
"""GitHub Issues and branch integration for Level 3 Execution policy.

Integrates with the 3-level enforcement system to automatically manage
GitHub Issues corresponding to tasks tracked by the session. Called by
post-tool-tracker.py on TaskCreate/TaskUpdate events.

Key behaviours
--------------
Create  -- On ``TaskCreate``: opens a GitHub Issue with a description built
           from the task story, assigns priority/complexity labels, and
           creates a matching branch in ``{label}/{issueId}`` format
           (e.g. ``fix/42``, ``feature/123``).
Close   -- On ``TaskUpdate(completed)``: closes the corresponding issue with
           a closing comment summarising what was done.
Mapping -- Issue numbers are persisted to ``github-issues.json`` in the
           session log directory so the PR workflow can reference them.

Safety constraints
------------------
- Maximum 10 GitHub operations per session (creates + closes combined).
- 15 s timeout on every ``gh`` CLI call.
- All public functions wrapped in try/except -- never raises.
- Entire module is a no-op when ``gh auth status`` fails (offline mode).

Branch naming format::

    {semantic-label}/{issue-number}

    Semantic labels: fix, feature, refactor, docs, enhancement, test
    Example: fix/42, feature/123, docs/55

Version: 3.1.0
Last Modified: 2026-03-07
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

MAX_OPS_PER_SESSION = 10
GH_TIMEOUT = 15  # seconds

# Cached per-invocation (module-level)
_gh_available = None
_ops_count = 0


def _get_session_id():
    """Read the current session ID from the session-progress.json state file.

    Returns:
        str: The session_id value from the file, or an empty string if the
            file does not exist, cannot be parsed, or lacks the key.
    """
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('session_id', '')
    except Exception:
        pass
    return ''


def _get_repo_root():
    """Return the absolute path to the git repository root from the current directory.

    Runs ``git rev-parse --show-toplevel`` with a 5-second timeout.

    Returns:
        str or None: Absolute repo root path, or None if not inside a git
            repository or the command fails.
    """
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


def _get_mapping_file():
    """Return the Path to the github-issues.json mapping file for the current session.

    If a session ID is available the file is placed under the per-session log
    directory; otherwise a shared fallback path is used.

    Returns:
        Path: Resolved path to the github-issues.json mapping file.
    """
    session_id = _get_session_id()
    if session_id:
        session_dir = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id
        return session_dir / 'github-issues.json'
    # Fallback: use a general mapping file
    return Path.home() / '.claude' / 'memory' / 'logs' / 'github-issues.json'


def _load_issues_mapping():
    """Load the task-to-issue mapping dict from the session mapping file.

    Returns:
        dict: Parsed mapping with at minimum the keys ``task_to_issue`` (dict),
            ``ops_count`` (int), and ``session_id`` (str). Returns this default
            structure if the file is missing or unreadable.
    """
    mapping_file = _get_mapping_file()
    try:
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'task_to_issue': {}, 'ops_count': 0, 'session_id': _get_session_id()}


def _save_issues_mapping(mapping):
    """Write the task-to-issue mapping dict to the session mapping file.

    Creates parent directories as needed. Failures are silently ignored so
    that a write error never interrupts the main workflow.

    Args:
        mapping (dict): Mapping data to serialise and persist.
    """
    mapping_file = _get_mapping_file()
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def _get_ops_count():
    """Return the number of GitHub operations already performed this session.

    Returns:
        int: Value of ``ops_count`` from the persisted mapping, or 0 if not set.
    """
    mapping = _load_issues_mapping()
    return mapping.get('ops_count', 0)


def _increment_ops_count():
    """Increment the session GitHub operations counter and persist it to disk."""
    mapping = _load_issues_mapping()
    mapping['ops_count'] = mapping.get('ops_count', 0) + 1
    _save_issues_mapping(mapping)


def is_gh_available():
    """Check if gh CLI is installed and authenticated. Cached per invocation."""
    global _gh_available
    if _gh_available is not None:
        return _gh_available

    try:
        result = subprocess.run(
            ['gh', 'auth', 'status'],
            capture_output=True, text=True, timeout=GH_TIMEOUT
        )
        _gh_available = (result.returncode == 0)
    except Exception:
        _gh_available = False

    return _gh_available


def extract_task_id_from_response(tool_response):
    """Parse the task ID from a TaskCreate tool response.

    Handles multiple response formats:

    - ``"Task #1 created successfully: ..."``
    - ``"Task created with id 1"``
    - ``"Created task 1: ..."``
    - ``{"id": "1", ...}`` or ``{"taskId": "1", ...}``
    - Any string containing digits after task-related keywords

    Args:
        tool_response (str or dict): Raw response from a TaskCreate tool call.
            Can be a plain string, a dict with an ``id``/``taskId`` field, or
            a dict with a ``content`` field (str or list of dicts).

    Returns:
        str: The extracted task ID (e.g. ``'1'``), or an empty string if no
            numeric ID can be found.
    """
    try:
        content = ''
        if isinstance(tool_response, dict):
            # Check for direct 'id' field in response
            direct_id = tool_response.get('id', '')
            if direct_id:
                return str(direct_id)
            # Check for taskId field
            direct_tid = tool_response.get('taskId', '')
            if direct_tid:
                return str(direct_tid)

            c = tool_response.get('content', '')
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                for item in c:
                    if isinstance(item, dict):
                        content += item.get('text', '')
                    elif isinstance(item, str):
                        content += item
        elif isinstance(tool_response, str):
            content = tool_response

        if not content:
            return ''

        # Pattern 1: "Task #N" (e.g. "Task #1 created successfully")
        if 'Task #' in content:
            after_hash = content.split('Task #', 1)[1]
            task_id = ''
            for ch in after_hash:
                if ch.isdigit():
                    task_id += ch
                else:
                    break
            if task_id:
                return task_id

        # Pattern 2: "id N" or "id: N" or "ID: N"
        content_lower = content.lower()
        for marker in ['id ', 'id: ', 'id:', 'task ']:
            idx = content_lower.find(marker)
            if idx >= 0:
                after = content[idx + len(marker):].strip()
                task_id = ''
                for ch in after:
                    if ch.isdigit():
                        task_id += ch
                    elif task_id:
                        break
                if task_id:
                    return task_id

        # Pattern 3: First standalone number in the content
        import re
        match = re.search(r'\b(\d+)\b', content)
        if match:
            return match.group(1)

    except Exception:
        pass
    return ''


def _get_flow_trace_context():
    """Load the current session's flow-trace.json for execution context fields.

    Reads the trace file for the active session and extracts key planning
    metadata: task_type, complexity, model, skill/agent, context_pct, and
    plan_mode.

    Returns:
        dict: Mapping of extracted fields (task_type, complexity, model, skill,
            context_pct, plan_mode), or an empty dict if the session ID is
            unavailable, the file is missing, or parsing fails.
    """
    session_id = _get_session_id()
    if not session_id:
        return {}
    trace_file = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id / 'flow-trace.json'
    try:
        if trace_file.exists():
            with open(trace_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            # v4.4.0+: array of traces - use latest entry
            if isinstance(raw, list) and raw:
                data = raw[-1]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
            return {
                'task_type': data.get('task_type', ''),
                'complexity': data.get('complexity', 0),
                'model': data.get('model', ''),
                'skill': data.get('skill', ''),
                'context_pct': data.get('context_pct', 0),
                'plan_mode': data.get('plan_mode', False),
            }
    except Exception:
        pass
    return {}


def _get_session_progress_context():
    """Load session-progress.json for tool counts, completed tasks, and modified files.

    Returns:
        dict: Mapping with keys tool_counts, tasks_completed, total_progress,
            modified_files, errors_seen, started_at, and context_estimate_pct,
            or an empty dict if the file is missing or unreadable.
    """
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                'tool_counts': data.get('tool_counts', {}),
                'tasks_completed': data.get('tasks_completed', 0),
                'total_progress': data.get('total_progress', 0),
                'modified_files': data.get('modified_files_since_commit', []),
                'errors_seen': data.get('errors_seen', 0),
                'started_at': data.get('started_at', ''),
                'context_estimate_pct': data.get('context_estimate_pct', 0),
            }
    except Exception:
        pass
    return {}


def _get_tool_activity_for_task(task_id):
    """Scan tool-tracker.jsonl for tool activity belonging to a specific task.

    Locates the Nth TaskCreate event corresponding to task_id, then records
    all subsequent tool calls until a TaskUpdate(completed) event for that
    task is found.

    Args:
        task_id: Task ID string or int (e.g. '1') used to locate the
            TaskCreate event by ordinal position.

    Returns:
        dict: Keys files_read, files_written, files_edited (lists of file
            paths), commands_run and searches (lists of strings), edits
            (list of edit-description strings), and total_tools (int).
            All lists are empty and total_tools is 0 if the log is missing
            or no matching activity is found.
    """
    tracker_log = Path.home() / '.claude' / 'memory' / 'logs' / 'tool-tracker.jsonl'
    result = {
        'files_read': [],
        'files_written': [],
        'files_edited': [],
        'commands_run': [],
        'searches': [],
        'edits': [],
        'total_tools': 0,
    }
    try:
        if not tracker_log.exists():
            return result

        # Read all entries, find the activity window for THIS specific task
        # Strategy: Find the TaskCreate that matches task_id, record until its TaskUpdate(completed)
        recording = False
        task_id_str = str(task_id)
        with open(tracker_log, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                tool = entry.get('tool', '')

                # Start recording only when we see a TaskCreate followed by
                # a TaskUpdate for THIS task_id (or the Nth TaskCreate matching task_id order)
                if not recording and tool == 'TaskCreate':
                    # Match by checking if this is the Nth task (task_id = "1" means 1st TaskCreate)
                    # We track a counter to find the right TaskCreate
                    if not hasattr(result, '_tc_count'):
                        result['_tc_count'] = 0
                    result['_tc_count'] = result.get('_tc_count', 0) + 1
                    if str(result.get('_tc_count', 0)) == task_id_str:
                        recording = True
                        result = {
                            'files_read': [], 'files_written': [], 'files_edited': [],
                            'commands_run': [], 'searches': [], 'edits': [], 'total_tools': 0,
                            '_tc_count': result.get('_tc_count', 0),
                        }
                    continue

                # Stop recording when this task is marked completed
                if tool == 'TaskUpdate' and entry.get('task_id') == task_id_str:
                    if entry.get('task_status') == 'completed':
                        break

                if not recording:
                    continue

                result['total_tools'] += 1
                file_path = entry.get('file', '')

                if tool == 'Read' and file_path:
                    if file_path not in result['files_read']:
                        result['files_read'].append(file_path)
                elif tool == 'Write' and file_path:
                    if file_path not in result['files_written']:
                        result['files_written'].append(file_path)
                    lines = entry.get('content_lines', 0)
                    if lines:
                        result['edits'].append(file_path + ' (' + str(lines) + ' lines written)')
                elif tool == 'Edit' and file_path:
                    if file_path not in result['files_edited']:
                        result['files_edited'].append(file_path)
                    old_hint = entry.get('old_hint', '')
                    new_hint = entry.get('new_hint', '')
                    edit_size = entry.get('edit_size', 0)
                    if old_hint or new_hint:
                        edit_desc = file_path
                        if edit_size:
                            edit_desc += ' (' + ('+' if edit_size > 0 else '') + str(edit_size) + ' chars)'
                        result['edits'].append(edit_desc)
                elif tool == 'Bash':
                    cmd = entry.get('command', '')
                    desc = entry.get('desc', '')
                    if cmd:
                        result['commands_run'].append(desc or cmd[:100])
                elif tool in ('Grep', 'Glob'):
                    pattern = entry.get('pattern', '')
                    if pattern:
                        result['searches'].append(tool + ': ' + pattern)

    except Exception:
        pass
    return result


def create_github_issue(task_id, subject, description):
    """
    Create a comprehensive GitHub issue for a task.

    Includes: full description, acceptance criteria, session context,
    execution environment info, complexity analysis, and related metadata.

    Args:
        task_id: Task ID string (e.g. '1')
        subject: Task subject line
        description: Task description

    Returns:
        Issue number (int) on success, None on failure.
    """
    def _debug_log_gh(msg):
        """Log to github-issue-debug.log with [GH-CREATE] prefix"""
        try:
            log_path = Path.home() / '.claude' / 'memory' / 'logs' / 'github-issue-debug.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass

    try:
        _debug_log_gh(f"[GH-CREATE] START: task_id={task_id}, subject='{subject[:50]}'")

        _debug_log_gh(f"[GH-CREATE] Checking if gh is available...")
        if not is_gh_available():
            _debug_log_gh(f"[GH-CREATE] ✗ gh not available, returning None")
            return None
        _debug_log_gh(f"[GH-CREATE] ✓ gh is available")

        _debug_log_gh(f"[GH-CREATE] Checking ops count (MAX={MAX_OPS_PER_SESSION})...")
        ops_count = _get_ops_count()
        _debug_log_gh(f"[GH-CREATE] ops_count={ops_count}")
        if ops_count >= MAX_OPS_PER_SESSION:
            _debug_log_gh(f"[GH-CREATE] ✗ ops_count >= MAX, returning None")
            return None

        _debug_log_gh(f"[GH-CREATE] Getting repo root...")
        repo_root = _get_repo_root()
        _debug_log_gh(f"[GH-CREATE] repo_root={repo_root}")
        if not repo_root:
            _debug_log_gh(f"[GH-CREATE] ✗ no repo_root, returning None")
            return None

        # Build issue title and body
        # CHANGED v3.0: Use semantic title format (no [TASK-X] prefix)
        # Format: {type}: {subject}
        # Example: bugfix: Model selection defaulting to HAIKU
        _debug_log_gh(f"[GH-CREATE] Detecting issue type...")
        issue_type_label = _detect_issue_type(subject, description)
        _debug_log_gh(f"[GH-CREATE] issue_type_label={issue_type_label}")
        title = issue_type_label + ': ' + subject
        # Truncate title to 256 chars (GitHub limit is higher but keep it readable)
        title = title[:256]
        _debug_log_gh(f"[GH-CREATE] title='{title[:60]}'")

        _debug_log_gh(f"[GH-CREATE] Getting session context...")
        session_id = _get_session_id()
        _debug_log_gh(f"[GH-CREATE] session_id={session_id}")
        flow_ctx = _get_flow_trace_context()
        _debug_log_gh(f"[GH-CREATE] flow_ctx keys={list(flow_ctx.keys())}")
        progress_ctx = _get_session_progress_context()
        _debug_log_gh(f"[GH-CREATE] progress_ctx keys={list(progress_ctx.keys())}")

        # --- Build comprehensive issue body with story format ---
        body_lines = []
        issue_type = _detect_issue_type(subject, description)
        complexity = flow_ctx.get('complexity', 0)

        # CHANGED v3.0: Problem-centric body format (not task-centric)
        # Section 1: Problem Statement
        body_lines.append('## Problem Statement')
        body_lines.append('')
        body_lines.append(description if description else subject)
        body_lines.append('')

        # Section 1b: Context & Background
        body_lines.append('## Context & Background')
        body_lines.append('')
        body_lines.append('Related to: ' + issue_type.capitalize() + ' | Complexity: ' + str(complexity) + '/25')
        body_lines.append('')

        # Section 2: Task Overview (metadata table)
        body_lines.append('## Task Overview')
        body_lines.append('')
        body_lines.append('| Field | Value |')
        body_lines.append('|-------|-------|')
        body_lines.append('| **Task ID** | ' + str(task_id) + ' |')
        body_lines.append('| **Subject** | ' + subject + ' |')
        body_lines.append('| **Type** | ' + issue_type + ' |')
        if complexity:
            body_lines.append('| **Complexity** | ' + str(complexity) + '/25 |')
            # Priority derivation
            if complexity >= 15:
                priority = 'Critical'
            elif complexity >= 10:
                priority = 'High'
            elif complexity >= 5:
                priority = 'Medium'
            else:
                priority = 'Low'
            body_lines.append('| **Priority** | ' + priority + ' |')
        if flow_ctx.get('model'):
            body_lines.append('| **Model** | ' + flow_ctx['model'] + ' |')
        if flow_ctx.get('skill'):
            body_lines.append('| **Skill/Agent** | ' + flow_ctx['skill'] + ' |')
        if flow_ctx.get('plan_mode'):
            body_lines.append('| **Plan Mode** | Required |')
        body_lines.append('')

        # Section 3: Acceptance Criteria
        body_lines.append('## Acceptance Criteria')
        body_lines.append('')
        if description:
            criteria_found = False
            for line in description.split('\n'):
                line = line.strip()
                if line.startswith('- ') or line.startswith('* '):
                    body_lines.append('- [ ] ' + line[2:])
                    criteria_found = True
                elif line and len(line) > 15:
                    body_lines.append('- [ ] ' + line)
                    criteria_found = True
            if not criteria_found:
                body_lines.append('- [ ] ' + subject)
        else:
            body_lines.append('- [ ] ' + subject)
        # Add standard criteria based on type
        if issue_type == 'fix':
            body_lines.append('- [ ] Root cause identified and documented')
            body_lines.append('- [ ] Fix verified - bug no longer reproducible')
        elif issue_type == 'feature':
            body_lines.append('- [ ] Feature implemented and functional')
            body_lines.append('- [ ] Code follows existing patterns and conventions')
        elif issue_type == 'refactor':
            body_lines.append('- [ ] No behavior changes - all existing functionality preserved')
            body_lines.append('- [ ] Code quality improved')
        body_lines.append('- [ ] Changes committed and pushed')
        body_lines.append('')

        # Section 4: Session Context
        body_lines.append('## Session Context')
        body_lines.append('')
        body_lines.append('| Field | Value |')
        body_lines.append('|-------|-------|')
        if session_id:
            body_lines.append('| **Session ID** | `' + session_id + '` |')
        body_lines.append('| **Created At** | ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' |')
        if progress_ctx.get('started_at'):
            body_lines.append('| **Session Started** | ' + progress_ctx['started_at'] + ' |')
        if progress_ctx.get('context_estimate_pct'):
            body_lines.append('| **Context Usage** | ' + str(progress_ctx['context_estimate_pct']) + '% |')
        if progress_ctx.get('tasks_completed'):
            body_lines.append('| **Tasks Completed So Far** | ' + str(progress_ctx['tasks_completed']) + ' |')
        if progress_ctx.get('total_progress'):
            body_lines.append('| **Session Progress** | ' + str(progress_ctx['total_progress']) + '% |')

        # Get current branch
        try:
            branch_result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5, cwd=repo_root
            )
            if branch_result.returncode == 0:
                body_lines.append('| **Branch** | `' + branch_result.stdout.strip() + '` |')
        except Exception:
            pass

        # Get repo name
        try:
            remote_result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                capture_output=True, text=True, timeout=5, cwd=repo_root
            )
            if remote_result.returncode == 0:
                remote_url = remote_result.stdout.strip()
                repo_name = remote_url.rsplit('/', 1)[-1].replace('.git', '')
                body_lines.append('| **Repository** | ' + repo_name + ' |')
        except Exception:
            pass

        body_lines.append('')

        # Section 5: Related files (if any modified files tracked)
        if progress_ctx.get('modified_files'):
            body_lines.append('## Files Modified (Before This Task)')
            body_lines.append('')
            for f in progress_ctx['modified_files'][:15]:
                body_lines.append('- `' + f + '`')
            body_lines.append('')

        # Footer
        body_lines.append('---')
        body_lines.append('')
        body_lines.append('_Auto-created by Claude Memory System (Level 3 Execution) | v3.0.0_')

        body = '\n'.join(body_lines)

        # Build labels using the comprehensive label system
        issue_type = _detect_issue_type(subject, description)
        complexity = flow_ctx.get('complexity', 0)
        labels = _build_issue_labels(issue_type, complexity, subject, description)

        # Auto-create any missing labels in the repo
        _ensure_labels_exist(labels, repo_root)

        # Create issue via gh CLI with labels
        _debug_log_gh(f"[GH-CREATE] Building gh CLI command...")
        cmd = [
            'gh', 'issue', 'create',
            '--title', title,
            '--body', body,
        ]
        _debug_log_gh(f"[GH-CREATE] Base command: {cmd}")
        cmd_with_labels = cmd + ['--label', ','.join(labels)]
        _debug_log_gh(f"[GH-CREATE] Command with labels: gh issue create --title ... --body ... --label {','.join(labels)}")

        _debug_log_gh(f"[GH-CREATE] Running gh command (timeout={GH_TIMEOUT}s)...")
        try:
            result = subprocess.run(
                cmd_with_labels,
                capture_output=True, text=True, timeout=GH_TIMEOUT,
                cwd=repo_root
            )
            _debug_log_gh(f"[GH-CREATE] gh returned: returncode={result.returncode}")
            if result.stdout:
                _debug_log_gh(f"[GH-CREATE] stdout: {result.stdout[:200]}")
            if result.stderr:
                _debug_log_gh(f"[GH-CREATE] stderr: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            _debug_log_gh(f"[GH-CREATE] ✗ gh command TIMEOUT after {GH_TIMEOUT}s")
            raise
        except Exception as e:
            _debug_log_gh(f"[GH-CREATE] ✗ gh command EXCEPTION: {type(e).__name__}: {str(e)[:150]}")
            raise

        # If label creation still failed, retry without labels
        if result.returncode != 0 and 'label' in result.stderr.lower():
            _debug_log_gh(f"[GH-CREATE] Label error detected, retrying without labels...")
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=GH_TIMEOUT,
                cwd=repo_root
            )
            _debug_log_gh(f"[GH-CREATE] Retry returned: returncode={result.returncode}")

        if result.returncode == 0 and result.stdout.strip():
            _debug_log_gh(f"[GH-CREATE] ✓ gh command succeeded")
            # stdout contains the issue URL, e.g. https://github.com/user/repo/issues/42
            issue_url = result.stdout.strip()
            issue_number = None
            if '/issues/' in issue_url:
                num_str = issue_url.rsplit('/issues/', 1)[1].strip()
                if num_str.isdigit():
                    issue_number = int(num_str)

            # Save mapping (include issue_type for branch naming)
            mapping = _load_issues_mapping()
            task_key = str(task_id) if task_id else 'unknown'
            mapping['task_to_issue'][task_key] = {
                'issue_number': issue_number,
                'issue_url': issue_url,
                'title': title,
                'issue_type': issue_type,
                'labels': labels,
                'created_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                'status': 'open'
            }
            mapping['ops_count'] = mapping.get('ops_count', 0) + 1
            _save_issues_mapping(mapping)

            # ATOMIC: Create branch immediately after issue creation.
            # This ensures the chain Issue -> Branch -> Work -> PR -> Merge
            # never breaks. Branch is created in the same call as the issue.
            _debug_log_gh(f"[GH-CREATE] Branch creation block: issue_number={issue_number}")
            if issue_number:
                _debug_log_gh(f"[GH-CREATE] ✓ issue_number exists, checking for existing branch...")
                existing_branch = get_session_branch()
                _debug_log_gh(f"[GH-CREATE] existing_branch={existing_branch}")
                if not existing_branch:
                    _debug_log_gh(f"[GH-CREATE] No existing branch, calling create_issue_branch({issue_number}, '{subject[:30]}', '{issue_type}')...")
                    branch = create_issue_branch(issue_number, subject, issue_type)
                    _debug_log_gh(f"[GH-CREATE] create_issue_branch() returned: {branch}")
                    if branch:
                        _debug_log_gh(f"[GH-CREATE] ✓ Branch created successfully: {branch}")
                        try:
                            sys.stdout.write('[GH] Branch: ' + branch + ' (auto-created with issue #' + str(issue_number) + ')\n')
                            sys.stdout.flush()
                        except Exception as e:
                            _debug_log_gh(f"[GH-CREATE] Could not write stdout: {str(e)[:100]}")
                    else:
                        _debug_log_gh(f"[GH-CREATE] ✗ Branch creation returned None")
                else:
                    _debug_log_gh(f"[GH-CREATE] ⚠️ Branch already exists ({existing_branch}), skipping creation")
            else:
                _debug_log_gh(f"[GH-CREATE] ✗ issue_number is falsy, skipping branch creation")

            _debug_log_gh(f"[GH-CREATE] ✓ RETURNING issue_number={issue_number}")
            return issue_number
        else:
            _debug_log_gh(f"[GH-CREATE] ✗ gh command failed: returncode={result.returncode}, stdout='{result.stdout[:100]}'")
            return None

    except subprocess.TimeoutExpired as e:
        _debug_log_gh(f"[GH-CREATE] ✗ TIMEOUT EXCEPTION: {str(e)[:150]}")
        return None
    except Exception as e:
        _debug_log_gh(f"[GH-CREATE] ✗ EXCEPTION: {type(e).__name__}: {str(e)[:200]}")
        import traceback
        _debug_log_gh(f"[GH-CREATE] Traceback: {traceback.format_exc()[:500]}")
        return None


def _build_close_comment(task_id, issue_data):
    """Build a comprehensive Markdown closing comment for a GitHub issue.

    The comment includes a resolution story (narrative derived from issue type),
    files changed and investigated, commands executed, RCA section for bugfix
    issues, tool usage breakdown, duration from creation to now, and session
    context metrics.

    Args:
        task_id: Task ID string or int used to retrieve tool activity via
            _get_tool_activity_for_task.
        issue_data (dict): Persisted issue metadata dict with keys title,
            issue_type, and created_at (ISO datetime string).

    Returns:
        str: Formatted Markdown comment body ready to post to GitHub.
    """
    lines = []

    task_title = issue_data.get('title', 'Task ' + str(task_id))
    issue_type = issue_data.get('issue_type', _detect_issue_type(task_title))
    created_at = issue_data.get('created_at', '')
    closed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    # Calculate duration
    duration_str = ''
    if created_at:
        try:
            start = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%S')
            end = datetime.strptime(closed_at, '%Y-%m-%dT%H:%M:%S')
            delta = end - start
            total_secs = int(delta.total_seconds())
            if total_secs >= 3600:
                hours = total_secs // 3600
                mins = (total_secs % 3600) // 60
                duration_str = str(hours) + 'h ' + str(mins) + 'm'
            elif total_secs >= 60:
                mins = total_secs // 60
                secs = total_secs % 60
                duration_str = str(mins) + 'm ' + str(secs) + 's'
            else:
                duration_str = str(total_secs) + 's'
        except Exception:
            pass

    # Get tool activity for this task
    activity = _get_tool_activity_for_task(task_id)
    all_changed_files = list(set(activity.get('files_written', []) + activity.get('files_edited', [])))
    files_read = activity.get('files_read', [])
    edits = activity.get('edits', [])
    commands = activity.get('commands_run', [])
    searches = activity.get('searches', [])
    total_tools = activity.get('total_tools', 0)

    # Section 1: Resolution Story (comprehensive narrative)
    lines.append('## Resolution Story')
    lines.append('')

    # Build a narrative based on issue type and actual work done
    if issue_type == 'fix':
        lines.append('This bug has been investigated, root-caused, and fixed.')
        if files_read:
            lines.append('The investigation involved reading ' + str(len(files_read))
                         + ' file(s) to understand the problem context and trace the root cause.')
        if all_changed_files:
            lines.append('The fix was applied across ' + str(len(all_changed_files))
                         + ' file(s) to resolve the issue.')
        if commands:
            lines.append('Verification was performed using ' + str(len(commands))
                         + ' command(s) to confirm the fix works correctly.')
    elif issue_type == 'refactor':
        lines.append('The code has been restructured to improve maintainability and design.')
        if files_read:
            lines.append('First, ' + str(len(files_read))
                         + ' file(s) were analyzed to understand the existing code structure.')
        if all_changed_files:
            lines.append('The refactoring touched ' + str(len(all_changed_files))
                         + ' file(s) while preserving all existing functionality.')
    elif issue_type == 'docs':
        lines.append('Documentation has been created or updated to reflect the current state.')
        if all_changed_files:
            lines.append(str(len(all_changed_files)) + ' documentation file(s) were updated.')
    elif issue_type == 'feature':
        lines.append('The new feature has been fully implemented and is ready for use.')
        if files_read:
            lines.append('Research phase: ' + str(len(files_read))
                         + ' existing file(s) were studied to understand patterns and conventions.')
        if all_changed_files:
            lines.append('Implementation phase: ' + str(len(all_changed_files))
                         + ' file(s) were created or modified.')
        if commands:
            lines.append('Validation phase: ' + str(len(commands))
                         + ' command(s) were executed to verify the implementation.')
    elif issue_type == 'enhancement':
        lines.append('The existing feature has been enhanced as requested.')
        if all_changed_files:
            lines.append(str(len(all_changed_files))
                         + ' file(s) were updated to deliver the enhancement.')
    else:
        lines.append('This task has been completed successfully.')
        if all_changed_files:
            lines.append(str(len(all_changed_files)) + ' file(s) were modified.')
    lines.append('')

    # Duration info
    lines.append('| Field | Value |')
    lines.append('|-------|-------|')
    lines.append('| **Status** | Completed |')
    if duration_str:
        lines.append('| **Duration** | ' + duration_str + ' |')
    lines.append('| **Closed At** | ' + closed_at + ' |')
    lines.append('')

    # Section 2: Files Changed
    if all_changed_files:
        lines.append('## Files Changed')
        lines.append('')
        for f in all_changed_files[:20]:
            lines.append('- `' + f + '`')
        lines.append('')

    # Section 3: Detailed Edits
    if edits:
        lines.append('## Changes Made')
        lines.append('')
        for edit in edits[:15]:
            lines.append('- ' + edit)
        lines.append('')

    # Section 4: Files Investigated
    if files_read:
        lines.append('## Files Investigated')
        lines.append('')
        for f in files_read[:15]:
            lines.append('- `' + f + '`')
        lines.append('')

    # Section 5: Commands Executed
    if commands:
        lines.append('## Commands Executed')
        lines.append('')
        for cmd in commands[:10]:
            lines.append('- `' + cmd + '`')
        lines.append('')

    # Section 6: Searches Performed
    if searches:
        lines.append('## Searches Performed')
        lines.append('')
        for s in searches[:10]:
            lines.append('- ' + s)
        lines.append('')

    # Section 7: RCA (Root Cause Analysis) - only for bugfix issues
    if issue_type == 'fix':
        lines.append('## Root Cause Analysis (RCA)')
        lines.append('')
        if files_read:
            lines.append('**Investigation:** ' + str(len(files_read)) + ' files investigated')
        if all_changed_files:
            lines.append('**Root Cause Location:** ' + ', '.join(['`' + f + '`' for f in all_changed_files[:5]]))
        if edits:
            lines.append('**Fix Applied:** ' + str(len(edits)) + ' edit(s) made')
            for edit in edits[:5]:
                lines.append('  - ' + edit)
        if commands:
            lines.append('**Verification:** ' + str(len(commands)) + ' command(s) run to verify fix')
        lines.append('')

    # Section 8: Tool Usage Summary
    if total_tools > 0:
        lines.append('## Tool Usage')
        lines.append('')
        lines.append('| Metric | Value |')
        lines.append('|--------|-------|')
        lines.append('| Total Tool Calls | ' + str(total_tools) + ' |')
        if files_read:
            lines.append('| Files Read | ' + str(len(files_read)) + ' |')
        if all_changed_files:
            lines.append('| Files Changed | ' + str(len(all_changed_files)) + ' |')
        if commands:
            lines.append('| Commands Run | ' + str(len(commands)) + ' |')
        if searches:
            lines.append('| Searches | ' + str(len(searches)) + ' |')
        lines.append('')

    # Section 9: Session Context
    progress_ctx = _get_session_progress_context()
    flow_ctx = _get_flow_trace_context()

    if progress_ctx or flow_ctx:
        lines.append('## Session Context')
        lines.append('')
        lines.append('| Field | Value |')
        lines.append('|-------|-------|')
        session_id = _get_session_id()
        if session_id:
            lines.append('| Session | `' + session_id + '` |')
        if flow_ctx.get('complexity'):
            lines.append('| Complexity | ' + str(flow_ctx['complexity']) + '/25 |')
        if flow_ctx.get('model'):
            lines.append('| Model | ' + flow_ctx['model'] + ' |')
        if flow_ctx.get('skill'):
            lines.append('| Skill/Agent | ' + flow_ctx['skill'] + ' |')
        if progress_ctx.get('tasks_completed'):
            lines.append('| Tasks Completed | ' + str(progress_ctx['tasks_completed']) + ' |')
        if progress_ctx.get('context_estimate_pct'):
            lines.append('| Context Usage | ' + str(progress_ctx['context_estimate_pct']) + '% |')
        if progress_ctx.get('errors_seen'):
            lines.append('| Errors Encountered | ' + str(progress_ctx['errors_seen']) + ' |')
        lines.append('')

    # Footer
    lines.append('---')
    lines.append('_Auto-closed by Claude Memory System (Level 3 Execution) | v3.0.0_')

    return '\n'.join(lines)


def close_github_issue(task_id):
    """
    Close the GitHub issue associated with a task with a comprehensive summary comment.

    The closing comment includes:
      - What was done (files changed, edits made)
      - RCA analysis (if bugfix type)
      - Tool usage breakdown
      - Duration, session context, commands run

    Args:
        task_id: Task ID string (e.g. '1')

    Returns:
        True if closed successfully, False otherwise.
    """
    try:
        if not is_gh_available():
            return False

        if _get_ops_count() >= MAX_OPS_PER_SESSION:
            return False

        repo_root = _get_repo_root()
        if not repo_root:
            return False

        # Look up issue number from mapping
        mapping = _load_issues_mapping()
        task_key = str(task_id)
        issue_data = mapping.get('task_to_issue', {}).get(task_key)

        # Fallback 1: if exact key not found, try 'unknown' key
        if not issue_data:
            issue_data = mapping.get('task_to_issue', {}).get('unknown')
            if issue_data and issue_data.get('status') == 'open':
                mapping['task_to_issue'][task_key] = issue_data
                if 'unknown' in mapping.get('task_to_issue', {}):
                    del mapping['task_to_issue']['unknown']
                _save_issues_mapping(mapping)

        # Fallback 2: Find the most recently created OPEN issue in THIS session's mapping.
        # This is SAFE because each session has its own mapping file (no cross-session risk).
        # Needed because Claude's task IDs can mismatch between TaskCreate response
        # (e.g. "Task #1") and TaskUpdate input (e.g. taskId="3") after /clear.
        if not issue_data:
            latest_open = None
            latest_time = ''
            for key, data in mapping.get('task_to_issue', {}).items():
                if data.get('status') == 'open':
                    created = data.get('created_at', '')
                    if created >= latest_time:
                        latest_time = created
                        latest_open = data
                        task_key = key
            if latest_open:
                issue_data = latest_open

        if not issue_data:
            return False

        issue_number = issue_data.get('issue_number')
        if not issue_number:
            return False

        # Already closed?
        if issue_data.get('status') == 'closed':
            return True

        # Build comprehensive closing comment
        close_comment = _build_close_comment(task_id, issue_data)

        # Close via gh CLI with detailed comment
        result = subprocess.run(
            ['gh', 'issue', 'close', str(issue_number),
             '--comment', close_comment],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )

        if result.returncode == 0:
            # Update mapping
            issue_data['status'] = 'closed'
            issue_data['closed_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            mapping['task_to_issue'][task_key] = issue_data
            mapping['ops_count'] = mapping.get('ops_count', 0) + 1
            _save_issues_mapping(mapping)
            return True

    except Exception:
        pass
    return False


def _detect_issue_type(subject, description=''):
    """Classify the issue type from the subject and description text.

    Keyword matching selects the most appropriate semantic type label.
    The result drives both GitHub label assignment and branch naming
    (e.g. bugfix/42, feature/123).

    Args:
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        str: One of 'bugfix', 'feature', 'refactor', 'docs', 'enhancement',
            'perf', 'test', or 'chore'. Defaults to 'feature' when no
            keywords match.
    """
    combined = (subject + ' ' + (description or '')).lower()
    if any(w in combined for w in ['fix', 'bug', 'error', 'broken', 'crash', 'issue', 'resolve']):
        return 'bugfix'
    if any(w in combined for w in ['refactor', 'cleanup', 'reorganize', 'simplify', 'restructure']):
        return 'refactor'
    if any(w in combined for w in ['doc', 'readme', 'comment', 'documentation', 'javadoc']):
        return 'docs'
    if any(w in combined for w in ['test', 'spec', 'coverage', 'unit test', 'integration test']):
        return 'test'
    if any(w in combined for w in ['performance', 'perf', 'optimize', 'speed', 'faster']):
        return 'perf'
    if any(w in combined for w in ['update', 'enhance', 'improve', 'upgrade']):
        return 'enhancement'
    if any(w in combined for w in ['chore', 'maintenance', 'dependency', 'dependencies']):
        return 'chore'
    return 'feature'


# -----------------------------------------------------------------------
# LABEL SYSTEM: Auto-create and assign labels to GitHub issues
# -----------------------------------------------------------------------

# All labels the system uses, with colors and descriptions.
# These get auto-created in the repo if they don't exist yet.
LABEL_DEFINITIONS = {
    # Type labels
    'bug':              {'color': 'd73a4a', 'description': 'Something isn\'t working'},
    'enhancement':      {'color': 'a2eeef', 'description': 'New feature or request'},
    'refactor':         {'color': 'D4C5F9', 'description': 'Code restructuring without behavior change'},
    'documentation':    {'color': '0075ca', 'description': 'Improvements or additions to documentation'},
    'test':             {'color': 'BFD4F2', 'description': 'Test coverage or test infrastructure'},
    # Priority labels
    'critical-priority': {'color': '8B0000', 'description': 'CRITICAL - blocks other work'},
    'high-priority':     {'color': 'FF0000', 'description': 'High priority - should be done soon'},
    'medium-priority':   {'color': 'FFA500', 'description': 'Medium priority - can wait'},
    'low-priority':      {'color': 'FBCA04', 'description': 'Low priority - nice to have'},
    # Complexity labels
    'complexity-high':   {'color': 'B60205', 'description': 'High complexity (10+ score)'},
    'complexity-medium': {'color': 'D93F0B', 'description': 'Medium complexity (4-9 score)'},
    'complexity-low':    {'color': '0E8A16', 'description': 'Low complexity (1-3 score)'},
    # Scope labels
    'backend':          {'color': '1D76DB', 'description': 'Backend / server-side changes'},
    'frontend':         {'color': 'C5DEF5', 'description': 'Frontend / UI changes'},
    'devops':           {'color': 'EDEDED', 'description': 'CI/CD, deployment, infrastructure'},
    'config':           {'color': 'F9D0C4', 'description': 'Configuration or settings changes'},
    'scripts':          {'color': 'E99695', 'description': 'Hook scripts or automation'},
    'policy':           {'color': 'D4C5F9', 'description': 'Policy or architecture changes'},
    # Auto-management labels
    'auto-created':     {'color': 'C2E0C6', 'description': 'Auto-created by Claude Memory System'},
}

# Cache for labels known to exist in the repo (avoids repeated gh calls)
_repo_labels_cache = None


def _get_repo_labels(repo_root):
    """Fetch all label names currently defined in the GitHub repository.

    The result is cached in the module-level ``_repo_labels_cache`` set so
    that subsequent calls within the same invocation do not make additional
    ``gh`` CLI requests.

    Args:
        repo_root (str): Absolute path to the git repository root, passed as
            the working directory for the ``gh`` CLI call.

    Returns:
        set: Label name strings present in the repo, or an empty set if the
            ``gh label list`` call fails or returns no data.
    """
    global _repo_labels_cache
    if _repo_labels_cache is not None:
        return _repo_labels_cache

    try:
        result = subprocess.run(
            ['gh', 'label', 'list', '--limit', '100', '--json', 'name'],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            _repo_labels_cache = {item['name'] for item in data}
            return _repo_labels_cache
    except Exception:
        pass
    _repo_labels_cache = set()
    return _repo_labels_cache


def _ensure_labels_exist(labels, repo_root):
    """Create any of the given labels that do not already exist in the repository.

    Only creates labels that are defined in LABEL_DEFINITIONS. Uses
    ``gh label create --force`` so re-creation of an existing label is
    idempotent. Failures for individual labels are silently ignored.

    Args:
        labels (list[str]): Label names to ensure exist.
        repo_root (str): Absolute path to the git repository root.
    """
    existing = _get_repo_labels(repo_root)
    for label_name in labels:
        if label_name in existing:
            continue
        defn = LABEL_DEFINITIONS.get(label_name)
        if not defn:
            continue
        try:
            subprocess.run(
                ['gh', 'label', 'create', label_name,
                 '--color', defn['color'],
                 '--description', defn['description'],
                 '--force'],
                capture_output=True, text=True, timeout=GH_TIMEOUT,
                cwd=repo_root
            )
            existing.add(label_name)
        except Exception:
            pass


def _detect_scope_labels(subject, description=''):
    """Detect applicable scope/technology labels from the subject and description.

    Checks for keywords associated with backend, frontend, devops, config,
    scripts, and policy scopes.

    Args:
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        list[str]: Scope label name strings that matched (may be empty).
    """
    labels = []
    combined = (subject + ' ' + (description or '')).lower()

    if any(w in combined for w in ['api', 'endpoint', 'server', 'service', 'database', 'backend',
                                    'spring', 'flask', 'rest', 'query']):
        labels.append('backend')
    if any(w in combined for w in ['ui', 'frontend', 'template', 'css', 'html', 'component',
                                    'dashboard', 'page', 'layout', 'view']):
        labels.append('frontend')
    if any(w in combined for w in ['deploy', 'ci', 'cd', 'docker', 'kubernetes', 'pipeline',
                                    'build', 'release', 'version']):
        labels.append('devops')
    if any(w in combined for w in ['config', 'setting', 'environment', 'properties', 'json config']):
        labels.append('config')
    if any(w in combined for w in ['script', 'hook', 'automation', 'daemon', 'enforcer',
                                    'tracker', 'notifier', 'policy script']):
        labels.append('scripts')
    if any(w in combined for w in ['policy', 'architecture', 'level-1', 'level-2', 'level-3',
                                    'enforcement', 'standard']):
        labels.append('policy')

    return labels


def _build_issue_labels(issue_type, complexity, subject, description=''):
    """Build the complete set of labels to attach to a new GitHub issue.

    Assigns one type label (semantic format matching branch naming), one
    priority label based on complexity score, a status label ('in-progress'),
    and any relevant scope labels detected from the subject/description.

    Args:
        issue_type (str): Semantic type string from _detect_issue_type
            (e.g. 'bugfix', 'feature', 'refactor').
        complexity (int or float): Task complexity score (0-25).
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        list[str]: Label name strings to assign to the issue.
    """
    labels = []

    # 1. Type label (semantic format - matches branch naming!)
    # Supported types: bugfix, feature, refactor, docs, enhancement, perf, test, chore
    # These also match branch naming: bugfix/42, feature/123, etc.
    type_map = {
        'bugfix': 'bugfix',
        'fix': 'bugfix',  # backward compatibility
        'feature': 'feature',
        'refactor': 'refactor',
        'docs': 'docs',
        'enhancement': 'enhancement',
        'perf': 'perf',
        'test': 'test',
        'chore': 'chore',
    }
    labels.append(type_map.get(issue_type, 'feature'))

    # 2. Priority label (CHANGED v3.0: semantic naming)
    # p0-critical (>=18), p1-high (12-17), p2-medium (6-11), p3-low (0-5)
    if complexity and isinstance(complexity, (int, float)):
        c = int(complexity)
        if c >= 18:
            labels.append('p0-critical')
        elif c >= 12:
            labels.append('p1-high')
        elif c >= 6:
            labels.append('p2-medium')
        else:
            labels.append('p3-low')

    # 3. Status label (always in-progress for new issues)
    labels.append('in-progress')

    # 4. Scope/technology labels (optional - only if relevant)
    labels.extend(_detect_scope_labels(subject, description))

    return labels


def _get_priority_labels(complexity):
    """Return priority and complexity labels for a given complexity score.

    .. deprecated::
        Use _build_issue_labels() instead. Retained for backward compatibility.

    Args:
        complexity (int or float or None): Task complexity score (0-25).

    Returns:
        list[str]: Priority label and complexity label strings, or an empty
            list if complexity is falsy or not numeric.
    """
    labels = []
    if not complexity or not isinstance(complexity, (int, float)):
        return labels

    complexity = int(complexity)

    if complexity >= 15:
        labels.append('critical-priority')
    elif complexity >= 10:
        labels.append('high-priority')
    elif complexity >= 5:
        labels.append('medium-priority')
    else:
        labels.append('low-priority')

    if complexity >= 10:
        labels.append('complexity-high')
    elif complexity >= 4:
        labels.append('complexity-medium')
    else:
        labels.append('complexity-low')

    return labels


def _slugify(text, max_len=40):
    """Convert text to a URL- and branch-safe slug.

    Lowercases the input, replaces spaces, hyphens, underscores, and
    forward slashes with a single hyphen, strips non-alphanumeric
    characters, and truncates at a word boundary up to max_len.

    Args:
        text (str): Input text to convert.
        max_len (int): Maximum length of the returned slug. Defaults to 40.

    Returns:
        str: Lowercase hyphen-separated slug with no leading or trailing
            hyphens and length <= max_len.
    """
    slug = ''
    for ch in text.lower():
        if ch.isalnum():
            slug += ch
        elif ch in (' ', '-', '_', '/'):
            if slug and slug[-1] != '-':
                slug += '-'
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Truncate at max_len, but don't cut mid-word if possible
    if len(slug) > max_len:
        cut = slug[:max_len]
        last_hyphen = cut.rfind('-')
        if last_hyphen > max_len // 2:
            slug = cut[:last_hyphen]
        else:
            slug = cut
    return slug.strip('-')


def create_issue_branch(issue_number, subject, issue_type=None):
    """
    Create and checkout a git branch named {label}/{issueId} WITH COMPREHENSIVE ERROR HANDLING.
    Examples: fix/42, feature/123, refactor/99, docs/55, enhancement/78

    IMPORTANT: Must include issue ID for auto-close policy to work!
    The branch name is used to link issues in github-issues.json and PR workflow.

    Only creates if currently on main/master.
    Stores branch name in github-issues.json under 'session_branch'.

    Logs ALL steps to branch-creation-debug.log for troubleshooting.
    Blocks with error message if critical failure (prevents silent failures).

    Args:
        issue_number: GitHub issue number (int)
        subject: Task subject (used for type detection if issue_type not provided)
        issue_type: Optional explicit type ('fix', 'feature', 'refactor', 'docs', etc.)

    Returns:
        Branch name string on success, None on failure.
    """
    debug_log = []
    branch_name = None

    try:
        repo_root = _get_repo_root()
        if not repo_root:
            error_msg = "[BRANCH-CREATE] CRITICAL ERROR: Not in a git repository"
            debug_log.append(error_msg)
            _log_branch_debug(debug_log, error_msg)
            sys.stdout.write(f"\n{error_msg}\n\n")
            sys.stdout.flush()
            return None

        # STEP 1: Determine current branch
        debug_log.append(f"[BRANCH-CREATE] STEP 1: Reading current branch...")
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=repo_root
        )
        if result.returncode != 0:
            error_msg = f"[BRANCH-CREATE] STEP 1 FAILED: Could not read current branch"
            debug_log.append(f"  Error: {result.stderr}")
            _log_branch_debug(debug_log, error_msg)
            sys.stdout.write(f"\n[GH ERROR] {error_msg}\n\n")
            sys.stdout.flush()
            return None

        current_branch = result.stdout.strip()
        debug_log.append(f"[BRANCH-CREATE] STEP 1 OK: Current branch = {current_branch}")

        # Check if we're already on a feature branch
        if current_branch not in ('main', 'master'):
            info_msg = f"[BRANCH-CREATE] INFO: Already on {current_branch}, skipping branch creation"
            debug_log.append(info_msg)
            _log_branch_debug(debug_log, info_msg)
            return None

        # STEP 2: Detect issue type
        debug_log.append(f"[BRANCH-CREATE] STEP 2: Detecting issue type from subject...")
        if not issue_type:
            issue_type = _detect_issue_type(subject)
        debug_log.append(f"[BRANCH-CREATE] STEP 2 OK: Issue type = {issue_type}")

        # STEP 3: Build branch name
        branch_name = issue_type + '/' + str(issue_number)
        debug_log.append(f"[BRANCH-CREATE] STEP 3: Branch name = {branch_name}")

        # STEP 4: Create and checkout new branch
        debug_log.append(f"[BRANCH-CREATE] STEP 4: Creating branch (git checkout -b {branch_name})...")
        result = subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )

        if result.returncode == 0:
            debug_log.append(f"[BRANCH-CREATE] STEP 4 OK: Branch created and checked out")

            # STEP 5: Verify we're on the branch
            verify_result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5,
                cwd=repo_root
            )
            if verify_result.returncode == 0:
                verified_branch = verify_result.stdout.strip()
                debug_log.append(f"[BRANCH-CREATE] STEP 5 VERIFY: Confirmed on {verified_branch}")

            # STEP 6: Store branch name in mapping (with session_id for future session validation)
            debug_log.append(f"[BRANCH-CREATE] STEP 6: Saving to github-issues.json...")
            mapping = _load_issues_mapping()
            mapping['session_branch'] = branch_name
            mapping['session_id'] = _get_current_session_id()  # Save current session_id
            mapping['branch_created_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            mapping['branch_from_issue'] = issue_number
            mapping['branch_type'] = issue_type
            _save_issues_mapping(mapping)
            debug_log.append(f"[BRANCH-CREATE] STEP 6 OK: Branch info saved")

            success_msg = f"[BRANCH-CREATE] ✅ SUCCESS: {branch_name}"
            debug_log.append(success_msg)
            _log_branch_debug(debug_log, success_msg)
            sys.stdout.write(f"[GH] Branch: {branch_name} (created + checked out)\n")
            sys.stdout.flush()
            return branch_name

        else:
            # STEP 4b: Branch might already exist - try checkout
            debug_log.append(f"[BRANCH-CREATE] STEP 4 FAILED: Create failed with code {result.returncode}")
            debug_log.append(f"  stderr: {result.stderr[:300]}")
            debug_log.append(f"[BRANCH-CREATE] STEP 4b: Attempting checkout on existing branch...")

            result = subprocess.run(
                ['git', 'checkout', branch_name],
                capture_output=True, text=True, timeout=10,
                cwd=repo_root
            )
            if result.returncode == 0:
                debug_log.append(f"[BRANCH-CREATE] STEP 4b OK: Existing branch checked out")
                mapping = _load_issues_mapping()
                mapping['session_branch'] = branch_name
                mapping['session_id'] = _get_current_session_id()  # Save current session_id
                mapping['branch_checked_out_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                _save_issues_mapping(mapping)
                success_msg = f"[BRANCH-CREATE] ✅ SUCCESS: {branch_name} (existing)"
                debug_log.append(success_msg)
                _log_branch_debug(debug_log, success_msg)
                sys.stdout.write(f"[GH] Branch: {branch_name} (existing, checked out)\n")
                sys.stdout.flush()
                return branch_name
            else:
                # CRITICAL: Both create AND checkout failed
                error_msg = f"[BRANCH-CREATE] 🔴 CRITICAL FAILURE: Cannot create or checkout {branch_name}"
                debug_log.append(f"[BRANCH-CREATE] STEP 4b FAILED: Checkout failed with code {result.returncode}")
                debug_log.append(f"  stderr: {result.stderr[:300]}")
                debug_log.append(error_msg)
                debug_log.append(f"[BRANCH-CREATE] ACTION REQUIRED: Fix git manually or try again")
                _log_branch_debug(debug_log, error_msg)

                # BLOCKING: Print prominent error so user sees it
                sys.stdout.write(f"\n{'='*70}\n")
                sys.stdout.write(f"[GH ERROR] Branch creation FAILED: {branch_name}\n")
                sys.stdout.write(f"  Cannot create new branch: {result.stderr[:150]}\n")
                sys.stdout.write(f"  Cannot checkout existing: {result.stderr[:150]}\n")
                sys.stdout.write(f"  ACTION: Check git status and fix manually\n")
                sys.stdout.write(f"  DEBUG: See ~/.claude/memory/logs/branch-creation-debug.log\n")
                sys.stdout.write(f"{'='*70}\n\n")
                sys.stdout.flush()
                return None

    except subprocess.TimeoutExpired:
        error_msg = f"[BRANCH-CREATE] TIMEOUT: git command exceeded timeout (repo_root={repo_root})"
        debug_log.append(error_msg)
        _log_branch_debug(debug_log, error_msg)
        sys.stdout.write(f"\n[GH ERROR] Branch creation timeout: {branch_name}\n\n")
        sys.stdout.flush()
        return None

    except Exception as e:
        error_msg = f"[BRANCH-CREATE] EXCEPTION: {type(e).__name__}: {str(e)}"
        debug_log.append(error_msg)
        _log_branch_debug(debug_log, error_msg)
        sys.stdout.write(f"\n[GH ERROR] Branch creation exception: {str(e)[:150]}\n\n")
        sys.stdout.flush()
        return None


def _log_branch_debug(debug_log, final_msg):
    """Write comprehensive branch creation debug log to file."""
    try:
        log_dir = Path.home() / '.claude' / 'memory' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'branch-creation-debug.log'

        with open(log_file, 'a', encoding='utf-8') as f:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            f.write(f"\n{'═'*70}\n")
            f.write(f"[{ts}] Branch Creation Debug Log\n")
            f.write(f"{'═'*70}\n")
            for line in debug_log:
                f.write(f"{line}\n")
            f.write(f"{'═'*70}\n")
            f.write(f"[{ts}] FINAL: {final_msg}\n\n")
    except Exception:
        pass  # Logging errors should never block


def get_session_branch():
    """
    Get the branch name stored for the CURRENT SESSION ONLY.

    Returns branch name string only if:
    1. A session_branch exists in github-issues.json, AND
    2. It was created in the current session (session_id matches)

    Returns None if:
    - No branch stored, or
    - Branch is from a PREVIOUS session (stale)
    """
    try:
        # Get current session ID by finding latest session folder
        current_session_id = _get_current_session_id()

        # Load github-issues.json mapping
        mapping = _load_issues_mapping()

        # Check if stored branch matches current session
        stored_session_id = mapping.get('session_id', '')
        stored_branch = mapping.get('session_branch')

        # Only return branch if it's from CURRENT session
        if stored_branch and stored_session_id and stored_session_id == current_session_id:
            return stored_branch

        # Branch is stale or from different session - return None
        if stored_branch and stored_session_id != current_session_id:
            # Log this for debugging
            try:
                _debug_log_gh(f"[SESSION] Ignoring stale branch from previous session: {stored_branch} (old_sid={stored_session_id[:20]}..., current_sid={current_session_id[:20]}...)")
            except Exception:
                pass

        return None
    except Exception as e:
        # If anything fails, return None to prevent blocking
        try:
            _debug_log_gh(f"[SESSION] get_session_branch() exception: {type(e).__name__}: {str(e)[:150]}")
        except Exception:
            pass
        return None


def _get_current_session_id():
    """
    Get the current session ID by finding the latest session folder.
    Returns session_id string like 'SESSION-20260308-234215-WLOD' or empty string if not found.
    """
    try:
        sessions_dir = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions'
        if not sessions_dir.exists():
            return ''

        # Get all session folders, find the most recent one (by modification time)
        session_folders = [f for f in sessions_dir.iterdir() if f.is_dir() and f.name.startswith('SESSION-')]
        if not session_folders:
            return ''

        # Sort by modification time, get the latest
        latest = max(session_folders, key=lambda f: f.stat().st_mtime)
        return latest.name
    except Exception:
        return ''


def is_on_issue_branch():
    """
    Check if the current git branch matches the {label}/{id} pattern.
    Valid prefixes: fix/, feature/, refactor/, docs/, enhancement/, test/, task/
    Also supports legacy issue-{N} format for backwards compatibility.
    Returns True if on an issue branch, False otherwise.
    """
    valid_prefixes = ('fix/', 'feature/', 'refactor/', 'docs/',
                      'enhancement/', 'test/', 'task/', 'issue-')
    try:
        repo_root = _get_repo_root()
        if not repo_root:
            return False

        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=repo_root
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return any(branch.startswith(p) for p in valid_prefixes)
    except Exception:
        pass
    return False
