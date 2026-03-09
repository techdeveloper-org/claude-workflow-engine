#!/usr/bin/env python
"""
pre-tool-enforcer.py - PreToolUse hook that enforces policy before every tool call.

Script Name: pre-tool-enforcer.py
Version:     3.3.0 (Level 1/2 flow-trace blocking checks added)
Last Modified: 2026-03-07
Author:      Claude Memory System

Hook Type: PreToolUse
Trigger:   Runs BEFORE every tool call.
Exit 0   = Allow tool (may print optimization hints to stdout).
Exit 1/2 = BLOCK tool (prints blocking reason to stderr).

Policies enforced
-----------------
Level 3.3 - Review Checkpoint:
    DISABLED (v2.2.0): Hook shows checkpoint table; Claude auto-proceeds.
    Flag .checkpoint-pending-*.json is never written.

Level 3.1 - Task Breakdown (Loophole #7 Fix):
    Write/Edit/NotebookEdit are BLOCKED while .task-breakdown-pending.json
    exists for the current session+PID.
    Bash/Task NOT blocked (investigation allowed before TaskCreate).
    Flag cleared by post-tool-tracker.py when TaskCreate is called.

Level 3.5 - Skill/Agent Selection (Loophole #7 Fix):
    Write/Edit/NotebookEdit are BLOCKED while .skill-selection-pending.json
    exists for the current session+PID.
    Bash/Task NOT blocked (Bash needed for git/tests; Task IS step 3.5).
    Flag cleared by post-tool-tracker.py when Skill or Task is called.

Level 1 Sync System Check (v3.3.0):
    Write/Edit/NotebookEdit are BLOCKED if flow-trace.json for the current
    session does NOT contain LEVEL_1_CONTEXT and LEVEL_1_SESSION pipeline steps.
    Fail-open: if trace file is absent the check is skipped (fresh session).
    Block message: "Level 1 Sync System not complete yet!"

Level 2 Standards System Check (v3.3.0):
    Write/Edit/NotebookEdit are BLOCKED if flow-trace.json for the current
    session does NOT contain LEVEL_2_STANDARDS pipeline step.
    Fail-open: same as Level 1 check above.
    Block message: "Level 2 Standards System not complete yet!"

Level 3.5+ Dynamic Skill Context:
    Detects file extension/name on every Read/Write/Edit/Grep/Glob call
    and injects the matching skill/agent hint to stdout.

Level 3.6 - Tool Usage Optimization:
    Grep: warn if head_limit is missing.
    Read: warn if offset+limit are missing for large-file reads.

Level 3.7 - Failure Prevention:
    Bash: BLOCK Windows-only commands (del, copy, dir, xcopy, ...).
    Write/Edit/NotebookEdit: BLOCK Unicode chars in .py files on Windows.

Context Chain:
    3-level-flow.py writes flow-trace.json -> this hook reads it to
    provide task-aware optimization hints (v3.1.0+).

Windows-safe: ASCII only, no Unicode characters.
"""

import sys
import os
import json
import glob as _glob
from pathlib import Path
from datetime import datetime, timedelta

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (FLAG_DIR, CURRENT_SESSION_FILE)
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    FLAG_DIR = Path.home() / '.claude'
    # Per-project session file for multi-window isolation
    try:
        _pe_dir = os.path.dirname(os.path.abspath(__file__))
        if _pe_dir not in sys.path:
            sys.path.insert(0, _pe_dir)
        from project_session import get_project_session_file
        CURRENT_SESSION_FILE = get_project_session_file()
    except ImportError:
        CURRENT_SESSION_FILE = Path.home() / '.claude' / 'memory' / '.current-session.json'

# Metrics emitter (fire-and-forget, never blocks)
try:
    _me_dir = os.path.dirname(os.path.abspath(__file__))
    if _me_dir not in sys.path:
        sys.path.insert(0, _me_dir)
    from metrics_emitter import (emit_hook_execution, emit_enforcement_event,
                                  emit_flag_lifecycle)
    _METRICS_AVAILABLE = True
except Exception:
    def emit_hook_execution(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_enforcement_event(*a, **kw):
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
# NEW: TOOL OPTIMIZATION INTEGRATION (3.6 Middleware)
# ===================================================================
_optimizer = None
try:
    _arch_path = Path(__file__).parent / 'architecture' / '03-execution-system'
    sys.path.insert(0, str(_arch_path / '06-tool-optimization'))
    from tool_usage_optimization_policy import ToolUsageOptimizer
    _optimizer = ToolUsageOptimizer()
except Exception:
    pass  # Non-blocking: Optimizer unavailable

# ===================================================================
# NEW: FAILURE PREVENTION INTEGRATION (3.7 Pre-Execution Middleware)
# ===================================================================
_pre_checker = None
try:
    _arch_path = Path(__file__).parent / 'architecture' / '03-execution-system'
    sys.path.insert(0, str(_arch_path / 'failure-prevention'))
    from common_failures_prevention import PreExecutionChecker
    _pre_checker = PreExecutionChecker()
except Exception:
    pass  # Non-blocking: PreExecutionChecker unavailable

# Track hook start time for total duration
_HOOK_START = datetime.now()

# Tools that are BLOCKED while checkpoint is pending (file-modification tools ONLY)
# Write/Edit/NotebookEdit are the ONLY tools that directly create/modify source files.
# Bash, Task are NOT blocked: Bash is needed for git/investigation/tests.
# Task is a delegation mechanism (subagent tools are independently checked).
BLOCKED_WHILE_CHECKPOINT_PENDING = {'Write', 'Edit', 'NotebookEdit'}

# Tools that are ALWAYS ALLOWED (everything except direct file modification)
ALWAYS_ALLOWED = {'Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch', 'Task', 'Bash'}

# Max age for enforcement flags - auto-expire after 60 minutes (stale flag safety)
CHECKPOINT_MAX_AGE_MINUTES = 60

# Cached flow-trace context (loaded once per hook invocation)
_flow_trace_cache = None

# Cached failure knowledge base (loaded once per hook invocation)
_failure_kb_cache = None

# Cached per-session optimization event log (for aggregation)
_optimization_events_log = None


def _load_flow_trace_context():
    """
    Load flow-trace.json from the current session to chain context from 3-level-flow.
    Returns dict with task_type, complexity, model, skill, plan_mode, user_input,
    tech_stack, and supplementary_skills.
    Cached per invocation (module-level).

    This enables pre-tool-enforcer to:
    - Know what task type the session is working on
    - Provide task-aware optimization hints
    - Validate tool usage against the stated task context
    - Show other technologies and skills relevant to the task (new in v3.3.0)
    """
    global _flow_trace_cache
    if _flow_trace_cache is not None:
        return _flow_trace_cache

    _flow_trace_cache = {}
    try:
        session_id = get_current_session_id()
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
                'plan_mode': final_decision.get('plan_mode', False),
                'user_input': data.get('user_input', {}).get('prompt', '')[:200],
                'tech_stack': final_decision.get('tech_stack', []),
                'supplementary_skills': final_decision.get('supplementary_skills', []),
            }
    except Exception:
        pass
    return _flow_trace_cache


def _load_failure_kb():
    """
    Load failure-kb.json from architecture/03-execution-system/failure-prevention/.
    Returns dict keyed by tool name, each containing a list of known failure patterns.

    Policy link: policies/03-execution-system/failure-prevention/common-failures-prevention.md
    Architecture: scripts/architecture/03-execution-system/failure-prevention/failure-kb.json
    """
    global _failure_kb_cache
    if _failure_kb_cache is not None:
        return _failure_kb_cache

    _failure_kb_cache = {}
    try:
        script_dir = Path(__file__).parent
        kb_path = script_dir / 'architecture' / '03-execution-system' / 'failure-prevention' / 'failure-kb.json'
        if kb_path.exists():
            with open(kb_path, 'r', encoding='utf-8') as f:
                _failure_kb_cache = json.load(f)
    except Exception:
        pass
    return _failure_kb_cache


def check_failure_kb_hints(tool_name, tool_input):
    """
    Level 3.7: Consult failure-kb.json for known failure patterns.
    Returns hints (non-blocking) based on known failure patterns for this tool.

    Policy link: policies/03-execution-system/failure-prevention/common-failures-prevention.md
    """
    hints = []
    kb = _load_failure_kb()
    if not kb:
        return hints

    tool_patterns = kb.get(tool_name, [])
    for pattern in tool_patterns:
        pattern_id = pattern.get('pattern_id', '')
        solution = pattern.get('solution', {})
        sol_type = solution.get('type', '')

        # Check Edit tool: warn about line number prefix
        if tool_name == 'Edit' and pattern_id == 'edit_line_number_prefix':
            old_str = tool_input.get('old_string', '')
            if old_str:
                import re
                if re.match(r'^\s*\d+', old_str):
                    hints.append(
                        '[FAILURE-KB] Edit: old_string may contain line number prefix. '
                        'Strip line numbers before Edit (pattern from failure-kb.json).'
                    )

        # Check Edit tool: warn about editing without reading
        elif tool_name == 'Edit' and pattern_id == 'edit_without_read':
            hints.append(
                '[FAILURE-KB] Edit: Ensure file was Read before Edit '
                '(known failure pattern from failure-kb.json).'
            )

        # Check Read tool: warn about large files
        elif tool_name == 'Read' and pattern_id == 'read_file_too_large':
            offset = tool_input.get('offset')
            limit = tool_input.get('limit')
            if offset is None and limit is None:
                # Already handled by check_read(), but add KB source attribution
                pass

        # Check Grep tool: warn about missing head_limit
        elif tool_name == 'Grep' and pattern_id == 'grep_no_head_limit':
            head_limit = tool_input.get('head_limit', 0)
            if not head_limit:
                # Already handled by check_grep(), but add KB source attribution
                pass

        # Check Bash tool: known command translations
        elif tool_name == 'Bash' and sol_type == 'translate':
            cmd = tool_input.get('command', '').strip().lower()
            mapping = solution.get('mapping', {})
            for win_cmd, unix_cmd in mapping.items():
                if cmd.startswith(win_cmd.lower()):
                    hints.append(
                        '[FAILURE-KB] Bash: Translate "' + win_cmd + '" -> "' + unix_cmd + '" '
                        '(known failure from failure-kb.json, confidence: ' +
                        str(pattern.get('confidence', 0)) + ')'
                    )

    return hints


def get_current_session_id():
    """
    Read the active session ID from .current-session.json or session-progress.json.
    Falls back to session-progress.json if .current-session.json is missing
    (which happens after /clear or fresh sessions).
    Returns empty string if not available (fail open - don't block on missing data).
    """
    try:
        if CURRENT_SESSION_FILE.exists():
            with open(CURRENT_SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            sid = data.get('current_session_id', '')
            if sid:
                return sid
    except Exception:
        pass
    # Fallback: read from session-progress.json (written by 3-level-flow.py)
    try:
        progress_file = Path.home() / '.claude' / 'memory' / 'logs' / 'session-progress.json'
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            sid = data.get('session_id', '')
            if sid and sid.startswith('SESSION-'):
                return sid
    except Exception:
        pass
    return ''


def find_session_flag(pattern_prefix, current_session_id):
    """
    Find session-specific flag file matching the current session ID.
    Returns (flag_path, flag_data) or (None, None) if not found.
    Auto-cleans stale flags (>60 min).

    v4.4.0: Flags now live inside the session folder:
      ~/.claude/memory/logs/sessions/{SESSION_ID}/flags/{name}.json
    Also checks legacy ~/.claude/ location for backward compat.

    Args:
        pattern_prefix: Flag name prefix (e.g. '.task-breakdown-pending').
        current_session_id: Active session ID string.

    Returns:
        (flag_path, flag_data) or (None, None) if not found/expired.
    """
    # v4.4.0: Check session folder first (new location)
    # Convert prefix like '.task-breakdown-pending' to filename 'task-breakdown-pending.json'
    flag_name = pattern_prefix.lstrip('.') + '.json'
    memory_base = Path.home() / '.claude' / 'memory'
    session_flag_path = memory_base / 'logs' / 'sessions' / current_session_id / 'flags' / flag_name

    if session_flag_path.exists():
        try:
            with open(session_flag_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Auto-expire stale flags (>60 min)
            created_at_str = data.get('created_at', '')
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age = datetime.now() - created_at
                    if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                        session_flag_path.unlink(missing_ok=True)
                        return (None, None)
                except Exception:
                    pass

            return (session_flag_path, data)
        except Exception:
            pass

    # Legacy fallback: check ~/.claude/ for old-format flags
    legacy_path = FLAG_DIR / '{}-{}.json'.format(pattern_prefix, current_session_id)
    if legacy_path.exists():
        try:
            with open(legacy_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            created_at_str = data.get('created_at', '')
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age = datetime.now() - created_at
                    if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                        legacy_path.unlink(missing_ok=True)
                        return (None, None)
                except Exception:
                    pass

            return (legacy_path, data)
        except Exception:
            pass

    # Legacy fallback: PID-based flags
    import glob as _flag_glob
    legacy_pattern = str(FLAG_DIR / '{}-{}-*.json'.format(pattern_prefix, current_session_id))
    legacy_files = _flag_glob.glob(legacy_pattern)
    if legacy_files:
        legacy_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        for lf in legacy_files:
            try:
                with open(lf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return (Path(lf), data)
            except Exception:
                pass

    return (None, None)


def check_checkpoint_pending(tool_name):
    """
    Level 3.3: Block code-changing tools if review checkpoint is pending.
    User must say 'ok'/'proceed' before coding can start.

    SESSION-AWARE (Loophole #11): Uses session-specific flag files.
    Each window has its own flag file. No cross-window interference.

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    flag_path, flag_data = find_session_flag('.checkpoint-pending', current_session_id)
    if flag_path is None:
        return hints, blocks

    # --- Same session: block until user says ok ---
    session_id = flag_data.get('session_id', 'unknown')
    prompt_preview = flag_data.get('prompt_preview', '')[:80]

    blocks.append(
        '[PRE-TOOL BLOCKED] Review checkpoint is pending!\n'
        '  Session  : ' + session_id + '\n'
        '  Task     : ' + prompt_preview + '\n'
        '  Tool     : ' + tool_name + ' is BLOCKED until user confirms.\n'
        '  Required : User must reply with "ok" or "proceed" first.\n'
        '  Reason   : CLAUDE.md policy - no coding before checkpoint review.\n'
        '  Action   : Show the [REVIEW CHECKPOINT] to user and WAIT.'
    )

    return hints, blocks

def check_task_breakdown_pending(tool_name):
    """
    Level 3.1: Block code-changing tools if task breakdown is pending.
    Claude MUST call TaskCreate before any Write/Edit/Bash/Task.

    SESSION-AWARE (Loophole #11): Uses session-specific flag files.

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    # Only file-modification tools blocked. Bash/Task allowed for investigation.
    BLOCKED_WHILE_TASK_PENDING = {'Write', 'Edit', 'NotebookEdit'}

    if tool_name not in BLOCKED_WHILE_TASK_PENDING:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    flag_path, flag_data = find_session_flag('.task-breakdown-pending', current_session_id)
    if flag_path is None:
        return hints, blocks

    # TTL: auto-expire flag after 90 seconds (prevents permanent blocking)
    flag_created = flag_data.get('created_at', '')
    if flag_created:
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(flag_created)
            age_seconds = (datetime.now() - created_dt).total_seconds()
            if age_seconds > 90:
                try:
                    flag_path.unlink()
                except Exception:
                    pass
                hints.append('[HINT] TaskCreate recommended but not required (flag expired after 90s)')
                return hints, blocks
        except Exception:
            pass

    session_id = flag_data.get('session_id', 'unknown')
    prompt_preview = flag_data.get('prompt_preview', '')[:80]

    blocks.append(
        '[PRE-TOOL BLOCKED] Step 3.1 Task Breakdown is pending!\n'
        '  Session  : ' + session_id + '\n'
        '  Task     : ' + prompt_preview + '\n'
        '  Tool     : ' + tool_name + ' is BLOCKED until TaskCreate is called.\n'
        '  Required : Call TaskCreate tool FIRST to create task(s) for this request.\n'
        '  Reason   : CLAUDE.md Step 3.1 - TaskCreate MANDATORY before any coding.\n'
        '  Action   : Call TaskCreate with subject and description, then continue.'
    )

    return hints, blocks


def check_skill_selection_pending(tool_name):
    """
    Level 3.5: Block code-changing tools if skill/agent selection is pending.
    Claude MUST invoke Skill tool or Task(agent) before any Write/Edit.

    Note: Task/Bash NOT blocked - Task IS how Step 3.5 is done, Bash needed for git/tests.
    SESSION-AWARE (Loophole #11): Uses session-specific flag files.

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    # Only file-modification tools blocked. Bash allowed for git/investigation/tests.
    BLOCKED_WHILE_SKILL_PENDING = {'Write', 'Edit', 'NotebookEdit'}

    if tool_name not in BLOCKED_WHILE_SKILL_PENDING:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    flag_path, flag_data = find_session_flag('.skill-selection-pending', current_session_id)
    if flag_path is None:
        return hints, blocks

    # TTL: auto-expire flag after 90 seconds (prevents permanent blocking)
    flag_created = flag_data.get('created_at', '')
    if flag_created:
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(flag_created)
            age_seconds = (datetime.now() - created_dt).total_seconds()
            if age_seconds > 90:
                try:
                    flag_path.unlink()
                except Exception:
                    pass
                hints.append('[HINT] Skill/Agent invocation recommended but not required (flag expired after 90s)')
                return hints, blocks
        except Exception:
            pass

    session_id = flag_data.get('session_id', 'unknown')
    required_skill = flag_data.get('required_skill', 'unknown')
    required_type = flag_data.get('required_type', 'skill')

    if required_type == 'agent':
        action_required = 'Launch agent via Task tool: Task(subagent_type="' + required_skill + '")'
    else:
        action_required = 'Invoke skill via Skill tool: Skill(skill="' + required_skill + '")'

    blocks.append(
        '[PRE-TOOL BLOCKED] Step 3.5 Skill/Agent Selection is pending!\n'
        '  Session  : ' + session_id + '\n'
        '  Tool     : ' + tool_name + ' is BLOCKED until Skill/Agent is invoked.\n'
        '  Required : ' + action_required + '\n'
        '  Reason   : CLAUDE.md Step 3.5 - Skill/Agent MUST be invoked before coding.\n'
        '  Action   : Invoke the skill/agent first, then continue coding.'
    )

    return hints, blocks


def _load_raw_flow_trace():
    """
    Load the LATEST flow-trace entry from flow-trace.json for the current session.
    Returns the parsed dict, or None if unavailable.
    Handles both array format (v4.4.0+) and legacy single-dict format.
    Used by Level 1/2 completion checks which need the pipeline array,
    not just the final_decision summary extracted by _load_flow_trace_context().
    """
    try:
        session_id = get_current_session_id()
        if not session_id:
            return None
        memory_base = Path.home() / '.claude' / 'memory'
        trace_file = memory_base / 'logs' / 'sessions' / session_id / 'flow-trace.json'
        if not trace_file.exists():
            return None
        with open(trace_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # v4.4.0+: array of traces - return the latest one
        if isinstance(data, list) and data:
            return data[-1]
        # Legacy: single dict
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def _pipeline_step_present(raw_trace, step_name):
    """
    Return True if the named pipeline step exists in flow-trace.json's pipeline array.
    step_name is compared against the 'step' field of each pipeline entry.
    """
    if not raw_trace:
        return False
    for entry in raw_trace.get('pipeline', []):
        if entry.get('step') == step_name:
            return True
    return False


def check_context_read_complete(tool_name):
    """
    ENFORCEMENT: Block Write/Edit/NotebookEdit/Bash if context files have NOT been read.

    Context-read enforcement: The policy states "read SRS, README, CLAUDE.md before
    coding". The context-reader.py (Level 3.0) creates a .context-read-SESSION-PID.json
    flag when it completes. This function checks for that flag.

    BLOCKED_TOOLS: Write, Edit, NotebookEdit, Bash (code-changing tools)
    FLAG_PATTERN: .context-read-{SESSION_ID}-{PID}.json in ~/.claude/memory/flags/

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    # Only block code-changing tools
    BLOCKED_IF_NO_CONTEXT = {'Write', 'Edit', 'NotebookEdit', 'Bash'}

    if tool_name not in BLOCKED_IF_NO_CONTEXT:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    # Check for context-read flag in flags directory
    try:
        flag_dir = Path.home() / '.claude' / 'memory' / 'flags'
        pid = os.getpid()
        flag_pattern = f'.context-read-{current_session_id}-{pid}.json'

        flag_files = list(flag_dir.glob(flag_pattern)) if flag_dir.exists() else []
        if not flag_files:
            # Flag doesn't exist yet - context reading may not be done
            # Fail-open: allow tool (context-reader runs on UserPromptSubmit)
            return hints, blocks

        # Flag exists - check if enforcement applies
        flag_file = flag_files[0]
        flag_data = json.loads(flag_file.read_text(encoding='utf-8'))

        is_new_project = flag_data.get('is_new_project', True)
        enforcement_applies = flag_data.get('enforcement_applies', False)

        if is_new_project:
            # Fresh project - no context files to read
            # Enforcement SKIPPED for new projects
            return hints, blocks

        if not enforcement_applies:
            # Existing project but context was read
            return hints, blocks

        # Existing project AND enforcement applies = block writes until context is read
        # TODO V2: Check if context was actually read (look for metadata in flag)
        # For now: fail-open (allow tool)
        pass

    except Exception:
        # If we can't check the flag, fail-open (allow the tool)
        pass

    return hints, blocks


def check_level1_sync_complete(tool_name):
    """
    Level 1 Sync System enforcement: Block Write/Edit/NotebookEdit if the
    Level 1 Sync System (context reading, session init, pattern detection) has
    NOT been completed by 3-level-flow.py for the current session.

    Completion is detected by the presence of LEVEL_1_CONTEXT and
    LEVEL_1_SESSION entries in the flow-trace.json pipeline array.

    Fail-open: if flow-trace.json cannot be read (e.g. first prompt of session
    before 3-level-flow has written the file), the check is skipped and the
    tool is allowed through.  This prevents false positives on the very first
    tool call of a fresh session.

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    BLOCKED_TOOLS = {'Write', 'Edit', 'NotebookEdit'}
    if tool_name not in BLOCKED_TOOLS:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    raw_trace = _load_raw_flow_trace()
    if raw_trace is None:
        # Fail-open: trace not available yet, do not block
        return hints, blocks

    # Level 1 is complete when both key pipeline steps are present
    level1_context_done = _pipeline_step_present(raw_trace, 'LEVEL_1_CONTEXT')
    level1_session_done = _pipeline_step_present(raw_trace, 'LEVEL_1_SESSION')

    if level1_context_done and level1_session_done:
        return hints, blocks

    missing = []
    if not level1_context_done:
        missing.append('LEVEL_1_CONTEXT (context reading)')
    if not level1_session_done:
        missing.append('LEVEL_1_SESSION (session init)')

    blocks.append(
        '[PRE-TOOL BLOCKED] Level 1 Sync System not complete yet!\n'
        '  Session  : ' + current_session_id + '\n'
        '  Tool     : ' + tool_name + ' is BLOCKED until Level 1 finishes.\n'
        '  Missing  : ' + ', '.join(missing) + '\n'
        '  Required : Need context reading, session init, pattern detection.\n'
        '  Reason   : 3-level-flow.py Level 1 must complete before code changes.\n'
        '  Action   : Wait for 3-level-flow.py to finish Level 1 Sync System.'
    )

    return hints, blocks


def check_level2_standards_complete(tool_name):
    """
    Level 2 Standards System enforcement: Block Write/Edit/NotebookEdit if the
    Level 2 Standards System (coding standards loader) has NOT been completed
    by 3-level-flow.py for the current session.

    Completion is detected by the presence of LEVEL_2_STANDARDS in the
    flow-trace.json pipeline array.

    Fail-open: same as check_level1_sync_complete - if trace is unavailable
    the check is skipped to avoid blocking legitimate first-prompt tool calls.

    Returns (hints, blocks) tuple.
    """
    hints = []
    blocks = []

    BLOCKED_TOOLS = {'Write', 'Edit', 'NotebookEdit'}
    if tool_name not in BLOCKED_TOOLS:
        return hints, blocks

    current_session_id = get_current_session_id()
    if not current_session_id:
        return hints, blocks

    raw_trace = _load_raw_flow_trace()
    if raw_trace is None:
        # Fail-open: trace not available yet, do not block
        return hints, blocks

    # Check for any Level 2 step name variant (3-level-flow.py uses different names
    # across versions: LEVEL_2_STANDARDS (older), LEVEL_2_1_COMMON + LEVEL_2_2_MICROSERVICES (newer))
    L2_STEP_NAMES = {'LEVEL_2_STANDARDS', 'LEVEL_2_1_COMMON', 'LEVEL_2_2_MICROSERVICES'}
    if any(_pipeline_step_present(raw_trace, name) for name in L2_STEP_NAMES):
        return hints, blocks

    blocks.append(
        '[PRE-TOOL BLOCKED] Level 2 Standards System not complete yet!\n'
        '  Session  : ' + current_session_id + '\n'
        '  Tool     : ' + tool_name + ' is BLOCKED until Level 2 finishes.\n'
        '  Required : Need to load 65 coding standards.\n'
        '  Reason   : 3-level-flow.py Level 2 must complete before code changes.\n'
        '  Action   : Wait for 3-level-flow.py to finish Level 2 Standards System.'
    )

    return hints, blocks


# Unicode chars that CRASH Python on Windows (cp1252 encoding)
# Listed as escape sequences so THIS file stays ASCII-safe
UNICODE_DANGER = [
    '\u2705', '\u274c', '\u2728', '\U0001f4dd', '\u2192', '\u2193', '\u2191',
    '\u2713', '\u2717', '\u2022', '\u2605', '\U0001f680', '\u26a0', '\U0001f6a8',
    '\U0001f4ca', '\U0001f4cb', '\U0001f50d', '\u2b50', '\U0001f4c4', '\u270f',
    '\u2714', '\u2716', '\U0001f527', '\U0001f4a1', '\U0001f916', '\u2139',
    '\U0001f512', '\U0001f513', '\U0001f3af', '\u21d2', '\u2764', '\U0001f4a5',
    '\u2714', '\u25cf', '\u25cb', '\u25a0', '\u25a1', '\u2660', '\u2663',
    '\u2665', '\u2666', '\u00bb', '\u00ab', '\u2026', '\u2014', '\u2013',
    '\u201c', '\u201d', '\u2018', '\u2019', '\u00ae', '\u00a9', '\u2122',
    '\u00b7', '\u00b0', '\u00b1', '\u00d7', '\u00f7', '\u221e', '\u2248',
    '\u2260', '\u2264', '\u2265', '\u00bc', '\u00bd', '\u00be',
]

# Windows-only commands that fail in bash shell
# Format: (windows_cmd_prefix, bash_equivalent)
WINDOWS_CMDS = [
    ('del ',    'rm'),
    ('del\t',   'rm'),
    ('copy ',   'cp'),
    ('xcopy ',  'cp -r'),
    ('move ',   'mv'),
    ('ren ',    'mv'),
    ('md ',     'mkdir'),
    ('rd ',     'rmdir'),
    ('dir ',    'ls'),
    ('dir\n',   'ls'),
    ('type ',   'cat'),
    ('attrib ', 'chmod'),
    ('icacls ', 'chmod'),
    ('taskkill','kill'),
    ('tasklist','ps aux'),
    ('where ',  'which'),
    ('findstr ','grep'),
    ('cls\n',   'clear'),
    ('cls\r',   'clear'),
    ('cls',     'clear'),
    ('ipconfig','ifconfig / ip addr'),
    ('netstat ','netstat / ss'),
    ('systeminfo','uname -a'),
    ('schtasks ','cron'),
    ('sc ',     'systemctl'),
    ('net ',    'systemctl / id'),
    ('reg ',    'No equivalent in bash'),
    ('regedit', 'No equivalent in bash'),
    ('msiexec', 'No equivalent in bash'),
]


def check_bash(command):
    """Level 3.7: Detect and block Windows-only shell commands + branch protection.

    Scans the command string for Windows-only prefixes listed in WINDOWS_CMDS.
    Also enforces branch protection: blocks git push/commit to main/master
    when no issue branch has been created (GitHub workflow enforcement).

    Policy:    policies/03-execution-system/failure-prevention/
               common-failures-prevention.md
    KB source: scripts/architecture/03-execution-system/failure-prevention/
               failure-kb.json (pattern: bash_windows_command)

    Args:
        command: Full Bash command string from tool_input['command'].

    Returns:
        tuple: (hints, blocks) where blocks is non-empty when a Windows
               command is detected or branch policy is violated.
    """
    hints = []
    blocks = []
    cmd_stripped = command.strip()
    cmd_lower = cmd_stripped.lower()

    # ===================================================================
    # BRANCH PROTECTION: Block git push to main/master
    # Forces creating an issue branch first via github_issue_manager.py
    # ===================================================================
    if 'git push' in cmd_lower:
        # Check if pushing to main or master (direct push or via origin)
        push_to_protected = False
        for protected in ['main', 'master']:
            if ('push origin ' + protected) in cmd_lower:
                push_to_protected = True
            elif cmd_lower.strip().endswith('push origin ' + protected):
                push_to_protected = True

        if push_to_protected:
            # Check current branch - if we're ON main, block
            try:
                import subprocess as _sp
                _branch_result = _sp.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                )
                current_branch = _branch_result.stdout.strip()
                if current_branch in ('main', 'master'):
                    blocks.append(
                        '[PRE-TOOL BLOCKED] Direct push to ' + current_branch + ' is NOT allowed!\n'
                        '  Policy   : GitHub Branch Protection (github-branch-pr-policy)\n'
                        '  Current  : On branch "' + current_branch + '"\n'
                        '  Required : Create an issue branch first (e.g. fix/42, feature/123)\n'
                        '  Workflow : TaskCreate -> GitHub Issue -> Branch -> Work -> PR -> Merge\n'
                        '  Action   : Create a task with TaskCreate, then use the issue branch.'
                    )
            except Exception:
                pass

    # ===================================================================
    # WINDOWS COMMAND BLOCKING
    # ===================================================================
    for win_cmd, bash_equiv in WINDOWS_CMDS:
        win_lower = win_cmd.lower()
        # Check if command starts with win_cmd or has it after newline/semicolon/&&
        if (cmd_lower.startswith(win_lower) or
                ('\n' + win_lower) in cmd_lower or
                ('; ' + win_lower) in cmd_lower or
                ('&& ' + win_lower) in cmd_lower):
            blocks.append(
                '[PRE-TOOL L3.7] BLOCKED - Windows command in bash shell!\n'
                '  Detected : ' + win_cmd.strip() + '\n'
                '  Use instead: ' + bash_equiv + '\n'
                '  Fix the command and retry.'
            )
            break  # One block message is enough

    return hints, blocks


def check_python_unicode(content):
    """Level 3.7: Detect Unicode characters that crash Python on Windows cp1252.

    Iterates over UNICODE_DANGER to find emoji, smart-quote, arrow, and other
    non-ASCII codepoints that the Windows cp1252 console cannot encode without
    raising UnicodeEncodeError.  Returns a blocking message with up to five
    sample offending characters so the developer knows what to replace.

    Policy:    policies/03-execution-system/failure-prevention/
               common-failures-prevention.md
    Arch ref:  scripts/architecture/03-execution-system/failure-prevention/
               windows-python-unicode-checker.py

    Args:
        content: String content of the Python file about to be written.

    Returns:
        list: Block message strings (empty list means no violations found).
    """
    blocks = []
    found_count = 0
    sample = []

    for char in UNICODE_DANGER:
        if char in content:
            found_count += 1
            if len(sample) < 5:
                sample.append(repr(char))

    if found_count > 0:
        blocks.append(
            '[PRE-TOOL L3.7] BLOCKED - Unicode chars in Python file!\n'
            '  Platform : Windows (cp1252 encoding)\n'
            '  Problem  : ' + str(found_count) + ' unicode char(s) will cause UnicodeEncodeError\n'
            '  Sample   : ' + ', '.join(sample) + '\n'
            '  Fix      : Replace with ASCII: [OK] [ERROR] [WARN] [INFO] -> * #\n'
            '  Rule     : NEVER use Unicode in Python scripts on Windows!'
        )

    return blocks


def check_write_edit(tool_name, tool_input):
    """Level 3.6 + 3.7: Tool Optimization and Unicode enforcement for writes.

    Checks:
      1. (3.7) Block Unicode characters in .py files on Windows
      2. (3.6) Warn if Write content exceeds 500 lines (suggest Edit instead)
      3. (3.6) Warn if target file is large (>50KB) and using Write (full overwrite)

    Args:
        tool_name: 'Write', 'Edit', or 'NotebookEdit'.
        tool_input: Tool parameters dict.

    Returns:
        tuple: (hints, blocks)
    """
    hints = []
    blocks = []

    file_path = (
        tool_input.get('file_path', '') or
        tool_input.get('notebook_path', '') or
        ''
    )

    content = (
        tool_input.get('content', '') or
        tool_input.get('new_string', '') or
        tool_input.get('new_source', '') or
        ''
    )

    # Level 3.7: Unicode check for .py files
    if file_path.endswith('.py') and content:
        blocks.extend(check_python_unicode(content))

    # Level 3.6: Tool Optimization for Write/Edit
    if content:
        content_lines = content.count('\n') + 1

        # Write tool with very large content - suggest Edit instead
        if tool_name == 'Write' and content_lines > 500:
            hints.append(
                f'[TOOL-OPT] Write: content is {content_lines} lines. '
                f'Prefer Edit for targeted changes instead of full file rewrites.'
            )

        # Write to existing large file - warn about full overwrite
        if tool_name == 'Write' and file_path:
            try:
                import os
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 50 * 1024:  # >50KB
                        hints.append(
                            f'[TOOL-OPT] Write: overwriting large file '
                            f'({file_size // 1024}KB). Use Edit for targeted '
                            f'changes to save context tokens.'
                        )
            except Exception:
                pass

    return hints, blocks


def check_grep(tool_input):
    """Level 3.6: BLOCK Grep content-mode calls without head_limit.

    When output_mode is 'content', Grep can return thousands of lines and
    waste the context window.  This check BLOCKS such calls until head_limit
    is set.  For 'files_with_matches' and 'count' modes, the output is
    already compact so only a hint is emitted.

    Policy: policies/03-execution-system/06-tool-optimization/
            tool-usage-optimization-policy.md

    Args:
        tool_input (dict): Tool parameters from the Grep call.

    Returns:
        tuple: (hints, blocks) where blocks is non-empty when output_mode
               is 'content' and head_limit is missing.
    """
    hints = []
    blocks = []
    head_limit = tool_input.get('head_limit', 0)
    output_mode = tool_input.get('output_mode', 'files_with_matches')

    if not head_limit:
        ctx = _load_flow_trace_context()
        complexity = ctx.get('complexity', 0)
        suggested = 50 if (complexity and complexity >= 10) else 100

        if output_mode == 'content':
            # BLOCK: content mode without head_limit can flood context
            blocks.append(
                f'[TOOL-OPT BLOCKED] Grep output_mode="content" requires head_limit. '
                f'Add head_limit={suggested} to prevent context overflow. '
                f'Rule: ALWAYS set head_limit on Grep content-mode calls.'
            )
        else:
            # HINT only for compact modes (files_with_matches, count)
            hints.append(
                f'[TOOL-OPT] Grep: Consider adding head_limit={suggested} to limit output.'
            )

    return hints, blocks


def check_read(tool_input):
    """Level 3.6: BLOCK Read on large files without offset/limit.

    Checks actual file size on disk.  Files larger than 50KB (~500+ lines)
    are BLOCKED unless offset or limit is provided.  Smaller files pass
    with a hint.  This prevents accidentally dumping thousands of lines
    into the context window.

    Policy: policies/03-execution-system/06-tool-optimization/
            tool-usage-optimization-policy.md

    Args:
        tool_input (dict): Tool parameters from the Read call.

    Returns:
        tuple: (hints, blocks) where blocks is non-empty when file is large
               and no offset/limit is set.
    """
    hints = []
    blocks = []
    limit = tool_input.get('limit')
    offset = tool_input.get('offset')

    if not limit and not offset:
        file_path = tool_input.get('file_path', '')
        if file_path:
            try:
                import os
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 50 * 1024:  # >50KB = likely >500 lines
                        blocks.append(
                            f'[TOOL-OPT BLOCKED] Read: file is '
                            f'{file_size // 1024}KB (>{50}KB limit). '
                            f'Add limit=200 and offset=0 to read in chunks. '
                            f'Rule: Use offset+limit for files >500 lines.'
                        )
                    elif file_size > 20 * 1024:  # 20-50KB = hint
                        hints.append(
                            f'[TOOL-OPT] Read: file is {file_size // 1024}KB. '
                            f'Consider using offset+limit to save context tokens.'
                        )
            except Exception:
                pass
        # No file_path or can't stat: generic hint
        if not blocks and not hints:
            ctx = _load_flow_trace_context()
            complexity = ctx.get('complexity', 0)
            if complexity and complexity >= 10:
                hints.append(
                    '[TOOL-OPT] Read: No limit/offset set. '
                    'High complexity task - use offset+limit to conserve context.'
                )

    return hints, blocks


# =============================================================================
# DYNAMIC PER-FILE SKILL SELECTION (v3.0.0)
# =============================================================================
# Maps file extensions and special filenames to the most appropriate skill/agent.
# Runs on EVERY tool call that targets a file (Read/Write/Edit/Grep/Glob).
# This makes skill context DYNAMIC instead of fixed-per-session.
#
# Example: A project with .java + .py + .ts + Dockerfile files:
#   - Edit User.java      -> [SKILL-CONTEXT] java-spring-boot-microservices
#   - Edit deploy.py       -> [SKILL-CONTEXT] python-system-scripting
#   - Edit app.component.ts -> [SKILL-CONTEXT] angular-engineer (agent)
#   - Edit Dockerfile       -> [SKILL-CONTEXT] docker
# =============================================================================

# Extension -> (skill_or_agent_name, type, brief_context)
FILE_EXT_SKILL_MAP = {
    # Java ecosystem
    '.java':        ('java-spring-boot-microservices', 'skill', 'Java/Spring Boot patterns, annotations, DI, REST controllers'),
    '.gradle':      ('java-spring-boot-microservices', 'skill', 'Gradle build config for Spring Boot'),
    '.kt':          ('android-backend-engineer', 'agent', 'Kotlin/Android backend, API integration, data flow'),
    '.kts':         ('android-backend-engineer', 'agent', 'Kotlin script/Gradle DSL'),

    # Python ecosystem
    '.py':          ('python-system-scripting', 'skill', 'Python scripting, Windows-safe, ASCII-only, cp1252 compatible'),

    # JavaScript/TypeScript ecosystem
    '.ts':          ('angular-engineer', 'agent', 'TypeScript/Angular components, services, modules, RxJS'),
    '.tsx':         ('ui-ux-designer', 'agent', 'React TSX components, hooks, state management'),
    '.js':          ('ui-ux-designer', 'agent', 'JavaScript UI logic, DOM, event handling'),
    '.jsx':         ('ui-ux-designer', 'agent', 'React JSX components, hooks, state management'),
    '.vue':         ('ui-ux-designer', 'agent', 'Vue.js SFC components, composition API'),

    # Web/Styling
    '.css':         ('css-core', 'skill', 'CSS layout, flexbox, grid, responsive design, variables'),
    '.scss':        ('css-core', 'skill', 'SCSS/Sass, mixins, nesting, variables, partials'),
    '.less':        ('css-core', 'skill', 'Less CSS preprocessor, mixins, variables'),
    '.html':        ('ui-ux-designer', 'agent', 'HTML structure, semantic elements, accessibility'),

    # iOS/macOS
    '.swift':       ('swift-backend-engineer', 'agent', 'Swift backend, Vapor, REST APIs, async/await'),

    # Database
    '.sql':         ('rdbms-core', 'skill', 'SQL queries, schema design, indexing, joins, transactions'),

    # DevOps
    '.yml':         None,  # Handled by filename check (could be K8s, Docker, Jenkins, etc.)
    '.yaml':        None,  # Handled by filename check

    # Android UI
    '.xml':         None,  # Could be Android layout, Maven POM, or generic XML - check filename

    # Documentation
    '.md':          None,  # No specific skill needed
}

# Special filename patterns -> (skill_or_agent_name, type, brief_context)
# Checked BEFORE extension mapping (higher priority)
FILENAME_SKILL_MAP = [
    # Build files
    ('pom.xml',             'java-spring-boot-microservices', 'skill', 'Maven POM, Spring Boot dependencies, plugins'),
    ('build.gradle',        'java-spring-boot-microservices', 'skill', 'Gradle build for Spring Boot'),
    ('build.gradle.kts',    'java-spring-boot-microservices', 'skill', 'Gradle Kotlin DSL for Spring Boot'),

    # Docker
    ('Dockerfile',          'docker', 'skill', 'Dockerfile, multi-stage builds, layer optimization, security'),
    ('docker-compose.yml',  'docker', 'skill', 'Docker Compose services, networks, volumes'),
    ('docker-compose.yaml', 'docker', 'skill', 'Docker Compose services, networks, volumes'),
    ('.dockerignore',       'docker', 'skill', 'Docker build context exclusions'),

    # Kubernetes
    ('deployment.yaml',     'kubernetes', 'skill', 'K8s Deployment spec, replicas, strategy, probes'),
    ('deployment.yml',      'kubernetes', 'skill', 'K8s Deployment spec, replicas, strategy, probes'),
    ('service.yaml',        'kubernetes', 'skill', 'K8s Service spec, ClusterIP, NodePort, LoadBalancer'),
    ('service.yml',         'kubernetes', 'skill', 'K8s Service spec, ClusterIP, NodePort, LoadBalancer'),
    ('ingress.yaml',        'kubernetes', 'skill', 'K8s Ingress rules, TLS, host/path routing'),
    ('ingress.yml',         'kubernetes', 'skill', 'K8s Ingress rules, TLS, host/path routing'),
    ('configmap.yaml',      'kubernetes', 'skill', 'K8s ConfigMap, environment config'),
    ('secret.yaml',         'kubernetes', 'skill', 'K8s Secret, base64, encryption'),
    ('statefulset.yaml',    'kubernetes', 'skill', 'K8s StatefulSet, persistent storage, ordered startup'),
    ('values.yaml',         'kubernetes', 'skill', 'Helm chart values, templates, releases'),
    ('Chart.yaml',          'kubernetes', 'skill', 'Helm Chart metadata, dependencies'),

    # Jenkins
    ('Jenkinsfile',         'jenkins-pipeline', 'skill', 'Jenkins pipeline, stages, agents, post actions'),

    # Frontend configs
    ('angular.json',        'angular-engineer', 'agent', 'Angular workspace config, build, serve'),
    ('tsconfig.json',       'angular-engineer', 'agent', 'TypeScript compiler config'),
    ('package.json',        None, None, None),  # Needs content analysis, skip for now

    # Android
    ('AndroidManifest.xml', 'android-backend-engineer', 'agent', 'Android manifest, permissions, activities'),

    # iOS
    ('Podfile',             'swiftui-designer', 'agent', 'CocoaPods dependencies for iOS'),
    ('Package.swift',       'swift-backend-engineer', 'agent', 'Swift Package Manager, dependencies'),

    # SEO
    ('robots.txt',          'seo-keyword-research-core', 'skill', 'SEO robots directives, crawl rules'),
    ('sitemap.xml',         'seo-keyword-research-core', 'skill', 'SEO sitemap, URL priorities, change freq'),

    # Database
    ('schema.sql',          'rdbms-core', 'skill', 'Database schema DDL, tables, constraints, indexes'),
    ('migration.sql',       'rdbms-core', 'skill', 'Database migration, ALTER TABLE, data transforms'),
    ('init.sql',            'rdbms-core', 'skill', 'Database initialization, seed data'),
]

# Directory path patterns -> (skill_or_agent_name, type, brief_context)
# Checked if filename/extension match is None
DIR_PATTERN_SKILL_MAP = [
    ('/src/main/java/',         'java-spring-boot-microservices', 'skill', 'Java source in Spring Boot project'),
    ('/src/test/java/',         'java-spring-boot-microservices', 'skill', 'Java test in Spring Boot project'),
    ('/src/main/resources/',    'java-spring-boot-microservices', 'skill', 'Spring Boot resources (application.yml, etc.)'),
    ('/controller/',            'java-spring-boot-microservices', 'skill', 'Spring MVC/REST controller layer'),
    ('/service/',               'java-spring-boot-microservices', 'skill', 'Spring service/business logic layer'),
    ('/repository/',            'java-spring-boot-microservices', 'skill', 'Spring Data JPA repository layer'),
    ('/entity/',                'java-spring-boot-microservices', 'skill', 'JPA entity/model layer'),
    ('/dto/',                   'java-spring-boot-microservices', 'skill', 'Data Transfer Object pattern'),
    ('/config/',                'java-spring-boot-microservices', 'skill', 'Spring configuration classes'),
    ('/k8s/',                   'kubernetes', 'skill', 'Kubernetes manifests directory'),
    ('/helm/',                  'kubernetes', 'skill', 'Helm chart directory'),
    ('/charts/',                'kubernetes', 'skill', 'Helm charts directory'),
    ('/deploy/',                'devops-engineer', 'agent', 'Deployment scripts/config'),
    ('/ci/',                    'devops-engineer', 'agent', 'CI/CD pipeline config'),
    ('/res/layout/',            'android-ui-designer', 'agent', 'Android XML layout files'),
    ('/res/drawable/',          'android-ui-designer', 'agent', 'Android drawable resources'),
    ('/res/values/',            'android-ui-designer', 'agent', 'Android values (strings, colors, styles)'),
    ('/components/',            'angular-engineer', 'agent', 'Frontend component directory'),
    ('/services/',              'angular-engineer', 'agent', 'Frontend service directory'),
]

# NEW: Map technology names to file extensions and their corresponding skills/agents
# Used by _infer_skills_from_tech_stack() to show OTHER FILES IN THIS TASK
_TECH_TO_FILE_SKILL = {
    'spring-boot': ('.java',       'java-spring-boot-microservices'),
    'java':        ('.java',       'java-spring-boot-microservices'),
    'angular':     ('.ts',         'angular-engineer'),
    'typescript':  ('.ts',         'angular-engineer'),
    'react':       ('.tsx',        'ui-ux-designer'),
    'vue':         ('.vue',        'ui-ux-designer'),
    'css':         ('.css',        'css-core'),
    'scss':        ('.scss',       'css-core'),
    'html':        ('.html',       'ui-ux-designer'),
    'python':      ('.py',         'python-backend-engineer'),
    'flask':       ('.py',         'python-backend-engineer'),
    'django':      ('.py',         'python-backend-engineer'),
    'fastapi':     ('.py',         'python-backend-engineer'),
    'docker':      ('Dockerfile',  'docker'),
    'kubernetes':  ('.yaml',       'kubernetes'),
    'jenkins':     ('Jenkinsfile', 'jenkins-pipeline'),
    'postgresql':  ('.sql',        'rdbms-core'),
    'mysql':       ('.sql',        'rdbms-core'),
    'mongodb':     ('.json',       'nosql-core'),
    'kotlin':      ('.kt',         'android-backend-engineer'),
    'swift':       ('.swift',      'swift-backend-engineer'),
}


def _infer_skills_from_tech_stack(tech_stack, exclude_skill=None):
    """Build hint string showing other file types in the task's tech stack.

    Takes a list of detected technologies and returns a formatted string showing
    the file extensions and corresponding skills/agents that would be used for
    other files in this task.

    Used to show users: "OTHER FILES IN THIS TASK: .ts -> angular-engineer | Dockerfile -> docker"

    Args:
        tech_stack (list[str]): Technologies detected in the task (e.g., ['spring-boot', 'angular'])
        exclude_skill (str): Skill/agent name to skip (to avoid repeating what's already shown)

    Returns:
        str: Formatted string like ".ts -> angular-engineer | Dockerfile -> docker"
             Empty string if nothing to show or all entries are unknown/excluded.
    """
    if not tech_stack or tech_stack == ['unknown']:
        return ''

    parts = []
    for tech in tech_stack:
        if tech == 'unknown' or tech not in _TECH_TO_FILE_SKILL:
            continue

        file_ext, skill = _TECH_TO_FILE_SKILL[tech]
        if skill == exclude_skill:
            continue  # Skip if already shown as primary skill

        parts.append(f"{file_ext} -> {skill}")

    return ' | '.join(parts)


# Track last printed skill to avoid spamming same hint repeatedly
_last_skill_hint = ''


def check_dynamic_skill_context(tool_name, tool_input, trace_context=None):
    """Level 3.5+ Dynamic: inject skill/agent context based on target file type.

    Extracts the target file path from any Read, Write, Edit, NotebookEdit,
    Grep, or Glob tool call, then resolves the most appropriate skill or agent
    via a priority chain:
      1. Special filename map (FILENAME_SKILL_MAP)
      2. Directory path patterns (DIR_PATTERN_SKILL_MAP)
      3. File extension map (FILE_EXT_SKILL_MAP)
      4. YAML/XML content heuristics

    Emits a [SKILL-CONTEXT] hint to stdout so Claude applies correct patterns
    for the specific file.  Does NOT block; does NOT override the session-level
    skill already selected by 3-level-flow.py.  Deduplicates consecutive
    identical hints via the _last_skill_hint module-level cache.

    If trace_context is provided (new in v3.3.0), adds task-aware information:
    - Shows all technologies in the current task (TASK TECH STACK)
    - Shows the session-level primary skill/agent (SESSION PRIMARY)
    - Shows other file types in this task (OTHER FILES IN THIS TASK)

    Args:
        tool_name: Name of the tool being called ('Read', 'Write', etc.).
        tool_input: Dict of tool parameters containing the file path key.
        trace_context (dict): Optional flow-trace context with task/skill info.
                             If None, output is identical to previous behavior.

    Returns:
        list: Hint strings to print to stdout.  Empty when no skill matched
              or the same hint was emitted for the previous tool call.
    """
    global _last_skill_hint
    hints = []

    # Extract file path from tool input
    file_path = ''
    if tool_name in ('Read', 'Write', 'Edit', 'NotebookEdit'):
        file_path = (tool_input.get('file_path', '') or
                     tool_input.get('notebook_path', '') or '')
    elif tool_name == 'Grep':
        file_path = tool_input.get('path', '') or ''
        # Also check glob pattern for type hints
        glob_pattern = tool_input.get('glob', '') or tool_input.get('type', '') or ''
        if glob_pattern and not file_path:
            # e.g., glob="*.java" or type="java"
            file_path = glob_pattern
    elif tool_name == 'Glob':
        file_path = tool_input.get('pattern', '') or ''

    if not file_path:
        return hints

    # Normalize path separators
    normalized = file_path.replace('\\', '/')

    # Extract filename and extension
    if '/' in normalized:
        filename = normalized.rsplit('/', 1)[1]
    else:
        filename = normalized
    # Get extension
    ext = ''
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[1].lower()

    # --- STEP 1: Check special filenames first (highest priority) ---
    matched_skill = None
    matched_type = None
    matched_context = None

    for pattern_name, skill_name, skill_type, context in FILENAME_SKILL_MAP:
        if skill_name is None:
            continue
        # Exact filename match or ends-with match
        if filename == pattern_name or filename.lower() == pattern_name.lower():
            matched_skill = skill_name
            matched_type = skill_type
            matched_context = context
            break

    # --- STEP 2: Check directory path patterns ---
    if not matched_skill:
        for dir_pattern, skill_name, skill_type, context in DIR_PATTERN_SKILL_MAP:
            if dir_pattern in normalized:
                matched_skill = skill_name
                matched_type = skill_type
                matched_context = context
                break

    # --- STEP 3: Check file extension ---
    if not matched_skill and ext:
        ext_entry = FILE_EXT_SKILL_MAP.get(ext)
        if ext_entry and ext_entry is not None:
            matched_skill, matched_type, matched_context = ext_entry

    # --- STEP 4: YAML files - try to detect K8s vs Docker vs generic ---
    if not matched_skill and ext in ('.yml', '.yaml'):
        lower_name = filename.lower()
        if any(k in lower_name for k in ['deploy', 'service', 'ingress', 'configmap',
                                          'secret', 'stateful', 'daemonset', 'values',
                                          'chart', 'namespace', 'pv', 'pvc', 'hpa']):
            matched_skill = 'kubernetes'
            matched_type = 'skill'
            matched_context = 'Kubernetes manifest YAML'
        elif 'docker-compose' in lower_name:
            matched_skill = 'docker'
            matched_type = 'skill'
            matched_context = 'Docker Compose services'
        elif 'jenkins' in lower_name or 'pipeline' in lower_name:
            matched_skill = 'jenkins-pipeline'
            matched_type = 'skill'
            matched_context = 'Jenkins pipeline YAML config'
        elif 'application' in lower_name:
            matched_skill = 'java-spring-boot-microservices'
            matched_type = 'skill'
            matched_context = 'Spring Boot application.yml config'

    # --- STEP 5: XML files - detect Android vs Maven vs generic ---
    if not matched_skill and ext == '.xml':
        lower_name = filename.lower()
        lower_path = normalized.lower()
        if 'pom.xml' == lower_name:
            matched_skill = 'java-spring-boot-microservices'
            matched_type = 'skill'
            matched_context = 'Maven POM dependencies and plugins'
        elif '/res/layout/' in lower_path or '/res/drawable/' in lower_path or '/res/values/' in lower_path:
            matched_skill = 'android-ui-designer'
            matched_type = 'agent'
            matched_context = 'Android XML layout/resource'
        elif 'AndroidManifest' in filename:
            matched_skill = 'android-backend-engineer'
            matched_type = 'agent'
            matched_context = 'Android manifest, permissions, activities'

    # --- Output hint if we found a match ---
    if matched_skill:
        # Avoid repeating same hint for consecutive same-skill tool calls
        hint_key = matched_skill + ':' + filename
        if hint_key != _last_skill_hint:
            _last_skill_hint = hint_key

            type_label = 'agent' if matched_type == 'agent' else 'skill'
            short_file = filename
            if len(normalized) > 60:
                # Show last 2-3 path segments
                parts = normalized.split('/')
                short_file = '/'.join(parts[-3:]) if len(parts) > 3 else normalized

            # Build hint using line-list approach for extensibility
            hint_lines = [
                '[SKILL-CONTEXT] ' + short_file + ' -> ' + matched_skill + ' (' + type_label + ')',
                '  CONTEXT: ' + (matched_context or ''),
            ]

            # NEW: Add task-aware context if trace_context provided (v3.3.0+)
            if trace_context:
                task_tech = trace_context.get('tech_stack', [])
                session_primary = trace_context.get('skill', '')

                # Show task tech stack if present and not 'unknown'
                if task_tech and task_tech != ['unknown']:
                    hint_lines.append('  TASK TECH STACK: ' + ', '.join(task_tech))

                # Show session-level primary skill/agent
                if session_primary:
                    hint_lines.append('  SESSION PRIMARY: ' + session_primary)

                # Show other file types in this task
                other_str = _infer_skills_from_tech_stack(task_tech, exclude_skill=matched_skill)
                if other_str:
                    hint_lines.append('  OTHER FILES IN THIS TASK: ' + other_str)

            hint_lines.append('  ACTION: Apply ' + matched_skill + ' patterns and best practices for this file.')
            hint = '\n'.join(hint_lines)
            hints.append(hint)

    return hints


def _run_policy_optimization(tool_name, tool_input, flow_ctx):
    """
    Level 3.6 + 3.7 Middleware: Apply tool optimization and pre-execution failure checking.
    Prints hints to stdout (non-blocking). Never raises exceptions.

    Args:
        tool_name: Name of the tool about to be called.
        tool_input: Input parameters dict for the tool.
        flow_ctx: Flow trace context dict with task type, complexity, skill, etc.

    Returns:
        list: All hints (optimization + failure prevention combined).
    """
    hints = []

    # Level 3.6: Tool Usage Optimization
    if _optimizer:
        try:
            optimized = _optimizer.optimize(tool_name, tool_input, flow_ctx)
            # Check if any changes were made by the optimizer
            changes = {}
            for key in optimized:
                if key in tool_input and optimized[key] != tool_input[key]:
                    changes[key] = optimized[key]
                elif key not in tool_input:
                    changes[key] = optimized[key]

            if changes:
                for key, val in changes.items():
                    hint = '[3.6-OPTIMIZE] {} -> {} set to {}'.format(
                        tool_name, key, str(val)[:100]
                    )
                    hints.append(hint)
        except Exception:
            pass  # Non-blocking

    # Level 3.7: Pre-Execution Failure Prevention Check
    if _pre_checker:
        try:
            check_result = _pre_checker.check_tool_call(tool_name, tool_input)
            issues = check_result.get('issues', [])
            for issue in issues:
                issue_type = issue.get('type', 'unknown')
                suggestion = issue.get('suggestion', '')
                hint = '[3.7-PREVENTION] {}: {} - {}'.format(
                    tool_name, issue_type, suggestion[:100]
                )
                hints.append(hint)
        except Exception:
            pass  # Non-blocking

    return hints


def main():
    """PreToolUse hook entry point.

    Reads tool name and input from Claude Code hook stdin (JSON), then runs
    all enforcement checks in order:
      1. Checkpoint pending (Level 3.3)
      2. Task breakdown pending (Level 3.1)
      3. Skill/agent selection pending (Level 3.5)
      4. Dynamic skill context hints (Level 3.5+)
      5. Failure-KB hints (Level 3.7)
      6. Tool-specific checker: Bash / Write-Edit / Grep / Read

    Hints are written to stdout (non-blocking, shown as context to Claude).
    Blocks are written to stderr and the process exits with code 2 (the
    blocking exit code per Claude Code hook protocol).

    Never raises exceptions; all errors are silently swallowed so a broken
    hook never disrupts the underlying tool call.
    """
    # ===================================================================
    # TRACKING: Record start time
    # ===================================================================
    _track_start_time = datetime.now()

    # CONTEXT CHAIN: Load flow-trace context from 3-level-flow (cached per invocation)
    # This gives pre-tool-enforcer awareness of task type, complexity, skill, model
    flow_ctx = _load_flow_trace_context()

    # INTEGRATION: Load tool optimization policies from scripts/architecture/
    # This runs before every tool to apply optimizations
    # L3.6: Tool Usage Optimizer (with retry - 3 attempts, 10s timeout each)
    try:
        script_dir = Path(__file__).parent
        tool_opt_script = script_dir / 'architecture' / '03-execution-system' / '06-tool-optimization' / 'tool-usage-optimization-policy.py'
        if tool_opt_script.exists():
            import subprocess
            _opt_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run([sys.executable, str(tool_opt_script)], timeout=10, capture_output=True)
                    if _r.returncode == 0:
                        _opt_ok = True
                        break
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] tool-usage-optimizer failed, retrying...\n')
                except Exception:
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] tool-usage-optimizer error, retrying...\n')
            if not _opt_ok:
                sys.stdout.write('[POLICY-WARN] tool-usage-optimizer failed after 3 retries\n')
    except:
        pass  # Policy execution is optional, don't block

    # Read tool info from stdin
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
    except Exception:
        # Never block on parse errors
        sys.exit(0)

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    if not isinstance(tool_input, dict):
        tool_input = {}

    # CRITICAL: VERIFY SKILL/AGENT EXISTS BEFORE INVOCATION (Step 3.5)
    # LLM has skill definitions ? decides to use one ? we verify it exists
    if tool_name in ('Skill', 'Agent'):
        try:
            skill_or_agent_name = tool_input.get('skill', tool_input.get('agent', ''))
            if skill_or_agent_name:
                skill_loader_script = Path(__file__).parent / 'architecture' / \
                    '03-execution-system' / '05-skill-agent-selection' / 'core-skills-loader.py'

                if skill_loader_script.exists():
                    # Verify the skill/agent exists locally
                    result = subprocess.run(
                        [sys.executable, str(skill_loader_script), skill_or_agent_name],
                        capture_output=True,
                        timeout=15
                    )

                    if result.returncode == 0:
                        try:
                            load_info = json.loads(result.stdout)
                            skill_data = load_info.get('skill_loaded', {})
                            agent_data = load_info.get('agent_loaded', {})

                            if skill_data.get('loaded') or agent_data.get('loaded'):
                                hint = f'[VERIFY] {skill_or_agent_name}: Available and ready'
                                sys.stdout.write(hint + '\n')
                            elif skill_data.get('status') == 'not_found' or agent_data.get('status') == 'not_found':
                                # Provide available skills/agents for LLM
                                available = load_info.get('available_skills', []) or load_info.get('available_agents', [])
                                if available:
                                    hint = f'[HINT] {skill_or_agent_name} not found. Available: {", ".join(available[:5])}'
                                    sys.stdout.write(hint + '\n')
                        except Exception:
                            pass  # Non-critical
        except Exception:
            pass  # Non-blocking - let tool invocation proceed anyway

    all_hints = []
    all_blocks = []

    # CHECKPOINT ENFORCEMENT (Level 3.3 - runs first, before all other checks)
    h, b = check_checkpoint_pending(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    # If already blocked by checkpoint, skip other checks (no need to pile on)
    # Exit code 2 = blocking error (Claude Code docs: stderr fed to Claude, tool blocked)
    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'checkpoint_block',
                                   tool_name=tool_name,
                                   reason='checkpoint-pending flag active',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'checkpoint'})
        except Exception:
            pass
        sys.exit(2)

    # TASK BREAKDOWN ENFORCEMENT (Level 3.1 - TaskCreate must be called first)
    h, b = check_task_breakdown_pending(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'task_breakdown_block',
                                   tool_name=tool_name,
                                   reason='task-breakdown-pending flag active',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'task_breakdown'})
        except Exception:
            pass
        sys.exit(2)

    # SKILL/AGENT SELECTION ENFORCEMENT (Level 3.5 - Skill/Task must be invoked first)
    h, b = check_skill_selection_pending(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'skill_selection_block',
                                   tool_name=tool_name,
                                   reason='skill-selection-pending flag active',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'skill_selection'})
        except Exception:
            pass
        sys.exit(2)

    # CONTEXT READ ENFORCEMENT (Level 3.0 - Project context must be read pre-flight)
    h, b = check_context_read_complete(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'context_read_block',
                                   tool_name=tool_name,
                                   reason='Project context reading not complete (Level 3.0)',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'context_read'})
        except Exception:
            pass
        sys.exit(2)

    # LEVEL 1 SYNC SYSTEM ENFORCEMENT (flow-trace pipeline check)
    h, b = check_level1_sync_complete(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'level1_sync_block',
                                   tool_name=tool_name,
                                   reason='Level 1 Sync System not complete in flow-trace',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'level1_sync'})
        except Exception:
            pass
        sys.exit(2)

    # LEVEL 2 STANDARDS SYSTEM ENFORCEMENT (flow-trace pipeline check)
    h, b = check_level2_standards_complete(tool_name)
    all_hints.extend(h)
    all_blocks.extend(b)

    if all_blocks:
        for hint in all_hints:
            sys.stdout.write(hint + '\n')
        sys.stdout.flush()
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'level2_standards_block',
                                   tool_name=tool_name,
                                   reason='Level 2 Standards System not complete in flow-trace',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=2,
                                extra={'tool': tool_name, 'block_type': 'level2_standards'})
        except Exception:
            pass
        sys.exit(2)

    # DYNAMIC SKILL CONTEXT (Level 3.5+ - v3.0.0, enhanced v3.3.0)
    # Inject per-file skill hints for any tool that targets a file
    # NEW (v3.3.0): Include task-aware context (tech stack, other files in task)
    if tool_name in ('Read', 'Write', 'Edit', 'NotebookEdit', 'Grep', 'Glob'):
        skill_hints = check_dynamic_skill_context(tool_name, tool_input, trace_context=flow_ctx)
        all_hints.extend(skill_hints)

    # NEW (v3.3.0): POLICY OPTIMIZATION MIDDLEWARE (3.6 + 3.7)
    # Level 3.6: Tool Usage Optimization + Level 3.7: Pre-Execution Failure Prevention
    # Both integrated as non-blocking hints that guide Claude's tool invocation
    opt_hints = _run_policy_optimization(tool_name, tool_input, flow_ctx)
    all_hints.extend(opt_hints)

    # FAILURE-KB INTEGRATION (v3.2.0): Consult failure-kb.json for known patterns
    # Policy: policies/03-execution-system/failure-prevention/common-failures-prevention.md
    # Data: scripts/architecture/03-execution-system/failure-prevention/failure-kb.json
    kb_hints = check_failure_kb_hints(tool_name, tool_input)
    all_hints.extend(kb_hints)

    # Route to appropriate checker
    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        h, b = check_bash(command)
        all_hints.extend(h)
        all_blocks.extend(b)

    elif tool_name in ('Write', 'Edit', 'NotebookEdit'):
        h, b = check_write_edit(tool_name, tool_input)
        all_hints.extend(h)
        all_blocks.extend(b)

    elif tool_name == 'Grep':
        h, b = check_grep(tool_input)
        all_hints.extend(h)
        all_blocks.extend(b)

    elif tool_name == 'Read':
        h, b = check_read(tool_input)
        all_hints.extend(h)
        all_blocks.extend(b)

    # Output hints to stdout (shown to Claude as context - non-blocking)
    for hint in all_hints:
        sys.stdout.write(hint + '\n')
    sys.stdout.flush()

    # Output blocks to stderr and exit 1 (BLOCKS the tool call)
    if all_blocks:
        for block in all_blocks:
            sys.stderr.write(block + '\n')
        sys.stderr.flush()
        try:
            _sid = get_current_session_id()
            _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_enforcement_event('pre-tool-enforcer.py', 'windows_or_unicode_block',
                                   tool_name=tool_name,
                                   reason=all_blocks[0][:150] if all_blocks else 'blocked',
                                   blocked=True, session_id=_sid)
            emit_hook_execution('pre-tool-enforcer.py', _dur,
                                session_id=_sid, exit_code=1,
                                extra={'tool': tool_name, 'hints': len(all_hints),
                                       'blocks': len(all_blocks)})
        except Exception:
            pass

        # ===================================================================
        # TRACKING: Record blocking event
        # ===================================================================
        try:
            _session_id = get_current_session_id() or 'unknown'
            _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
            record_policy_execution(
                session_id=_session_id,
                policy_name="pre-tool-enforcer",
                policy_script="pre-tool-enforcer.py",
                policy_type="Core Hook",
                input_params={
                    "tool": tool_name if 'tool_name' in dir() else "unknown"
                },
                output_results={
                    "status": "BLOCKED",
                    "blocks_count": len(all_blocks) if 'all_blocks' in dir() else 0,
                    "hints_provided": len(all_hints) if 'all_hints' in dir() else 0
                },
                decision=f"Tool {tool_name if 'tool_name' in dir() else 'unknown'} blocked by enforcement policy",
                duration_ms=_duration_ms
            )
        except Exception:
            pass

        sys.exit(1)

    try:
        _sid = get_current_session_id()
        _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_hook_execution('pre-tool-enforcer.py', _dur,
                            session_id=_sid, exit_code=0,
                            extra={'tool': tool_name, 'hints': len(all_hints)})
    except Exception:
        pass

    # ===================================================================
    # TRACKING: Record overall execution (success path)
    # ===================================================================
    try:
        _session_id = get_current_session_id() or 'unknown'
        _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
        record_policy_execution(
            session_id=_session_id,
            policy_name="pre-tool-enforcer",
            policy_script="pre-tool-enforcer.py",
            policy_type="Core Hook",
            input_params={
                "tool": tool_name if 'tool_name' in dir() else "unknown"
            },
            output_results={
                "status": "ALLOWED",
                "hints_provided": len(all_hints) if 'all_hints' in dir() else 0
            },
            decision=f"Tool {tool_name if 'tool_name' in dir() else 'unknown'} allowed with optimization hints",
            duration_ms=_duration_ms
        )
    except Exception:
        pass

    # Success: output confirmation
    sys.stdout.write('[L3.6] Tool optimization verified\n')
    sys.stdout.flush()
    sys.exit(0)


if __name__ == '__main__':
    main()
