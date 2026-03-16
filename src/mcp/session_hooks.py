"""
Session MCP Hook Integration - Bridges pipeline scripts to Session MCP tools.

Provides direct Python calls to session_accumulate, session_finalize,
session_create, and session_link WITHOUT subprocess overhead.

Usage from 3-level-flow.py / clear-session-handler.py:
    from src.mcp.session_hooks import accumulate_request, finalize_session, create_session, link_sessions

These functions import session_mcp_server tools directly (same process, no IPC).
All calls are non-blocking (wrapped in try/except, never crash the caller).

Version: 1.0.0
Windows-Safe: ASCII only (cp1252 compatible)
"""

import sys
import json
from pathlib import Path
from typing import Optional

# Ensure src/mcp is importable
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _safe_parse(result_json: str) -> dict:
    """Parse JSON result from MCP tool, return empty dict on failure."""
    try:
        return json.loads(result_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def create_session(
    project: str = "default",
    task_type: str = "",
    skill: str = "",
    prompt: str = "",
    project_cwd: str = ""
) -> Optional[str]:
    """Create a new session and return the session ID.

    Non-blocking: returns None on any failure.
    """
    try:
        from session_mcp_server import session_create
        result = _safe_parse(session_create(
            project=project,
            task_type=task_type,
            skill=skill,
            prompt=prompt,
            project_cwd=project_cwd
        ))
        if result.get("success"):
            return result.get("session_id")
    except Exception:
        pass
    return None


def link_sessions(child_id: str, parent_id: str) -> bool:
    """Link child session to parent. Non-blocking."""
    try:
        from session_mcp_server import session_link
        result = _safe_parse(session_link(child_id=child_id, parent_id=parent_id))
        return result.get("success", False)
    except Exception:
        return False


def accumulate_request(
    session_id: str,
    prompt: str = "",
    task_type: str = "",
    skill: str = "",
    complexity: int = 0,
    model: str = "",
    cwd: str = "",
    plan_mode: bool = False,
    context_pct: int = 0,
    supplementary_skills: str = "",
    standards_count: int = 0,
    rules_count: int = 0
) -> bool:
    """Accumulate per-request data for session summary.

    Called at the end of 3-level-flow.py pipeline execution.
    Non-blocking: returns False on any failure, never crashes caller.
    """
    try:
        from session_mcp_server import session_accumulate
        result = _safe_parse(session_accumulate(
            session_id=session_id,
            prompt=prompt,
            task_type=task_type,
            skill=skill,
            complexity=complexity,
            model=model,
            cwd=cwd,
            plan_mode=plan_mode,
            context_pct=context_pct,
            supplementary_skills=supplementary_skills,
            standards_count=standards_count,
            rules_count=rules_count
        ))
        return result.get("success", False)
    except Exception:
        return False


def finalize_session(session_id: str) -> bool:
    """Generate comprehensive session summary on /clear.

    Called by clear-session-handler.py.
    Non-blocking: returns False on any failure, never crashes caller.
    """
    try:
        from session_mcp_server import session_finalize
        result = _safe_parse(session_finalize(session_id=session_id))
        return result.get("success", False)
    except Exception:
        return False


def tag_session(session_id: str, tags: str, summary: str = "") -> bool:
    """Add tags to session. Non-blocking."""
    try:
        from session_mcp_server import session_tag
        result = _safe_parse(session_tag(
            session_id=session_id, tags=tags, summary=summary
        ))
        return result.get("success", False)
    except Exception:
        return False
