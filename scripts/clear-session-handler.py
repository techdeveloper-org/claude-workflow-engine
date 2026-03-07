#!/usr/bin/env python3
"""
Script Name: clear-session-handler.py
Version: 3.2.0 (Flag auto-expiry cleanup - Loophole #10)
Last Modified: 2026-03-05
Description: Detects /clear command usage via UserPromptSubmit hook.
             Compares current transcript message count vs last known count.
             If count decreased or transcript changed = /clear was used.
             Action: Save old session, create new one.

             MULTI-WINDOW FIX: Each window gets isolated state file (PID-based)
             to prevent conflicts across multiple Claude Code instances.

Detection Logic:
  - Tracks transcript_path + message count in ~/.claude/.hook-state-{PID}.json (WINDOW-SPECIFIC)
  - If msg_count < last_msg_count  -> /clear detected (count dropped)
  - If transcript_path changed     -> new conversation/window detected
  - If msg_count == 0 + no prior   -> fresh start

Voice: Writes .session-start-voice flag for stop-notifier.py to speak.
       Does NOT speak directly - single voice pipeline via stop-notifier.

Windows-Safe: No Unicode chars (ASCII only, cp1252 compatible)
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Windows: ASCII-only output (no Unicode/emojis)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Metrics emitter (fire-and-forget, never blocks)
try:
    _me_dir = os.path.dirname(os.path.abspath(__file__))
    if _me_dir not in sys.path:
        sys.path.insert(0, _me_dir)
    from metrics_emitter import emit_hook_execution
    _METRICS_AVAILABLE = True
except Exception:
    def emit_hook_execution(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""
    _METRICS_AVAILABLE = False

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False
    print("[WARN] Policy tracking not available - continuing without tracking")

# Track hook start time
_HOOK_START = datetime.now()

# File locking for shared JSON state (Loophole #19)
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


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

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (MEMORY_BASE, SCRIPTS_DIR, CURRENT_DIR, FLAG_DIR,
                           SESSION_START_FLAG, CURRENT_SESSION_FILE)
    SESSIONS_DIR = MEMORY_BASE / 'sessions'
    CLEAR_LOG = MEMORY_BASE / 'logs' / 'clear-events.log'
    SESSION_START_VOICE_FLAG = SESSION_START_FLAG  # Use imported constant
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    MEMORY_BASE = Path.home() / '.claude' / 'memory'
    SCRIPTS_DIR = Path.home() / '.claude' / 'scripts'
    CURRENT_DIR = SCRIPTS_DIR if SCRIPTS_DIR.exists() else (MEMORY_BASE / 'current')
    SESSIONS_DIR = MEMORY_BASE / 'sessions'
    # Per-project session file for multi-window isolation
    try:
        _csh_dir = os.path.dirname(os.path.abspath(__file__))
        if _csh_dir not in sys.path:
            sys.path.insert(0, _csh_dir)
        from project_session import get_project_session_file
        CURRENT_SESSION_FILE = get_project_session_file()
    except ImportError:
        CURRENT_SESSION_FILE = MEMORY_BASE / '.current-session.json'
    CLEAR_LOG = MEMORY_BASE / 'logs' / 'clear-events.log'
    SESSION_START_VOICE_FLAG = Path.home() / '.claude' / '.session-start-voice'
    FLAG_DIR = Path.home() / '.claude'

# MULTI-WINDOW FIX: Get window-specific hook state file via isolator
HOOK_STATE_FILE = None  # Initialized in _init_window_isolation()

# Flag auto-expiry configuration (Loophole #10)
FLAG_EXPIRY_MINUTES = 60   # Auto-delete flags older than 60 minutes
FLAG_CLEANUP_ON_STARTUP = True


# =============================================================================
# FLAG AUTO-EXPIRY UTILITIES (Loophole #10)
# =============================================================================

def _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES):
    """Remove flag files in FLAG_DIR older than max_age_minutes.

    Scans ~/.claude/ for all .*.json flag files and deletes any whose
    filesystem modification time exceeds the expiry threshold.

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

    Checks file modification time and, if present, the JSON created_at
    field.  Stale files are deleted before returning False.

    Args:
        flag_path: str or Path to the flag JSON file.
        max_age_minutes: Maximum allowed age in minutes (default 60).

    Returns:
        bool: True if fresh and usable; False if expired/missing.
    """
    try:
        path = Path(flag_path)
        if not path.exists():
            return False

        mod_time = datetime.fromtimestamp(path.stat().st_mtime)
        age_minutes = (datetime.now() - mod_time).total_seconds() / 60

        if age_minutes > max_age_minutes:
            path.unlink(missing_ok=True)
            return False

        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if 'created_at' in data:
                created = datetime.fromisoformat(data['created_at'])
                json_age = (datetime.now() - created).total_seconds() / 60
                if json_age > max_age_minutes:
                    path.unlink(missing_ok=True)
                    return False
        except Exception:
            pass

        return True
    except Exception:
        return False


# =============================================================================
# WINDOW ISOLATION (Multi-Window Fix)
# =============================================================================

def _init_window_isolation():
    """Initialize window/PID-specific isolation."""
    global HOOK_STATE_FILE
    try:
        # Import from session-window-isolator
        from session_window_isolator import get_window_state_file, register_window
        HOOK_STATE_FILE = get_window_state_file()
        # Register this window for lifecycle tracking
        register_window('session-unknown')  # Will be updated after session is known
        log_event(f"[INIT] Window isolation active: PID={os.getpid()}, state_file={HOOK_STATE_FILE.name}")
    except ImportError:
        # Fallback if isolator not available (backwards compatibility)
        HOOK_STATE_FILE = Path.home() / '.claude' / '.hook-state.json'
        log_event(f"[WARN] session-window-isolator not found, using shared state: {HOOK_STATE_FILE}")


# =============================================================================
# LOGGING
# =============================================================================

def log_event(msg):
    """Append a timestamped event message to the clear-events.log file.

    Creates parent directories automatically.  All content must be ASCII-safe
    (cp1252 compatible on Windows).  Errors are silently swallowed.

    Args:
        msg (str): ASCII-safe message to append.
    """
    CLEAR_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(CLEAR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# HOOK STDIN
# =============================================================================

def read_hook_stdin():
    """Read JSON data piped by the Claude Code UserPromptSubmit hook via stdin.

    Uses select() to avoid blocking indefinitely when stdin has no data.
    Returns {} if stdin is empty or unavailable.

    Returns:
        dict: Parsed hook payload, or {} on any read or parse error.
    """
    try:
        import select

        if sys.stdin.isatty():
            return {}

        # Use select to check if data is ready (with 0.1s timeout)
        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0.1)
            if readable:
                raw = sys.stdin.read()
                if raw and raw.strip():
                    return json.loads(raw.strip())
        except (OSError, IOError):
            # select() not available on this platform
            pass

    except Exception:
        pass
    return {}


# =============================================================================
# TRANSCRIPT ANALYSIS
# =============================================================================

def count_transcript_messages(transcript_path):
    """Count user and assistant messages in the Claude Code transcript file.

    Handles both JSONL format (one JSON object per line, the Claude Code
    default) and single-JSON-array format.  Returns special values for
    unreadable or empty files.

    Args:
        transcript_path (str or Path): Path to the transcript file.  May be
                                       None or empty for a fresh session.

    Returns:
        int:  -1 if the file cannot be read or state is unknown.
               0 if the file is empty or does not exist (fresh conversation).
              N (> 0) for N user/assistant messages found.
             99 if the file has content but cannot be parsed (assume messages).
    """
    if not transcript_path:
        return -1

    path = Path(transcript_path)

    if not path.exists():
        return 0  # No file = definitely fresh

    try:
        content = path.read_text(encoding='utf-8', errors='replace').strip()
        if not content:
            return 0  # Empty file = fresh

        count = 0

        # Try JSONL format (one JSON object per line) - Claude Code default
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if isinstance(msg, dict):
                    role = msg.get('role', '') or msg.get('type', '')
                    if role in ('user', 'assistant', 'human'):
                        count += 1
            except Exception:
                pass

        if count > 0:
            return count

        # Try single JSON array
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return len([m for m in data
                            if isinstance(m, dict)
                            and m.get('role') in ('user', 'assistant', 'human')])
            if isinstance(data, dict):
                msgs = data.get('messages', data.get('conversation', []))
                return len([m for m in msgs
                            if isinstance(m, dict)
                            and m.get('role') in ('user', 'assistant', 'human')])
        except Exception:
            pass

        # File exists and has content but can't parse = assume has messages
        return 99

    except Exception:
        return -1


# =============================================================================
# STATE TRACKING
# =============================================================================

def read_state():
    """Read the PID-isolated hook state file with Windows file locking.

    HOOK_STATE_FILE is set by _init_window_isolation() to a window-specific
    path so multiple Claude Code windows do not interfere with each other.

    Returns:
        dict: Persisted state containing 'last_transcript_path',
              'last_msg_count', and 'updated_at', or {} when the file is
              missing or unreadable.
    """
    if not HOOK_STATE_FILE.exists():
        return {}
    try:
        with open(HOOK_STATE_FILE, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data
    except Exception:
        return {}


def write_state(transcript_path, msg_count):
    """Persist the current transcript state to the PID-isolated hook state file.

    Creates parent directories if needed.  Uses _lock_file/_unlock_file to
    prevent data corruption from concurrent hook invocations.

    Args:
        transcript_path (str or Path): Current transcript file path.
        msg_count (int): Current message count in the transcript.
    """
    state = {
        'last_transcript_path': str(transcript_path) if transcript_path else '',
        'last_msg_count': msg_count,
        'updated_at': datetime.now().isoformat()
    }
    try:
        HOOK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HOOK_STATE_FILE, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(state, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass


def detect_clear(current_transcript_path, current_msg_count):
    """Compare current transcript state with the last persisted state to detect /clear.

    Four detection cases are checked in order:
      1. No previous state + msg count <= 1  -> first ever conversation.
      2. Transcript file path changed        -> new conversation or window.
      3. Message count dropped               -> /clear was used.
      4. Same path, was non-empty, now empty -> transcript emptied.

    Args:
        current_transcript_path (str or Path): Path to the active transcript.
        current_msg_count (int): Number of messages found in the transcript.

    Returns:
        tuple: (is_fresh, reason_string) where is_fresh is True when a session
               boundary is detected and reason_string describes the cause.
    """
    state = read_state()
    last_transcript = state.get('last_transcript_path', '')
    last_count = state.get('last_msg_count', -1)

    # Case 1: No previous state at all - fresh start
    if not last_transcript and current_msg_count <= 1:
        return True, 'first_ever_conversation'

    # Case 2: Transcript file changed - new conversation/window
    if (last_transcript
            and current_transcript_path
            and str(current_transcript_path) != last_transcript):
        return True, f'transcript_changed_from_{Path(last_transcript).name}_to_{Path(str(current_transcript_path)).name}'

    # Case 3: Message count dropped - /clear was used
    if (last_count != -1
            and current_msg_count != -1
            and current_msg_count < last_count):
        return True, f'msg_count_dropped_from_{last_count}_to_{current_msg_count}'

    # Case 4: Transcript empty with same path - cleared
    if (last_transcript
            and current_transcript_path
            and str(current_transcript_path) == last_transcript
            and current_msg_count == 0
            and last_count > 0):
        return True, f'transcript_emptied_was_{last_count}_now_0'

    return False, 'ongoing_conversation'


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def get_current_session_id():
    """Read the active session ID from CURRENT_SESSION_FILE.

    Returns:
        str or None: Session ID string, or None when the file is missing or
                     the 'current_session_id' key is absent.
    """
    if not CURRENT_SESSION_FILE.exists():
        return None
    try:
        with open(CURRENT_SESSION_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('current_session_id')
    except Exception:
        return None


def close_current_session(session_id):
    """Mark an active session as COMPLETED and delete the current-session marker.

    Updates the session's JSON file with end_time and status='COMPLETED', then
    deletes CURRENT_SESSION_FILE so 3-level-flow.py creates a fresh session on
    the next user message.  All file operations use _lock_file/_unlock_file.

    Args:
        session_id (str): Session identifier to close.

    Returns:
        bool: True after attempting to close; False when session_id is falsy.
    """
    if not session_id:
        return False

    # Update session JSON file with end time
    session_file = SESSIONS_DIR / f'{session_id}.json'
    if session_file.exists():
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)

            data['end_time'] = datetime.now().isoformat()
            data['status'] = 'COMPLETED'
            data['closed_reason'] = 'clear_command_detected_by_hook'

            with open(session_file, 'w', encoding='utf-8') as f:
                _lock_file(f)
                json.dump(data, f, indent=2)
                _unlock_file(f)

            log_event(f"Session closed and saved: {session_id}")
        except Exception as e:
            log_event(f"Error updating session file {session_id}: {e}")

    # Delete .current-session.json so 3-level-flow creates a fresh session
    if CURRENT_SESSION_FILE.exists():
        try:
            CURRENT_SESSION_FILE.unlink()
            log_event(f"Removed .current-session.json (cleared for {session_id})")
        except Exception as e:
            log_event(f"Error removing current session file: {e}")

    return True


def write_voice_flag(message):
    """Write the session-start voice flag for stop-notifier.py to consume.

    Uses the single voice pipeline: flag -> stop-notifier -> voice-notifier ->
    audio.  This function writes the PID-isolated flag path so only the Stop
    hook of THIS window picks it up.

    Args:
        message (str): ASCII-safe human-readable text for the voice greeting.
    """
    try:
        SESSION_START_VOICE_FLAG.write_text(message, encoding='utf-8')
        log_event(f"[voice] Flag written for stop-notifier: {message[:60]}")
    except Exception as e:
        log_event(f"[voice] Failed to write voice flag: {e}")


def get_previous_session_context(session_id):
    """
    Read the previous session's flow-trace.json to build a context summary.
    1. Printed to stdout so Claude sees it on the first message after /clear.
    2. Written to .previous-session-context.json so 3-level-flow.py can read it
       (state file handoff instead of stdout-only).
    Returns formatted string or None if no data available.
    """
    if not session_id:
        return None

    logs_dir = MEMORY_BASE / 'logs' / 'sessions' / session_id
    flow_trace = logs_dir / 'flow-trace.json'

    if not flow_trace.exists():
        log_event(f"No flow-trace found for session {session_id} at {flow_trace}")
        return None

    try:
        with open(flow_trace, 'r', encoding='utf-8') as f:
            data = json.load(f)

        user_input = data.get('user_input', {})
        final_decision = data.get('final_decision', {})
        meta = data.get('meta', {})

        prompt = user_input.get('prompt', 'Unknown')
        task_type = final_decision.get('task_type', 'Unknown')
        skill = final_decision.get('skill_or_agent', 'Unknown')
        complexity = final_decision.get('complexity', '?')
        model = final_decision.get('model_selected', 'Unknown')
        started_at = meta.get('flow_start', '')[:19].replace('T', ' ')

        # Truncate long prompts
        if len(prompt) > 300:
            prompt = prompt[:300] + '...'

        lines = [
            '',
            '[PREVIOUS SESSION CONTEXT - AUTO-LOADED AFTER /clear]',
            '=' * 65,
            f'Session ID  : {session_id}',
            f'Started At  : {started_at}',
            f'Task Type   : {task_type} (Complexity: {complexity})',
            f'Skill/Agent : {skill}',
            f'Model Used  : {model}',
            f'Last Prompt : {prompt}',
            '=' * 65,
            '[CONTINUITY] Resume work from where the previous session left off.',
            '[CONTINUITY] The user did /clear but you can reference this context.',
            '',
        ]

        # CONTEXT HANDOFF: Write state file for 3-level-flow to read
        # This fixes the context loss between clear-session-handler and 3-level-flow
        try:
            handoff_file = FLAG_DIR / '.previous-session-context.json'
            handoff_data = {
                'previous_session_id': session_id,
                'task_type': task_type,
                'complexity': complexity,
                'skill': skill,
                'model': model,
                'last_prompt': prompt,
                'started_at': started_at,
                'written_at': datetime.now().isoformat(),
            }
            handoff_file.write_text(json.dumps(handoff_data, indent=2), encoding='utf-8')
            log_event(f"Context handoff file written: {handoff_file}")
        except Exception as e:
            log_event(f"Warning: Could not write context handoff file: {e}")

        log_event(f"Previous session context loaded for {session_id}")
        return '\n'.join(lines)

    except Exception as e:
        log_event(f"Error reading previous session context: {e}")
        return None


def create_new_session(reason=''):
    """Create a new session by calling session-id-generator.py.

    Invokes the generator with a timestamped description that includes the
    reason for the new session.  Also resets session-progress.json so the
    context-usage estimate starts fresh.

    Args:
        reason (str): Short label describing why the session was created
                      (e.g. 'msg_count_dropped_from_5_to_1').

    Returns:
        str or None: New session ID (e.g. 'SESSION-20260305-123456-ABCD'),
                     or None when the generator script fails or returns no
                     recognisable session ID.
    """
    sess_script = CURRENT_DIR / 'session-id-generator.py'
    if not sess_script.exists():
        log_event(f"ERROR: session-id-generator.py not found at {sess_script}")
        return None

    desc = f"New session after /clear at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if reason:
        desc += f" ({reason})"

    try:
        result = subprocess.run(
            [sys.executable, str(sess_script), 'create', '--description', desc],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=15
        )

        new_session_id = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('SESSION-'):
                new_session_id = line
                break

        if new_session_id:
            log_event(f"New session created: {new_session_id} (reason: {reason})")
            # Reset session-progress.json so context % starts fresh for new session
            _reset_session_progress(new_session_id)
            return new_session_id
        else:
            log_event(f"ERROR: Could not parse session ID from output: {result.stdout[:200]}")
            return None

    except Exception as e:
        log_event(f"ERROR creating session: {e}")
        return None


def _reset_session_progress(new_session_id=''):
    """
    Reset session-progress.json when a new session starts.
    This ensures context % estimate starts from 0 (fresh session)
    instead of accumulating from previous sessions.
    """
    session_progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
    try:
        fresh = {
            'total_progress': 0,
            'tool_counts': {},
            'content_chars': 0,
            'started_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'tasks_completed': 0,
            'errors_seen': 0,
            'context_estimate_pct': 15,
            'session_id': new_session_id,
            'reset_reason': 'new session after /clear'
        }
        session_progress_file.parent.mkdir(parents=True, exist_ok=True)
        with open(session_progress_file, 'w', encoding='utf-8') as f:
            import json as _json
            _lock_file(f)
            _json.dump(fresh, f, indent=2)
            _unlock_file(f)
        log_event(f"session-progress.json reset for new session {new_session_id}")
    except Exception as e:
        log_event(f"WARNING: Could not reset session-progress.json: {e}")


# =============================================================================
# SESSION CHAINING
# =============================================================================

def _finalize_session_summary(session_id):
    """
    Finalize session summary (generate session-summary.md) before closing.
    Called by clear-session-handler on /clear.
    """
    summary_script = CURRENT_DIR / 'session-summary-manager.py'
    if not summary_script.exists():
        log_event(f"[WARN] session-summary-manager.py not found, skipping finalize")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(summary_script), 'finalize',
             '--session', session_id],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode == 0:
            log_event(f"[SUMMARY] Finalized for {session_id}")
        else:
            log_event(f"[SUMMARY WARN] Finalize failed: {result.stderr[:100]}")
    except Exception as e:
        log_event(f"[SUMMARY ERROR] {e}")


def _link_session_chain(child_session, parent_session):
    """
    Link new session to its parent via session-chain-manager.py.
    Called after /clear creates a new session.
    """
    chain_script = CURRENT_DIR / 'session-chain-manager.py'
    if not chain_script.exists():
        log_event(f"[WARN] session-chain-manager.py not found, skipping chain link")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(chain_script), 'link',
             '--child', child_session, '--parent', parent_session],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode == 0:
            log_event(f"[CHAIN] Linked {child_session} -> parent: {parent_session}")
        else:
            log_event(f"[CHAIN WARN] Link failed: {result.stderr[:100]}")
    except Exception as e:
        log_event(f"[CHAIN ERROR] {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """UserPromptSubmit hook entry point - detect /clear and manage sessions.

    Execution flow:
      1. Initialise PID-based window isolation (HOOK_STATE_FILE).
      2. Clean up expired enforcement flags (Loophole #10).
      3. Load session-management policies from architecture scripts (3 retries).
      4. Read hook stdin (transcript_path + prompt).
      5. Count messages in the current transcript file.
      6. detect_clear() to see if a session boundary occurred.
      7. On fresh session:
           - Load previous session context from flow-trace.json.
           - Finalise the old session summary.
           - Close the old session (set COMPLETED + delete marker).
           - Print context so Claude sees it on first message.
           - Clear ALL enforcement flags.
           - Create a new session via session-id-generator.py.
           - Chain-link new session to old via session-chain-manager.py.
           - Write a voice flag for stop-notifier.py.
      8. Update hook state file for next invocation.
      9. Always exits 0.
    """
    # ===================================================================
    # TRACKING: Record start time and sub-operations list
    # ===================================================================
    _policy_start_time = datetime.now()
    _sub_operations = []

    # Initialize window isolation (PID-based state files)
    _init_window_isolation()

    # Flag auto-expiry cleanup at session start (Loophole #10)
    # Runs before reading any session state so stale flags are gone first.
    if FLAG_CLEANUP_ON_STARTUP:
        _expired = _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES)
        if _expired > 0:
            log_event(f"[FLAG-CLEANUP] Removed {_expired} expired flag(s) "
                      f"older than {FLAG_EXPIRY_MINUTES} minutes")

    # INTEGRATION: Load session management policies from scripts/architecture/
    # Retry up to 3 times. Warn on failure (session-handler should not hard-break).
    try:
        script_dir = Path(__file__).parent
        session_loader = script_dir / 'architecture' / '01-sync-system' / 'session-management' / 'session-loader.py'
        if session_loader.exists():
            _sl_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run([sys.executable, str(session_loader)], timeout=10, capture_output=True)
                    if _r.returncode == 0:
                        _sl_ok = True
                        break
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] session-loader failed, retrying...\n')
                        sys.stdout.flush()
                except Exception:
                    if _attempt < 3:
                        sys.stdout.write('[RETRY ' + str(_attempt) + '/3] session-loader error, retrying...\n')
                        sys.stdout.flush()
            if not _sl_ok:
                sys.stdout.write('[POLICY-WARN] session-loader failed after 3 retries\n')
                sys.stdout.flush()
    except:
        pass

    hook_data = read_hook_stdin()

    transcript_path = hook_data.get('transcript_path', '')
    prompt = hook_data.get('prompt', '')
    prompt_preview = prompt[:80].replace('\n', ' ')

    # Count messages in current transcript
    current_msg_count = count_transcript_messages(transcript_path)

    log_event(
        f"Hook fired | msg_count={current_msg_count} | "
        f"transcript={transcript_path} | prompt='{prompt_preview}'"
    )

    # If we can't determine state at all, skip
    if current_msg_count == -1 and not transcript_path:
        log_event("Cannot determine conversation state - skipping")
        # Still update state with what we know
        write_state(transcript_path, current_msg_count)
        sys.exit(0)

    # Detect if this is a fresh conversation
    is_fresh, reason = detect_clear(transcript_path, current_msg_count)

    if is_fresh:
        log_event(f"[CLEAR DETECTED] reason={reason}")

        current_session = get_current_session_id()

        if current_session:
            # Load previous session context BEFORE closing (reads flow-trace.json)
            prev_context = get_previous_session_context(current_session)

            # Finalize session summary BEFORE closing
            _finalize_session_summary(current_session)

            # Save and close the old session
            print(f"[SESSION] /clear detected - saving: {current_session}")
            close_current_session(current_session)
            print(f"[SESSION] Old session saved: {current_session}")

            # Print previous context AFTER session markers so Claude sees it clearly
            if prev_context:
                print(prev_context)

            # Clear ALL enforcement flags from ALL sessions - /clear = fresh start
            # Loophole #11: flags are now session-specific, use glob to find all
            import glob as _glob
            for pattern, flag_name in [
                ('.checkpoint-pending-*.json', 'Checkpoint'),
                ('.task-breakdown-pending-*.json', 'Task-breakdown'),
                ('.skill-selection-pending-*.json', 'Skill-selection'),
            ]:
                for flag_file in _glob.glob(str(FLAG_DIR / pattern)):
                    try:
                        Path(flag_file).unlink()
                        log_event(f"{flag_name} flag cleared on /clear: {Path(flag_file).name}")
                    except Exception:
                        pass

            # Create fresh session
            new_session = create_new_session(reason=reason)
            if new_session:
                print(f"[SESSION] New session started: {new_session}")
                log_event(f"Session transition complete: {current_session} -> {new_session}")

                # Chain link: new session -> parent (old session)
                _link_session_chain(new_session, current_session)
                # Voice: English, professional boss-assistant style
                import random
                hour = datetime.now().hour
                if hour < 12:
                    greet = 'Good morning'
                elif hour < 17:
                    greet = 'Good afternoon'
                else:
                    greet = 'Good evening'
                clear_messages = [
                    f"{greet} Sir. Session cleared and refreshed. Ready for your next task.",
                    f"{greet} Sir. Fresh session started. What would you like to work on?",
                    f"{greet} Sir. Previous session saved. I am ready for new commands.",
                    f"{greet} Sir. Session reset complete. Let me know what you need.",
                ]
                write_voice_flag(random.choice(clear_messages))
            else:
                print(f"[SESSION] Warning: Could not create new session")
                log_event("Warning: Failed to create new session after /clear")
        else:
            # No existing session - just create a new one
            # (3-level-flow will also try to create if none exists, but we do it here
            #  so it's ready before 3-level-flow reads it)
            new_session = create_new_session(reason=reason)
            if new_session:
                print(f"[SESSION] First session created: {new_session}")
                # Voice: first session - professional welcome
                import random
                hour = datetime.now().hour
                if hour < 12:
                    greet = 'Good morning'
                elif hour < 17:
                    greet = 'Good afternoon'
                else:
                    greet = 'Good evening'
                first_messages = [
                    f"{greet} Sir. First session started. I am ready to assist you.",
                    f"{greet} Sir. Welcome. Tell me what you would like to work on today.",
                    f"{greet} Sir. New session initialized. Ready for your commands.",
                ]
                write_voice_flag(random.choice(first_messages))

    else:
        log_event(f"Ongoing conversation ({reason}) - no session change")

    # Always update state with current values for next call comparison
    write_state(transcript_path, current_msg_count)

    # Cleanup window state on exit
    try:
        from session_window_isolator import cleanup_window
        cleanup_window()
    except Exception:
        pass

    # ===================================================================
    # TRACKING: Record overall policy execution
    # ===================================================================
    try:
        _policy_duration = int((datetime.now() - _policy_start_time).total_seconds() * 1000)
        _current_session = get_current_session_id()

        if HAS_TRACKING and _current_session:
            record_policy_execution(
                session_id=_current_session,
                policy_name="clear-session-handler",
                policy_script="clear-session-handler.py",
                policy_type="Utility Hook",
                input_params={
                    "transcript_path": str(transcript_path) if transcript_path else "",
                    "msg_count": current_msg_count
                },
                output_results={
                    "is_fresh": is_fresh if 'is_fresh' in dir() else False,
                    "reason": reason if 'reason' in dir() else "unknown"
                },
                decision=f"Session handler processed: {reason if 'reason' in dir() else 'ongoing'}",
                duration_ms=_policy_duration,
                sub_operations=_sub_operations if _sub_operations else None
            )
    except Exception as e:
        log_event(f"[TRACK-ERROR] Failed to record policy execution: {e}")

    try:
        _dur_csh = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_hook_execution('clear-session-handler.py', _dur_csh,
                            session_id='', exit_code=0,
                            extra={'reason': reason if 'reason' in dir() else ''})
    except Exception:
        pass

    sys.exit(0)


if __name__ == '__main__':
    main()
