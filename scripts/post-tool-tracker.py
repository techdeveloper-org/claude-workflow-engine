#!/usr/bin/env python
# Script Name: post-tool-tracker.py
# Version: 3.0.0 (Context Chaining from flow-trace)
# Last Modified: 2026-03-01
# Description: PostToolUse hook - L3.9 tracking + L3.11 commit + L6 subagent + voice on task complete
#              Now with flow-trace context chaining for task-aware tracking
# v3.0.0: Reads flow-trace.json for task type, complexity, skill context.
#          Enriches tool-tracker.jsonl entries with task context. Better progress estimation.
# v2.3.0: Added PID-based flag isolation for multi-window support
# v2.2.0: Auto work-done voice flag when all tasks completed (fixes unreliable voice)
# v2.1.0: Added file change tracking for git commit reminders (10+ modified files warning)
# Author: Claude Memory System
#
# Hook Type: PostToolUse
# Trigger: Runs AFTER every tool call (NEVER blocks)
# Exit: Always 0
#
# Policies enforced:
#   Level 3.9 - Execute Tasks (Auto-Tracking):
#     - Read  -> progress +10%
#     - Write -> progress +40%  (likely completed something)
#     - Edit  -> progress +30%  (likely completed something)
#     - Bash  -> progress +15%  (ran a command)
#     - Task  -> progress +20%  (delegated work)
#     - Grep/Glob -> progress +5% (searching)
#
# Logs to: ~/.claude/memory/logs/tool-tracker.jsonl
# Windows-safe: ASCII only, no Unicode chars

import sys
import os
import json
import glob as _glob
from pathlib import Path
from datetime import datetime

# Lazy-loaded GitHub issue manager (non-blocking, never fails the hook)
_github_issue_manager = None


def _get_github_issue_manager():
    """Lazy import of github_issue_manager module. Returns module or None."""
    global _github_issue_manager
    if _github_issue_manager is None:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            import github_issue_manager
            _github_issue_manager = github_issue_manager
        except ImportError:
            _github_issue_manager = False
    return _github_issue_manager if _github_issue_manager is not False else None


# Cached flow-trace context (loaded once per hook invocation)
_flow_trace_cache = None


def _load_flow_trace_context():
    """
    Load flow-trace.json from the current session to chain context from 3-level-flow.
    Returns dict with task_type, complexity, model, skill.
    Cached per invocation (module-level).

    Context chain: 3-level-flow.py -> flow-trace.json -> post-tool-tracker.py
    This enables:
    - Enriching tool-tracker.jsonl entries with task context
    - Better progress estimation weighted by complexity
    - Task-aware git commit messages
    """
    global _flow_trace_cache
    if _flow_trace_cache is not None:
        return _flow_trace_cache

    _flow_trace_cache = {}
    try:
        session_id = _get_session_id_from_progress()
        if not session_id:
            return _flow_trace_cache

        memory_base = Path.home() / '.claude' / 'memory'
        trace_file = memory_base / 'logs' / 'sessions' / session_id / 'flow-trace.json'
        if trace_file.exists():
            with open(trace_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            final_decision = data.get('final_decision', {})
            _flow_trace_cache = {
                'task_type': final_decision.get('task_type', ''),
                'complexity': final_decision.get('complexity', 0),
                'model': final_decision.get('model_selected', ''),
                'skill': final_decision.get('skill_or_agent', ''),
            }
    except Exception:
        pass
    return _flow_trace_cache


# Loophole #19 fix: file locking for Windows (parallel tool call safety)
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

# Progress delta per tool call (approximate % contribution)
PROGRESS_DELTA = {
    'Read':         10,
    'Write':        40,
    'Edit':         30,
    'NotebookEdit': 25,
    'Bash':         15,
    'Task':         20,
    'Grep':          5,
    'Glob':          5,
    'WebFetch':      8,
    'WebSearch':     8,
}

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (SESSION_STATE_FILE, TRACKER_LOG, FLAG_DIR)
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    SESSION_STATE_FILE = Path.home() / '.claude' / 'memory' / 'logs' / 'session-progress.json'
    TRACKER_LOG = Path.home() / '.claude' / 'memory' / 'logs' / 'tool-tracker.jsonl'
    FLAG_DIR = Path.home() / '.claude'


def _get_session_id_from_progress():
    """Get current session ID from session-progress.json."""
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('session_id', '')
    except Exception:
        pass
    return ''


def _clear_session_flags(pattern_prefix, session_id):
    """
    Clear PID-isolated session-specific flag file(s).

    MULTI-WINDOW FIX: Clears only the current window's flag
    Pattern: .{prefix}-{SESSION_ID}-{PID}.json

    Args:
        pattern_prefix: Flag type prefix (e.g., 'task-breakdown-pending')
        session_id: Session ID
    """
    if session_id:
        # Direct path for current window's flag (includes PID)
        current_pid = os.getpid()
        flag_path = FLAG_DIR / f'{pattern_prefix}-{session_id}-{current_pid}.json'
        if flag_path.exists():
            try:
                flag_path.unlink()
            except Exception:
                pass


def get_response_content_length(tool_response):
    """
    Extract approximate character count from tool response.
    This measures actual content size instead of using flat per-tool estimates.
    """
    if not tool_response:
        return 0
    if isinstance(tool_response, dict):
        content = tool_response.get('content', '')
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    total += len(str(item.get('text', '')))
                elif isinstance(item, str):
                    total += len(item)
            return total
    if isinstance(tool_response, str):
        return len(tool_response)
    return 0


def estimate_context_pct(tool_counts, content_chars=0):
    """
    Estimate context window usage % based on actual content size.

    v2.0.0: Accurate estimation using transcript file + fixed overhead.

    Context window breakdown (from /context analysis):
      - System prompt:    ~1.5%
      - Tools:            ~8.8%
      - Memory files:     ~16.8%  (CLAUDE.md, skills, etc.)
      - Agents:           ~0.3%
      - Skills:           ~0.4%
      - Autocompact buf:  ~16.5%
      FIXED OVERHEAD:     ~44.5%

      - Messages:         ~49.9%  (user + Claude responses + tool results)
      DYNAMIC CONTENT:    varies per session

    Hooks only see tool responses (~28% of all content).
    Messages (user prompts, Claude responses) are invisible to hooks.
    So we use a 3.5x multiplier on tracked content, or transcript file size.

    Caps at 95% (never report 100%).
    """
    CONTEXT_WINDOW = 200000  # Pro plan token limit
    FIXED_OVERHEAD_PCT = 44.5  # system prompt + tools + agents + memory + skills + autocompact

    # Estimate message portion using tracked content with 3.5x multiplier
    # Transcript file method removed: includes compacted/old messages, overcounts badly
    message_pct = 0.0
    if content_chars > 0:
        content_tokens = content_chars / 4.0
        # Hooks see ~28% of all content, so multiply by 3.5 to estimate total
        message_pct = (content_tokens / CONTEXT_WINDOW) * 100.0 * 3.5
    else:
        # Fallback: count-based heuristic (least accurate but better than nothing)
        message_pct = (
            tool_counts.get('Read', 0) * 5 +
            tool_counts.get('Write', 0) * 3 +
            tool_counts.get('Edit', 0) * 3 +
            tool_counts.get('Bash', 0) * 3 +
            tool_counts.get('Grep', 0) * 2 +
            tool_counts.get('Glob', 0) * 1 +
            tool_counts.get('Task', 0) * 6 +
            tool_counts.get('WebFetch', 0) * 5 +
            tool_counts.get('WebSearch', 0) * 4
        )

    return min(95, int(FIXED_OVERHEAD_PCT + message_pct))


def _lock_file(f):
    """Lock file for exclusive access (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except (IOError, OSError):
            pass  # lock failed - proceed without lock (better than crash)


def _unlock_file(f):
    """Unlock file (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass


def load_session_progress():
    """Load current session progress (with file locking for parallel safety)."""
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
            return data
    except Exception:
        pass
    return {
        'total_progress': 0,
        'tool_counts': {},
        'started_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'tasks_completed': 0,
        'errors_seen': 0,
    }


def save_session_progress(state):
    """Save current session progress (with file locking for parallel safety)."""
    try:
        SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_STATE_FILE, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(state, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass


def log_tool_entry(entry):
    """Append tool usage entry to tracker log."""
    try:
        TRACKER_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


def is_error_response(tool_response):
    """Check if the tool call resulted in an error."""
    if isinstance(tool_response, dict):
        # Check for is_error flag
        if tool_response.get('is_error', False):
            return True
        # Check content for error indicators
        content = tool_response.get('content', '')
        if isinstance(content, str):
            lower = content.lower()
            if lower.startswith('error:') or lower.startswith('failed:'):
                return True
    return False


def main():
    # INTEGRATION: Load progress tracking policies from scripts/architecture/
    # Retry up to 3 times. On 3rd failure, warn but don't hard-break
    # (PostToolUse runs per-tool, not session-level).
    try:
        script_dir = Path(__file__).parent
        progress_script = script_dir / 'architecture' / '03-execution-system' / '08-progress-tracking' / 'check-incomplete-work.py'
        if progress_script.exists():
            import subprocess
            _prog_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(progress_script)],
                        timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _prog_ok = True
                        break
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] check-incomplete-work failed, retrying...\n')
                        sys.stdout.flush()
                except Exception:
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] check-incomplete-work error, retrying...\n')
                        sys.stdout.flush()
            if not _prog_ok:
                sys.stdout.write('[POLICY-WARN] check-incomplete-work failed after 3 retries\n')
                sys.stdout.flush()
    except:
        pass

    # Read tool result from stdin
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})
    tool_response = data.get('tool_response', {})

    try:
        # Determine status
        is_error = is_error_response(tool_response)
        status = 'error' if is_error else 'success'

        # Calculate progress delta
        delta = 0 if is_error else PROGRESS_DELTA.get(tool_name, 0)

        # CONTEXT CHAIN: Load flow-trace context from 3-level-flow
        flow_ctx = _load_flow_trace_context()

        # Build log entry (enriched with task context from flow-trace)
        entry = {
            'ts': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'tool': tool_name,
            'status': status,
            'progress_delta': delta,
        }
        # Add task context to every entry for full traceability
        if flow_ctx.get('task_type'):
            entry['task_type'] = flow_ctx['task_type']
        if flow_ctx.get('complexity'):
            entry['complexity'] = flow_ctx['complexity']
        if flow_ctx.get('skill'):
            entry['skill'] = flow_ctx['skill']

        # v2.1.0: Rich activity data per tool type (for narrative session summaries)
        inp = tool_input or {}

        if tool_name in ('Read', 'Write', 'Edit', 'NotebookEdit'):
            file_path = inp.get('file_path', '') or inp.get('notebook_path', '') or ''
            if file_path:
                parts = file_path.replace('\\', '/').split('/')
                entry['file'] = '/'.join(parts[-3:]) if len(parts) > 3 else file_path

        if tool_name == 'Bash':
            cmd = inp.get('command', '')
            if cmd:
                entry['command'] = cmd[:200]
            desc = inp.get('description', '')
            if desc:
                entry['desc'] = desc[:150]

        elif tool_name == 'Edit':
            old_s = inp.get('old_string', '')
            new_s = inp.get('new_string', '')
            if old_s or new_s:
                entry['edit_size'] = len(new_s) - len(old_s)
                # Capture a brief hint of what changed
                if old_s:
                    entry['old_hint'] = old_s[:80].replace('\n', ' ').strip()
                if new_s:
                    entry['new_hint'] = new_s[:80].replace('\n', ' ').strip()

        elif tool_name == 'Write':
            content = inp.get('content', '')
            if content:
                entry['content_lines'] = content.count('\n') + 1

        elif tool_name == 'Grep':
            entry['pattern'] = inp.get('pattern', '')[:100]
            if inp.get('path'):
                parts = inp['path'].replace('\\', '/').split('/')
                entry['search_path'] = '/'.join(parts[-2:]) if len(parts) > 2 else inp['path']

        elif tool_name == 'Glob':
            entry['pattern'] = inp.get('pattern', '')[:100]

        elif tool_name == 'Agent':
            entry['desc'] = inp.get('description', '')[:150]
            entry['agent_type'] = inp.get('subagent_type', '')

        elif tool_name == 'TaskCreate':
            entry['task_subject'] = inp.get('subject', '')[:150]

        elif tool_name == 'TaskUpdate':
            entry['task_status'] = inp.get('status', '')
            entry['task_id'] = inp.get('taskId', '')

        elif tool_name == 'Skill':
            entry['skill_name'] = inp.get('skill', '')

        elif tool_name in ('WebSearch', 'WebFetch'):
            entry['query'] = inp.get('query', inp.get('url', ''))[:150]

        # Log the entry
        log_tool_entry(entry)

        # Update session progress
        state = load_session_progress()
        state['total_progress'] = min(100, state['total_progress'] + delta)
        state['tool_counts'][tool_name] = state['tool_counts'].get(tool_name, 0) + 1
        state['last_tool'] = tool_name
        state['last_tool_at'] = entry['ts']

        # Track file modifications since last commit (for git reminder)
        if tool_name in ('Write', 'Edit', 'NotebookEdit') and not is_error:
            file_path = (tool_input or {}).get('file_path', '') or (tool_input or {}).get('notebook_path', '')
            if file_path:
                modified_files = state.get('modified_files_since_commit', [])
                short_path = '/'.join(file_path.replace('\\', '/').split('/')[-3:])
                if short_path not in modified_files:
                    modified_files.append(short_path)
                state['modified_files_since_commit'] = modified_files

        if is_error:
            state['errors_seen'] = state.get('errors_seen', 0) + 1

        # Loophole #17 fix: removed Write/Edit tasks_completed increment
        # Only TaskUpdate(status=completed) should increment (line ~320)
        # Previous code double-counted: Write/Edit + TaskUpdate both incremented

        # Track actual response content size for accurate context estimation
        resp_chars = get_response_content_length(tool_response)
        state['content_chars'] = state.get('content_chars', 0) + resp_chars

        # Compute and store dynamic context estimate so context-monitor-v2.py reads it
        ctx_est = estimate_context_pct(state['tool_counts'], state.get('content_chars', 0))
        state['context_estimate_pct'] = ctx_est

        save_session_progress(state)

        # -----------------------------------------------------------------------
        # STEP 3.1 ENFORCEMENT: Clear task-breakdown flag when TaskCreate is called
        # (Loophole #11: session-specific flag files)
        # -----------------------------------------------------------------------
        if tool_name == 'TaskCreate' and not is_error:
            try:
                # Loophole #15 fix: validate TaskCreate has meaningful content
                tc_subject = (tool_input or {}).get('subject', '')
                tc_desc = (tool_input or {}).get('description', '')
                if len(tc_subject) >= 10 and len(tc_desc) >= 10:
                    sid = _get_session_id_from_progress()
                    _clear_session_flags('.task-breakdown-pending', sid)
                    # Track total tasks created for auto work-done detection
                    state['tasks_created'] = state.get('tasks_created', 0) + 1
                    save_session_progress(state)
                else:
                    # FEEDBACK: Tell Claude why task-breakdown flag didn't clear
                    reasons = []
                    if len(tc_subject) < 10:
                        reasons.append('subject too short (' + str(len(tc_subject)) + ' chars, need 10+)')
                    if len(tc_desc) < 10:
                        reasons.append('description too short (' + str(len(tc_desc)) + ' chars, need 10+)')
                    sys.stdout.write(
                        '[POST-TOOL WARN] TaskCreate validation FAILED - task-breakdown flag NOT cleared!\n'
                        '  Reason: ' + ', '.join(reasons) + '\n'
                        '  Fix: Call TaskCreate again with a meaningful subject (10+ chars) and description (10+ chars).\n'
                    )
                    sys.stdout.flush()
            except Exception:
                pass

            # GitHub Issues: Create issue for new task
            try:
                gim = _get_github_issue_manager()
                if gim:
                    # Use task ID from response first, fallback to sequential count
                    task_id = gim.extract_task_id_from_response(tool_response)
                    if not task_id:
                        # Fallback: use tasks_created count as ID (matches TaskUpdate taskId)
                        task_id = str(state.get('tasks_created', 1))
                    tc_subject = (tool_input or {}).get('subject', '')
                    tc_desc = (tool_input or {}).get('description', '')
                    if tc_subject and len(tc_subject) >= 5:
                        issue_num = gim.create_github_issue(task_id, tc_subject, tc_desc)
                        if issue_num:
                            sys.stdout.write('[GH] Issue #' + str(issue_num) + ' created\n')
                            sys.stdout.flush()

                            # GitHub Branch: Create issue branch on first task
                            # Branch format: {label}/{issueId} (e.g. fix/42, feature/123)
                            branch = gim.get_session_branch()
                            if not branch:  # First task - create branch
                                issue_type = gim._detect_issue_type(tc_subject, tc_desc) if hasattr(gim, '_detect_issue_type') else None
                                branch = gim.create_issue_branch(issue_num, tc_subject, issue_type)
                                if branch:
                                    sys.stdout.write('[GH] Branch: ' + branch + '\n')
                                    sys.stdout.flush()
            except Exception:
                pass  # Never block on GitHub failures

        # -----------------------------------------------------------------------
        # STEP 3.5 ENFORCEMENT: Clear skill-selection flag when Skill or Task is called
        # (Loophole #11: session-specific flag files)
        # -----------------------------------------------------------------------
        if tool_name in ('Skill', 'Task') and not is_error:
            try:
                sid = _get_session_id_from_progress()
                # Loophole #16 fix: verify invoked skill/agent matches required
                should_clear = True
                if sid:
                    flag_path = FLAG_DIR / f'.skill-selection-pending-{sid}.json'
                    if flag_path.exists():
                        with open(flag_path, 'r', encoding='utf-8') as f:
                            flag_data = json.load(f)
                        required = flag_data.get('required_skill', '')
                        if required:
                            actual = ''
                            if tool_name == 'Skill':
                                actual = (tool_input or {}).get('skill', '')
                            elif tool_name == 'Task':
                                actual = (tool_input or {}).get('subagent_type', '')
                            if actual and required and actual != required:
                                should_clear = False  # wrong skill invoked
                if should_clear:
                    _clear_session_flags('.skill-selection-pending', sid)
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # LOOPHOLE #6 FIX 2: Subagent Return Reminder
        # When Task tool completes (subagent returns), remind parent to review
        # the result and call TaskUpdate if the delegated task is complete.
        # Parent = Orchestrator, Subagent = Worker. Only parent mutates state.
        # -----------------------------------------------------------------------
        if tool_name == 'Task' and not is_error:
            try:
                subagent_type = (tool_input or {}).get('subagent_type', 'unknown')
                sys.stdout.write(
                    '[POST-TOOL L6.2] Subagent returned! (type: '
                    + subagent_type + ')\n'
                    '  REMINDER: Subagent cannot call TaskUpdate - YOU must do it.\n'
                    '  ACTION: Review subagent result -> TaskUpdate(completed) if task is done.\n'
                    '  RULE: Parent = Orchestrator. Only parent mutates task state.\n'
                )
                sys.stdout.flush()
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # STEP 3.11 + LOOPHOLE #6 FIX 3: Phase Completion Guard
        # When TaskUpdate is called with status=completed, print hint to stdout.
        # Enhanced: counts completed vs total tasks to detect phase completion.
        # -----------------------------------------------------------------------
        if tool_name == 'TaskUpdate' and not is_error:
            try:
                task_status = (tool_input or {}).get('status', '')
                if task_status == 'completed':
                    state['tasks_completed'] = state.get('tasks_completed', 0) + 1
                    completed_count = state.get('tasks_completed', 1)
                    # Reset modified files tracker after task completion (git commit expected)
                    state['modified_files_since_commit'] = []
                    save_session_progress(state)
                    sys.stdout.write(
                        '[POST-TOOL L3.11] Task marked COMPLETED (#'
                        + str(completed_count) + ')!\n'
                        '  PHASE GUARD: Check ALL tasks in current phase.\n'
                        '  IF no tasks remain in_progress in this phase:\n'
                        '    -> Phase is COMPLETE -> git add + git commit + git push IMMEDIATELY.\n'
                        '  IF tasks still in_progress:\n'
                        '    -> Continue working on remaining tasks.\n'
                        '  RULE: Phase completion = ALL tasks done, not just this one.\n'
                        '  RULE: DO NOT skip git commit on phase completion.\n'
                    )
                    sys.stdout.flush()

                    # AUTO WORK-DONE VOICE (v2.2.0):
                    # After each task completion, print strong reminder to Claude.
                    # Claude must check TaskList and write .session-work-done if all done.
                    sys.stdout.write(
                        '[POST-TOOL VOICE] Task #' + str(completed_count) + ' completed.\n'
                        '  CHECK: Are ALL tasks now completed?\n'
                        '  IF YES -> Write ~/.claude/.session-work-done with session summary.\n'
                        '  Command: python -c "from pathlib import Path; '
                        'Path.home().joinpath(\'.claude\',\'.session-work-done\')'
                        '.write_text(\'Sir, all tasks completed. [YOUR SUMMARY HERE]\', encoding=\'utf-8\')"\n'
                    )
                    sys.stdout.flush()

                    # GitHub Issues: Close issue for completed task
                    try:
                        gim = _get_github_issue_manager()
                        if gim:
                            closed_task_id = (tool_input or {}).get('taskId', '')
                            if closed_task_id:
                                closed = gim.close_github_issue(closed_task_id)
                                if closed:
                                    sys.stdout.write('[GH] Issue closed for task ' + str(closed_task_id) + '\n')
                                    sys.stdout.flush()
                    except Exception:
                        pass  # Never block on GitHub failures

                    # AUTO-COMMIT: Actually trigger auto-commit on task completion
                    try:
                        import subprocess as _subprocess
                        _script_dir = os.path.dirname(os.path.abspath(__file__))
                        _commit_enforcer = os.path.join(_script_dir, 'architecture', '03-execution-system', '09-git-commit', 'auto-commit-enforcer.py')
                        if os.path.exists(_commit_enforcer):
                            _cr = _subprocess.run(
                                [sys.executable, _commit_enforcer, '--enforce-now'],
                                timeout=60, capture_output=True
                            )
                            if _cr.returncode == 0:
                                sys.stdout.write('[POST-TOOL L3.11] Auto-commit enforcer executed successfully\n')
                            else:
                                sys.stdout.write('[POST-TOOL L3.11] Auto-commit: no changes to commit or skipped\n')
                            sys.stdout.flush()
                    except Exception:
                        pass  # Never block on auto-commit

                    # BUILD VALIDATION: Compile check on task completion
                    try:
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        if script_dir not in sys.path:
                            sys.path.insert(0, script_dir)
                        import auto_build_validator
                        modified = state.get('modified_files_since_commit', [])
                        build_result = auto_build_validator.validate_build(
                            modified_files=modified
                        )
                        if build_result['all_passed']:
                            sys.stdout.write(
                                '[BUILD] ' + build_result['summary'] + '\n'
                            )
                            sys.stdout.flush()
                        else:
                            # BUILD FAILED - tell Claude to fix it
                            sys.stdout.write(
                                '[BUILD FAILED] ' + build_result['summary'] + '\n'
                                '  ACTION: FIX the build errors below BEFORE moving to next task!\n'
                                '  DO NOT mark this task complete until build passes.\n'
                            )
                            for r in build_result['results']:
                                if not r['passed']:
                                    sys.stdout.write(
                                        '  --- ' + r['label'] + ' ---\n'
                                        + r.get('output', '')[:1500] + '\n'
                                    )
                            sys.stdout.flush()
                    except Exception:
                        pass  # Never block on build validation failures

                    # AUTO WORK-DONE: Write .session-work-done flag when ALL tasks complete
                    try:
                        tasks_created = state.get('tasks_created', 0)
                        tasks_completed_now = state.get('tasks_completed', 0)
                        if tasks_created > 0 and tasks_completed_now >= tasks_created:
                            work_done_flag = Path.home() / '.claude' / '.session-work-done'
                            work_done_flag.parent.mkdir(parents=True, exist_ok=True)
                            work_done_flag.write_text(
                                'All ' + str(tasks_completed_now) + ' tasks completed. Auto-written by post-tool-tracker.',
                                encoding='utf-8'
                            )
                            sys.stdout.write(
                                '[AUTO] .session-work-done written ('
                                + str(tasks_completed_now) + '/' + str(tasks_created)
                                + ' tasks done) -> PR workflow will trigger on Stop hook\n'
                            )
                            sys.stdout.flush()
                    except Exception:
                        pass  # Never block on work-done flag

            except Exception:
                pass

        # GIT REMINDER: When 10+ files modified without commit
        modified_count = len(state.get('modified_files_since_commit', []))
        if modified_count >= 10 and tool_name in ('Write', 'Edit', 'NotebookEdit'):
            sys.stdout.write(
                '[POST-TOOL GIT] WARNING: ' + str(modified_count) + ' files modified since last commit!\n'
                '  ACTION: Consider running git add + git commit + git push.\n'
                '  FILES: ' + ', '.join(state.get('modified_files_since_commit', [])[-5:]) + '...\n'
            )
            sys.stdout.flush()

        # Also write to .context-usage so it stays fresh (context-monitor fallback path)
        try:
            context_usage_file = Path.home() / '.claude' / 'memory' / '.context-usage'
            context_usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(context_usage_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'percentage': ctx_est,
                    'updated_at': entry['ts'],
                    'source': 'post-tool-tracker dynamic estimate',
                    'tool_counts': state['tool_counts']
                }, f)
        except Exception:
            pass

    except Exception:
        pass  # NEVER block on tracking errors

    sys.exit(0)


if __name__ == '__main__':
    main()
