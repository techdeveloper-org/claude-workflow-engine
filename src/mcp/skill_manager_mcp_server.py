"""
Skill Manager MCP Server - Full skill lifecycle management.

Consolidates skill_manager.py (793), skill_selection_criteria.py (384),
skill_agent_loader.py (359) = 1,536 LOC into a single FastMCP server.

Lifecycle: Load -> Validate -> Rank -> Detect Conflicts -> Select

Backend: Direct file I/O from ~/.claude/skills/ and ~/.claude/agents/
Transport: stdio

Tools (8):
  skill_load_all, skill_load, skill_search, skill_validate,
  skill_rank, skill_detect_conflicts, agent_load_all, agent_load
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler

mcp = FastMCP(
    "skill-manager",
    instructions="Skill & agent lifecycle: load, validate, rank, detect conflicts"
)

SKILLS_DIR = Path.home() / ".claude" / "skills"
AGENTS_DIR = Path.home() / ".claude" / "agents"


def _extract_metadata(content: str) -> dict:
    """Extract metadata from SKILL.md/agent.md frontmatter or content."""
    meta = {}
    # Try YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip().lower()] = val.strip()

    # Extract capabilities from content
    caps = re.findall(r"-\s+\*\*Capabilities?\*\*\s*:\s*(.+)", content, re.IGNORECASE)
    if caps:
        meta["capabilities"] = [c.strip() for c in caps[0].split(",")]

    # Extract trigger patterns
    triggers = re.findall(r"TRIGGER\s+when\s*:\s*(.+)", content, re.IGNORECASE)
    if triggers:
        meta["triggers"] = [t.strip() for t in triggers]

    # Extract plain key: value lines (exclusive, exclusive_domain, conflicts_with)
    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("#") or not line_s:
            continue
        if ":" in line_s and not line_s.startswith("-") and not line_s.startswith("*"):
            key, val = line_s.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "exclusive" and val.lower() in ("true", "yes"):
                meta["exclusive"] = True
            elif key == "exclusive_domain":
                meta["exclusive_domain"] = val
            elif key == "conflicts_with":
                meta["conflicts_with"] = [c.strip() for c in val.split(",")]

    return meta


def _load_skill_file(skill_name: str) -> Optional[tuple]:
    """Load skill content + path. Returns (content, path) or (None, None)."""
    # Try direct path
    for fname in ["SKILL.md", "skill.md"]:
        fp = SKILLS_DIR / skill_name / fname
        if fp.exists():
            return fp.read_text(encoding="utf-8", errors="ignore"), str(fp)
    # Try subdirectory pattern: skills/*/skill_name/SKILL.md
    for fp in SKILLS_DIR.glob(f"*/{skill_name}/SKILL.md"):
        return fp.read_text(encoding="utf-8", errors="ignore"), str(fp)
    return None, None


def _load_agent_file(agent_name: str) -> Optional[tuple]:
    """Load agent content + path. Returns (content, path) or (None, None)."""
    fp = AGENTS_DIR / agent_name / "agent.md"
    if fp.exists():
        return fp.read_text(encoding="utf-8", errors="ignore"), str(fp)
    return None, None


# =============================================================================
# TOOL 1: LOAD ALL SKILLS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_load_all() -> str:
    """Load all available skills from ~/.claude/skills/ with metadata.

    Returns list of all skills with name, path, size, and extracted metadata.
    """
    try:
        skills = []
        if not SKILLS_DIR.exists():
            return to_json({"success": True, "skills": [], "count": 0})

        # Find all SKILL.md files
        for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
            name = skill_file.parent.name
            try:
                content = skill_file.read_text(encoding="utf-8", errors="ignore")
                meta = _extract_metadata(content)
                skills.append({
                    "name": name,
                    "path": str(skill_file),
                    "size_bytes": skill_file.stat().st_size,
                    "capabilities": meta.get("capabilities", []),
                    "triggers": meta.get("triggers", []),
                    "description": meta.get("description", ""),
                })
            except Exception:
                skills.append({"name": name, "path": str(skill_file), "error": "load_failed"})

        return to_json({"success": True, "skills": skills, "count": len(skills)})
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 2: LOAD SINGLE SKILL
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_load(skill_name: str) -> str:
    """Load full SKILL.md content for a specific skill.

    Args:
        skill_name: Skill name (e.g., 'java-spring-boot-microservices')
    """
    try:
        content, path = _load_skill_file(skill_name)
        if content is None:
            # List available skills for suggestion
            available = []
            if SKILLS_DIR.exists():
                available = [f.parent.name for f in SKILLS_DIR.rglob("SKILL.md")][:10]
            return to_json({
                "success": False,
                "error": f"Skill not found: {skill_name}",
                "available": available
            })

        meta = _extract_metadata(content)
        return to_json({
            "success": True,
            "name": skill_name,
            "path": path,
            "content": content,
            "size_bytes": len(content),
            "metadata": meta,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 3: SEARCH SKILLS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_search(query: str = "", tags: str = "", project_type: str = "") -> str:
    """Search skills by keyword, tags, or project type.

    Args:
        query: Keyword to search in skill names and content
        tags: Comma-separated tags to filter by
        project_type: Filter by project type (python, java, typescript, etc.)
    """
    try:
        if not SKILLS_DIR.exists():
            return to_json({"success": True, "results": [], "count": 0})

        results = []
        query_lower = query.lower()
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()] if tags else []

        for skill_file in SKILLS_DIR.rglob("SKILL.md"):
            name = skill_file.parent.name
            name_lower = name.lower()

            try:
                content = skill_file.read_text(encoding="utf-8", errors="ignore")
                content_lower = content.lower()

                # Query match
                if query_lower and query_lower not in name_lower and query_lower not in content_lower:
                    continue

                # Tag match
                if tag_list:
                    matched_tags = [t for t in tag_list if t in name_lower or t in content_lower]
                    if not matched_tags:
                        continue

                # Project type match
                if project_type:
                    pt_lower = project_type.lower()
                    if pt_lower not in name_lower and pt_lower not in content_lower:
                        continue

                meta = _extract_metadata(content)
                results.append({
                    "name": name,
                    "path": str(skill_file),
                    "capabilities": meta.get("capabilities", []),
                    "description": meta.get("description", ""),
                    "relevance": (
                        (3 if query_lower and query_lower in name_lower else 0) +
                        (1 if query_lower and query_lower in content_lower else 0)
                    ),
                })
            except Exception:
                continue

        results.sort(key=lambda r: r.get("relevance", 0), reverse=True)

        return to_json({
            "success": True,
            "results": results[:20],
            "count": len(results),
            "query": query,
            "tags": tag_list,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 4: VALIDATE SKILL
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_validate(skill_name: str, required_capabilities: str = "") -> str:
    """Validate whether a skill satisfies required capabilities.

    Args:
        skill_name: Skill to validate
        required_capabilities: Comma-separated required capabilities (e.g., 'orm,jwt,rest_api')
    """
    try:
        content, _ = _load_skill_file(skill_name)
        if content is None:
            return to_json({"success": False, "error": f"Skill not found: {skill_name}"})

        meta = _extract_metadata(content)
        skill_caps = {c.lower() for c in meta.get("capabilities", [])}
        required = [c.strip().lower() for c in required_capabilities.split(",") if c.strip()]

        if not required:
            return to_json({"success": True, "valid": True, "message": "No requirements specified"})

        missing = [c for c in required if c not in skill_caps]
        valid = len(missing) == 0

        return to_json({
            "success": True,
            "valid": valid,
            "skill": skill_name,
            "skill_capabilities": sorted(skill_caps),
            "required": required,
            "missing": missing,
            "message": "OK" if valid else f"Missing: {', '.join(missing)}",
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 5: RANK SKILLS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_rank(
    task_type: str = "",
    project_type: str = "",
    complexity: int = 5,
    required_capabilities: str = ""
) -> str:
    """Rank available skills by relevance to task requirements.

    Scoring: name match (3pts) + project type match (2pts) +
    capability coverage (1pt each) + complexity alignment (1pt).

    Args:
        task_type: Task type (e.g., 'Implementation', 'Bug Fix')
        project_type: Language (python, java, etc.)
        complexity: Task complexity 1-10
        required_capabilities: Comma-separated required capabilities
    """
    try:
        if not SKILLS_DIR.exists():
            return to_json({"success": True, "ranked": [], "count": 0})

        required = [c.strip().lower() for c in required_capabilities.split(",") if c.strip()]
        ranked = []

        for skill_file in SKILLS_DIR.rglob("SKILL.md"):
            name = skill_file.parent.name
            try:
                content = skill_file.read_text(encoding="utf-8", errors="ignore")
                content_lower = content.lower()
                meta = _extract_metadata(content)
                caps = {c.lower() for c in meta.get("capabilities", [])}

                score = 0
                reasons = []

                # Project type match
                if project_type and project_type.lower() in name.lower():
                    score += 3
                    reasons.append(f"name matches {project_type}")
                elif project_type and project_type.lower() in content_lower:
                    score += 2
                    reasons.append(f"content mentions {project_type}")

                # Task type match
                if task_type and task_type.lower() in content_lower:
                    score += 1
                    reasons.append(f"supports {task_type}")

                # Capability coverage
                if required:
                    covered = sum(1 for c in required if c in caps)
                    score += covered
                    if covered > 0:
                        reasons.append(f"{covered}/{len(required)} capabilities")

                if score > 0:
                    ranked.append({
                        "name": name,
                        "score": score,
                        "reasons": reasons,
                        "capabilities": sorted(caps)[:5],
                    })
            except Exception:
                continue

        ranked.sort(key=lambda r: r["score"], reverse=True)

        return to_json({
            "success": True,
            "ranked": ranked[:10],
            "count": len(ranked),
            "criteria": {
                "task_type": task_type,
                "project_type": project_type,
                "complexity": complexity,
            },
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 6: DETECT CONFLICTS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def skill_detect_conflicts(skill_names: str) -> str:
    """Detect conflicts between selected skills.

    Checks: exclusive flag, explicit conflicts_with lists, exclusive domain overlap.

    Args:
        skill_names: Comma-separated skill names to check
    """
    try:
        names = [n.strip() for n in skill_names.split(",") if n.strip()]
        skills = []

        for name in names:
            content, _ = _load_skill_file(name)
            if content:
                meta = _extract_metadata(content)
                meta["name"] = name
                skills.append(meta)

        conflicts = []
        for i, s1 in enumerate(skills):
            for s2 in skills[i + 1:]:
                n1 = s1.get("name", "")
                n2 = s2.get("name", "")

                # Check exclusive flag
                if s1.get("exclusive") or s2.get("exclusive"):
                    conflicts.append({
                        "skill1": n1, "skill2": n2,
                        "reason": f"{'  ' + n1 if s1.get('exclusive') else n2} is exclusive"
                    })
                    continue

                # Check conflicts_with
                c1 = [c.lower() for c in (s1.get("conflicts_with") or [])]
                c2 = [c.lower() for c in (s2.get("conflicts_with") or [])]
                if n2.lower() in c1 or n1.lower() in c2:
                    conflicts.append({
                        "skill1": n1, "skill2": n2,
                        "reason": "Explicit conflict declared"
                    })
                    continue

                # Check exclusive domain
                d1 = (s1.get("exclusive_domain") or "").lower()
                d2 = (s2.get("exclusive_domain") or "").lower()
                if d1 and d2 and d1 == d2:
                    conflicts.append({
                        "skill1": n1, "skill2": n2,
                        "reason": f"Same exclusive domain: {d1}"
                    })

        return to_json({
            "success": True,
            "skills_checked": names,
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "compatible": len(conflicts) == 0,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 7 & 8: AGENT TOOLS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def agent_load_all() -> str:
    """Load all available agents from ~/.claude/agents/ with metadata."""
    try:
        agents = []
        if not AGENTS_DIR.exists():
            return to_json({"success": True, "agents": [], "count": 0})

        for agent_dir in sorted(AGENTS_DIR.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_file = agent_dir / "agent.md"
            if not agent_file.exists():
                continue
            name = agent_dir.name
            try:
                content = agent_file.read_text(encoding="utf-8", errors="ignore")
                meta = _extract_metadata(content)
                agents.append({
                    "name": name,
                    "path": str(agent_file),
                    "size_bytes": agent_file.stat().st_size,
                    "description": meta.get("description", ""),
                })
            except Exception:
                agents.append({"name": name, "error": "load_failed"})

        return to_json({"success": True, "agents": agents, "count": len(agents)})
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


@mcp.tool()
@mcp_tool_handler
def agent_load(agent_name: str) -> str:
    """Load full agent.md content for a specific agent.

    Args:
        agent_name: Agent name (e.g., 'orchestrator-agent')
    """
    try:
        content, path = _load_agent_file(agent_name)
        if content is None:
            available = []
            if AGENTS_DIR.exists():
                available = [d.name for d in AGENTS_DIR.iterdir()
                           if d.is_dir() and (d / "agent.md").exists()][:10]
            return to_json({
                "success": False,
                "error": f"Agent not found: {agent_name}",
                "available": available
            })

        meta = _extract_metadata(content)
        return to_json({
            "success": True,
            "name": agent_name,
            "path": path,
            "content": content,
            "size_bytes": len(content),
            "metadata": meta,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
