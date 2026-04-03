"""GitHub issue lifecycle management.

Provides create_github_issue(), close_github_issue(), _build_close_comment(),
and extract_task_id_from_response() plus private helpers used exclusively by
issue creation/closing logic.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .client import GH_TIMEOUT, MAX_OPS_PER_SESSION, is_gh_available
from .labels import _build_issue_labels, _detect_issue_type, _ensure_labels_exist
from .session_integration import (
    _get_ops_count,
    _get_session_id,
    _increment_ops_count,
    _load_issues_mapping,
    _save_issues_mapping,
)

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import SESSION_STATE_FILE
except ImportError:
    SESSION_STATE_FILE = Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_repo_root():
    """Return the absolute path to the git repository root from the current directory.

    Runs ``git rev-parse --show-toplevel`` with a 5-second timeout.

    Returns:
        str or None: Absolute repo root path, or None if not inside a git
            repository or the command fails.
    """
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_flow_trace_context():
    """Load the current session's flow-trace.json for execution context fields.

    Reads the trace file for the active session and extracts key planning
    metadata: task_type, complexity, model, skill/agent, context_pct, and
    plan_mode.

    Returns:
        dict: Mapping of extracted fields (task_type, complexity, model, skill,
            context_pct, plan_mode), or an empty dict if the session ID is
            unavailable, the file is missing, or parsing fails.
    """
    session_id = _get_session_id()
    if not session_id:
        return {}
    trace_file = Path.home() / ".claude" / "memory" / "logs" / "sessions" / session_id / "flow-trace.json"
    try:
        if trace_file.exists():
            with open(trace_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # v4.4.0+: array of traces - use latest entry
            if isinstance(raw, list) and raw:
                data = raw[-1]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
            return {
                "task_type": data.get("task_type", ""),
                "complexity": data.get("complexity", 0),
                "model": data.get("model", ""),
                "skill": data.get("skill", ""),
                "context_pct": data.get("context_pct", 0),
                "plan_mode": data.get("plan_mode", False),
            }
    except Exception:
        pass
    return {}


def _get_session_progress_context():
    """Load session-progress.json for tool counts, completed tasks, and modified files.

    Returns:
        dict: Mapping with keys tool_counts, tasks_completed, total_progress,
            modified_files, errors_seen, started_at, and context_estimate_pct,
            or an empty dict if the file is missing or unreadable.
    """
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "tool_counts": data.get("tool_counts", {}),
                "tasks_completed": data.get("tasks_completed", 0),
                "total_progress": data.get("total_progress", 0),
                "modified_files": data.get("modified_files_since_commit", []),
                "errors_seen": data.get("errors_seen", 0),
                "started_at": data.get("started_at", ""),
                "context_estimate_pct": data.get("context_estimate_pct", 0),
            }
    except Exception:
        pass
    return {}


def _get_tool_activity_for_task(task_id):
    """Scan tool-tracker.jsonl for tool activity belonging to a specific task.

    Locates the Nth TaskCreate event corresponding to task_id, then records
    all subsequent tool calls until a TaskUpdate(completed) event for that
    task is found.

    Args:
        task_id: Task ID string or int (e.g. '1') used to locate the
            TaskCreate event by ordinal position.

    Returns:
        dict: Keys files_read, files_written, files_edited (lists of file
            paths), commands_run and searches (lists of strings), edits
            (list of edit-description strings), and total_tools (int).
            All lists are empty and total_tools is 0 if the log is missing
            or no matching activity is found.
    """
    tracker_log = Path.home() / ".claude" / "memory" / "logs" / "tool-tracker.jsonl"
    result = {
        "files_read": [],
        "files_written": [],
        "files_edited": [],
        "commands_run": [],
        "searches": [],
        "edits": [],
        "total_tools": 0,
    }
    try:
        if not tracker_log.exists():
            return result

        # Read all entries, find the activity window for THIS specific task
        # Strategy: Find the TaskCreate that matches task_id, record until its TaskUpdate(completed)
        recording = False
        task_id_str = str(task_id)
        with open(tracker_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                tool = entry.get("tool", "")

                # Start recording only when we see a TaskCreate followed by
                # a TaskUpdate for THIS task_id (or the Nth TaskCreate matching task_id order)
                if not recording and tool == "TaskCreate":
                    # Match by checking if this is the Nth task (task_id = "1" means 1st TaskCreate)
                    # We track a counter to find the right TaskCreate
                    if not hasattr(result, "_tc_count"):
                        result["_tc_count"] = 0
                    result["_tc_count"] = result.get("_tc_count", 0) + 1
                    if str(result.get("_tc_count", 0)) == task_id_str:
                        recording = True
                        result = {
                            "files_read": [],
                            "files_written": [],
                            "files_edited": [],
                            "commands_run": [],
                            "searches": [],
                            "edits": [],
                            "total_tools": 0,
                            "_tc_count": result.get("_tc_count", 0),
                        }
                    continue

                # Stop recording when this task is marked completed
                if tool == "TaskUpdate" and entry.get("task_id") == task_id_str:
                    if entry.get("task_status") == "completed":
                        break

                if not recording:
                    continue

                result["total_tools"] += 1
                file_path = entry.get("file", "")

                if tool == "Read" and file_path:
                    if file_path not in result["files_read"]:
                        result["files_read"].append(file_path)
                elif tool == "Write" and file_path:
                    if file_path not in result["files_written"]:
                        result["files_written"].append(file_path)
                    lines = entry.get("content_lines", 0)
                    if lines:
                        result["edits"].append(file_path + " (" + str(lines) + " lines written)")
                elif tool == "Edit" and file_path:
                    if file_path not in result["files_edited"]:
                        result["files_edited"].append(file_path)
                    old_hint = entry.get("old_hint", "")
                    new_hint = entry.get("new_hint", "")
                    edit_size = entry.get("edit_size", 0)
                    if old_hint or new_hint:
                        edit_desc = file_path
                        if edit_size:
                            edit_desc += " (" + ("+" if edit_size > 0 else "") + str(edit_size) + " chars)"
                        result["edits"].append(edit_desc)
                elif tool == "Bash":
                    cmd = entry.get("command", "")
                    desc = entry.get("desc", "")
                    if cmd:
                        result["commands_run"].append(desc or cmd[:100])
                elif tool in ("Grep", "Glob"):
                    pattern = entry.get("pattern", "")
                    if pattern:
                        result["searches"].append(tool + ": " + pattern)

    except Exception:
        pass
    return result


def _slugify(text, max_len=40):
    """Convert text to a URL- and branch-safe slug.

    Lowercases the input, replaces spaces, hyphens, underscores, and
    forward slashes with a single hyphen, strips non-alphanumeric
    characters, and truncates at a word boundary up to max_len.

    Args:
        text (str): Input text to convert.
        max_len (int): Maximum length of the returned slug. Defaults to 40.

    Returns:
        str: Lowercase hyphen-separated slug with no leading or trailing
            hyphens and length <= max_len.
    """
    slug = ""
    for ch in text.lower():
        if ch.isalnum():
            slug += ch
        elif ch in (" ", "-", "_", "/"):
            if slug and slug[-1] != "-":
                slug += "-"
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate at max_len, but don't cut mid-word if possible
    if len(slug) > max_len:
        cut = slug[:max_len]
        last_hyphen = cut.rfind("-")
        if last_hyphen > max_len // 2:
            slug = cut[:last_hyphen]
        else:
            slug = cut
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_task_id_from_response(tool_response):
    """Parse the task ID from a TaskCreate tool response.

    Handles multiple response formats:

    - ``"Task #1 created successfully: ..."``
    - ``"Task created with id 1"``
    - ``"Created task 1: ..."``
    - ``{"id": "1", ...}`` or ``{"taskId": "1", ...}``
    - Any string containing digits after task-related keywords

    Args:
        tool_response (str or dict): Raw response from a TaskCreate tool call.
            Can be a plain string, a dict with an ``id``/``taskId`` field, or
            a dict with a ``content`` field (str or list of dicts).

    Returns:
        str: The extracted task ID (e.g. ``'1'``), or an empty string if no
            numeric ID can be found.
    """
    try:
        content = ""
        if isinstance(tool_response, dict):
            # Check for direct 'id' field in response
            direct_id = tool_response.get("id", "")
            if direct_id:
                return str(direct_id)
            # Check for taskId field
            direct_tid = tool_response.get("taskId", "")
            if direct_tid:
                return str(direct_tid)

            c = tool_response.get("content", "")
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                for item in c:
                    if isinstance(item, dict):
                        content += item.get("text", "")
                    elif isinstance(item, str):
                        content += item
        elif isinstance(tool_response, str):
            content = tool_response

        if not content:
            return ""

        # Pattern 1: "Task #N" (e.g. "Task #1 created successfully")
        if "Task #" in content:
            after_hash = content.split("Task #", 1)[1]
            task_id = ""
            for ch in after_hash:
                if ch.isdigit():
                    task_id += ch
                else:
                    break
            if task_id:
                return task_id

        # Pattern 2: "id N" or "id: N" or "ID: N"
        content_lower = content.lower()
        for marker in ["id ", "id: ", "id:", "task "]:
            idx = content_lower.find(marker)
            if idx >= 0:
                after = content[idx + len(marker) :].strip()
                task_id = ""
                for ch in after:
                    if ch.isdigit():
                        task_id += ch
                    elif task_id:
                        break
                if task_id:
                    return task_id

        # Pattern 3: First standalone number in the content
        match = re.search(r"\b(\d+)\b", content)
        if match:
            return match.group(1)

    except Exception:
        pass
    return ""


def _build_close_comment(task_id, issue_data):
    """Build a comprehensive Markdown closing comment for a GitHub issue.

    The comment includes a resolution story (narrative derived from issue type),
    files changed and investigated, commands executed, RCA section for bugfix
    issues, tool usage breakdown, duration from creation to now, and session
    context metrics.

    Args:
        task_id: Task ID string or int used to retrieve tool activity via
            _get_tool_activity_for_task.
        issue_data (dict): Persisted issue metadata dict with keys title,
            issue_type, and created_at (ISO datetime string).

    Returns:
        str: Formatted Markdown comment body ready to post to GitHub.
    """
    lines = []

    task_title = issue_data.get("title", "Task " + str(task_id))
    issue_type = issue_data.get("issue_type", _detect_issue_type(task_title))
    created_at = issue_data.get("created_at", "")
    closed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Calculate duration
    duration_str = ""
    if created_at:
        try:
            start = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S")
            end = datetime.strptime(closed_at, "%Y-%m-%dT%H:%M:%S")
            delta = end - start
            total_secs = int(delta.total_seconds())
            if total_secs >= 3600:
                hours = total_secs // 3600
                mins = (total_secs % 3600) // 60
                duration_str = str(hours) + "h " + str(mins) + "m"
            elif total_secs >= 60:
                mins = total_secs // 60
                secs = total_secs % 60
                duration_str = str(mins) + "m " + str(secs) + "s"
            else:
                duration_str = str(total_secs) + "s"
        except Exception:
            pass

    # Get tool activity for this task
    activity = _get_tool_activity_for_task(task_id)
    all_changed_files = list(set(activity.get("files_written", []) + activity.get("files_edited", [])))
    files_read = activity.get("files_read", [])
    edits = activity.get("edits", [])
    commands = activity.get("commands_run", [])
    searches = activity.get("searches", [])
    total_tools = activity.get("total_tools", 0)

    # Section 1: Resolution Story (comprehensive narrative)
    lines.append("## Resolution Story")
    lines.append("")

    # Build a narrative based on issue type and actual work done
    if issue_type == "fix":
        lines.append("This bug has been investigated, root-caused, and fixed.")
        if files_read:
            lines.append(
                "The investigation involved reading "
                + str(len(files_read))
                + " file(s) to understand the problem context and trace the root cause."
            )
        if all_changed_files:
            lines.append("The fix was applied across " + str(len(all_changed_files)) + " file(s) to resolve the issue.")
        if commands:
            lines.append(
                "Verification was performed using "
                + str(len(commands))
                + " command(s) to confirm the fix works correctly."
            )
    elif issue_type == "refactor":
        lines.append("The code has been restructured to improve maintainability and design.")
        if files_read:
            lines.append(
                "First, " + str(len(files_read)) + " file(s) were analyzed to understand the existing code structure."
            )
        if all_changed_files:
            lines.append(
                "The refactoring touched "
                + str(len(all_changed_files))
                + " file(s) while preserving all existing functionality."
            )
    elif issue_type == "docs":
        lines.append("Documentation has been created or updated to reflect the current state.")
        if all_changed_files:
            lines.append(str(len(all_changed_files)) + " documentation file(s) were updated.")
    elif issue_type == "feature":
        lines.append("The new feature has been fully implemented and is ready for use.")
        if files_read:
            lines.append(
                "Research phase: "
                + str(len(files_read))
                + " existing file(s) were studied to understand patterns and conventions."
            )
        if all_changed_files:
            lines.append("Implementation phase: " + str(len(all_changed_files)) + " file(s) were created or modified.")
        if commands:
            lines.append(
                "Validation phase: " + str(len(commands)) + " command(s) were executed to verify the implementation."
            )
    elif issue_type == "enhancement":
        lines.append("The existing feature has been enhanced as requested.")
        if all_changed_files:
            lines.append(str(len(all_changed_files)) + " file(s) were updated to deliver the enhancement.")
    else:
        lines.append("This task has been completed successfully.")
        if all_changed_files:
            lines.append(str(len(all_changed_files)) + " file(s) were modified.")
    lines.append("")

    # Duration info
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append("| **Status** | Completed |")
    if duration_str:
        lines.append("| **Duration** | " + duration_str + " |")
    lines.append("| **Closed At** | " + closed_at + " |")
    lines.append("")

    # Section 2: Files Changed
    if all_changed_files:
        lines.append("## Files Changed")
        lines.append("")
        for f in all_changed_files[:20]:
            lines.append("- `" + f + "`")
        lines.append("")

    # Section 3: Detailed Edits
    if edits:
        lines.append("## Changes Made")
        lines.append("")
        for edit in edits[:15]:
            lines.append("- " + edit)
        lines.append("")

    # Section 4: Files Investigated
    if files_read:
        lines.append("## Files Investigated")
        lines.append("")
        for f in files_read[:15]:
            lines.append("- `" + f + "`")
        lines.append("")

    # Section 5: Commands Executed
    if commands:
        lines.append("## Commands Executed")
        lines.append("")
        for cmd in commands[:10]:
            lines.append("- `" + cmd + "`")
        lines.append("")

    # Section 6: Searches Performed
    if searches:
        lines.append("## Searches Performed")
        lines.append("")
        for s in searches[:10]:
            lines.append("- " + s)
        lines.append("")

    # Section 7: RCA (Root Cause Analysis) - only for bugfix issues
    if issue_type == "fix":
        lines.append("## Root Cause Analysis (RCA)")
        lines.append("")
        if files_read:
            lines.append("**Investigation:** " + str(len(files_read)) + " files investigated")
        if all_changed_files:
            lines.append("**Root Cause Location:** " + ", ".join(["`" + f + "`" for f in all_changed_files[:5]]))
        if edits:
            lines.append("**Fix Applied:** " + str(len(edits)) + " edit(s) made")
            for edit in edits[:5]:
                lines.append("  - " + edit)
        if commands:
            lines.append("**Verification:** " + str(len(commands)) + " command(s) run to verify fix")
        lines.append("")

    # Section 8: Tool Usage Summary
    if total_tools > 0:
        lines.append("## Tool Usage")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append("| Total Tool Calls | " + str(total_tools) + " |")
        if files_read:
            lines.append("| Files Read | " + str(len(files_read)) + " |")
        if all_changed_files:
            lines.append("| Files Changed | " + str(len(all_changed_files)) + " |")
        if commands:
            lines.append("| Commands Run | " + str(len(commands)) + " |")
        if searches:
            lines.append("| Searches | " + str(len(searches)) + " |")
        lines.append("")

    # Section 9: Session Context
    progress_ctx = _get_session_progress_context()
    flow_ctx = _get_flow_trace_context()

    if progress_ctx or flow_ctx:
        lines.append("## Session Context")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        session_id = _get_session_id()
        if session_id:
            lines.append("| Session | `" + session_id + "` |")
        if flow_ctx.get("complexity"):
            lines.append("| Complexity | " + str(flow_ctx["complexity"]) + "/25 |")
        if flow_ctx.get("model"):
            lines.append("| Model | " + flow_ctx["model"] + " |")
        if flow_ctx.get("skill"):
            lines.append("| Skill/Agent | " + flow_ctx["skill"] + " |")
        if progress_ctx.get("tasks_completed"):
            lines.append("| Tasks Completed | " + str(progress_ctx["tasks_completed"]) + " |")
        if progress_ctx.get("context_estimate_pct"):
            lines.append("| Context Usage | " + str(progress_ctx["context_estimate_pct"]) + "% |")
        if progress_ctx.get("errors_seen"):
            lines.append("| Errors Encountered | " + str(progress_ctx["errors_seen"]) + " |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("_Auto-closed by Claude Memory System (Level 3 Execution) | v3.0.0_")

    return "\n".join(lines)


def create_github_issue(task_id, subject, description):
    """Create a comprehensive GitHub issue for a task.

    Includes: full description, acceptance criteria, session context,
    execution environment info, complexity analysis, and related metadata.

    Args:
        task_id: Task ID string (e.g. '1')
        subject: Task subject line
        description: Task description

    Returns:
        Issue number (int) on success, None on failure.
    """
    # Import branch manager here to avoid circular import at module level
    from .branch_manager import create_issue_branch

    def _debug_log_gh(msg):
        """Log to github-issue-debug.log with [GH-CREATE] prefix"""
        try:
            log_path = Path.home() / ".claude" / "memory" / "logs" / "github-issue-debug.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                ts = datetime.now().isoformat()
                f.write("[" + ts + "] " + msg + "\n")
        except Exception:
            pass

    try:
        _debug_log_gh("[GH-CREATE] START: task_id=" + str(task_id) + ", subject='" + str(subject)[:50] + "'")

        _debug_log_gh("[GH-CREATE] Checking if gh is available...")
        if not is_gh_available():
            _debug_log_gh("[GH-CREATE] [FAIL] gh not available, returning None")
            return None
        _debug_log_gh("[GH-CREATE] [PASS] gh is available")

        _debug_log_gh("[GH-CREATE] Checking ops count (MAX=" + str(MAX_OPS_PER_SESSION) + ")...")
        ops_count = _get_ops_count()
        _debug_log_gh("[GH-CREATE] ops_count=" + str(ops_count))
        if ops_count >= MAX_OPS_PER_SESSION:
            _debug_log_gh("[GH-CREATE] [FAIL] ops_count >= MAX, returning None")
            return None

        _debug_log_gh("[GH-CREATE] Getting repo root...")
        repo_root = _get_repo_root()
        _debug_log_gh("[GH-CREATE] repo_root=" + str(repo_root))
        if not repo_root:
            _debug_log_gh("[GH-CREATE] [FAIL] no repo_root, returning None")
            return None

        # Build issue title and body
        # CHANGED v3.0: Use semantic title format (no [TASK-X] prefix)
        # Format: {type}: {subject}
        # Example: bugfix: Model selection defaulting to HAIKU
        _debug_log_gh("[GH-CREATE] Detecting issue type...")
        issue_type_label = _detect_issue_type(subject, description)
        _debug_log_gh("[GH-CREATE] issue_type_label=" + issue_type_label)
        title = issue_type_label + ": " + subject
        # Truncate title to 256 chars (GitHub limit is higher but keep it readable)
        title = title[:256]
        _debug_log_gh("[GH-CREATE] title=" + repr(title[:60]))

        _debug_log_gh("[GH-CREATE] Getting session context...")
        session_id = _get_session_id()
        _debug_log_gh("[GH-CREATE] session_id=" + str(session_id))
        flow_ctx = _get_flow_trace_context()
        _debug_log_gh("[GH-CREATE] flow_ctx keys=" + str(list(flow_ctx.keys())))
        progress_ctx = _get_session_progress_context()
        _debug_log_gh("[GH-CREATE] progress_ctx keys=" + str(list(progress_ctx.keys())))

        # --- Build comprehensive issue body with story format ---
        body_lines = []
        issue_type = _detect_issue_type(subject, description)
        complexity = flow_ctx.get("complexity", 0)

        # CHANGED v3.0: Problem-centric body format (not task-centric)
        # Section 1: Problem Statement
        body_lines.append("## Problem Statement")
        body_lines.append("")
        body_lines.append(description if description else subject)
        body_lines.append("")

        # Section 1b: Context & Background
        body_lines.append("## Context & Background")
        body_lines.append("")
        body_lines.append("Related to: " + issue_type.capitalize() + " | Complexity: " + str(complexity) + "/25")
        body_lines.append("")

        # Section 2: Task Overview (metadata table)
        body_lines.append("## Task Overview")
        body_lines.append("")
        body_lines.append("| Field | Value |")
        body_lines.append("|-------|-------|")
        body_lines.append("| **Task ID** | " + str(task_id) + " |")
        body_lines.append("| **Subject** | " + subject + " |")
        body_lines.append("| **Type** | " + issue_type + " |")
        if complexity:
            body_lines.append("| **Complexity** | " + str(complexity) + "/25 |")
            # Priority derivation
            if complexity >= 15:
                priority = "Critical"
            elif complexity >= 10:
                priority = "High"
            elif complexity >= 5:
                priority = "Medium"
            else:
                priority = "Low"
            body_lines.append("| **Priority** | " + priority + " |")
        if flow_ctx.get("model"):
            body_lines.append("| **Model** | " + flow_ctx["model"] + " |")
        if flow_ctx.get("skill"):
            body_lines.append("| **Skill/Agent** | " + flow_ctx["skill"] + " |")
        if flow_ctx.get("plan_mode"):
            body_lines.append("| **Plan Mode** | Required |")
        body_lines.append("")

        # Section 3: Acceptance Criteria
        body_lines.append("## Acceptance Criteria")
        body_lines.append("")
        if description:
            criteria_found = False
            for line in description.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    body_lines.append("- [ ] " + line[2:])
                    criteria_found = True
                elif line and len(line) > 15:
                    body_lines.append("- [ ] " + line)
                    criteria_found = True
            if not criteria_found:
                body_lines.append("- [ ] " + subject)
        else:
            body_lines.append("- [ ] " + subject)
        # Add standard criteria based on type
        if issue_type == "fix":
            body_lines.append("- [ ] Root cause identified and documented")
            body_lines.append("- [ ] Fix verified - bug no longer reproducible")
        elif issue_type == "feature":
            body_lines.append("- [ ] Feature implemented and functional")
            body_lines.append("- [ ] Code follows existing patterns and conventions")
        elif issue_type == "refactor":
            body_lines.append("- [ ] No behavior changes - all existing functionality preserved")
            body_lines.append("- [ ] Code quality improved")
        body_lines.append("- [ ] Changes committed and pushed")
        body_lines.append("")

        # Section 4: Session Context
        body_lines.append("## Session Context")
        body_lines.append("")
        body_lines.append("| Field | Value |")
        body_lines.append("|-------|-------|")
        if session_id:
            body_lines.append("| **Session ID** | `" + session_id + "` |")
        body_lines.append("| **Created At** | " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " |")
        if progress_ctx.get("started_at"):
            body_lines.append("| **Session Started** | " + progress_ctx["started_at"] + " |")
        if progress_ctx.get("context_estimate_pct"):
            body_lines.append("| **Context Usage** | " + str(progress_ctx["context_estimate_pct"]) + "% |")
        if progress_ctx.get("tasks_completed"):
            body_lines.append("| **Tasks Completed So Far** | " + str(progress_ctx["tasks_completed"]) + " |")
        if progress_ctx.get("total_progress"):
            body_lines.append("| **Session Progress** | " + str(progress_ctx["total_progress"]) + "% |")

        # Get current branch
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, cwd=repo_root
            )
            if branch_result.returncode == 0:
                body_lines.append("| **Branch** | `" + branch_result.stdout.strip() + "` |")
        except Exception:
            pass

        # Get repo name
        try:
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5, cwd=repo_root
            )
            if remote_result.returncode == 0:
                remote_url = remote_result.stdout.strip()
                repo_name = remote_url.rsplit("/", 1)[-1].replace(".git", "")
                body_lines.append("| **Repository** | " + repo_name + " |")
        except Exception:
            pass

        body_lines.append("")

        # Section 5: Related files (if any modified files tracked)
        if progress_ctx.get("modified_files"):
            body_lines.append("## Files Modified (Before This Task)")
            body_lines.append("")
            for f in progress_ctx["modified_files"][:15]:
                body_lines.append("- `" + f + "`")
            body_lines.append("")

        # Footer
        body_lines.append("---")
        body_lines.append("")
        body_lines.append("_Auto-created by Claude Memory System (Level 3 Execution) | v3.0.0_")

        body = "\n".join(body_lines)

        # Build labels using the comprehensive label system
        issue_type = _detect_issue_type(subject, description)
        complexity = flow_ctx.get("complexity", 0)
        labels = _build_issue_labels(issue_type, complexity, subject, description)

        # Auto-create any missing labels in the repo
        _ensure_labels_exist(labels, repo_root)

        # Create issue via gh CLI with labels
        _debug_log_gh("[GH-CREATE] Building gh CLI command...")
        cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
        ]
        cmd_with_labels = cmd + ["--label", ",".join(labels)]
        _debug_log_gh(
            "[GH-CREATE] Command with labels: gh issue create --title ... --body ... --label " + ",".join(labels)
        )

        _debug_log_gh("[GH-CREATE] Running gh command (timeout=" + str(GH_TIMEOUT) + "s)...")
        try:
            result = subprocess.run(cmd_with_labels, capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=repo_root)
            _debug_log_gh("[GH-CREATE] gh returned: returncode=" + str(result.returncode))
            if result.stdout:
                _debug_log_gh("[GH-CREATE] stdout: " + result.stdout[:200])
            if result.stderr:
                _debug_log_gh("[GH-CREATE] stderr: " + result.stderr[:200])
        except subprocess.TimeoutExpired:
            _debug_log_gh("[GH-CREATE] [FAIL] gh command TIMEOUT after " + str(GH_TIMEOUT) + "s")
            raise
        except Exception as e:
            _debug_log_gh("[GH-CREATE] [FAIL] gh command EXCEPTION: " + type(e).__name__ + ": " + str(e)[:150])
            raise

        # If label creation still failed, retry without labels
        if result.returncode != 0 and "label" in result.stderr.lower():
            _debug_log_gh("[GH-CREATE] Label error detected, retrying without labels...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=repo_root)
            _debug_log_gh("[GH-CREATE] Retry returned: returncode=" + str(result.returncode))

        if result.returncode == 0 and result.stdout.strip():
            _debug_log_gh("[GH-CREATE] [PASS] gh command succeeded")
            # stdout contains the issue URL, e.g. https://github.com/user/repo/issues/42
            issue_url = result.stdout.strip()
            issue_number = None
            if "/issues/" in issue_url:
                num_str = issue_url.rsplit("/issues/", 1)[1].strip()
                if num_str.isdigit():
                    issue_number = int(num_str)

            # Save mapping (include issue_type for branch naming)
            mapping = _load_issues_mapping()
            task_key = str(task_id) if task_id else "unknown"
            mapping["task_to_issue"][task_key] = {
                "issue_number": issue_number,
                "issue_url": issue_url,
                "title": title,
                "issue_type": issue_type,
                "labels": labels,
                "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "status": "open",
            }
            # Increment per-session ops_count (not global) and save
            mapping = _increment_ops_count(mapping)
            _save_issues_mapping(mapping)

            # ATOMIC: Create branch immediately after issue creation.
            # This ensures the chain Issue -> Branch -> Work -> PR -> Merge
            # never breaks. Branch is created in the same call as the issue.
            _debug_log_gh("[GH-CREATE] Branch creation block: issue_number=" + str(issue_number))
            if issue_number:
                _debug_log_gh("[GH-CREATE] [PASS] issue_number exists, checking for THIS issue branch...")
                # Each issue gets its own branch: {issue_type}/{issue_number}
                issue_specific_branch = issue_type + "/" + str(issue_number)
                _debug_log_gh("[GH-CREATE] expected_branch_name=" + issue_specific_branch)
                # Note: We always create a new branch for each issue (don't check for existing)
                # because each issue should have its own dedicated branch
                _debug_log_gh("[GH-CREATE] Creating branch for this issue (" + issue_specific_branch + ")...")
                branch = create_issue_branch(issue_number, subject, issue_type)
                _debug_log_gh("[GH-CREATE] create_issue_branch() returned: " + str(branch))
                if branch:
                    _debug_log_gh("[GH-CREATE] [PASS] Branch created successfully: " + branch)
                    try:
                        sys.stdout.write(
                            "[GH] Branch: " + branch + " (auto-created with issue #" + str(issue_number) + ")\n"
                        )
                        sys.stdout.flush()
                    except Exception as e:
                        _debug_log_gh("[GH-CREATE] Could not write stdout: " + str(e)[:100])
                else:
                    _debug_log_gh("[GH-CREATE] [FAIL] Branch creation returned None")
            else:
                _debug_log_gh("[GH-CREATE] [FAIL] issue_number is falsy, skipping branch creation")

            _debug_log_gh("[GH-CREATE] [PASS] RETURNING issue_number=" + str(issue_number))
            return issue_number
        else:
            _debug_log_gh(
                "[GH-CREATE] [FAIL] gh command failed: returncode="
                + str(result.returncode)
                + ", stdout='"
                + result.stdout[:100]
                + "'"
            )
            return None

    except subprocess.TimeoutExpired as e:
        try:
            _debug_log_gh("[GH-CREATE] [FAIL] TIMEOUT EXCEPTION: " + str(e)[:150])
        except Exception:
            pass
        return None
    except Exception as e:
        try:
            import traceback

            _debug_log_gh("[GH-CREATE] [FAIL] EXCEPTION: " + type(e).__name__ + ": " + str(e)[:200])
            _debug_log_gh("[GH-CREATE] Traceback: " + traceback.format_exc()[:500])
        except Exception:
            pass
        return None


def close_github_issue(task_id):
    """Close the GitHub issue associated with a task with a comprehensive summary comment.

    The closing comment includes:
      - What was done (files changed, edits made)
      - RCA analysis (if bugfix type)
      - Tool usage breakdown
      - Duration, session context, commands run

    Args:
        task_id: Task ID string (e.g. '1')

    Returns:
        True if closed successfully, False otherwise.
    """
    try:
        if not is_gh_available():
            return False

        if _get_ops_count() >= MAX_OPS_PER_SESSION:
            return False

        repo_root = _get_repo_root()
        if not repo_root:
            return False

        # Look up issue number from mapping
        mapping = _load_issues_mapping()
        task_key = str(task_id)
        issue_data = mapping.get("task_to_issue", {}).get(task_key)

        # Fallback 1: if exact key not found, try 'unknown' key
        if not issue_data:
            issue_data = mapping.get("task_to_issue", {}).get("unknown")
            if issue_data and issue_data.get("status") == "open":
                mapping["task_to_issue"][task_key] = issue_data
                if "unknown" in mapping.get("task_to_issue", {}):
                    del mapping["task_to_issue"]["unknown"]
                _save_issues_mapping(mapping)

        # Fallback 2: Find the most recently created OPEN issue in THIS session's mapping.
        # This is SAFE because each session has its own mapping file (no cross-session risk).
        # Needed because Claude's task IDs can mismatch between TaskCreate response
        # (e.g. "Task #1") and TaskUpdate input (e.g. taskId="3") after /clear.
        if not issue_data:
            latest_open = None
            latest_time = ""
            for key, data in mapping.get("task_to_issue", {}).items():
                if data.get("status") == "open":
                    created = data.get("created_at", "")
                    if created >= latest_time:
                        latest_time = created
                        latest_open = data
                        task_key = key
            if latest_open:
                issue_data = latest_open

        if not issue_data:
            return False

        issue_number = issue_data.get("issue_number")
        if not issue_number:
            return False

        # Already closed?
        if issue_data.get("status") == "closed":
            return True

        # Build comprehensive closing comment
        close_comment = _build_close_comment(task_id, issue_data)

        # Close via gh CLI with detailed comment
        result = subprocess.run(
            ["gh", "issue", "close", str(issue_number), "--comment", close_comment],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=repo_root,
        )

        if result.returncode == 0:
            # Update mapping
            issue_data["status"] = "closed"
            issue_data["closed_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            mapping["task_to_issue"][task_key] = issue_data
            # Increment per-session ops_count (not global) and save
            mapping = _increment_ops_count(mapping)
            _save_issues_mapping(mapping)
            return True

    except Exception:
        pass
    return False
