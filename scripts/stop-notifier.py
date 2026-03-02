#!/usr/bin/env python3
"""
Script Name: stop-notifier.py
Version: 4.0.0 (Session Summary Voice + Bug Fixes)
Last Modified: 2026-02-28
Description: Stop hook - speaks dynamic English voice updates via LLM.

v4.0.0: MAJOR FIXES + Session Summary Voice Integration
  - FIXED: increment_retry destroying original message (spoke '{"retries": 1}')
  - FIXED: Simplified flow - no retry complexity, just try LLM -> fallback -> speak -> done
  - FIXED: API key empty file check
  - NEW: work_done/task_complete use session summary data for rich voice context
  - NEW: Loads comprehensive summary from session-summary-manager for voice output
v3.2.0: Increased LLM timeout (5s -> 15s), retry logic, better error handling
v3.1.0: Non-blocking speak (fire-and-forget), faster LLM (5s timeout)

VOICE TRIGGERS (3 flag files, checked in priority order):
  1. ~/.claude/.session-start-voice   -> New session started
  2. ~/.claude/.task-complete-voice    -> Task completed
  3. ~/.claude/.session-work-done      -> All work done (written by Claude)

HOW IT WORKS (v4.0.0 - simplified):
  1. Fires on every Claude 'Stop' event (after each AI response)
  2. Checks for any voice flag files (in priority order)
  3. If flag EXISTS: reads original message, calls OpenRouter LLM
  4. If LLM fails: uses static fallback (NEVER speaks raw JSON/garbage)
  5. Always deletes flag after speaking (no retry accumulation)
  6. For work_done: loads session summary for rich context in voice
  7. If no flags: stays completely silent (most responses)

PERSONALITY: Boss-assistant style
  - Addresses user as "Sir"
  - Professional but warm Indian English
  - Short, clear, natural updates

LLM: OpenRouter API (REQUIRED for dynamic voice)
API Key: ~/.claude/config/openrouter-api-key
Setup: https://openrouter.ai -> Create API key -> paste in file

Windows-Safe: ASCII only (no Unicode/emojis in print statements)
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from urllib import request as urllib_request

# Windows ASCII-safe encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import (MEMORY_BASE, SCRIPTS_DIR, CURRENT_DIR, FLAG_DIR,
                           SESSION_START_FLAG, TASK_COMPLETE_FLAG, WORK_DONE_FLAG, STOP_LOG, CONFIG_DIR)
    API_KEY_FILE = CONFIG_DIR / 'openrouter-api-key'
except ImportError:
    # Fallback for standalone mode (no IDE_INSTALL_DIR set)
    MEMORY_BASE = Path.home() / '.claude' / 'memory'
    SCRIPTS_DIR = Path.home() / '.claude' / 'scripts'
    CURRENT_DIR = SCRIPTS_DIR if SCRIPTS_DIR.exists() else (MEMORY_BASE / 'current')
    FLAG_DIR = Path.home() / '.claude'
    SESSION_START_FLAG = FLAG_DIR / '.session-start-voice'
    TASK_COMPLETE_FLAG = FLAG_DIR / '.task-complete-voice'
    WORK_DONE_FLAG = FLAG_DIR / '.session-work-done'
    STOP_LOG = MEMORY_BASE / 'logs' / 'stop-notifier.log'
    API_KEY_FILE = Path.home() / '.claude' / 'config' / 'openrouter-api-key'

VOICE_SCRIPT = CURRENT_DIR / 'voice-notifier.py'

# OpenRouter config
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Fast models in priority order (cheapest first)
LLM_MODELS = [
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "google/gemini-2.0-flash-001",
]

VOICE_SYSTEM_PROMPT = (
    "You are Neerja, a professional Indian English-speaking female voice assistant. "
    "You address the user as 'Sir'. You are warm, professional, and concise. "
    "Generate a SHORT spoken notification message (1-2 sentences max, under 30 words). "
    "The message will be spoken aloud via text-to-speech, so keep it natural and conversational. "
    "Do NOT use any special characters, markdown, emojis, or formatting. "
    "Just plain spoken English text. Be specific about what happened if context is provided."
)


# =============================================================================
# LOGGING
# =============================================================================

def log_s(msg):
    STOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(STOP_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# READ HOOK STDIN
# =============================================================================

def read_hook_stdin():
    """Read JSON data from Claude Code Stop hook stdin"""
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

def read_flag_message(flag_path):
    """
    Read a flag file's ORIGINAL MESSAGE content.
    v4.0.0: Safely extracts the message even if flag was corrupted.
    Returns the human-readable message or empty string.
    """
    if not flag_path.exists():
        return ''
    try:
        raw = flag_path.read_text(encoding='utf-8').strip()
        if not raw:
            return ''
        # v4.0.0 FIX: If the content looks like JSON (corrupted by old retry logic),
        # ignore it and return empty - caller will use static default
        if raw.startswith('{') and 'retries' in raw:
            log_s(f"[flag] Ignoring corrupted retry JSON in {flag_path.name}")
            return ''
        return raw
    except Exception as e:
        log_s(f"[flag] Error reading {flag_path.name}: {e}")
        return ''


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

def get_current_session_id():
    """Get current session ID from .current-session.json"""
    current_session_file = MEMORY_BASE / '.current-session.json'
    if not current_session_file.exists():
        return None
    try:
        with open(current_session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('current_session_id')
    except Exception:
        return None


def _get_session_issues_file():
    """Get the github-issues.json file for the current session (if it exists)."""
    try:
        session_id = get_current_session_id()
        if not session_id:
            # Fallback: read from session-progress.json
            progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
            if progress_file.exists():
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session_id = data.get('session_id', '')
        if session_id:
            issues_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'github-issues.json'
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
        return ''

    # Try reading the summary JSON
    summary_file = MEMORY_BASE / 'logs' / 'sessions' / session_id / 'session-summary.json'
    if summary_file.exists():
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Build a rich context for LLM from summary data
            parts = []
            req_count = data.get('request_count', 0)
            if req_count > 0:
                parts.append(f"{req_count} requests handled")

            types = data.get('task_types', [])
            if types:
                parts.append(f"task types: {', '.join(types[:3])}")

            skills = data.get('skills_used', [])
            if skills:
                parts.append(f"skills used: {', '.join(skills[:3])}")

            projects = data.get('projects_touched', [])
            if projects:
                parts.append(f"projects: {', '.join(projects[:2])}")

            max_c = data.get('max_complexity', 0)
            if max_c > 0:
                parts.append(f"max complexity: {max_c}/25")

            # Get the last prompt for context
            requests = data.get('requests', [])
            if requests:
                last_prompt = requests[-1].get('prompt', '')[:100]
                if last_prompt:
                    parts.append(f"last task: {last_prompt}")

            if parts:
                return '. '.join(parts)
        except Exception as e:
            log_s(f"[summary] Error loading summary for voice: {e}")

    # Fallback: try session progress
    progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
    if progress_file.exists():
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            tool_counts = prog.get('tool_counts', {})
            total_tools = sum(tool_counts.values())
            tasks_done = prog.get('tasks_completed', 0)
            if total_tools > 0 or tasks_done > 0:
                return f"{total_tools} tool calls, {tasks_done} tasks completed"
        except Exception:
            pass

    return ''


# =============================================================================
# LLM MESSAGE GENERATION (OpenRouter)
# =============================================================================

def load_api_key():
    """Load OpenRouter API key from config file. Returns None if missing or empty."""
    if not API_KEY_FILE.exists():
        return None
    try:
        key = API_KEY_FILE.read_text(encoding='utf-8').strip()
        # v4.0.0: Check for empty file too
        if not key or len(key) < 10:
            return None
        return key
    except Exception:
        return None


def generate_dynamic_message(event_type, context=''):
    """
    Call OpenRouter LLM to generate a natural, dynamic voice message.
    Returns message string or None (caller uses static fallback).
    """
    api_key = load_api_key()
    if not api_key:
        log_s(f"[llm] No API key found for {event_type} - using static fallback")
        return None

    log_s(f"[llm] Starting LLM call for {event_type}")

    hour = datetime.now().hour
    if hour < 12:
        time_context = "morning"
    elif hour < 17:
        time_context = "afternoon"
    else:
        time_context = "evening"

    # Build the user prompt based on event type
    if event_type == 'session_start':
        user_prompt = (
            f"It is {time_context}. A new coding session just started. "
            f"Generate a greeting for the user."
        )
        if context:
            user_prompt += f" Context: {context}"

    elif event_type == 'task_complete':
        user_prompt = f"A coding task was just completed."
        if context:
            user_prompt += f" Here is what was done: {context}."
        user_prompt += " Generate a brief completion notification."

    elif event_type == 'work_done':
        user_prompt = f"All coding tasks for this session are done."
        if context:
            user_prompt += f" Session summary: {context}."
        user_prompt += " Generate a brief wrap-up notification."

    else:
        user_prompt = f"Generate a brief notification. Context: {context}"

    # Try each model until one works
    for attempt, model in enumerate(LLM_MODELS, 1):
        try:
            log_s(f"[llm] Attempt {attempt}/{len(LLM_MODELS)}: {model}")

            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": VOICE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 60,
                "temperature": 0.7,
            }).encode('utf-8')

            req = urllib_request.Request(
                OPENROUTER_URL,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}',
                    'HTTP-Referer': 'https://claude-code-voice.local',
                    'X-Title': 'Claude Code Voice',
                },
                method='POST'
            )

            with urllib_request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                message = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()

                if message:
                    # Clean up any markdown or special chars
                    message = message.replace('*', '').replace('#', '').replace('`', '')
                    message = message.replace('\n', ' ').strip()
                    if message.startswith('"') and message.endswith('"'):
                        message = message[1:-1]
                    log_s(f"[llm] SUCCESS ({model}): {message[:80]}")
                    return message
                else:
                    log_s(f"[llm] {model} returned empty, trying next...")

        except urllib_request.URLError as e:
            log_s(f"[llm] {model} URL error: {str(e)[:80]}")
            continue
        except Exception as e:
            log_s(f"[llm] {model} failed ({type(e).__name__}): {str(e)[:80]}")
            continue

    log_s(f"[llm] All models failed - using static fallback")
    return None


# =============================================================================
# SPEAK VIA voice-notifier.py
# =============================================================================

def speak(text):
    """
    Launch voice-notifier.py as DETACHED process (fire-and-forget).
    Non-blocking: stop-notifier exits immediately, voice plays in background.
    """
    if not text or not text.strip():
        return

    if not VOICE_SCRIPT.exists():
        log_s(f"[ERROR] voice-notifier.py not found at {VOICE_SCRIPT}")
        return

    try:
        creation_flags = 0
        if sys.platform == 'win32':
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

def handle_voice_flag(flag_path, event_type, get_default_fn, extra_context=''):
    """
    Unified voice handler for any flag type.
    v4.0.0: Simple, reliable flow:
      1. Read original message from flag
      2. Build context (original message + extra_context like session summary)
      3. Try LLM with context
      4. If LLM fails -> use static default (NEVER speak raw flag content)
      5. Speak the message
      6. Always delete flag (no retry accumulation)

    Returns True if spoke something.
    """
    if not flag_path.exists():
        return False

    # Step 1: Read original message from flag
    original_message = read_flag_message(flag_path)
    log_s(f"[{event_type}] Flag found, original message: {original_message[:80]}")

    # Step 2: Build LLM context from original message + session summary
    llm_context = ''
    if original_message:
        llm_context = original_message
    if extra_context:
        llm_context = f"{llm_context}. {extra_context}" if llm_context else extra_context

    # Step 3: Try LLM for dynamic message
    message = generate_dynamic_message(event_type, llm_context)

    # Step 4: If LLM fails, use static default (NEVER the raw flag content)
    if not message:
        message = get_default_fn()
        log_s(f"[{event_type}] Using static fallback: {message[:80]}")

    # Step 5: Speak
    print(f"[VOICE] {event_type} notification...")
    speak(message)

    # Step 6: Always delete flag - no retry accumulation
    delete_flag(flag_path)

    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    # INTEGRATION: Load git commit policies from scripts/architecture/
    # Retry up to 3 times per policy script. Warn on failure (Stop hook
    # should not hard-break; it runs AFTER the response is sent).
    try:
        from pathlib import Path
        import subprocess
        script_dir = Path(__file__).parent
        git_commit_script = script_dir / 'architecture' / '03-execution-system' / '09-git-commit' / 'auto-commit-enforcer.py'
        if git_commit_script.exists():
            _commit_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run([sys.executable, str(git_commit_script), '--enforce-now'], timeout=60, capture_output=True)
                    if _r.returncode == 0:
                        _commit_ok = True
                        break
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] auto-commit-enforcer failed, retrying...')
                except Exception:
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] auto-commit-enforcer error, retrying...')
            if not _commit_ok:
                log_s('[POLICY-WARN] auto-commit-enforcer failed after 3 retries')
    except:
        pass

    hook_data = read_hook_stdin()

    # =========================================================================
    # SESSION END MAINTENANCE (non-blocking, before voice)
    # Architecture scripts: auto-save-session, archive-old-sessions, failure-detector
    # =========================================================================
    script_dir = Path(__file__).parent

    # 1. Auto-save session state before cleanup (3 retries)
    # Architecture: 01-sync-system/session-management/auto-save-session.py
    try:
        save_script = script_dir / 'architecture' / '01-sync-system' / 'session-management' / 'auto-save-session.py'
        if save_script.exists():
            project_name = Path.cwd().name
            _save_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(save_script), '--project', project_name],
                        timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _save_ok = True
                        break
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] auto-save-session failed, retrying...')
                except Exception:
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] auto-save-session error, retrying...')
            if _save_ok:
                log_s('[SESSION-SAVE] Auto-saved session for: ' + project_name)
            else:
                log_s('[POLICY-WARN] auto-save-session failed after 3 retries')
    except Exception as e:
        log_s('[SESSION-SAVE] Skipped: ' + str(e))

    # 2. Archive old sessions - keep last 10, archive >30 days (3 retries)
    # Architecture: 01-sync-system/session-management/archive-old-sessions.py
    try:
        archive_script = script_dir / 'architecture' / '01-sync-system' / 'session-management' / 'archive-old-sessions.py'
        if archive_script.exists():
            _arch_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(archive_script)],
                        timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _arch_ok = True
                        break
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] archive-old-sessions failed, retrying...')
                except Exception:
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] archive-old-sessions error, retrying...')
            if _arch_ok:
                log_s('[SESSION-ARCHIVE] Old sessions archived')
            else:
                log_s('[POLICY-WARN] archive-old-sessions failed after 3 retries')
    except Exception as e:
        log_s('[SESSION-ARCHIVE] Skipped: ' + str(e))

    # 3. Failure detection analysis - learn from errors (3 retries)
    # Architecture: 03-execution-system/failure-prevention/failure-detector.py
    try:
        failure_script = script_dir / 'architecture' / '03-execution-system' / 'failure-prevention' / 'failure-detector.py'
        if failure_script.exists():
            _fail_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(failure_script), '--analyze-logs'],
                        timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _fail_ok = True
                        break
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] failure-detector failed, retrying...')
                except Exception:
                    if _attempt < 3:
                        log_s('[RETRY ' + str(_attempt) + '/3] failure-detector error, retrying...')
            if _fail_ok:
                log_s('[FAILURE-DETECT] Failure patterns analyzed')
            else:
                log_s('[POLICY-WARN] failure-detector failed after 3 retries')
    except Exception as e:
        log_s('[FAILURE-DETECT] Skipped: ' + str(e))

    spoke_something = False

    # PRIORITY 1: Session start voice
    if SESSION_START_FLAG.exists():
        spoke_something = handle_voice_flag(
            SESSION_START_FLAG,
            'session_start',
            get_session_start_default,
        )

    # PRIORITY 2: Task complete voice (with session summary context)
    if TASK_COMPLETE_FLAG.exists():
        summary_context = get_session_summary_for_voice()
        spoke_something = handle_voice_flag(
            TASK_COMPLETE_FLAG,
            'task_complete',
            get_task_complete_default,
            extra_context=summary_context,
        )

    # PRIORITY 3: All work done - trigger PR workflow first, then voice
    pr_triggered = False
    if WORK_DONE_FLAG.exists():
        # GitHub PR Workflow: commit, push, PR, review, merge (non-blocking)
        pr_merged = False
        try:
            script_dir = Path(__file__).parent
            if str(script_dir) not in sys.path:
                sys.path.insert(0, str(script_dir))
            import github_pr_workflow
            pr_merged = github_pr_workflow.run_pr_workflow()
            pr_triggered = True
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Error: {e}")

        # Voice notification (after PR workflow)
        summary_context = get_session_summary_for_voice()
        spoke_something = handle_voice_flag(
            WORK_DONE_FLAG,
            'work_done',
            get_work_done_default,
            extra_context=summary_context,
        )

        # If PR workflow failed to merge, write a retry flag so next Stop can retry
        if pr_triggered and not pr_merged:
            try:
                retry_flag = FLAG_DIR / '.pr-workflow-retry'
                retry_flag.write_text('PR workflow ran but merge failed - retry on next Stop',
                                      encoding='utf-8')
                log_s("[PR-WORKFLOW] Merge failed - retry flag written for next Stop")
            except Exception:
                pass

    # PRIORITY 3b: PR workflow retry (from previous failed merge attempt)
    if not pr_triggered and (FLAG_DIR / '.pr-workflow-retry').exists():
        try:
            script_dir = Path(__file__).parent
            if str(script_dir) not in sys.path:
                sys.path.insert(0, str(script_dir))
            import github_pr_workflow
            pr_merged = github_pr_workflow.run_pr_workflow()
            if pr_merged:
                (FLAG_DIR / '.pr-workflow-retry').unlink(missing_ok=True)
                log_s("[PR-WORKFLOW] Retry succeeded - PR merged")
            else:
                log_s("[PR-WORKFLOW] Retry failed - will try again on next Stop")
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Retry error: {e}")

    # PRIORITY 4: Branch-based PR detection (fallback when work_done flag was never written)
    # This catches sessions where Claude works without TaskCreate/TaskUpdate
    # Also ensures version bump + PR workflow runs even for manual PR creation
    if not pr_triggered:
        try:
            branch_result = subprocess.run(
                ['git', 'branch', '--show-current'],
                capture_output=True, text=True, timeout=5
            )
            current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ''

            if current_branch and current_branch not in ('main', 'master'):
                # On a feature branch - check if work is done
                should_trigger = False
                trigger_reason = ''

                # Check 1: All session issues are closed
                session_issues_file = _get_session_issues_file()
                if session_issues_file and session_issues_file.exists():
                    try:
                        mapping = json.loads(session_issues_file.read_text(encoding='utf-8'))
                        task_issues = mapping.get('task_to_issue', {})
                        if task_issues:
                            all_closed = all(
                                d.get('status') == 'closed'
                                for d in task_issues.values()
                            )
                            if all_closed:
                                should_trigger = True
                                trigger_reason = 'all issues closed'
                    except Exception:
                        pass

                # Check 2: No tracked issues but all tasks completed
                # (covers manual PR creation where github-issues.json is missing)
                if not should_trigger:
                    try:
                        progress_file = MEMORY_BASE / 'logs' / 'session-progress.json'
                        if progress_file.exists():
                            with open(progress_file, 'r', encoding='utf-8') as f:
                                progress = json.load(f)
                            tasks_created = progress.get('tasks_created', 0)
                            tasks_completed = progress.get('tasks_completed', 0)
                            if tasks_created > 0 and tasks_completed >= tasks_created:
                                should_trigger = True
                                trigger_reason = f'all {tasks_completed} tasks completed'
                    except Exception:
                        pass

                if should_trigger:
                    log_s(f"[PR-WORKFLOW] Branch detection: on {current_branch} ({trigger_reason}) - triggering PR workflow (includes version bump)")
                    script_dir = Path(__file__).parent
                    if str(script_dir) not in sys.path:
                        sys.path.insert(0, str(script_dir))
                    import github_pr_workflow
                    github_pr_workflow.run_pr_workflow()
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Branch detection error: {e}")

    if not spoke_something:
        log_s("[OK] Stop hook fired | No voice flags found (normal, most stops are silent)")

    sys.exit(0)


if __name__ == '__main__':
    main()
