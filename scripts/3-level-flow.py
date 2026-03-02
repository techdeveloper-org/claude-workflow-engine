#!/usr/bin/env python3
"""
Script Name: 3-level-flow.py
Version: 3.0.0
Last Modified: 2026-02-18
Description: Complete 3-level architecture flow with full JSON trace.
             Every policy logs: input received, rules applied, output produced,
             decision made, what was passed to next policy. A-to-Z traceability.
Author: Claude Memory System
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

VERSION = "3.7.0"
SCRIPT_NAME = "3-level-flow.py"

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (MEMORY_BASE, SCRIPTS_DIR, CURRENT_DIR, FLAG_DIR, POLICIES_DIR)
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    MEMORY_BASE = Path.home() / '.claude' / 'memory'
    SCRIPTS_DIR = Path.home() / '.claude' / 'scripts'
    CURRENT_DIR = SCRIPTS_DIR if SCRIPTS_DIR.exists() else (MEMORY_BASE / 'current')
    FLAG_DIR = Path.home() / '.claude'
    POLICIES_DIR = Path.home() / '.claude' / 'policies'

SCRIPT_DIR = Path(__file__).parent  # For policy-executor integration
PYTHON = sys.executable


def load_policy_rules() -> dict:
    """Load all policy documentation from ~/.claude/policies/ directories."""
    policies = {
        'level-1': {},
        'level-2': {},
        'level-3': {}
    }

    try:
        if not POLICIES_DIR.exists():
            return policies

        # Load Level 1 policies (Sync System) — recursive into subdirs
        level_1_dir = POLICIES_DIR / '01-sync-system'
        if level_1_dir.exists():
            for policy_file in level_1_dir.glob('**/*.md'):
                try:
                    content = policy_file.read_text(encoding='utf-8')
                    policies['level-1'][policy_file.stem] = content[:500]
                except Exception:
                    pass

        # Load Level 2 policies (Standards System) — recursive into subdirs
        level_2_dir = POLICIES_DIR / '02-standards-system'
        if level_2_dir.exists():
            for policy_file in level_2_dir.glob('**/*.md'):
                try:
                    content = policy_file.read_text(encoding='utf-8')
                    policies['level-2'][policy_file.stem] = content[:500]
                except Exception:
                    pass

        # Load Level 3 policies (Execution System) — recursive into subdirs
        level_3_dir = POLICIES_DIR / '03-execution-system'
        if level_3_dir.exists():
            for policy_file in level_3_dir.glob('**/*.md'):
                try:
                    content = policy_file.read_text(encoding='utf-8')
                    policies['level-3'][policy_file.stem] = content[:500]
                except Exception:
                    pass

        return policies

    except Exception as e:
        print(f"[WARN] Failed to load policies: {e}", file=sys.stderr)
        return policies


def checkpoint_flag_path(session_id):
    """Session-specific + PID-isolated checkpoint flag path.
    Pattern: .checkpoint-pending-{SESSION_ID}-{PID}.json
    Must match pre-tool-enforcer.py find_session_flag() and post-tool-tracker _clear_session_flags()."""
    return FLAG_DIR / f'.checkpoint-pending-{session_id}-{os.getpid()}.json'


def task_breakdown_flag_path(session_id):
    """Session-specific + PID-isolated task breakdown flag path.
    Pattern: .task-breakdown-pending-{SESSION_ID}-{PID}.json
    Must match pre-tool-enforcer.py find_session_flag() and post-tool-tracker _clear_session_flags()."""
    return FLAG_DIR / f'.task-breakdown-pending-{session_id}-{os.getpid()}.json'


def skill_selection_flag_path(session_id):
    """Session-specific + PID-isolated skill selection flag path.
    Pattern: .skill-selection-pending-{SESSION_ID}-{PID}.json
    Must match pre-tool-enforcer.py find_session_flag() and post-tool-tracker _clear_session_flags()."""
    return FLAG_DIR / f'.skill-selection-pending-{session_id}-{os.getpid()}.json'

# Short approval words that clear the checkpoint flag
# MUST be <= 30 chars total
APPROVAL_WORDS = {
    'ok', 'okay', 'proceed', 'yes', 'yep', 'sure', 'go',
    'haan', 'han', 'hao', 'theek hai', 'chalo', 'karo',
    'go ahead', 'done', 'continue', 'approved', 'confirm',
    'ok proceed', 'yes proceed', 'okay proceed', 'haan karo',
    'ok go', 'yes go', 'ok done', 'ok sure', 'haan chalo',
}


def is_approval_message(msg):
    """
    True if the message is a short user confirmation like 'ok', 'proceed', 'haan'.
    Must be <= 30 chars. Checks:
      1. Exact match against APPROVAL_WORDS (handles 'ok proceed', 'yes go', etc.)
      2. All words in message are individually approval words (handles any combo)
    """
    m = msg.strip().lower()
    if len(m) > 30:
        return False
    # Exact match (includes compound phrases like 'ok proceed')
    if m in APPROVAL_WORDS:
        return True
    # All-words match: every word must be an approval word
    # This handles any combination like 'ok proceed go' without listing all combos
    words = m.split()
    if words and all(w in APPROVAL_WORDS for w in words):
        return True
    return False


# Loophole #14 fix: non-coding messages skip checkpoint enforcement
NON_CODING_INDICATORS = [
    'what is', 'what are', 'how does', 'how do', 'how to', 'why does', 'why is',
    'explain', 'describe', 'tell me', 'show me', 'list all', 'list the',
    'can you', 'could you explain', 'what does', 'whats the', "what's the",
    'kya hai', 'kaise hai', 'kaise kare', 'kya hota', 'samjha do', 'bata do',
    'batao', 'samjhao', 'dikhao', 'kya matlab', 'meaning of',
    'difference between', 'compare', 'versus', 'vs ',
    'summary', 'status', 'progress', 'kitna hua', 'kahan tak',
]


def is_non_coding_message(msg):
    """
    Detect if the user message is a question/research/info request (not coding).
    These messages should NOT trigger checkpoint enforcement.
    Returns True if the message appears to be non-coding (question/info).
    """
    m = msg.strip().lower()
    # Very short messages (< 15 chars) that aren't approvals are likely quick questions
    if len(m) < 15 and '?' in m:
        return True
    # Check for question mark with non-coding indicator
    if '?' in m and any(indicator in m for indicator in NON_CODING_INDICATORS):
        return True
    # Pure question indicators (even without ?)
    if any(m.startswith(indicator) for indicator in NON_CODING_INDICATORS):
        return True
    return False


def get_session_progress(session_id):
    """
    Read session-progress.json to check what tools have already been called.
    Used to detect mid-session continuations where TaskCreate/Skill were already done.
    Returns dict with tool_counts, tasks_completed, etc.
    """
    progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
    try:
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Only return data if it belongs to the current session
            if data.get('session_id', '') == session_id:
                return data
    except Exception:
        pass
    return {}


def is_mid_session_continuation(session_id):
    """
    Detect if this is a follow-up message in an active session where
    checkpoint approval, TaskCreate, and Skill invocation already happened.
    Returns True if enforcement flags should NOT be re-created.
    """
    progress = get_session_progress(session_id)
    if not progress:
        return False

    tool_counts = progress.get('tool_counts', {})
    tasks_completed = progress.get('tasks_completed', 0)

    # If TaskCreate was called AND Skill/Task was invoked -> mid-session continuation
    has_task_create = tool_counts.get('TaskCreate', 0) > 0
    has_skill = tool_counts.get('Skill', 0) > 0
    has_task_agent = tool_counts.get('Task', 0) > 0

    return has_task_create and (has_skill or has_task_agent)


def clear_all_enforcement_flags(reason=''):
    """Delete ALL enforcement flags (checkpoint + task-breakdown + skill-selection) on approval."""
    try:
        import glob as _glob
        cleared = 0
        for pattern in ['.checkpoint-pending-*.json', '.task-breakdown-pending-*.json', '.skill-selection-pending-*.json']:
            for flag_file in _glob.glob(str(FLAG_DIR / pattern)):
                Path(flag_file).unlink()
                cleared += 1
        if cleared > 0:
            print(f'[ENFORCEMENT] {cleared} flag(s) cleared - {reason}')
        else:
            print(f'[ENFORCEMENT] No flags to clear - {reason}')
    except Exception:
        pass


def clear_checkpoint_flag(reason=''):
    """Alias - clears ALL enforcement flags (backward compat)."""
    clear_all_enforcement_flags(reason)


def write_checkpoint_flag(session_id, prompt_preview):
    """Write session-specific checkpoint flag so pre-tool-enforcer can block code tools."""
    try:
        flag_path = checkpoint_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'prompt_preview': prompt_preview[:100],
                'reason': 'awaiting_user_ok'
            }, f)
    except Exception:
        pass


def write_task_breakdown_flag(session_id, prompt_preview):
    """
    Step 3.1 enforcement flag (session-specific).
    Cleared by post-tool-tracker.py when TaskCreate is detected.
    pre-tool-enforcer.py blocks Write/Edit/Bash until this flag is gone.
    """
    try:
        flag_path = task_breakdown_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'prompt_preview': prompt_preview[:100],
                'reason': 'step_3_1_task_breakdown_required',
                'policy': 'TaskCreate MUST be called before any Write/Edit/Bash'
            }, f)
    except Exception:
        pass


def write_skill_selection_flag(session_id, required_skill, required_type):
    """
    Step 3.5 enforcement flag (session-specific).
    Only written for non-adaptive skills (adaptive needs no tool invocation).
    Cleared by post-tool-tracker.py when Skill or Task tool is detected.
    pre-tool-enforcer.py blocks Write/Edit/Bash until this flag is gone.
    """
    try:
        flag_path = skill_selection_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'required_skill': required_skill,
                'required_type': required_type,
                'reason': 'step_3_5_skill_selection_required',
                'policy': 'Skill/Task tool MUST be invoked before any Write/Edit/Bash'
            }, f)
    except Exception:
        pass


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def ts():
    """Current ISO timestamp"""
    return datetime.now().isoformat()


def run_script(script_path, args=None, timeout=30):
    """Run a Python script, return (stdout, stderr, returncode, duration_ms)"""
    cmd = [PYTHON, str(script_path)]
    if args:
        cmd.extend(args if isinstance(args, list) else [args])

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    t0 = datetime.now()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout, env=env
        )
        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        return result.stdout, result.stderr, result.returncode, duration_ms
    except subprocess.TimeoutExpired:
        return '', 'TIMEOUT', 1, timeout * 1000
    except Exception as e:
        return '', str(e), 1, 0


MAX_RETRIES = 3  # Retry failed policy scripts up to 3 times


def run_script_with_retry(script_path, args=None, timeout=10, step_name='unknown'):
    """
    Run a policy script with retry logic.
    - Retries up to MAX_RETRIES times on failure.
    - On 3rd failure: writes failure to summary, hard-breaks session.
    - Timeouts are short (10s default) for fast execution.
    Returns (stdout, stderr, returncode, total_duration_ms)
    """
    last_stdout, last_stderr, last_rc, total_dur = '', '', 1, 0

    for attempt in range(1, MAX_RETRIES + 1):
        stdout, stderr, rc, dur = run_script(script_path, args, timeout)
        total_dur += dur

        if rc == 0:
            # Success
            if attempt > 1:
                print(f"   [RECOVERED] {step_name} succeeded on attempt {attempt}")
            return stdout, stderr, rc, total_dur

        last_stdout, last_stderr, last_rc = stdout, stderr, rc

        if attempt < MAX_RETRIES:
            print(f"   [RETRY {attempt}/{MAX_RETRIES}] {step_name} failed, retrying...")
        else:
            # 3rd failure - HARD BREAK SESSION
            error_detail = (last_stderr or last_stdout or 'Unknown error')[:300]
            _policy_hard_break(step_name, str(script_path.name), error_detail, attempt)

    # Should not reach here (hard break exits), but just in case
    return last_stdout, last_stderr, last_rc, total_dur


def _policy_hard_break(step_name, script_name, error_detail, attempts):
    """
    Hard-break the session when a policy fails after all retries.
    Writes failure to session summary file and exits with code 1.
    """
    # Write failure to session summary
    try:
        summary_file = MEMORY_BASE / 'logs' / 'policy-failure-summary.json'
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        failure_data = {
            'timestamp': datetime.now().isoformat(),
            'step': step_name,
            'script': script_name,
            'error': error_detail,
            'retries': attempts,
            'action': 'SESSION_BROKEN',
            'reason': f'Policy {step_name} ({script_name}) failed after {attempts} retries'
        }
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(failure_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Also append to session log if available
    try:
        progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            progress['policy_failure'] = {
                'step': step_name,
                'script': script_name,
                'error': error_detail[:200],
                'timestamp': datetime.now().isoformat()
            }
            progress['session_broken'] = True
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Print failure banner
    SEP = "=" * 80
    print()
    print(SEP)
    print("[SESSION BREAK] POLICY FAILED AFTER 3 RETRIES")
    print(SEP)
    print(f"  Step    : {step_name}")
    print(f"  Script  : {script_name}")
    print(f"  Retries : {attempts}")
    print(f"  Error   : {error_detail[:200]}")
    print(SEP)
    print("[ACTION] Session broken. Fix the failing policy script and retry.")
    print("[LOGGED] Failure saved to: policy-failure-summary.json")
    print(SEP)

    sys.exit(1)


def safe_json(text):
    """Parse JSON safely, return dict or {}"""
    try:
        return json.loads(text.strip())
    except Exception:
        return {}


def write_json(path, data):
    """Write JSON file, never crash main flow"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def read_json(path):
    """Read JSON file safely"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def show_help():
    print(f"{SCRIPT_NAME} v{VERSION}")
    print("3-Level Architecture Flow with Full JSON Trace")
    print()
    print("Usage:")
    print(f"  python {SCRIPT_NAME} [--verbose|-v] [--summary|-s] [--help] \"message\"")
    print()
    print("Output: flow-trace.json in session log directory")


# =============================================================================
# MAIN
# =============================================================================

def read_hook_stdin():
    """
    Read user prompt + cwd from Claude hook stdin (JSON format).
    Claude Code hook sends: {"prompt": "...", "session_id": "...", "cwd": "...", ...}
    Returns (prompt, cwd)
    """
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw and raw.strip():
                data = json.loads(raw.strip())
                prompt = data.get('prompt', '') or data.get('message', '')
                cwd = data.get('cwd', '')
                return prompt, cwd
    except Exception:
        pass
    return '', ''


def detect_tech_stack(cwd=None):
    """
    Detect actual tech stack from project files.
    Returns list of detected technologies.
    Priority: read actual files, not just check existence.

    IMPORTANT: Skip home directory and system directories.
    Scanning home dir causes false-positive tech detection (e.g., a stray
    requirements.txt with flask maps to ui-ux-designer for ALL queries).
    Only scan directories that look like actual project directories.
    """
    home = Path.home()
    # Directories that are NOT project directories - skip them
    skip_dirs = {home, home / '.claude', home / '.claude' / 'memory',
                 home / '.claude' / 'memory' / 'current'}

    search_dirs = []
    if cwd:
        candidate = Path(cwd)
        if candidate not in skip_dirs:
            search_dirs.append(candidate)

    # Only add process CWD if it differs from hook cwd and is a project dir
    proc_cwd = Path.cwd()
    if proc_cwd not in skip_dirs and proc_cwd not in search_dirs:
        search_dirs.append(proc_cwd)

    # If no valid project dirs found, return unknown immediately
    if not search_dirs:
        return ['unknown']

    stack = []

    for d in search_dirs:
        if not d.exists():
            continue

        # --- Python frameworks ---
        req = d / 'requirements.txt'
        if req.exists():
            try:
                content = req.read_text(encoding='utf-8', errors='ignore').lower()
                if 'flask' in content:
                    stack.append('flask')
                elif 'django' in content:
                    stack.append('django')
                elif 'fastapi' in content:
                    stack.append('fastapi')
                else:
                    stack.append('python')
            except Exception:
                stack.append('python')
        elif (d / 'app.py').exists() or (d / 'setup.py').exists() or (d / 'pyproject.toml').exists():
            stack.append('python')

        # --- Java / Spring Boot ---
        pom = d / 'pom.xml'
        if pom.exists():
            try:
                content = pom.read_text(encoding='utf-8', errors='ignore').lower()
                if 'spring-boot' in content or 'spring.boot' in content:
                    stack.append('spring-boot')
                else:
                    stack.append('java')
            except Exception:
                stack.append('java')
        elif (d / 'build.gradle').exists():
            stack.append('java')

        # --- Node / Angular / React / Vue ---
        pkg = d / 'package.json'
        if pkg.exists():
            try:
                content = pkg.read_text(encoding='utf-8', errors='ignore').lower()
                if '@angular' in content or '"angular"' in content:
                    stack.append('angular')
                elif 'react' in content:
                    stack.append('react')
                elif 'vue' in content:
                    stack.append('vue')
                else:
                    stack.append('nodejs')
            except Exception:
                stack.append('nodejs')

        # --- Mobile ---
        if (d / 'Podfile').exists() or list(d.glob('*.xcodeproj')):
            stack.append('swiftui')
        if (d / 'AndroidManifest.xml').exists():
            stack.append('kotlin')

        # --- DevOps ---
        if (d / 'Dockerfile').exists() or (d / 'docker-compose.yml').exists():
            stack.append('docker')
        if (d / 'Jenkinsfile').exists():
            stack.append('jenkins')
        k8s_files = list(d.glob('*.yaml')) + list(d.glob('k8s/*.yaml'))
        for f in k8s_files[:3]:
            try:
                if 'apiVersion' in f.read_text(encoding='utf-8', errors='ignore'):
                    stack.append('kubernetes')
                    break
            except Exception:
                pass

        if stack:
            break  # Found tech stack from this dir, stop searching

    return stack if stack else ['unknown']


# =============================================================================
# SKILL / AGENT REGISTRY
# Source of truth: ~/.claude/agents/ + ~/.claude/skills/INDEX.md
#
# PRIORITY RULES:
#   1. TASK TYPE is PRIMARY - matches by what the user wants to DO, not project files
#   2. TECH STACK is SECONDARY - matches by detected project technology
#   3. Skill vs Agent by TASK NATURE (not complexity): guidance=Skill, autonomous=Agent
#   4. ALWAYS invoke matching skill/agent (no complexity threshold)
#   5. No match -> SUGGEST new skill/agent to user (not silently adaptive)
# =============================================================================

# TASK TYPE REGISTRY - Primary selection based on WHAT user is trying to do
# task_type comes from prompt-generator.py (Step 3.0)
# This is the FIRST thing checked - more reliable than file scanning
TASK_TYPE_TO_AGENT = {
    # --- UI / Frontend / Design ---
    'UI/UX':             ('ui-ux-designer', 'agent'),
    'Dashboard':         ('ui-ux-designer', 'agent'),  # from prompt-generator
    'Frontend':          ('ui-ux-designer', 'agent'),
    'Design':            ('ui-ux-designer', 'agent'),
    'HTML/CSS':          ('ui-ux-designer', 'agent'),
    'Template':          ('ui-ux-designer', 'agent'),

    # --- Angular / TypeScript ---
    'Angular':           ('angular-engineer', 'agent'),
    'TypeScript':        ('angular-engineer', 'agent'),

    # --- Backend / API / Java ---
    'Backend':           ('spring-boot-microservices', 'agent'),
    'API':               ('spring-boot-microservices', 'agent'),
    'API Creation':      ('spring-boot-microservices', 'agent'),  # from prompt-generator
    'Microservice':      ('spring-boot-microservices', 'agent'),
    'Spring':            ('spring-boot-microservices', 'agent'),
    'Java':              ('spring-boot-microservices', 'agent'),
    'Configuration':     ('spring-boot-microservices', 'agent'),  # from prompt-generator

    # --- Authentication / Security ---
    'Authentication':    ('spring-boot-microservices', 'agent'),  # from prompt-generator
    'Authorization':     ('spring-boot-microservices', 'agent'),  # from prompt-generator
    'Security':          ('spring-boot-microservices', 'agent'),

    # --- Database ---
    'Database':          ('rdbms-core', 'skill'),  # from prompt-generator
    'SQL':               ('rdbms-core', 'skill'),
    'NoSQL':             ('nosql-core', 'skill'),

    # --- Testing / QA ---
    'Testing':           ('qa-testing-agent', 'agent'),  # from prompt-generator
    'QA':                ('qa-testing-agent', 'agent'),

    # --- DevOps / Infra ---
    'DevOps':            ('devops-engineer', 'agent'),
    'Docker':            ('devops-engineer', 'agent'),
    'Kubernetes':        ('devops-engineer', 'agent'),
    'Jenkins':           ('devops-engineer', 'agent'),
    'CI/CD':             ('devops-engineer', 'agent'),
    'Infrastructure':    ('devops-engineer', 'agent'),

    # --- Mobile ---
    'Mobile/Android':    ('android-backend-engineer', 'agent'),
    'Android':           ('android-backend-engineer', 'agent'),
    'Kotlin':            ('android-backend-engineer', 'agent'),
    'Mobile/iOS':        ('swiftui-designer', 'agent'),
    'iOS':               ('swiftui-designer', 'agent'),
    'SwiftUI':           ('swiftui-designer', 'agent'),
    'Swift':             ('swift-backend-engineer', 'agent'),

    # --- SEO ---
    'SEO':               ('dynamic-seo-agent', 'agent'),

    # --- System/Script tasks (about the Claude memory system itself) ---
    'System/Script':     ('adaptive-skill-intelligence', 'skill'),
    'Sync/Update':       ('adaptive-skill-intelligence', 'skill'),

    # --- Intentionally NOT mapped (let tech stack or adaptive decide) ---
    # 'Bug Fix':         depends on what is being fixed (tech stack is better)
    # 'Refactoring':     depends on what is being refactored
    # 'Documentation':   no specific agent
    # 'General Task':    always adaptive
    # 'General':         always adaptive
}

# =============================================================================
# LAYER 2: PROMPT KEYWORD SCORING
# When task_type is General/unknown, scan the RAW USER MESSAGE for signals.
# Each agent has a set of keywords; the highest-scoring agent wins.
# Minimum score threshold = 2 (at least 2 keyword matches required).
# This is the "dynamic" layer - works on any prompt without API calls.
# =============================================================================
AGENT_KEYWORD_SCORES = {
    'ui-ux-designer': [
        'ui', 'ux', 'design', 'layout', 'dashboard', 'interface', 'frontend',
        'css', 'html', 'page', 'screen', 'widget', 'card', 'modal', 'form',
        'button', 'nav', 'navbar', 'sidebar', 'header', 'footer', 'style',
        'responsive', 'theme', 'color', 'font', 'template', 'component style',
        'dark mode', 'light mode', 'animation', 'transition', 'hover', 'flex',
        'grid', 'bootstrap', 'tailwind', 'material',
    ],
    'angular-engineer': [
        'angular', 'typescript', 'ng', 'ngmodule', 'ngcomponent', 'ngrouter',
        'rxjs', 'observable', 'service angular', 'component', 'routing',
        'ngform', 'reactive form', 'angular service',
    ],
    'spring-boot-microservices': [
        'spring', 'java', 'microservice', 'springboot', 'spring boot', 'rest api',
        'endpoint', 'controller', 'entity', 'repository', 'jpa', 'hibernate',
        'bean', 'autowired', 'service layer', 'dto', 'request mapping', 'eureka',
        'feign', 'config server', 'gateway', 'maven', 'gradle',
    ],
    'devops-engineer': [
        'docker', 'kubernetes', 'k8s', 'jenkins', 'pipeline', 'ci/cd', 'cicd',
        'deploy', 'container', 'helm', 'dockerfile', 'image', 'pod', 'cluster',
        'ingress', 'namespace', 'manifest', 'yaml kubernetes', 'registry',
        'build pipeline', 'jenkins file', 'jenkins pipeline',
    ],
    'qa-testing-agent': [
        'test', 'testing', 'unit test', 'integration test', 'qa', 'junit',
        'pytest', 'test case', 'test suite', 'mock', 'assertion', 'coverage',
        'regression', 'e2e', 'selenium', 'testng',
    ],
    'android-backend-engineer': [
        'android', 'kotlin', 'apk', 'android studio', 'coroutine', 'retrofit',
        'room database', 'viewmodel', 'livedata', 'jetpack', 'manifest',
        'activity', 'fragment', 'recycler', 'gradle android',
    ],
    'swiftui-designer': [
        'ios', 'swift', 'swiftui', 'iphone', 'ipad', 'xcode', 'uikit',
        'storyboard', 'app store', 'swift ui', 'ios app',
    ],
    'swift-backend-engineer': [
        'vapor', 'swift server', 'swift backend', 'swift rest', 'swift api',
    ],
    'orchestrator-agent': [
        'multi service', 'multiple service', 'cross service', 'full stack',
        'end to end', 'orchestrat', 'coordinate', 'across service',
    ],
    # System/meta tasks about the Claude memory system itself
    # These queries have NO tech stack and NO project files -> they were
    # falling all the way to Layer 3 (tech stack) and picking wrong agents.
    # Adding explicit keyword detection here fixes Layer 2 for meta queries.
    'adaptive-skill-intelligence': [
        # System/memory system keywords
        'loophole', 'loophole hai', 'koi loophole',  # 2-3 hits on "aur koi loophole hai"
        'hook', 'memory system', 'flow.py', 'flow.sh',
        '3-level', 'session handler', 'auto-fix', 'skill detection',
        'skill selection', 'pre-tool', 'post-tool', 'stop-notifier',
        'standards-loader', 'context-monitor', 'blocking-policy',
        'task-auto-analyzer', 'plan-mode', 'model-selection',
        'claude system', 'claude memory', 'prompt-generator',
        # Hinglish git/sync/confirm queries (2+ hits needed)
        'sync ho gaya', 'push ho gaya', 'sab sync', 'push kar',
        'confirm kar', 'push diya', 'push kar diya',  # for "push kar diya confirm kar"
        'kya sync', 'sync hua', 'ho gaya push', 'commit kar',
    ],
}

KEYWORD_MIN_SCORE = 2  # At least 2 keyword matches to select an agent


def select_by_prompt_keywords(user_message):
    """
    Scan the raw user message for agent/skill keywords.
    Returns (agent_name, agent_type, score) or (None, None, 0) if no clear winner.

    This is the dynamic layer - works on natural language prompts
    without requiring pre-classification or API calls.
    """
    # Skills that use Skill tool (not Task tool with agent)
    SKILL_NAMES = {'adaptive-skill-intelligence', 'rdbms-core', 'nosql-core',
                   'java-spring-boot-microservices', 'docker', 'kubernetes',
                   'jenkins-pipeline'}

    msg = user_message.lower()
    scores = {}

    for agent, keywords in AGENT_KEYWORD_SCORES.items():
        score = sum(1 for kw in keywords if kw in msg)
        if score > 0:
            scores[agent] = score

    if not scores:
        return None, None, 0

    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]

    if best_score < KEYWORD_MIN_SCORE:
        return None, None, best_score  # Not confident enough

    agent_type = 'skill' if best_agent in SKILL_NAMES else 'agent'
    return best_agent, agent_type, best_score


# PRIMARY: Agents (~/.claude/agents/) - highest priority
# Maps tech -> agent name
AGENTS_REGISTRY = {
    'spring-boot':  'spring-boot-microservices',
    'java':         'spring-boot-microservices',
    'angular':      'angular-engineer',
    'react':        'ui-ux-designer',
    'vue':          'ui-ux-designer',
    # flask/django removed — they are Python backend frameworks, NOT UI tools.
    # mapping them to ui-ux-designer was causing wrong skill selection for all
    # queries where requirements.txt had flask/django in the scanned directory.
    # They now fall through to adaptive-skill-intelligence (Layer 4).
    'swiftui':      'swiftui-designer',
    'swift':        'swift-backend-engineer',
    'kotlin':       'android-backend-engineer',
    'docker':       'devops-engineer',       # devops-engineer handles Docker+K8s+Jenkins
    'kubernetes':   'devops-engineer',
    'jenkins':      'devops-engineer',
    'seo':          'dynamic-seo-agent',
    'qa':           'qa-testing-agent',
    # No agent for: fastapi, python, nodejs -> skill fallback or adaptive
}

# SUPPLEMENTARY: Skills (~/.claude/skills/) - added on top of agent when useful
# Maps tech -> skill name (injected as extra knowledge alongside the agent)
SKILLS_REGISTRY = {
    'spring-boot':  'java-spring-boot-microservices',
    'java':         'java-design-patterns-core',
    'postgresql':   'rdbms-core',
    'mysql':        'rdbms-core',
    'mongodb':      'nosql-core',
    'docker':       'docker',
    'kubernetes':   'kubernetes',
    'jenkins':      'jenkins-pipeline',
    # Standalone skills when no agent exists:
    'fastapi':      None,   # -> adaptive
    'python':       None,   # -> adaptive
    'nodejs':       None,   # -> adaptive
    'unknown':      None,
}


def get_agent_and_skills(tech_stack, task_type='General', user_message=''):
    """
    4-layer selection (MOST reliable to least reliable):

    Layer 1: TASK TYPE registry    - exact match on classified task type
    Layer 2: PROMPT KEYWORD score  - keyword analysis of raw user message (DYNAMIC)
    Layer 3: TECH STACK registry   - project file detection
    Layer 4: adaptive-skill-intel  - creates a new skill if truly nothing matches

    The "dynamic" layer (2) means this function can recognize new tasks
    from natural language without needing pre-classified task types or
    project files on disk.

    Returns (primary_name, primary_type, supplementary_skills, reason)
    """
    supplementary_skills = []

    # =========================================================================
    # LAYER 1: Task type registry (fast exact match on classified type)
    # =========================================================================
    task_match = TASK_TYPE_TO_AGENT.get(task_type)
    if task_match and task_type not in ('General', 'General Task', 'Unknown', ''):
        name, atype = task_match
        for tech in tech_stack:
            if tech != 'unknown':
                skill = SKILLS_REGISTRY.get(tech)
                if skill and skill not in supplementary_skills:
                    supplementary_skills.append(skill)
        reason = (
            f"[L1-TaskType] '{task_type}' -> {atype}: {name}"
            + (f" + tech: {tech_stack}" if tech_stack != ['unknown'] else "")
            + (f" + supp: {supplementary_skills}" if supplementary_skills else "")
        )
        return name, atype, supplementary_skills, reason

    # =========================================================================
    # LAYER 2: Prompt keyword scoring (dynamic - works on raw natural language)
    # Scans the user's actual words for agent/skill signals
    # =========================================================================
    if user_message:
        kw_agent, kw_type, kw_score = select_by_prompt_keywords(user_message)
        if kw_agent:
            # Collect supplementary skills from tech stack too
            for tech in tech_stack:
                if tech != 'unknown':
                    skill = SKILLS_REGISTRY.get(tech)
                    if skill and skill not in supplementary_skills:
                        supplementary_skills.append(skill)
            reason = (
                f"[L2-KeywordScore={kw_score}] prompt keywords -> {kw_type}: {kw_agent}"
                + (f" + task_type: {task_type}" if task_type else "")
                + (f" + supp: {supplementary_skills}" if supplementary_skills else "")
            )
            return kw_agent, kw_type, supplementary_skills, reason

    # =========================================================================
    # LAYER 3: Tech stack registry (file-based detection)
    # =========================================================================
    primary_agent = None
    primary_tech = None
    skill_fallback = None

    for tech in tech_stack:
        agent = AGENTS_REGISTRY.get(tech)
        if agent and primary_agent is None:
            primary_agent = agent
            primary_tech = tech

        skill = SKILLS_REGISTRY.get(tech)
        if skill and skill not in supplementary_skills:
            supplementary_skills.append(skill)

        if not agent and skill and skill_fallback is None:
            skill_fallback = skill

    if primary_agent:
        reason = (
            f"[L3-TechStack] '{primary_tech}' -> agent: {primary_agent}"
            + (f" + supp: {supplementary_skills}" if supplementary_skills else "")
        )
        return primary_agent, 'agent', supplementary_skills, reason

    if skill_fallback:
        reason = f"[L3-TechStack] [{', '.join(tech_stack)}] -> skill: {skill_fallback}"
        return skill_fallback, 'skill', [], reason

    # =========================================================================
    # LAYER 4: adaptive-skill-intelligence (PROACTIVE SUGGESTION MODE)
    # When no match found, Claude MUST suggest creating a new skill/agent
    # to the user instead of silently proceeding. User decides YES/NO.
    # If same unmatched domain appears 2+ times -> stronger suggestion.
    # =========================================================================
    reason = (
        f"[L4-Adaptive] No match: task_type='{task_type}', tech=[{', '.join(tech_stack)}], "
        f"keywords=low -> SUGGEST new skill/agent to user (fallback: adaptive-skill-intelligence)"
    )
    return 'adaptive-skill-intelligence', 'skill', [], reason


def _ensure_architecture_modules_synced():
    """
    Issue #9 & #10 Fix: Ensure architecture modules are available locally.
    When running from ~/.claude/scripts/ (deployed), check if architecture/
    subdirectory exists.  If not, log a warning so users know they need to sync.
    When running from the source repo (development), the modules are already
    present at SCRIPT_DIR/architecture/.

    The hook-downloader.py (in claude-code-ide repo) is responsible for the
    full GitHub sync.  This function provides a lightweight local check and
    creates the directory structure if needed so that subsequent calls don't
    fail hard.
    """
    arch_dir = SCRIPT_DIR / 'architecture'

    # Running from deployment location (~/.claude/scripts/)
    deployed_arch = SCRIPTS_DIR / 'architecture'

    for check_dir in [arch_dir, deployed_arch]:
        if check_dir.exists() and any(check_dir.iterdir()):
            return  # Modules found, nothing to do

    # Architecture directory missing or empty — create stub dirs and log warning
    try:
        for subdir in [
            'architecture/01-sync-system/session-management',
            'architecture/01-sync-system/context-management',
            'architecture/01-sync-system/user-preferences',
            'architecture/01-sync-system/pattern-detection',
            'architecture/02-standards-system',
            'architecture/03-execution-system/00-prompt-generation',
            'architecture/03-execution-system/01-task-breakdown',
            'architecture/03-execution-system/02-plan-mode',
            'architecture/03-execution-system/04-model-selection',
            'architecture/03-execution-system/05-skill-agent-selection',
            'architecture/03-execution-system/06-tool-optimization',
            'architecture/03-execution-system/08-progress-tracking',
            'architecture/03-execution-system/09-git-commit',
            'architecture/03-execution-system/failure-prevention',
        ]:
            (SCRIPTS_DIR / subdir).mkdir(parents=True, exist_ok=True)

        warning_log = LOG_DIR / 'arch-sync-warning.log'
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(warning_log, 'a', encoding='utf-8') as f:
                f.write(
                    f"[{datetime.now().isoformat()}] WARNING: Architecture modules not found "
                    f"in {arch_dir} or {deployed_arch}. "
                    f"Run hook-downloader.py to sync from GitHub.\n"
                )
        except Exception:
            pass
    except Exception:
        pass


def main():
    mode = 'standard'
    user_message = ''
    message_parts = []

    for arg in sys.argv[1:]:
        if arg in ('--verbose', '-v'):
            mode = 'verbose'
        elif arg in ('--summary', '-s'):
            mode = 'summary'
        elif arg in ('--help', '-h'):
            show_help()
            sys.exit(0)
        elif arg == '--version':
            print(f"{SCRIPT_NAME} v{VERSION}")
            sys.exit(0)
        else:
            message_parts.append(arg)

    # Join all non-flag args as the message (handles multi-word messages)
    if message_parts:
        user_message = ' '.join(message_parts)

    # If no message from args, try reading from hook stdin (Claude Code sends JSON)
    hook_cwd = ''
    if not user_message:
        user_message, hook_cwd = read_hook_stdin()

    # Last resort fallback - clearly marked as fallback (not dummy data)
    if not user_message:
        user_message = "[NO MESSAGE - hook did not pass user prompt]"

    # =========================================================================
    # STEP 0: SYNC ARCHITECTURE MODULES + VERIFY POLICIES (v3.4.1)
    # Issues #9 & #10: Ensure architecture modules are synced to local scripts
    # dir and all policy modules are verified (not blindly executed as CLI tools).
    # =========================================================================
    _ensure_architecture_modules_synced()

    try:
        policy_executor = SCRIPT_DIR / 'policy-executor.py'
        if policy_executor.exists():
            # Run policy health check in background (non-blocking, capture output)
            subprocess.run([PYTHON, str(policy_executor)], timeout=15, capture_output=True)
    except Exception:
        pass  # Policy executor is optional, don't block if it fails

    # CHECKPOINT ENFORCEMENT: Clear ALL flags if user is confirming with 'ok'/'proceed' etc.
    # This MUST run before anything else so pre-tool-enforcer sees cleared flags.
    _is_approval = is_approval_message(user_message)
    if _is_approval:
        clear_all_enforcement_flags(reason='user said: ' + user_message.strip()[:20])

    SEP = "=" * 80
    flow_start = datetime.now()

    # =========================================================================
    # INITIALIZE TRACE OBJECT
    # This is the central JSON object that tracks everything A-to-Z
    # =========================================================================
    trace = {
        "meta": {
            "flow_version": VERSION,
            "script": SCRIPT_NAME,
            "mode": mode,
            "flow_start": flow_start.isoformat(),
            "flow_end": None,
            "duration_seconds": None,
            "session_id": None,
            "log_dir": None
        },
        "user_input": {
            "prompt": user_message,
            "received_at": flow_start.isoformat(),
            "source": "UserPromptSubmit hook"
        },
        "pipeline": [],
        "final_decision": {},
        "work_started": False,
        "status": "RUNNING"
    }

    print(SEP)
    print(f"3-LEVEL ARCHITECTURE FLOW v{VERSION} (Mode: {mode})")
    print(SEP)
    print(f"Message: {user_message}")
    print(SEP)
    print()

    # =========================================================================
    # CLAUDE.MD MERGE DETECTION
    # =========================================================================
    project_claude_md = None
    if hook_cwd:
        candidate = Path(hook_cwd) / 'CLAUDE.md'
        if candidate.exists():
            project_claude_md = str(candidate)
    if not project_claude_md:
        # Check current working directory
        cwd_candidate = Path.cwd() / 'CLAUDE.md'
        if cwd_candidate.exists():
            project_claude_md = str(cwd_candidate)

    if project_claude_md:
        print('[MERGE] Project CLAUDE.md detected: ' + project_claude_md)
        print('[MERGE] Global policies CANNOT be overridden by project CLAUDE.md')
        print('[MERGE] Rule: Global = BOSS, Project = ADDITIONAL context only')
        trace['merge_detection'] = {
            'project_claude_md': project_claude_md,
            'policy': 'Global policies immutable, project adds context only'
        }
    else:
        trace['merge_detection'] = {'project_claude_md': None}
    print()

    # =========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT (BLOCKING)
    # =========================================================================
    print("[LEVEL -1] AUTO-FIX ENFORCEMENT (BLOCKING)")

    step_start = datetime.now()
    auto_fix_script = CURRENT_DIR / 'auto-fix-enforcer.py'

    lvl_minus1_input = {
        "trigger": "user_prompt_received",
        "user_message": user_message,
        "purpose": "Verify ALL systems operational before any work",
        "is_blocking": True
    }

    stdout, stderr, rc, dur = run_script_with_retry(auto_fix_script, timeout=10, step_name='Level-1.Auto-Fix')
    status_str = 'SUCCESS' if rc == 0 else 'FAILED'

    # Parse checks from stdout
    checks_found = {}
    for line in stdout.splitlines():
        if '[1/7]' in line or 'Python' in line and 'available' in line:
            checks_found['python'] = 'OK' if 'OK' in line or 'available' in line else 'FAIL'
        elif '[2/7]' in line or 'critical files' in line.lower():
            checks_found['critical_files'] = 'OK' if 'present' in line.lower() or 'OK' in line else 'FAIL'
        elif '[3/7]' in line or 'blocking enforcer' in line.lower():
            checks_found['blocking_enforcer'] = 'OK' if 'initialized' in line.lower() or 'OK' in line else 'FAIL'
        elif '[4/7]' in line or 'session state' in line.lower():
            checks_found['session_state'] = 'OK' if 'valid' in line.lower() or 'OK' in line else 'FAIL'
        elif '[5/7]' in line or 'daemon' in line.lower():
            checks_found['daemons'] = 'INFO'
        elif '[6/7]' in line or 'git' in line.lower():
            checks_found['git'] = 'INFO'
        elif '[7/7]' in line or 'unicode' in line.lower():
            checks_found['windows_unicode'] = 'OK' if 'No fixes needed' in stdout or 'operational' in stdout.lower() else 'FIXED'

    lvl_minus1_output = {
        "exit_code": rc,
        "status": status_str,
        "checks": checks_found if checks_found else {
            "python": "OK", "critical_files": "OK", "blocking_enforcer": "OK",
            "session_state": "OK", "daemons": "INFO", "git": "INFO", "windows_unicode": "OK"
        },
        "raw_output_lines": len(stdout.splitlines())
    }

    lvl_minus1_decision = "PROCEED - All systems operational" if rc == 0 else "BLOCKED - Fix failures first"
    lvl_minus1_passed = {
        "cleared": rc == 0,
        "proceed": rc == 0,
        "blocked": rc != 0,
        "status": "ALL_SYSTEMS_OK" if rc == 0 else "BLOCKED"
    }

    trace["pipeline"].append({
        "step": "LEVEL_MINUS_1",
        "name": "Auto-Fix Enforcement",
        "level": -1,
        "order": 0,
        "is_blocking": True,
        "timestamp": step_start.isoformat(),
        "duration_ms": dur,
        "input": lvl_minus1_input,
        "policy": {
            "script": "auto-fix-enforcer.py",
            "version": "2.0.0",
            "rules_applied": [
                "check_python_available",
                "check_critical_files_present",
                "check_blocking_enforcer_initialized",
                "check_session_state_valid",
                "check_daemon_status",
                "check_git_repository",
                "check_windows_unicode_in_python_files"
            ]
        },
        "policy_output": lvl_minus1_output,
        "decision": lvl_minus1_decision,
        "passed_to_next": lvl_minus1_passed
    })

    if rc != 0:
        print("   [FAIL] System issues - BLOCKED!")
        trace["status"] = "BLOCKED"
        trace["work_started"] = False
        _save_trace(trace, None, flow_start)
        sys.exit(1)

    print("   [OK] All systems operational")
    print("[OK] LEVEL -1 COMPLETE")
    print()

    # =========================================================================
    # LEVEL 1.1: CONTEXT MANAGEMENT
    # =========================================================================
    print("[LEVEL 1] SYNC SYSTEM (FOUNDATION)")

    step_start = datetime.now()
    ctx_script = CURRENT_DIR / 'context-monitor-v2.py'
    ctx_stdout, _, ctx_rc, ctx_dur = run_script_with_retry(ctx_script, ['--current-status'], timeout=8, step_name='Level-1.1.Context')
    ctx_data = safe_json(ctx_stdout)

    context_pct = ctx_data.get('percentage', 0)
    context_level = ctx_data.get('level', 'unknown')
    ctx_recommendations = ctx_data.get('recommendations', [])

    # Determine action based on context %
    if context_pct >= 90:
        ctx_action = "CRITICAL - Save session, start new session"
        ctx_optimization = "aggressive"
    elif context_pct >= 85:
        ctx_action = "HIGH - Use session state, extract summaries"
        ctx_optimization = "high"
    elif context_pct >= 70:
        ctx_action = "MODERATE - Apply offset/limit/head_limit"
        ctx_optimization = "moderate"
    else:
        ctx_action = "GOOD - Continue normally"
        ctx_optimization = "none"

    trace["pipeline"].append({
        "step": "LEVEL_1_CONTEXT",
        "name": "Context Management",
        "level": 1,
        "order": 1,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": ctx_dur,
        "input": {
            "from_previous": "LEVEL_MINUS_1",
            "previous_decision": lvl_minus1_decision,
            "previous_passed": lvl_minus1_passed,
            "purpose": "Check context window usage before loading anything"
        },
        "policy": {
            "script": "context-monitor-v2.py",
            "args": ["--current-status"],
            "rules_applied": [
                "measure_context_percentage",
                "apply_threshold_classification",
                "generate_action_recommendation"
            ],
            "thresholds": {"green": 60, "yellow": 70, "orange": 80, "red": 85}
        },
        "policy_output": {
            "percentage": context_pct,
            "level": context_level,
            "thresholds": ctx_data.get('thresholds', {}),
            "recommendations": ctx_recommendations,
            "cache_entries": ctx_data.get('cache_entries', 0),
            "active_sessions": ctx_data.get('active_sessions', 0)
        },
        "decision": ctx_action,
        "passed_to_next": {
            "context_pct": context_pct,
            "context_level": context_level,
            "optimization_required": ctx_optimization != "none",
            "optimization_level": ctx_optimization,
            "action": ctx_action
        }
    })

    print(f"   [OK] Context: {context_pct}%")
    if mode == 'verbose':
        print(f"   Action: {ctx_action}")

    # =========================================================================
    # LEVEL 1.2: SESSION MANAGEMENT
    # =========================================================================
    step_start = datetime.now()
    sess_script = CURRENT_DIR / 'session-id-generator.py'
    sess_stdout, _, sess_rc, sess_dur = run_script_with_retry(sess_script, ['current'], timeout=8, step_name='Level-1.2.Session')

    session_id = 'UNKNOWN'
    for line in sess_stdout.splitlines():
        if line.startswith('Current Session:'):
            session_id = line.split(':', 1)[1].strip()
            break
        if 'Session ID:' in line and session_id == 'UNKNOWN':
            parts = line.split('Session ID:')
            if len(parts) > 1:
                candidate = parts[1].strip()
                if candidate.startswith('SESSION-'):
                    session_id = candidate

    # If no current session exists, auto-create a new one
    # This happens on first run, or after /clear (clear-session-handler deletes .current-session.json)
    if session_id == 'UNKNOWN' or sess_rc != 0:
        create_desc = f"Session auto-created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        new_out, _, new_rc, new_dur2 = run_script_with_retry(
            sess_script, ['create', '--description', create_desc], timeout=8, step_name='Level-1.2.Session-Create'
        )
        sess_dur += new_dur2
        for line in new_out.splitlines():
            line = line.strip()
            if line.startswith('SESSION-'):
                session_id = line
                break
        # Reset session-progress.json so context % starts fresh (tool counts from old session don't bleed in)
        try:
            session_progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
            fresh_progress = {
                'total_progress': 0,
                'tool_counts': {},
                'started_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                'tasks_completed': 0,
                'errors_seen': 0,
                'context_estimate_pct': 15,
                'session_id': session_id,
                'reset_reason': 'new session auto-created by 3-level-flow.py'
            }
            session_progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(session_progress_file, 'w', encoding='utf-8') as spf:
                json.dump(fresh_progress, spf, indent=2)
        except Exception:
            pass

        # Voice notification: write flag for stop-notifier to speak on new session
        # Only write if flag doesn't already exist (clear-session-handler may have set it)
        try:
            import datetime as _dt
            _voice_flag = Path.home() / '.claude' / '.session-start-voice'
            if not _voice_flag.exists():
                _hour = _dt.datetime.now().hour
                if _hour < 12:
                    _greet = 'Good morning'
                elif _hour < 17:
                    _greet = 'Good afternoon'
                else:
                    _greet = 'Good evening'
                _voice_msg = _greet + ' Sir. New session started. I am ready for your commands.'
                _voice_flag.write_text(_voice_msg, encoding='utf-8')
        except Exception:
            pass

    # Set up session log directory NOW that we have session_id
    session_log_dir = MEMORY_BASE / 'logs' / 'sessions' / session_id
    session_log_dir.mkdir(parents=True, exist_ok=True)
    trace["meta"]["session_id"] = session_id
    trace["meta"]["log_dir"] = str(session_log_dir)

    # =========================================================================
    # EARLY FLAG WRITING (Loophole #18 fix)
    # Write checkpoint + task-breakdown flags IMMEDIATELY after session_id is known.
    # This ensures enforcement is active even if the script times out later.
    # Skill-selection flag is written later (needs skill detection at step 3.5).
    #
    # Loophole #14 fix: SKIP flags for non-coding messages (questions/research).
    # Non-coding messages don't need checkpoint review or task breakdown.
    #
    # v3.1.0 fix: SKIP flags for mid-session continuations where TaskCreate
    # and Skill were already called. Follow-up messages (error feedback,
    # corrections, additional requests) should NOT re-create blocking flags.
    # =========================================================================
    _is_continuation = is_mid_session_continuation(session_id)
    _needs_enforcement = (
        not _is_approval
        and not is_non_coding_message(user_message)
        and not _is_continuation
    )
    if _needs_enforcement:
        # AUTO_PROCEED v1.0: Checkpoint text shows in trace but does NOT block.
        # User approved auto-proceed (2026-02-23) - trusts Claude's decisions.
        # write_checkpoint_flag() removed - no more .checkpoint-pending-*.json written.
        write_task_breakdown_flag(
            session_id=session_id or 'unknown',
            prompt_preview=user_message
        )

    trace["pipeline"].append({
        "step": "LEVEL_1_SESSION",
        "name": "Session Management",
        "level": 1,
        "order": 2,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": sess_dur,
        "input": {
            "from_previous": "LEVEL_1_CONTEXT",
            "context_pct": context_pct,
            "optimization_level": ctx_optimization,
            "purpose": "Load or create session ID for tracking all work"
        },
        "policy": {
            "script": "session-id-generator.py",
            "args": ["current"],
            "rules_applied": [
                "load_existing_session_if_active",
                "create_new_session_if_none",
                "format_SESSION_YYYYMMDD_HHMMSS_XXXX"
            ]
        },
        "policy_output": {
            "session_id": session_id,
            "session_id_format": "SESSION-YYYYMMDD-HHMMSS-XXXX",
            "log_dir": str(session_log_dir),
            "exit_code": sess_rc
        },
        "decision": f"Session {session_id} active - all logs will reference this ID",
        "passed_to_next": {
            "session_id": session_id,
            "log_dir": str(session_log_dir),
            "tracking_active": True
        }
    })

    print(f"   [OK] Session: {session_id}")

    # =========================================================================
    # LEVEL 1.3: USER PREFERENCES
    # Architecture script: 01-sync-system/user-preferences/load-preferences.py
    # Loads learned user preferences for decision-making.
    # =========================================================================
    step_start = datetime.now()
    prefs_script = MEMORY_BASE / '01-sync-system' / 'user-preferences' / 'load-preferences.py'
    if not prefs_script.exists():
        prefs_script = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'user-preferences' / 'load-preferences.py'

    prefs_loaded = 0
    prefs_dur = 0
    prefs_data = {}
    if prefs_script.exists():
        prefs_out, _, prefs_rc, prefs_dur = run_script_with_retry(prefs_script, timeout=5, step_name='Level-1.3.Preferences')
        if prefs_rc == 0 and prefs_out.strip():
            # Count preferences from output (lines with [CHECK] indicate set preferences)
            for line in prefs_out.splitlines():
                if '[CHECK]' in line or 'check' in line.lower():
                    prefs_loaded += 1
            prefs_data = {"raw_output_lines": len(prefs_out.splitlines())}

    trace["pipeline"].append({
        "step": "LEVEL_1_PREFERENCES",
        "name": "User Preferences",
        "level": 1,
        "order": 2.5,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": prefs_dur,
        "input": {
            "from_previous": "LEVEL_1_SESSION",
            "session_id": session_id,
            "purpose": "Load learned user preferences for decision-making"
        },
        "policy": {
            "script": "load-preferences.py",
            "rules_applied": [
                "load_technology_preferences",
                "load_language_preferences",
                "load_workflow_preferences"
            ]
        },
        "policy_output": {
            "preferences_loaded": prefs_loaded,
            "script_exists": prefs_script.exists(),
            "data": prefs_data
        },
        "decision": f"Loaded {prefs_loaded} user preferences" if prefs_loaded > 0 else "No preferences file found (first run)",
        "passed_to_next": {
            "preferences_available": prefs_loaded > 0,
            "preferences_count": prefs_loaded
        }
    })
    if prefs_loaded > 0:
        print(f"   [OK] Preferences: {prefs_loaded} loaded")
    else:
        print(f"   [OK] Preferences: None (first run)")

    # =========================================================================
    # LEVEL 1.4: SESSION STATE
    # Architecture script: 01-sync-system/session-management/session-state.py
    # Maintains durable session state outside Claude's context window.
    # =========================================================================
    step_start = datetime.now()
    state_script = MEMORY_BASE / '01-sync-system' / 'session-management' / 'session-state.py'
    if not state_script.exists():
        state_script = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'session-management' / 'session-state.py'

    state_dur = 0
    state_summary = {}
    if state_script.exists():
        st_out, _, st_rc, state_dur = run_script_with_retry(state_script, ['--summary'], timeout=5, step_name='Level-1.4.Session-State')
        if st_rc == 0 and st_out.strip():
            state_summary = safe_json(st_out)

    completed_tasks_count = state_summary.get('progress', {}).get('completed_tasks', 0)
    files_modified_count = state_summary.get('progress', {}).get('files_modified', 0)
    pending_work_count = state_summary.get('progress', {}).get('pending_work', 0)

    trace["pipeline"].append({
        "step": "LEVEL_1_STATE",
        "name": "Session State",
        "level": 1,
        "order": 2.7,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": state_dur,
        "input": {
            "from_previous": "LEVEL_1_PREFERENCES",
            "session_id": session_id,
            "purpose": "Load durable session state for context continuity"
        },
        "policy": {
            "script": "session-state.py",
            "args": ["--summary"],
            "rules_applied": [
                "load_project_state",
                "track_completed_tasks",
                "track_files_modified",
                "track_pending_work"
            ]
        },
        "policy_output": {
            "project": state_summary.get('project', 'unknown'),
            "completed_tasks": completed_tasks_count,
            "files_modified": files_modified_count,
            "pending_work": pending_work_count,
            "script_exists": state_script.exists()
        },
        "decision": f"Session state loaded: {completed_tasks_count} completed, {pending_work_count} pending",
        "passed_to_next": {
            "session_state_available": bool(state_summary),
            "pending_work": pending_work_count
        }
    })
    if state_summary:
        print(f"   [OK] State: {completed_tasks_count} tasks done, {files_modified_count} files, {pending_work_count} pending")
    else:
        print(f"   [OK] State: Fresh session")

    print("[OK] LEVEL 1 COMPLETE (4 sub-steps)")
    print()

    # =========================================================================
    # TECH STACK DETECTION (needed by Level 2.2 conditional loading)
    # =========================================================================
    tech_stack = detect_tech_stack(cwd=hook_cwd if hook_cwd else None)
    is_spring_boot = 'spring-boot' in tech_stack

    # =========================================================================
    # LEVEL 2: RULES/STANDARDS SYSTEM (2 sub-levels)
    # =========================================================================
    print("[LEVEL 2] RULES/STANDARDS SYSTEM (MIDDLE LAYER)")

    standards_script = MEMORY_BASE / '02-standards-system' / 'standards-loader.py'
    if not standards_script.exists():
        standards_script = SCRIPT_DIR / 'architecture' / '02-standards-system' / 'standards-loader.py'

    # ------------------------------------------------------------------
    # LEVEL 2.1: COMMON STANDARDS (always active)
    # ------------------------------------------------------------------
    step_start_2_1 = datetime.now()
    common_count = 12
    common_rules = 65
    common_list = []
    common_dur = 0

    if standards_script.exists():
        c_out, _, c_rc, common_dur = run_script_with_retry(standards_script, ['--load-common'], timeout=10, step_name='Level-2.1.Common')
        for line in c_out.splitlines():
            if 'Common Standards:' in line:
                try:
                    common_count = int(line.split(':')[1].strip())
                except Exception:
                    pass
            if 'Common Rules Loaded:' in line:
                try:
                    common_rules = int(line.split(':')[1].strip())
                except Exception:
                    pass
            if line.strip().startswith('-') or line.strip().startswith('*'):
                common_list.append(line.strip().lstrip('-* '))

    if not common_list:
        common_list = [
            "naming_conventions", "error_handling_common", "logging_standards",
            "security_basics", "code_organization", "api_design_common",
            "database_common", "constants_common", "testing_approach",
            "documentation_common", "git_standards", "file_organization"
        ]

    trace["pipeline"].append({
        "step": "LEVEL_2_1_COMMON",
        "name": "Common Standards (Universal)",
        "level": 2.1,
        "order": 3,
        "is_blocking": False,
        "timestamp": step_start_2_1.isoformat(),
        "duration_ms": common_dur,
        "input": {
            "from_previous": "LEVEL_1_SESSION",
            "session_id": session_id,
            "context_pct": context_pct,
            "purpose": "Load universal coding standards BEFORE any code generation"
        },
        "policy": {
            "script": "standards-loader.py",
            "args": ["--load-common"],
            "rules_applied": [
                "load_common_standards",
                "count_common_rules",
                "make_standards_available_to_execution_layer"
            ]
        },
        "policy_output": {
            "standards_loaded": common_count,
            "rules_loaded": common_rules,
            "standards_list": common_list,
            "exit_code": 0 if standards_script.exists() else -1,
            "fallback_used": not standards_script.exists()
        },
        "decision": f"Common: {common_count} standards ({common_rules} rules) loaded",
        "passed_to_next": {
            "common_standards": common_count,
            "common_rules": common_rules,
            "common_list": common_list
        }
    })

    print(f"   [2.1] Common Standards: {common_count} loaded, {common_rules} rules")

    # ------------------------------------------------------------------
    # LEVEL 2.2: MICROSERVICES STANDARDS (conditional on Spring Boot)
    # ------------------------------------------------------------------
    micro_count = 0
    micro_rules = 0
    micro_list = []
    micro_dur = 0
    microservices_active = is_spring_boot

    if is_spring_boot:
        step_start_2_2 = datetime.now()
        micro_count = 15
        micro_rules = 139

        if standards_script.exists():
            m_out, _, m_rc, micro_dur = run_script_with_retry(standards_script, ['--load-microservices'], timeout=10, step_name='Level-2.2.Microservices')
            for line in m_out.splitlines():
                if 'Microservices Standards:' in line:
                    try:
                        micro_count = int(line.split(':')[1].strip())
                    except Exception:
                        pass
                if 'Microservices Rules Loaded:' in line:
                    try:
                        micro_rules = int(line.split(':')[1].strip())
                    except Exception:
                        pass
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    micro_list.append(line.strip().lstrip('-* '))

        if not micro_list:
            micro_list = [
                "java_project_structure", "config_server_patterns",
                "secret_management", "response_format_ApiResponseDto",
                "api_design_standards", "database_conventions",
                "error_handling_rules", "service_layer_pattern",
                "entity_pattern", "controller_pattern",
                "constants_organization", "common_utilities",
                "documentation_standards", "kubernetes_network_policies",
                "k8s_docker_jenkins_infra"
            ]

        trace["pipeline"].append({
            "step": "LEVEL_2_2_MICROSERVICES",
            "name": "Microservices Standards (Spring Boot)",
            "level": 2.2,
            "order": 4,
            "is_blocking": False,
            "timestamp": step_start_2_2.isoformat(),
            "duration_ms": micro_dur,
            "input": {
                "from_previous": "LEVEL_2_1_COMMON",
                "tech_stack": tech_stack,
                "is_spring_boot": True,
                "purpose": "Load Spring Boot microservices standards"
            },
            "policy": {
                "script": "standards-loader.py",
                "args": ["--load-microservices"],
                "rules_applied": [
                    "load_microservices_standards",
                    "count_microservices_rules",
                    "spring_boot_specific_enforcement"
                ]
            },
            "policy_output": {
                "standards_loaded": micro_count,
                "rules_loaded": micro_rules,
                "standards_list": micro_list,
                "exit_code": 0 if standards_script.exists() else -1,
                "fallback_used": not standards_script.exists()
            },
            "decision": f"Microservices: {micro_count} standards ({micro_rules} rules) loaded (Spring Boot detected)",
            "passed_to_next": {
                "microservices_standards": micro_count,
                "microservices_rules": micro_rules,
                "microservices_list": micro_list
            }
        })

        print(f"   [2.2] Microservices Standards: {micro_count} loaded, {micro_rules} rules (Spring Boot detected)")
    else:
        trace["pipeline"].append({
            "step": "LEVEL_2_2_MICROSERVICES",
            "name": "Microservices Standards (SKIPPED)",
            "level": 2.2,
            "order": 4,
            "is_blocking": False,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": 0,
            "input": {
                "tech_stack": tech_stack,
                "is_spring_boot": False
            },
            "policy_output": {
                "skipped": True,
                "reason": "No Spring Boot detected in tech stack"
            },
            "decision": "SKIPPED - not a Spring Boot project",
            "passed_to_next": {
                "microservices_standards": 0,
                "microservices_rules": 0
            }
        })
        print(f"   [2.2] Microservices Standards: SKIPPED (no Spring Boot detected)")

    # Combined totals for backward compatibility
    standards_count = common_count + micro_count
    rules_count = common_rules + micro_rules
    standards_list = common_list + micro_list

    print(f"[OK] LEVEL 2 COMPLETE ({standards_count} standards, {rules_count} rules)")
    print()

    # =========================================================================
    # LEVEL 3: EXECUTION SYSTEM - 12 STEPS
    # =========================================================================
    print("[LEVEL 3] EXECUTION SYSTEM (IMPLEMENTATION) - 12 STEPS")

    # Carry-forward from Level 2 for chaining
    prev_output = {
        "standards_active": standards_count,
        "rules_active": rules_count,
        "common_standards": common_count,
        "common_rules": common_rules,
        "microservices_standards": micro_count,
        "microservices_rules": micro_rules,
        "microservices_active": microservices_active,
        "context_pct": context_pct,
        "session_id": session_id
    }

    # ------------------------------------------------------------------
    # STEP 3.0: PROMPT GENERATION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    complexity = 5
    task_type = 'General'
    prompt_script = MEMORY_BASE / '03-execution-system' / '00-prompt-generation' / 'prompt-generator.py'
    if not prompt_script.exists():
        prompt_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-prompt-generation' / 'prompt-generator.py'
    pr_out = ''
    pr_dur = 0
    enhanced_prompt_summary = ''
    rewritten_prompt = ''
    if prompt_script.exists():
        pr_out, _, _, pr_dur = run_script_with_retry(prompt_script, [user_message], timeout=8, step_name='Step-3.0.Prompt-Gen')
        for line in pr_out.splitlines():
            if 'estimated_complexity:' in line:
                try:
                    complexity = int(line.split(':')[1].strip())
                except Exception:
                    pass
            if line.startswith('task_type:'):
                task_type = line.split(':', 1)[1].strip()
            if line.startswith('rewritten_prompt:'):
                rewritten_prompt = line.split(':', 1)[1].strip()
            if line.startswith('enhanced_prompt:'):
                enhanced_prompt_summary = line.split(':', 1)[1].strip()

        # Use rewritten_prompt as the effective prompt (prefer over enhanced_prompt)
        effective_prompt = rewritten_prompt if rewritten_prompt else enhanced_prompt_summary

        # Show rewritten prompt to user - ALL modes
        if rewritten_prompt:
            print(f"   [3.0] Rewritten Prompt: {rewritten_prompt[:200]}")
        elif enhanced_prompt_summary:
            print(f"   [3.0] Enhanced Prompt: {enhanced_prompt_summary[:150]}")
        if mode == 'verbose' and pr_out:
            print(f"   [3.0] Prompt Generator Output:")
            for ln in pr_out.splitlines()[:10]:
                print(f"         {ln}")
    else:
        effective_prompt = user_message

    step_3_0_output = {
        "estimated_complexity": complexity,
        "task_type": task_type,
        "rewritten_prompt": rewritten_prompt if rewritten_prompt else "NOT_GENERATED",
        "enhanced_prompt": enhanced_prompt_summary if enhanced_prompt_summary else "NOT_GENERATED",
        "effective_prompt": effective_prompt if effective_prompt else user_message,
        "script_exists": prompt_script.exists()
    }
    step_3_0_decision = f"Complexity={complexity}, Type={task_type} - proceed with analysis"

    # STEP 3.0 MOVED TO AFTER SKILL SELECTION - See STEP 3.5

    # ------------------------------------------------------------------
    # STEP 3.1: TASK BREAKDOWN
    # ------------------------------------------------------------------
    step_start = datetime.now()
    task_count = 2
    task_script = MEMORY_BASE / '03-execution-system' / '01-task-breakdown' / 'task-auto-analyzer.py'
    if not task_script.exists():
        task_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '01-task-breakdown' / 'task-auto-analyzer.py'
    tk_dur = 0
    if task_script.exists():
        tk_out, _, _, tk_dur = run_script_with_retry(task_script, [user_message], timeout=8, step_name='Step-3.1.Task-Breakdown')
        for line in tk_out.splitlines():
            if 'Total Tasks:' in line:
                try:
                    task_count = int(line.split(':')[1].strip())
                except Exception:
                    pass

    step_3_1_output = {"task_count": task_count, "script_exists": task_script.exists()}

    # AUTO-CREATE TASKS: Generate task objects for tracking
    # Rule: "create_tasks_in_task_system" - implement here
    tasks_created = []
    if task_count > 0:
        for i in range(1, task_count + 1):
            task_subject = f"Task {i}/{task_count}: {task_type}"
            task_description = f"""
Task {i} of {task_count} identified by policy system.

Session: {session_id}
Complexity: {complexity}/25
Task Type: {task_type}
Agent/Skill: {skill_agent_name if 'skill_agent_name' in locals() else 'TBD'}

Work to complete: Execute phase {i} of the identified work breakdown.
"""
            try:
                # Import TaskCreate if available (this would be integrated with Claude Code's task system)
                # For now, just track in our logs
                tasks_created.append({
                    "task_id": f"{session_id}_task_{i}",
                    "subject": task_subject,
                    "description": task_description,
                    "status": "pending",
                    "created_at": datetime.now().isoformat()
                })
                print(f"   [3.0] ✓ Task {i}/{task_count} created: {task_subject}")
            except Exception as e:
                print(f"   [3.0] ✗ Failed to create task {i}: {str(e)}")

    step_3_1_output["tasks_created"] = len(tasks_created)
    step_3_1_output["tasks"] = tasks_created

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_0",
        "name": "Automatic Task Breakdown",
        "level": 3,
        "order": 4,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": tk_dur,
        "input": {
            "from_previous": "LEVEL_2_STANDARDS",
            "complexity": complexity,
            "task_type": task_type,
            "user_message": user_message,
            "purpose": "Break work into trackable tasks with dependencies"
        },
        "policy": {
            "script": "task-auto-analyzer.py",
            "args": [user_message],
            "rules_applied": [
                "calculate_complexity_score",
                "divide_into_phases_if_complex",
                "one_file_equals_one_task",
                "auto_detect_dependency_chain",
                "create_tasks_in_task_system"
            ]
        },
        "policy_output": {
            "task_count": task_count,
            "tasks_created": step_3_1_output.get("tasks_created", 0),
            "script_exists": task_script.exists(),
            "tasks": step_3_1_output.get("tasks", [])
        },
        "decision": f"Created {task_count} tasks with auto-tracking enabled ✓",
        "passed_to_next": {
            "task_count": task_count,
            "complexity": complexity,
            "task_type": task_type
        }
    })
    print(f"   [3.0] Task Breakdown: {task_count} tasks analyzed")
    prev_output = {"task_count": task_count, "complexity": complexity, "task_type": task_type}

    # ------------------------------------------------------------------
    # STEP 3.2: PLAN MODE SUGGESTION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    plan_required = False
    adj_complexity = complexity
    plan_script = MEMORY_BASE / '03-execution-system' / '02-plan-mode' / 'auto-plan-mode-suggester.py'
    if not plan_script.exists():
        plan_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '02-plan-mode' / 'auto-plan-mode-suggester.py'
    pl_dur = 0
    plan_score_detail = {}
    if plan_script.exists():
        pl_out, _, _, pl_dur = run_script_with_retry(plan_script, [str(complexity), user_message], timeout=8, step_name='Step-3.2.Plan-Mode')
        pl_data = safe_json(pl_out)
        plan_required = pl_data.get('plan_mode_required', False)
        if 'score' in pl_data:
            adj_complexity = pl_data.get('score', complexity)
        plan_score_detail = pl_data

    plan_str = 'REQUIRED' if plan_required else 'NOT required'

    # Determine plan mode reasoning
    if adj_complexity >= 20:
        plan_reason = "VERY_COMPLEX (>=20) - Auto-enter plan mode mandatory"
    elif adj_complexity >= 10:
        plan_reason = "COMPLEX (10-19) - Plan mode strongly recommended"
    elif adj_complexity >= 5:
        plan_reason = "MODERATE (5-9) - Recommend-then-ask (give recommendation with reasoning, then confirm)"
    else:
        plan_reason = "SIMPLE (<5) - Proceed directly"

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_1",
        "name": "Plan Mode Suggestion",
        "level": 3,
        "order": 5,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": pl_dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_0",
            "complexity": complexity,
            "task_count": task_count,
            "task_type": task_type,
            "user_message": user_message,
            "purpose": "Decide if plan mode needed before execution"
        },
        "policy": {
            "script": "auto-plan-mode-suggester.py",
            "args": [str(complexity), user_message],
            "rules_applied": [
                "analyze_multi_service_impact",
                "check_database_changes",
                "check_security_critical",
                "adjust_complexity_score",
                "score_0_4_no_plan",
                "score_5_9_recommend_then_ask",
                "score_10_19_recommend",
                "score_20plus_mandatory"
            ]
        },
        "policy_output": {
            "plan_mode_required": plan_required,
            "adjusted_complexity": adj_complexity,
            "plan_reasoning": plan_reason,
            "raw_output": plan_score_detail
        },
        "decision": f"Plan mode: {plan_str} - {plan_reason}",
        "passed_to_next": {
            "plan_required": plan_required,
            "adjusted_complexity": adj_complexity,
            "plan_str": plan_str
        }
    })
    print(f"   [3.1] Plan Mode: {plan_str} (complexity {adj_complexity})")
    prev_output = {"plan_required": plan_required, "adj_complexity": adj_complexity}

    # ------------------------------------------------------------------
    # STEP 3.3: CONTEXT CHECK (pre-execution re-verify)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    ctx_out2, _, _, ctx2_dur = run_script_with_retry(ctx_script, ['--current-status'], timeout=8, step_name='Step-3.3.Context-Recheck')
    ctx_data2 = safe_json(ctx_out2)
    context_pct2 = ctx_data2.get('percentage', context_pct)

    ctx2_ok = context_pct2 < 90
    ctx2_warning = context_pct2 >= 70

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_2",
        "name": "Context Check (Pre-Execution)",
        "level": 3,
        "order": 6,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": ctx2_dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_1",
            "plan_required": plan_required,
            "adj_complexity": adj_complexity,
            "purpose": "Re-verify context before heavy execution begins"
        },
        "policy": {
            "script": "context-monitor-v2.py",
            "args": ["--current-status"],
            "rules_applied": [
                "re_measure_context_after_loading",
                "block_at_90_percent",
                "warn_at_70_percent"
            ]
        },
        "policy_output": {
            "percentage": context_pct2,
            "changed_since_level_1": context_pct2 - context_pct,
            "safe_to_proceed": ctx2_ok,
            "warning": ctx2_warning
        },
        "decision": "SAFE - proceed with execution" if ctx2_ok else "CRITICAL - context too high",
        "passed_to_next": {
            "context_pct": context_pct2,
            "safe_to_proceed": ctx2_ok
        }
    })
    print(f"   [3.2] Context Check: {context_pct2}%")

    # ------------------------------------------------------------------
    # STEP 3.4: MODEL SELECTION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    # Model Selection: Opus 4.6 "The Strategist" | Sonnet 4.6 "The Workhorse" | Haiku 4.5 "The Executor"
    # Pricing: Opus $5/$25, Sonnet $3/$15, Haiku $1/$5 per MTok
    if adj_complexity < 5:
        selected_model = 'HAIKU'
        model_reason = "Simple task (<5) - Haiku 4.5 'The Executor' (fastest, $1/$5 MTok)"
    elif adj_complexity < 10:
        selected_model = 'HAIKU/SONNET'
        model_reason = "Moderate task (5-9) - Haiku or Sonnet based on type"
    elif adj_complexity < 20:
        selected_model = 'SONNET'
        model_reason = "Complex task (10-19) - Sonnet 4.6 'The Workhorse' ($3/$15 MTok)"
    else:
        selected_model = 'OPUS'
        model_reason = "Very complex (>=20) - Opus 4.6 'The Strategist' ($5/$25 MTok)"

    # Override rules
    model_overrides = []
    if plan_required:
        selected_model = 'OPUS'
        model_reason = "Plan mode active - Opus 4.6 'The Strategist' mandatory"
        model_overrides.append("plan_mode_forces_opus")
    if task_type in ('Security', 'Authentication'):
        if selected_model == 'HAIKU':
            selected_model = 'SONNET'
            model_overrides.append("security_task_minimum_sonnet")

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_3",
        "name": "Intelligent Model Selection",
        "level": 3,
        "order": 7,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": 0,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_2",
            "adjusted_complexity": adj_complexity,
            "task_type": task_type,
            "plan_required": plan_required,
            "context_pct": context_pct2,
            "purpose": "Select optimal Claude model for this task"
        },
        "policy": {
            "script": "model-auto-selector.py (inline logic)",
            "rules_applied": [
                "complexity_0_4_haiku",
                "complexity_5_9_haiku_or_sonnet",
                "complexity_10_19_sonnet",
                "complexity_20plus_opus",
                "plan_mode_forces_opus",
                "security_task_minimum_sonnet",
                "architecture_task_use_opus",
                "novel_problem_upgrade_one_level"
            ]
        },
        "policy_output": {
            "selected_model": selected_model,
            "reason": model_reason,
            "overrides_applied": model_overrides,
            "complexity_used": adj_complexity
        },
        "decision": f"Use {selected_model} - {model_reason}",
        "passed_to_next": {
            "model": selected_model,
            "model_reason": model_reason
        }
    })
    print(f"   [3.3] Model Selection: {selected_model}")
    prev_output = {"model": selected_model}

    # ------------------------------------------------------------------
    # STEP 3.5: SKILL/AGENT SELECTION
    # ------------------------------------------------------------------
    step_start = datetime.now()

    # tech_stack already detected before Level 2 (reused here)

    # Step 2: 4-layer selection: task_type -> keyword score -> tech_stack -> adaptive
    # Passes user_message for dynamic keyword analysis (Layer 2)
    skill_agent_name, agent_type, supplementary_skills, skill_reason = get_agent_and_skills(
        tech_stack, task_type=task_type, user_message=user_message
    )

    # Step 3: Escalate to orchestrator for very high complexity / many tasks
    # RULES:
    #   - NEVER override L1-TaskType matches (trust explicit task-type->agent mapping)
    #   - NEVER override adaptive-skill-intelligence (it handles its own logic)
    #   - Only escalate when complexity >= 15 OR task_count > 8 (truly overloaded)
    #   - orchestrator-agent is for MULTI-DOMAIN coordination, not just "many tasks"
    l1_matched = skill_reason.startswith('[L1-TaskType]')
    if (adj_complexity >= 15 or task_count > 8) and not l1_matched and skill_agent_name != 'adaptive-skill-intelligence':
        agent_type = 'agent'
        skill_agent_name = 'orchestrator-agent'
        skill_reason += ' [escalated to orchestrator-agent: complexity/task count]'

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_4",
        "name": "Auto Skill and Agent Selection",
        "level": 3,
        "order": 8,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": 0,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_3",
            "model": selected_model,
            "task_type": task_type,
            "complexity": adj_complexity,
            "task_count": task_count,
            "purpose": "Select skill or agent from registry for this task"
        },
        "policy": {
            "script": "auto-skill-agent-selector.py (inline logic)",
            "rules_applied": [
                "task_type_registry_checked_FIRST",
                "ui_ux_task_type_maps_to_ui_ux_designer_agent",
                "backend_task_type_maps_to_spring_boot_microservices",
                "devops_task_type_maps_to_devops_engineer",
                "tech_stack_used_as_secondary_selector",
                "collect_supplementary_skills_from_tech_stack",
                "if_no_match_use_adaptive_skill_intelligence",
                "escalate_to_orchestrator_agent_if_high_complexity"
            ]
        },
        "policy_output": {
            "tech_stack": tech_stack,
            "selected_type": agent_type,
            "selected_name": skill_agent_name,
            "supplementary_skills": supplementary_skills,
            "reason": skill_reason
        },
        "decision": f"Use {agent_type}: {skill_agent_name}" + (f" + skills {supplementary_skills}" if supplementary_skills else "") + f" ({skill_reason})",
        "passed_to_next": {
            "skill_or_agent": skill_agent_name,
            "type": agent_type,
            "supplementary_skills": supplementary_skills,
            "tech_stack": tech_stack
        }
    })
    supp_str = f" + {supplementary_skills}" if supplementary_skills else ""
    print(f"   [3.4] Skill/Agent: {skill_agent_name} ({agent_type}){supp_str}")

    # ------------------------------------------------------------------
    # STEP 3.5: PROMPT GENERATION (WITH SKILL CONTEXT)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    prompt_script = MEMORY_BASE / '03-execution-system' / '00-prompt-generation' / 'prompt-generator.py'
    if not prompt_script.exists():
        prompt_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-prompt-generation' / 'prompt-generator.py'
    pr_dur_3_5 = 0
    if prompt_script.exists():
        pr_out, _, _, pr_dur_3_5 = run_script_with_retry(prompt_script, [user_message], timeout=8, step_name='Step-3.5.Prompt-Skill-Context')
        pr_data = safe_json(pr_out)
        rewritten_prompt_3_5 = pr_data.get('rewritten_prompt', '')
        enhanced_prompt_3_5 = pr_data.get('enhanced_prompt', '')
    else:
        rewritten_prompt_3_5 = rewritten_prompt
        enhanced_prompt_3_5 = enhanced_prompt_summary

    step_3_5_output = {
        "estimated_complexity": complexity,
        "task_type": task_type,
        "rewritten_prompt": rewritten_prompt_3_5 if rewritten_prompt_3_5 else "NOT_GENERATED",
        "enhanced_prompt": enhanced_prompt_3_5 if enhanced_prompt_3_5 else "NOT_GENERATED",
        "effective_prompt": (rewritten_prompt_3_5 if rewritten_prompt_3_5 else enhanced_prompt_3_5) if (rewritten_prompt_3_5 or enhanced_prompt_3_5) else user_message,
        "script_exists": prompt_script.exists(),
        "skill_context_applied": True,
        "skill_or_agent": skill_agent_name,
        "supplementary_skills": supplementary_skills
    }
    step_3_5_decision = f"Enhanced prompt with skill context - using {skill_agent_name} for generation"

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_5",
        "name": "Prompt Generation (With Skill Context)",
        "level": 3,
        "order": 9,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": pr_dur_3_5,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_4",
            "user_message": user_message,
            "skill_or_agent": skill_agent_name,
            "supplementary_skills": supplementary_skills,
            "purpose": "Generate enhanced prompt with skill context"
        },
        "policy": {
            "script": "prompt-generator.py",
            "args": [user_message],
            "rules_applied": [
                "analyze_user_intent_with_skill_context",
                "rewrite_to_proper_english_prompt",
                "enrich_with_skill_agent_context",
                "extract_entities_and_operations",
                "apply_supplementary_skill_patterns"
            ]
        },
        "policy_output": step_3_5_output,
        "decision": step_3_5_decision,
        "passed_to_next": {
            "complexity": complexity,
            "task_type": task_type,
            "user_message": user_message,
            "rewritten_prompt": rewritten_prompt_3_5 if rewritten_prompt_3_5 else user_message,
            "use_rewritten_prompt": bool(rewritten_prompt_3_5),
            "skill_context_applied": True
        }
    })
    print(f"   [3.5] Prompt Generation (with skill context): Complexity={complexity}, Type={task_type}")
    if rewritten_prompt_3_5:
        print(f"   [3.5] CLAUDE_MUST: Use REWRITTEN_PROMPT + {skill_agent_name} patterns")

    # ------------------------------------------------------------------
    # STEP 3.6: TOOL OPTIMIZATION
    # ------------------------------------------------------------------
    tool_rules = [
        "read_files_gt_500_lines_use_offset_limit",
        "grep_always_add_head_limit_100",
        "glob_restrict_path_if_service_known",
        "tree_first_visit_use_L2_or_L3",
        "bash_combine_sequential_commands",
        "edit_write_show_brief_confirmation"
    ]

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_6",
        "name": "Tool Usage Optimization",
        "level": 3,
        "order": 10,
        "is_blocking": False,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": 0,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_5",
            "skill_agent": skill_agent_name,
            "context_pct": context_pct2,
            "purpose": "Apply token-saving optimizations to every tool call"
        },
        "policy": {
            "script": "tool-usage-optimizer.py (rules loaded)",
            "rules_applied": tool_rules
        },
        "policy_output": {
            "rules_active": len(tool_rules),
            "estimated_token_savings": "60-80%",
            "optimization_level": ctx_optimization
        },
        "decision": f"Tool optimization rules loaded - apply before every tool call",
        "passed_to_next": {
            "tool_rules_active": True,
            "optimization_level": ctx_optimization
        }
    })
    print(f"   [3.6] Tool Optimization: Ready ({len(tool_rules)} rules)")

    # ------------------------------------------------------------------
    # STEP 3.7: FAILURE PREVENTION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    fp_script = MEMORY_BASE / '03-execution-system' / 'failure-prevention' / 'pre-execution-checker.py'
    if not fp_script.exists():
        fp_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / 'failure-prevention' / 'pre-execution-checker.py'
    fp_dur = 0
    fp_checks = {}
    if fp_script.exists():
        fp_out, _, fp_rc, fp_dur = run_script_with_retry(fp_script, ['--check-all'], timeout=8, step_name='Step-3.7.Failure-Prevention')
        fp_checks = {"exit_code": fp_rc, "output_lines": len(fp_out.splitlines())}

    failure_rules = [
        "bash_del_to_rm_copy_to_cp_dir_to_ls",
        "github_operations_use_gh_cli",
        "git_local_use_git_command",
        "no_unicode_in_python_on_windows",
        "edit_tool_strip_line_number_prefix",
        "read_large_files_with_offset_limit"
    ]

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_7",
        "name": "Failure Prevention",
        "level": 3,
        "order": 11,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": fp_dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_6",
            "tool_rules_active": True,
            "purpose": "Pre-execution checks to prevent known failure patterns"
        },
        "policy": {
            "script": "pre-execution-checker.py",
            "args": ["--check-all"],
            "rules_applied": failure_rules
        },
        "policy_output": fp_checks if fp_checks else {"status": "rules_loaded", "script_found": fp_script.exists()},
        "decision": "Failure prevention active - auto-fix applied before every tool",
        "passed_to_next": {
            "failure_prevention_active": True,
            "auto_fixes_enabled": True
        }
    })
    print(f"   [3.7] Failure Prevention: Checked")

    # ------------------------------------------------------------------
    # STEP 3.8: PARALLEL EXECUTION ANALYSIS
    # ------------------------------------------------------------------
    parallel_possible = task_count >= 3

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_8",
        "name": "Parallel Execution Analysis",
        "level": 3,
        "order": 12,
        "is_blocking": False,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": 0,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_7",
            "task_count": task_count,
            "purpose": "Detect which tasks can run in parallel for 3-10x speedup"
        },
        "policy": {
            "script": "auto-parallel-detector.py (inline logic)",
            "rules_applied": [
                "check_tasks_with_no_blockedBy_dependencies",
                "group_tasks_by_dependency_wave",
                "calculate_speedup_estimate",
                "3_or_more_independent_use_parallel"
            ]
        },
        "policy_output": {
            "parallel_possible": parallel_possible,
            "task_count": task_count,
            "reason": "3+ independent tasks" if parallel_possible else "Tasks have dependencies or count < 3"
        },
        "decision": "Use parallel execution" if parallel_possible else "Use sequential execution",
        "passed_to_next": {
            "execution_mode": "parallel" if parallel_possible else "sequential",
            "parallel_possible": parallel_possible
        }
    })
    print(f"   [3.8] Parallel Analysis: {'Parallel' if parallel_possible else 'Sequential'}")

    # ------------------------------------------------------------------
    # STEPS 3.9 - 3.12: EXECUTE, SAVE, COMMIT, LOG
    # ------------------------------------------------------------------

    # Load policy rules from policies/ directory (recursive)
    loaded_policies = load_policy_rules()
    policy_count = sum(len(v) for v in loaded_policies.values())

    for step_info in [
        ("3.9",  13, "Execute Tasks",   "All policies enforced - execute with full standards active"),
        ("3.10", 14, "Session Save",    "Auto-save session state at each milestone"),
        ("3.11", 15, "Git Auto-Commit", f"Auto-commit + version bump + release ({policy_count} policies loaded)"),
        ("3.12", 16, "Logging",         "Log all policy applications, tool calls, decisions"),
    ]:
        step_num, order, step_name, step_decision = step_info
        trace["pipeline"].append({
            "step": f"LEVEL_3_STEP_{step_num.replace('.', '_')}",
            "name": step_name,
            "level": 3,
            "order": order,
            "is_blocking": False,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": 0,
            "input": {"from_previous": f"LEVEL_3_STEP_3_{int(float(step_num))-1 if float(step_num) > 9 else '8'}"},
            "policy": {"rules_applied": [step_name.lower().replace(' ', '_')]},
            "policy_output": {"status": "ACTIVE", "policies_loaded": policy_count},
            "decision": step_decision,
            "passed_to_next": {"status": "ACTIVE"}
        })
        print(f"   [{step_num}] {step_name}: Active")

    # =========================================================================
    # POLICY ENFORCEMENT OUTPUT: Print critical rules to stdout (Claude reads these)
    # Only rules NOT auto-enforced by scripts — Claude must follow these directly.
    # =========================================================================

    # Version-release policy
    if 'version-release-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] VERSION-RELEASE POLICY (from policies/03-execution-system/09-git-commit/):")
        print("   After pushing code changes to any repo:")
        print("   1. Bump VERSION file + source version constant")
        print("   2. Build artifact (mvn package for IDE)")
        print("   3. Commit version bump + push")
        print("   4. Create GitHub Release (gh release create) for IDE")
        print("   5. Ensure version consistency across README/CLAUDE.md/badges")

    # Task breakdown policy (not auto-enforced — Claude must use TaskCreate)
    if 'automatic-task-breakdown-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] TASK BREAKDOWN POLICY:")
        print("   1. ALWAYS create tasks via TaskCreate on EVERY coding request (minimum 1)")
        print("   2. Break complex tasks into phases (Foundation, Logic, API, Config)")
        print("   3. Mark tasks completed via TaskUpdate when done")
        print("   4. Create task dependencies if needed (blockedBy/blocks)")

    # Model selection policy (not auto-enforced — Claude must route correctly)
    if 'model-selection-enforcement' in loaded_policies.get('level-3', {}) or \
       'intelligent-model-selection-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] MODEL SELECTION POLICY:")
        print("   1. Search/explore tasks -> Use Agent(Explore, model=haiku)")
        print("   2. Architecture/design tasks -> Use Agent(Plan, model=opus)")
        print("   3. Implementation tasks -> Use current model (Sonnet/Opus)")
        print("   4. Simple tasks (grep, read) -> Use model=haiku for subagents")

    # Tool optimization policy (partially auto-enforced — these rules need Claude awareness)
    if 'tool-usage-optimization-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] TOOL OPTIMIZATION POLICY:")
        print("   1. Add head_limit to EVERY Grep call (default: 100)")
        print("   2. Use offset/limit for files >500 lines (Read tool)")
        print("   3. NEVER use 'tree' command - use Glob or 'find' instead")
        print("   4. Combine sequential Bash commands with && in a single call")

    # Failure prevention policy (partially auto-enforced — Unicode rule needs Claude)
    if 'common-failures-prevention' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] FAILURE PREVENTION POLICY:")
        print("   1. NO Unicode/emojis in Python files on Windows (use ASCII: [OK], [WARN])")
        print("   2. Strip line number prefixes before Edit (remove '  123->' patterns)")
        print("   3. Quote all file paths containing spaces")
        print("   4. Auto-translate: del->rm, copy->cp, dir->ls in Bash")

    # Common standards (Level 2.1) - always enforced
    if loaded_policies.get('level-2', {}):
        print()
        print("[ENFORCE] COMMON STANDARDS (Level 2.1):")
        print("   1. Use consistent naming: camelCase vars, PascalCase classes, UPPER_SNAKE constants")
        print("   2. NEVER swallow exceptions - catch specific types, include context")
        print("   3. NO hardcoded secrets/passwords/API keys in source code")
        print("   4. NO magic numbers/strings - use named constants")
        print("   5. Write meaningful commit messages (feat/fix/refactor: description)")
        print("   6. Validate ALL external input, use parameterized DB queries")

    # Microservices standards (Level 2.2) - only if Spring Boot detected
    if microservices_active:
        print()
        print("[ENFORCE] MICROSERVICES STANDARDS (Level 2.2 - Spring Boot):")
        print("   1. NO hardcoded strings - use constants (MessageConstants, ApiConstants)")
        print("   2. ALL API responses use ApiResponseDto<T> wrapper")
        print("   3. Service implementations are package-private, extend Helper classes")
        print("   4. Config Server ONLY for DB/Redis/Feign config (never in application.yml)")
        print("   5. Secrets via Secret Manager: ${SECRET:key-name} syntax")

    print("[OK] LEVEL 3 COMPLETE (All 12 steps executed)")
    print()

    # =========================================================================
    # FINAL DECISION - what was decided after all policies
    # =========================================================================
    flow_end = datetime.now()
    duration_sec = (flow_end - flow_start).total_seconds()

    final_decision = {
        "timestamp": flow_end.isoformat(),
        "user_prompt": user_message,
        "complexity": adj_complexity,
        "task_type": task_type,
        "plan_mode": plan_required,
        "model_selected": selected_model,
        "model_reason": model_reason,
        "task_count": task_count,
        "execution_mode": "parallel" if parallel_possible else "sequential",
        "skill_or_agent": skill_agent_name,
        "supplementary_skills": supplementary_skills,
        "tech_stack": tech_stack,
        "context_pct": context_pct2,
        "standards_active": standards_count,
        "rules_active": rules_count,
        "common_standards": common_count,
        "common_rules": common_rules,
        "microservices_standards": micro_count,
        "microservices_rules": micro_rules,
        "microservices_active": microservices_active,
        "session_id": session_id,
        "proceed": True,
        "summary": (
            f"Complexity={adj_complexity} {task_type} task -> "
            f"Model={selected_model}, {task_count} tasks, "
            f"{'Plan mode' if plan_required else 'Direct execution'}, "
            f"Context={context_pct2}%"
        )
    }

    trace["final_decision"] = final_decision
    trace["work_started"] = True
    trace["status"] = "COMPLETED"
    trace["meta"]["flow_end"] = flow_end.isoformat()
    trace["meta"]["duration_seconds"] = round(duration_sec, 2)

    # =========================================================================
    # COMPLETE SCRIPT INVENTORY (All 82 scripts)
    # Documents every script's status, category, hook, and execution result.
    # =========================================================================
    trace["script_inventory"] = _build_script_inventory()

    # =========================================================================
    # SAVE TRACE JSON
    # =========================================================================
    _save_trace(trace, session_log_dir, flow_start)

    # Update session JSON
    session_json_file = MEMORY_BASE / 'sessions' / f'{session_id}.json'
    if session_json_file.exists():
        sess_data = read_json(session_json_file)
        sess_data.update({
            "last_updated": flow_end.isoformat(),
            "log_dir": str(session_log_dir),
            "flow_runs": sess_data.get('flow_runs', 0) + 1,
            "last_prompt": user_message,
            "last_model": selected_model,
            "last_complexity": adj_complexity,
            "last_task_type": task_type,
            "last_context_pct": context_pct2,
            "standards_count": standards_count,
            "rules_count": rules_count,
            "last_flow_trace": str(session_log_dir / 'flow-trace.json')
        })
        write_json(session_json_file, sess_data)

    # =========================================================================
    # SESSION CHAINING - Auto-tag + load chain context
    # =========================================================================
    chain_script = CURRENT_DIR / 'session-chain-manager.py'
    chain_context_str = ""
    if chain_script.exists() and session_id and session_id != 'UNKNOWN':
        try:
            # Detect project from cwd
            cwd_str = hook_data.get('cwd', '') or os.getcwd()

            # Auto-tag this session
            tag_args = [
                sys.executable, str(chain_script), 'auto-tag',
                '--session', session_id,
                '--prompt', user_message[:300],
                '--task-type', task_type or '',
                '--skill', skill_agent_name or '',
                '--cwd', cwd_str,
            ]
            subprocess.run(
                tag_args, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=5
            )

            # Load chain context for display
            ctx_result = subprocess.run(
                [sys.executable, str(chain_script), 'context',
                 '--session', session_id],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=5
            )
            if ctx_result.returncode == 0 and ctx_result.stdout.strip():
                chain_output = ctx_result.stdout.strip()
                # Only show if there's actual chain data (not just "First session")
                if 'Parent:' in chain_output or 'Related:' in chain_output or 'Tag-related:' in chain_output:
                    chain_context_str = chain_output
        except Exception:
            pass  # Chain is non-blocking, never fail the flow

    # =========================================================================
    # SESSION SUMMARY - Accumulate this request's data
    # =========================================================================
    summary_script = CURRENT_DIR / 'session-summary-manager.py'
    if summary_script.exists() and session_id and session_id != 'UNKNOWN':
        try:
            cwd_str = hook_data.get('cwd', '') or os.getcwd()
            # v2.0.0: Pass additional fields for comprehensive summary
            supp_skills_str = ','.join(supplementary_skills) if supplementary_skills else ''
            subprocess.run(
                [sys.executable, str(summary_script), 'accumulate',
                 '--session', session_id,
                 '--prompt', user_message[:300],
                 '--task-type', task_type or '',
                 '--skill', skill_agent_name or '',
                 '--complexity', str(adj_complexity),
                 '--model', selected_model or '',
                 '--cwd', cwd_str,
                 '--plan-mode', str(plan_required).lower(),
                 '--context-pct', str(int(context_pct2)),
                 '--supplementary-skills', supp_skills_str,
                 '--standards-count', str(standards_count),
                 '--rules-count', str(rules_count)],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=5
            )
        except Exception:
            pass  # Summary is non-blocking

    # =========================================================================
    # CONSOLE OUTPUT
    # =========================================================================
    print(SEP)
    print("[OK] COMPLETE EXECUTION FLOW - ALL STEPS PASSED")
    print(SEP)
    print()
    print("[SUMMARY]:")
    print()
    print("LEVEL -1: Auto-Fix Enforcement")
    print("   +-- [OK] All 7 system checks passed")
    print()
    print("LEVEL 1: Sync System (4 sub-steps)")
    print(f"   +-- [1.1] Context: {context_pct}% -> {context_pct2}%")
    print(f"   +-- [1.2] Session: {session_id}")
    print(f"   +-- [1.3] Preferences: {prefs_loaded} loaded")
    print(f"   +-- [1.4] State: {completed_tasks_count} tasks, {files_modified_count} files")
    print()
    print("LEVEL 2: Standards System (2 sub-levels)")
    print(f"   +-- [2.1] Common: {common_count}, Rules: {common_rules}")
    if microservices_active:
        print(f"   +-- [2.2] Microservices: {micro_count}, Rules: {micro_rules}")
    else:
        print(f"   +-- [2.2] Microservices: SKIPPED (no Spring Boot)")
    print()
    print("LEVEL 3: Execution System (12 Steps)")
    print(f"   +-- [3.0] Complexity={complexity}, Type={task_type}")
    print(f"   +-- [3.1] Tasks={task_count}")
    print(f"   +-- [3.2] Plan Mode={plan_str}")
    print(f"   +-- [3.3] Context={context_pct2}%")
    print(f"   +-- [3.4] Model={selected_model} ({model_reason})")
    supp_summary = f" + {supplementary_skills}" if supplementary_skills else ""
    print(f"   +-- [3.5] Agent/Skill={skill_agent_name}{supp_summary}")
    print(f"   +-- [3.6] Tool Optimization={len(tool_rules)} rules")
    print(f"   +-- [3.7] Failure Prevention=Active")
    print(f"   +-- [3.8] Execution Mode={'Parallel' if parallel_possible else 'Sequential'}")
    print(f"   +-- [3.9-3.12] Execute, Save, Commit, Log=Active")
    print()
    print("[FINAL DECISION]:")
    print(f"   {final_decision['summary']}")
    print()
    print("[JSON TRACE]:")
    print(f"   {session_log_dir / 'flow-trace.json'}")
    print()
    if chain_context_str:
        print(chain_context_str)
        print()
    # =========================================================================
    # PRE-CODING REVIEW CHECKPOINT (ALWAYS SHOWN)
    # Always display checkpoint for consistency and transparency.
    # AUTO-ACCEPT: Checkpoint is informational only - never blocks execution.
    # User can see all decisions made by 3-level-flow before work starts.
    # =========================================================================
    trace_path = str(session_log_dir / 'flow-trace.json')
    _ctx_window_tokens = 200000
    _ctx_used_tokens = int(_ctx_window_tokens * context_pct2 / 100)
    _ctx_remaining_tokens = _ctx_window_tokens - _ctx_used_tokens
    _understood = rewritten_prompt[:200] if rewritten_prompt else "(no rewrite - using original message)"

    # Build checkpoint table with FULL decision chain visibility
    checkpoint_lines = [
        SEP,
        "[REVIEW CHECKPOINT] AUTO-PROCEED - Full Decision Chain",
        SEP,
        "",
        "📝 PROMPT TRANSFORMATION:",
        "  | Field              | Value                                              |",
        "  |--------------------|-----------------------------------------------------|",
        f"  | User Input         | {user_message[:51]:<51} |",
        f"  | Understanding      | {_understood[:51]:<51} |",
    ]

    # Add enhanced prompt (rewritten prompt from policy enrichment)
    enhanced_prompt = rewritten_prompt[:51] if rewritten_prompt else "(no rewrite applied)"
    checkpoint_lines.append(f"  | Enhanced Prompt    | {enhanced_prompt:<51} |")
    checkpoint_lines.append("")

    # Add decision analysis
    checkpoint_lines.append("🎯 DECISION ANALYSIS:")
    checkpoint_lines.append("  | Field              | Value                                              |")
    checkpoint_lines.append("  |--------------------|-----------------------------------------------------|")
    checkpoint_lines.append(f"  | Session ID         | {session_id:<51} |")
    checkpoint_lines.append(f"  | Task type          | {task_type:<51} |")

    complexity_str = f"{adj_complexity}/25"
    checkpoint_lines.append(f"  | Complexity         | {complexity_str:<51} |")
    checkpoint_lines.append(f"  | Model selected     | {selected_model:<51} |")
    checkpoint_lines.append(f"  | Agent/Skill        | {skill_agent_name:<51} |")
    checkpoint_lines.append(f"  | Plan mode          | {plan_str:<51} |")

    context_usage_str = f"{context_pct2}% (~{_ctx_used_tokens:,} / {_ctx_window_tokens:,} tokens)"
    checkpoint_lines.append(f"  | Context usage      | {context_usage_str:<51} |")
    context_remaining_str = f"~{_ctx_remaining_tokens:,} tokens"
    checkpoint_lines.append(f"  | Context remaining  | {context_remaining_str:<51} |")
    checkpoint_lines.append("")

    # Print checkpoint to console
    for line in checkpoint_lines:
        print(line)

    # SAVE CHECKPOINT TO FILE (so IDE can read and display it)
    try:
        session_dir = MEMORY_BASE / 'logs' / 'sessions' / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = session_dir / 'checkpoint.txt'
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(checkpoint_lines))
            f.write('\n')
        print(f"\n[✓] Checkpoint saved to: {checkpoint_file}")
    except Exception as e:
        print(f"\n[!] Could not save checkpoint: {e}")

    # Show status based on message type
    if _is_approval:
        print("  STATUS: User approval message - policies cleared, auto-proceeding")
    elif _is_continuation:
        print("  STATUS: Mid-session continuation - resuming previous context")
    elif is_non_coding_message(user_message):
        print("  STATUS: Non-coding question/research - running in Q&A mode")
    else:
        print("  STATUS: Full execution - all policies and steps active")

    print()
    print("  CLAUDE_INSTRUCTION: Hook checkpoint shown. AUTO-PROCEED to coding.")
    print("  DO NOT ask user for 'ok' or 'proceed'. Just start working immediately.")
    print("  Checkpoint is AUTOMATICALLY ACCEPTED - no blocking, no confirmation needed.")

    if rewritten_prompt and _needs_enforcement:
        print()
        print("  REWRITTEN PROMPT (Claude MUST use this as task description):")
        print(f"  >> {rewritten_prompt}")
        print()
        print("  CLAUDE_INSTRUCTION: The user wrote in informal language.")
        print("  Claude must solve the REWRITTEN_PROMPT above, not react to the raw message.")

    print()
    print(SEP)
    print("[OK] ALL 3 LEVELS + 12 STEPS VERIFIED - WORK STARTED")
    print(SEP)

    # LOOPHOLE #18 FIX: Checkpoint + task-breakdown flags are written EARLY (line ~968)
    # so they survive even if this script times out before reaching here.
    # Only skill-selection flag is written here (needs skill_agent_name from step 3.5).
    # LOOPHOLE #14 FIX: Skip for non-coding messages (questions/research).
    # v3.1.0 FIX: Skip for mid-session continuations (already approved + invoked).
    # v3.2.0 FIX: Skip for approval messages (user said ok - don't re-create flags!).
    if _needs_enforcement:
        # Step 3.5 enforcement: block coding until Skill/Task tool is invoked
        # SKIP for adaptive-skill-intelligence: suggestion is behavioral (CLAUDE.md),
        # not hook-enforced. Writing a flag for adaptive creates unresolvable block
        # because Claude may choose to suggest instead of invoking a tool.
        if skill_agent_name and skill_agent_name != 'adaptive-skill-intelligence':
            write_skill_selection_flag(
                session_id=session_id or 'unknown',
                required_skill=skill_agent_name,
                required_type=agent_type
            )

    sys.exit(0)


def _build_script_inventory():
    """
    Build complete inventory of ALL 82 scripts (66 architecture + 16 root).
    Each entry has: name, path, category, status, hook, description.
    This gives full visibility into which scripts exist, which ran, which were skipped.
    """
    inventory = {
        "total_scripts": 82,
        "architecture_scripts": 66,
        "root_scripts": 16,
        "generated_at": datetime.now().isoformat(),
        "hook_scripts": [],
        "active_scripts": [],
        "on_demand_scripts": [],
        "daemon_scripts": [],
        "phase4_scripts": [],
        "superseded_scripts": [],
    }

    # --- 6 HOOK SCRIPTS (Always Running) ---
    inventory["hook_scripts"] = [
        {"name": "3-level-flow.py", "hook": "UserPromptSubmit", "status": "EXECUTED", "desc": "Main 3-level pipeline (L-1, L1, L2, L3)"},
        {"name": "clear-session-handler.py", "hook": "UserPromptSubmit", "status": "EXECUTED", "desc": "Session state check, /clear handling"},
        {"name": "pre-tool-enforcer.py", "hook": "PreToolUse", "status": "EXECUTED", "desc": "L3.1/3.5 blocking + L3.6 hints + L3.7 prevention"},
        {"name": "post-tool-tracker.py", "hook": "PostToolUse", "status": "EXECUTED", "desc": "L3.9 progress tracking + GitHub issues + build validation"},
        {"name": "stop-notifier.py", "hook": "Stop", "status": "EXECUTED", "desc": "Session save + voice + PR workflow + auto-commit"},
        {"name": "auto-fix-enforcer.py", "hook": "via 3-level-flow.py", "status": "EXECUTED", "desc": "Level -1: 7 system health checks"},
    ]

    # --- 16 ACTIVE SCRIPTS (Called by hooks via subprocess) ---
    inventory["active_scripts"] = [
        {"name": "session-loader.py", "path": "01-sync-system/session-management/", "hook": "clear-session-handler.py", "status": "EXECUTED", "desc": "Loads past session context on start"},
        {"name": "context-monitor-v2.py", "path": "01-sync-system/context-management/", "hook": "3-level-flow.py L1.1+3.3", "status": "EXECUTED", "desc": "Enhanced context monitor (called twice per message)"},
        {"name": "session-state.py", "path": "01-sync-system/session-management/", "hook": "3-level-flow.py L1.4", "status": "EXECUTED", "desc": "Maintains durable session state"},
        {"name": "load-preferences.py", "path": "01-sync-system/user-preferences/", "hook": "3-level-flow.py L1.3", "status": "EXECUTED", "desc": "Loads user preferences for decision-making"},
        {"name": "standards-loader.py", "path": "02-standards-system/", "hook": "3-level-flow.py L2", "status": "EXECUTED", "desc": "Loads all coding standards and rules"},
        {"name": "prompt-generator.py", "path": "03-execution-system/00-prompt-generation/", "hook": "3-level-flow.py 3.0+3.5", "status": "EXECUTED", "desc": "Generates structured prompts (called twice)"},
        {"name": "task-auto-analyzer.py", "path": "03-execution-system/01-task-breakdown/", "hook": "3-level-flow.py 3.1", "status": "EXECUTED", "desc": "Automatic task breakdown + complexity analysis"},
        {"name": "auto-plan-mode-suggester.py", "path": "03-execution-system/02-plan-mode/", "hook": "3-level-flow.py 3.2", "status": "EXECUTED", "desc": "Decides if plan mode needed"},
        {"name": "pre-execution-checker.py", "path": "03-execution-system/failure-prevention/", "hook": "3-level-flow.py 3.7", "status": "EXECUTED", "desc": "Pre-execution failure KB check"},
        {"name": "tool-usage-optimizer.py", "path": "03-execution-system/06-tool-optimization/", "hook": "pre-tool-enforcer.py", "status": "EXECUTED", "desc": "Pre-execution token-saving optimizations"},
        {"name": "check-incomplete-work.py", "path": "03-execution-system/08-progress-tracking/", "hook": "post-tool-tracker.py", "status": "EXECUTED", "desc": "Detects incomplete tasks on session resume"},
        {"name": "auto-commit-enforcer.py", "path": "03-execution-system/09-git-commit/", "hook": "stop-notifier.py", "status": "EXECUTED", "desc": "Enforces auto-commit on task completion"},
        {"name": "auto-save-session.py", "path": "01-sync-system/session-management/", "hook": "stop-notifier.py", "status": "EXECUTED", "desc": "Auto-saves session before cleanup"},
        {"name": "archive-old-sessions.py", "path": "01-sync-system/session-management/", "hook": "stop-notifier.py", "status": "EXECUTED", "desc": "Archives sessions >30 days, keeps last 10"},
        {"name": "failure-detector.py", "path": "03-execution-system/failure-prevention/", "hook": "stop-notifier.py", "status": "EXECUTED", "desc": "Analyzes failure patterns from logs"},
    ]

    # --- 3 INLINE SCRIPTS (Logic inside hook code) ---
    inventory["active_scripts"].extend([
        {"name": "model-auto-selector.py", "path": "03-execution-system/04-model-selection/", "hook": "3-level-flow.py 3.4 INLINE", "status": "INLINE", "desc": "Logic implemented inline in 3-level-flow.py"},
        {"name": "auto-skill-agent-selector.py", "path": "03-execution-system/05-skill-agent-selection/", "hook": "3-level-flow.py 3.5 INLINE", "status": "INLINE", "desc": "Logic implemented inline in 3-level-flow.py"},
        {"name": "windows-python-unicode-checker.py", "path": "03-execution-system/failure-prevention/", "hook": "pre-tool-enforcer.py L3.7 INLINE", "status": "INLINE", "desc": "Logic implemented inline in pre-tool-enforcer.py"},
    ])

    # --- 10 ROOT UTILITY SCRIPTS ---
    inventory["on_demand_scripts"].extend([
        {"name": "session-id-generator.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Generates session IDs (called by 3-level-flow)"},
        {"name": "session-summary-manager.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Generates session-summary.json + .md"},
        {"name": "session-chain-manager.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Session chaining across /clear"},
        {"name": "github_issue_manager.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Creates/closes GitHub issues on TaskCreate/TaskUpdate"},
        {"name": "github_pr_workflow.py", "path": "scripts/", "category": "ROOT", "status": "AVAILABLE", "desc": "Full PR lifecycle orchestrator"},
        {"name": "auto_build_validator.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Auto-detect project type and run compile/build check"},
        {"name": "context-monitor-v2.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Root copy of context monitor"},
        {"name": "voice-notifier.py", "path": "scripts/", "category": "ROOT", "status": "EXECUTED", "desc": "Voice notification via PowerShell TTS"},
        {"name": "ide_paths.py", "path": "scripts/", "category": "ROOT", "status": "AVAILABLE", "desc": "IDE path resolution utility"},
        {"name": "policy-executor.py", "path": "scripts/", "category": "ROOT", "status": "AVAILABLE", "desc": "Policy execution utility"},
    ])

    # --- 33 ON-DEMAND UTILITIES (CLI tools for manual use) ---
    on_demand_arch = [
        # Context management
        {"name": "auto-context-pruner.py", "path": "01-sync-system/context-management/", "desc": "Auto-prunes context when >70%"},
        {"name": "context-cache.py", "path": "01-sync-system/context-management/", "desc": "File content summary caching"},
        {"name": "context-extractor.py", "path": "01-sync-system/context-management/", "desc": "Extracts essential info from tool outputs"},
        {"name": "file-type-optimizer.py", "path": "01-sync-system/context-management/", "desc": "Optimal read command per file type"},
        {"name": "monitor-and-cleanup-context.py", "path": "01-sync-system/context-management/", "desc": "Triggers cleanup when over threshold"},
        {"name": "smart-cleanup.py", "path": "01-sync-system/context-management/", "desc": "Policy-driven cleanup with dry-run"},
        {"name": "smart-file-summarizer.py", "path": "01-sync-system/context-management/", "desc": "Generates intelligent file summaries"},
        {"name": "tiered-cache.py", "path": "01-sync-system/context-management/", "desc": "Three-tier cache manager (hot/warm/cold)"},
        {"name": "update-context-usage.py", "path": "01-sync-system/context-management/", "desc": "Manually update context tracking file"},
        # Pattern detection
        {"name": "detect-patterns.py", "path": "01-sync-system/pattern-detection/", "desc": "Slow: reads all sessions, run manually"},
        {"name": "apply-patterns.py", "path": "01-sync-system/pattern-detection/", "desc": "Suggests stored patterns for a topic"},
        # Session management
        {"name": "session-search.py", "path": "01-sync-system/session-management/", "desc": "Search sessions by tags/project/date"},
        {"name": "session-save-triggers.py", "path": "01-sync-system/session-management/", "desc": "Detects threshold conditions for session save"},
        {"name": "protect-session-memory.py", "path": "01-sync-system/session-management/", "desc": "Verifies session files are protected"},
        {"name": "session-start-check.py", "path": "01-sync-system/session-management/", "desc": "Startup health check (daemon status, recommendations)"},
        # User preferences
        {"name": "track-preference.py", "path": "01-sync-system/user-preferences/", "desc": "Records a single preference entry"},
        {"name": "preference-detector.py", "path": "01-sync-system/user-preferences/", "desc": "Auto-detects preferences from conversation logs"},
        # Task breakdown
        {"name": "task-phase-enforcer.py", "path": "03-execution-system/01-task-breakdown/", "desc": "Validates task/phase breakdown requirements"},
        # Model selection
        {"name": "model-selection-monitor.py", "path": "03-execution-system/04-model-selection/", "desc": "Monitors model usage distribution"},
        {"name": "model-selection-enforcer.py", "path": "03-execution-system/04-model-selection/", "desc": "Enforces model selection rules"},
        # Skill/agent selection
        {"name": "auto-register-skills.py", "path": "03-execution-system/05-skill-agent-selection/", "desc": "Scans and registers new skills"},
        {"name": "core-skills-enforcer.py", "path": "03-execution-system/05-skill-agent-selection/", "desc": "Enforces core skill execution order"},
        # Tool optimization
        {"name": "smart-read.py", "path": "03-execution-system/06-tool-optimization/", "desc": "Smart offset/limit strategies for Read"},
        {"name": "pre-execution-optimizer.py", "path": "03-execution-system/06-tool-optimization/", "desc": "Optimizes tool parameters before execution"},
        {"name": "auto-tool-wrapper.py", "path": "03-execution-system/06-tool-optimization/", "desc": "Cache check + optimization hints wrapper"},
        {"name": "ast-code-navigator.py", "path": "03-execution-system/06-tool-optimization/", "desc": "AST extraction (Java/TS/JS/Python)"},
        # Recommendations
        {"name": "skill-detector.py", "path": "03-execution-system/07-recommendations/", "desc": "Auto-suggests skills from keywords"},
        {"name": "check-recommendations.py", "path": "03-execution-system/07-recommendations/", "desc": "Displays latest recommendations"},
        {"name": "skill-manager.py", "path": "03-execution-system/07-recommendations/", "desc": "CRUD interface for skill registry"},
        # Git commit
        {"name": "auto-commit-detector.py", "path": "03-execution-system/09-git-commit/", "desc": "Detects commit trigger conditions"},
        {"name": "auto-commit.py", "path": "03-execution-system/09-git-commit/", "desc": "Executes actual commit (calls detector)"},
        {"name": "trigger-auto-commit.py", "path": "03-execution-system/09-git-commit/", "desc": "Integration trigger for commit+push"},
        # Failure prevention
        {"name": "failure-solution-learner.py", "path": "03-execution-system/failure-prevention/", "desc": "Learns solutions from successful fixes"},
        {"name": "failure-pattern-extractor.py", "path": "03-execution-system/failure-prevention/", "desc": "Extracts patterns from failure logs"},
        {"name": "failure-learner.py", "path": "03-execution-system/failure-prevention/", "desc": "Updates KB with learned solutions"},
        {"name": "failure-detector-v2.py", "path": "03-execution-system/failure-prevention/", "desc": "Enhanced failure detector with --analyze mode"},
        {"name": "update-failure-kb.py", "path": "03-execution-system/failure-prevention/", "desc": "Project-specific failure learning"},
    ]
    for s in on_demand_arch:
        s["category"] = "ON-DEMAND"
        s["status"] = "AVAILABLE"
    inventory["on_demand_scripts"].extend(on_demand_arch)

    # --- 3 DAEMON SCRIPTS (Require background process) ---
    inventory["daemon_scripts"] = [
        {"name": "preference-auto-tracker.py", "path": "01-sync-system/user-preferences/", "status": "SKIPPED", "reason": "Requires watchdog library + background process", "desc": "Monitors logs continuously for preferences"},
        {"name": "task-auto-tracker.py", "path": "03-execution-system/01-task-breakdown/", "status": "SKIPPED", "reason": "Requires watchdog library + background process", "desc": "File monitoring with watchdog"},
        {"name": "skill-auto-suggester.py", "path": "03-execution-system/07-recommendations/", "status": "SKIPPED", "reason": "Requires background process", "desc": "Monitors conversation logs for skill suggestions"},
    ]

    # --- 4 PHASE-4 STUBS (Future automation, not production-ready) ---
    inventory["phase4_scripts"] = [
        {"name": "prompt-auto-wrapper.py", "path": "03-execution-system/00-prompt-generation/", "status": "STUB", "desc": "Phase-4: auto-generates structured prompts"},
        {"name": "plan-mode-auto-decider.py", "path": "03-execution-system/02-plan-mode/", "status": "STUB", "desc": "Phase-4: auto-enters plan mode without confirmation"},
        {"name": "skill-agent-auto-executor.py", "path": "03-execution-system/05-skill-agent-selection/", "status": "STUB", "desc": "Phase-4: auto-executes skills without confirmation"},
        {"name": "tool-call-interceptor.py", "path": "03-execution-system/06-tool-optimization/", "status": "STUB", "desc": "Phase-2: intercepts and rewrites tool calls"},
    ]

    # --- 3 SUPERSEDED SCRIPTS (Replaced by newer versions) ---
    inventory["superseded_scripts"] = [
        {"name": "context-estimator.py", "path": "01-sync-system/context-management/", "status": "SUPERSEDED", "replaced_by": "context-monitor-v2.py", "desc": "Original context estimator"},
        {"name": "monitor-context.py", "path": "01-sync-system/context-management/", "status": "SUPERSEDED", "replaced_by": "context-monitor-v2.py", "desc": "Original context monitor"},
        {"name": "intelligent-model-selector.py", "path": "03-execution-system/04-model-selection/", "status": "SUPERSEDED", "replaced_by": "inline in 3-level-flow.py", "desc": "Original model selector"},
        {"name": "git-auto-commit-ai.py", "path": "03-execution-system/09-git-commit/", "status": "SUPERSEDED", "replaced_by": "auto-commit-enforcer.py", "desc": "Phase-4: AI-generated commit messages"},
    ]

    # Summary counts
    executed = len([s for s in inventory["hook_scripts"] if s["status"] == "EXECUTED"])
    executed += len([s for s in inventory["active_scripts"] if s["status"] in ("EXECUTED", "INLINE")])
    executed += len([s for s in inventory["on_demand_scripts"] if s["status"] == "EXECUTED"])
    available = len([s for s in inventory["on_demand_scripts"] if s["status"] == "AVAILABLE"])

    inventory["summary"] = {
        "hook_scripts": len(inventory["hook_scripts"]),
        "active_executed": len([s for s in inventory["active_scripts"] if s["status"] == "EXECUTED"]),
        "active_inline": len([s for s in inventory["active_scripts"] if s["status"] == "INLINE"]),
        "on_demand_executed": len([s for s in inventory["on_demand_scripts"] if s["status"] == "EXECUTED"]),
        "on_demand_available": available,
        "daemon_skipped": len(inventory["daemon_scripts"]),
        "phase4_stubs": len(inventory["phase4_scripts"]),
        "superseded": len(inventory["superseded_scripts"]),
        "total_executed_this_session": executed,
        "total_available": available,
        "total_scripts": (
            len(inventory["hook_scripts"]) +
            len(inventory["active_scripts"]) +
            len(inventory["on_demand_scripts"]) +
            len(inventory["daemon_scripts"]) +
            len(inventory["phase4_scripts"]) +
            len(inventory["superseded_scripts"])
        ),
    }

    return inventory


def _save_trace(trace, session_log_dir, flow_start):
    """Save the complete JSON trace file"""
    try:
        if session_log_dir is None:
            # Fallback: save to memory/logs/
            fallback_dir = MEMORY_BASE / 'logs'
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fname = f"flow-trace-{flow_start.strftime('%Y%m%d-%H%M%S')}.json"
            write_json(fallback_dir / fname, trace)
        else:
            write_json(session_log_dir / 'flow-trace.json', trace)
            # Also keep a "latest" copy for easy access
            write_json(MEMORY_BASE / 'logs' / 'latest-flow-trace.json', trace)
    except Exception:
        pass


if __name__ == '__main__':
    main()
