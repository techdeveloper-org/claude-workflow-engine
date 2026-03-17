"""
Post-Tool Tracker MCP Server - Tool usage tracking after every tool call.

Consolidates post-tool-tracker.py (1,724 LOC) into a FastMCP server.
Tracks tool usage, progress, flags, and triggers post-execution workflows.

Responsibilities:
1. Log tool usage to tool-tracker.jsonl (rich activity data)
2. Update session progress (total_progress, tool_counts, modified_files)
3. Clear enforcement flags (task-breakdown, skill-selection) on appropriate tools
4. Track context window usage estimation
5. Enforce task update frequency (warn if >5 calls without TaskUpdate)
6. Complexity-aware phase enforcement (complexity >= 6 requires phased execution)

Backend: Direct file I/O (session-progress.json, tool-tracker.jsonl, flag files)
Transport: stdio

Tools (6):
  track_tool_usage, increment_progress, clear_enforcement_flag,
  get_progress_status, get_tool_stats, check_commit_readiness
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.path_resolver import get_config_dir

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler
from base.persistence import AtomicJsonStore, JsonlAppender, SessionIdResolver

mcp = FastMCP(
    "post-tool-tracker",
    instructions="Post-tool tracking: progress, flags, metrics after every tool call"
)

# Paths
MEMORY_PATH = get_config_dir()
LOGS_PATH = MEMORY_PATH / "logs"
PROGRESS_FILE = LOGS_PATH / "session-progress.json"
CURRENT_SESSION_FILE = MEMORY_PATH / ".current-session.json"

# Persistence singletons
_progress_store = AtomicJsonStore(PROGRESS_FILE)
_session_resolver = SessionIdResolver(MEMORY_PATH)

# Progress delta per tool type (complexity-weighted in track_tool_usage)
PROGRESS_DELTA = {
    "Write": 8, "Edit": 5, "NotebookEdit": 5,
    "Bash": 3, "Read": 1, "Grep": 1, "Glob": 1,
    "Agent": 4, "TaskCreate": 2, "TaskUpdate": 1,
    "Skill": 2, "WebSearch": 1, "WebFetch": 1,
}


def _get_session_id() -> str:
    """Get current session ID via SessionIdResolver singleton."""
    return _session_resolver.get()


def _default_progress() -> dict:
    """Default progress state factory."""
    return {
        "session_id": _get_session_id(),
        "total_progress": 0,
        "tool_counts": {},
        "last_tool": "",
        "last_tool_at": "",
        "tasks_created": 0,
        "tasks_completed": 0,
        "errors_seen": 0,
        "modified_files_since_commit": [],
        "content_chars": 0,
        "context_estimate_pct": 0,
        "tools_since_last_update": 0,
    }


def _load_progress() -> dict:
    """Load session progress state via AtomicJsonStore."""
    return _progress_store.load(default=_default_progress())


def _save_progress(state: dict):
    """Save session progress atomically via AtomicJsonStore."""
    _progress_store.save(state)


def _log_tool_entry(entry: dict):
    """Append tool entry to tool-tracker.jsonl."""
    session_id = _get_session_id()
    if not session_id:
        return
    session_dir = LOGS_PATH / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    tracker_file = session_dir / "tool-tracker.jsonl"
    with open(tracker_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _estimate_context_pct(tool_counts: dict, content_chars: int = 0) -> int:
    """Estimate context window usage percentage."""
    base = 15  # CLAUDE.md + system prompt
    tool_total = sum(tool_counts.values())
    tool_pct = min(40, tool_total * 0.5)
    content_pct = min(35, content_chars / 5000)
    return min(95, int(base + tool_pct + content_pct))


# =============================================================================
# TOOL 1: TRACK TOOL USAGE (Main entry point)
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def track_tool_usage(
    tool_name: str,
    tool_input: str = "{}",
    is_error: bool = False,
    response_chars: int = 0
) -> str:
    """Track a completed tool call with rich activity data.

    Updates session progress, logs to tool-tracker.jsonl, handles flag
    clearing, and enforces task update frequency.

    Args:
        tool_name: Tool that was called (Write, Edit, Bash, Read, etc.)
        tool_input: JSON string of tool parameters
        is_error: Whether the tool call resulted in an error
        response_chars: Approximate character count of tool response
    """
    try:
        params = json.loads(tool_input)
    except (json.JSONDecodeError, TypeError):
        params = {}

    try:
        state = _load_progress()
        session_id = _get_session_id()
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        warnings = []

        # Load flow-trace for complexity
        complexity = 0
        try:
            trace_file = LOGS_PATH / "sessions" / session_id / "flow-trace.json"
            if trace_file.exists():
                trace = json.loads(trace_file.read_text(encoding="utf-8"))
                if isinstance(trace, list) and trace:
                    trace = trace[-1]
                fd = trace.get("final_decision", {})
                complexity = fd.get("complexity", 0)
        except Exception:
            pass

        # Calculate complexity-weighted progress delta
        base_delta = 0 if is_error else PROGRESS_DELTA.get(tool_name, 0)
        if complexity >= 15 and base_delta > 0:
            delta = max(1, base_delta // 4)
        elif complexity >= 8 and base_delta > 0:
            delta = max(1, base_delta // 2)
        else:
            delta = base_delta

        # Build log entry
        entry = {
            "ts": now,
            "tool": tool_name,
            "status": "error" if is_error else "success",
            "progress_delta": delta,
        }

        # Rich activity data per tool type
        if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
            fp = params.get("file_path", "") or params.get("notebook_path", "")
            if fp:
                parts = fp.replace("\\", "/").split("/")
                entry["file"] = "/".join(parts[-3:]) if len(parts) > 3 else fp

        if tool_name == "Bash":
            entry["command"] = params.get("command", "")[:200]
        elif tool_name == "Edit":
            old_s = params.get("old_string", "")
            new_s = params.get("new_string", "")
            if old_s or new_s:
                entry["edit_size"] = len(new_s) - len(old_s)
        elif tool_name == "Write":
            content = params.get("content", "")
            if content:
                entry["content_lines"] = content.count("\n") + 1
        elif tool_name == "Grep":
            entry["pattern"] = params.get("pattern", "")[:100]
        elif tool_name == "TaskCreate":
            entry["task_subject"] = params.get("subject", "")[:150]
        elif tool_name == "Skill":
            entry["skill_name"] = params.get("skill", "")

        _log_tool_entry(entry)

        # Update progress state
        state["total_progress"] = min(100, state["total_progress"] + delta)
        state["tool_counts"][tool_name] = state["tool_counts"].get(tool_name, 0) + 1
        state["last_tool"] = tool_name
        state["last_tool_at"] = now
        state["content_chars"] = state.get("content_chars", 0) + response_chars
        state["context_estimate_pct"] = _estimate_context_pct(
            state["tool_counts"], state.get("content_chars", 0)
        )

        if is_error:
            state["errors_seen"] = state.get("errors_seen", 0) + 1

        # Track modified files since last commit
        if tool_name in ("Write", "Edit", "NotebookEdit") and not is_error:
            fp = params.get("file_path", "")
            if fp:
                modified = state.get("modified_files_since_commit", [])
                short = "/".join(fp.replace("\\", "/").split("/")[-3:])
                if short not in modified:
                    modified.append(short)
                state["modified_files_since_commit"] = modified

        # Clear flags on appropriate tools
        if tool_name == "TaskCreate" and not is_error:
            state["tasks_created"] = state.get("tasks_created", 0) + 1
            _clear_flag("task-breakdown-pending", session_id)

        if tool_name in ("Skill", "Task") and not is_error:
            _clear_flag("skill-selection-pending", session_id)

        # Task update frequency enforcement
        if tool_name in ("TaskUpdate", "TaskCreate"):
            state["tools_since_last_update"] = 0
        else:
            state["tools_since_last_update"] = state.get("tools_since_last_update", 0) + 1

        tools_since = state["tools_since_last_update"]
        if tools_since > 5 and tool_name in ("Write", "Edit", "Bash", "NotebookEdit"):
            if complexity >= 3:
                warnings.append(
                    f"{tools_since} tool calls since last TaskUpdate - "
                    "update every 2-3 calls (max 5)"
                )

        # Complexity phase enforcement
        if complexity >= 6 and state.get("tasks_created", 0) == 0:
            if tool_name in ("Write", "Edit", "NotebookEdit"):
                warnings.append(
                    f"Complexity={complexity} but 0 tasks created - "
                    "phased execution required for complexity >= 6"
                )

        if tool_name == "TaskUpdate":
            status = params.get("status", "")
            if status == "completed":
                state["tasks_completed"] = state.get("tasks_completed", 0) + 1

        _save_progress(state)

        return to_json({
            "success": True,
            "tool": tool_name,
            "progress_delta": delta,
            "total_progress": state["total_progress"],
            "context_estimate_pct": state["context_estimate_pct"],
            "warnings": warnings,
            "session_id": session_id
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


def _clear_flag(flag_name: str, session_id: str):
    """Clear an enforcement flag."""
    if not session_id:
        return
    # New location
    fp = LOGS_PATH / "sessions" / session_id / "flags" / f"{flag_name}.json"
    fp.unlink(missing_ok=True)
    # Legacy
    legacy = Path.home() / ".claude" / f".{flag_name}-{session_id}.json"
    legacy.unlink(missing_ok=True)


# =============================================================================
# TOOL 2: INCREMENT PROGRESS (Manual)
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def increment_progress(delta: int = 5, reason: str = "") -> str:
    """Manually increment session progress.

    Args:
        delta: Progress increment (1-20)
        reason: Reason for increment
    """
    try:
        state = _load_progress()
        state["total_progress"] = min(100, state["total_progress"] + delta)
        _save_progress(state)
        return to_json({
            "success": True,
            "total_progress": state["total_progress"],
            "delta": delta,
            "reason": reason
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 3: CLEAR ENFORCEMENT FLAG
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def clear_enforcement_flag(flag_name: str) -> str:
    """Clear a specific enforcement flag for current session.

    Args:
        flag_name: 'task-breakdown-pending' or 'skill-selection-pending'
    """
    try:
        session_id = _get_session_id()
        _clear_flag(flag_name, session_id)
        return to_json({
            "success": True,
            "cleared": flag_name,
            "session_id": session_id
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 4: GET PROGRESS STATUS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def get_progress_status() -> str:
    """Get current session progress snapshot."""
    try:
        state = _load_progress()
        return to_json({
            "success": True,
            "total_progress": state.get("total_progress", 0),
            "tasks_created": state.get("tasks_created", 0),
            "tasks_completed": state.get("tasks_completed", 0),
            "errors_seen": state.get("errors_seen", 0),
            "tool_counts": state.get("tool_counts", {}),
            "total_tool_calls": sum(state.get("tool_counts", {}).values()),
            "last_tool": state.get("last_tool", ""),
            "modified_files": state.get("modified_files_since_commit", []),
            "context_estimate_pct": state.get("context_estimate_pct", 0),
            "tools_since_last_update": state.get("tools_since_last_update", 0),
            "session_id": state.get("session_id", "")
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 5: GET TOOL STATS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def get_tool_stats() -> str:
    """Get detailed tool usage statistics for current session."""
    try:
        session_id = _get_session_id()
        tracker_file = LOGS_PATH / "sessions" / session_id / "tool-tracker.jsonl"

        if not tracker_file.exists():
            return to_json({"success": True, "entries": 0, "message": "No tool tracker data"})

        entries = []
        for line in tracker_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue

        # Compute stats
        by_tool = {}
        errors = 0
        files_modified = set()
        for e in entries:
            tool = e.get("tool", "unknown")
            by_tool[tool] = by_tool.get(tool, 0) + 1
            if e.get("status") == "error":
                errors += 1
            if e.get("file") and e.get("tool") in ("Write", "Edit"):
                files_modified.add(e["file"])

        return to_json({
            "success": True,
            "session_id": session_id,
            "total_entries": len(entries),
            "by_tool": by_tool,
            "errors": errors,
            "files_modified": sorted(files_modified),
            "files_modified_count": len(files_modified),
            "first_entry": entries[0].get("ts", "") if entries else "",
            "last_entry": entries[-1].get("ts", "") if entries else "",
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 6: CHECK COMMIT READINESS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_commit_readiness() -> str:
    """Check if auto-commit should be triggered based on modified files."""
    try:
        state = _load_progress()
        modified = state.get("modified_files_since_commit", [])
        progress = state.get("total_progress", 0)
        tasks_completed = state.get("tasks_completed", 0)

        should_commit = (
            len(modified) >= 3 or
            (progress >= 50 and len(modified) >= 1) or
            tasks_completed > 0
        )

        return to_json({
            "success": True,
            "should_commit": should_commit,
            "modified_files": modified,
            "modified_count": len(modified),
            "progress": progress,
            "tasks_completed": tasks_completed,
            "reason": (
                "3+ files modified" if len(modified) >= 3 else
                "Progress >= 50% with changes" if progress >= 50 and modified else
                "Task completed with changes" if tasks_completed > 0 else
                "Not enough changes yet"
            )
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
