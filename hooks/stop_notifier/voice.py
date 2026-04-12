"""stop_notifier/voice.py - Voice notification and TTS functions.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import json
import subprocess
import sys
from datetime import datetime

from .helpers import delete_flag, log_s, read_flag_message


def get_current_session_id():
    """Read the active session ID from per-project or legacy session file.

    Returns:
        str or None: Session ID string (e.g. 'SESSION-20260305-123456-ABCD'),
                     or None when no session file is found or unreadable.
    """
    try:
        from project_session import read_session_id

        sid = read_session_id()
        return sid if sid else None
    except ImportError:
        pass
    # Legacy fallback
    current_session_file = MEMORY_BASE / ".current-session.json"
    if not current_session_file.exists():
        return None
    try:
        with open(current_session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("current_session_id")
    except Exception:
        return None


def _get_session_issues_file():
    """Resolve the path to github-issues.json for the active session.

    Tries to read the session ID from .current-session.json first; falls back
    to reading session-progress.json when that file is unavailable.

    Returns:
        Path or None: Path to the github-issues.json file if the session ID
                      can be determined, or None otherwise.
    """
    try:
        session_id = get_current_session_id()
        if not session_id:
            # Fallback: read from session-progress.json
            progress_file = MEMORY_BASE / "logs" / "session-progress.json"
            if progress_file.exists():
                with open(progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session_id = data.get("session_id", "")
        if session_id:
            issues_file = MEMORY_BASE / "logs" / "sessions" / session_id / "github-issues.json"
            return issues_file
    except Exception:
        pass
    return None


def get_session_summary_for_voice():
    """
    Load the comprehensive session summary text for voice output.
    v4.0.0: Uses session-summary-manager's one-liner or builds from session data.
    Returns a short context string suitable for LLM voice generation.
    """
    session_id = get_current_session_id()
    if not session_id:
        return ""

    # Try reading the summary JSON
    summary_file = MEMORY_BASE / "logs" / "sessions" / session_id / "session-summary.json"
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Build a rich context for LLM from summary data
            parts = []
            req_count = data.get("request_count", 0)
            if req_count > 0:
                parts.append(f"{req_count} requests handled")

            types = data.get("task_types", [])
            if types:
                parts.append(f"task types: {', '.join(types[:3])}")

            skills = data.get("skills_used", [])
            if skills:
                parts.append(f"skills used: {', '.join(skills[:3])}")

            projects = data.get("projects_touched", [])
            if projects:
                parts.append(f"projects: {', '.join(projects[:2])}")

            max_c = data.get("max_complexity", 0)
            if max_c > 0:
                parts.append(f"max complexity: {max_c}/25")

            # Get the last prompt for context
            requests = data.get("requests", [])
            if requests:
                last_prompt = requests[-1].get("prompt", "")[:100]
                if last_prompt:
                    parts.append(f"last task: {last_prompt}")

            if parts:
                return ". ".join(parts)
        except Exception as e:
            log_s(f"[summary] Error loading summary for voice: {e}")

    # Fallback: try session progress
    progress_file = MEMORY_BASE / "logs" / "session-progress.json"
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                prog = json.load(f)
            tool_counts = prog.get("tool_counts", {})
            total_tools = sum(tool_counts.values())
            tasks_done = prog.get("tasks_completed", 0)
            if total_tools > 0 or tasks_done > 0:
                return f"{total_tools} tool calls, {tasks_done} tasks completed"
        except Exception:
            pass

    return ""


# =============================================================================
# SPEAK VIA voice-notifier.py
# =============================================================================


def speak(text):
    """
    Launch voice-notifier.py as DETACHED process (fire-and-forget).
    Non-blocking: stop-notifier exits immediately, voice plays in background.
    Skipped entirely if VOICE_ENABLED=False (env var or flag file).
    """
    if not text or not text.strip():
        return

    if not VOICE_ENABLED:
        log_s("[voice] Disabled (VOICE_ENABLED=0 or .voice-disabled flag). Skipping.")
        return

    if not VOICE_SCRIPT.exists():
        log_s(f"[ERROR] voice-notifier.py not found at {VOICE_SCRIPT}")
        return

    try:
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW

        subprocess.Popen(
            [sys.executable, str(VOICE_SCRIPT), text],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log_s(f"[voice] Launched (detached): {text[:80]}")
    except Exception as e:
        log_s(f"[voice] Error launching detached: {e}")


# =============================================================================
# STATIC FALLBACK MESSAGES (English, boss-assistant style)
# =============================================================================


def get_session_start_default():
    """Static fallback for session start greeting."""
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return f"{greeting} Sir. New session started. I am ready for your commands."


def get_task_complete_default():
    """Static fallback for task completion."""
    return "Sir, task completed successfully. What would you like to do next?"


def get_work_done_default():
    """Static fallback for all-work-done."""
    return "Sir, all tasks are completed. Everything looks good. Let me know if you need anything else."


# =============================================================================
# VOICE HANDLER - Simplified flow (v4.0.0)
# =============================================================================


def handle_voice_flag(flag_path, event_type, get_default_fn, extra_context=""):
    """
    Unified voice handler for any flag type.
    v4.3.0: Static messages only (Ollama removed):
      1. Read original message from flag (for logging context only)
      2. Use static default message
      3. Speak the message
      4. Always delete flag (no retry accumulation)

    Returns True if spoke something.
    """
    if not flag_path.exists():
        return False

    # Step 1: Read original message from flag (logging only)
    original_message = read_flag_message(flag_path)
    log_s(f"[{event_type}] Flag found, original message: {original_message[:80]}")

    # Step 2: Use static default message (no LLM call)
    message = get_default_fn()
    log_s(f"[{event_type}] Using static message: {message[:80]}")

    # Step 3: Speak
    print(f"[VOICE] {event_type} notification...")
    speak(message)

    # Step 4: Always delete flag - no retry accumulation
    delete_flag(flag_path)

    return True


# =============================================================================
# PR AUTO-CREATION FROM PIPELINE STEP 7 DATA
# =============================================================================
