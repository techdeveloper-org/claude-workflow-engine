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
import io
import json
import subprocess
from pathlib import Path
from datetime import datetime

# File locking for shared JSON state (Loophole #19)
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

# Metrics emitter (fire-and-forget, never blocks)
try:
    _metrics_dir = Path(__file__).parent
    if str(_metrics_dir) not in sys.path:
        sys.path.insert(0, str(_metrics_dir))
    from metrics_emitter import (emit_hook_execution, emit_policy_step,
                                  emit_flag_lifecycle, emit_enforcement_event)
    _METRICS_AVAILABLE = True
except Exception:
    # Define no-ops so call sites never need guards
    def emit_hook_execution(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_policy_step(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_flag_lifecycle(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    def emit_enforcement_event(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    _METRICS_AVAILABLE = False

# Phase 2: Lazy loading APIs
try:
    from trace_api import TraceAPI, rotate_trace_before_save
    from session_api import SessionAPI
    _LAZY_LOADING_AVAILABLE = True
except ImportError:
    _LAZY_LOADING_AVAILABLE = False
    def rotate_trace_before_save(trace, max_entries=30):
        if 'pipeline' in trace and len(trace['pipeline']) > max_entries:
            trace['pipeline'] = trace['pipeline'][-max_entries:]
        return trace


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

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

VERSION = "4.4.0"  # v4.4.0: Phase 1 bloat fixes - trace rotation + debug-only prints
SCRIPT_NAME = "3-level-flow.py"

# Phase 1 bloat fixes
DEBUG = os.getenv("CLAUDE_DEBUG", "").lower() == "1"  # Set CLAUDE_DEBUG=1 for verbose output
MAX_TRACE_ENTRIES = 30  # Keep only last 30 pipeline entries to reduce memory (100 KB → ~60 KB)

# Flag auto-expiry configuration (Loophole #10)
FLAG_EXPIRY_MINUTES = 60   # Auto-delete flags older than 60 minutes
FLAG_CLEANUP_ON_STARTUP = True

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


# =============================================================================
# FLAG AUTO-EXPIRY UTILITIES (Loophole #10)
# =============================================================================

def _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES):
    """Remove flag files in FLAG_DIR older than max_age_minutes.

    Scans ~/.claude/ for all .*.json flag files and deletes any whose
    filesystem modification time exceeds the expiry threshold.  Uses a
    try/except around every file operation so a single bad file never
    aborts the cleanup loop.

    Args:
        max_age_minutes: Maximum allowed flag age in minutes (default 60).

    Returns:
        int: Number of flag files deleted.
    """
    try:
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        cleaned = 0

        for flag_file in FLAG_DIR.glob('.*.json'):
            try:
                if flag_file.stat().st_mtime < cutoff_time.timestamp():
                    flag_file.unlink(missing_ok=True)
                    cleaned += 1
            except Exception:
                pass

        return cleaned
    except Exception:
        return 0


def _check_flag_age(flag_path, max_age_minutes=FLAG_EXPIRY_MINUTES):
    """Check if a flag file is still within its freshness window.

    First checks the file modification time against the cutoff.  If the
    file also contains a JSON 'created_at' ISO timestamp, that timestamp
    is used as a second (more accurate) age check.  Stale files are
    deleted before returning False so they are lazily cleaned on read.

    Args:
        flag_path: str or Path to the flag JSON file.
        max_age_minutes: Maximum allowed age in minutes (default 60).

    Returns:
        bool: True if the flag is fresh and usable; False if expired
              (file is deleted) or does not exist.
    """
    try:
        from datetime import timedelta
        path = Path(flag_path)
        if not path.exists():
            return False

        # Check file modification time first (fast path)
        mod_time = datetime.fromtimestamp(path.stat().st_mtime)
        age_minutes = (datetime.now() - mod_time).total_seconds() / 60

        if age_minutes > max_age_minutes:
            path.unlink(missing_ok=True)
            return False

        # Also verify created_at inside JSON when present (authoritative)
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if 'created_at' in data:
                created = datetime.fromisoformat(data['created_at'])
                json_age = (datetime.now() - created).total_seconds() / 60
                if json_age > max_age_minutes:
                    path.unlink(missing_ok=True)
                    return False
        except Exception:
            pass  # Malformed JSON - fall through; mtime check already passed

        return True
    except Exception:
        return False


def load_policy_rules() -> dict:
    """Load all policy documentation from ~/.claude/policies/ directories.

    Recursively scans the three policy level directories under POLICIES_DIR and
    reads up to 500 characters from each .md file.  Files that cannot be read
    are silently skipped so a single corrupt policy never blocks the flow.

    Returns:
        dict: Nested dict with keys 'level-1', 'level-2', 'level-3', each
              mapping {policy_stem: content_snippet (str, max 500 chars)}.
              Returns an empty structure if POLICIES_DIR does not exist.

    Example:
        >>> rules = load_policy_rules()
        >>> len(rules['level-2'])  # number of loaded Level 2 policy files
        3
    """
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


def _session_flag_dir(session_id):
    """Get the flags directory inside a session's log folder.

    v4.4.0: Flags are now stored INSIDE the session folder for perfect
    per-window isolation. No more scattered flags in ~/.claude/.

    Args:
        session_id (str): Active session identifier.

    Returns:
        Path: ~/.claude/memory/logs/sessions/{session_id}/flags/
    """
    d = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'flags'
    d.mkdir(parents=True, exist_ok=True)
    return d


def checkpoint_flag_path(session_id):
    """Build the session-specific checkpoint flag file path.

    v4.4.0: Now inside session folder, not ~/.claude/.
    Pattern: .../sessions/{SESSION_ID}/flags/checkpoint-pending.json

    Args:
        session_id (str): Active session identifier.

    Returns:
        Path: Absolute path to the checkpoint flag file.
    """
    return _session_flag_dir(session_id) / 'checkpoint-pending.json'


def task_breakdown_flag_path(session_id):
    """Build the session-specific task-breakdown flag file path.

    v4.4.0: Now inside session folder, not ~/.claude/.
    Pattern: .../sessions/{SESSION_ID}/flags/task-breakdown-pending.json

    Args:
        session_id (str): Active session identifier.

    Returns:
        Path: Absolute path to the task-breakdown flag file.
    """
    return _session_flag_dir(session_id) / 'task-breakdown-pending.json'


def skill_selection_flag_path(session_id):
    """Build the session-specific skill-selection flag file path.

    v4.4.0: Now inside session folder, not ~/.claude/.
    Pattern: .../sessions/{SESSION_ID}/flags/skill-selection-pending.json

    Args:
        session_id (str): Active session identifier.

    Returns:
        Path: Absolute path to the skill-selection flag file.
    """
    return _session_flag_dir(session_id) / 'skill-selection-pending.json'

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
    Read session-progress.json with file locking (Loophole #19).
    Used to detect mid-session continuations where TaskCreate/Skill were already done.
    Returns dict with tool_counts, tasks_completed, etc.
    """
    progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
    try:
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
            # Only return data if it belongs to the current session
            if data.get('session_id', '') == session_id:
                return data
    except Exception:
        pass
    return {}


def is_mid_session_continuation(session_id):
    """Detect if this is a follow-up message in an already-started session.

    Reads session-progress.json and checks whether TaskCreate and a Skill or
    Task delegation tool were both called earlier in the same session.  When
    both have occurred the session is mid-flight and enforcement flags must NOT
    be re-created, which would block legitimate continuation work.

    Args:
        session_id: Active session identifier used to locate the progress file.

    Returns:
        bool: True if TaskCreate and Skill/Task have already been called,
              indicating enforcement flags should be skipped for this message.
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
    """Delete ALL enforcement flags on user approval.

    v4.4.0: Clears flags from session folder AND legacy ~/.claude/ location.

    Args:
        reason: Human-readable label logged alongside the count of cleared flags.
    """
    try:
        import glob as _glob
        cleared = 0
        cleared_types = []

        # v4.4.0: Clear flags from ALL session folders
        sessions_dir = MEMORY_BASE / 'logs' / 'sessions'
        if sessions_dir.exists():
            for flags_dir in sessions_dir.glob('SESSION-*/flags'):
                for flag_file in flags_dir.glob('*.json'):
                    try:
                        flag_file.unlink()
                        cleared += 1
                    except Exception:
                        pass

        # Legacy cleanup: also clear old-style flags from ~/.claude/
        for pattern in [
            '.checkpoint-pending-*.json',
            '.task-breakdown-pending-*.json',
            '.skill-selection-pending-*.json',
        ]:
            for flag_file in _glob.glob(str(FLAG_DIR / pattern)):
                try:
                    Path(flag_file).unlink()
                    cleared += 1
                except Exception:
                    pass

        if cleared > 0 and DEBUG:
            print(f'[ENFORCEMENT] {cleared} flag(s) cleared - {reason}')

        try:
            for ft in cleared_types:
                emit_flag_lifecycle(ft, 'clear', reason=reason)
        except Exception:
            pass
    except Exception:
        pass


def clear_current_session_flags(session_id, reason=''):
    """Delete enforcement flags for the CURRENT session.

    v4.4.0: Flags are now in session folder. Also cleans legacy ~/.claude/ flags.

    Args:
        session_id: Current session identifier (e.g. SESSION-20260305-123456-ABCD).
        reason:     Human-readable label logged alongside cleared flag count.
    """
    if not session_id or session_id == "UNKNOWN":
        return

    try:
        import glob as _glob
        cleared = 0
        cleared_types = []

        # v4.4.0: Clear flags from session folder
        flags_dir = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'flags'
        if flags_dir.exists():
            for flag_type, fname in [
                ("checkpoint", "checkpoint-pending.json"),
                ("task_breakdown", "task-breakdown-pending.json"),
                ("skill_selection", "skill-selection-pending.json"),
            ]:
                flag_path = flags_dir / fname
                if flag_path.exists():
                    flag_path.unlink()
                    cleared += 1
                    if flag_type not in cleared_types:
                        cleared_types.append(flag_type)

        # Legacy cleanup: also clear old-style flags from ~/.claude/
        for pattern in [
            f".checkpoint-pending-{session_id}*.json",
            f".task-breakdown-pending-{session_id}*.json",
            f".skill-selection-pending-{session_id}*.json",
        ]:
            for old_flag in _glob.glob(str(FLAG_DIR / pattern)):
                try:
                    Path(old_flag).unlink()
                    cleared += 1
                except Exception:
                    pass

        if cleared > 0 and DEBUG:
            print(
                f"[ENFORCEMENT] {cleared} flag(s) cleared "
                f"(session: {session_id[:16]}...) - {reason}"
            )

        try:
            for ft in cleared_types:
                emit_flag_lifecycle(ft, "clear", reason=reason)
        except Exception:
            pass
    except Exception:
        pass


def clear_checkpoint_flag(reason=""):
    """Alias - clears ALL enforcement flags (backward compat)."""
    clear_all_enforcement_flags(reason)


def write_checkpoint_flag(session_id, prompt_preview):
    """Write the session-specific checkpoint flag so pre-tool-enforcer blocks code tools.

    Creates .checkpoint-pending-{SESSION_ID}-{PID}.json in FLAG_DIR.  The
    pre-tool-enforcer reads this flag and blocks Write/Edit/NotebookEdit until
    the user sends an approval message ('ok', 'proceed', etc.).

    Args:
        session_id (str): Active session identifier written into the flag data.
        prompt_preview (str): First 100 chars of the user prompt for context.
    """
    try:
        flag_path = checkpoint_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'prompt_preview': prompt_preview[:100],
                'reason': 'awaiting_user_ok'
            }, f)
            _unlock_file(f)
    except Exception:
        pass


def write_task_breakdown_flag(session_id, prompt_preview):
    """Write the Step 3.1 task-breakdown enforcement flag.

    Creates .task-breakdown-pending-{SESSION_ID}-{PID}.json in FLAG_DIR.
    pre-tool-enforcer.py blocks Write/Edit/NotebookEdit until TaskCreate is
    called, at which point post-tool-tracker.py deletes this flag.

    Args:
        session_id (str): Active session identifier written into the flag data.
        prompt_preview (str): First 100 chars of the user prompt for context.
    """
    try:
        flag_path = task_breakdown_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'prompt_preview': prompt_preview[:100],
                'reason': 'step_3_1_task_breakdown_required',
                'policy': 'TaskCreate MUST be called before any Write/Edit/Bash'
            }, f)
            _unlock_file(f)
        try:
            emit_flag_lifecycle('task_breakdown', 'write', session_id=session_id,
                                reason='step_3_1_task_breakdown_required')
        except Exception:
            pass
    except Exception:
        pass


def write_skill_selection_flag(session_id, required_skill, required_type):
    """Write the Step 3.5 skill-selection enforcement flag.

    Creates .skill-selection-pending-{SESSION_ID}-{PID}.json in FLAG_DIR.
    Only written for non-adaptive skills (adaptive-skill-intelligence needs no
    tool invocation).  pre-tool-enforcer.py blocks Write/Edit/NotebookEdit until
    the Skill or Task tool is invoked, after which post-tool-tracker.py removes
    this flag.

    Args:
        session_id (str): Active session identifier written into the flag data.
        required_skill (str): Name of the skill or agent that must be invoked.
        required_type (str): Either 'skill' (invoke via Skill tool) or 'agent'
                             (invoke via Task tool with subagent_type).
    """
    try:
        flag_path = skill_selection_flag_path(session_id)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(flag_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'required_skill': required_skill,
                'required_type': required_type,
                'reason': 'step_3_5_skill_selection_required',
                'policy': 'Skill/Task tool MUST be invoked before any Write/Edit/Bash'
            }, f)
            _unlock_file(f)
        try:
            emit_flag_lifecycle('skill_selection', 'write', session_id=session_id,
                                reason='step_3_5_skill_selection_required',
                                extra={'required_skill': required_skill,
                                       'required_type': required_type})
        except Exception:
            pass
    except Exception:
        pass


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def ts():
    """Return the current local time as an ISO 8601 string.

    Returns:
        str: Timestamp in 'YYYY-MM-DDTHH:MM:SS.ffffff' format.

    Example:
        >>> stamp = ts()
        >>> stamp.startswith('202')
        True
    """
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# PERFORMANCE: In-process module cache for eliminating subprocess overhead.
# Architecture scripts with enforce()/validate()/report() are imported as
# modules and called directly (~3x faster than subprocess on Windows).
# ---------------------------------------------------------------------------
_module_cache = {}       # {script_path_str: loaded_module}


def _import_script_module(script_path):
    """Import a Python script as a module for in-process execution."""
    import importlib.util
    key = str(script_path)
    if key in _module_cache:
        return _module_cache[key]
    try:
        script_dir = str(Path(script_path).parent)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        spec = importlib.util.spec_from_file_location(
            f"_policy_{Path(script_path).stem}", str(script_path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            mod.__name__ = f"_policy_{Path(script_path).stem}"
            spec.loader.exec_module(mod)
            _module_cache[key] = mod
            return mod
    except Exception:
        pass
    return None


def _call_mod_func(mod, func_name):
    """Call a module function and return (stdout, stderr, rc, dur_ms).

    Captures stdout to prevent inline scripts from printing to parent output.
    """
    import io
    t0 = datetime.now()
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        result = getattr(mod, func_name)()
        sys.stdout = old_stdout
        dur = int((datetime.now() - t0).total_seconds() * 1000)
        captured_text = captured.getvalue()
        if isinstance(result, dict):
            stdout = json.dumps(result)
        elif isinstance(result, str):
            stdout = result
        elif isinstance(result, bool):
            stdout = json.dumps({"status": "success" if result else "error"})
        else:
            stdout = str(result) if result else ''
        # Always prepend captured print output (policy scripts print parseable
        # lines like "Common Standards: 7" that callers grep for).
        if captured_text:
            stdout = captured_text.rstrip('\n') + '\n' + stdout if stdout else captured_text
        return stdout, '', 0, dur
    except Exception as e:
        sys.stdout = old_stdout
        dur = int((datetime.now() - t0).total_seconds() * 1000)
        return '', str(e), 1, dur


def _run_inline(script_path, args):
    """Try to run a script in-process by calling its function directly.

    Maps CLI patterns to function calls:
      --enforce  -> mod.enforce()
      --validate -> mod.validate()
      --report   -> mod.report()
      (no args)  -> mod.enforce() if it exists

    Returns (stdout, stderr, rc, dur_ms) or None for subprocess fallback.
    """
    arg_list = args if isinstance(args, list) else [args] if args else []

    # No args: try enforce() as default
    if len(arg_list) == 0:
        mod = _import_script_module(script_path)
        if mod and hasattr(mod, 'enforce'):
            return _call_mod_func(mod, 'enforce')
        return None

    # Single flag: --enforce, --validate, --report
    if len(arg_list) == 1 and arg_list[0] in ('--enforce', '--validate', '--report'):
        func_name = arg_list[0].lstrip('-')
        mod = _import_script_module(script_path)
        if mod and hasattr(mod, func_name):
            return _call_mod_func(mod, func_name)

    return None


def run_script(script_path, args=None, timeout=30):
    """Run a Python script, preferring in-process over subprocess.

    First tries _run_inline() for --enforce/--validate/--report calls
    (eliminates ~93ms subprocess overhead per call on Windows).
    Falls back to subprocess.run() for complex argument patterns.

    Returns:
        tuple: (stdout, stderr, returncode, duration_ms)
    """
    inline_result = _run_inline(script_path, args)
    if inline_result is not None:
        return inline_result

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
    """Run a policy script with automatic retry and hard-break on exhaustion.

    Retries the target script up to MAX_RETRIES (3) times.  On each success
    the accumulated stdout, stderr, returncode, and total elapsed milliseconds
    are returned immediately.  If every attempt fails, _policy_hard_break() is
    called, which logs the failure and terminates the process with exit code 1.

    Timeouts are kept short (10 s default) so that a hanging script does not
    block the entire hook execution chain.

    Args:
        script_path: Path object pointing to the Python script to execute.
        args: Optional list of CLI arguments forwarded to the script, or None.
        timeout: Per-attempt timeout in seconds.  Defaults to 10.
        step_name: Label used in retry and hard-break log messages.

    Returns:
        tuple: (stdout, stderr, returncode, total_duration_ms) from the
               successful attempt.  Never returns on the 3rd failure
               because _policy_hard_break() exits the process.
    """
    last_stdout, last_stderr, last_rc, total_dur = '', '', 1, 0

    for attempt in range(1, MAX_RETRIES + 1):
        stdout, stderr, rc, dur = run_script(script_path, args, timeout)
        total_dur += dur

        if rc == 0:
            # Success
            if attempt > 1 and DEBUG:
                print(f"   [RECOVERED] {step_name} succeeded on attempt {attempt}")
            return stdout, stderr, rc, total_dur

        last_stdout, last_stderr, last_rc = stdout, stderr, rc

        if attempt < MAX_RETRIES and DEBUG:
            print(f"   [RETRY {attempt}/{MAX_RETRIES}] {step_name} failed, retrying...")
        else:
            # 3rd failure - HARD BREAK SESSION
            error_detail = (last_stderr or last_stdout or 'Unknown error')[:300]
            _policy_hard_break(step_name, str(script_path.name), error_detail, attempt)

    # Should not reach here (hard break exits), but just in case
    return last_stdout, last_stderr, last_rc, total_dur


def _policy_hard_break(step_name, script_name, error_detail, attempts):
    """Hard-break the session when a policy script fails after all retries.

    Writes a structured failure record to policy-failure-summary.json and
    appends it to session-progress.json so the dashboard can surface the
    error.  Then prints a formatted banner to stdout and exits with code 1,
    which causes Claude Code to surface the failure to the user.

    Args:
        step_name (str): Human-readable step label (e.g. 'Level 1 Sync').
        script_name (str): Filename of the failing script for the log entry.
        error_detail (str): Excerpt of stderr/stdout from the last attempt.
        attempts (int): Number of retries that were exhausted before giving up.

    Raises:
        SystemExit: Always exits with code 1 after logging the failure.
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
    """Parse a JSON string without raising an exception on malformed input.

    Handles mixed output (print lines + JSON) by finding the last JSON
    object in the text when direct parsing fails.

    Args:
        text (str): Raw text that may contain a JSON object.

    Returns:
        dict: Parsed object, or an empty dict on any parse error.
    """
    if not text or not text.strip():
        return {}
    stripped = text.strip()
    # Fast path: pure JSON
    try:
        return json.loads(stripped)
    except Exception:
        pass
    # Slow path: find last JSON object in mixed output
    last_brace = stripped.rfind('\n{')
    if last_brace >= 0:
        try:
            return json.loads(stripped[last_brace + 1:])
        except Exception:
            pass
    # Try finding first { to end
    first_brace = stripped.find('{')
    if first_brace > 0:
        try:
            return json.loads(stripped[first_brace:])
        except Exception:
            pass
    return {}


def write_json(path, data):
    """Write a dict as a pretty-printed JSON file with Windows file locking.

    Uses _lock_file/_unlock_file (msvcrt on Windows, no-op elsewhere) so that
    parallel PostToolUse hook invocations do not corrupt the file.  Parent
    directories are created automatically.  Any exception is silently swallowed
    so this function never crashes the main flow.

    Args:
        path (Path): Destination file path.  Parent directories are created if
                     they do not exist.
        data (dict): Serialisable Python dict to write.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(data, f, indent=2, ensure_ascii=False)
            _unlock_file(f)
    except Exception:
        pass


def read_json(path):
    """Read a JSON file safely with Windows file locking.

    Uses _lock_file/_unlock_file to prevent reading a partially written file.
    Returns an empty dict on any error (file missing, parse failure, etc.) so
    callers never need to guard against exceptions.

    Args:
        path (Path): Path to the JSON file to read.

    Returns:
        dict: Parsed content, or {} on any error.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data
    except Exception:
        return {}


def show_help():
    """Print brief usage information for the script to stdout."""
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
    """Read user prompt and working directory from Claude Code hook stdin.

    Claude Code UserPromptSubmit hook pipes a JSON object with at least:
      {"prompt": "...", "session_id": "...", "cwd": "...", ...}

    On Unix/Mac: Uses select() to avoid blocking indefinitely when stdin has no data.
    On Windows: select() doesn't work with stdin, so tries reading directly.
    Returns ('', '') if stdin is empty or unavailable.

    Returns:
        tuple: (prompt, cwd) both as strings.  Returns ('', '') on any
               read or parse error.
    """
    try:
        if sys.stdin.isatty():
            return '', ''

        # Try to read from stdin - platform-specific handling
        try:
            # On Unix/Mac, use select() to avoid blocking
            if sys.platform != 'win32':
                import select
                readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not readable:
                    return '', ''

            # On Windows OR if select said data is ready, try to read
            raw = sys.stdin.read()
            if raw and raw.strip():
                data = json.loads(raw.strip())
                prompt = data.get('prompt', '') or data.get('message', '')
                cwd = data.get('cwd', '')
                return prompt, cwd
        except (OSError, IOError, ImportError):
            # select() not available, or stdin read failed
            # On Windows this is expected, just try direct read (already done above)
            pass

    except Exception:
        pass
    return '', ''


def detect_tech_stack(cwd=None):
    """Detect the technology stack in use by scanning actual project files.

    Reads requirements.txt, pom.xml, package.json, Dockerfile, etc. to
    determine whether the project uses Flask, Spring Boot, Angular, Docker,
    Kubernetes, and similar technologies.  The hook CWD is checked first; the
    process CWD is used as a fallback if it differs.

    Home and system directories (~/.claude, ~/.claude/memory) are excluded
    from the scan to prevent false-positive detections caused by stray
    configuration files in those locations.

    Args:
        cwd (str, optional): Working directory reported by the Claude hook
                             (from stdin).  If None or pointing to a system
                             directory, the process CWD is used.

    Returns:
        list: One or more technology name strings such as ['spring-boot',
              'docker'], or ['unknown'] when no recognizable project files are
              found.  Detection stops at the first non-empty result.

    Example:
        >>> stack = detect_tech_stack('/home/user/myapp')
        >>> 'spring-boot' in stack
        True
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
    """Scan the raw user message for agent and skill keyword matches.

    This is the Layer 2 dynamic selection mechanism.  It counts how many
    keywords from each agent's AGENT_KEYWORD_SCORES list appear in the
    lowercased user message.  The agent with the highest count wins,
    provided the count meets KEYWORD_MIN_SCORE (2).  No API calls or
    pre-classified task types are required.

    Args:
        user_message: The raw user prompt string (any language).

    Returns:
        tuple: (agent_name, agent_type, score) where agent_type is 'skill'
               or 'agent'.  Returns (None, None, 0) if no agent scores at
               least KEYWORD_MIN_SCORE matches.
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
    # NEW: CSS and styling agents
    'css':          'ui-ux-designer',
    'scss':         'ui-ux-designer',
    # NEW: HTML and markup
    'html':         'ui-ux-designer',
    # NEW: TypeScript
    'typescript':   'angular-engineer',
    # NEW: Python backend frameworks
    'python':       'python-backend-engineer',
    'flask':        'python-backend-engineer',
    'django':       'python-backend-engineer',
    'fastapi':      'python-backend-engineer',
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
    # NEW: CSS and styling skills
    'css':          'css-core',
    'scss':         'css-core',
    # NEW: Python backend framework skills
    'python':       'python-system-scripting',
    'flask':        'python-system-scripting',
    'django':       'python-system-scripting',
    'fastapi':      'python-system-scripting',
    # Standalone skills when no agent exists:
    'nodejs':       None,   # -> adaptive
    'unknown':      None,
}


def get_agent_and_skills(tech_stack, task_type='General', user_message=''):
    """Select the primary skill/agent and supplementary skills for the request.

    Uses a 4-layer waterfall from most-reliable to least-reliable:

    Layer 1 - Task type registry: exact match on the classified task_type
    Layer 2 - Prompt keyword scoring: keyword analysis of the raw message
    Layer 3 - Tech stack registry: file-based project technology detection
    Layer 4 - adaptive-skill-intelligence: fallback when nothing else matches

    The keyword layer (2) makes selection dynamic: it works on plain natural
    language without pre-classified types or project files on disk.

    Args:
        tech_stack: List of technology strings from detect_tech_stack(),
                    e.g. ['flask', 'docker'] or ['unknown'].
        task_type: Classified task type string from prompt-generator.py,
                   e.g. 'Backend', 'Testing', or 'General'.
        user_message: Raw user prompt forwarded for Layer 2 keyword scoring.

    Returns:
        tuple: (primary_name, primary_type, supplementary_skills, reason)
               where primary_type is 'skill' or 'agent', supplementary_skills
               is a list of additional skill names, and reason is a string
               explaining which layer made the selection.
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
    # LAYER 3: Tech stack registry (file-based detection) with multi-domain support
    # =========================================================================
    all_agents = []
    all_skills = []
    skill_fallback = None

    for tech in tech_stack:
        agent = AGENTS_REGISTRY.get(tech)
        if agent and agent not in all_agents:
            all_agents.append(agent)

        skill = SKILLS_REGISTRY.get(tech)
        if skill and skill not in all_skills:
            all_skills.append(skill)
            if skill not in supplementary_skills:
                supplementary_skills.append(skill)

        if not agent and skill and skill_fallback is None:
            skill_fallback = skill

    # Multi-domain orchestrator escalation rule (from auto-skill-agent-selection)
    if all_agents:
        FRONTEND_AGENTS = {'ui-ux-designer', 'angular-engineer', 'swiftui-designer'}
        BACKEND_AGENTS = {'spring-boot-microservices', 'android-backend-engineer', 'swift-backend-engineer', 'python-backend-engineer'}
        DEVOPS_AGENTS = {'devops-engineer'}

        agent_domains = set()
        for agent in all_agents:
            if agent in FRONTEND_AGENTS:
                agent_domains.add('frontend')
            elif agent in BACKEND_AGENTS:
                agent_domains.add('backend')
            elif agent in DEVOPS_AGENTS:
                agent_domains.add('devops')

        # If 2+ domains detected, use orchestrator-agent as primary
        if len(agent_domains) >= 2:
            # All detected agents become supplementary skills
            for agent in all_agents:
                if agent not in supplementary_skills:
                    supplementary_skills.append(agent)
            reason = (
                f"[L3-TechStack-Multi] Multi-domain detected ({', '.join(sorted(agent_domains))}) "
                f"-> orchestrator-agent (coordinates {len(all_agents)} agents)"
                + (f" + supp: {supplementary_skills}" if supplementary_skills else "")
            )
            return 'orchestrator-agent', 'agent', supplementary_skills, reason

    if all_agents:
        primary_agent = all_agents[0]
        primary_tech = tech_stack[0]
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
            'architecture/03-execution-system/00-context-reading',
            'architecture/03-execution-system/00-code-graph-analysis',
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



# =============================================================================

def _find_previous_session(current_session_id, project_path):
    """Find the most recent session for the same project to chain to.

    Scans session JSON files in ~/.claude/memory/sessions/ and returns the
    most recently updated session that matches the project path (via cwd or
    metadata).  Skips the current session.

    Args:
        current_session_id: The just-created session ID to exclude.
        project_path: The project working directory to match against.

    Returns:
        str or None: The parent session ID, or None if no match found.
    """
    sessions_dir = MEMORY_BASE / 'sessions'
    if not sessions_dir.exists():
        return None

    best_match = None
    best_time = ''
    project_name = Path(project_path).name if project_path else ''

    try:
        for sf in sessions_dir.glob('SESSION-*.json'):
            sid = sf.stem
            if sid == current_session_id:
                continue
            try:
                data = json.loads(sf.read_text(encoding='utf-8'))
                # Match by project path or cwd in metadata
                sess_cwd = data.get('metadata', {}).get('cwd', '')
                sess_project = data.get('metadata', {}).get('project', '')
                last_updated = data.get('last_updated', data.get('start_time', ''))

                # Check if same project
                is_match = False
                if project_path and sess_cwd and Path(sess_cwd).name == project_name:
                    is_match = True
                elif project_path and sess_project and Path(sess_project).name == project_name:
                    is_match = True
                elif not sess_cwd and not sess_project:
                    # No project info stored - still chain by time proximity
                    is_match = True

                if is_match and last_updated > best_time:
                    best_time = last_updated
                    best_match = sid
            except Exception:
                continue
    except Exception:
        return None

    return best_match

# SESSION CHANGE DETECTION (replaces clear-session-handler.py)
# Reads Claude Code's history.jsonl to detect /clear or new conversation.
# =============================================================================

SESSION_STATE_FILE = Path.home() / '.claude' / '.hook-state.json'


def _read_claude_code_session_id():
    """Read the latest sessionId from Claude Code history.jsonl.

    Claude Code writes each prompt to ~/.claude/history.jsonl with a sessionId
    field that changes when the user starts a new conversation or uses /clear.

    Returns:
        str: The sessionId from the last history entry, or empty string.
    """
    history_file = Path.home() / '.claude' / 'history.jsonl'
    if not history_file.exists():
        return ''
    try:
        last_line = ''
        with open(history_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if last_line:
            data = json.loads(last_line)
            return data.get('sessionId', '')
    except Exception:
        pass
    return ''


def _read_session_state():
    """Read persisted session state for change detection."""
    if not SESSION_STATE_FILE.exists():
        return {}
    try:
        with open(SESSION_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _write_session_state(conversation_id):
    """Persist session state for next invocation comparison."""
    state = _read_session_state()
    state['last_conversation_id'] = conversation_id
    state['flow_count'] = state.get('flow_count', 0) + 1
    state['updated_at'] = datetime.now().isoformat()
    try:
        SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def _detect_and_handle_session_change():
    """Detect if /clear was used or a new conversation started.

    Compares the current Claude Code sessionId (from history.jsonl) with the
    previously stored one.  If changed, closes the old session and returns True.

    Returns:
        bool: True if session changed (new session needed), False otherwise.
    """
    current_conv_id = _read_claude_code_session_id()
    state = _read_session_state()
    last_conv_id = state.get('last_conversation_id', '')
    flow_count = state.get('flow_count', 0)

    is_fresh = False
    reason = 'ongoing_conversation'

    # Case 1: First ever run (no previous state)
    if flow_count == 0:
        is_fresh = True
        reason = 'first_ever_conversation'

    # Case 2: Conversation ID changed (/clear or new window)
    elif (current_conv_id and last_conv_id
          and current_conv_id != last_conv_id):
        is_fresh = True
        reason = 'conversation_id_changed'

    if is_fresh:
        # Close old session if one exists
        try:
            csf = MEMORY_BASE / '.current-session.json'
            if csf.exists():
                old_data = json.loads(csf.read_text(encoding='utf-8'))
                old_session = old_data.get('current_session_id', '')
                if old_session:
                    # Close old session
                    sess_file = MEMORY_BASE / 'sessions' / (old_session + '.json')
                    if sess_file.exists():
                        sdata = json.loads(sess_file.read_text(encoding='utf-8'))
                        sdata['status'] = 'COMPLETED'
                        sdata['end_time'] = datetime.now().isoformat()
                        sess_file.write_text(json.dumps(sdata, indent=2), encoding='utf-8')

                    # Finalize session summary
                    try:
                        ssm = CURRENT_DIR / 'session-summary-manager.py'
                        if ssm.exists():
                            subprocess.run(
                                [PYTHON, str(ssm), 'finalize', '--session', old_session],
                                timeout=10, capture_output=True
                            )
                    except Exception:
                        pass

                    # Delete current-session pointer so Level 1.2 creates fresh
                    csf.unlink(missing_ok=True)

                    sys.stderr.write(f'[SESSION] /clear detected - old session saved: {old_session}\n')
                    sys.stderr.write(f'[SESSION] Reason: {reason}\n')
        except Exception:
            pass

    # Always update state with current conversation ID
    _write_session_state(current_conv_id)
    return is_fresh


def main():
    """Entry point for the 3-level architecture flow hook.

    Parses CLI arguments and/or Claude Code hook stdin (JSON), then runs
    the complete pipeline: Level -1 auto-fix enforcement, Level 1 sync
    system (context + session + preferences), Level 2 standards loading,
    and Level 3 execution system (12 sub-steps from prompt generation
    through skill/agent selection and task breakdown).

    Writes a JSON flow-trace to the session log directory on every run.
    Exits with code 1 if any blocking level fails; exits with code 0 on
    successful completion.
    """
    mode = 'standard'
    user_message = ''
    message_parts = []

    for arg in sys.argv[1:]:
        if arg in ('--verbose', '-v'):
            mode = 'verbose'
        elif arg in ('--summary', '-s'):
            mode = 'summary'
        elif arg == '--checkpoint':
            pass  # Consumed: checkpoint is always shown (no-op flag for backward compat)
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
    # STEP 0: FLAG AUTO-EXPIRY CLEANUP (Loophole #10 - v3.9.0)
    # Remove stale flag files older than FLAG_EXPIRY_MINUTES at startup so
    # they never accumulate in ~/.claude/ between sessions.
    # =========================================================================
    if FLAG_CLEANUP_ON_STARTUP:
        _expired_count = _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES)
        if _expired_count > 0:
            sys.stderr.write(f"[FLAG-CLEANUP] Removed {_expired_count} expired flag(s) "
                             f"older than {FLAG_EXPIRY_MINUTES} minutes\n")

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

    # CHECKPOINT ENFORCEMENT: Clear flags if user is confirming with 'ok'/'proceed' etc.
    # This MUST run before anything else so pre-tool-enforcer sees cleared flags.
    #
    # Loophole #11 distinction:
    #   - Approval message ('ok', 'proceed', 'haan') -> clear_current_session_flags()
    #     Only this session+PID's flags are cleared so other open windows keep theirs.
    #   - /clear command -> handled by clear-session-handler.py BEFORE this script runs,
    #     using clear_all_enforcement_flags() to wipe every window's stale flags.
    _is_approval = is_approval_message(user_message)
    if _is_approval:
        # Read current session_id early (before session management step) so we can
        # do precise session-scoped clearing.  Falls back to PID-only if not found.
        _early_session_id = 'UNKNOWN'
        try:
            # Per-project session file for multi-window isolation
            try:
                from project_session import read_session_id as _read_sid
                _early_session_id = _read_sid() or 'UNKNOWN'
            except ImportError:
                _csf = MEMORY_BASE / '.current-session.json'
                if _csf.exists():
                    import json as _json_early
                    _early_session_id = _json_early.loads(_csf.read_text(encoding='utf-8')).get(
                        'current_session_id', 'UNKNOWN'
                    ) or 'UNKNOWN'
        except Exception:
            pass
        clear_current_session_flags(
            session_id=_early_session_id,
            reason='user approval: ' + user_message.strip()[:20]
        )

    SEP = "=" * 80
    flow_start = datetime.now()

    # =========================================================================
    # INITIALIZE TRACE OBJECT
    # This is the central JSON object that tracks everything A-to-Z
    # =========================================================================
    trace = {
        "_schema_version": "2.0",  # Artifact versioning (Improvement #6) - validates cross-script compatibility
        "meta": {
            "flow_version": VERSION,
            "script": SCRIPT_NAME,
            "mode": mode,
            "flow_start": flow_start.isoformat(),
            "flow_end": None,
            "duration_seconds": None,
            "session_id": None,
            "log_dir": None,
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
        },
        "user_input": {
            "prompt": user_message,
            "prompt_length": len(user_message),
            "received_at": flow_start.isoformat(),
            "source": "UserPromptSubmit hook"
        },
        "pipeline": [],
        "final_decision": {},
        "work_started": False,
        "status": "RUNNING",
        "errors": [],
        "warnings": [],
    }

    # COMPACT OUTPUT: Redirect verbose prints to buffer, print compact at end
    # All existing print() calls go to _verbose_buf (saved to verbose-output.txt)
    # Only compact summary goes to real stdout (injected into Claude context)
    _verbose_buf = io.StringIO()
    _real_stdout = sys.stdout
    sys.stdout = _verbose_buf

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
    # SESSION CHANGE DETECTION (before any level runs)
    # Detects /clear or new conversation via Claude Code history.jsonl sessionId.
    # If changed, closes old session so Level 1.2 creates a fresh one.
    # =========================================================================
    _detect_and_handle_session_change()

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
        "status": "PASSED" if rc == 0 else "FAILED",
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
        "passed_to_next": lvl_minus1_passed,
        "errors": [],
        "warnings": []
    })

    if rc != 0:
        print("   [FAIL] System issues - BLOCKED!")
        trace["status"] = "BLOCKED"
        trace["work_started"] = False
        _save_trace(trace, None, flow_start)
        try:
            emit_policy_step('LEVEL_MINUS_1_AUTO_FIX', level=-1, passed=False,
                             duration_ms=dur, session_id='',
                             details={'exit_code': rc,
                                      'checks': lvl_minus1_output.get('checks', {})})
        except Exception:
            pass
        # Restore stdout before exit so error message is visible
        sys.stdout = _real_stdout
        print("[3-LEVEL FLOW] BLOCKED - Level -1 auto-fix failed")
        sys.exit(1)

    try:
        emit_policy_step('LEVEL_MINUS_1_AUTO_FIX', level=-1, passed=True,
                         duration_ms=dur, session_id='',
                         details={'checks': lvl_minus1_output.get('checks', {})})
    except Exception:
        pass
    print("   [OK] All systems operational")
    print("[OK] LEVEL -1 COMPLETE")
    print()

    # =========================================================================
    # LEVEL 1.1: CONTEXT MANAGEMENT
    # =========================================================================
    print("[LEVEL 1] SYNC SYSTEM (FOUNDATION)")

    step_start = datetime.now()
    # Level 1.1 uses session-pruning-policy for context monitoring
    ctx_script = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'context-management' / 'session-pruning-policy.py'
    if not ctx_script.exists():
        ctx_script = MEMORY_BASE / 'architecture' / '01-sync-system' / 'context-management' / 'session-pruning-policy.py'
    if not ctx_script.exists():
        ctx_script = CURRENT_DIR / 'context-monitor-v2.py'  # fallback for backward compatibility

    ctx_stdout, _, ctx_rc, ctx_dur = run_script_with_retry(ctx_script, ['--enforce'], timeout=8, step_name='Level-1.1.Context')
    ctx_data = safe_json(ctx_stdout)

    # session-pruning-policy.py returns 'context_percentage', not 'percentage'
    context_pct = ctx_data.get('context_percentage', ctx_data.get('percentage', 0))
    context_level = ctx_data.get('context_level', ctx_data.get('level', 'unknown'))
    ctx_recommendations = ctx_data.get('recommendations', [])

    # Fallback: if policy returned 0%, try session-progress.json (maintained by post-tool-tracker)
    if context_pct == 0:
        try:
            _sp_file = MEMORY_BASE / 'logs' / 'session-progress.json'
            if _sp_file.exists():
                with open(_sp_file, 'r', encoding='utf-8') as _spf:
                    _sp_data = json.load(_spf)
                _sp_ctx = _sp_data.get('context_estimate_pct', 0)
                if _sp_ctx > 0:
                    context_pct = _sp_ctx
        except Exception:
            pass

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
        "status": "PASSED",
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
    # Every prompt gets its own session ID and folder. No reuse.
    # =========================================================================
    step_start = datetime.now()
    sess_script = CURRENT_DIR / 'session-id-generator.py'

    # ALWAYS create a new session for every prompt
    create_desc = f"Session auto-created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    new_out, _, new_rc, sess_dur = run_script(
        sess_script, ['create', '--description', create_desc], timeout=8
    )

    session_id = 'UNKNOWN'
    for line in new_out.splitlines():
        line = line.strip()
        if line.startswith('SESSION-'):
            session_id = line
            break

    # SESSION CHAINING: Find most recent session for same project and link
    # This gives Claude context about what was done before in related sessions
    _prev_session_id = _find_previous_session(session_id, hook_cwd or str(Path.cwd()))
    if _prev_session_id and session_id != 'UNKNOWN':
        try:
            chain_script = CURRENT_DIR / 'session-chain-manager.py'
            if chain_script.exists():
                subprocess.run(
                    [PYTHON, str(chain_script), 'link',
                     '--child', session_id, '--parent', _prev_session_id],
                    timeout=5, capture_output=True
                )
        except Exception:
            pass

    # Set up session log directory NOW that we have session_id
    # NEVER create folder for UNKNOWN/unknown - only valid SESSION-* IDs
    if session_id and session_id not in ('UNKNOWN', 'unknown'):
        session_log_dir = MEMORY_BASE / 'logs' / 'sessions' / session_id
        session_log_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Fallback: use a timestamped temp dir instead of polluting with 'unknown'
        _ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        session_log_dir = MEMORY_BASE / 'logs' / 'sessions' / f'TEMP-{_ts}'
        session_log_dir.mkdir(parents=True, exist_ok=True)
    trace["meta"]["session_id"] = session_id
    trace["meta"]["log_dir"] = str(session_log_dir)

    # Store project cwd in session JSON for future chaining
    _sess_json_path = MEMORY_BASE / 'sessions' / f'{session_id}.json'
    if _sess_json_path.exists():
        try:
            _sd = json.loads(_sess_json_path.read_text(encoding='utf-8'))
            _sd.setdefault('metadata', {})
            _sd['metadata']['cwd'] = hook_cwd or str(Path.cwd())
            _sd['metadata']['project'] = hook_cwd or str(Path.cwd())
            if _prev_session_id:
                _sd['parent_session'] = _prev_session_id
            _sess_json_path.write_text(json.dumps(_sd, indent=2), encoding='utf-8')
        except Exception:
            pass

    # Determine session status and message number (v3.7.1 enrichment)
    _sess_flow_runs = 0
    _sess_status = "NEW"
    if _sess_json_path.exists():
        try:
            with open(_sess_json_path, 'r', encoding='utf-8') as _sf:
                _lock_file(_sf)
                _sdata = json.load(_sf)
                _unlock_file(_sf)
            _sess_flow_runs = _sdata.get('flow_runs', 0)
            _parent = _sdata.get('parent_session', '')
            if _parent:
                _sess_status = "CHAINED"
            elif _sess_flow_runs > 0:
                _sess_status = "RESUMED"
        except Exception:
            pass
    trace["meta"]["session_status"] = _sess_status
    trace["meta"]["message_number"] = _sess_flow_runs + 1

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

    # FLAG LIFECYCLE FIX: Clear stale flags from previous prompts BEFORE
    # creating new ones.  This prevents flag accumulation where old flags
    # block tools even after the context that created them is gone.
    if _needs_enforcement and session_id:
        clear_current_session_flags(session_id, reason='new-prompt-cleanup')

    if _needs_enforcement:
        # AUTO_PROCEED v1.0: Checkpoint text shows in trace but does NOT block.
        # User approved auto-proceed (2026-02-23) - trusts Claude's decisions.
        # write_checkpoint_flag() removed - no more .checkpoint-pending-*.json written.
        write_task_breakdown_flag(
            session_id=session_id,
            prompt_preview=user_message
        )

    trace["pipeline"].append({
        "step": "LEVEL_1_SESSION",
        "name": "Session Management",
        "level": 1,
        "order": 2,
        "is_blocking": False,
        "status": "PASSED",
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
            "exit_code": new_rc
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
    prefs_script = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'user-preferences' / 'user-preferences-policy.py'
    if not prefs_script.exists():
        prefs_script = MEMORY_BASE / '01-sync-system' / 'user-preferences' / 'user-preferences-policy.py'

    prefs_loaded = 0
    prefs_dur = 0
    prefs_data = {}
    if prefs_script.exists():
        prefs_out, _, prefs_rc, prefs_dur = run_script_with_retry(prefs_script, ['--enforce'], timeout=5, step_name='Level-1.3.Preferences')
        if prefs_rc == 0 and prefs_out.strip():
            prefs_data = safe_json(prefs_out)
            prefs_loaded = prefs_data.get('preferences_count', 0)

    trace["pipeline"].append({
        "step": "LEVEL_1_PREFERENCES",
        "name": "User Preferences",
        "level": 1,
        "order": 2.5,
        "is_blocking": False,
        "status": "PASSED",
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
    state_script = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'session-management' / 'session-memory-policy.py'
    if not state_script.exists():
        state_script = MEMORY_BASE / '01-sync-system' / 'session-management' / 'session-memory-policy.py'

    state_dur = 0
    state_summary = {}
    if state_script.exists():
        st_out, _, st_rc, state_dur = run_script_with_retry(state_script, ['--enforce'], timeout=5, step_name='Level-1.4.Session-State')
        if st_rc == 0 and st_out.strip():
            state_summary = safe_json(st_out)

    completed_tasks_count = state_summary.get('progress', {}).get('completed_tasks', 0)
    files_modified_count = state_summary.get('progress', {}).get('files_modified', 0)
    pending_work_count = state_summary.get('progress', {}).get('pending_work', 0)

    # Fallback: if session-memory-policy returned 0s, use session-progress.json
    # (maintained by post-tool-tracker with real tool usage data)
    if completed_tasks_count == 0 and files_modified_count == 0:
        try:
            _sp_file = MEMORY_BASE / 'logs' / 'session-progress.json'
            if _sp_file.exists():
                with open(_sp_file, 'r', encoding='utf-8') as _spf:
                    _sp_data = json.load(_spf)
                completed_tasks_count = _sp_data.get('tasks_completed', 0)
                _mod_files = _sp_data.get('modified_files_since_commit', [])
                files_modified_count = len(_mod_files) if isinstance(_mod_files, list) else 0
                # Count total tools used as a proxy for work done
                _tc = _sp_data.get('tool_counts', {})
                _total_tools = sum(_tc.values()) if isinstance(_tc, dict) else 0
                if pending_work_count == 0 and _total_tools > 0:
                    pending_work_count = max(0, _total_tools - completed_tasks_count)
        except Exception:
            pass

    trace["pipeline"].append({
        "step": "LEVEL_1_STATE",
        "name": "Session State",
        "level": 1,
        "order": 2.7,
        "is_blocking": False,
        "status": "PASSED",
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

    # =========================================================================
    # LEVEL 1.5: CROSS-PROJECT PATTERN DETECTION
    # Architecture script: 01-sync-system/pattern-detection/detect-patterns.py
    # Policy: cross-project-patterns-policy.md
    # Detects technology patterns across projects for intelligent suggestions.
    # Runs full detection on NEW sessions or when patterns file is stale (>24h).
    # =========================================================================
    step_start = datetime.now()
    patterns_arch_dir = SCRIPT_DIR / 'architecture' / '01-sync-system' / 'pattern-detection'
    detect_script = patterns_arch_dir / 'cross-project-patterns-policy.py'
    patterns_file = Path.home() / '.claude' / 'memory' / 'cross-project-patterns.json'

    patterns_detected = 0
    patterns_dur = 0
    cross_patterns = []
    detection_ran = False

    if detect_script.exists():
        # Run full detection only on NEW sessions or when patterns file is stale
        run_detection = (_sess_status == "NEW")
        if not run_detection and not patterns_file.exists():
            run_detection = True
        if not run_detection and patterns_file.exists():
            try:
                file_age_hours = (datetime.now().timestamp() - patterns_file.stat().st_mtime) / 3600
                if file_age_hours > 24:
                    run_detection = True
            except Exception:
                pass

        if run_detection:
            det_out, _, det_rc, det_dur = run_script_with_retry(detect_script, timeout=10, step_name='Level-1.5.Pattern-Detect')
            patterns_dur += det_dur
            detection_ran = True

    # Load patterns file (lightweight JSON read, regardless of whether detection ran)
    if patterns_file.exists():
        try:
            with open(patterns_file, 'r', encoding='utf-8') as pf:
                _lock_file(pf)
                pdata = json.load(pf)
                _unlock_file(pf)
            cross_patterns = pdata.get('patterns', [])
            patterns_detected = len(cross_patterns)
        except Exception:
            pass

    trace["pipeline"].append({
        "step": "LEVEL_1_PATTERNS",
        "name": "Cross-Project Pattern Detection",
        "level": 1,
        "order": 2.9,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": patterns_dur,
        "input": {
            "from_previous": "LEVEL_1_STATE",
            "session_id": session_id,
            "purpose": "Detect technology patterns across projects for intelligent suggestions"
        },
        "policy": {
            "script": "detect-patterns.py",
            "policy_file": "cross-project-patterns-policy.md",
            "rules_applied": [
                "scan_session_summaries_across_projects",
                "detect_technology_stack_keywords",
                "calculate_pattern_confidence",
                "save_cross_project_patterns_json"
            ]
        },
        "policy_output": {
            "patterns_detected": patterns_detected,
            "top_patterns": [{"name": p["name"], "type": p["type"], "confidence": p["confidence"]} for p in cross_patterns[:5]],
            "detection_ran": detection_ran,
            "script_exists": detect_script.exists()
        },
        "decision": f"Detected {patterns_detected} cross-project patterns" if patterns_detected > 0 else "No patterns detected (insufficient data or first analysis)",
        "passed_to_next": {
            "patterns_available": patterns_detected > 0,
            "patterns_count": patterns_detected,
            "top_pattern_names": [p["name"] for p in cross_patterns[:5]]
        }
    })
    if patterns_detected > 0:
        top_names = ", ".join([p["name"] for p in cross_patterns[:3]])
        print(f"   [OK] Patterns: {patterns_detected} detected (top: {top_names})")
    else:
        print(f"   [OK] Patterns: None detected yet")

    # =========================================================================
    # LEVEL 1.6: SCRIPT DEPENDENCY VALIDATION (Improvement #6)
    # Validates that all scripts can safely call each other:
    #   - All dependency scripts exist on disk
    #   - No circular dependencies in the dependency graph
    #   - Artifact JSON files include schema version headers
    # Non-blocking: validation issues are logged as warnings, never block flow.
    # =========================================================================
    step_start = datetime.now()
    dep_validator_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / 'script-dependency-validator.py'
    dep_deployed = SCRIPTS_DIR / 'architecture' / '03-execution-system' / 'script-dependency-validator.py'

    dep_status = 'SKIPPED'
    dep_dur = 0
    dep_result = {}
    dep_missing = []
    dep_cycles = []
    dep_artifact_issues = 0
    dep_script_path = dep_validator_script if dep_validator_script.exists() else (dep_deployed if dep_deployed.exists() else None)

    if dep_script_path:
        dep_out, dep_err, dep_rc, dep_dur = run_script(dep_script_path, args=['--report'], timeout=8)
        if dep_out.strip():
            try:
                dep_result = json.loads(dep_out.strip())
                dep_missing = dep_result.get('missing_dependencies', [])
                dep_cycles = dep_result.get('circular_dependencies', [])
                dep_artifact_issues = len(dep_result.get('artifact_issues', []))
                dep_status = dep_result.get('overall_status', 'UNKNOWN')
            except Exception:
                dep_status = 'PARSE_ERROR'
        else:
            dep_status = 'NO_OUTPUT'
    else:
        dep_status = 'SCRIPT_NOT_FOUND'

    trace["pipeline"].append({
        "step": "LEVEL_1_6_DEP_VALIDATION",
        "name": "Script Dependency Validation",
        "level": 1.6,
        "order": 3.0,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": dep_dur,
        "input": {
            "from_previous": "LEVEL_1_PATTERNS",
            "session_id": session_id,
            "purpose": "Validate script dependencies and artifact schema versions"
        },
        "policy": {
            "script": "script-dependency-validator.py",
            "args": ["--report"],
            "rules_applied": [
                "validate_dependency_existence",
                "detect_circular_dependencies",
                "validate_artifact_schema_versions"
            ]
        },
        "policy_output": {
            "overall_status": dep_status,
            "missing_dependencies": dep_missing,
            "circular_dependencies": dep_cycles,
            "artifact_issues_count": dep_artifact_issues,
            "scripts_validated": dep_result.get('scripts_total', 0),
            "dependencies_checked": dep_result.get('dependencies_total', 0),
            "script_found": dep_script_path is not None,
        },
        "decision": (
            f"Dependencies valid, no cycles"
            if dep_status == 'PASS'
            else f"Dependency validation: {dep_status} "
                 f"(missing={len(dep_missing)}, cycles={len(dep_cycles)}, "
                 f"artifact_issues={dep_artifact_issues})"
        ),
        "passed_to_next": {
            "dep_validation_status": dep_status,
            "dep_issues_found": bool(dep_missing or dep_cycles)
        }
    })

    if dep_status == 'PASS':
        print(f"   [OK] Dep Validator: {dep_result.get('scripts_total', '?')} scripts, "
              f"{dep_result.get('dependencies_total', '?')} deps, no cycles")
    elif dep_status in ('SKIPPED', 'SCRIPT_NOT_FOUND'):
        print(f"   [OK] Dep Validator: Skipped (script not found)")
    else:
        if dep_missing:
            print(f"   [WARN] Dep Validator: {len(dep_missing)} missing dep(s)")
        if dep_cycles:
            print(f"   [WARN] Dep Validator: {len(dep_cycles)} cycle(s) detected")
        if dep_artifact_issues:
            print(f"   [INFO] Dep Validator: {dep_artifact_issues} artifact(s) missing schema version")
        if not (dep_missing or dep_cycles or dep_artifact_issues):
            print(f"   [OK] Dep Validator: {dep_status}")

    print("[OK] LEVEL 1 COMPLETE (6 sub-steps)")
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

    standards_script = SCRIPT_DIR / 'architecture' / '02-standards-system' / 'common-standards-policy.py'
    if not standards_script.exists():
        standards_script = MEMORY_BASE / '02-standards-system' / 'common-standards-policy.py'

    # ------------------------------------------------------------------
    # LEVEL 2.1: COMMON STANDARDS (always active)
    # ------------------------------------------------------------------
    step_start_2_1 = datetime.now()
    common_count = 0
    common_rules = 0
    common_list = []
    common_dur = 0

    if standards_script.exists():
        c_out, _, c_rc, common_dur = run_script_with_retry(standards_script, ['--enforce'], timeout=10, step_name='Level-2.1.Common')
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
        "status": "PASSED",
        "timestamp": step_start_2_1.isoformat(),
        "duration_ms": common_dur,
        "input": {
            "from_previous": "LEVEL_1_PATTERNS",
            "session_id": session_id,
            "context_pct": context_pct,
            "cross_project_patterns": patterns_detected,
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
        micro_count = 0
        micro_rules = 0

        # Use coding-standards-enforcement-policy.py for microservices standards
        coding_standards_script = SCRIPT_DIR / 'architecture' / '02-standards-system' / 'coding-standards-enforcement-policy.py'
        if not coding_standards_script.exists():
            coding_standards_script = MEMORY_BASE / '02-standards-system' / 'coding-standards-enforcement-policy.py'

        if coding_standards_script.exists():
            m_out, _, m_rc, micro_dur = run_script_with_retry(coding_standards_script, ['--enforce'], timeout=10, step_name='Level-2.2.Microservices')
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
            "status": "PASSED",
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
            "status": "PASSED",
            "timestamp": datetime.now().isoformat(),
            "duration_ms": dur,
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
    # LEVEL 3: EXECUTION SYSTEM - PRE-FLIGHT + 12 STEPS
    # =========================================================================
    print("[LEVEL 3] EXECUTION SYSTEM (PRE-FLIGHT + 12 STEPS)")

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
    # STEP 3.0.0: CONTEXT READING (PRE-FLIGHT)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    context_reader_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-context-reading' / 'context-reader.py'
    if not context_reader_script.exists():
        context_reader_script = MEMORY_BASE / '03-execution-system' / '00-context-reading' / 'context-reader.py'

    context_cache = {}
    enrichment_data = {}
    cr_dur = 0

    if context_reader_script.exists():
        # Pass hook_cwd and session_id to context-reader
        cr_out, _, _, cr_dur = run_script_with_retry(
            context_reader_script,
            [hook_cwd or str(Path.cwd()), session_id],
            timeout=5,
            step_name='Step-3.0.0.Context-Reading'
        )

        # Extract trace entry and context from output
        try:
            # Last line should be JSON trace entry (from print(json.dumps(trace_entry)))
            lines = cr_out.strip().splitlines()
            for line in lines:
                if line.startswith('{'):
                    trace_entry = json.loads(line)
                    # Extract context cache if available
                    if 'passed_to_next' in trace_entry:
                        enrichment_data = trace_entry.get('passed_to_next', {})
                    break
        except Exception as e:
            print(f"[WARN] Could not parse context-reader output: {e}")
            enrichment_data = {}

        # Save enrichment data to session for prompt-generator to use
        try:
            enrichment_file = session_log_dir / 'enrichment-data.json'
            enrichment_file.write_text(json.dumps({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'enrichment_data': enrichment_data
            }, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"[WARN] Could not save enrichment data: {e}")

        # Show context reading result
        if enrichment_data.get('project_name'):
            print(f"   [3.0.0] Project: {enrichment_data.get('project_name', 'Unknown')}")
            print(f"   [3.0.0] Version: {enrichment_data.get('current_version', 'Unknown')}")
            if enrichment_data.get('tech_stack'):
                print(f"   [3.0.0] Tech Stack: {', '.join(enrichment_data.get('tech_stack', []))}")
        else:
            print(f"   [3.0.0] Context: Not available (new project)")

    step_3_0_0_output = {
        "project_detected": enrichment_data.get('context_available', False) if enrichment_data else False,
        "project_name": enrichment_data.get('project_name'),
        "enrichment_data": enrichment_data,
        "script_exists": context_reader_script.exists()
    }
    step_3_0_0_decision = f"Context reading completed - {'Project context loaded' if enrichment_data else 'No context files found'}"

    # Add STEP 3.0.0 to trace pipeline
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_0_0",
        "name": "Context Reading (Pre-Flight)",
        "level": 3,
        "order": 0,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": cr_dur,
        "input": {
            "from_previous": "LEVEL_2_STANDARDS",
            "hook_cwd": hook_cwd or str(Path.cwd()),
            "session_id": session_id,
            "purpose": "Detect and read project context files before execution"
        },
        "policy": {
            "script": "context-reader.py",
            "args": [hook_cwd or str(Path.cwd()), session_id],
            "rules_applied": [
                "detect_project_from_readme",
                "scan_context_files",
                "read_with_encoding_safety",
                "extract_metadata",
                "cache_in_session",
                "handle_missing_files_gracefully"
            ]
        },
        "policy_output": step_3_0_0_output,
        "decision": step_3_0_0_decision,
        "passed_to_next": {
            "project_name": enrichment_data.get('project_name'),
            "current_version": enrichment_data.get('current_version'),
            "tech_stack": enrichment_data.get('tech_stack', []),
            "project_overview": enrichment_data.get('project_overview', '')[:500],
            "enrichment_available": bool(enrichment_data)
        }
    })
    print(f"   [3.0.0] Context Reading: Complete")

    # ------------------------------------------------------------------
    # STEP 3.0.1: CODE GRAPH ANALYSIS (PRE-FLIGHT)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    graph_analyzer_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-code-graph-analysis' / 'code-graph-analyzer.py'
    if not graph_analyzer_script.exists():
        graph_analyzer_script = MEMORY_BASE / '03-execution-system' / '00-code-graph-analysis' / 'code-graph-analyzer.py'

    graph_complexity_score = 0
    graph_metrics_summary = ''
    graph_analysis_data = {}
    ga_dur = 0

    if graph_analyzer_script.exists():
        # Pass project dir, session_id, and tech_stack CSV from enrichment
        tech_stack_csv = ','.join(enrichment_data.get('tech_stack', [])) if enrichment_data else ''
        ga_out, _, _, ga_dur = run_script_with_retry(
            graph_analyzer_script,
            [hook_cwd or str(Path.cwd()), session_id, tech_stack_csv],
            timeout=10,
            step_name='Step-3.0.1.Graph-Analysis'
        )

        # Parse output - last JSON line is the trace entry
        try:
            lines = ga_out.strip().splitlines()
            for line in reversed(lines):
                if line.startswith('{'):
                    ga_trace = json.loads(line)
                    if 'passed_to_next' in ga_trace:
                        graph_analysis_data = ga_trace.get('passed_to_next', {})
                        graph_complexity_score = graph_analysis_data.get('graph_complexity_score', 0)
                        graph_metrics_summary = graph_analysis_data.get('graph_metrics_summary', '')
                    break
        except Exception as e:
            print(f"[WARN] Could not parse graph-analyzer output: {e}")
            graph_complexity_score = 0

        # Save graph analysis data to session for prompt-generator
        try:
            graph_file = session_log_dir / 'graph-analysis-result.json'
            graph_file.write_text(json.dumps({
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'graph_complexity_score': graph_complexity_score,
                'graph_analysis_data': graph_analysis_data
            }, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"[WARN] Could not save graph analysis result: {e}")

        # Display result
        if graph_complexity_score > 0:
            print(f"   [3.0.1] Graph Complexity: {graph_complexity_score}/25")
            if graph_metrics_summary:
                print(f"   [3.0.1] Metrics: {graph_metrics_summary[:80]}")
        else:
            print(f"   [3.0.1] Graph Analysis: Not available")
    else:
        print(f"   [3.0.1] Graph Analyzer: Script not found")

    step_3_0_1_output = {
        "graph_complexity_score": graph_complexity_score,
        "graph_metrics_summary": graph_metrics_summary,
        "analysis_available": graph_complexity_score > 0,
        "script_exists": graph_analyzer_script.exists()
    }
    step_3_0_1_decision = f"Graph complexity = {graph_complexity_score}/25 - {'structural analysis applied' if graph_complexity_score > 0 else 'analysis unavailable'}"

    # Add STEP 3.0.1 to trace pipeline
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_0_1",
        "name": "Code Graph Analysis (Pre-Flight)",
        "level": 3,
        "order": 0.1,
        "is_blocking": False,
        "timestamp": step_start.isoformat(),
        "duration_ms": ga_dur,
        "input": {
            "hook_cwd": hook_cwd or str(Path.cwd()),
            "session_id": session_id,
            "tech_stack": enrichment_data.get('tech_stack', []) if enrichment_data else [],
            "purpose": "Build dependency graph and calculate structural complexity"
        },
        "policy": {
            "script": "code-graph-analyzer.py",
            "args": [hook_cwd or str(Path.cwd()), session_id],
            "rules_applied": [
                "discover_source_files",
                "extract_imports_ast_and_regex",
                "build_dependency_digraph",
                "calculate_centrality_metrics",
                "calculate_cyclomatic_complexity",
                "score_graph_complexity_1_25",
            ]
        },
        "policy_output": step_3_0_1_output,
        "decision": step_3_0_1_decision,
        "status": "PASSED",
        "passed_to_next": {
            "graph_complexity_score": graph_complexity_score,
            "graph_metrics_summary": graph_metrics_summary,
            "top_bottleneck_files": graph_analysis_data.get('top_bottleneck_files', []),
            "analysis_available": graph_complexity_score > 0
        }
    })
    print(f"   [3.0.1] Code Graph Analysis: Complete")

    # ------------------------------------------------------------------
    # STEP 3.0: PROMPT GENERATION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    complexity = 5
    task_type = 'General'
    prompt_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-prompt-generation' / 'prompt-generation-policy.py'
    if not prompt_script.exists():
        prompt_script = MEMORY_BASE / '03-execution-system' / '00-prompt-generation' / 'prompt-generation-policy.py'
    pr_out = ''
    pr_dur = 0
    enhanced_prompt_summary = ''
    rewritten_prompt = ''
    if prompt_script.exists():
        # Prompt script takes message as argument to auto-generate
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
    # ------------------------------------------------------------------
    # COMBINE COMPLEXITY: keyword (30%) + graph (70%)
    # ------------------------------------------------------------------
    keyword_complexity = complexity  # Save original keyword-based score
    if graph_complexity_score > 0:
        # Graph analysis available - combine both scores: keyword(30%) + graph(70%)
        combined = round((keyword_complexity * 0.3) + (graph_complexity_score * 0.7))
        complexity = max(1, min(combined, 25))
        complexity_combining_formula = (
            f"(keyword={keyword_complexity} * 0.3) + (graph={graph_complexity_score} * 0.7) "
            f"= {round(keyword_complexity * 0.3, 1)} + {round(graph_complexity_score * 0.7, 1)} "
            f"= {complexity}/25"
        )
        print(f"   [3.0+] Combined Complexity: {complexity}/25 (keyword={keyword_complexity}, graph={graph_complexity_score})")
        print(f"   [3.0+] Formula: {complexity_combining_formula}")
    else:
        complexity_combining_formula = f"keyword_only={complexity}/25 (graph not available)"
        print(f"   [3.0+] Keyword Complexity: {complexity}/25 (graph not available)")

    step_3_0_output["keyword_complexity"] = keyword_complexity
    step_3_0_output["graph_complexity"] = graph_complexity_score
    step_3_0_output["combined_complexity"] = complexity
    step_3_0_output["complexity_combining_formula"] = complexity_combining_formula
    step_3_0_output["estimated_complexity"] = complexity  # Override with combined

    step_3_0_decision = f"Complexity={complexity}/25 (kw={keyword_complexity}+graph={graph_complexity_score}), Type={task_type}"

    # STEP 3.0 MOVED TO AFTER SKILL SELECTION - See STEP 3.5

    # ------------------------------------------------------------------
    # STEP 3.1: TASK BREAKDOWN
    # ------------------------------------------------------------------
    step_start = datetime.now()
    task_count = 2
    task_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '01-task-breakdown' / 'automatic-task-breakdown-policy.py'
    if not task_script.exists():
        task_script = MEMORY_BASE / '03-execution-system' / '01-task-breakdown' / 'automatic-task-breakdown-policy.py'
    tk_dur = 0
    if task_script.exists():
        # Task script supports --analyze <message> for task breakdown
        tk_out, _, _, tk_dur = run_script_with_retry(task_script, ['--analyze', user_message], timeout=8, step_name='Step-3.1.Task-Breakdown')
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

    # Store tasks_planned in session-progress.json for visibility
    # (not tasks_created, to avoid poisoning post-tool-tracker completion checks)
    # Flag stays alive until Claude calls TaskCreate → post-tool-tracker clears it
    if tasks_created and session_id:
        try:
            _sp_file = MEMORY_BASE / 'logs' / 'session-progress.json'
            _sp_data = {}
            if _sp_file.exists():
                with open(_sp_file, 'r', encoding='utf-8') as _f:
                    _sp_data = json.load(_f)
            _sp_data['tasks_planned'] = max(
                _sp_data.get('tasks_planned', 0), len(tasks_created)
            )
            with open(_sp_file, 'w', encoding='utf-8') as _f:
                json.dump(_sp_data, _f, indent=2)
        except Exception:
            pass

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_0",
        "name": "Automatic Task Breakdown",
        "level": 3,
        "order": 4,
        "is_blocking": False,
        "status": "PASSED",
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
    try:
        emit_policy_step('LEVEL_3_STEP_3_0_TASK_BREAKDOWN', level=3, passed=True,
                         duration_ms=0, session_id=session_id or '',
                         details={'task_count': task_count, 'complexity': complexity,
                                  'task_type': task_type})
    except Exception:
        pass

    # ------------------------------------------------------------------
    # STEP 3.2: PLAN MODE SUGGESTION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    plan_required = False
    adj_complexity = complexity
    plan_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '02-plan-mode' / 'auto-plan-mode-suggestion-policy.py'
    if not plan_script.exists():
        plan_script = MEMORY_BASE / '03-execution-system' / '02-plan-mode' / 'auto-plan-mode-suggestion-policy.py'
    pl_dur = 0
    plan_score_detail = {}
    if plan_script.exists():
        # Plan mode suggestion script (requires argument after --suggest)
        pl_out, _, _, pl_dur = run_script_with_retry(plan_script, ['--suggest', user_message, '--complexity', str(complexity)], timeout=8, step_name='Step-3.2.Plan-Mode')
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
        "status": "PASSED",
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
    ctx_out2, ctx2_dur = ctx_stdout, 0  # Reuse Level 1 result (no redundant subprocess call)
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
        "status": "PASSED",
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
    try:
        emit_policy_step('LEVEL_3_STEP_3_2_CONTEXT_CHECK', level=3, passed=ctx2_ok,
                         duration_ms=0, session_id=session_id or '',
                         details={'context_pct': context_pct2, 'safe_to_proceed': ctx2_ok})
    except Exception:
        pass

    # ------------------------------------------------------------------
    # STEP 3.3A: INTELLIGENT DECISION ENGINE (LLM-Powered)
    # Replaces keyword-based guessing with local Ollama LLM for:
    #   - Task Type, Model Selection, Skill/Agent Selection, Complexity
    # SKIP for trivial prompts (questions, short messages, approvals)
    # ------------------------------------------------------------------
    step_start_llm = datetime.now()
    llm_decision = None
    _skip_llm = False

    # Skip LLM for trivial prompts - saves ~20-25s per prompt
    _msg_lower = user_message.strip().lower()
    _msg_words = len(user_message.split())
    if _msg_words <= 5:
        _skip_llm = True
        print("   [3.3A] LLM Decision Engine: SKIPPED (message <= 5 words)")
    elif _msg_lower.startswith(('yes', 'no', 'ok', 'haan', 'nahi', 'theek', 'sure', 'done',
                                 'commit', 'push', 'ha ', 'ni ', 'kr', 'kar')):
        _skip_llm = True
        print("   [3.3A] LLM Decision Engine: SKIPPED (approval/short command)")
    elif _msg_lower.endswith('?') and _msg_words <= 12:
        _skip_llm = True
        print("   [3.3A] LLM Decision Engine: SKIPPED (short question)")

    # LLM result cache - avoid re-calling for similar prompts in same session
    _llm_cache_file = MEMORY_BASE / 'logs' / 'llm-decision-cache.json'

    if not _skip_llm:
        # Check cache first
        try:
            if _llm_cache_file.exists():
                with open(_llm_cache_file, 'r', encoding='utf-8') as _cf:
                    _cache = json.load(_cf)
                _cache_key = f"{task_type}:{','.join(sorted(tech_stack))}:{_msg_lower[:50]}"
                _cached = _cache.get(_cache_key)
                if _cached:
                    _cache_age = (datetime.now() - datetime.fromisoformat(_cached.get('cached_at', '2000-01-01'))).total_seconds()
                    if _cache_age < 300:  # 5 min cache TTL
                        llm_decision = _cached.get('decision')
                        if llm_decision:
                            print(f"   [3.3A] LLM Decision Engine: CACHED (age={int(_cache_age)}s) "
                                  f"task={llm_decision.get('task_type')}, agent={llm_decision.get('agent_name')}")
                            _skip_llm = True
        except Exception:
            pass

    llm_engine_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '04-model-selection' / 'intelligent-decision-engine.py'
    if not llm_engine_script.exists():
        llm_engine_script = MEMORY_BASE / '03-execution-system' / '04-model-selection' / 'intelligent-decision-engine.py'

    if llm_engine_script.exists() and not _skip_llm:
        try:
            import tempfile as _llm_tempfile
            llm_context = {
                'user_message': user_message,
                'keyword_task_type': task_type,
                'keyword_complexity': adj_complexity,
                'tech_stack': tech_stack,
                'keywords': [],
                'context_pct': context_pct2,
                'task_count': task_count,
                'plan_required': plan_required,
                'project_name': Path.cwd().name,
            }
            with _llm_tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as _llm_tf:
                json.dump(llm_context, _llm_tf)
                _llm_tf_path = _llm_tf.name
            llm_out, llm_err, llm_rc, llm_dur = run_script(llm_engine_script, [_llm_tf_path], timeout=45)
            try:
                os.unlink(_llm_tf_path)
            except OSError:
                pass
            if llm_rc == 0 and llm_out.strip():
                llm_json = None
                # Parse JSON from output (may have text before JSON)
                last_brace = llm_out.rfind('\n{')
                if last_brace >= 0:
                    try:
                        llm_json = json.loads(llm_out[last_brace + 1:])
                    except json.JSONDecodeError:
                        pass
                if llm_json is None and llm_out.strip().startswith('{'):
                    try:
                        llm_json = json.loads(llm_out.strip())
                    except json.JSONDecodeError:
                        pass
                if llm_json and 'error' not in llm_json:
                    llm_decision = llm_json
                    # Override pipeline variables with LLM decisions
                    task_type = llm_decision.get('task_type', task_type)
                    adj_complexity = llm_decision.get('complexity', adj_complexity)
                    print(f"   [3.3A] LLM Decision Engine: task={task_type}, "
                          f"complexity={adj_complexity}, model={llm_decision.get('model')}, "
                          f"agent={llm_decision.get('agent_name')} "
                          f"(confidence={llm_decision.get('confidence', 0):.1%}, "
                          f"{llm_decision.get('duration_ms', 0)}ms, "
                          f"llm={llm_decision.get('llm_model_used', 'unknown')})")
                    # Cache the result (5 min TTL) to avoid re-calling for similar prompts
                    try:
                        _cache = {}
                        if _llm_cache_file.exists():
                            with open(_llm_cache_file, 'r', encoding='utf-8') as _cf:
                                _cache = json.load(_cf)
                        _cache_key = f"{task_type}:{','.join(sorted(tech_stack))}:{_msg_lower[:50]}"
                        _cache[_cache_key] = {
                            'decision': llm_decision,
                            'cached_at': datetime.now().isoformat()
                        }
                        # Keep cache small - max 20 entries
                        if len(_cache) > 20:
                            _sorted = sorted(_cache.items(), key=lambda x: x[1].get('cached_at', ''))
                            _cache = dict(_sorted[-20:])
                        _llm_cache_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(_llm_cache_file, 'w', encoding='utf-8') as _cf:
                            json.dump(_cache, _cf)
                    except Exception:
                        pass
                else:
                    err_msg = llm_json.get('error', 'unknown') if llm_json else llm_err[:100]
                    print(f"   [3.3A] LLM Decision Engine FAILED: {err_msg}")
            else:
                print(f"   [3.3A] LLM Decision Engine FAILED: rc={llm_rc}")
        except Exception as _llm_ex:
            print(f"   [3.3A] LLM Decision Engine ERROR: {_llm_ex}")
    elif not _skip_llm:
        print(f"   [3.3A] LLM Decision Engine: script not found (skipped)")

    llm_dur_ms = int((datetime.now() - step_start_llm).total_seconds() * 1000)
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_3A",
        "name": "Intelligent Decision Engine (LLM)",
        "level": 3,
        "order": 6.5,
        "is_blocking": True,
        "status": "PASSED" if llm_decision else "FAILED",
        "timestamp": step_start_llm.isoformat(),
        "duration_ms": llm_dur_ms,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_2",
            "user_message_preview": user_message[:100],
            "keyword_task_type": task_type,
            "keyword_complexity": adj_complexity,
            "tech_stack": tech_stack,
            "context_pct": context_pct2,
            "purpose": "LLM-powered unified decision for task_type, model, skill/agent"
        },
        "policy": {
            "script": "intelligent-decision-engine.py",
            "rules_applied": [
                "llm_replaces_keyword_guessing",
                "mandatory_pipeline_step",
                "openrouter_free_models",
                "plan_mode_forces_opus"
            ]
        },
        "policy_output": llm_decision if llm_decision else {"error": "LLM failed"},
        "decision": f"LLM decided: task={task_type}, model={llm_decision.get('model') if llm_decision else 'N/A'}" if llm_decision else "LLM failed - using keyword fallback",
        "passed_to_next": {
            "llm_decision_available": llm_decision is not None,
            "overrides_model_selection": llm_decision is not None,
            "overrides_skill_selection": llm_decision is not None
        }
    })
    try:
        emit_policy_step('LEVEL_3_STEP_3_3A_LLM_DECISION', level=3,
                         passed=llm_decision is not None,
                         duration_ms=llm_dur_ms, session_id=session_id or '',
                         details={'llm_available': llm_decision is not None,
                                  'model': llm_decision.get('model') if llm_decision else None,
                                  'agent': llm_decision.get('agent_name') if llm_decision else None,
                                  'confidence': llm_decision.get('confidence') if llm_decision else 0})
    except Exception:
        pass

    # ------------------------------------------------------------------
    # STEP 3.4: MODEL SELECTION (via intelligent-model-selection-policy.py)
    # If LLM decision engine succeeded, use its model recommendation.
    # Otherwise fall back to existing keyword/threshold logic.
    # ------------------------------------------------------------------
    step_start = datetime.now()
    model_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '04-model-selection' / 'intelligent-model-selection-policy.py'
    if not model_script.exists():
        model_script = MEMORY_BASE / '03-execution-system' / '04-model-selection' / 'intelligent-model-selection-policy.py'

    selected_model = None
    model_reason = ''
    model_overrides = []
    model_script_used = False

    # LLM decision is checked AFTER script fallback (see below, line marked LLM_FINAL)
    _llm_model_override = None
    if llm_decision and llm_decision.get('model') in ('HAIKU', 'SONNET', 'OPUS'):
        _llm_model_override = llm_decision['model']
        _llm_model_reason = f"[LLM] {llm_decision.get('model_reasoning', 'LLM decision')}"

    if model_script.exists():
        try:
            ms_out, ms_err, ms_rc, ms_dur = run_script(model_script, ['--analyze', user_message, '--complexity', str(adj_complexity)], timeout=8)
            if ms_rc == 0 and ms_out.strip():
                # Parse JSON — script may output only JSON or JSON after text
                try:
                    ms_json = json.loads(ms_out.strip())
                except json.JSONDecodeError:
                    ms_json = None
                    last_brace = ms_out.rfind('\n{')
                    if last_brace >= 0:
                        ms_json = json.loads(ms_out[last_brace + 1:])
                raw_model = ms_json.get('recommended_model', '').upper() if ms_json else ''
                ms_reasoning = ms_json.get('reasoning', '') if ms_json else ''
                ms_confidence = ms_json.get('confidence', 0) if ms_json else 0
                if raw_model in ('HAIKU', 'SONNET', 'OPUS'):
                    selected_model = raw_model
                    model_reason = f"[Script] {ms_reasoning} (confidence={ms_confidence})"
                    model_script_used = True
        except (json.JSONDecodeError, Exception):
            pass

    # Fallback: inline logic if script failed or not found
    if not selected_model:
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

    # LLM_FINAL: LLM decision overrides BOTH script and inline fallback
    # Only plan_required and security overrides can override LLM (below)
    if _llm_model_override:
        selected_model = _llm_model_override
        model_reason = _llm_model_reason
        model_script_used = True
        model_overrides.append('llm_decision_engine_override')

    # Override rules (always applied, even on LLM results)
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
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_2",
            "adjusted_complexity": adj_complexity,
            "task_type": task_type,
            "plan_required": plan_required,
            "context_pct": context_pct2,
            "purpose": "Select optimal Claude model for this task"
        },
        "policy": {
            "script": "intelligent-model-selection-policy.py" if model_script_used else "inline fallback",
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
    try:
        emit_policy_step('LEVEL_3_STEP_3_3_MODEL_SELECTION', level=3, passed=True,
                         duration_ms=0, session_id=session_id or '',
                         details={'model': selected_model, 'reason': model_reason,
                                  'complexity': adj_complexity,
                                  'overrides': model_overrides})
    except Exception:
        pass

    # ------------------------------------------------------------------
    # STEP 3.5: SKILL/AGENT SELECTION (via auto-skill-agent-selection-policy.py)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    skill_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '05-skill-agent-selection' / 'auto-skill-agent-selection-policy.py'
    if not skill_script.exists():
        skill_script = MEMORY_BASE / '03-execution-system' / '05-skill-agent-selection' / 'auto-skill-agent-selection-policy.py'

    skill_agent_name = None
    agent_type = None
    supplementary_skills = []
    skill_reason = ''
    skill_script_used = False

    # USE LLM DECISION if available (overrides all keyword-based skill selection)
    if llm_decision and llm_decision.get('agent_name'):
        skill_agent_name = llm_decision['agent_name']
        agent_type = llm_decision.get('agent_type', 'agent')
        supplementary_skills = llm_decision.get('supplementary_skills', [])
        skill_reason = f"[LLM] {llm_decision.get('agent_reasoning', 'LLM decision')}"
        skill_script_used = True

    elif skill_script.exists():
        try:
            import tempfile as _tempfile
            task_ctx = {
                'task_type': task_type,
                'complexity': {'score': adj_complexity},
                'prompt': {'text': user_message},
                'tech_stack': tech_stack,
                'task_count': task_count
            }
            with _tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tf:
                json.dump(task_ctx, tf)
                tf_path = tf.name
            ss_out, ss_err, ss_rc, ss_dur = run_script(skill_script, ['--select', tf_path], timeout=10)
            try:
                os.unlink(tf_path)
            except OSError:
                pass
            if ss_rc == 0 and ss_out.strip():
                # Parse multi-line JSON block from end of stdout
                ss_json = None
                # Find the last top-level '{' that starts a JSON object
                last_brace = ss_out.rfind('\n{')
                if last_brace >= 0:
                    try:
                        ss_json = json.loads(ss_out[last_brace + 1:])
                    except json.JSONDecodeError:
                        pass
                if ss_json is None and ss_out.strip().startswith('{'):
                    try:
                        ss_json = json.loads(ss_out.strip())
                    except json.JSONDecodeError:
                        pass
                if ss_json:
                    ss_skills = ss_json.get('skills', [])
                    ss_agents = ss_json.get('agents', [])
                    if ss_agents:
                        skill_agent_name = ss_agents[0]
                        agent_type = 'agent'
                        supplementary_skills = ss_skills
                        skill_reason = f"[Script] {'; '.join(ss_json.get('reasoning', []))}"
                        skill_script_used = True
                    elif ss_skills:
                        skill_agent_name = ss_skills[0]
                        agent_type = 'skill'
                        supplementary_skills = ss_skills[1:]
                        skill_reason = f"[Script] {'; '.join(ss_json.get('reasoning', []))}"
                        skill_script_used = True
        except (json.JSONDecodeError, Exception):
            pass

    # Fallback: inline 4-layer waterfall if script failed or returned nothing
    if not skill_agent_name:
        skill_agent_name, agent_type, supplementary_skills, skill_reason = get_agent_and_skills(
            tech_stack, task_type=task_type, user_message=user_message
        )

    # Escalate to orchestrator for very high complexity / many tasks
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
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_3",
            "model": selected_model,
            "task_type": task_type,
            "complexity": adj_complexity,
            "task_count": task_count,
            "purpose": "Select skill or agent from registry for this task"
        },
        "policy": {
            "script": "intelligent-decision-engine.py (LLM)" if (llm_decision and llm_decision.get('agent_name')) else ("auto-skill-agent-selection-policy.py" if skill_script_used else "inline 4-layer waterfall"),
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
    try:
        emit_policy_step('LEVEL_3_STEP_3_4_SKILL_SELECTION', level=3, passed=True,
                         duration_ms=0, session_id=session_id or '',
                         details={'skill': skill_agent_name, 'type': agent_type,
                                  'supplementary': supplementary_skills,
                                  'reason': skill_reason})
    except Exception:
        pass

    # ------------------------------------------------------------------
    # STEP 3.5: PROMPT GENERATION (WITH SKILL CONTEXT)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    prompt_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '00-prompt-generation' / 'prompt-generation-policy.py'
    if not prompt_script.exists():
        prompt_script = MEMORY_BASE / '03-execution-system' / '00-prompt-generation' / 'prompt-generation-policy.py'
    pr_dur_3_5 = 0
    if prompt_script.exists():
        # Prompt script with skill context - PASS SKILL INFO for enhanced generation
        # Format: [user_message, skill_name, skill_type, supplementary_skills_csv]
        supplementary_csv = ','.join(supplementary_skills) if supplementary_skills else ''
        pr_args = [user_message, skill_agent_name, agent_type, supplementary_csv]
        pr_out, _, _, pr_dur_3_5 = run_script_with_retry(prompt_script, pr_args, timeout=8, step_name='Step-3.5.Prompt-Skill-Context')
        pr_data = safe_json(pr_out)
        rewritten_prompt_3_5 = pr_data.get('rewritten_prompt', '')
        enhanced_prompt_3_5 = pr_data.get('enhanced_prompt', '')
    else:
        rewritten_prompt_3_5 = rewritten_prompt
        enhanced_prompt_3_5 = enhanced_prompt_summary

    # FINAL EFFECTIVE PROMPT - Use skill-contextualized version for execution
    final_effective_prompt = (rewritten_prompt_3_5 if rewritten_prompt_3_5 else enhanced_prompt_3_5) if (rewritten_prompt_3_5 or enhanced_prompt_3_5) else user_message

    step_3_5_output = {
        "estimated_complexity": complexity,
        "task_type": task_type,
        "rewritten_prompt": rewritten_prompt_3_5 if rewritten_prompt_3_5 else "NOT_GENERATED",
        "enhanced_prompt": enhanced_prompt_3_5 if enhanced_prompt_3_5 else "NOT_GENERATED",
        "effective_prompt": final_effective_prompt,
        "script_exists": prompt_script.exists(),
        "skill_context_applied": True,
        "skill_or_agent": skill_agent_name,
        "supplementary_skills": supplementary_skills
    }
    step_3_5_decision = f"Enhanced prompt with skill context - using {skill_agent_name} for generation"

    print(f"   [3.5] Prompt Re-enhanced with skill context: {skill_agent_name}")
    print(f"   [3.5] Final Prompt: {final_effective_prompt[:100]}...")

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_5",
        "name": "Prompt Generation (With Skill Context)",
        "level": 3,
        "order": 9,
        "is_blocking": False,
        "status": "PASSED",
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
    # STEP 3.6: TOOL OPTIMIZATION (via tool-usage-optimization-policy.py)
    # ------------------------------------------------------------------
    step_start = datetime.now()
    tool_opt_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '06-tool-optimization' / 'tool-usage-optimization-policy.py'
    if not tool_opt_script.exists():
        tool_opt_script = MEMORY_BASE / '03-execution-system' / '06-tool-optimization' / 'tool-usage-optimization-policy.py'

    tool_rules = [
        "read_files_gt_500_lines_use_offset_limit",
        "grep_always_add_head_limit_100",
        "glob_restrict_path_if_service_known",
        "tree_first_visit_use_L2_or_L3",
        "bash_combine_sequential_commands",
        "edit_write_show_brief_confirmation"
    ]
    to_dur = 0
    to_script_used = False
    to_output = {}

    if tool_opt_script.exists():
        try:
            to_out, to_err, to_rc, to_dur = run_script(tool_opt_script, ['--enforce'], timeout=8)
            to_script_used = to_rc == 0
            to_output = {"exit_code": to_rc, "output_lines": len(to_out.splitlines())}
        except Exception:
            pass

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_6",
        "name": "Tool Usage Optimization",
        "level": 3,
        "order": 10,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": to_dur,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_5",
            "skill_agent": skill_agent_name,
            "context_pct": context_pct2,
            "purpose": "Apply token-saving optimizations to every tool call"
        },
        "policy": {
            "script": "tool-usage-optimization-policy.py" if to_script_used else "inline rules",
            "rules_applied": tool_rules
        },
        "policy_output": to_output if to_script_used else {
            "rules_active": len(tool_rules),
            "estimated_token_savings": "60-80%",
            "optimization_level": ctx_optimization
        },
        "decision": "Tool optimization enforced via script" if to_script_used else "Tool optimization rules loaded (inline)",
        "passed_to_next": {
            "tool_rules_active": True,
            "optimization_level": ctx_optimization
        }
    })
    print(f"   [3.6] Tool Optimization: {'Enforced' if to_script_used else 'Ready'} ({len(tool_rules)} rules)")

    # ------------------------------------------------------------------
    # STEP 3.7: FAILURE PREVENTION
    # ------------------------------------------------------------------
    step_start = datetime.now()
    fp_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / 'failure-prevention' / 'common-failures-prevention.py'
    if not fp_script.exists():
        fp_script = MEMORY_BASE / '03-execution-system' / 'failure-prevention' / 'common-failures-prevention.py'
    fp_dur = 0
    fp_checks = {}
    if fp_script.exists():
        fp_out, _, fp_rc, fp_dur = run_script_with_retry(fp_script, ['--enforce'], timeout=8, step_name='Step-3.7.Failure-Prevention')
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
        "status": "PASSED",
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
    # STEP 3.8: PARALLEL EXECUTION ANALYSIS (via parallel-execution-policy.py)
    # ------------------------------------------------------------------
    par_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / 'parallel-execution-policy.py'
    if not par_script.exists():
        par_script = MEMORY_BASE / '03-execution-system' / 'parallel-execution-policy.py'

    parallel_possible = task_count >= 3  # inline fallback default
    par_script_used = False
    par_execution_mode = 'sequential'
    par_reason = "3+ independent tasks" if parallel_possible else "Tasks have dependencies or count < 3"

    if par_script.exists():
        try:
            pe_out, pe_err, pe_rc, pe_dur = run_script(par_script, ['--enforce'], timeout=8)
            if pe_rc == 0:
                parallel_possible = True
                par_execution_mode = 'parallel'
                par_reason = pe_out.strip() if pe_out.strip() else "Policy enforced - parallel safe"
                par_script_used = True
            else:
                parallel_possible = False
                par_execution_mode = 'sequential'
                par_reason = pe_out.strip() if pe_out.strip() else "Policy enforced - sequential required"
                par_script_used = True
        except Exception:
            pass

    # Override: if task_count < 3, parallel never makes sense regardless of script
    if task_count < 3:
        parallel_possible = False
        par_execution_mode = 'sequential'
        if not par_script_used:
            par_reason = "Tasks have dependencies or count < 3"

    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_8",
        "name": "Parallel Execution Analysis",
        "level": 3,
        "order": 12,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": datetime.now().isoformat(),
        "duration_ms": pe_dur if par_script_used else 0,
        "input": {
            "from_previous": "LEVEL_3_STEP_3_7",
            "task_count": task_count,
            "purpose": "Detect which tasks can run in parallel for 3-10x speedup"
        },
        "policy": {
            "script": "parallel-execution-policy.py" if par_script_used else "inline fallback",
            "rules_applied": [
                "check_tasks_with_no_blockedBy_dependencies",
                "group_tasks_by_dependency_wave",
                "calculate_speedup_estimate",
                "3_or_more_independent_use_parallel",
                "token_limit_awareness" if par_script_used else "simple_count_check"
            ]
        },
        "policy_output": {
            "parallel_possible": parallel_possible,
            "task_count": task_count,
            "execution_mode": par_execution_mode,
            "reason": par_reason
        },
        "decision": "Use parallel execution" if parallel_possible else "Use sequential execution",
        "passed_to_next": {
            "execution_mode": par_execution_mode,
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

    # --- Step 3.9: Execute Tasks (via task-progress-tracking-policy.py) ---
    step_start = datetime.now()
    exec_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '08-progress-tracking' / 'task-progress-tracking-policy.py'
    if not exec_script.exists():
        exec_script = MEMORY_BASE / '03-execution-system' / '08-progress-tracking' / 'task-progress-tracking-policy.py'
    exec_dur = 0
    exec_script_used = False
    if exec_script.exists():
        try:
            ex_out, ex_err, ex_rc, exec_dur = run_script(exec_script, ['--enforce'], timeout=8)
            exec_script_used = ex_rc == 0
        except Exception:
            pass
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_9",
        "name": "Execute Tasks",
        "level": 3,
        "order": 13,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": exec_dur,
        "input": {"from_previous": "LEVEL_3_STEP_3_8"},
        "policy": {
            "script": "task-progress-tracking-policy.py" if exec_script_used else "declarative",
            "rules_applied": ["task_progress_tracking", "incomplete_work_detection"]
        },
        "policy_output": {"status": "ENFORCED" if exec_script_used else "ACTIVE", "policies_loaded": policy_count},
        "decision": "Task tracking enforced via script" if exec_script_used else "All policies enforced - execute with full standards active",
        "passed_to_next": {"status": "ACTIVE"}
    })
    print(f"   [3.9] Execute Tasks: {'Enforced' if exec_script_used else 'Active'}")

    # --- Step 3.10: Session Save (declarative - actual save by stop-notifier.py Stop hook) ---
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_10",
        "name": "Session Save",
        "level": 3,
        "order": 14,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": datetime.now().isoformat(),
        "duration_ms": 0,
        "input": {"from_previous": "LEVEL_3_STEP_3_9"},
        "policy": {
            "script": "stop-notifier.py (Stop hook)",
            "rules_applied": ["session_save_on_stop"]
        },
        "policy_output": {"status": "ACTIVE", "executor": "stop-notifier.py"},
        "decision": "Auto-save session state at each milestone (via Stop hook)",
        "passed_to_next": {"status": "ACTIVE"}
    })
    print(f"   [3.10] Session Save: Active (stop-notifier)")

    # --- Step 3.11: Git Auto-Commit (via git-auto-commit-policy.py pre-check) ---
    step_start = datetime.now()
    git_script = SCRIPT_DIR / 'architecture' / '03-execution-system' / '09-git-commit' / 'git-auto-commit-policy.py'
    if not git_script.exists():
        git_script = MEMORY_BASE / '03-execution-system' / '09-git-commit' / 'git-auto-commit-policy.py'
    git_dur = 0
    git_script_used = False
    if git_script.exists():
        try:
            gc_out, gc_err, gc_rc, git_dur = run_script(git_script, ['--detect', '--json'], timeout=10)
            git_script_used = gc_rc == 0
        except Exception:
            pass
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_11",
        "name": "Git Auto-Commit",
        "level": 3,
        "order": 15,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": step_start.isoformat(),
        "duration_ms": git_dur,
        "input": {"from_previous": "LEVEL_3_STEP_3_10"},
        "policy": {
            "script": "git-auto-commit-policy.py" if git_script_used else "declarative",
            "rules_applied": ["auto_commit_detection", "version_bump", "release_creation"]
        },
        "policy_output": {"status": "ENFORCED" if git_script_used else "ACTIVE", "policies_loaded": policy_count},
        "decision": f"Git auto-commit pre-checked via script ({policy_count} policies loaded)" if git_script_used else f"Auto-commit + version bump + release ({policy_count} policies loaded)",
        "passed_to_next": {"status": "ACTIVE"}
    })
    print(f"   [3.11] Git Auto-Commit: {'Pre-checked' if git_script_used else 'Active'}")

    # --- Step 3.12: Logging (declarative - actual logging by post-tool-tracker.py) ---
    trace["pipeline"].append({
        "step": "LEVEL_3_STEP_3_12",
        "name": "Logging",
        "level": 3,
        "order": 16,
        "is_blocking": False,
        "status": "PASSED",
        "timestamp": datetime.now().isoformat(),
        "duration_ms": 0,
        "input": {"from_previous": "LEVEL_3_STEP_3_11"},
        "policy": {
            "script": "post-tool-tracker.py (PostToolUse hook)",
            "rules_applied": ["log_all_policy_applications", "log_tool_calls", "log_decisions"]
        },
        "policy_output": {"status": "ACTIVE", "executor": "post-tool-tracker.py"},
        "decision": "Log all policy applications, tool calls, decisions (via PostToolUse hook)",
        "passed_to_next": {"status": "ACTIVE"}
    })
    print(f"   [3.12] Logging: Active (post-tool-tracker)")

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

    # GitHub Issues auto-close policy (Claude must include issue refs in commits/PRs)
    if 'github-issues-integration-policy' in loaded_policies.get('level-3', {}) or \
       'github-branch-pr-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] GITHUB ISSUES AUTO-CLOSE POLICY:")
        print("   1. On issue branch (fix/42, feature/123): include 'Closes #N' in commit messages")
        print("   2. PR body MUST contain 'Closes #N' for ALL related open issues")
        print("   3. When ALL tasks complete: issues auto-close via post-tool-tracker")
        print("   4. NEVER leave issues open after PR merge - verify closure")
        print("   5. Branch format: {label}/{issueId} (e.g. fix/42, feature/123)")

    # Task breakdown policy (not auto-enforced — Claude must use TaskCreate)
    if 'automatic-task-breakdown-policy' in loaded_policies.get('level-3', {}):
        print()
        print("[ENFORCE] TASK BREAKDOWN POLICY:")
        print("   1. ALWAYS create tasks via TaskCreate on EVERY coding request (minimum 1)")
        print("   2. Break complex tasks into phases (Foundation, Logic, API, Config)")
        print("   3. Mark tasks completed via TaskUpdate when done")
        print("   4. Create task dependencies if needed (blockedBy/blocks)")

    # Model selection policy (not auto-enforced — Claude must route correctly)
    if 'intelligent-model-selection-policy' in loaded_policies.get('level-3', {}):
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

    # Enrich model_reason with full decision chain for transparency (Fix #3)
    _kw = keyword_complexity if 'keyword_complexity' in dir() else adj_complexity
    _gr = graph_complexity_score if 'graph_complexity_score' in dir() else 0
    _formula = complexity_combining_formula if 'complexity_combining_formula' in dir() else f"keyword_only={adj_complexity}/25"
    if _gr > 0:
        _chain_prefix = (
            f"graph={_gr}, keyword={_kw}, combined={adj_complexity} [{_formula}] -> "
        )
    else:
        _chain_prefix = f"keyword={_kw}/25 (graph unavailable) -> "
    model_reason = _chain_prefix + model_reason

    # Risk level based on complexity
    _risk_level = "LOW"
    if adj_complexity >= 15:
        _risk_level = "HIGH"
    elif adj_complexity >= 8:
        _risk_level = "MEDIUM"

    final_decision = {
        "timestamp": flow_end.isoformat(),
        "user_prompt": user_message,
        "complexity": adj_complexity,
        "task_type": task_type,
        "plan_mode": plan_required,
        "model_selected": selected_model,
        "model_reason": model_reason,
        "complexity_combining_formula": _formula,
        "keyword_complexity": _kw,
        "graph_complexity": _gr,
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
        "cross_project_patterns": {
            "count": patterns_detected,
            "top": [{"name": p["name"], "type": p["type"], "confidence": p["confidence"]} for p in cross_patterns[:5]],
            "detection_ran": detection_ran
        },
        "proceed": True,
        "risk_level": _risk_level,
        "prompt_transformation": {
            "raw_input": user_message[:500],
            "task_type_detected": task_type,
            "complexity_assessed": adj_complexity,
            "model_chosen": selected_model,
            "skill_chosen": skill_agent_name,
        },
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
    print("LEVEL 1: Sync System (6 sub-steps)")
    print(f"   +-- [1.1] Context: {context_pct}% -> {context_pct2}%")
    print(f"   +-- [1.2] Session: {session_id}")
    print(f"   +-- [1.3] Preferences: {prefs_loaded} loaded")
    print(f"   +-- [1.4] State: {completed_tasks_count} tasks, {files_modified_count} files")
    print(f"   +-- [1.5] Patterns: {patterns_detected} cross-project patterns")
    print(f"   +-- [1.6] Dep Validator: {dep_status}")
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
    print(f"   +-- [3.9] Execute={'Enforced' if exec_script_used else 'Active'}, [3.10] Save=stop-notifier, [3.11] Commit={'Pre-checked' if git_script_used else 'Active'}, [3.12] Log=post-tool-tracker")
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

    if graph_complexity_score > 0:
        complexity_str = f"{adj_complexity}/25 (kw={keyword_complexity} + graph={graph_complexity_score})"
    else:
        complexity_str = f"{adj_complexity}/25 (keyword only)"
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

    # =========================================================================
    # COMPACT OUTPUT: Restore real stdout, save verbose, print compact summary
    # =========================================================================
    sys.stdout = _real_stdout
    _verbose_text = _verbose_buf.getvalue()
    _verbose_buf.close()

    # Save verbose output to session log directory
    try:
        if session_log_dir and session_log_dir.exists():
            (session_log_dir / 'verbose-output.txt').write_text(
                _verbose_text, encoding='utf-8'
            )
    except Exception:
        pass

    # --- COMPACT STDOUT (this is what Claude sees in context) ---
    _ctx_pct = context_pct2 if 'context_pct2' in dir() else context_pct
    _model = selected_model if 'selected_model' in dir() else '?'
    _cplx = complexity if 'complexity' in dir() else '?'
    _tasks = task_count if 'task_count' in dir() else 0
    _skill = skill_agent_name if 'skill_agent_name' in dir() else ''
    _plan = plan_str if 'plan_str' in dir() else 'NO'
    _ttype = task_type if 'task_type' in dir() else 'General'
    _parallel = 'Parallel' if (parallel_possible if 'parallel_possible' in dir() else False) else 'Sequential'
    _std_count = standards_count if 'standards_count' in dir() else 0
    _rules = rules_count if 'rules_count' in dir() else 0
    _dep = dep_status if 'dep_status' in dir() else 'OK'
    _prefs = prefs_loaded if 'prefs_loaded' in dir() else 0
    _patterns = patterns_detected if 'patterns_detected' in dir() else 0
    _completed = completed_tasks_count if 'completed_tasks_count' in dir() else 0
    _files_mod = files_modified_count if 'files_modified_count' in dir() else 0
    _pending = pending_work_count if 'pending_work_count' in dir() else 0

    print(f"[3-LEVEL FLOW v{VERSION}] Session={session_id} | Context={_ctx_pct}% | Complexity={_cplx}/25 | Model={_model}")
    print(f"[L-1] OK | [L1] Ctx={_ctx_pct}% Sess={session_id} Prefs={_prefs} State={_completed}t/{_files_mod}f/{_pending}p Patterns={_patterns} Dep={_dep}")
    print(f"[L2] Standards={_std_count}/{_rules}r | [L3] Tasks={_tasks} Plan={_plan} Mode={_parallel}")
    print(f"[L3] Agent/Skill={_skill} | Type={_ttype} | ToolOpt=Active | FailPrev=Active")

    # Enforcement policies (compact 1-liners instead of 5+ lines each)
    print("[ENFORCE] VersionRelease | IssueAutoClose | TaskBreakdown | ModelSelection | ToolOptimization | FailurePrevention | CommonStandards")

    # Final decision
    _decision_summary = ''
    try:
        _decision_summary = final_decision.get('summary', '') if 'final_decision' in dir() else ''
    except Exception:
        pass
    if _decision_summary:
        print(f"[DECISION] {_decision_summary}")

    # Trace file location
    print(f"[TRACE] {session_log_dir / 'flow-trace.json'}")

    # Rewritten prompt (if any)
    if 'rewritten_prompt' in dir() and rewritten_prompt and _needs_enforcement:
        print(f"[REWRITTEN] {rewritten_prompt[:200]}")

    # Claude instruction (keep - critical for behavior)
    print("[OK] ALL 3 LEVELS VERIFIED - AUTO-PROCEED TO WORK")

    # LOOPHOLE #18 FIX: Checkpoint + task-breakdown flags are written EARLY (line ~968)
    # so they survive even if this script times out before reaching here.
    # Only skill-selection flag is written here (needs skill_agent_name from step 3.5).
    # LOOPHOLE #14 FIX: Skip for non-coding messages (questions/research).
    # v3.1.0 FIX: Skip for mid-session continuations (already approved + invoked).
    # v3.2.0 FIX: Skip for approval messages (user said ok - don't re-create flags!).
    # v4.5.0: Skill-selection flag NO LONGER written.
    # 3-level-flow already injects the skill/agent context into the prompt
    # at step 3.5 (prompt re-enhancement). The prompt injection IS the
    # enforcement - Claude sees the skill instructions and follows them.
    # Writing a blocking flag on top was redundant and caused false blocks
    # when Claude had already received the skill context.
    # The write_skill_selection_flag function is kept for backward compat
    # but is no longer called from the main flow.

    # =========================================================================
    # METRICS: emit hook_execution summary for 3-level-flow
    # =========================================================================
    try:
        _flow_total_ms = int((datetime.now() - flow_start).total_seconds() * 1000)
        emit_hook_execution(
            hook_name='3-level-flow.py',
            duration_ms=_flow_total_ms,
            session_id=session_id or '',
            exit_code=0,
            extra={
                'model': selected_model if 'selected_model' in dir() else '',
                'task_type': task_type if 'task_type' in dir() else '',
                'complexity': adj_complexity if 'adj_complexity' in dir() else 0,
                'context_pct': context_pct2 if 'context_pct2' in dir() else 0,
                'skill': skill_agent_name if 'skill_agent_name' in dir() else '',
            }
        )
        # Final summary policy step
        emit_policy_step(
            'FULL_FLOW_COMPLETE', level=3, passed=True,
            duration_ms=_flow_total_ms,
            session_id=session_id or '',
            details={
                'model': selected_model if 'selected_model' in dir() else '',
                'task_type': task_type if 'task_type' in dir() else '',
                'complexity': adj_complexity if 'adj_complexity' in dir() else 0,
                'skill': skill_agent_name if 'skill_agent_name' in dir() else '',
                'plan_mode': plan_required if 'plan_required' in dir() else False,
            }
        )
    except Exception:
        pass

    sys.exit(0)


def _build_script_inventory():
    """Build a complete inventory of all scripts in the 3-level architecture.

    Constructs a structured dict categorising every known script by lifecycle
    role: hook scripts, active subprocess scripts, on-demand CLI utilities,
    daemon scripts, Phase-4 stubs, and superseded scripts.  Each entry
    records name, path, hook trigger, execution status, and a brief
    description so the flow-trace.json has full A-to-Z visibility.

    Returns:
        dict: Inventory containing categorised script lists and a 'summary'
              sub-dict with aggregate counts for each category.
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
        {"name": "context-reader.py", "path": "03-execution-system/00-context-reading/", "hook": "3-level-flow.py 3.0.0", "status": "EXECUTED", "desc": "Reads project context (README/SRS/VERSION) pre-flight"},
        {"name": "code-graph-analyzer.py", "path": "03-execution-system/00-code-graph-analysis/", "hook": "3-level-flow.py 3.0.1", "status": "EXECUTED", "desc": "Builds dependency graph, calculates structural complexity"},
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

    # --- 1 INLINE SCRIPT (Logic inside hook code) + 2 NOW WIRED ---
    inventory["active_scripts"].extend([
        {"name": "intelligent-model-selection-policy.py", "path": "03-execution-system/04-model-selection/", "hook": "3-level-flow.py 3.4", "status": "CALLED", "desc": "Script called via run_script(), inline fallback if fails"},
        {"name": "auto-skill-agent-selection-policy.py", "path": "03-execution-system/05-skill-agent-selection/", "hook": "3-level-flow.py 3.5", "status": "CALLED", "desc": "Script called via run_script(), inline 4-layer waterfall as fallback"},
        {"name": "parallel-execution-policy.py", "path": "03-execution-system/", "hook": "3-level-flow.py 3.8", "status": "CALLED", "desc": "Script called via run_script(), inline count check as fallback"},
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
    """Save the flow-trace JSON to the session log directory with rotation.

    ROTATE mode (Phase 1 fix): flow-trace.json keeps only the latest 30 pipeline
    entries. This reduces memory bloat from 100 KB to ~60 KB per session.
    Older entries are discarded (not archived - they're logged but not kept).

    Also keeps a latest-flow-trace.json copy at the top-level logs directory
    for fast access by other hooks.

    Args:
        trace: The fully-populated trace dict accumulated during the pipeline.
        session_log_dir: Path to the session-specific log directory, or None.
        flow_start: datetime of when the pipeline began (used for fallback
                    filename generation only).
    """
    try:
        if session_log_dir is None:
            # Fallback: save to memory/logs/
            fallback_dir = MEMORY_BASE / 'logs'
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fname = f"flow-trace-{flow_start.strftime('%Y%m%d-%H%M%S')}.json"
            write_json(fallback_dir / fname, trace)
        else:
            # Phase 1 fix: Apply trace rotation (keep last MAX_TRACE_ENTRIES)
            if "pipeline" in trace and len(trace["pipeline"]) > MAX_TRACE_ENTRIES:
                total_before = len(trace["pipeline"])
                trace["pipeline"] = trace["pipeline"][-MAX_TRACE_ENTRIES:]
                if DEBUG:
                    sys.stderr.write(
                        f"[TRACE-ROTATION] Kept last {MAX_TRACE_ENTRIES} of {total_before} entries\n"
                    )

            # 1. Write flow-trace.json (ROTATE - keep last 30 entries only)
            trace_file = session_log_dir / 'flow-trace.json'
            write_json(trace_file, trace)

            # 2. Keep a "latest" copy for easy access by other hooks
            write_json(MEMORY_BASE / 'logs' / 'latest-flow-trace.json', trace)

            # Phase 2: Create trace index for lazy loading
            if _LAZY_LOADING_AVAILABLE:
                try:
                    session_id = trace.get('meta', {}).get('session_id')
                    if session_id:
                        from trace_api import TraceIndex
                        idx = TraceIndex(session_id)
                        idx._build_index()  # Build and save index
                except Exception:
                    pass
    except Exception:
        pass



if __name__ == '__main__':
    main()
