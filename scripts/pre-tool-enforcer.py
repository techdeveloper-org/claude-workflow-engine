#!/usr/bin/env python
# Script Name: pre-tool-enforcer.py
# Version: 3.2.0 (Policy-linked + failure-kb.json integration)
# Last Modified: 2026-03-03
# Description: PreToolUse hook - L3.1/3.5 blocking + L3.6 hints + L3.7 prevention
#              + L3.5+ dynamic per-file skill context switching
#              + flow-trace.json context chaining for task-aware enforcement
# v3.1.0: Reads flow-trace.json for task type, complexity, skill/agent context.
#          Provides task-aware optimization hints. Full context chain from 3-level-flow.
# v3.0.0: Dynamic per-file skill/agent selection - switches skill context per tool call
#          based on target file extension/name. Mixed-stack projects get correct skill per file.
# v2.3.0: Added window-isolation helpers for PID-specific flag isolation
# v2.2.0: Checkpoint blocking disabled - hook shows table, Claude auto-proceeds (no ok/proceed needed)
# v2.1.0: Enhanced optimization hints with consistent [OPTIMIZATION] format and clearer guidance
# Author: Claude Memory System
#
# Hook Type: PreToolUse
# Trigger: Runs BEFORE every tool call
# Exit 0 = Allow tool (may print hints to stdout)
# Exit 1 = BLOCK tool (prints reason to stderr)
#
# Policies enforced:
#   Level 3.3 - Review Checkpoint:
#     - DISABLED (v2.2.0): Hook shows checkpoint table, Claude auto-proceeds. No blocking.
#     - Flag file .checkpoint-pending-*.json is NEVER written (removed from 3-level-flow.py)
#   Level 3.1 - Task Breakdown (Loophole #7 Fix):
#     - Write/Edit/NotebookEdit: BLOCK if .task-breakdown-pending.json exists (same session+PID)
#     - Bash/Task NOT blocked: investigation and exploration allowed before TaskCreate
#     - Cleared when TaskCreate is called (post-tool-tracker.py)
#   Level 3.5 - Skill/Agent Selection (Loophole #7 Fix):
#     - Write/Edit/NotebookEdit: BLOCK if .skill-selection-pending.json exists (same session+PID)
#     - Bash/Task NOT blocked: Bash needed for git/tests, Task IS how Step 3.5 is done
#     - Cleared when Skill or Task tool is called (post-tool-tracker.py)
#   Level 3.6 - Tool Usage Optimization:
#     - Grep: warn if missing head_limit
#     - Read: warn if missing offset+limit (for large files)
#   Level 3.7 - Failure Prevention:
#     - Bash: BLOCK Windows-only commands (del, copy, dir, xcopy, etc.)
#     - Write/Edit/NotebookEdit: BLOCK Unicode chars in .py files on Windows
#
# Windows-safe: ASCII only, no Unicode chars

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
    CURRENT_SESSION_FILE = Path.home() / '.claude' / 'memory' / '.current-session.json'

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


def _load_flow_trace_context():
    """
    Load flow-trace.json from the current session to chain context from 3-level-flow.
    Returns dict with task_type, complexity, model, skill, plan_mode, user_input.
    Cached per invocation (module-level).

    This enables pre-tool-enforcer to:
    - Know what task type the session is working on
    - Provide task-aware optimization hints
    - Validate tool usage against the stated task context
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
                data = json.load(f)
            final_decision = data.get('final_decision', {})
            _flow_trace_cache = {
                'task_type': final_decision.get('task_type', ''),
                'complexity': final_decision.get('complexity', 0),
                'model': final_decision.get('model_selected', ''),
                'skill': final_decision.get('skill_or_agent', ''),
                'plan_mode': final_decision.get('plan_mode', False),
                'user_input': data.get('user_input', {}).get('prompt', '')[:200],
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
    Read the active session ID from .current-session.json.
    Returns empty string if not available (fail open - don't block on missing data).
    """
    try:
        if CURRENT_SESSION_FILE.exists():
            with open(CURRENT_SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('current_session_id', '')
    except Exception:
        pass
    return ''


def find_session_flag(pattern_prefix, current_session_id):
    """
    Find PID-isolated session-specific flag file for the current window.
    Returns (flag_path, flag_data) or (None, None) if not found.
    Also auto-cleans stale flags (>60 min) from current session.

    MULTI-WINDOW FIX: Looks for flags with matching SESSION_ID AND PID.
    Pattern: .{prefix}-{SESSION_ID}-{PID}.json

    Returns:
        (flag_path, flag_data) for current window's flag, or (None, None)
    """
    current_pid = os.getpid()
    pid_specific_pattern = '{}-{}-{}.json'.format(pattern_prefix, current_session_id, current_pid)
    pid_specific_path = FLAG_DIR / pid_specific_pattern

    if pid_specific_path.exists():
        try:
            with open(pid_specific_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Auto-expire stale flags (>60 min)
            created_at_str = data.get('created_at', '')
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age = datetime.now() - created_at
                    if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                        pid_specific_path.unlink(missing_ok=True)
                        return (None, None)
                except Exception:
                    pass

            return (pid_specific_path, data)
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
    """Level 3.7: Detect Windows-only commands that fail in bash.
    Policy: policies/03-execution-system/failure-prevention/common-failures-prevention.md
    KB: scripts/architecture/03-execution-system/failure-prevention/failure-kb.json (bash_windows_command)"""
    hints = []
    blocks = []
    cmd_stripped = command.strip()
    cmd_lower = cmd_stripped.lower()

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
    """Level 3.7: Detect Unicode chars in Python files (crash on Windows cp1252).
    Policy: policies/03-execution-system/failure-prevention/common-failures-prevention.md
    Architecture: scripts/architecture/03-execution-system/failure-prevention/windows-python-unicode-checker.py"""
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
    """Level 3.7: Check Python files for Unicode before writing."""
    hints = []
    blocks = []

    file_path = (
        tool_input.get('file_path', '') or
        tool_input.get('notebook_path', '') or
        ''
    )

    if file_path.endswith('.py'):
        content = (
            tool_input.get('content', '') or
            tool_input.get('new_string', '') or
            tool_input.get('new_source', '') or
            ''
        )
        if content:
            blocks.extend(check_python_unicode(content))

    return hints, blocks


def check_grep(tool_input):
    """Level 3.6: Grep optimization - warn about missing head_limit. Task-aware.
    Policy: policies/03-execution-system/06-tool-optimization/tool-usage-optimization-policy.md
    KB: scripts/architecture/03-execution-system/failure-prevention/failure-kb.json (grep_no_head_limit)"""
    hints = []
    head_limit = tool_input.get('head_limit', 0)

    if not head_limit:
        ctx = _load_flow_trace_context()
        complexity = ctx.get('complexity', 0)
        # Higher complexity = more likely to have large search results
        if complexity and complexity >= 10:
            hints.append(
                '[OPTIMIZATION] Grep: Add head_limit=50 (high complexity task - save context). '
                'Default CLAUDE.md rule: ALWAYS set head_limit on Grep calls.'
            )
        else:
            hints.append(
                '[OPTIMIZATION] Grep: Add head_limit=100 to prevent excessive output. '
                'Default CLAUDE.md rule: ALWAYS set head_limit on Grep calls.'
            )

    return hints, []


def check_read(tool_input):
    """Level 3.6: Read optimization - hint about offset+limit for large files. Task-aware."""
    hints = []
    limit = tool_input.get('limit')
    offset = tool_input.get('offset')

    if not limit and not offset:
        ctx = _load_flow_trace_context()
        complexity = ctx.get('complexity', 0)
        if complexity and complexity >= 10:
            hints.append(
                '[OPTIMIZATION] Read: No limit/offset set. '
                'High complexity task - use offset+limit to conserve context window.'
            )
        else:
            hints.append(
                '[OPTIMIZATION] Read: No limit/offset set. '
                'For files >500 lines, use offset+limit to save context tokens.'
            )

    return hints, []


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

# Track last printed skill to avoid spamming same hint repeatedly
_last_skill_hint = ''


def check_dynamic_skill_context(tool_name, tool_input):
    """
    Level 3.5+ Dynamic: Detect file type and inject appropriate skill/agent context.

    Runs on Read/Write/Edit/Grep/Glob - any tool that targets a specific file.
    Prints a [SKILL-CONTEXT] hint to stdout so Claude gets file-appropriate guidance.

    Does NOT block (hints only). Does NOT override session-level selection.
    Adds per-file context ON TOP of the primary skill/agent.

    Returns list of hint strings.
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

            hint = (
                '[SKILL-CONTEXT] ' + short_file + ' -> '
                + matched_skill + ' (' + type_label + ')\n'
                '  CONTEXT: ' + (matched_context or '') + '\n'
                '  ACTION: Apply ' + matched_skill + ' patterns and best practices for this file.'
            )
            hints.append(hint)

    return hints


def main():
    # CONTEXT CHAIN: Load flow-trace context from 3-level-flow (cached per invocation)
    # This gives pre-tool-enforcer awareness of task type, complexity, skill, model
    flow_ctx = _load_flow_trace_context()

    # INTEGRATION: Load tool optimization policies from scripts/architecture/
    # This runs before every tool to apply optimizations
    # L3.6: Tool Usage Optimizer (with retry - 3 attempts, 10s timeout each)
    try:
        script_dir = Path(__file__).parent
        tool_opt_script = script_dir / 'architecture' / '03-execution-system' / '06-tool-optimization' / 'tool-usage-optimizer.py'
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
        sys.exit(2)

    # DYNAMIC SKILL CONTEXT (Level 3.5+ - v3.0.0)
    # Inject per-file skill hints for any tool that targets a file
    if tool_name in ('Read', 'Write', 'Edit', 'NotebookEdit', 'Grep', 'Glob'):
        skill_hints = check_dynamic_skill_context(tool_name, tool_input)
        all_hints.extend(skill_hints)

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
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
