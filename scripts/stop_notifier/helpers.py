#!/usr/bin/env python3
# ruff: noqa: F821
"""
Script Name: stop-notifier.py
Version: 4.3.0 (Static messages only, Ollama removed)
Last Modified: 2026-04-06
Description: Stop hook - speaks static English voice updates after each Claude response.

v4.3.0: Static messages only (Ollama removed)
  - REMOVED: Ollama LLM call and all related constants/functions
  - UNCHANGED: Voice notification pipeline (flag files, speak(), TTS)
  - UNCHANGED: WORK_DONE_SUMMARY environment variable support
  - Static fallback messages are now the ONLY message source
v4.2.0: Local LLM only (Ollama)
v4.1.0: Direct voice notification on TaskUpdate(completed)
  - NEW: Accepts WORK_DONE_SUMMARY environment variable from post-tool-tracker.py
  - NEW: Called directly by post-tool-tracker.py when all tasks complete (no Stop hook wait)
  - Flow: TaskUpdate(completed) -> post-tool-tracker.py -> stop-notifier.py -> voice + summary
v4.0.0: MAJOR FIXES + Session Summary Voice Integration
  - FIXED: increment_retry destroying original message (spoke '{"retries": 1}')
  - FIXED: Simplified flow - no retry complexity, just fallback -> speak -> done
  - FIXED: API key empty file check
  - NEW: work_done/task_complete use session summary data for rich voice context
  - NEW: Loads comprehensive summary from session-summary-manager for voice output
v3.2.0: Increased LLM timeout (5s -> 15s), retry logic, better error handling
v3.1.0: Non-blocking speak (fire-and-forget), faster LLM (5s timeout)

VOICE TRIGGERS (3 flag files, checked in priority order):
  1. ~/.claude/.session-start-voice   -> New session started
  2. ~/.claude/.task-complete-voice    -> Task completed
  3. ~/.claude/.session-work-done      -> All work done (written by Claude)

HOW IT WORKS (v4.3.0 - static messages only):
  1. Fires on every Claude 'Stop' event (after each AI response)
  2. Checks for any voice flag files (in priority order)
  3. If flag EXISTS: reads original message, uses static fallback message
  4. Always deletes flag after speaking (no retry accumulation)
  5. For work_done: loads session summary for voice context
  6. If no flags: stays completely silent (most responses)

PERSONALITY: Boss-assistant style
  - Addresses user as "Sir"
  - Professional but warm Indian English
  - Short, clear, natural updates

Voice: Static messages only. No LLM dependency.
Windows-Safe: ASCII only (no Unicode/emojis in print statements)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows ASCII-safe encoding
if sys.platform == "win32":
    import io

    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

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

# Track hook start time
_HOOK_START = datetime.now()

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (
        CONFIG_DIR,
        CURRENT_DIR,
        FLAG_DIR,
        MEMORY_BASE,
        SCRIPTS_DIR,
        SESSION_START_FLAG,
        STOP_LOG,
        TASK_COMPLETE_FLAG,
        WORK_DONE_FLAG,
    )

    API_KEY_FILE = CONFIG_DIR / "openrouter-api-key"
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    MEMORY_BASE = Path.home() / ".claude" / "memory"
    SCRIPTS_DIR = Path.home() / ".claude" / "scripts"
    CURRENT_DIR = SCRIPTS_DIR if SCRIPTS_DIR.exists() else (MEMORY_BASE / "current")
    FLAG_DIR = Path.home() / ".claude"
    SESSION_START_FLAG = FLAG_DIR / ".session-start-voice"
    TASK_COMPLETE_FLAG = FLAG_DIR / ".task-complete-voice"
    WORK_DONE_FLAG = FLAG_DIR / ".session-work-done"
    STOP_LOG = MEMORY_BASE / "logs" / "stop-notifier.log"
    API_KEY_FILE = Path.home() / ".claude" / "config" / "openrouter-api-key"

# =============================================================================
# PID ISOLATION FOR VOICE FLAGS (Loophole #11 fix)
#
# Multi-window problem: When multiple Claude Code windows are open, all
# instances share the same flag files (.session-start-voice, etc.).  This
# causes the wrong Stop hook instance to pick up and consume a flag written
# by a DIFFERENT window, resulting in duplicate/missed voice notifications.
#
# Fix: PID-isolated flag names - {prefix}-{PID}
# Each Claude Code process writes/reads its own flags using its PID.
# The stop-notifier in window A only reads flags written by window A.
#
# Contract (MUST match clear-session-handler.py and 3-level-flow.py):
#   .session-start-voice-{PID}
#   .task-complete-voice-{PID}
#   .session-work-done-{PID}
#
# Backward compatibility: if no PID-specific flag found, fall back to the
# legacy shared flag (written by older versions of the scripts).
# =============================================================================
_PID = os.getpid()

SESSION_START_FLAG_PID = FLAG_DIR / f".session-start-voice-{_PID}"
TASK_COMPLETE_FLAG_PID = FLAG_DIR / f".task-complete-voice-{_PID}"
WORK_DONE_FLAG_PID = FLAG_DIR / f".session-work-done-{_PID}"

VOICE_SCRIPT = CURRENT_DIR / "voice-notifier.py"

# ============================================================================
# VOICE MODE CONFIGURATION
# Set VOICE_ENABLED=0 in env or ~/.claude/.voice-disabled to disable voice
# Voice is optional - summary/PR workflow still runs without it
# ============================================================================
_voice_disabled_flag = FLAG_DIR / ".voice-disabled"
VOICE_ENABLED = os.environ.get("VOICE_ENABLED", "1") != "0" and not _voice_disabled_flag.exists()

# Voice is delivered via static messages only (no LLM dependency).


# =============================================================================
# LOGGING
# =============================================================================


def log_s(msg):
    """Append a timestamped message to the stop-notifier log file.

    Creates parent directories automatically.  Errors are silently swallowed
    so logging never crashes the hook.

    Args:
        msg (str): ASCII-safe message to append.
    """
    STOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(STOP_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# READ HOOK STDIN
# =============================================================================


def read_hook_stdin():
    """Read JSON data piped by the Claude Code Stop hook via stdin.

    The Stop hook sends a small JSON object.  This function is safe when stdin
    is a TTY (returns {} instead of blocking).

    Returns:
        dict: Parsed hook payload, or {} on any read or parse error.
    """
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw and raw.strip():
                return json.loads(raw.strip())
    except Exception:
        pass
    return {}


# =============================================================================
# FLAG FILE HELPERS
# =============================================================================


def read_flag(flag_path):
    """Read a flag file's content. Returns stripped text or empty string.

    Non-destructive: does NOT delete the flag file after reading.
    """
    if not flag_path.exists():
        return ""
    try:
        raw = flag_path.read_text(encoding="utf-8").strip()
        return raw
    except Exception:
        return ""


def increment_retry(flag_path, max_retries=3):
    """Increment retry counter in a flag file. Returns True if retries remaining.

    For plain text flags: creates JSON with retries=1.
    For JSON flags: increments the retries field.
    Returns False when max_retries exceeded or on read error for .json files.
    """
    try:
        if flag_path.suffix == ".json":
            # JSON flag: read, increment, write
            try:
                raw = flag_path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (FileNotFoundError, json.JSONDecodeError):
                return False
        else:
            # Plain text flag: wrap in JSON dict
            data = {"retries": 0}
            if flag_path.exists():
                try:
                    content = flag_path.read_text(encoding="utf-8").strip()
                    data["content"] = content
                except Exception:
                    pass

        current = data.get("retries", 0)
        if current >= max_retries:
            return False

        data["retries"] = current + 1
        flag_path.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception:
        return False


def read_flag_message(flag_path):
    """
    Read a flag file's ORIGINAL MESSAGE content.
    v4.0.0: Safely extracts the message even if flag was corrupted.
    Returns the human-readable message or empty string.
    """
    if not flag_path.exists():
        return ""
    try:
        raw = flag_path.read_text(encoding="utf-8").strip()
        if not raw:
            return ""
        # v4.0.0 FIX: If the content looks like JSON (corrupted by old retry logic),
        # ignore it and return empty - caller will use static default
        if raw.startswith("{") and "retries" in raw:
            log_s(f"[flag] Ignoring corrupted retry JSON in {flag_path.name}")
            return ""
        return raw
    except Exception as e:
        log_s(f"[flag] Error reading {flag_path.name}: {e}")
        return ""


def delete_flag(flag_path):
    """Delete a flag file after processing."""
    if not flag_path.exists():
        return
    try:
        flag_path.unlink()
        log_s(f"[flag] Deleted: {flag_path.name}")
    except Exception as e:
        log_s(f"[flag] Could not delete {flag_path.name}: {e}")


# =============================================================================
# SESSION SUMMARY FOR VOICE (v4.0.0 - NEW)
# =============================================================================
