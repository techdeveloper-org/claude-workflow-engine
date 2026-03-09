#!/usr/bin/env python3
"""
Script Name: session-chain-manager.py
Version: 1.0.0
Last Modified: 2026-02-23
Description: Session Chaining System - tracks relationships between sessions.
             Each session knows its parent (previous session), children (sessions
             that followed it), related sessions (by topic/project/skill), and
             tags for topic-based grouping.

             This gives Claude context continuity across /clear boundaries.
             When a new session starts, it can look at the chain to understand
             what was worked on before, which sessions are related, and what
             the user's recent workflow looks like.

Usage:
    # Link current session to parent (called by clear-session-handler.py)
    python session-chain-manager.py link --child SESSION-NEW --parent SESSION-OLD

    # Add tags to a session (called by 3-level-flow.py)
    python session-chain-manager.py tag --session SESSION-ID --tags "spring-boot,docker,k8s"

    # Mark two sessions as related (same topic/project)
    python session-chain-manager.py relate --session SESSION-A --related SESSION-B

    # Get chain context for a session (returns related sessions summary)
    python session-chain-manager.py context --session SESSION-ID

    # Get full chain for a session (ancestors + descendants)
    python session-chain-manager.py chain --session SESSION-ID

    # Search sessions by tag
    python session-chain-manager.py search --tag "spring-boot"

Hook Type: Utility (called by other hooks, not directly by Claude Code)
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
CHAIN_INDEX_FILE = MEMORY_BASE / 'sessions' / 'chain-index.json'
CHAIN_LOG = MEMORY_BASE / 'logs' / 'session-chain.log'
LOGS_SESSION_DIR = MEMORY_BASE / 'logs' / 'sessions'


# =============================================================================
# SESSION SUMMARY READER
# =============================================================================

def _read_session_summary_text(session_id):
    """Read the one-liner summary text from session-summary.json.

    Uses _lock_file/_unlock_file (Windows msvcrt file locking) to prevent
    reading a partially written file when the summary manager is finalising
    concurrently.

    Args:
        session_id (str): Session identifier used to locate the summary file
                          under LOGS_SESSION_DIR/{session_id}/session-summary.json.

    Returns:
        str or None: The 'summary_text' field from the JSON, or None when the
                     file is missing or the field is absent.
    """
    summary_file = LOGS_SESSION_DIR / session_id / 'session-summary.json'
    if not summary_file.exists():
        return None
    try:
        with open(summary_file, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        return data.get("summary_text")
    except Exception:
        return None


# =============================================================================
# LOGGING
# =============================================================================

def log_event(msg):
    """Append a timestamped message to the session-chain.log file.

    Creates parent directories automatically.  Content must be ASCII-safe
    for Windows cp1252 compatibility.  Errors are silently swallowed.

    Args:
        msg (str): ASCII-safe message to append.
    """
    CHAIN_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(CHAIN_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# CHAIN INDEX - Central index of all session relationships
# =============================================================================
#
# Structure:
# {
#   "version": "1.0.0",
#   "sessions": {
#     "SESSION-20260223-133518-2DRM": {
#       "parent": "SESSION-20260223-123812-PCZR",
#       "children": ["SESSION-20260223-140000-XXXX"],
#       "related": ["SESSION-20260222-100000-YYYY"],
#       "tags": ["spring-boot", "scheduler", "blog-generation"],
#       "project": "techdeveloper-scheduler",
#       "skill": "java-spring-boot-microservices",
#       "task_type": "Implementation",
#       "summary": "Blog generation scheduler improvements",
#       "created_at": "2026-02-23T13:35:18",
#       "last_prompt": "fix the blog scheduler..."
#     }
#   },
#   "tag_index": {
#     "spring-boot": ["SESSION-20260223-133518-2DRM", ...],
#     "docker": ["SESSION-20260222-100000-YYYY", ...]
#   }
# }
# =============================================================================

def read_chain_index():
    """Read the chain index JSON file with Windows file locking.

    Creates and returns a default empty index structure when the file does not
    exist yet.  Required keys ('version', 'sessions', 'tag_index') are
    back-filled if they are missing from an older index file.

    Returns:
        dict: Chain index with 'version', 'sessions', 'tag_index', and
              'last_updated' keys.  Returns a safe empty structure on errors.
    """
    if not CHAIN_INDEX_FILE.exists():
        return {
            "version": "1.0.0",
            "sessions": {},
            "tag_index": {},
            "last_updated": datetime.now().isoformat()
        }
    try:
        with open(CHAIN_INDEX_FILE, 'r', encoding='utf-8') as f:
            _lock_file(f)
            data = json.load(f)
            _unlock_file(f)
        # Ensure required keys
        data.setdefault("version", "1.0.0")
        data.setdefault("sessions", {})
        data.setdefault("tag_index", {})
        return data
    except Exception as e:
        log_event(f"[ERROR] Failed to read chain index: {e}")
        return {"version": "1.0.0", "sessions": {}, "tag_index": {}}


def write_chain_index(data):
    """Write the chain index dict to CHAIN_INDEX_FILE with Windows file locking.

    Stamps 'last_updated' with the current ISO timestamp before writing.
    Creates parent directories if needed.

    Args:
        data (dict): Complete chain index to persist (must be JSON-serialisable).
    """
    data["last_updated"] = datetime.now().isoformat()
    CHAIN_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CHAIN_INDEX_FILE, 'w', encoding='utf-8') as f:
            _lock_file(f)
            json.dump(data, f, indent=2)
            _unlock_file(f)
        log_event("[OK] Chain index saved")
    except Exception as e:
        log_event(f"[ERROR] Failed to write chain index: {e}")


def ensure_session_entry(index, session_id):
    """Ensure the chain index has an entry for session_id, creating one if absent.

    The default entry has None for parent/project/skill/task_type/summary/
    last_prompt, and empty lists for children/related/tags.

    Args:
        index (dict): Chain index dict from read_chain_index().
        session_id (str): Session identifier to ensure exists.

    Returns:
        dict: The same index dict, guaranteed to contain session_id.
    """
    if session_id not in index["sessions"]:
        index["sessions"][session_id] = {
            "parent": None,
            "children": [],
            "related": [],
            "tags": [],
            "project": None,
            "skill": None,
            "task_type": None,
            "summary": None,
            "created_at": datetime.now().isoformat(),
            "last_prompt": None
        }
    return index


# =============================================================================
# CORE OPERATIONS
# =============================================================================

def link_sessions(child_id, parent_id):
    """Link a new child session to its parent session in the chain index.

    Called by clear-session-handler.py immediately after /clear creates a new
    session.  Sets 'parent' on the child entry and appends child_id to the
    parent's 'children' list.  Also copies last_prompt, skill, and task_type
    from the parent's session JSON file when those fields are not yet set.

    Args:
        child_id (str): New session identifier (created after /clear).
        parent_id (str): Previous session identifier (active before /clear).

    Returns:
        bool: True on success; False when either ID is empty or they are equal.
    """
    if not child_id or not parent_id:
        log_event(f"[WARN] link_sessions called with empty IDs: child={child_id}, parent={parent_id}")
        return False

    if child_id == parent_id:
        log_event(f"[WARN] Cannot link session to itself: {child_id}")
        return False

    index = read_chain_index()
    index = ensure_session_entry(index, child_id)
    index = ensure_session_entry(index, parent_id)

    # Set parent on child
    index["sessions"][child_id]["parent"] = parent_id

    # Add child to parent's children list (no duplicates)
    if child_id not in index["sessions"][parent_id]["children"]:
        index["sessions"][parent_id]["children"].append(child_id)

    # Copy relevant metadata from parent's session JSON if available
    parent_session_file = SESSIONS_DIR / f'{parent_id}.json'
    if parent_session_file.exists():
        try:
            pdata = json.loads(parent_session_file.read_text(encoding='utf-8'))
            parent_entry = index["sessions"][parent_id]
            if not parent_entry.get("last_prompt"):
                parent_entry["last_prompt"] = pdata.get("last_prompt")
            if not parent_entry.get("skill"):
                parent_entry["skill"] = pdata.get("last_model")
            if not parent_entry.get("task_type"):
                parent_entry["task_type"] = pdata.get("last_task_type")
        except Exception:
            pass

    write_chain_index(index)
    log_event(f"[OK] Linked: {child_id} -> parent: {parent_id}")
    return True


def tag_session(session_id, tags, project=None, skill=None, task_type=None,
                summary=None, last_prompt=None):
    """Add tags and optional metadata to a session's chain index entry.

    Called by 3-level-flow.py after the task context (task_type, skill,
    project) is determined so that sessions can be searched and related by
    topic.  Duplicate tags are silently ignored.

    Args:
        session_id (str): Target session identifier.
        tags (list): List of tag strings to add (lower-cased automatically).
        project (str, optional): Project name extracted from the cwd.
        skill (str, optional): Primary skill or agent selected for the session.
        task_type (str, optional): Classified task type (e.g. 'Backend').
        summary (str, optional): Human-readable one-liner for the session.
        last_prompt (str, optional): Most recent user prompt (for context).

    Returns:
        bool: True on success; False when session_id is falsy.
    """
    if not session_id:
        return False

    index = read_chain_index()
    index = ensure_session_entry(index, session_id)

    entry = index["sessions"][session_id]

    # Add new tags (no duplicates)
    for tag in tags:
        tag = tag.strip().lower()
        if tag and tag not in entry["tags"]:
            entry["tags"].append(tag)

        # Update tag_index
        if tag not in index["tag_index"]:
            index["tag_index"][tag] = []
        if session_id not in index["tag_index"][tag]:
            index["tag_index"][tag].append(session_id)

    # Update metadata (only if provided and not already set, or if overwriting)
    if project:
        entry["project"] = project
    if skill:
        entry["skill"] = skill
    if task_type:
        entry["task_type"] = task_type
    if summary:
        entry["summary"] = summary
    if last_prompt:
        entry["last_prompt"] = last_prompt

    write_chain_index(index)
    log_event(f"[OK] Tagged {session_id}: tags={tags}, project={project}")
    return True


def relate_sessions(session_a, session_b):
    """Mark two sessions as related to each other in the chain index.

    Adds each session ID to the other's 'related' list (bidirectional).
    Duplicate entries are silently ignored.

    Args:
        session_a (str): First session identifier.
        session_b (str): Second session identifier.

    Returns:
        bool: True on success; False when either ID is falsy or both are equal.
    """
    if not session_a or not session_b or session_a == session_b:
        return False

    index = read_chain_index()
    index = ensure_session_entry(index, session_a)
    index = ensure_session_entry(index, session_b)

    if session_b not in index["sessions"][session_a]["related"]:
        index["sessions"][session_a]["related"].append(session_b)
    if session_a not in index["sessions"][session_b]["related"]:
        index["sessions"][session_b]["related"].append(session_a)

    write_chain_index(index)
    log_event(f"[OK] Related: {session_a} <-> {session_b}")
    return True


# =============================================================================
# CHAIN CONTEXT - Get related sessions for context continuity
# =============================================================================

def get_chain_context(session_id, max_ancestors=5, max_related=5):
    """Build a chain context summary for a session.

    Walks up the parent chain (up to max_ancestors ancestors), collects
    directly related sessions (up to max_related), and finds sessions that
    share tags with the current session.  Also enriches ancestor entries with
    rich summary text from session-summary.json when available.

    Used by 3-level-flow.py to provide context continuity at session start.

    Args:
        session_id (str): Target session identifier.
        max_ancestors (int): Maximum number of ancestor sessions to walk.
                             Defaults to 5.
        max_related (int): Maximum number of related sessions to include.
                           Defaults to 5.

    Returns:
        dict or None: Context dict with 'ancestor_chain', 'related_sessions',
                      'tag_related', and session metadata fields.  Returns None
                      when session_id is not found in the chain index.
    """
    index = read_chain_index()

    if session_id not in index["sessions"]:
        return None

    entry = index["sessions"][session_id]
    result = {
        "session_id": session_id,
        "parent": entry.get("parent"),
        "children": entry.get("children", []),
        "tags": entry.get("tags", []),
        "project": entry.get("project"),
        "ancestor_chain": [],
        "related_sessions": [],
        "tag_related": []
    }

    # Walk up the parent chain
    current = entry.get("parent")
    depth = 0
    while current and depth < max_ancestors:
        if current not in index["sessions"]:
            break
        ancestor = index["sessions"][current]
        # Try to read rich summary from session-summary.json
        rich_summary = _read_session_summary_text(current)
        result["ancestor_chain"].append({
            "session_id": current,
            "summary": rich_summary or ancestor.get("summary") or ancestor.get("last_prompt", "")[:80],
            "tags": ancestor.get("tags", []),
            "project": ancestor.get("project"),
            "skill": ancestor.get("skill"),
            "task_type": ancestor.get("task_type")
        })
        current = ancestor.get("parent")
        depth += 1

    # Get directly related sessions
    for rel_id in entry.get("related", [])[:max_related]:
        if rel_id in index["sessions"]:
            rel = index["sessions"][rel_id]
            result["related_sessions"].append({
                "session_id": rel_id,
                "summary": rel.get("summary") or rel.get("last_prompt", "")[:80],
                "tags": rel.get("tags", []),
                "project": rel.get("project")
            })

    # Find sessions with overlapping tags
    session_tags = set(entry.get("tags", []))
    if session_tags:
        tag_matches = {}
        for tag in session_tags:
            for sid in index["tag_index"].get(tag, []):
                if sid != session_id and sid not in [r["session_id"] for r in result["related_sessions"]]:
                    if sid not in tag_matches:
                        tag_matches[sid] = {"session_id": sid, "shared_tags": []}
                    tag_matches[sid]["shared_tags"].append(tag)

        # Sort by number of shared tags (most relevant first)
        sorted_matches = sorted(tag_matches.values(),
                                key=lambda x: len(x["shared_tags"]), reverse=True)

        for match in sorted_matches[:max_related]:
            sid = match["session_id"]
            if sid in index["sessions"]:
                sess = index["sessions"][sid]
                match["summary"] = sess.get("summary") or sess.get("last_prompt", "")[:80]
                match["project"] = sess.get("project")
            result["tag_related"].append(match)

    return result


def get_full_chain(session_id):
    """Get the complete ancestor and descendant chain for a session.

    Walks up the parent chain (all ancestors) and walks down the children
    tree via BFS (all descendants).  Visited set prevents infinite loops in
    malformed indexes.

    Args:
        session_id (str): Target session identifier.

    Returns:
        dict or None: Dict with 'ancestors' (oldest first), 'current', and
                      'descendants' (BFS order).  Returns None when session_id
                      is not in the chain index.
    """
    index = read_chain_index()
    if session_id not in index["sessions"]:
        return None

    chain = {"ancestors": [], "current": session_id, "descendants": []}

    # Walk up
    current = index["sessions"][session_id].get("parent")
    while current and current in index["sessions"]:
        chain["ancestors"].insert(0, current)
        current = index["sessions"][current].get("parent")

    # Walk down (BFS)
    queue = list(index["sessions"][session_id].get("children", []))
    visited = {session_id}
    while queue:
        sid = queue.pop(0)
        if sid in visited or sid not in index["sessions"]:
            continue
        visited.add(sid)
        chain["descendants"].append(sid)
        queue.extend(index["sessions"][sid].get("children", []))

    return chain


def search_by_tag(tag):
    """Search for sessions that have the given tag in the chain index.

    Args:
        tag (str): Tag to search for (normalised to lowercase automatically).

    Returns:
        list: List of dicts each containing 'session_id', 'summary', 'tags',
              'project', 'task_type', and 'created_at' for matched sessions.
              Empty list when no sessions have the tag.
    """
    index = read_chain_index()
    tag = tag.strip().lower()
    session_ids = index["tag_index"].get(tag, [])
    results = []
    for sid in session_ids:
        if sid in index["sessions"]:
            entry = index["sessions"][sid]
            results.append({
                "session_id": sid,
                "summary": entry.get("summary") or entry.get("last_prompt", "")[:80],
                "tags": entry.get("tags", []),
                "project": entry.get("project"),
                "task_type": entry.get("task_type"),
                "created_at": entry.get("created_at")
            })
    return results


def format_chain_context(ctx):
    """Format a chain context dict into a human-readable multi-line string.

    Produces a '[SESSION CHAIN]' section showing parent, ancestors (with
    project, tags, and summary), directly related sessions, tag-related
    sessions, current tags, and project.

    Args:
        ctx (dict or None): Chain context from get_chain_context(), or None.

    Returns:
        str: Formatted multi-line string ready to print to hook stdout.
             Returns a 'No chain data available' message when ctx is falsy.
    """
    if not ctx:
        return "[CHAIN] No chain data available"

    lines = []
    lines.append("[SESSION CHAIN]")

    # Parent
    if ctx.get("parent"):
        lines.append(f"   Parent: {ctx['parent']}")

    # Ancestors
    if ctx.get("ancestor_chain"):
        lines.append("   Ancestors:")
        for anc in ctx["ancestor_chain"]:
            summary = anc.get("summary", "")[:60]
            tags = ", ".join(anc.get("tags", [])[:3])
            proj = anc.get("project", "")
            line = f"      {anc['session_id']}"
            if proj:
                line += f" [{proj}]"
            if tags:
                line += f" ({tags})"
            if summary:
                line += f" - {summary}"
            lines.append(line)

    # Related by explicit link
    if ctx.get("related_sessions"):
        lines.append("   Related:")
        for rel in ctx["related_sessions"]:
            summary = rel.get("summary", "")[:60]
            lines.append(f"      {rel['session_id']} - {summary}")

    # Related by tags
    if ctx.get("tag_related"):
        lines.append("   Tag-related:")
        for tr in ctx["tag_related"][:3]:
            shared = ", ".join(tr.get("shared_tags", []))
            summary = tr.get("summary", "")[:50]
            lines.append(f"      {tr['session_id']} (shared: {shared}) - {summary}")

    # Current tags
    if ctx.get("tags"):
        lines.append(f"   Tags: {', '.join(ctx['tags'])}")

    if ctx.get("project"):
        lines.append(f"   Project: {ctx['project']}")

    if len(lines) == 1:
        lines.append("   (First session - no chain history)")

    return "\n".join(lines)


# =============================================================================
# AUTO-TAG EXTRACTION
# =============================================================================

def extract_tags_from_prompt(prompt, task_type='', skill='', project_cwd=''):
    """Auto-extract relevant tags from a user prompt and session context.

    Derives tags from four sources:
      1. task_type  -> normalised to lowercase kebab-case.
      2. skill      -> added as-is unless it is 'adaptive-skill-intelligence'.
      3. project_cwd -> extracts the project directory name from the path.
      4. prompt keywords -> scans for known tech topics (spring boot, docker, etc.).

    Args:
        prompt (str): Raw user message for keyword extraction.
        task_type (str): Classified task type (e.g. 'Backend').
        skill (str): Primary skill or agent selected for the session.
        project_cwd (str): Working directory path to extract the project name from.

    Returns:
        list: Deduplicated list of lowercase tag strings.
    """
    tags = []

    # From task type
    if task_type:
        tags.append(task_type.lower().replace('/', '-').replace(' ', '-'))

    # From skill
    if skill and skill != 'adaptive-skill-intelligence':
        tags.append(skill.lower())

    # From project directory (extract project name)
    if project_cwd:
        parts = Path(project_cwd).parts
        for part in reversed(parts):
            if part.startswith('techdeveloper-') or part.startswith('surgricalswale-') or part.startswith('lovepoet-'):
                tags.append(part.lower())
                break
            elif part in ('techdeveloper', 'surgricalswale', 'lovepoet'):
                tags.append(part.lower())
                break

    # From prompt keywords (common tech topics)
    prompt_lower = prompt.lower()
    tech_keywords = {
        'spring boot': 'spring-boot',
        'docker': 'docker',
        'kubernetes': 'kubernetes',
        'k8s': 'kubernetes',
        'jenkins': 'jenkins',
        'angular': 'angular',
        'react': 'react',
        'mongodb': 'mongodb',
        'postgresql': 'postgresql',
        'redis': 'redis',
        'elasticsearch': 'elasticsearch',
        'eureka': 'eureka',
        'config server': 'config-server',
        'gateway': 'gateway',
        'auth': 'authentication',
        'blog': 'blog',
        'scheduler': 'scheduler',
        'sitemap': 'sitemap',
        'claude.md': 'claude-md',
        'memory system': 'memory-system',
        'hook': 'hooks',
        'session': 'session-management',
        'skill': 'skill-management',
        'agent': 'agent-management',
        'python': 'python',
        'java': 'java',
        'kotlin': 'kotlin',
        'swift': 'swift',
        'css': 'css',
        'seo': 'seo',
        'network policy': 'network-policy',
        'deployment': 'deployment',
        'ci/cd': 'cicd',
        'pipeline': 'pipeline',
    }

    for keyword, tag in tech_keywords.items():
        if keyword in prompt_lower and tag not in tags:
            tags.append(tag)

    # Deduplicate and clean
    seen = set()
    clean_tags = []
    for t in tags:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            clean_tags.append(t)

    return clean_tags


# =============================================================================
# AUTO-RELATE by shared tags
# =============================================================================

def auto_relate_by_tags(session_id, min_shared_tags=2):
    """
    Automatically relate sessions that share 2+ tags.
    Called after tagging a session. Creates bidirectional links.
    """
    index = read_chain_index()
    if session_id not in index["sessions"]:
        return

    my_tags = set(index["sessions"][session_id].get("tags", []))
    if len(my_tags) < min_shared_tags:
        return

    my_related = set(index["sessions"][session_id].get("related", []))
    new_relations = 0

    # Find sessions with overlapping tags
    candidate_sessions = set()
    for tag in my_tags:
        for sid in index["tag_index"].get(tag, []):
            if sid != session_id and sid not in my_related:
                candidate_sessions.add(sid)

    for sid in candidate_sessions:
        if sid not in index["sessions"]:
            continue
        their_tags = set(index["sessions"][sid].get("tags", []))
        shared = my_tags & their_tags
        if len(shared) >= min_shared_tags:
            # Relate them
            if sid not in index["sessions"][session_id].get("related", []):
                index["sessions"][session_id].setdefault("related", []).append(sid)
            if session_id not in index["sessions"][sid].get("related", []):
                index["sessions"][sid].setdefault("related", []).append(session_id)
            new_relations += 1

    if new_relations > 0:
        write_chain_index(index)
        log_event(f"[OK] Auto-related {session_id}: {new_relations} new relations by shared tags")


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for session-chain-manager.py.

    Dispatches to one of the following sub-commands:
      link    - Link a child session to its parent (called on /clear).
      tag     - Add tags and metadata to a session.
      relate  - Mark two sessions as related (bidirectional).
      context - Print the chain context for a session.
      chain   - Print the complete ancestor + descendant chain.
      search  - Search sessions by tag.

    Exits 0 on success or 1 on any error.
    """
    parser = argparse.ArgumentParser(description='Session Chain Manager v1.0.0')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # link
    link_parser = subparsers.add_parser('link', help='Link child session to parent')
    link_parser.add_argument('--child', required=True, help='Child session ID')
    link_parser.add_argument('--parent', required=True, help='Parent session ID')

    # tag
    tag_parser = subparsers.add_parser('tag', help='Add tags to session')
    tag_parser.add_argument('--session', required=True, help='Session ID')
    tag_parser.add_argument('--tags', required=True, help='Comma-separated tags')
    tag_parser.add_argument('--project', help='Project name')
    tag_parser.add_argument('--skill', help='Skill used')
    tag_parser.add_argument('--task-type', help='Task type')
    tag_parser.add_argument('--summary', help='Session summary')
    tag_parser.add_argument('--prompt', help='Last prompt')

    # relate
    relate_parser = subparsers.add_parser('relate', help='Mark sessions as related')
    relate_parser.add_argument('--session', required=True, help='First session ID')
    relate_parser.add_argument('--related', required=True, help='Second session ID')

    # context
    ctx_parser = subparsers.add_parser('context', help='Get chain context')
    ctx_parser.add_argument('--session', required=True, help='Session ID')
    ctx_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # chain
    chain_parser = subparsers.add_parser('chain', help='Get full chain')
    chain_parser.add_argument('--session', required=True, help='Session ID')

    # search
    search_parser = subparsers.add_parser('search', help='Search by tag')
    search_parser.add_argument('--tag', required=True, help='Tag to search')

    # auto-tag (extract tags from prompt and add)
    autotag_parser = subparsers.add_parser('auto-tag', help='Auto-extract and add tags')
    autotag_parser.add_argument('--session', required=True, help='Session ID')
    autotag_parser.add_argument('--prompt', default='', help='User prompt')
    autotag_parser.add_argument('--task-type', default='', help='Task type')
    autotag_parser.add_argument('--skill', default='', help='Skill name')
    autotag_parser.add_argument('--cwd', default='', help='Current working directory')
    autotag_parser.add_argument('--project', default='', help='Project name')
    autotag_parser.add_argument('--summary', default='', help='Session summary')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == 'link':
        ok = link_sessions(args.child, args.parent)
        if ok:
            print(f"[OK] Linked {args.child} -> parent: {args.parent}")
        else:
            print(f"[ERROR] Failed to link sessions")
            sys.exit(1)

    elif args.command == 'tag':
        tags = [t.strip() for t in args.tags.split(',') if t.strip()]
        ok = tag_session(
            args.session, tags,
            project=args.project,
            skill=args.skill,
            task_type=args.task_type,
            summary=args.summary,
            last_prompt=args.prompt
        )
        if ok:
            print(f"[OK] Tagged {args.session}: {tags}")
            auto_relate_by_tags(args.session)
        else:
            print(f"[ERROR] Failed to tag session")
            sys.exit(1)

    elif args.command == 'relate':
        ok = relate_sessions(args.session, args.related)
        if ok:
            print(f"[OK] Related {args.session} <-> {args.related}")
        else:
            print(f"[ERROR] Failed to relate sessions")
            sys.exit(1)

    elif args.command == 'context':
        ctx = get_chain_context(args.session)
        if args.json:
            print(json.dumps(ctx, indent=2))
        else:
            print(format_chain_context(ctx))

    elif args.command == 'chain':
        chain = get_full_chain(args.session)
        if chain:
            print(json.dumps(chain, indent=2))
        else:
            print(f"[WARN] No chain data for {args.session}")

    elif args.command == 'search':
        results = search_by_tag(args.tag)
        if results:
            print(f"[OK] Found {len(results)} sessions with tag '{args.tag}':")
            for r in results:
                summary = r.get('summary', '')[:60]
                print(f"   {r['session_id']} - {summary}")
        else:
            print(f"[INFO] No sessions found with tag '{args.tag}'")

    elif args.command == 'auto-tag':
        tags = extract_tags_from_prompt(
            args.prompt, args.task_type, args.skill, args.cwd
        )
        if tags:
            ok = tag_session(
                args.session, tags,
                project=args.project,
                skill=args.skill,
                task_type=args.task_type,
                summary=args.summary,
                last_prompt=args.prompt
            )
            if ok:
                print(f"[OK] Auto-tagged {args.session}: {tags}")
                auto_relate_by_tags(args.session)
            else:
                print(f"[ERROR] Failed to auto-tag")
                sys.exit(1)
        else:
            print(f"[INFO] No tags extracted from prompt")

    sys.exit(0)


if __name__ == '__main__':
    main()
