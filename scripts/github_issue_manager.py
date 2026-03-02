#!/usr/bin/env python
# Script Name: github_issue_manager.py
# Version: 3.0.0
# Last Modified: 2026-02-28
# Description: GitHub Issues + Branch integration for Level 3 Execution.
#              Auto-creates issues on TaskCreate, auto-closes on TaskUpdate(completed).
#              Creates issue branches using {label}/{issueId} format (e.g. fix/42, feature/123).
#              Adds priority + complexity labels. Includes comprehensive stories on create/close.
#              Uses gh CLI. Non-blocking - never fails the hook if GitHub is unavailable.
# Author: Claude Memory System
#
# Safety:
#   - Max 10 GitHub operations per session (create + close combined)
#   - 15s timeout on all gh CLI calls
#   - All public functions wrapped in try/except (never raises)
#   - gh auth status is the implicit enable/disable toggle

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
    """Get current session ID from session-progress.json."""
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('session_id', '')
    except Exception:
        pass
    return ''


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


def _get_mapping_file():
    """Get path to the github-issues.json mapping file for current session."""
    session_id = _get_session_id()
    if session_id:
        session_dir = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id
        return session_dir / 'github-issues.json'
    # Fallback: use a general mapping file
    return Path.home() / '.claude' / 'memory' / 'logs' / 'github-issues.json'


def _load_issues_mapping():
    """Load task-to-issue mapping from disk."""
    mapping_file = _get_mapping_file()
    try:
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'task_to_issue': {}, 'ops_count': 0, 'session_id': _get_session_id()}


def _save_issues_mapping(mapping):
    """Persist task-to-issue mapping to disk."""
    mapping_file = _get_mapping_file()
    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
    except Exception:
        pass


def _get_ops_count():
    """Get number of GitHub operations performed this session."""
    mapping = _load_issues_mapping()
    return mapping.get('ops_count', 0)


def _increment_ops_count():
    """Increment and persist the ops counter."""
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
    """
    Parse task ID from a TaskCreate tool response.

    Handles multiple response formats:
      - "Task #1 created successfully: ..."
      - "Task created with id 1"
      - "Created task 1: ..."
      - {"id": "1", ...}
      - Any string containing digits after task-related keywords

    Returns the task ID string (e.g. '1') or empty string.
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
    """
    Load flow-trace.json to get current session's execution context:
    task type, complexity, model, skill/agent, context usage, etc.
    Returns dict with extracted fields, or empty dict.
    """
    session_id = _get_session_id()
    if not session_id:
        return {}
    trace_file = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id / 'flow-trace.json'
    try:
        if trace_file.exists():
            with open(trace_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
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
    """
    Load session-progress.json for current tool counts, tasks completed, modified files.
    Returns dict with extracted fields, or empty dict.
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
    """
    Scan tool-tracker.jsonl for activity related to a specific task.
    Returns dict with files_read, files_written, files_edited, commands_run, searches.
    Scans entries AFTER the TaskCreate for this task_id until the TaskUpdate(completed).
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
    try:
        if not is_gh_available():
            return None

        if _get_ops_count() >= MAX_OPS_PER_SESSION:
            return None

        repo_root = _get_repo_root()
        if not repo_root:
            return None

        # Build issue title and body
        title = '[TASK-' + str(task_id) + '] ' + subject if task_id else subject
        # Truncate title to 256 chars (GitHub limit is higher but keep it readable)
        title = title[:256]

        session_id = _get_session_id()
        flow_ctx = _get_flow_trace_context()
        progress_ctx = _get_session_progress_context()

        # --- Build comprehensive issue body with story format ---
        body_lines = []
        issue_type = _detect_issue_type(subject, description)
        complexity = flow_ctx.get('complexity', 0)

        # Section 1: Story / Narrative
        body_lines.append('## Story')
        body_lines.append('')
        # Build a comprehensive narrative based on issue type
        if issue_type == 'fix':
            body_lines.append('A bug has been identified that needs to be resolved. '
                              'The issue affects the system behavior described below and '
                              'requires investigation, root cause analysis, and a targeted fix.')
        elif issue_type == 'refactor':
            body_lines.append('The existing code needs restructuring to improve maintainability, '
                              'readability, or performance. This refactoring should preserve all '
                              'current functionality while improving the internal design.')
        elif issue_type == 'docs':
            body_lines.append('Documentation needs to be created or updated to accurately reflect '
                              'the current system behavior, API contracts, or setup instructions.')
        elif issue_type == 'test':
            body_lines.append('Test coverage needs to be added or improved to ensure system '
                              'reliability and prevent regressions in the affected components.')
        elif issue_type == 'enhancement':
            body_lines.append('An existing feature needs to be enhanced or optimized to '
                              'better serve the current requirements and improve user experience.')
        else:
            body_lines.append('A new feature needs to be implemented as described below. '
                              'This involves designing the solution, implementing the code, '
                              'and verifying it works correctly end-to-end.')
        body_lines.append('')

        # Add the actual task description as the detailed story
        if description:
            body_lines.append('**What needs to be done:**')
            body_lines.append('')
            body_lines.append(description)
        else:
            body_lines.append('**What needs to be done:** ' + subject)
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
        cmd = [
            'gh', 'issue', 'create',
            '--title', title,
            '--body', body,
        ]
        cmd_with_labels = cmd + ['--label', ','.join(labels)]

        result = subprocess.run(
            cmd_with_labels,
            capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=repo_root
        )

        # If label creation still failed, retry without labels
        if result.returncode != 0 and 'label' in result.stderr.lower():
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=GH_TIMEOUT,
                cwd=repo_root
            )

        if result.returncode == 0 and result.stdout.strip():
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

            return issue_number

    except Exception:
        pass
    return None


def _build_close_comment(task_id, issue_data):
    """
    Build a comprehensive closing comment for a GitHub issue.

    Includes:
      - Resolution summary (what was done)
      - Files changed (read/written/edited)
      - Commands executed
      - Duration (created_at -> now)
      - RCA analysis (if bugfix type)
      - Tool usage breakdown
      - Session metrics

    Returns comment string.
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
    """
    Detect the issue type from subject and description text.
    Returns one of: 'fix', 'feature', 'refactor', 'docs', 'enhancement', 'test'.
    Used for both label assignment and branch naming.
    """
    combined = (subject + ' ' + (description or '')).lower()
    if any(w in combined for w in ['fix', 'bug', 'error', 'broken', 'crash', 'issue', 'resolve']):
        return 'fix'
    if any(w in combined for w in ['refactor', 'cleanup', 'reorganize', 'simplify', 'restructure']):
        return 'refactor'
    if any(w in combined for w in ['doc', 'readme', 'comment', 'documentation', 'javadoc']):
        return 'docs'
    if any(w in combined for w in ['test', 'spec', 'coverage', 'unit test', 'integration test']):
        return 'test'
    if any(w in combined for w in ['update', 'enhance', 'improve', 'upgrade', 'optimize']):
        return 'enhancement'
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
    """Fetch all labels currently in the GitHub repo. Cached per invocation."""
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
    """Create any labels that don't exist in the repo yet."""
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
    """Detect scope/technology labels from subject and description."""
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
    """
    Build the complete list of labels for a GitHub issue.
    Returns list of label name strings.
    """
    labels = []

    # 1. Auto-management label
    labels.append('auto-created')

    # 2. Type label (maps issue_type to actual repo label names)
    type_label_map = {
        'fix': 'bug',
        'feature': 'enhancement',
        'refactor': 'refactor',
        'docs': 'documentation',
        'enhancement': 'enhancement',
        'test': 'test',
    }
    labels.append(type_label_map.get(issue_type, 'enhancement'))

    # 3. Priority label
    if complexity and isinstance(complexity, (int, float)):
        c = int(complexity)
        if c >= 15:
            labels.append('critical-priority')
        elif c >= 10:
            labels.append('high-priority')
        elif c >= 5:
            labels.append('medium-priority')
        else:
            labels.append('low-priority')

    # 4. Complexity label
    if complexity and isinstance(complexity, (int, float)):
        c = int(complexity)
        if c >= 10:
            labels.append('complexity-high')
        elif c >= 4:
            labels.append('complexity-medium')
        else:
            labels.append('complexity-low')

    # 5. Scope/technology labels
    labels.extend(_detect_scope_labels(subject, description))

    return labels


def _get_priority_labels(complexity):
    """
    Get priority and complexity labels based on task complexity score.
    Returns list of label strings.
    DEPRECATED: Use _build_issue_labels() instead. Kept for backward compatibility.
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
    """
    Convert text to a URL/branch-safe slug.
    Lowercase, hyphens only, no special chars, max max_len chars.
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
    Create and checkout a git branch named {label}/{issueId}.
    Examples: fix/42, feature/123, refactor/99, docs/55, enhancement/78

    Only creates if currently on main/master.
    Stores branch name in github-issues.json under 'session_branch'.

    Args:
        issue_number: GitHub issue number (int)
        subject: Task subject (used for type detection if issue_type not provided)
        issue_type: Optional explicit type ('fix', 'feature', 'refactor', 'docs', etc.)

    Returns:
        Branch name string on success, None on failure.
    """
    try:
        repo_root = _get_repo_root()
        if not repo_root:
            return None

        # Check current branch - only create from main/master
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=repo_root
        )
        if result.returncode != 0:
            return None

        current_branch = result.stdout.strip()
        if current_branch not in ('main', 'master'):
            # Already on a feature branch - don't create another
            return None

        # Determine the label prefix for branch naming
        if not issue_type:
            issue_type = _detect_issue_type(subject)

        # Build branch name: {label}/{issueId}
        branch_name = issue_type + '/' + str(issue_number)

        # Create and checkout new branch
        result = subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root
        )

        if result.returncode == 0:
            # Store branch name in mapping
            mapping = _load_issues_mapping()
            mapping['session_branch'] = branch_name
            mapping['branch_created_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            mapping['branch_from_issue'] = issue_number
            mapping['branch_type'] = issue_type
            _save_issues_mapping(mapping)
            return branch_name
        else:
            # Branch might already exist - try checkout
            result = subprocess.run(
                ['git', 'checkout', branch_name],
                capture_output=True, text=True, timeout=10,
                cwd=repo_root
            )
            if result.returncode == 0:
                mapping = _load_issues_mapping()
                mapping['session_branch'] = branch_name
                _save_issues_mapping(mapping)
                return branch_name

    except Exception:
        pass
    return None


def get_session_branch():
    """
    Get the branch name stored for the current session.
    Returns branch name string or None if no session branch exists.
    """
    try:
        mapping = _load_issues_mapping()
        return mapping.get('session_branch')
    except Exception:
        pass
    return None


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
