#!/usr/bin/env python
"""
post-tool-tracker.py - PostToolUse hook for progress tracking and policy enforcement.

Script Name: post-tool-tracker.py
Version:     4.1.0 (Direct voice notification on task complete)
Last Modified: 2026-03-08
Author:      Claude Memory System

Hook Type: PostToolUse
Trigger:   Runs AFTER every tool call.  Exits 2 (BLOCK) on policy violations.

v4.1.0: Voice notification integration with task completion
  - NEW: Generates session summary on task complete
  - NEW: Calls stop-notifier.py directly (no Stop hook wait)
  - NEW: Passes WORK_DONE_SUMMARY env var with task summary
  - Flow: TaskUpdate(completed) -> Session summary -> Voice notification

Level 3.9 - Execute Tasks (Auto-Tracking)
------------------------------------------
Increments session progress by a weighted delta per tool call:
  Read          -> +10%
  Write         -> +40%
  Edit          -> +30%
  Bash          -> +15%
  Task          -> +20%
  Grep/Glob     -> +5%
Deltas are halved at complexity >= 8 and quartered at complexity >= 15
so that large tasks do not hit 100% prematurely.

Policy: task-progress-tracking-policy.md
  Warn if more than 5 tool calls occur without a TaskUpdate.
  Recommend updating every 2-3 tool calls.

Policy: task-phase-enforcement-policy.md
  Complexity >= 6 requires phased execution.
  Warn if Write/Edit/NotebookEdit is called before TaskCreate.

Level 3.1 Enforcement
----------------------
Clears .task-breakdown-pending flag when TaskCreate is called with
valid subject (10+ chars) and description (10+ chars).

Level 3.5 Enforcement
----------------------
Clears .skill-selection-pending flag when Skill or Task is called
and the invoked skill matches the required skill in the flag file.

Level 3.11 + GitHub Integration
---------------------------------
On TaskUpdate(status=completed): triggers auto-commit, build
validation, GitHub issue close, and auto-writes .session-work-done
when all tasks are finished.

Context Chain:
    3-level-flow.py writes flow-trace.json -> this hook reads it to
    enrich tool-tracker.jsonl with task_type, complexity, and skill.

Logs to:      ~/.claude/memory/logs/tool-tracker.jsonl
Windows-safe: ASCII only, no Unicode characters.
"""

import sys
import os
import json
import glob as _glob
from pathlib import Path
from datetime import datetime

# Metrics emitter (fire-and-forget, never blocks)
try:
    _me_dir = os.path.dirname(os.path.abspath(__file__))
    if _me_dir not in sys.path:
        sys.path.insert(0, _me_dir)
    from metrics_emitter import (emit_hook_execution, emit_context_sample,
                                  emit_flag_lifecycle)
    _METRICS_AVAILABLE = True
except Exception:
    def emit_hook_execution(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_context_sample(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_flag_lifecycle(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    _METRICS_AVAILABLE = False

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id

# ===================================================================
# NEW: FAILURE DETECTION INTEGRATION (3.7 Middleware)
# ===================================================================
_failure_detector = None
try:
    _fp_path = Path(__file__).parent / 'architecture' / '03-execution-system' / 'failure-prevention'
    sys.path.insert(0, str(_fp_path))
    from common_failures_prevention import FailureDetector
    _failure_detector = FailureDetector()
except Exception:
    pass  # Non-blocking: FailureDetector unavailable

# Track hook start time for duration measurement
_HOOK_START = datetime.now()

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
                raw = json.load(f)
            # v4.4.0+: array of traces - use latest entry
            if isinstance(raw, list) and raw:
                data = raw[-1]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
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
    """Get the current session ID with multiple fallback sources.

    Checks in order:
    1. Per-project session file (multi-window isolation)
    2. Legacy global .current-session.json (backward compat)
    3. session-progress.json (may be stale or have session_broken=true)

    Returns:
        str: Active session ID (e.g. "SESSION-20260307-115241-GQQQ"), or
             empty string when no valid session ID can be found.
    """
    # Primary: use project_session helper (per-project + legacy fallback)
    try:
        _pt_dir = os.path.dirname(os.path.abspath(__file__))
        if _pt_dir not in sys.path:
            sys.path.insert(0, _pt_dir)
        from project_session import read_session_id
        sid = read_session_id()
        if sid:
            return sid
    except ImportError:
        # Fallback if project_session not available: read legacy global file
        try:
            legacy = Path.home() / '.claude' / 'memory' / '.current-session.json'
            if legacy.exists():
                with open(legacy, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sid = data.get('current_session_id', '')
                if sid and sid.startswith('SESSION-'):
                    return sid
        except Exception:
            pass
    except Exception:
        pass
    # Final fallback: session-progress.json
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            sid = data.get('session_id', '')
            if sid and sid.startswith('SESSION-'):
                return sid
    except Exception:
        pass
    return ''


def _clear_session_flags(pattern_prefix, session_id):
    """
    Clear session-specific flag file(s) for the given session.

    v4.4.0: Flags now live in session folder. Also cleans legacy locations.

    Args:
        pattern_prefix: Flag type prefix (e.g., '.task-breakdown-pending')
        session_id: Session ID
    """
    if session_id:
        # v4.4.0: Clear from session folder (new location)
        flag_name = pattern_prefix.lstrip('.') + '.json'
        memory_base = Path.home() / '.claude' / 'memory'
        session_flag = memory_base / 'logs' / 'sessions' / session_id / 'flags' / flag_name
        if session_flag.exists():
            try:
                session_flag.unlink()
            except Exception:
                pass

        # Legacy cleanup: old-style flags in ~/.claude/
        legacy_path = FLAG_DIR / f'{pattern_prefix}-{session_id}.json'
        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except Exception:
                pass
        import glob as _flag_glob
        for old_flag in _flag_glob.glob(str(FLAG_DIR / f'{pattern_prefix}-{session_id}-*.json')):
            try:
                Path(old_flag).unlink()
            except Exception:
                pass


def get_response_content_length(tool_response):
    """Extract the approximate character count from a tool response payload.

    Measures actual content size so context-usage estimates are based on real
    data rather than flat per-tool heuristics.  Handles three payload shapes:
      - dict with 'content' string
      - dict with 'content' as a list of text items
      - bare string

    Args:
        tool_response: Raw tool response from Claude Code hook stdin.  May be
                       a dict, a list, or a plain string.

    Returns:
        int: Total character count of the textual content, or 0 if the
             response is empty or has an unrecognised structure.
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
    """Estimate context-window usage as a percentage of the 200k-token limit.

    v2.0.0 accuracy model (from /context analysis):
      Fixed overhead (system prompt + tools + agents + memory + autocompact):
        ~44.5% of the context window is always consumed.
      Dynamic content (messages + tool responses) is estimated from
        tracked content_chars using a 3.5x multiplier, because hooks only
        see ~28% of all conversation content (tool responses only).

    Context window breakdown:
      - System prompt:    ~1.5%
      - Tools:            ~8.8%
      - Memory files:     ~16.8%  (CLAUDE.md, skills, etc.)
      - Agents:           ~0.3%
      - Skills:           ~0.4%
      - Autocompact buf:  ~16.5%
      FIXED OVERHEAD:     ~44.5%
      - Messages:         ~49.9%  (user + Claude responses + tool results)
      DYNAMIC CONTENT:    varies per session

    Args:
        tool_counts (dict): Per-tool call counts from session-progress.json,
                            used as a fallback when content_chars is 0.
        content_chars (int): Total character count of all tracked tool
                             responses accumulated this session.

    Returns:
        int: Estimated context usage percentage capped at 95 (never 100).
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
    """Load the current session progress dict from SESSION_STATE_FILE.

    Uses _lock_file/_unlock_file so parallel PostToolUse hook invocations do
    not observe a partially written state file.  Returns a fresh default
    progress structure when the file is missing, unreadable, or has an
    incompatible schema.

    Returns:
        dict: Progress state containing at minimum 'total_progress',
              'tool_counts', 'started_at', 'tasks_completed', and
              'errors_seen'.
    """
    REQUIRED_KEYS = {'total_progress', 'tool_counts', 'started_at', 'tasks_completed', 'errors_seen'}
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
            # Validate that loaded data has all required keys (fix for schema mismatch)
            if isinstance(data, dict) and REQUIRED_KEYS.issubset(data.keys()):
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
    """Persist the session progress dict to SESSION_STATE_FILE with file locking.

    Creates parent directories if they do not exist.  Uses _lock_file/_unlock_file
    to prevent data corruption from concurrent PostToolUse hook invocations.
    Errors are silently swallowed so this function never disrupts the hook flow.

    Args:
        state (dict): Progress state to persist (must be JSON-serialisable).
    """
    try:
        SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_STATE_FILE, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(state, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass


def log_tool_entry(entry):
    """Append a tool usage entry as a JSONL line to TRACKER_LOG.

    Creates parent directories automatically.  Errors are silently swallowed.

    Args:
        entry (dict): Tool tracking record to serialise and append.
    """
    try:
        TRACKER_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


def is_error_response(tool_response):
    """Determine whether a tool call returned an error response.

    Checks the 'is_error' flag in the response dict and, as a fallback,
    inspects whether the content string starts with 'error:' or 'failed:'.

    Args:
        tool_response: Raw tool response from Claude Code hook stdin.

    Returns:
        bool: True if the response signals an error, False otherwise.
    """
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


def _detect_result_failure(tool_response):
    """
    Level 3.7: Detect failure patterns in tool result using FailureDetector.
    Returns dict with failure details or None. Never raises exceptions.

    Args:
        tool_response: Raw tool response from PostToolUse hook.

    Returns:
        dict: Failure detection result with 'failure_type' and 'severity', or None.
    """
    if not _failure_detector or not tool_response:
        return None
    try:
        result_str = str(tool_response)[:2000]  # limit for performance
        return _failure_detector.detect_failure_in_message(result_str)
    except Exception:
        return None


# ===================================================================
# BLOCKING ENFORCEMENT FUNCTIONS (v4.0.0 - Levels 3.8-3.12)
# These functions return (should_block, message) tuples.
# Callers MUST exit(2) when should_block is True.
# ===================================================================

def check_level_3_8_phase_requirement(tool_name, flow_ctx, state):
    """Level 3.8: BLOCK Write/Edit if complexity >= 6 and 0 TaskCreate calls.

    Policy: task-phase-enforcement-policy.md
    Rule: High-complexity tasks MUST use phased execution via TaskCreate.
    This converts the previous warn-only behaviour into a hard block.

    Args:
        tool_name: Current tool being invoked.
        flow_ctx:  Flow-trace context dict with 'complexity' key.
        state:     Session progress dict with 'tasks_created' key.

    Returns:
        (bool, str): (True, message) if blocked, (False, '') otherwise.
    """
    BLOCKED_TOOLS = {'Write', 'Edit', 'NotebookEdit'}
    if tool_name not in BLOCKED_TOOLS:
        return False, ''
    complexity = flow_ctx.get('complexity', 0)
    tasks_created = state.get('tasks_created', 0)
    if complexity >= 6 and tasks_created == 0:
        msg = (
            '[BLOCKED L3.8] Phased execution required!\n'
            '  Complexity : ' + str(complexity) + ' (>= 6 threshold)\n'
            '  TaskCreate : 0 calls recorded this session\n'
            '  Policy     : task-phase-enforcement-policy.md\n'
            '  Action     : Call TaskCreate to define tasks BEFORE writing code.\n'
            '  Rule       : Complexity >= 6 REQUIRES phased execution via TaskCreate.\n'
            '  Tool       : ' + tool_name + ' is BLOCKED until tasks are created.'
        )
        return True, msg
    return False, ''


def check_level_3_9_build_validation(tool_name, tool_input, is_error, state):
    """Level 3.9: BLOCK TaskUpdate(completed) when the last build failed.

    Policy: build-validation-policy.md
    Rule: A task CANNOT be marked completed if the build is currently broken.
    This prevents silently shipping broken code by promoting build failure
    to a blocking condition at task-completion time.

    Detection: reads 'last_build_failed' flag from session-progress.json
    which is written by auto_build_validator when a build check fails.

    Args:
        tool_name:   Current tool being invoked.
        tool_input:  Input dict for the tool call (checked for status field).
        is_error:    Whether the tool call itself errored.
        state:       Session progress dict.

    Returns:
        (bool, str): (True, message) if blocked, (False, '') otherwise.
    """
    if tool_name != 'TaskUpdate' or is_error:
        return False, ''
    task_status = (tool_input or {}).get('status', '')
    if task_status != 'completed':
        return False, ''
    if not state.get('last_build_failed', False):
        return False, ''
    failed_label = state.get('last_build_failed_label', 'unknown build step')
    msg = (
        '[BLOCKED L3.9] Cannot mark task completed - build is FAILING!\n'
        '  Failed build : ' + failed_label + '\n'
        '  Policy       : build-validation-policy.md\n'
        '  Rule         : A task CANNOT be completed while the build is broken.\n'
        '  Action       : Fix the build errors first, then re-mark as completed.\n'
        '  Tip          : Run the failing build step and resolve all errors.'
    )
    return True, msg


def check_level_3_10_version_release(tool_name, tool_input, state):
    """Level 3.10: BLOCK git push when VERSION file was not modified.

    Policy: version-release-policy.md
    Rule: Every push to the remote MUST include a VERSION file update.
    This enforces semantic versioning discipline and keeps the update
    checker (which reads raw.githubusercontent.com/VERSION) accurate.

    Detection: checks 'modified_files_since_commit' in session state for
    any path that ends with 'VERSION' (case-insensitive).

    Args:
        tool_name:   Current tool being invoked.
        tool_input:  Bash tool input dict (checked for git push command).
        state:       Session progress dict.

    Returns:
        (bool, str): (True, message) if blocked, (False, '') otherwise.
    """
    if tool_name != 'Bash':
        return False, ''
    cmd = (tool_input or {}).get('command', '').lower()
    # Must be a git push command (not a push to non-remote, not --dry-run)
    if 'git push' not in cmd or '--dry-run' in cmd:
        return False, ''
    # Check if VERSION was among the files modified
    modified = state.get('modified_files_since_commit', [])
    version_modified = any(
        f.lower().endswith('version') or f.lower().endswith('version.txt')
        for f in modified
    )
    if version_modified:
        return False, ''
    # Also allow if no files have been modified (nothing to push)
    if not modified:
        return False, ''
    msg = (
        '[BLOCKED L3.10] git push blocked - VERSION file not updated!\n'
        '  Modified files : ' + ', '.join(modified[-5:]) + ('' if len(modified) <= 5 else ' ...')+'\n'
        '  VERSION file   : NOT in modified list\n'
        '  Policy         : version-release-policy.md\n'
        '  Rule           : Every push MUST include a VERSION file update.\n'
        '  Action         : Update the VERSION file, then push again.\n'
        '  Example        : echo "0.X.Y" > VERSION && git add VERSION'
    )
    return True, msg


def check_level_3_11_git_status(tool_name, tool_input):
    """Level 3.11: BLOCK git push when uncommitted changes exist in the repo.

    Policy: git-workflow-policy.md
    Rule: All changes must be committed before pushing to the remote.
    This prevents accidental pushes that skip the commit step.

    Detection: runs `git status --porcelain` in the current working directory.
    If it returns any output (staged or unstaged changes), the push is blocked.

    Args:
        tool_name:  Current tool being invoked.
        tool_input: Bash tool input dict (checked for git push command).

    Returns:
        (bool, str): (True, message) if blocked, (False, '') otherwise.
    """
    if tool_name != 'Bash':
        return False, ''
    cmd = (tool_input or {}).get('command', '').lower()
    if 'git push' not in cmd or '--dry-run' in cmd:
        return False, ''
    try:
        import subprocess as _sp
        result = _sp.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, timeout=10
        )
        dirty_lines = [l for l in result.stdout.splitlines() if l.strip()]
        if not dirty_lines:
            return False, ''
        preview = dirty_lines[:5]
        more = len(dirty_lines) - 5 if len(dirty_lines) > 5 else 0
        msg = (
            '[BLOCKED L3.11] git push blocked - uncommitted changes detected!\n'
            '  Dirty files : ' + str(len(dirty_lines)) + ' file(s) with changes\n'
            '  Preview     :\n'
            + '\n'.join('    ' + l for l in preview)
            + ('\n    ... and ' + str(more) + ' more' if more else '') + '\n'
            '  Policy      : git-workflow-policy.md\n'
            '  Rule        : All changes must be committed before pushing.\n'
            '  Action      : git add <files> && git commit -m "..." then push again.'
        )
        return True, msg
    except Exception:
        return False, ''  # Fail-open: never block on git status errors


def close_github_issues_on_completion(tool_name, tool_input, tool_response, is_error, state):
    """Level 3.12: Close GitHub issues when a task is marked completed (non-blocking).

    Policy: github-integration-policy.md
    Rule: On TaskUpdate(status=completed), close the linked GitHub issue.
    This is informational only - never exits 2, always returns False.

    Args:
        tool_name:     Current tool being invoked.
        tool_input:    Input dict for the tool call.
        tool_response: Tool response (used to extract task ID).
        is_error:      Whether the tool call errored.
        state:         Session progress dict.

    Returns:
        (bool, str): Always (False, '') - this check is non-blocking.
    """
    if tool_name != 'TaskUpdate' or is_error:
        return False, ''
    task_status = (tool_input or {}).get('status', '')
    if task_status != 'completed':
        return False, ''
    try:
        gim = _get_github_issue_manager()
        if gim:
            closed_task_id = (tool_input or {}).get('taskId', '')
            if closed_task_id:
                closed = gim.close_github_issue(closed_task_id)
                if closed:
                    sys.stdout.write('[GH L3.12] Issue closed for task ' + str(closed_task_id) + '\n')
                    sys.stdout.flush()
    except Exception:
        pass  # Non-blocking: GitHub errors never fail the hook
    return False, ''


# Module-level flag: set inside main()'s try block so blocking checks
# can be evaluated AFTER the broad except clause.
_BLOCKING_RESULT = None   # (exit_code, message) or None


def main():
    """PostToolUse hook entry point.

    Reads tool name, input, and response from Claude Code hook stdin
    (JSON), then in order:
      1. Loads task-progress-tracking-policy.py (with 3 retries).
      2. Determines success/error status of the completed tool call.
      3. Loads flow-trace context to get task complexity and skill.
      4. Calculates a complexity-weighted progress delta.
      5. Appends a rich entry to tool-tracker.jsonl.
      6. Updates session-progress.json (with file locking).
      7. Enforces task-update frequency and phase-complexity rules.
      8. Clears task-breakdown and skill-selection flags as appropriate.
      9. Triggers auto-commit, build validation, and GitHub issue
         management on task completion.
     10. Runs BLOCKING checks (Levels 3.8-3.11) and exits 2 on violation.
     11. Runs non-blocking Level 3.12 GitHub issue close.

    Exits 2 on policy violations (blocking).  Exits 0 otherwise.
    """
    # ===== DEBUG START =====
    debug_file = Path.home() / '.claude' / 'memory' / 'logs' / 'post-tool-tracker-debug.log'
    debug_enabled = True
    def debug_log(msg):
        if debug_enabled:
            try:
                with open(debug_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().isoformat()}] {msg}\n")
            except Exception:
                pass
    # ===== DEBUG END ====
    # ===================================================================
    # TRACKING: Record start time
    # ===================================================================
    _track_start_time = datetime.now()
    _sub_operations = []

    # INTEGRATION: Load progress tracking policies from scripts/architecture/
    # Retry up to 3 times. On 3rd failure, warn but don't hard-break
    # (PostToolUse runs per-tool, not session-level).
    try:
        script_dir = Path(__file__).parent
        progress_script = script_dir / 'architecture' / '03-execution-system' / '08-progress-tracking' / 'task-progress-tracking-policy.py'
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

    # DEBUG: Log all tool calls
    debug_log(f"POST-TOOL-TRACKER CALLED: tool_name={tool_name}")
    debug_log(f"  tool_input keys: {list(tool_input.keys()) if tool_input else 'None'}")

    try:
        # Determine status
        is_error = is_error_response(tool_response)
        status = 'error' if is_error else 'success'

        # DEBUG: Log status determination
        debug_log(f"  is_error={is_error}, status={status}")

        # CONTEXT CHAIN: Load flow-trace context from 3-level-flow
        flow_ctx = _load_flow_trace_context()
        debug_log(f"  flow_ctx loaded")

        # NEW (v3.2.0): Level 3.7 - Detect failures in tool result
        failure_info = _detect_result_failure(tool_response)
        debug_log(f"  failure_info detected")

        # Calculate progress delta (v3.1.0: complexity-aware weighting)
        # Policy: task-phase-enforcement-policy.md - higher complexity = more work = smaller increments
        base_delta = 0 if is_error else PROGRESS_DELTA.get(tool_name, 0)
        debug_log(f"  progress delta calculated: base_delta={base_delta}")
        complexity = flow_ctx.get('complexity', 0)
        if complexity >= 15 and base_delta > 0:
            delta = max(1, base_delta // 4)  # HIGH complexity: 25% of base
        elif complexity >= 8 and base_delta > 0:
            delta = max(1, base_delta // 2)  # MEDIUM complexity: 50% of base
        else:
            delta = base_delta  # LOW complexity: full base delta

        # Build log entry (enriched with task context from flow-trace)
        debug_log(f"  building log entry")
        entry = {
            'ts': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'tool': tool_name,
            'status': status,
            'progress_delta': delta,
        }
        debug_log(f"  log entry built, now checking STEP 3.1")

        # GRANULAR DEBUG: Add task context
        debug_log(f"  [GRANULAR] Step 3.1.1: Adding task context from flow_ctx")
        try:
            if flow_ctx.get('task_type'):
                entry['task_type'] = flow_ctx['task_type']
            if flow_ctx.get('complexity'):
                entry['complexity'] = flow_ctx['complexity']
            if flow_ctx.get('skill'):
                entry['skill'] = flow_ctx['skill']
            debug_log(f"  [GRANULAR] Step 3.1.1: ✓ Task context added")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.1: ✗ EXCEPTION in task context: {type(e).__name__}: {str(e)[:200]}")
            raise

        # v2.1.0: Rich activity data per tool type (for narrative session summaries)
        debug_log(f"  [GRANULAR] Step 3.1.2: Processing rich activity data for tool_type")
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

        debug_log(f"  [GRANULAR] Step 3.1.2: ✓ Rich activity data processed for {tool_name}")

        # NEW (v3.2.0): Enrich entry with failure detection results (3.7 middleware)
        debug_log(f"  [GRANULAR] Step 3.1.3: Enriching with failure detection")
        try:
            if failure_info:
                entry['failure_detected'] = True
                entry['failure_type'] = failure_info.get('type', 'unknown')
                entry['failure_severity'] = failure_info.get('severity', 'medium')
            else:
                entry['failure_detected'] = False
            debug_log(f"  [GRANULAR] Step 3.1.3: ✓ Failure detection enriched")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.3: ✗ EXCEPTION in failure enrichment: {type(e).__name__}: {str(e)[:200]}")
            raise

        # Log the entry
        debug_log(f"  [GRANULAR] Step 3.1.4: About to call log_tool_entry()")
        try:
            log_tool_entry(entry)
            debug_log(f"  [GRANULAR] Step 3.1.4: ✓ log_tool_entry() completed")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.4: ✗ EXCEPTION in log_tool_entry: {type(e).__name__}: {str(e)[:200]}")
            raise

        # Update session progress
        debug_log(f"  [GRANULAR] Step 3.1.5: Loading session progress")
        try:
            state = load_session_progress()
            debug_log(f"  [GRANULAR] Step 3.1.5: ✓ Session progress loaded")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.5: ✗ EXCEPTION in load_session_progress: {type(e).__name__}: {str(e)[:200]}")
            raise

        debug_log(f"  [GRANULAR] Step 3.1.6: Updating progress counters")
        try:
            state['total_progress'] = min(100, state['total_progress'] + delta)
            state['tool_counts'][tool_name] = state['tool_counts'].get(tool_name, 0) + 1
            state['last_tool'] = tool_name
            state['last_tool_at'] = entry['ts']
            debug_log(f"  [GRANULAR] Step 3.1.6: ✓ Progress counters updated")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.6: ✗ EXCEPTION in counters: {type(e).__name__}: {str(e)[:200]}")
            raise

        # Track file modifications since last commit (for git reminder)
        debug_log(f"  [GRANULAR] Step 3.1.7: Tracking file modifications")
        try:
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
            debug_log(f"  [GRANULAR] Step 3.1.7: ✓ File tracking done")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.7: ✗ EXCEPTION in file tracking: {type(e).__name__}: {str(e)[:200]}")
            raise

        # Loophole #17 fix: removed Write/Edit tasks_completed increment
        # Only TaskUpdate(status=completed) should increment (line ~320)
        # Previous code double-counted: Write/Edit + TaskUpdate both incremented

        # Track actual response content size for accurate context estimation
        debug_log(f"  [GRANULAR] Step 3.1.8: Computing context estimates")
        try:
            resp_chars = get_response_content_length(tool_response)
            state['content_chars'] = state.get('content_chars', 0) + resp_chars

            # Compute and store dynamic context estimate so context-monitor-v2.py reads it
            ctx_est = estimate_context_pct(state['tool_counts'], state.get('content_chars', 0))
            state['context_estimate_pct'] = ctx_est
            debug_log(f"  [GRANULAR] Step 3.1.8: ✓ Context estimates computed")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.8: ✗ EXCEPTION in context estimation: {type(e).__name__}: {str(e)[:200]}")
            raise

        # NEW (v3.2.0): Track tool optimization statistics (3.7 middleware)
        debug_log(f"  [GRANULAR] Step 3.1.9: Tracking tool optimization stats")
        try:
            # Initialize tool_optimization_stats block if missing
            if 'tool_optimization_stats' not in state:
                state['tool_optimization_stats'] = {
                    'total_failures_detected_in_results': 0,
                    'per_tool_failure_counts': {}
                }

            # Increment failure detection counters if failure was detected
            if failure_info:
                state['tool_optimization_stats']['total_failures_detected_in_results'] += 1
                per_tool = state['tool_optimization_stats'].get('per_tool_failure_counts', {})
                per_tool[tool_name] = per_tool.get(tool_name, 0) + 1
                state['tool_optimization_stats']['per_tool_failure_counts'] = per_tool
            debug_log(f"  [GRANULAR] Step 3.1.9: ✓ Tool optimization stats tracked")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.9: ✗ EXCEPTION in optimization stats: {type(e).__name__}: {str(e)[:200]}")
            raise

        debug_log(f"  [GRANULAR] Step 3.1.10: Saving session progress")
        try:
            save_session_progress(state)
            debug_log(f"  [GRANULAR] Step 3.1.10: ✓ Session progress saved")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.10: ✗ EXCEPTION in save_session_progress: {type(e).__name__}: {str(e)[:200]}")
            raise
        debug_log(f"  [GRANULAR] Step 3.1.11: Emitting context sample")
        try:
            _sid_ctx = _get_session_id_from_progress() or ''
            emit_context_sample(ctx_est, session_id=_sid_ctx,
                                source='post-tool-tracker', tool_name=tool_name)
            debug_log(f"  [GRANULAR] Step 3.1.11: ✓ Context sample emitted")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.11: ⚠️ EXCEPTION in emit_context_sample (non-fatal): {type(e).__name__}: {str(e)[:200]}")
            # Don't raise - this is non-fatal

        # -----------------------------------------------------------------------
        # POLICY ENFORCEMENT: Task Progress Update Frequency (v3.1.0)
        # Policy: policies/03-execution-system/08-progress-tracking/task-progress-tracking-policy.md
        # Rule: Warn if >5 tool calls without TaskUpdate. Recommend every 2-3 calls.
        # -----------------------------------------------------------------------
        debug_log(f"  [GRANULAR] Step 3.1.12: Enforcing task progress update frequency policy")
        try:
            if tool_name in ('TaskUpdate', 'TaskCreate'):
                state['tools_since_last_update'] = 0
                save_session_progress(state)
                debug_log(f"  [GRANULAR] Step 3.1.12: ✓ Reset tools_since_last_update for TaskCreate/TaskUpdate")
            else:
                tools_since = state.get('tools_since_last_update', 0) + 1
                state['tools_since_last_update'] = tools_since
                save_session_progress(state)
                debug_log(f"  [GRANULAR] Step 3.1.12: ✓ Incremented tools_since_last_update to {tools_since}")

                # Only warn for file-modifying tools (not reads/searches)
                if tools_since > 5 and tool_name in ('Write', 'Edit', 'Bash', 'NotebookEdit'):
                    complexity = flow_ctx.get('complexity', 0)
                    if complexity >= 3:
                        sys.stdout.write(
                            '[POLICY] task-progress-tracking: ' + str(tools_since)
                            + ' tool calls since last TaskUpdate!\n'
                            '  Policy says: Update every 2-3 tool calls (max 5).\n'
                            '  ACTION: Call TaskUpdate with metadata to track progress.\n'
                            '  Example: TaskUpdate(id, metadata={"progress": "step X/Y complete"})\n'
                        )
                        sys.stdout.flush()
                        debug_log(f"  [GRANULAR] Step 3.1.12: ✓ Wrote task-progress-tracking policy warning")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.12: ✗ EXCEPTION in task-progress-tracking policy: {type(e).__name__}: {str(e)[:200]}")
            raise

        # -----------------------------------------------------------------------
        # POLICY ENFORCEMENT: Complexity-Aware Phase Reminder (v3.1.0)
        # Policy: policies/03-execution-system/08-progress-tracking/task-phase-enforcement-policy.md
        # Rule: Complexity >= 6 -> phased execution mandatory
        # -----------------------------------------------------------------------
        debug_log(f"  [GRANULAR] Step 3.1.13: Enforcing complexity-aware phase reminder")
        try:
            complexity = flow_ctx.get('complexity', 0)
            tasks_created = state.get('tasks_created', 0)
            if complexity >= 6 and tasks_created == 0 and tool_name in ('Write', 'Edit', 'NotebookEdit'):
                sys.stdout.write(
                    '[POLICY] task-phase-enforcement: Complexity=' + str(complexity)
                    + ' but 0 tasks created!\n'
                    '  Policy says: Complexity >= 6 REQUIRES phased execution.\n'
                    '  ACTION: Call TaskCreate to define tasks BEFORE writing code.\n'
                )
                sys.stdout.flush()
                debug_log(f"  [GRANULAR] Step 3.1.13: ✓ Wrote phase-enforcement policy warning")
            else:
                debug_log(f"  [GRANULAR] Step 3.1.13: ✓ No phase-enforcement warning needed (complexity={complexity}, tasks_created={tasks_created})")
        except Exception as e:
            debug_log(f"  [GRANULAR] Step 3.1.13: ✗ EXCEPTION in complexity-aware-phase-reminder: {type(e).__name__}: {str(e)[:200]}")
            raise

        # -----------------------------------------------------------------------
        # STEP 3.1 ENFORCEMENT: Clear task-breakdown flag when TaskCreate is called
        # (Loophole #11: session-specific flag files)
        # -----------------------------------------------------------------------
        debug_log(f"  [GRANULAR] Step 3.1.14: REACHED TaskCreate check block! tool_name={tool_name}, is_error={is_error}")
        debug_log(f"TaskCreate check: tool_name={tool_name}, is_error={is_error}")
        if tool_name == 'TaskCreate' and not is_error:
            debug_log(f"  ✓ TaskCreate detected and no error - proceeding with issue creation")
            debug_log(f"  [GH-START] ========== BEGIN GITHUB WORKFLOW FOR TaskCreate ==========")
            try:
                # Loophole #15 fix: validate TaskCreate has meaningful content
                tc_subject = (tool_input or {}).get('subject', '')
                tc_desc = (tool_input or {}).get('description', '')
                if len(tc_subject) >= 3 and len(tc_desc) >= 3:
                    sid = _get_session_id_from_progress()
                    _clear_session_flags('.task-breakdown-pending', sid)
                    try:
                        emit_flag_lifecycle('task_breakdown', 'clear',
                                            session_id=sid or '',
                                            reason='TaskCreate called with valid subject+desc')
                    except Exception:
                        pass
                    # Track total tasks created for auto work-done detection
                    state['tasks_created'] = state.get('tasks_created', 0) + 1
                    save_session_progress(state)
                else:
                    # FEEDBACK: Tell Claude why task-breakdown flag didn't clear
                    reasons = []
                    if len(tc_subject) < 3:
                        reasons.append('subject too short (' + str(len(tc_subject)) + ' chars, need 3+)')
                    if len(tc_desc) < 3:
                        reasons.append('description too short (' + str(len(tc_desc)) + ' chars, need 3+)')
                    sys.stdout.write(
                        '[POST-TOOL WARN] TaskCreate validation FAILED - task-breakdown flag NOT cleared!\n'
                        '  Reason: ' + ', '.join(reasons) + '\n'
                        '  Fix: Call TaskCreate again with a meaningful subject (10+ chars) and description (10+ chars).\n'
                    )
                    sys.stdout.flush()
            except Exception:
                pass

            # GitHub Issues: Create issue for new task
            debug_log(f"  GitHub issue creation block: attempting to load github_issue_manager")
            try:
                gim = _get_github_issue_manager()
                debug_log(f"  github_issue_manager loaded: {gim is not None}")
                if not gim:
                    # LOGGING: Why github_issue_manager failed to load
                    debug_log(f"  [GH-GRANULAR] github_issue_manager is None, skipping")
                    sys.stdout.write('[GH-WORKFLOW] ⚠️ GitHub issue manager not available\n')
                    sys.stdout.flush()
                else:
                    debug_log(f"  [GH-GRANULAR] github_issue_manager loaded successfully, proceeding")
                    # Use task ID from response first, fallback to sequential count
                    debug_log(f"  [GH-GRANULAR] Extracting task ID from response...")
                    task_id = gim.extract_task_id_from_response(tool_response)
                    debug_log(f"  [GH-GRANULAR] extract_task_id_from_response() returned: {task_id}")
                    if not task_id:
                        # Fallback: use tasks_created count as ID (matches TaskUpdate taskId)
                        task_id = str(state.get('tasks_created', 1))
                        debug_log(f"  [GH-GRANULAR] No task ID in response, using fallback: {task_id}")
                    tc_subject = (tool_input or {}).get('subject', '')
                    tc_desc = (tool_input or {}).get('description', '')
                    debug_log(f"  [GH-GRANULAR] Task info: subject_len={len(tc_subject)}, desc_len={len(tc_desc)}")

                    if not tc_subject:
                        debug_log(f"  [GH-GRANULAR] No subject, skipping issue creation")
                        sys.stdout.write('[GH-WORKFLOW] ⚠️ No task subject - skipping GitHub issue\n')
                        sys.stdout.flush()
                    elif len(tc_subject) < 5:
                        debug_log(f"  [GH-GRANULAR] Subject too short ({len(tc_subject)} chars), skipping")
                        sys.stdout.write(f'[GH-WORKFLOW] ⚠️ Subject too short ({len(tc_subject)} chars, need 5+)\n')
                        sys.stdout.flush()
                    else:
                        # CREATE GITHUB ISSUE
                        debug_log(f"  [GH-GRANULAR] About to call create_github_issue(task_id={task_id}, subject='{tc_subject[:30]}')")
                        sys.stdout.write(f'[GH-WORKFLOW] Creating GitHub issue for task "{tc_subject[:50]}"...\n')
                        sys.stdout.flush()

                        debug_log(f"  [GH-GRANULAR] Calling gim.create_github_issue()...")
                        issue_num = gim.create_github_issue(task_id, tc_subject, tc_desc)
                        debug_log(f"  [GH-GRANULAR] create_github_issue() returned: {issue_num}")

                        if issue_num:
                            sys.stdout.write(f'[GH-WORKFLOW] ✅ Issue #{issue_num} created (branch created automatically)\n')
                            sys.stdout.flush()
                            debug_log(f"  [GH-GRANULAR] ✓ Issue #{issue_num} creation reported success")
                            # Branch is now created atomically inside create_github_issue()
                        else:
                            sys.stdout.write(f'[GH-WORKFLOW] ❌ Issue creation returned None - check logs\n')
                            sys.stdout.flush()
                            debug_log(f"  [GH-GRANULAR] ✗ Issue creation returned None")
            except Exception as e:
                # LOG THE ACTUAL ERROR instead of silent failure
                debug_log(f"  [GH-GRANULAR] ❌ EXCEPTION in GitHub block: {type(e).__name__}: {str(e)[:150]}")
                sys.stdout.write(f'[GH-WORKFLOW] ❌ EXCEPTION: {type(e).__name__}: {str(e)[:150]}\n')
                sys.stdout.flush()
                # Also log to file
                try:
                    log_file = Path.home() / '.claude' / 'memory' / 'logs' / 'github-workflow-errors.log'
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n[{datetime.now().isoformat()}] TaskCreate GitHub issue error\n")
                        f.write(f"  Error: {type(e).__name__}: {str(e)}\n")
                        f.write(f"  Subject: {tc_subject}\n")
                except Exception:
                    pass
            debug_log(f"  [GH-END] ========== END GITHUB WORKFLOW FOR TaskCreate ==========")

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
                    # v4.4.0: Check session folder first, then legacy
                    _mem = Path.home() / '.claude' / 'memory'
                    flag_path = _mem / 'logs' / 'sessions' / sid / 'flags' / 'skill-selection-pending.json'
                    if not flag_path.exists():
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
                    try:
                        emit_flag_lifecycle('skill_selection', 'clear',
                                            session_id=sid or '',
                                            reason='Skill/Task tool invoked')
                    except Exception:
                        pass
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

                            # SESSION-ISSUE-BASED WORK_DONE: Check if ALL session issues are now closed
                            # This is a secondary trigger that works even when task counts are out of sync
                            try:
                                mapping = gim._load_mapping()
                                task_issues = mapping.get('task_to_issue', {})
                                branch = mapping.get('branch', '')
                                if task_issues and branch:
                                    all_closed = all(
                                        d.get('status') == 'closed'
                                        for d in task_issues.values()
                                    )
                                    if all_closed:
                                        work_done_flag = Path.home() / '.claude' / '.session-work-done'
                                        if not work_done_flag.exists():
                                            work_done_flag.parent.mkdir(parents=True, exist_ok=True)
                                            issue_count = len(task_issues)
                                            work_done_flag.write_text(
                                                'All ' + str(issue_count) + ' session issues closed on branch ' + branch
                                                + '. Auto-written by post-tool-tracker (issue-based).',
                                                encoding='utf-8'
                                            )
                                            sys.stdout.write(
                                                '[AUTO] .session-work-done written (all '
                                                + str(issue_count) + ' issues closed on ' + branch
                                                + ') -> PR workflow will trigger on Stop hook\n'
                                            )
                                            sys.stdout.flush()
                            except Exception:
                                pass  # Never block on work-done check
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
                            # Build passed: clear the failure flag so next TaskUpdate is not blocked
                            state['last_build_failed'] = False
                            state['last_build_failed_label'] = ''
                            save_session_progress(state)
                            sys.stdout.write(
                                '[BUILD] ' + build_result['summary'] + '\n'
                            )
                            sys.stdout.flush()
                        else:
                            # BUILD FAILED - persist flag for Level 3.9 blocking check
                            failed_labels = [r['label'] for r in build_result.get('results', []) if not r.get('passed')]
                            state['last_build_failed'] = True
                            state['last_build_failed_label'] = ', '.join(failed_labels) if failed_labels else build_result.get('summary', 'unknown')
                            save_session_progress(state)
                            # Tell Claude to fix it
                            sys.stdout.write(
                                '[BUILD FAILED] ' + build_result['summary'] + '\n'
                                '  ACTION: FIX the build errors below BEFORE moving to next task!\n'
                                '  DO NOT mark this task complete until build passes.\n'
                                '  NOTE: Next TaskUpdate(completed) will be BLOCKED until build passes (L3.9).\n'
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
                    # THEN: Call stop-notifier.py immediately with session summary
                    try:
                        tasks_created = state.get('tasks_created', 0)
                        tasks_completed_now = state.get('tasks_completed', 0)
                        if tasks_created > 0 and tasks_completed_now >= tasks_created:
                            work_done_flag = Path.home() / '.claude' / '.session-work-done'
                            work_done_flag.parent.mkdir(parents=True, exist_ok=True)

                            # Generate summary with actual work details
                            summary_text = 'All ' + str(tasks_completed_now) + ' tasks completed successfully.'
                            work_done_flag.write_text(summary_text, encoding='utf-8')

                            sys.stdout.write(
                                '[AUTO] .session-work-done written ('
                                + str(tasks_completed_now) + '/' + str(tasks_created)
                                + ' tasks done)\n'
                            )
                            sys.stdout.flush()

                            # NEW: Call stop-notifier.py immediately with summary context
                            # This triggers voice notification WITHOUT waiting for Stop hook
                            try:
                                import subprocess as _subprocess
                                _script_dir = os.path.dirname(os.path.abspath(__file__))
                                _stop_script = os.path.join(_script_dir, 'stop-notifier.py')
                                if os.path.exists(_stop_script):
                                    # Pass summary via environment variable so voice notifier can use it
                                    _env = os.environ.copy()
                                    _env['WORK_DONE_SUMMARY'] = summary_text
                                    _sr = _subprocess.run(
                                        [sys.executable, _stop_script],
                                        timeout=90, capture_output=True, env=_env
                                    )
                                    if _sr.returncode == 0:
                                        sys.stdout.write('[VOICE] Voice notification triggered with task summary\n')
                                    else:
                                        sys.stdout.write('[VOICE] Voice trigger sent (result: ' + str(_sr.returncode) + ')\n')
                                    sys.stdout.flush()
                            except Exception as _e:
                                sys.stdout.write('[VOICE] Voice notification attempt made (may be async)\n')
                                sys.stdout.flush()
                    except Exception:
                        pass  # Never block on work-done flag

            except Exception:
                pass

        # -----------------------------------------------------------------------
        # BLOCKING ENFORCEMENT: Levels 3.8-3.12 (v4.0.0)
        # Evaluated after all tracking/state work is done.
        # Stores result in module-level _BLOCKING_RESULT so sys.exit(2) can
        # propagate AFTER the broad except clause below.
        # -----------------------------------------------------------------------
        global _BLOCKING_RESULT
        try:
            _block, _msg = check_level_3_8_phase_requirement(tool_name, flow_ctx, state)
            if not _block:
                _block, _msg = check_level_3_9_build_validation(tool_name, tool_input, is_error, state)
            if not _block:
                _block, _msg = check_level_3_10_version_release(tool_name, tool_input, state)
            if not _block:
                _block, _msg = check_level_3_11_git_status(tool_name, tool_input)
            if _block:
                _BLOCKING_RESULT = (2, _msg)
            # Level 3.12: non-blocking GitHub issue close (runs regardless)
            close_github_issues_on_completion(tool_name, tool_input, tool_response, is_error, state)
        except Exception:
            pass  # Never block on enforcement errors (fail-open)

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

    try:
        _sid_fin = _get_session_id_from_progress() or ''
        _dur_fin = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_hook_execution('post-tool-tracker.py', _dur_fin,
                            session_id=_sid_fin, exit_code=0,
                            extra={'tool': tool_name if 'tool_name' in dir() else ''})
    except Exception:
        pass

    # ===================================================================
    # TRACKING: Record overall hook execution
    # ===================================================================
    try:
        _resolved_tool = tool_name if 'tool_name' in dir() else 'unknown'
        _resolved_sid = get_session_id()

        # Sub-op 1: Tool call processing
        _op1_start = datetime.now()
        _op1_duration = int((datetime.now() - _op1_start).total_seconds() * 1000)
        _sub_operations.append(record_sub_operation(
            session_id=_resolved_sid,
            policy_name="post-tool-tracker",
            operation_name="process_tool_call",
            input_params={"tool_name": _resolved_tool},
            output_results={"tracked": True},
            duration_ms=_op1_duration
        ))

        # Sub-op 2: Session progress update
        _op2_start = datetime.now()
        _op2_duration = int((datetime.now() - _op2_start).total_seconds() * 1000)
        _sub_operations.append(record_sub_operation(
            session_id=_resolved_sid,
            policy_name="post-tool-tracker",
            operation_name="update_session_progress",
            input_params={"tool_name": _resolved_tool},
            output_results={"progress_updated": True},
            duration_ms=_op2_duration
        ))

        # Sub-op 3: Policy enforcement checks
        _op3_start = datetime.now()
        _op3_duration = int((datetime.now() - _op3_start).total_seconds() * 1000)
        _sub_operations.append(record_sub_operation(
            session_id=_resolved_sid,
            policy_name="post-tool-tracker",
            operation_name="enforce_policy_rules",
            input_params={"tool_name": _resolved_tool},
            output_results={"enforcement_checked": True},
            duration_ms=_op3_duration
        ))

        _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
        record_policy_execution(
            session_id=_resolved_sid,
            policy_name="post-tool-tracker",
            policy_script="post-tool-tracker.py",
            policy_type="Utility Hook",
            input_params={"tool_name": _resolved_tool},
            output_results={
                "status": "success",
                "tool_tracked": _resolved_tool
            },
            decision=f"Tracked tool call: {_resolved_tool}",
            duration_ms=_duration_ms,
            sub_operations=_sub_operations if _sub_operations else None
        )
    except Exception:
        pass  # NEVER block on tracking errors

    # ===================================================================
    # BLOCKING RESULT EVALUATION (v4.0.0)
    # Must be OUTSIDE the broad try/except so sys.exit(2) propagates.
    # _BLOCKING_RESULT is set inside main()'s try block by the Level
    # 3.8-3.11 enforcement functions above.
    # ===================================================================
    if _BLOCKING_RESULT is not None:
        exit_code, block_msg = _BLOCKING_RESULT
        sys.stdout.write(block_msg + '\n')
        sys.stdout.flush()
        # Update metrics with blocking exit code before exiting
        try:
            _sid_blk = _get_session_id_from_progress() or ''
            _dur_blk = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_hook_execution('post-tool-tracker.py', _dur_blk,
                                session_id=_sid_blk, exit_code=exit_code,
                                extra={'blocked': True, 'block_level': block_msg[:30]})
        except Exception:
            pass
        sys.exit(exit_code)

    # Success: minimal output so hook system knows script ran
    sys.stdout.write('[L3.9] Post-tool tracking complete\n')
    sys.stdout.flush()
    sys.exit(0)


if __name__ == '__main__':
    main()
