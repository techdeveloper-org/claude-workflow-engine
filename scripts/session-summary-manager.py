#!/usr/bin/env python3
"""
Script Name: session-summary-manager.py
Version: 2.1.0
Last Modified: 2026-03-03
Description: Session Summary Manager - accumulates per-request data and generates
             COMPREHENSIVE human-readable summaries for each session.

             v2.0.0: Major upgrade - comprehensive summaries with:
               - Tool usage statistics (from session-progress.json + tool-tracker.jsonl)
               - Files modified/read tracking (from tool-tracker.jsonl)
               - Session duration calculation
               - Context usage tracking (start/end/peak)
               - Pipeline decision insights (from flow-trace.json)
               - Average/max complexity stats
               - Supplementary skills tracking
               - Plan mode usage tracking
               - Git activity tracking
               - Session insights auto-generation
               - Rich markdown with tables and sections

             v1.0.0: Basic summary (prompt, type, skill, model, complexity only)

Usage:
    # Accumulate data for current request (called by 3-level-flow.py)
    python session-summary-manager.py accumulate \
        --session SESSION-ID \
        --prompt "user message" \
        --task-type "Implementation" \
        --skill "java-spring-boot-microservices" \
        --complexity 7 \
        --model "SONNET" \
        --cwd "/path/to/project" \
        --plan-mode "false" \
        --context-pct 45 \
        --supplementary-skills "docker,kubernetes" \
        --standards-count 14 \
        --rules-count 89

    # Finalize summary on session close (called by clear-session-handler.py)
    python session-summary-manager.py finalize --session SESSION-ID

    # Read summary for a session
    python session-summary-manager.py read --session SESSION-ID

Hook Type: Utility (called by 3-level-flow.py and clear-session-handler.py)
Windows-Safe: No Unicode chars (ASCII only, cp1252 compatible)
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

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

MEMORY_BASE = Path.home() / '.claude' / 'memory'
SESSIONS_DIR = MEMORY_BASE / 'sessions'
LOGS_DIR = MEMORY_BASE / 'logs'
SUMMARY_LOG = LOGS_DIR / 'session-summary.log'


# =============================================================================
# LOGGING
# =============================================================================

def log_event(msg):
    """Append a timestamped message to the session-summary.log file.

    Creates parent directories automatically.  Content must be ASCII-safe for
    Windows cp1252 compatibility.  Errors are silently swallowed.

    Args:
        msg (str): ASCII-safe message to append.
    """
    SUMMARY_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(SUMMARY_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# PATHS
# =============================================================================

def session_log_dir(session_id):
    """Return the per-session log directory path.

    Args:
        session_id (str): Session identifier.

    Returns:
        Path: LOGS_DIR/sessions/{session_id}
    """
    return LOGS_DIR / 'sessions' / session_id


def summary_json_path(session_id):
    """Return the path to the session's accumulated JSON summary file.

    Args:
        session_id (str): Session identifier.

    Returns:
        Path: session_log_dir(session_id)/session-summary.json
    """
    return session_log_dir(session_id) / 'session-summary.json'


def summary_md_path(session_id):
    """Return the path to the session's human-readable Markdown summary file.

    Args:
        session_id (str): Session identifier.

    Returns:
        Path: session_log_dir(session_id)/session-summary.md
    """
    return session_log_dir(session_id) / 'session-summary.md'


# =============================================================================
# ACCUMULATE - Called on every request by 3-level-flow.py
# =============================================================================

def accumulate(session_id, prompt='', task_type='', skill='', complexity=0,
               model='', cwd='', plan_mode='false', context_pct=0,
               supplementary_skills='', standards_count=0, rules_count=0):
    """Accumulate a per-request entry in the session's summary JSON.

    Called by 3-level-flow.py after every user message.  Reads the existing
    summary JSON (or creates a fresh one), appends a new request entry, and
    updates aggregate fields (skills_used, task_types, max_complexity, etc.).

    Uses _lock_file/_unlock_file to prevent data corruption under concurrent
    hook invocations.

    Args:
        session_id (str): Active session identifier.
        prompt (str): User message text (truncated to 500 chars).
        task_type (str): Classified task type (e.g. 'Backend').
        skill (str): Primary skill or agent selected.
        complexity (int): Task complexity score (0-25).
        model (str): Model name used for this request (e.g. 'SONNET').
        cwd (str): Working directory of the project.
        plan_mode (str): 'true' or 'false' string from flow output.
        context_pct (int): Estimated context window usage at this point.
        supplementary_skills (str): Comma-separated supplementary skill names.
        standards_count (int): Number of active standards loaded.
        rules_count (int): Number of active rules loaded.

    Returns:
        bool: True on success; False when session_id is falsy or write fails.
    """
    if not session_id:
        return False

    log_dir = session_log_dir(session_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    json_path = summary_json_path(session_id)

    # Load existing or create new
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
        except Exception:
            data = _new_summary(session_id)
    else:
        data = _new_summary(session_id)

    # Ensure required keys exist (file may have been created by another script
    # like plan-session-archiver with only plan_info)
    defaults = _new_summary(session_id)
    for key in defaults:
        if key not in data:
            data[key] = defaults[key]

    # Add this request as an entry (v2.1.0: enhanced fields + decision rationale)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt[:500],
        "prompt_char_count": len(prompt),
        "task_type": task_type,
        "skill": skill,
        "complexity": complexity,
        "model": model,
        "cwd": cwd,
        "plan_mode": str(plan_mode).lower() == 'true',
        "context_pct": context_pct,
        "supplementary_skills": [s.strip() for s in supplementary_skills.split(',') if s.strip()] if supplementary_skills else [],
        "decision_rationale": f"Complexity {complexity} -> Model {model}, Skill {skill}",
    }

    data["requests"].append(entry)
    data["request_count"] = len(data["requests"])
    data["last_updated"] = datetime.now().isoformat()

    # Track unique values
    if skill and skill not in data["skills_used"]:
        data["skills_used"].append(skill)
    if task_type and task_type not in data["task_types"]:
        data["task_types"].append(task_type)
    if model and model not in data["models_used"]:
        data["models_used"].append(model)

    # Track supplementary skills (v2.0.0)
    if supplementary_skills:
        for s in supplementary_skills.split(','):
            s = s.strip()
            if s and s not in data.get("all_supplementary_skills", []):
                data.setdefault("all_supplementary_skills", []).append(s)

    # Track plan mode usage (v2.0.0)
    if str(plan_mode).lower() == 'true':
        data["plan_mode_count"] = data.get("plan_mode_count", 0) + 1

    # Track context usage over time (v2.0.0)
    try:
        ctx = int(context_pct)
        ctx_history = data.setdefault("context_history", [])
        ctx_history.append(ctx)
        data["peak_context_pct"] = max(data.get("peak_context_pct", 0), ctx)
    except (ValueError, TypeError):
        pass

    # Track standards/rules (v2.0.0)
    try:
        data["standards_count"] = int(standards_count)
        data["rules_count"] = int(rules_count)
    except (ValueError, TypeError):
        pass

    # Track total prompt chars (v2.1.0)
    data["total_prompt_chars"] = data.get("total_prompt_chars", 0) + len(prompt)

    # Extract project from cwd
    if cwd:
        project = _extract_project(cwd)
        if project and project not in data["projects_touched"]:
            data["projects_touched"].append(project)

    # Track max and total complexity (v2.0.0: also track total for average)
    try:
        c = int(complexity)
        if c > data.get("max_complexity", 0):
            data["max_complexity"] = c
        data["total_complexity"] = data.get("total_complexity", 0) + c
    except (ValueError, TypeError):
        pass

    # Write back
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(data, f, indent=2)
            _unlock_file(f)
        log_event(f"[OK] Accumulated request #{data['request_count']} for {session_id}")
        return True
    except Exception as e:
        log_event(f"[ERROR] Failed to accumulate for {session_id}: {e}")
        return False


def _new_summary(session_id):
    """Create a new empty summary structure for a session.

    Initialises all aggregate counters to zero and empty lists so
    accumulate() can safely use setdefault and arithmetic on the returned dict.

    Args:
        session_id (str): Session identifier to embed in the summary.

    Returns:
        dict: Fresh summary dict at version '2.1.0' with all required fields.
    """
    return {
        "version": "2.1.0",
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "status": "ACTIVE",
        "request_count": 0,
        "requests": [],
        "skills_used": [],
        "all_supplementary_skills": [],
        "task_types": [],
        "models_used": [],
        "projects_touched": [],
        "max_complexity": 0,
        "total_complexity": 0,
        "plan_mode_count": 0,
        "peak_context_pct": 0,
        "context_history": [],
        "standards_count": 0,
        "rules_count": 0,
        "summary_text": None,
        # v2.1.0: Quality metrics
        "total_prompt_chars": 0,
        "error_rate_pct": 0.0,
        "success_rate_pct": 100.0,
        "total_tool_calls": 0,
    }


def _extract_project(cwd):
    """Extract a meaningful project name from an absolute working directory path.

    Prefers directory parts that start with known project prefixes
    ('techdeveloper-', 'surgricalswale-', 'lovepoet-') or match their short
    forms.  Falls back to the last non-generic directory name (skipping
    'backend', 'src', 'Documents', etc.).

    Args:
        cwd (str): Absolute path to the project's working directory.

    Returns:
        str or None: Extracted project name, or None when no meaningful name
                     can be determined.
    """
    parts = Path(cwd).parts
    for part in reversed(parts):
        if part.startswith(('techdeveloper-', 'surgricalswale-', 'lovepoet-')):
            return part
        if part in ('techdeveloper', 'surgricalswale', 'lovepoet'):
            return part
    # Fallback: last non-generic directory name
    for part in reversed(parts):
        if part not in ('backend', 'frontend', 'src', 'main', 'java', 'resources',
                        'Documents', 'Users', 'workspace-spring-tool-suite-4-4.27.0-new',
                        'C:', 'c'):
            return part
    return None


# =============================================================================
# WORK STORY - Narrative reconstruction from tool activity
# =============================================================================

def _build_work_stories(requests, tool_entries):
    """
    Build a narrative 'Work Story' for each user request.
    Groups tool entries by request time window and reconstructs
    what was investigated, planned, changed, and the outcome.

    Returns list of story dicts, one per request.
    """
    if not requests:
        return []

    stories = []

    # Parse request timestamps for time-window grouping
    req_times = []
    for req in requests:
        ts_str = req.get("timestamp", "")
        try:
            req_times.append(datetime.fromisoformat(ts_str))
        except Exception:
            req_times.append(None)

    # Parse tool entry timestamps
    parsed_entries = []
    for entry in tool_entries:
        ts_str = entry.get("ts", "")
        try:
            parsed_entries.append((datetime.fromisoformat(ts_str), entry))
        except Exception:
            pass

    # Assign tool entries to the request they belong to (by time window)
    for i, req in enumerate(requests):
        start_time = req_times[i]
        # End time = next request's start, or far future
        if i + 1 < len(req_times) and req_times[i + 1]:
            end_time = req_times[i + 1]
        else:
            end_time = datetime(2099, 12, 31)

        # Collect entries in this time window
        req_entries = []
        if start_time:
            for entry_time, entry in parsed_entries:
                if start_time <= entry_time < end_time:
                    req_entries.append(entry)

        # Build the story for this request
        story = _analyze_request_activity(req, req_entries)
        stories.append(story)

    return stories


def _analyze_request_activity(req, entries):
    """
    Analyze a single request's tool activity and produce a narrative story.

    Returns a dict with:
      - task: what was asked (from prompt)
      - investigation: what was read/searched (findings)
      - planning: tasks created, agents delegated
      - changes: what was written/edited (the fix/implementation)
      - commands: what was run (tests, builds, etc.)
      - outcome: success/errors summary
    """
    prompt = req.get("prompt", "")[:300]
    task_type = req.get("task_type", "")

    # Categorize activities
    investigation = []  # Read, Grep, Glob, WebSearch, WebFetch
    planning = []       # TaskCreate, Agent, EnterPlanMode, Skill
    changes = []        # Write, Edit
    commands = []       # Bash
    errors = []         # Any error entries

    for e in entries:
        tool = e.get("tool", "")
        status = e.get("status", "success")
        file_path = e.get("file", "")

        if status == "error":
            err_desc = f"{tool}"
            if file_path:
                err_desc += f" on `{file_path}`"
            elif e.get("command"):
                err_desc += f": `{e['command'][:60]}`"
            errors.append(err_desc)

        if tool == "Read":
            if file_path:
                investigation.append(f"Read `{file_path}`")

        elif tool == "Grep":
            pattern = e.get("pattern", "")
            search_path = e.get("search_path", "")
            if pattern:
                desc = f"Searched for `{pattern}`"
                if search_path:
                    desc += f" in `{search_path}`"
                investigation.append(desc)

        elif tool == "Glob":
            pattern = e.get("pattern", "")
            if pattern:
                investigation.append(f"Found files matching `{pattern}`")

        elif tool in ("WebSearch", "WebFetch"):
            query = e.get("query", "")
            if query:
                investigation.append(f"Web lookup: {query[:80]}")

        elif tool == "Edit":
            if file_path:
                old_hint = e.get("old_hint", "")
                new_hint = e.get("new_hint", "")
                edit_size = e.get("edit_size", 0)
                desc = f"Edited `{file_path}`"
                if old_hint and new_hint:
                    desc += f" (changed `{old_hint[:40]}...` -> `{new_hint[:40]}...`)"
                elif edit_size > 0:
                    desc += f" (+{edit_size} chars)"
                changes.append(desc)

        elif tool == "Write":
            if file_path:
                lines_count = e.get("content_lines", 0)
                desc = f"Wrote `{file_path}`"
                if lines_count:
                    desc += f" ({lines_count} lines)"
                changes.append(desc)

        elif tool == "Bash":
            cmd = e.get("command", "")
            desc_text = e.get("desc", "")
            if desc_text:
                commands.append(desc_text[:100])
            elif cmd:
                # Clean up command for readability
                cmd_short = cmd.strip()[:80]
                commands.append(f"`{cmd_short}`")

        elif tool == "TaskCreate":
            subject = e.get("task_subject", "")
            if subject:
                planning.append(f"Created task: {subject}")

        elif tool == "TaskUpdate":
            task_status = e.get("task_status", "")
            task_id = e.get("task_id", "")
            if task_status == "completed":
                planning.append(f"Completed task #{task_id}")
            elif task_status == "in_progress":
                planning.append(f"Started task #{task_id}")

        elif tool == "Agent":
            desc_text = e.get("desc", "")
            agent_type = e.get("agent_type", "")
            if desc_text:
                planning.append(f"Delegated to {agent_type}: {desc_text}")
            elif agent_type:
                planning.append(f"Used {agent_type} agent")

        elif tool == "Skill":
            skill_name = e.get("skill_name", "")
            if skill_name:
                planning.append(f"Invoked skill: {skill_name}")

    # Deduplicate (keep order)
    investigation = _dedupe_list(investigation)
    changes = _dedupe_list(changes)
    commands = _dedupe_list(commands)

    return {
        "task": prompt,
        "task_type": task_type,
        "investigation": investigation,
        "planning": planning,
        "changes": changes,
        "commands": commands,
        "errors": errors,
        "tool_count": len(entries),
    }


def _dedupe_list(items):
    """Remove duplicates from a list while preserving insertion order.

    Args:
        items (list): Input list that may contain duplicate strings.

    Returns:
        list: New list with first occurrences of each item retained.
    """
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# =============================================================================
# DATA ENRICHMENT - Pull data from other sources on finalize
# =============================================================================

def _load_tool_stats(session_id):
    """Load tool usage statistics from session-progress.json for the given session.

    Only returns data when the session_id in session-progress.json matches the
    requested session to avoid returning stale data from a different session.

    Args:
        session_id (str): Session identifier to match against the progress file.

    Returns:
        dict: Stat fields including 'tool_counts', 'total_progress',
              'content_chars', 'tasks_completed', 'errors_seen',
              'context_estimate_pct', and 'modified_files_since_commit'.
              Returns {} when the file is missing, unreadable, or belongs to a
              different session.
    """
    progress_file = LOGS_DIR / 'session-progress.json'
    try:
        if progress_file.exists():
            with open(progress_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
            # Only use if it matches this session
            if data.get('session_id', '') == session_id:
                return {
                    "tool_counts": data.get("tool_counts", {}),
                    "total_progress": data.get("total_progress", 0),
                    "content_chars": data.get("content_chars", 0),
                    "tasks_completed": data.get("tasks_completed", 0),
                    "errors_seen": data.get("errors_seen", 0),
                    "context_estimate_pct": data.get("context_estimate_pct", 0),
                    "modified_files_since_commit": data.get("modified_files_since_commit", []),
                }
    except Exception as e:
        log_event(f"[WARN] Could not load tool stats: {e}")
    return {}


def _load_tool_tracker_entries(session_id):
    """Load and filter tool-tracker.jsonl entries for the given session.

    Reads the JSONL file and filters entries to those whose timestamp is on or
    after the session's start_time (from the session JSON file).  Also
    classifies entries into files_modified, files_read, and error_entries.

    Args:
        session_id (str): Session identifier used to look up the session start
                          time and filter relevant entries.

    Returns:
        tuple: (entries, files_modified, files_read, error_entries) where each
               element is a list.  Returns four empty lists when the tracker
               file does not exist.
    """
    tracker_file = LOGS_DIR / 'tool-tracker.jsonl'
    entries = []
    files_modified = []
    files_read = []
    error_entries = []

    if not tracker_file.exists():
        return entries, files_modified, files_read, error_entries

    # Get session start time from session JSON
    session_start = None
    session_file = SESSIONS_DIR / f'{session_id}.json'
    if session_file.exists():
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                sess = json.load(f)
                _unlock_file(f)
            start_str = sess.get('start_time', '')
            if start_str:
                session_start = datetime.fromisoformat(start_str)
        except Exception:
            pass

    try:
        with open(tracker_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Filter entries by session time window
                    if session_start:
                        entry_ts = entry.get('ts', '')
                        if entry_ts:
                            try:
                                entry_time = datetime.fromisoformat(entry_ts)
                                if entry_time < session_start:
                                    continue
                            except Exception:
                                continue

                    entries.append(entry)

                    # Track files
                    file_path = entry.get('file', '')
                    tool = entry.get('tool', '')
                    status = entry.get('status', '')

                    if file_path:
                        if tool in ('Write', 'Edit', 'NotebookEdit') and status == 'success':
                            if file_path not in files_modified:
                                files_modified.append(file_path)
                        elif tool == 'Read' and status == 'success':
                            if file_path not in files_read:
                                files_read.append(file_path)

                    if status == 'error':
                        error_entries.append(entry)

                except Exception:
                    continue
    except Exception as e:
        log_event(f"[WARN] Could not load tool tracker: {e}")

    return entries, files_modified, files_read, error_entries


def _load_flow_trace(session_id):
    """Load the flow-trace.json pipeline decision data for a session.

    Uses _lock_file/_unlock_file (Windows file locking, Loophole #19) to
    prevent reading a partially written file.

    Args:
        session_id (str): Session identifier used to locate the trace file at
                          session_log_dir(session_id)/flow-trace.json.

    Returns:
        dict: Full flow-trace data, or {} when the file is missing or
              unreadable.
    """
    flow_trace = session_log_dir(session_id) / 'flow-trace.json'
    if not flow_trace.exists():
        return {}
    try:
        with open(flow_trace, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data
    except Exception:
        return {}


def _load_policy_execution_data(session_id):
    """Load policy execution tracking data from flow-trace.json for a session.

    Reads the all_policies_executed array from flow-trace.json and computes
    aggregate statistics: total count, total duration, slowest/fastest
    policies, and the decisions_timeline list.

    Uses _lock_file/_unlock_file (Windows file locking, Loophole #19) to
    prevent reading a partially written file.

    Args:
        session_id (str): Session identifier used to locate the trace file at
                          session_log_dir(session_id)/flow-trace.json.

    Returns:
        dict or None: Dict with keys 'total_policies', 'total_duration_ms',
                      'policies', 'slowest_policies', 'fastest_policies', and
                      'decisions_timeline'.  Returns None when the file is
                      missing, unreadable, or contains no policy records.
    """
    flow_trace_path = session_log_dir(session_id) / 'flow-trace.json'
    if not flow_trace_path.exists():
        return None

    try:
        with open(flow_trace_path, 'r', encoding='utf-8') as f:
            _lock_file(f)
            trace = json.load(f)
            _unlock_file(f)
    except Exception as e:
        log_event(f"[WARN] Could not load flow-trace for policy data: {e}")
        return None

    try:
        policies = trace.get("all_policies_executed", [])
        if not policies:
            return None

        total_duration_ms = 0
        policy_records = []
        for p in policies:
            try:
                duration_ms = int(p.get("duration_ms", 0))
            except (TypeError, ValueError):
                duration_ms = 0
            total_duration_ms += duration_ms
            policy_records.append({
                "name": str(p.get("name", p.get("script", "unknown"))),
                "duration_ms": duration_ms,
                "decision": str(p.get("decision", p.get("result", ""))),
                "timestamp": str(p.get("timestamp", "")),
                "type": str(p.get("type", "Hook")),
            })

        sorted_by_duration = sorted(policy_records, key=lambda x: x["duration_ms"], reverse=True)
        slowest = sorted_by_duration[:3]
        fastest = sorted(policy_records, key=lambda x: x["duration_ms"])[:3]

        decisions_timeline = trace.get("decisions_timeline", [])

        return {
            "total_policies": len(policy_records),
            "total_duration_ms": total_duration_ms,
            "policies": policy_records,
            "slowest_policies": slowest,
            "fastest_policies": fastest,
            "decisions_timeline": decisions_timeline,
        }
    except Exception as e:
        log_event(f"[WARN] Error processing policy execution data: {e}")
        return None


def _load_session_json(session_id):
    """Load the session metadata JSON from the sessions directory.

    Uses _lock_file/_unlock_file (Windows file locking, Loophole #19).

    Args:
        session_id (str): Session identifier used to locate
                          SESSIONS_DIR/{session_id}.json.

    Returns:
        dict: Session metadata, or {} when the file is missing or unreadable.
    """
    session_file = SESSIONS_DIR / f'{session_id}.json'
    if not session_file.exists():
        return {}
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data
    except Exception:
        return {}


def _load_tool_optimization_stats(session_id):
    """
    Load tool optimization statistics from session-progress.json.

    Reads the tool_optimization_stats block that contains failure detection
    counts and per-tool optimization statistics from the post-tool-tracker.py
    hook enhancements (Level 3.7 middleware).

    Args:
        session_id (str): Session identifier.

    Returns:
        dict: Tool optimization stats with 'total_failures_detected_in_results'
              and 'per_tool_failure_counts', or {} when unavailable.
    """
    try:
        progress_file = LOGS_DIR / 'session-progress.json'
        if not progress_file.exists():
            return {}
        with open(progress_file, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data.get('tool_optimization_stats', {})
    except Exception:
        return {}


def _calculate_duration(created_at, last_updated):
    """Calculate the elapsed time between two ISO 8601 timestamps.

    Args:
        created_at (str): ISO timestamp for the start of the interval.
        last_updated (str): ISO timestamp for the end of the interval.

    Returns:
        tuple: (human_readable, total_seconds) where human_readable is a
               string like '1h 23m 45s' and total_seconds is an integer.
               Returns ('unknown', 0) on any parse error.
    """
    try:
        start = datetime.fromisoformat(created_at)
        end = datetime.fromisoformat(last_updated)
        delta = end - start
        total_seconds = int(delta.total_seconds())

        if total_seconds < 0:
            return "0s", 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return ' '.join(parts), total_seconds
    except Exception:
        return "unknown", 0


# =============================================================================
# FINALIZE - Called on session close by clear-session-handler.py
# =============================================================================

def finalize(session_id):
    """Generate the comprehensive session summary on session close.

    Merges data from four sources, generates session-summary.md, updates the
    session-summary.json with status=COMPLETED, writes a one-liner summary_text,
    updates the chain-index, and optionally triggers context auto-cleanup.

    Data sources:
      1. Accumulated per-request JSON (session-summary.json) from accumulate().
      2. Tool usage stats from session-progress.json (_load_tool_stats).
      3. Detailed tool entries + files from tool-tracker.jsonl
         (_load_tool_tracker_entries).
      4. Pipeline decisions from flow-trace.json (_load_flow_trace).

    Called by clear-session-handler.py on /clear.

    Args:
        session_id (str): Session identifier to finalise.

    Returns:
        bool: True on success; False when session_id is falsy or the summary
              markdown cannot be written.
    """
    if not session_id:
        return False

    json_path = summary_json_path(session_id)
    if not json_path.exists():
        log_event(f"[WARN] No accumulated data for {session_id}, building from session JSON")
        data = _build_from_session_json(session_id)
        if not data:
            return False
    else:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                _lock_file(f)
                data = json.load(f)
                _unlock_file(f)
        except Exception as e:
            log_event(f"[ERROR] Failed to read summary JSON for {session_id}: {e}")
            return False

    # === ENRICH DATA FROM EXTERNAL SOURCES (v2.0.0) ===

    # 1. Tool usage stats from session-progress.json
    tool_stats = _load_tool_stats(session_id)
    if tool_stats:
        data["tool_stats"] = tool_stats

    # 2. Detailed tool entries + files from tool-tracker.jsonl
    tool_entries, files_modified, files_read, error_entries = _load_tool_tracker_entries(session_id)
    data["files_modified"] = files_modified
    data["files_read"] = files_read
    data["tool_entry_count"] = len(tool_entries)
    data["error_count"] = len(error_entries)
    if error_entries:
        data["errors"] = [
            {"ts": e.get("ts", ""), "tool": e.get("tool", ""), "file": e.get("file", "")}
            for e in error_entries[:10]  # Keep last 10 errors max
        ]

    # 3. Flow trace decisions + script inventory
    flow_trace = _load_flow_trace(session_id)
    if flow_trace:
        final_decision = flow_trace.get("final_decision", {})
        data["last_flow_decision"] = {
            "task_type": final_decision.get("task_type", ""),
            "complexity": final_decision.get("complexity", 0),
            "model_selected": final_decision.get("model_selected", ""),
            "model_reason": final_decision.get("model_reason", ""),
            "skill_or_agent": final_decision.get("skill_or_agent", ""),
            "supplementary_skills": final_decision.get("supplementary_skills", []),
            "tech_stack": final_decision.get("tech_stack", []),
            "execution_mode": final_decision.get("execution_mode", ""),
            "task_count": final_decision.get("task_count", 0),
            "standards_active": final_decision.get("standards_active", 0),
            "rules_active": final_decision.get("rules_active", 0),
        }
        meta = flow_trace.get("meta", {})
        data["flow_version"] = meta.get("flow_version", "")
        data["flow_duration_ms"] = int(meta.get("duration_seconds", 0) * 1000)

        # 3b. Script inventory from flow-trace (all 82 scripts)
        script_inv = flow_trace.get("script_inventory", {})
        if script_inv:
            inv_summary = script_inv.get("summary", {})
            data["script_inventory_summary"] = {
                "total_scripts": inv_summary.get("total_scripts", 0),
                "executed_this_session": inv_summary.get("total_executed_this_session", 0),
                "available_on_demand": inv_summary.get("total_available", 0),
                "hook_scripts": inv_summary.get("hook_scripts", 0),
                "active_executed": inv_summary.get("active_executed", 0),
                "active_inline": inv_summary.get("active_inline", 0),
                "daemon_skipped": inv_summary.get("daemon_skipped", 0),
                "phase4_stubs": inv_summary.get("phase4_stubs", 0),
                "superseded": inv_summary.get("superseded", 0),
            }

    # 3c. Policy execution tracking from flow-trace.json
    try:
        policy_exec_data = _load_policy_execution_data(session_id)
        if policy_exec_data:
            data["policy_execution_summary"] = {
                "total_policies": policy_exec_data.get("total_policies", 0),
                "total_duration_ms": policy_exec_data.get("total_duration_ms", 0),
                "slowest_policies": policy_exec_data.get("slowest_policies", [])[:3],
                "fastest_policies": policy_exec_data.get("fastest_policies", [])[:3],
                "decisions_count": len(policy_exec_data.get("decisions_timeline", [])),
            }
            data["all_policies_executed"] = policy_exec_data.get("policies", [])
            data["decisions_timeline"] = policy_exec_data.get("decisions_timeline", [])
    except Exception as e:
        log_event(f"[WARN] Policy execution data loading failed (non-blocking): {e}")

    # 3d. Tool Optimization Stats (3.6 + 3.7 Middleware) - NEW v3.2.0
    try:
        tool_opt_stats = _load_tool_optimization_stats(session_id)
        if tool_opt_stats:
            data["tool_optimization_stats"] = tool_opt_stats
    except Exception as e:
        log_event(f"[WARN] Tool optimization stats loading failed (non-blocking): {e}")

    # 4. Session metadata (duration, status)
    session_json = _load_session_json(session_id)
    if session_json:
        data["session_description"] = session_json.get("description", "")
        data["flow_runs"] = session_json.get("flow_runs", 0)

    # 5. Calculate duration
    duration_human, duration_seconds = _calculate_duration(
        data.get("created_at", ""),
        data.get("last_updated", "")
    )
    data["duration_human"] = duration_human
    data["duration_seconds"] = duration_seconds

    # 6. Calculate average complexity
    req_count = data.get("request_count", 0)
    total_complexity = data.get("total_complexity", 0)
    data["avg_complexity"] = round(total_complexity / req_count, 1) if req_count > 0 else 0

    # 6b. Calculate quality metrics (v2.1.0)
    total_tool_calls_calc = len(tool_entries)
    error_count_calc = len(error_entries)
    data["total_tool_calls"] = total_tool_calls_calc
    if total_tool_calls_calc > 0:
        data["error_rate_pct"] = round((error_count_calc / total_tool_calls_calc) * 100, 1)
        data["success_rate_pct"] = round(((total_tool_calls_calc - error_count_calc) / total_tool_calls_calc) * 100, 1)
    else:
        data["error_rate_pct"] = 0.0
        data["success_rate_pct"] = 100.0

    # 7. Build work stories (narrative per request)
    work_stories = _build_work_stories(data.get("requests", []), tool_entries)
    data["work_stories"] = work_stories

    # === GENERATE OUTPUT ===

    # Generate markdown summary
    md = _generate_markdown(data)

    # Write session-summary.md
    md_path = summary_md_path(session_id)
    try:
        md_path.write_text(md, encoding='utf-8')
        log_event(f"[OK] Comprehensive summary MD generated: {md_path}")
    except Exception as e:
        log_event(f"[ERROR] Failed to write summary MD for {session_id}: {e}")
        return False

    # Update JSON with status and summary text
    data["status"] = "COMPLETED"
    data["summary_text"] = _generate_one_liner(data)
    data["finalized_at"] = datetime.now().isoformat()
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(data, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass

    # Update chain-index with summary
    _update_chain_summary(session_id, data)

    # AUTO-CLEANUP: Check context and trigger cleanup if needed
    try:
        auto_trigger_cleanup_if_needed(session_id, data)
    except Exception as e:
        log_event(f"[INFO] Auto-cleanup check failed (non-blocking): {e}")

    return True


def auto_trigger_cleanup_if_needed(session_id, summary_data):
    """Execute automatic cleanup when estimated context usage exceeds 90%.

    Estimates context usage from request_count * 1500 tokens per request
    against the 200k-token limit.  When above 90%, deletes old session files
    (keeps last 5) and old log directories (keeps last 10), then resets the
    context baseline to 10% for the next session.

    Called from finalize() after every session close.  Non-blocking: errors
    are caught and logged.

    Args:
        session_id (str): Session identifier used for log messages.
        summary_data (dict): Finalised summary dict containing 'request_count'.
    """
    request_count = summary_data.get("request_count", 0)
    estimated_tokens_per_request = 1500
    estimated_used = request_count * estimated_tokens_per_request
    total_context_window = 200000
    estimated_percentage = (estimated_used / total_context_window) * 100

    log_event(f"[CHECK] Session {session_id}: Estimated context usage = {estimated_percentage:.1f}%")

    if estimated_percentage > 90:
        log_event(f"[ALERT] Context high ({estimated_percentage:.1f}%) - AUTO-EXECUTING cleanup NOW")

        old_sessions_deleted = _execute_session_cleanup()
        log_event(f"[CLEANUP] Deleted {old_sessions_deleted} old session files")

        baseline_file = (LOGS_DIR / 'context-baseline.json')
        baseline_file.parent.mkdir(parents=True, exist_ok=True)

        baseline = {
            "last_cleanup_session": session_id,
            "last_cleanup_time": datetime.now().isoformat(),
            "old_sessions_deleted": old_sessions_deleted,
            "old_logs_compacted": _cleanup_old_logs(),
            "context_reset_to": 10,
        }

        with open(baseline_file, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(baseline, f, indent=2)
            _unlock_file(f)

        log_event(f"[BASELINE] Context reset to 10% for next session")


def _execute_session_cleanup():
    """Delete old session JSON files from SESSIONS_DIR, keeping the 5 newest.

    Returns:
        int: Number of session files deleted.
    """
    deleted_count = 0
    try:
        sessions = sorted(list(SESSIONS_DIR.glob('SESSION-*.json')),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        sessions_to_keep = 5
        for old_session_file in sessions[sessions_to_keep:]:
            try:
                old_session_file.unlink()
                deleted_count += 1
            except Exception:
                pass
    except Exception:
        pass
    return deleted_count


def _cleanup_old_logs():
    """Delete old per-session log directories from LOGS_DIR/sessions/, keeping 10 newest.

    Uses shutil.rmtree for recursive directory deletion.  Errors on individual
    directories are silently ignored.

    Returns:
        int: Number of log directories deleted.
    """
    cleaned_count = 0
    try:
        session_logs = sorted(list((LOGS_DIR / 'sessions').glob('SESSION-*')),
                             key=lambda p: p.stat().st_mtime, reverse=True)
        logs_to_keep = 10
        for old_log_dir in session_logs[logs_to_keep:]:
            try:
                import shutil
                shutil.rmtree(old_log_dir)
                cleaned_count += 1
            except Exception:
                pass
    except Exception:
        pass
    return cleaned_count


def _build_from_session_json(session_id):
    """Build summary data from session JSON when no accumulated data exists"""
    session_file = SESSIONS_DIR / f'{session_id}.json'
    if not session_file.exists():
        return None

    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            _lock_file(f)
            sess = json.load(f)
            _unlock_file(f)
    except Exception:
        return None

    data = _new_summary(session_id)
    data["created_at"] = sess.get("start_time", data["created_at"])

    if sess.get("last_prompt"):
        data["requests"].append({
            "timestamp": sess.get("last_updated", ""),
            "prompt": sess.get("last_prompt", "")[:500],
            "task_type": sess.get("last_task_type", ""),
            "skill": sess.get("last_model", ""),
            "complexity": sess.get("last_complexity", 0),
            "model": sess.get("last_model", ""),
            "cwd": "",
            "plan_mode": False,
            "context_pct": sess.get("last_context_pct", 0),
            "supplementary_skills": [],
        })
        data["request_count"] = 1

    if sess.get("last_task_type"):
        data["task_types"].append(sess["last_task_type"])
    if sess.get("last_model"):
        data["models_used"].append(sess["last_model"])

    json_path = summary_json_path(session_id)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(data, f, indent=2)
            _unlock_file(f)
    except Exception:
        pass

    return data


# =============================================================================
# SUMMARY GENERATION
# =============================================================================

def _generate_one_liner(data):
    """Generate a comprehensive single-line summary of the session"""
    req_count = data.get("request_count", 0)
    projects = data.get("projects_touched", [])
    skills = data.get("skills_used", [])
    types = data.get("task_types", [])
    duration = data.get("duration_human", "")
    max_c = data.get("max_complexity", 0)
    files_mod = len(data.get("files_modified", []))
    tool_stats = data.get("tool_stats", {})
    tool_calls = sum(tool_stats.get("tool_counts", {}).values()) if tool_stats else 0

    parts = []
    parts.append(f"{req_count} requests")

    if duration and duration != "unknown":
        parts.append(f"duration: {duration}")

    if projects:
        parts.append(f"project: {', '.join(projects[:2])}")
    if types:
        parts.append(f"type: {', '.join(types[:3])}")
    if skills:
        parts.append(f"skills: {', '.join(skills[:3])}")
    if max_c > 0:
        parts.append(f"max-complexity: {max_c}/25")
    if tool_calls > 0:
        parts.append(f"tool-calls: {tool_calls}")
    if files_mod > 0:
        parts.append(f"files-modified: {files_mod}")

    if data.get("requests"):
        first_prompt = data["requests"][0].get("prompt", "")[:60]
        if first_prompt:
            parts.append(f"started: {first_prompt}")

    return " | ".join(parts)


def _generate_markdown(data):
    """Generate COMPREHENSIVE human-readable session-summary.md (v2.0.0)"""
    session_id = data.get("session_id", "UNKNOWN")
    created = data.get("created_at", "")[:19].replace('T', ' ')
    last_updated = data.get("last_updated", "")[:19].replace('T', ' ')
    req_count = data.get("request_count", 0)
    skills = data.get("skills_used", [])
    supp_skills = data.get("all_supplementary_skills", [])
    types = data.get("task_types", [])
    models = data.get("models_used", [])
    projects = data.get("projects_touched", [])
    max_complexity = data.get("max_complexity", 0)
    avg_complexity = data.get("avg_complexity", 0)
    requests = data.get("requests", [])
    duration_human = data.get("duration_human", "unknown")
    duration_seconds = data.get("duration_seconds", 0)
    plan_mode_count = data.get("plan_mode_count", 0)
    peak_context = data.get("peak_context_pct", 0)
    standards_count = data.get("standards_count", 0)
    rules_count = data.get("rules_count", 0)
    tool_stats = data.get("tool_stats", {})
    files_modified = data.get("files_modified", [])
    files_read = data.get("files_read", [])
    error_count = data.get("error_count", 0)
    errors = data.get("errors", [])
    flow_decision = data.get("last_flow_decision", {})
    flow_version = data.get("flow_version", "")
    flow_runs = data.get("flow_runs", 0)

    lines = []

    # ===================== HEADER =====================
    lines.append(f"# Session Summary: {session_id}")
    lines.append("")

    # ===================== OVERVIEW TABLE =====================
    lines.append("## Overview")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Session ID | `{session_id}` |")
    lines.append(f"| Status | **{data.get('status', 'UNKNOWN')}** |")
    lines.append(f"| Created | {created} |")
    lines.append(f"| Last Updated | {last_updated} |")
    lines.append(f"| Duration | **{duration_human}** |")
    lines.append(f"| Total Requests | **{req_count}** |")
    lines.append(f"| Flow Runs | {flow_runs} |")
    if projects:
        lines.append(f"| Projects | {', '.join(projects)} |")
    if flow_version:
        lines.append(f"| Flow Version | {flow_version} |")
    lines.append("")

    # ===================== SESSION METRICS =====================
    lines.append("## Session Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Max Complexity | **{max_complexity}/25** |")
    lines.append(f"| Avg Complexity | {avg_complexity}/25 |")
    lines.append(f"| Peak Context Usage | {peak_context}% |")
    lines.append(f"| Plan Mode Used | {plan_mode_count} time(s) |")
    lines.append(f"| Standards Active | {standards_count} |")
    lines.append(f"| Rules Active | {rules_count} |")
    lines.append(f"| Errors Encountered | {error_count} |")

    tool_counts = tool_stats.get("tool_counts", {})
    total_tool_calls = sum(tool_counts.values()) if tool_counts else 0
    lines.append(f"| Total Tool Calls | {total_tool_calls} |")
    lines.append(f"| Files Modified | {len(files_modified)} |")
    lines.append(f"| Files Read | {len(files_read)} |")
    tasks_completed = tool_stats.get("tasks_completed", 0)
    if tasks_completed > 0:
        lines.append(f"| Tasks Completed | {tasks_completed} |")
    # v2.1.0: Quality metrics
    error_rate = data.get("error_rate_pct", 0.0)
    success_rate = data.get("success_rate_pct", 100.0)
    lines.append(f"| Success Rate | **{success_rate}%** |")
    lines.append(f"| Error Rate | {error_rate}% |")
    total_prompt_chars = data.get("total_prompt_chars", 0)
    if total_prompt_chars > 0:
        lines.append(f"| Total Prompt Chars | {total_prompt_chars} |")
    lines.append("")

    # ===================== SKILLS & MODELS =====================
    lines.append("## Skills & Models Used")
    lines.append("")
    if skills:
        lines.append(f"**Primary Skills:** {', '.join(skills)}")
    else:
        lines.append("**Primary Skills:** None")
    if supp_skills:
        lines.append(f"**Supplementary Skills:** {', '.join(supp_skills)}")
    lines.append(f"**Models:** {', '.join(models) if models else 'None'}")
    lines.append(f"**Task Types:** {', '.join(types) if types else 'None'}")
    if flow_decision.get("tech_stack"):
        lines.append(f"**Tech Stack:** {', '.join(flow_decision['tech_stack'])}")
    lines.append("")

    # ===================== TOOL USAGE STATS =====================
    if tool_counts:
        lines.append("## Tool Usage Statistics")
        lines.append("")
        lines.append("| Tool | Calls | Contribution |")
        lines.append("|------|-------|-------------|")

        # Sort by count descending
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        for tool_name, count in sorted_tools:
            pct = round((count / total_tool_calls) * 100, 1) if total_tool_calls > 0 else 0
            bar_len = int(pct / 5)  # Simple bar
            bar = '#' * bar_len
            lines.append(f"| {tool_name} | {count} | {pct}% {bar} |")
        lines.append(f"| **TOTAL** | **{total_tool_calls}** | **100%** |")
        lines.append("")

    # ===================== TOOL OPTIMIZATION SUMMARY (3.6 + 3.7 Middleware) =====================
    # NEW v3.2.0: Display results of Level 3.6 and 3.7 policy enforcement
    tool_opt_stats = data.get("tool_optimization_stats", {})
    if tool_opt_stats.get("total_failures_detected_in_results", 0) > 0:
        lines.append("## Tool Optimization Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Tool Calls | {total_tool_calls} |")

        total_failures = tool_opt_stats.get("total_failures_detected_in_results", 0)
        lines.append(f"| Failures Detected (3.7) | {total_failures} |")

        per_tool_counts = tool_opt_stats.get("per_tool_failure_counts", {})
        if per_tool_counts:
            most_common_tools = sorted(per_tool_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            if most_common_tools:
                most_common_str = ", ".join([f"{t}: {c}" for t, c in most_common_tools])
                lines.append(f"| Most Problematic Tools | {most_common_str} |")

        lines.append("")

    # ===================== FILES MODIFIED =====================
    if files_modified:
        lines.append("## Files Modified")
        lines.append("")
        for i, f in enumerate(files_modified[:20], 1):
            lines.append(f"{i}. `{f}`")
        if len(files_modified) > 20:
            lines.append(f"... and {len(files_modified) - 20} more files")
        lines.append("")

    # ===================== FILES READ =====================
    if files_read:
        lines.append("## Files Read")
        lines.append("")
        for i, f in enumerate(files_read[:15], 1):
            lines.append(f"{i}. `{f}`")
        if len(files_read) > 15:
            lines.append(f"... and {len(files_read) - 15} more files")
        lines.append("")

    # ===================== CONTEXT USAGE TREND =====================
    context_history = data.get("context_history", [])
    if context_history and len(context_history) > 1:
        lines.append("## Context Usage Trend")
        lines.append("")
        lines.append(f"- Start: {context_history[0]}%")
        lines.append(f"- End: {context_history[-1]}%")
        lines.append(f"- Peak: {max(context_history)}%")
        lines.append(f"- Change: {context_history[-1] - context_history[0]:+d}%")
        lines.append("")

    # ===================== ERRORS =====================
    if errors:
        lines.append("## Errors Encountered")
        lines.append("")
        lines.append("| # | Time | Tool | File |")
        lines.append("|---|------|------|------|")
        for i, err in enumerate(errors, 1):
            ts = err.get("ts", "")[-8:]  # HH:MM:SS
            tool = err.get("tool", "")
            file_path = err.get("file", "N/A")
            lines.append(f"| {i} | {ts} | {tool} | `{file_path}` |")
        lines.append("")

    # ===================== SCRIPT INVENTORY (82 scripts) =====================
    inv = data.get("script_inventory_summary", {})
    if inv:
        lines.append("---")
        lines.append("")
        lines.append("## Script Inventory (82 Total)")
        lines.append("")
        lines.append("| Category | Count | Status |")
        lines.append("|----------|-------|--------|")
        lines.append("| Hook Scripts (always running) | " + str(inv.get("hook_scripts", 0)) + " | EXECUTED |")
        lines.append("| Active (subprocess by hooks) | " + str(inv.get("active_executed", 0)) + " | EXECUTED |")
        lines.append("| Active (inline in hooks) | " + str(inv.get("active_inline", 0)) + " | INLINE |")
        lines.append("| On-Demand Utilities | " + str(inv.get("available_on_demand", 0)) + " | AVAILABLE |")
        lines.append("| Daemon (need background) | " + str(inv.get("daemon_skipped", 0)) + " | SKIPPED |")
        lines.append("| Phase-4 Stubs (future) | " + str(inv.get("phase4_stubs", 0)) + " | STUB |")
        lines.append("| Superseded (replaced) | " + str(inv.get("superseded", 0)) + " | SUPERSEDED |")
        lines.append("| **Total Executed This Session** | **" + str(inv.get("executed_this_session", 0)) + "** | |")
        lines.append("| **Total Scripts** | **" + str(inv.get("total_scripts", 0)) + "** | |")
        lines.append("")

    # ===================== WORK STORY (Narrative) =====================
    work_stories = data.get("work_stories", [])
    lines.append("---")
    lines.append("")
    lines.append("## Work Story")
    lines.append("")

    if work_stories and any(s.get("tool_count", 0) > 0 for s in work_stories):
        # Render rich narrative per request
        for i, (req, story) in enumerate(zip(requests, work_stories), 1):
            ts = req.get("timestamp", "")[:19].replace('T', ' ')
            prompt = req.get("prompt", "")[:300]
            task_type = req.get("task_type", "")
            skill = req.get("skill", "")
            model = req.get("model", "")
            complexity = req.get("complexity", 0)
            plan_mode = req.get("plan_mode", False)
            ctx_pct = req.get("context_pct", 0)
            supp = req.get("supplementary_skills", [])
            tool_count = story.get("tool_count", 0)

            lines.append(f"### Request {i}: {task_type or 'General'} ({ts})")
            lines.append("")

            # Task description
            lines.append(f"**Task:** {prompt}")
            meta_parts = []
            if complexity:
                meta_parts.append(f"Complexity: {complexity}/25")
            if model:
                meta_parts.append(f"Model: {model}")
            if skill:
                meta_parts.append(f"Skill: {skill}")
            if plan_mode:
                meta_parts.append("Plan Mode: Yes")
            if ctx_pct:
                meta_parts.append(f"Context: {ctx_pct}%")
            if supp:
                meta_parts.append(f"Supplementary: {', '.join(supp)}")
            if meta_parts:
                lines.append(f"*{' | '.join(meta_parts)}*")
            lines.append("")

            # Investigation / Findings
            investigation = story.get("investigation", [])
            if investigation:
                lines.append("**Investigation & Findings:**")
                for item in investigation[:15]:
                    lines.append(f"  - {item}")
                if len(investigation) > 15:
                    lines.append(f"  - ... and {len(investigation) - 15} more")
                lines.append("")

            # Planning / Task Breakdown
            planning = story.get("planning", [])
            if planning:
                lines.append("**Planning & Delegation:**")
                for item in planning:
                    lines.append(f"  - {item}")
                lines.append("")

            # Changes / Implementation
            changes = story.get("changes", [])
            if changes:
                lines.append("**Changes & Implementation:**")
                for item in changes[:20]:
                    lines.append(f"  - {item}")
                if len(changes) > 20:
                    lines.append(f"  - ... and {len(changes) - 20} more changes")
                lines.append("")

            # Commands Run
            commands = story.get("commands", [])
            if commands:
                lines.append("**Commands Executed:**")
                for item in commands[:10]:
                    lines.append(f"  - {item}")
                if len(commands) > 10:
                    lines.append(f"  - ... and {len(commands) - 10} more commands")
                lines.append("")

            # Errors
            story_errors = story.get("errors", [])
            if story_errors:
                lines.append("**Errors:**")
                for item in story_errors[:5]:
                    lines.append(f"  - {item}")
                lines.append("")

            # Outcome line
            if tool_count > 0:
                outcome_parts = [f"{tool_count} tool calls"]
                if changes:
                    outcome_parts.append(f"{len(changes)} file(s) changed")
                if story_errors:
                    outcome_parts.append(f"{len(story_errors)} error(s)")
                else:
                    outcome_parts.append("no errors")
                lines.append(f"**Outcome:** {' | '.join(outcome_parts)}")
                lines.append("")

            lines.append("---")
            lines.append("")

    else:
        # Fallback: basic request timeline (no tool data available)
        for i, req in enumerate(requests, 1):
            ts = req.get("timestamp", "")[:19].replace('T', ' ')
            prompt = req.get("prompt", "")[:300]
            task_type = req.get("task_type", "")
            skill = req.get("skill", "")
            model = req.get("model", "")
            complexity = req.get("complexity", 0)
            plan_mode = req.get("plan_mode", False)
            ctx_pct = req.get("context_pct", 0)
            supp = req.get("supplementary_skills", [])

            lines.append(f"### Request {i} ({ts})")
            lines.append(f"- **Prompt:** {prompt}")
            if task_type:
                lines.append(f"- **Type:** {task_type}")
            if complexity:
                lines.append(f"- **Complexity:** {complexity}/25")
            if model:
                lines.append(f"- **Model:** {model}")
            if skill:
                lines.append(f"- **Skill/Agent:** {skill}")
            if supp:
                lines.append(f"- **Supplementary:** {', '.join(supp)}")
            if plan_mode:
                lines.append(f"- **Plan Mode:** Yes")
            if ctx_pct:
                lines.append(f"- **Context:** {ctx_pct}%")
            lines.append("")

    # ===================== PIPELINE DECISIONS =====================
    if flow_decision:
        lines.append("## Last Pipeline Decision")
        lines.append("")
        lines.append("| Decision | Value |")
        lines.append("|----------|-------|")
        if flow_decision.get("task_type"):
            lines.append(f"| Task Type | {flow_decision['task_type']} |")
        if flow_decision.get("complexity"):
            lines.append(f"| Complexity | {flow_decision['complexity']}/25 |")
        if flow_decision.get("model_selected"):
            lines.append(f"| Model | {flow_decision['model_selected']} |")
        if flow_decision.get("model_reason"):
            lines.append(f"| Model Reason | {flow_decision['model_reason']} |")
        if flow_decision.get("skill_or_agent"):
            lines.append(f"| Skill/Agent | {flow_decision['skill_or_agent']} |")
        if flow_decision.get("execution_mode"):
            lines.append(f"| Execution Mode | {flow_decision['execution_mode']} |")
        if flow_decision.get("task_count"):
            lines.append(f"| Task Count | {flow_decision['task_count']} |")
        lines.append("")

    # ===================== SESSION INSIGHTS =====================
    insights = _generate_insights(data)
    if insights:
        lines.append("## Session Insights")
        lines.append("")
        for insight in insights:
            lines.append(f"- {insight}")
        lines.append("")

    # ===================== POLICY EXECUTION TIMELINE =====================
    try:
        policy_exec_summary = data.get("policy_execution_summary", {})
        all_policies_executed = data.get("all_policies_executed", [])
        decisions_timeline = data.get("decisions_timeline", [])

        total_pol = policy_exec_summary.get("total_policies", 0)
        if total_pol > 0:
            total_dur_ms = policy_exec_summary.get("total_duration_ms", 0)
            slowest_policies = policy_exec_summary.get("slowest_policies", [])
            fastest_policies = policy_exec_summary.get("fastest_policies", [])
            decisions_count = policy_exec_summary.get("decisions_count", 0)

            lines.append("---")
            lines.append("")
            lines.append(f"## Policy Execution Timeline ({total_pol} Policies)")
            lines.append("")
            lines.append("*Detailed execution flow of policy enforcement during this session*")
            lines.append("")

            # Main policy table sorted by execution order (timestamp)
            sorted_policies = sorted(
                all_policies_executed,
                key=lambda x: x.get("timestamp", "")
            )
            lines.append("| Policy | Duration | Decision | Type |")
            lines.append("|--------|----------|----------|------|")
            for pol in sorted_policies:
                pol_name = pol.get("name", "unknown")
                pol_dur = pol.get("duration_ms", 0)
                pol_decision = pol.get("decision", "")[:60]
                pol_type = pol.get("type", "Hook")

                # Add type badge for better visual distinction
                if "Hook" in pol_type:
                    type_badge = "Hook"
                elif "Policy" in pol_type:
                    type_badge = "Policy"
                else:
                    type_badge = pol_type

                lines.append(f"| {pol_name} | {pol_dur}ms | {pol_decision} | {type_badge} |")
            lines.append("")

            # Execution statistics subsection
            lines.append("### Execution Statistics")
            lines.append("")
            lines.append(f"- **Total Policies**: {total_pol}")
            lines.append(f"- **Total Duration**: {total_dur_ms}ms")

            # Calculate and display average duration
            if total_pol > 0:
                avg_duration = int(total_dur_ms / total_pol)
                lines.append(f"- **Average Duration**: {avg_duration}ms per policy")

            if slowest_policies:
                slowest_top = slowest_policies[0]
                lines.append(
                    f"- **Slowest**: {slowest_top.get('name', 'N/A')} "
                    f"({slowest_top.get('duration_ms', 0)}ms)"
                )
            if fastest_policies:
                fastest_top = fastest_policies[0]
                lines.append(
                    f"- **Fastest**: {fastest_top.get('name', 'N/A')} "
                    f"({fastest_top.get('duration_ms', 0)}ms)"
                )
            if decisions_count > 0:
                lines.append(f"- **Decisions Recorded**: {decisions_count}")
            lines.append("")

            # Policy decisions timeline subsection
            if decisions_timeline:
                lines.append("### Policy Decisions Timeline")
                lines.append("")
                for idx, decision in enumerate(decisions_timeline, 1):
                    if isinstance(decision, dict):
                        dec_policy = decision.get("policy", decision.get("name", "unknown"))
                        dec_text = decision.get("decision", decision.get("result", str(decision)))[:80]
                    else:
                        dec_policy = "policy"
                        dec_text = str(decision)[:80]
                    lines.append(f"{idx}. **{dec_policy}**: {dec_text}")
                lines.append("")
    except Exception:
        pass

    # ===================== TL;DR =====================
    one_liner = _generate_one_liner(data)
    lines.append("---")
    lines.append("")
    lines.append(f"**TL;DR:** {one_liner}")
    lines.append("")

    return "\n".join(lines)


def _generate_insights(data):
    """Auto-generate session insights based on data patterns"""
    insights = []
    req_count = data.get("request_count", 0)
    max_c = data.get("max_complexity", 0)
    avg_c = data.get("avg_complexity", 0)
    tool_stats = data.get("tool_stats", {})
    tool_counts = tool_stats.get("tool_counts", {})
    files_modified = data.get("files_modified", [])
    files_read = data.get("files_read", [])
    error_count = data.get("error_count", 0)
    peak_ctx = data.get("peak_context_pct", 0)
    duration_seconds = data.get("duration_seconds", 0)
    plan_mode_count = data.get("plan_mode_count", 0)
    types = data.get("task_types", [])

    # Session type insight
    if req_count == 1:
        insights.append("Quick single-request session")
    elif req_count <= 3:
        insights.append("Short session with focused work")
    elif req_count <= 10:
        insights.append("Medium session with multiple requests")
    else:
        insights.append(f"Extended session with {req_count} requests")

    # Complexity insight
    if max_c >= 20:
        insights.append(f"High complexity work (max {max_c}/25) - Opus-level tasks")
    elif max_c >= 10:
        insights.append(f"Moderate complexity work (max {max_c}/25) - Sonnet-level tasks")
    elif max_c > 0:
        insights.append(f"Low complexity work (max {max_c}/25) - Quick tasks")

    # Tool usage insight
    total_tools = sum(tool_counts.values()) if tool_counts else 0
    if total_tools > 50:
        insights.append(f"Heavy tool usage ({total_tools} calls) - significant coding session")
    elif total_tools > 20:
        insights.append(f"Moderate tool usage ({total_tools} calls)")

    # Read vs Write ratio
    reads = tool_counts.get('Read', 0) + tool_counts.get('Grep', 0) + tool_counts.get('Glob', 0)
    writes = tool_counts.get('Write', 0) + tool_counts.get('Edit', 0)
    if reads > 0 and writes > 0:
        if reads > writes * 3:
            insights.append("Research-heavy session (more reading than writing)")
        elif writes > reads:
            insights.append("Implementation-heavy session (more writing than reading)")

    # File modification insight
    if len(files_modified) > 10:
        insights.append(f"Large scope change ({len(files_modified)} files modified)")
    elif len(files_modified) > 0:
        insights.append(f"Targeted changes ({len(files_modified)} files modified)")

    # Error insight
    if error_count > 0:
        error_rate = round((error_count / total_tools) * 100, 1) if total_tools > 0 else 0
        if error_rate > 20:
            insights.append(f"High error rate ({error_rate}%) - debugging session likely")
        else:
            insights.append(f"{error_count} error(s) encountered ({error_rate}% rate)")

    # Context usage insight
    if peak_ctx > 80:
        insights.append(f"Near context limit (peak {peak_ctx}%) - cleanup may be needed")
    elif peak_ctx > 50:
        insights.append(f"Moderate context usage (peak {peak_ctx}%)")

    # Duration insight
    if duration_seconds > 3600:
        hours = duration_seconds // 3600
        insights.append(f"Long session ({hours}+ hours of work)")
    elif duration_seconds > 1800:
        insights.append("Extended session (30+ minutes)")

    # Plan mode insight
    if plan_mode_count > 0:
        insights.append(f"Used plan mode {plan_mode_count} time(s) - structured approach")

    # Multi-type insight
    if len(types) > 2:
        insights.append(f"Multi-faceted session ({', '.join(types[:4])})")

    return insights


def _update_chain_summary(session_id, data):
    """Update the session's 'summary' field in chain-index.json after finalization.

    Reads the chain index, sets the one-liner summary for session_id (if it
    exists in the index), and writes back with an updated 'last_updated'
    timestamp.  Uses _lock_file/_unlock_file for Windows file locking.

    Args:
        session_id (str): Session identifier to update in the chain index.
        data (dict): Finalised summary dict used to generate the one-liner.
    """
    chain_index_file = SESSIONS_DIR / 'chain-index.json'
    if not chain_index_file.exists():
        return

    try:
        with open(chain_index_file, 'r', encoding='utf-8') as f:
            _lock_file(f)
            chain = json.load(f)
            _unlock_file(f)

        if session_id in chain.get("sessions", {}):
            chain["sessions"][session_id]["summary"] = _generate_one_liner(data)
            chain["last_updated"] = datetime.now().isoformat()

            with open(chain_index_file, 'w', encoding='utf-8') as f:
                _lock_file(f)
                json.dump(chain, f, indent=2)
                _unlock_file(f)
            log_event(f"[OK] Chain index updated with summary for {session_id}")
    except Exception as e:
        log_event(f"[WARN] Could not update chain index: {e}")


# =============================================================================
# READ - Get summary for a session
# =============================================================================

def read_summary(session_id, fmt='md'):
    """Read the session summary in the requested output format.

    Args:
        session_id (str): Session identifier to read.
        fmt (str): Output format - one of 'md' (Markdown file content),
                   'json' (structured dict), or 'text' (one-liner string).
                   Defaults to 'md'.

    Returns:
        str, dict, or None: Content in the requested format, or None when no
                            summary is available for the session.
    """
    if fmt == 'text':
        json_path = summary_json_path(session_id)
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    _lock_file(f)
                    data = json.load(f)
                    _unlock_file(f)
                return data.get("summary_text") or _generate_one_liner(data)
            except Exception:
                pass
        return None

    elif fmt == 'json':
        json_path = summary_json_path(session_id)
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    _lock_file(f)
                    data = json.load(f)
                    _unlock_file(f)
                return data
            except Exception:
                pass
        return None

    else:  # md
        md_path = summary_md_path(session_id)
        if md_path.exists():
            try:
                return md_path.read_text(encoding='utf-8')
            except Exception:
                pass
        json_path = summary_json_path(session_id)
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    _lock_file(f)
                    data = json.load(f)
                    _unlock_file(f)
                return _generate_markdown(data)
            except Exception:
                pass
        return None


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for session-summary-manager.py.

    Dispatches to one of the following sub-commands:
      accumulate - Add a per-request entry to the session summary (called by
                   3-level-flow.py after every user message).
      finalize   - Generate comprehensive session-summary.md + JSON on session
                   close (called by clear-session-handler.py on /clear).
      read       - Print the session summary in md, json, or text format.

    Exits 0 on success or 1 on any error.
    """
    parser = argparse.ArgumentParser(description='Session Summary Manager v2.1.0')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # accumulate (v2.0.0: added new args)
    acc = subparsers.add_parser('accumulate', help='Accumulate request data')
    acc.add_argument('--session', required=True, help='Session ID')
    acc.add_argument('--prompt', default='', help='User prompt')
    acc.add_argument('--task-type', default='', help='Task type')
    acc.add_argument('--skill', default='', help='Skill/agent name')
    acc.add_argument('--complexity', default=0, type=int, help='Complexity score')
    acc.add_argument('--model', default='', help='Model selected')
    acc.add_argument('--cwd', default='', help='Working directory')
    # v2.0.0 new args
    acc.add_argument('--plan-mode', default='false', help='Whether plan mode was used')
    acc.add_argument('--context-pct', default=0, type=int, help='Context usage percentage')
    acc.add_argument('--supplementary-skills', default='', help='Comma-separated supplementary skills')
    acc.add_argument('--standards-count', default=0, type=int, help='Number of active standards')
    acc.add_argument('--rules-count', default=0, type=int, help='Number of active rules')

    # finalize
    fin = subparsers.add_parser('finalize', help='Generate final comprehensive summary on close')
    fin.add_argument('--session', required=True, help='Session ID')

    # read
    rd = subparsers.add_parser('read', help='Read session summary')
    rd.add_argument('--session', required=True, help='Session ID')
    rd.add_argument('--format', default='md', choices=['md', 'json', 'text'],
                    help='Output format')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == 'accumulate':
        ok = accumulate(
            args.session,
            prompt=args.prompt,
            task_type=args.task_type,
            skill=args.skill,
            complexity=args.complexity,
            model=args.model,
            cwd=args.cwd,
            plan_mode=args.plan_mode,
            context_pct=args.context_pct,
            supplementary_skills=args.supplementary_skills,
            standards_count=args.standards_count,
            rules_count=args.rules_count,
        )
        if ok:
            print(f"[OK] Accumulated for {args.session}")
        else:
            print(f"[ERROR] Failed to accumulate")
            sys.exit(1)

    elif args.command == 'finalize':
        ok = finalize(args.session)
        if ok:
            print(f"[OK] Comprehensive summary finalized for {args.session}")
        else:
            print(f"[ERROR] Failed to finalize summary")
            sys.exit(1)

    elif args.command == 'read':
        result = read_summary(args.session, fmt=args.format)
        if result:
            if isinstance(result, dict):
                print(json.dumps(result, indent=2))
            else:
                print(result)
        else:
            print(f"[INFO] No summary found for {args.session}")

    sys.exit(0)


if __name__ == '__main__':
    main()
