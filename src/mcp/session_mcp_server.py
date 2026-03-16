"""
Session Management MCP Server - FastMCP-based session persistence for Claude Code.

Replaces 5+ session scripts with direct MCP tools. Includes session chaining,
ID generation, tag extraction, and flow context building.
Backend: Direct file I/O with pathlib
Transport: stdio

Tools (10):
  session_save, session_load, session_list, session_archive, session_query,
  session_create, session_link, session_tag, session_get_context, session_search_tags
"""

import json
import random
import re
import shutil
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("session-mgr", instructions="Session management with direct file I/O")

# Base paths
MEMORY_PATH = Path.home() / ".claude" / "memory"
SESSIONS_PATH = MEMORY_PATH / "sessions"
STATE_PATH = MEMORY_PATH / ".state"
CHAIN_INDEX_FILE = MEMORY_PATH / ".chain-index.json"
CURRENT_SESSION_FILE = MEMORY_PATH / ".current-session.json"

# Tech keywords for auto-tag extraction
_TECH_KEYWORDS = [
    "spring-boot", "docker", "kubernetes", "jenkins", "angular", "react",
    "mongodb", "postgresql", "redis", "elasticsearch", "eureka",
    "config-server", "gateway", "auth", "blog", "scheduler", "sitemap",
    "python", "java", "kotlin", "swift", "css", "seo", "mcp", "langgraph",
    "flask", "fastapi", "django", "terraform", "github-actions", "kafka",
]


def _json(data: dict) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


def _ensure_dirs(project: str = None):
    """Ensure session directories exist."""
    SESSIONS_PATH.mkdir(parents=True, exist_ok=True)
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    if project:
        (SESSIONS_PATH / project).mkdir(parents=True, exist_ok=True)


@mcp.tool()
def session_save(
    session_id: str,
    data_type: str,
    content: str,
    project: str = "default"
) -> str:
    """Save session data to disk atomically.

    Args:
        session_id: Unique session identifier (e.g., '2026-03-15-14-30')
        data_type: Type of data - 'summary', 'state', 'context'
        content: Content to save (markdown or JSON string)
        project: Project name for organizing sessions
    """
    try:
        _ensure_dirs(project)

        if data_type == "state":
            # State files go to .state directory
            file_path = STATE_PATH / f"{project}.json"
            # Parse content as JSON if possible, otherwise wrap it
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                data = {"content": content, "updated_at": datetime.now().isoformat()}

            # Atomic write: write to temp then rename
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            temp_path.replace(file_path)

        elif data_type == "summary":
            # Session summaries go to sessions/{project}/
            file_path = SESSIONS_PATH / project / f"session-{session_id}.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        elif data_type == "context":
            # Context snapshots
            file_path = SESSIONS_PATH / project / f"context-{session_id}.json"
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            temp_path.replace(file_path)

        else:
            return _json({"success": False, "error": f"Unknown data_type: {data_type}"})

        return _json({
            "success": True,
            "file": str(file_path),
            "data_type": data_type,
            "session_id": session_id,
            "size_bytes": file_path.stat().st_size
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_load(
    session_id: str = "",
    data_type: str = "state",
    project: str = "default"
) -> str:
    """Load session data from disk.

    Args:
        session_id: Session identifier (empty for latest state)
        data_type: 'summary', 'state', or 'context'
        project: Project name
    """
    try:
        if data_type == "state":
            file_path = STATE_PATH / f"{project}.json"
            if not file_path.exists():
                return _json({
                    "success": True,
                    "data": {},
                    "message": "No state file found"
                })
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _json({"success": True, "data": data, "file": str(file_path)})

        elif data_type == "summary":
            if session_id:
                file_path = SESSIONS_PATH / project / f"session-{session_id}.md"
            else:
                # Find latest session file
                project_dir = SESSIONS_PATH / project
                if not project_dir.exists():
                    return _json({"success": True, "data": "", "message": "No sessions found"})
                session_files = sorted(project_dir.glob("session-*.md"), reverse=True)
                if not session_files:
                    return _json({"success": True, "data": "", "message": "No sessions found"})
                file_path = session_files[0]

            if not file_path.exists():
                return _json({"success": False, "error": f"Session not found: {session_id}"})
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return _json({"success": True, "data": content, "file": str(file_path)})

        elif data_type == "context":
            file_path = SESSIONS_PATH / project / f"context-{session_id}.json"
            if not file_path.exists():
                return _json({"success": False, "error": f"Context not found: {session_id}"})
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _json({"success": True, "data": data, "file": str(file_path)})

        else:
            return _json({"success": False, "error": f"Unknown data_type: {data_type}"})

    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_list(project: str = "", limit: int = 20) -> str:
    """List available sessions.

    Args:
        project: Filter by project name (empty = all projects)
        limit: Maximum number of sessions to return
    """
    try:
        sessions = []

        if project:
            project_dirs = [SESSIONS_PATH / project]
        else:
            if not SESSIONS_PATH.exists():
                return _json({"success": True, "sessions": [], "count": 0})
            project_dirs = [d for d in SESSIONS_PATH.iterdir() if d.is_dir()]

        for proj_dir in project_dirs:
            if not proj_dir.exists():
                continue
            proj_name = proj_dir.name
            for session_file in sorted(proj_dir.glob("session-*.md"), reverse=True):
                stat = session_file.stat()
                sessions.append({
                    "project": proj_name,
                    "session_id": session_file.stem.replace("session-", ""),
                    "file": str(session_file),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
                if len(sessions) >= limit:
                    break

        # Sort by modified time descending
        sessions.sort(key=lambda s: s["modified"], reverse=True)
        sessions = sessions[:limit]

        return _json({
            "success": True,
            "sessions": sessions,
            "count": len(sessions)
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_archive(days_old: int = 30) -> str:
    """Archive sessions older than specified days.

    Args:
        days_old: Archive sessions older than this many days (default: 30)
    """
    try:
        cutoff = datetime.now() - timedelta(days=days_old)
        archived = []
        archive_dir = SESSIONS_PATH / "_archived"
        archive_dir.mkdir(parents=True, exist_ok=True)

        if not SESSIONS_PATH.exists():
            return _json({"success": True, "archived": [], "count": 0})

        for proj_dir in SESSIONS_PATH.iterdir():
            if not proj_dir.is_dir() or proj_dir.name.startswith("_"):
                continue

            for session_file in proj_dir.glob("session-*.md"):
                file_mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
                if file_mtime < cutoff:
                    # Move to archive
                    dest_dir = archive_dir / proj_dir.name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / session_file.name
                    shutil.move(str(session_file), str(dest))
                    archived.append({
                        "file": session_file.name,
                        "project": proj_dir.name,
                        "age_days": (datetime.now() - file_mtime).days
                    })

        return _json({
            "success": True,
            "archived": archived,
            "count": len(archived),
            "archive_dir": str(archive_dir)
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_query(filters: str = "{}") -> str:
    """Query sessions with filters.

    Args:
        filters: JSON string with filter criteria.
            Supported keys: project, date_from, date_to, keyword
            Example: '{"project": "claude-insight", "keyword": "MCP"}'
    """
    try:
        filter_dict = json.loads(filters)
        project_filter = filter_dict.get("project", "")
        date_from = filter_dict.get("date_from", "")
        date_to = filter_dict.get("date_to", "")
        keyword = filter_dict.get("keyword", "").lower()

        results = []

        if not SESSIONS_PATH.exists():
            return _json({"success": True, "results": [], "count": 0})

        if project_filter:
            project_dirs = [SESSIONS_PATH / project_filter]
        else:
            project_dirs = [d for d in SESSIONS_PATH.iterdir() if d.is_dir() and not d.name.startswith("_")]

        for proj_dir in project_dirs:
            if not proj_dir.exists():
                continue

            for session_file in sorted(proj_dir.glob("session-*.md"), reverse=True):
                stat = session_file.stat()
                file_date = datetime.fromtimestamp(stat.st_mtime)

                # Date filters
                if date_from:
                    from_dt = datetime.fromisoformat(date_from)
                    if file_date < from_dt:
                        continue
                if date_to:
                    to_dt = datetime.fromisoformat(date_to)
                    if file_date > to_dt:
                        continue

                # Keyword filter
                if keyword:
                    with open(session_file, "r", encoding="utf-8") as f:
                        content = f.read().lower()
                    if keyword not in content:
                        continue

                results.append({
                    "project": proj_dir.name,
                    "session_id": session_file.stem.replace("session-", ""),
                    "file": str(session_file),
                    "modified": file_date.isoformat(),
                    "size_bytes": stat.st_size
                })

                if len(results) >= 50:
                    break

        return _json({
            "success": True,
            "results": results,
            "count": len(results),
            "filters": filter_dict
        })
    except json.JSONDecodeError:
        return _json({"success": False, "error": "Invalid JSON in filters parameter"})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


def _load_chain_index() -> dict:
    """Load session chain index from disk."""
    try:
        if CHAIN_INDEX_FILE.exists():
            return json.loads(CHAIN_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"version": "1.0.0", "sessions": {}, "tag_index": {}}


def _save_chain_index(index: dict):
    """Save session chain index atomically."""
    CHAIN_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = CHAIN_INDEX_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")
    temp.replace(CHAIN_INDEX_FILE)


def _extract_tags(prompt: str, task_type: str = "", skill: str = "",
                  project_cwd: str = "") -> list:
    """Auto-extract tags from prompt and metadata."""
    tags = set()
    if task_type:
        tags.add(task_type.lower().replace(" ", "-"))
    if skill and skill != "adaptive-skill-intelligence":
        tags.add(skill)
    if project_cwd:
        parts = project_cwd.replace("\\", "/").rstrip("/").split("/")
        if parts:
            tags.add(parts[-1])
    prompt_lower = prompt.lower()
    for kw in _TECH_KEYWORDS:
        if kw in prompt_lower:
            tags.add(kw)
    return sorted(tags)


@mcp.tool()
def session_create(
    project: str = "default",
    task_type: str = "",
    skill: str = "",
    prompt: str = "",
    project_cwd: str = ""
) -> str:
    """Create a new session with unique ID and register it in the chain index.

    Generates ID format: SESSION-YYYYMMDD-HHMMSS-XXXX

    Args:
        project: Project name
        task_type: Type of task (e.g., 'Implementation', 'Bug Fix')
        skill: Skill being used
        prompt: User's prompt text (used for auto-tag extraction)
        project_cwd: Working directory path (used for project tag extraction)
    """
    try:
        now = datetime.now()
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        session_id = f"SESSION-{now.strftime('%Y%m%d-%H%M%S')}-{suffix}"

        # Auto-extract tags
        tags = _extract_tags(prompt, task_type, skill, project_cwd)

        # Register in chain index
        index = _load_chain_index()
        index["sessions"][session_id] = {
            "parent": None,
            "children": [],
            "related": [],
            "tags": tags,
            "project": project,
            "skill": skill,
            "task_type": task_type,
            "summary": "",
            "created_at": now.isoformat(),
            "last_prompt": prompt[:200] if prompt else ""
        }

        # Update tag index
        for tag in tags:
            if tag not in index["tag_index"]:
                index["tag_index"][tag] = []
            if session_id not in index["tag_index"][tag]:
                index["tag_index"][tag].append(session_id)

        _save_chain_index(index)

        # Update current session pointer
        CURRENT_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURRENT_SESSION_FILE.write_text(json.dumps({
            "current_session_id": session_id,
            "project": project,
            "created_at": now.isoformat()
        }, indent=2), encoding="utf-8")

        _ensure_dirs(project)

        return _json({
            "success": True,
            "session_id": session_id,
            "project": project,
            "tags": tags,
            "created_at": now.isoformat()
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_link(
    child_id: str,
    parent_id: str
) -> str:
    """Link a child session to its parent (for /clear continuity).

    Args:
        child_id: New session ID (child)
        parent_id: Previous session ID (parent)
    """
    try:
        index = _load_chain_index()

        if parent_id not in index["sessions"]:
            index["sessions"][parent_id] = {
                "parent": None, "children": [], "related": [],
                "tags": [], "project": "", "skill": "", "task_type": "",
                "summary": "", "created_at": "", "last_prompt": ""
            }

        if child_id not in index["sessions"]:
            index["sessions"][child_id] = {
                "parent": parent_id, "children": [], "related": [],
                "tags": [], "project": "", "skill": "", "task_type": "",
                "summary": "", "created_at": datetime.now().isoformat(),
                "last_prompt": ""
            }
        else:
            index["sessions"][child_id]["parent"] = parent_id

        if child_id not in index["sessions"][parent_id]["children"]:
            index["sessions"][parent_id]["children"].append(child_id)

        _save_chain_index(index)

        return _json({
            "success": True,
            "child": child_id,
            "parent": parent_id,
            "message": f"Linked {child_id} -> {parent_id}"
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_tag(
    session_id: str,
    tags: str,
    summary: str = ""
) -> str:
    """Add tags and optional summary to a session. Auto-relates by shared tags.

    Args:
        session_id: Session ID to tag
        tags: Comma-separated tag list (e.g., 'spring-boot,docker,scheduler')
        summary: Optional session summary text
    """
    try:
        index = _load_chain_index()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        if session_id not in index["sessions"]:
            index["sessions"][session_id] = {
                "parent": None, "children": [], "related": [],
                "tags": [], "project": "", "skill": "", "task_type": "",
                "summary": "", "created_at": datetime.now().isoformat(),
                "last_prompt": ""
            }

        session = index["sessions"][session_id]
        existing_tags = set(session.get("tags", []))
        new_tags = existing_tags | set(tag_list)
        session["tags"] = sorted(new_tags)

        if summary:
            session["summary"] = summary

        # Update tag index
        for tag in tag_list:
            if tag not in index["tag_index"]:
                index["tag_index"][tag] = []
            if session_id not in index["tag_index"][tag]:
                index["tag_index"][tag].append(session_id)

        # Auto-relate sessions that share 2+ tags
        related_found = []
        for other_id, other_session in index["sessions"].items():
            if other_id == session_id:
                continue
            other_tags = set(other_session.get("tags", []))
            shared = new_tags & other_tags
            if len(shared) >= 2:
                if other_id not in session.get("related", []):
                    session.setdefault("related", []).append(other_id)
                if session_id not in other_session.get("related", []):
                    other_session.setdefault("related", []).append(session_id)
                related_found.append(other_id)

        _save_chain_index(index)

        return _json({
            "success": True,
            "session_id": session_id,
            "tags": session["tags"],
            "auto_related": related_found
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_get_context(
    session_id: str,
    max_ancestors: int = 5,
    max_related: int = 5
) -> str:
    """Get chain context for a session (ancestors + related sessions).

    Walks the parent chain and finds related sessions for context continuity.

    Args:
        session_id: Session to get context for
        max_ancestors: Max parent sessions to walk (default: 5)
        max_related: Max related sessions to include (default: 5)
    """
    try:
        index = _load_chain_index()

        if session_id not in index["sessions"]:
            return _json({
                "success": True,
                "session_id": session_id,
                "ancestors": [],
                "related": [],
                "message": "Session not found in chain index"
            })

        session = index["sessions"][session_id]

        # Walk parent chain
        ancestors = []
        current = session.get("parent")
        visited = {session_id}
        while current and len(ancestors) < max_ancestors and current not in visited:
            visited.add(current)
            if current in index["sessions"]:
                parent = index["sessions"][current]
                ancestors.append({
                    "session_id": current,
                    "summary": parent.get("summary", ""),
                    "tags": parent.get("tags", []),
                    "task_type": parent.get("task_type", ""),
                    "skill": parent.get("skill", ""),
                    "created_at": parent.get("created_at", "")
                })
                current = parent.get("parent")
            else:
                break

        # Find related sessions
        related = []
        for rel_id in session.get("related", [])[:max_related]:
            if rel_id in index["sessions"]:
                rel = index["sessions"][rel_id]
                shared_tags = set(session.get("tags", [])) & set(rel.get("tags", []))
                related.append({
                    "session_id": rel_id,
                    "summary": rel.get("summary", ""),
                    "tags": rel.get("tags", []),
                    "shared_tags": sorted(shared_tags),
                    "created_at": rel.get("created_at", "")
                })

        return _json({
            "success": True,
            "session_id": session_id,
            "current": {
                "tags": session.get("tags", []),
                "task_type": session.get("task_type", ""),
                "skill": session.get("skill", ""),
                "project": session.get("project", "")
            },
            "ancestors": ancestors,
            "related": related,
            "chain_depth": len(ancestors)
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def session_search_tags(
    tags: str,
    limit: int = 20
) -> str:
    """Search sessions by tags. Returns sessions matching ANY of the given tags.

    Args:
        tags: Comma-separated tag list to search for
        limit: Max results (default: 20)
    """
    try:
        index = _load_chain_index()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        matching = {}
        for tag in tag_list:
            for sid in index.get("tag_index", {}).get(tag, []):
                if sid not in matching:
                    matching[sid] = {"session_id": sid, "matched_tags": [], "all_tags": []}
                matching[sid]["matched_tags"].append(tag)
                if sid in index["sessions"]:
                    matching[sid]["all_tags"] = index["sessions"][sid].get("tags", [])
                    matching[sid]["summary"] = index["sessions"][sid].get("summary", "")
                    matching[sid]["project"] = index["sessions"][sid].get("project", "")

        # Sort by number of matched tags (most relevant first)
        results = sorted(matching.values(),
                        key=lambda x: len(x["matched_tags"]), reverse=True)[:limit]

        return _json({
            "success": True,
            "results": results,
            "count": len(results),
            "searched_tags": tag_list
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
