"""
Pre-Tool Gate MCP Server - Policy enforcement before every tool call.

Consolidates pre-tool-enforcer.py (2,027 LOC) into a FastMCP server.
Enforces 8 policy checks before allowing Write/Edit/NotebookEdit:

1. Checkpoint review pending (Level 3.3)
2. Task breakdown pending (Level 3.1) - TaskCreate must be called first
3. Skill/agent selection pending (Level 3.5) - Skill must be invoked first
4. Context read complete (Level 3.0) - Project context must be read
5. Level 1 sync complete - Session/context sync done
6. Level 2 standards complete - Standards loaded
7. Bash Windows command blocking (Level 3.7) - Block del/copy/dir/xcopy
8. Python Unicode blocking (Level 3.7) - Block non-ASCII in .py on Windows

Also provides:
- Dynamic skill context hints (file extension -> skill suggestion)
- Failure KB pattern matching (known failure prevention)
- Tool-specific optimization hints (Grep head_limit, Read offset/limit)

Backend: Direct file I/O (flag files, flow-trace.json, failure-kb.json)
Transport: stdio

Tools (8):
  validate_tool_call, check_task_breakdown, check_skill_selected,
  check_level_completion, get_enforcer_state, check_failure_patterns,
  get_dynamic_skill_hint, reset_enforcer_flags
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.path_resolver import get_config_dir

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler
from base.persistence import SessionIdResolver

mcp = FastMCP(
    "pre-tool-gate",
    instructions="Policy enforcement gate - validates tool calls before execution"
)

# Paths
MEMORY_PATH = get_config_dir()
FLAG_DIR = Path.home() / ".claude"
CURRENT_SESSION_FILE = MEMORY_PATH / ".current-session.json"
LOGS_PATH = MEMORY_PATH / "logs" / "sessions"

# Singleton session resolver
_session_resolver = SessionIdResolver(MEMORY_PATH)

# Constants
CHECKPOINT_MAX_AGE_MINUTES = 60
FLAG_TTL_SECONDS = 90
BLOCKED_TOOLS = {"Write", "Edit", "NotebookEdit"}
ALWAYS_ALLOWED = {"Read", "Grep", "Glob", "WebFetch", "WebSearch", "Task"}

# Windows commands to block
WINDOWS_BLOCKED_CMDS = [
    "del ", "del/", "copy ", "copy/", "xcopy", "move ", "ren ", "rename ",
    "dir ", "dir/", "type ", "cls", "md ", "mkdir ", "rd ", "rmdir ",
    "attrib ", "cacls ", "comp ", "compact ", "diskcomp", "diskcopy",
    "format ", "label ", "mode ", "more ", "net ", "path ", "print ",
    "recover ", "replace ", "sort ", "subst ", "tree ", "vol ",
]


def _get_session_id() -> str:
    """Get current session ID via SessionIdResolver singleton."""
    return _session_resolver.get()


def _find_flag(flag_name: str, session_id: str) -> Optional[dict]:
    """Find session-specific flag file, auto-expire stale flags."""
    if not session_id:
        return None

    # New location: session folder
    flag_file = LOGS_PATH / session_id / "flags" / f"{flag_name}.json"
    if flag_file.exists():
        try:
            data = json.loads(flag_file.read_text(encoding="utf-8"))
            # Auto-expire
            created = data.get("created_at", "")
            if created:
                age = datetime.now() - datetime.fromisoformat(created)
                if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                    flag_file.unlink(missing_ok=True)
                    return None
            return data
        except Exception:
            pass

    # Legacy: ~/.claude/ location
    legacy = FLAG_DIR / f".{flag_name}-{session_id}.json"
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            created = data.get("created_at", "")
            if created:
                age = datetime.now() - datetime.fromisoformat(created)
                if age > timedelta(minutes=CHECKPOINT_MAX_AGE_MINUTES):
                    legacy.unlink(missing_ok=True)
                    return None
            return data
        except Exception:
            pass

    return None


def _check_flag_with_ttl(flag_name: str, session_id: str, ttl_seconds: int = 90):
    """Check flag with TTL expiry. Returns (is_active, flag_data)."""
    data = _find_flag(flag_name, session_id)
    if not data:
        return False, None

    created = data.get("created_at", "")
    if created:
        try:
            age = (datetime.now() - datetime.fromisoformat(created)).total_seconds()
            if age > ttl_seconds:
                # Expired - try to clean up
                flag_file = LOGS_PATH / session_id / "flags" / f"{flag_name}.json"
                flag_file.unlink(missing_ok=True)
                return False, None
        except Exception:
            pass

    return True, data


def _load_flow_trace(session_id: str) -> Optional[dict]:
    """Load latest flow-trace entry for session."""
    if not session_id:
        return None
    trace_file = LOGS_PATH / session_id / "flow-trace.json"
    if not trace_file.exists():
        return None
    try:
        data = json.loads(trace_file.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data[-1]
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _pipeline_step_present(trace: dict, step_name: str) -> bool:
    """Check if pipeline step exists in flow-trace."""
    if not trace:
        return False
    for entry in trace.get("pipeline", []):
        if entry.get("step") == step_name:
            return True
    return False


# =============================================================================
# TOOL 1: FULL VALIDATION PIPELINE
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def validate_tool_call(tool_name: str, tool_input: str = "{}") -> str:
    """Run all policy checks for a tool call. Returns allow/block decision.

    Checks in order:
    1. Checkpoint pending (Level 3.3)
    2. Task breakdown pending (Level 3.1)
    3. Skill selection pending (Level 3.5)
    4. Context read complete (Level 3.0)
    5. Level 1 sync complete
    6. Level 2 standards complete
    7. Bash Windows command blocking (Level 3.7)
    8. Python Unicode blocking (Level 3.7)

    Args:
        tool_name: Tool being called (Write, Edit, Bash, Read, Grep, etc.)
        tool_input: JSON string of tool parameters
    """
    try:
        params = json.loads(tool_input)
    except (json.JSONDecodeError, TypeError):
        params = {}

    session_id = _get_session_id()
    hints = []
    blocks = []

    # Always-allowed tools skip blocking checks
    if tool_name in ALWAYS_ALLOWED:
        return to_json({
            "allowed": True,
            "tool": tool_name,
            "hints": [],
            "blocks": [],
            "reason": "Tool is always allowed"
        })

    # Only run blocking checks for file-modification tools
    if tool_name in BLOCKED_TOOLS:
        # Check 1: Checkpoint pending
        flag = _find_flag("checkpoint-pending", session_id)
        if flag:
            blocks.append(f"Review checkpoint pending - user must confirm before {tool_name}")

        # Check 2: Task breakdown pending
        if not blocks:
            active, data = _check_flag_with_ttl("task-breakdown-pending", session_id, FLAG_TTL_SECONDS)
            if active:
                blocks.append(f"Task breakdown pending - call TaskCreate before {tool_name}")

        # Check 3: Skill selection pending
        if not blocks:
            active, data = _check_flag_with_ttl("skill-selection-pending", session_id, FLAG_TTL_SECONDS)
            if active:
                skill = data.get("required_skill", "unknown") if data else "unknown"
                blocks.append(f"Skill selection pending - invoke '{skill}' before {tool_name}")

        # Check 4-6: Flow-trace pipeline checks (fail-open if no trace)
        if not blocks:
            trace = _load_flow_trace(session_id)
            if trace:
                if not _pipeline_step_present(trace, "LEVEL_1_CONTEXT") and \
                   not _pipeline_step_present(trace, "LEVEL_1_SESSION"):
                    blocks.append("Level 1 Sync System not complete yet")
                elif not _pipeline_step_present(trace, "LEVEL_2_STANDARDS"):
                    blocks.append("Level 2 Standards System not complete yet")

    # Check 7: Bash Windows commands
    if tool_name == "Bash" and sys.platform == "win32":
        command = params.get("command", "").strip().lower()
        for blocked_cmd in WINDOWS_BLOCKED_CMDS:
            if command.startswith(blocked_cmd.strip().lower()):
                blocks.append(f"Windows command '{blocked_cmd.strip()}' blocked - use Unix equivalent")
                break

    # Check 8: Python Unicode blocking
    if tool_name in ("Write", "Edit") and sys.platform == "win32":
        file_path = params.get("file_path", "")
        content = params.get("content", "") or params.get("new_string", "")
        if file_path.endswith(".py") and content:
            try:
                content.encode("ascii")
            except UnicodeEncodeError:
                blocks.append("Non-ASCII characters in .py file on Windows (cp1252 unsafe)")

    # Optimization hints (non-blocking)
    if tool_name == "Grep":
        if not params.get("head_limit"):
            hints.append("Add head_limit to Grep (mandatory optimization)")
    elif tool_name == "Read":
        file_path = params.get("file_path", "")
        if file_path and not params.get("offset") and not params.get("limit"):
            p = Path(file_path)
            if p.exists() and p.is_file():
                try:
                    lines = sum(1 for _ in open(p, "rb"))
                    if lines > 500:
                        hints.append(f"Large file ({lines} lines) - use offset/limit")
                except Exception:
                    pass

    allowed = len(blocks) == 0

    return to_json({
        "allowed": allowed,
        "tool": tool_name,
        "session_id": session_id,
        "hints": hints,
        "blocks": blocks,
        "checks_run": 8 if tool_name in BLOCKED_TOOLS else 2,
        "reason": blocks[0] if blocks else "All checks passed"
    })


# =============================================================================
# TOOL 2: TASK BREAKDOWN CHECK
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_task_breakdown() -> str:
    """Check if task breakdown is pending for current session."""
    try:
        session_id = _get_session_id()
        active, data = _check_flag_with_ttl("task-breakdown-pending", session_id, FLAG_TTL_SECONDS)
        return to_json({
            "success": True,
            "pending": active,
            "session_id": session_id,
            "flag_data": data,
            "ttl_seconds": FLAG_TTL_SECONDS
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 3: SKILL SELECTION CHECK
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_skill_selected() -> str:
    """Check if skill/agent selection is pending for current session."""
    try:
        session_id = _get_session_id()
        active, data = _check_flag_with_ttl("skill-selection-pending", session_id, FLAG_TTL_SECONDS)
        return to_json({
            "success": True,
            "pending": active,
            "session_id": session_id,
            "required_skill": data.get("required_skill", "") if data else "",
            "required_type": data.get("required_type", "") if data else "",
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 4: LEVEL COMPLETION CHECK
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_level_completion(level: str = "all") -> str:
    """Check if pipeline levels are complete in flow-trace.

    Args:
        level: 'level1', 'level2', or 'all'
    """
    try:
        session_id = _get_session_id()
        trace = _load_flow_trace(session_id)

        if not trace:
            return to_json({
                "success": True,
                "session_id": session_id,
                "trace_found": False,
                "message": "No flow-trace found (fail-open)"
            })

        l1_context = _pipeline_step_present(trace, "LEVEL_1_CONTEXT")
        l1_session = _pipeline_step_present(trace, "LEVEL_1_SESSION")
        l2_standards = _pipeline_step_present(trace, "LEVEL_2_STANDARDS")

        return to_json({
            "success": True,
            "session_id": session_id,
            "trace_found": True,
            "level1_context": l1_context,
            "level1_session": l1_session,
            "level1_complete": l1_context and l1_session,
            "level2_standards": l2_standards,
            "level2_complete": l2_standards,
            "all_complete": l1_context and l1_session and l2_standards
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 5: ENFORCER STATE
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def get_enforcer_state() -> str:
    """Get current enforcer state snapshot (all flags + flow-trace status)."""
    try:
        session_id = _get_session_id()

        checkpoint = _find_flag("checkpoint-pending", session_id)
        task_active, task_data = _check_flag_with_ttl("task-breakdown-pending", session_id, FLAG_TTL_SECONDS)
        skill_active, skill_data = _check_flag_with_ttl("skill-selection-pending", session_id, FLAG_TTL_SECONDS)
        trace = _load_flow_trace(session_id)

        return to_json({
            "success": True,
            "session_id": session_id,
            "flags": {
                "checkpoint_pending": checkpoint is not None,
                "task_breakdown_pending": task_active,
                "skill_selection_pending": skill_active,
                "required_skill": skill_data.get("required_skill", "") if skill_data else ""
            },
            "pipeline": {
                "trace_exists": trace is not None,
                "level1_complete": (
                    _pipeline_step_present(trace, "LEVEL_1_CONTEXT") and
                    _pipeline_step_present(trace, "LEVEL_1_SESSION")
                ) if trace else False,
                "level2_complete": _pipeline_step_present(trace, "LEVEL_2_STANDARDS") if trace else False
            },
            "blocked_tools": sorted(BLOCKED_TOOLS),
            "always_allowed": sorted(ALWAYS_ALLOWED)
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 6: FAILURE KB PATTERNS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_failure_patterns(tool_name: str, tool_input: str = "{}") -> str:
    """Check known failure patterns from failure-kb.json for a tool call.

    Returns non-blocking hints about known failure patterns.

    Args:
        tool_name: Tool name (Edit, Read, Bash, etc.)
        tool_input: JSON string of tool parameters
    """
    try:
        params = json.loads(tool_input)
    except (json.JSONDecodeError, TypeError):
        params = {}

    hints = []

    # Load failure KB
    project_root = Path(__file__).resolve().parent.parent.parent
    kb_path = project_root / "scripts" / "architecture" / "03-execution-system" / "failure-prevention" / "failure-kb.json"

    kb = {}
    if kb_path.exists():
        try:
            kb = json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Check patterns
    if tool_name == "Edit":
        old_str = params.get("old_string", "")
        if old_str and re.match(r"^\s*\d+", old_str):
            hints.append("Edit old_string may contain line number prefix - strip before Edit")
        if not params.get("file_path"):
            hints.append("Edit requires file_path parameter")

    elif tool_name == "Bash" and sys.platform == "win32":
        cmd = params.get("command", "").strip().lower()
        # Check Windows -> Unix translations
        translations = {
            "del ": "rm", "copy ": "cp", "move ": "mv", "type ": "cat",
            "dir ": "ls", "cls": "clear", "ren ": "mv", "md ": "mkdir -p",
        }
        for win_cmd, unix_cmd in translations.items():
            if cmd.startswith(win_cmd):
                hints.append(f"Translate Windows '{win_cmd.strip()}' -> Unix '{unix_cmd}'")

    elif tool_name == "Grep":
        if not params.get("head_limit"):
            hints.append("Grep without head_limit can return excessive output")

    elif tool_name == "Read":
        fp = params.get("file_path", "")
        if fp and not params.get("offset") and not params.get("limit"):
            hints.append("Consider adding offset/limit for large files")

    return to_json({
        "success": True,
        "tool": tool_name,
        "hints": hints,
        "kb_loaded": bool(kb),
        "patterns_checked": len(hints)
    })


# =============================================================================
# TOOL 7: DYNAMIC SKILL HINT
# =============================================================================

# File extension -> skill mapping
_EXT_SKILL_MAP = {
    ".java": "java-spring-boot-microservices",
    ".kt": "kotlin-core",
    ".py": "python-core",
    ".ts": "typescript-core",
    ".tsx": "react-core",
    ".js": "javascript-core",
    ".jsx": "react-core",
    ".swift": "swiftui-core",
    ".xml": "android-xml-ui",
    ".css": "css-core",
    ".scss": "css-core",
    ".html": "html5-core",
    ".sql": "rdbms-core",
    ".yml": "docker",
    ".yaml": "kubernetes",
    ".tf": "kubernetes",
    ".md": None,
    ".json": "json-core",
    ".graphql": "graphql-core",
}


@mcp.tool()
@mcp_tool_handler
def get_dynamic_skill_hint(file_path: str) -> str:
    """Get skill/agent hint based on file extension.

    Args:
        file_path: File path being accessed
    """
    try:
        ext = Path(file_path).suffix.lower()
        skill = _EXT_SKILL_MAP.get(ext)

        # Special cases
        name = Path(file_path).name.lower()
        if name == "dockerfile" or name.endswith(".dockerfile"):
            skill = "docker"
        elif name == "jenkinsfile":
            skill = "jenkins-pipeline"
        elif name.endswith(".github/workflows"):
            skill = "github-actions-ci"

        return to_json({
            "success": True,
            "file": file_path,
            "extension": ext,
            "suggested_skill": skill,
            "has_suggestion": skill is not None
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 8: RESET FLAGS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def reset_enforcer_flags(flag_name: str = "all") -> str:
    """Reset enforcement flags for current session.

    Args:
        flag_name: 'task-breakdown-pending', 'skill-selection-pending',
                   'checkpoint-pending', or 'all'
    """
    try:
        session_id = _get_session_id()
        if not session_id:
            return to_json({"success": False, "error": "No active session"})

        flags_to_clear = []
        if flag_name == "all":
            flags_to_clear = ["task-breakdown-pending", "skill-selection-pending", "checkpoint-pending"]
        else:
            flags_to_clear = [flag_name]

        cleared = []
        for fname in flags_to_clear:
            # New location
            fp = LOGS_PATH / session_id / "flags" / f"{fname}.json"
            if fp.exists():
                fp.unlink(missing_ok=True)
                cleared.append(fname)
            # Legacy location
            legacy = FLAG_DIR / f".{fname}-{session_id}.json"
            if legacy.exists():
                legacy.unlink(missing_ok=True)
                if fname not in cleared:
                    cleared.append(fname)

        return to_json({
            "success": True,
            "session_id": session_id,
            "cleared": cleared,
            "count": len(cleared)
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
