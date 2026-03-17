"""
Standards Loader MCP Server - Project type detection + standards loading.

Consolidates standard_selector.py (706), standards_integration.py (620),
standards_schema.py (354), standards-loader.py (~200) = 1,880 LOC into
a single FastMCP server.

Workflow:
1. Detect project type from marker files (setup.py, pom.xml, package.json, etc.)
2. Detect framework within project type (Flask, Spring Boot, React, etc.)
3. Load standards from 4 sources with priority ordering:
   custom(4) > team(3) > framework(2) > language(1)
4. Detect and resolve conflicts (higher priority wins)
5. Return merged rules for pipeline enforcement

Backend: Direct file I/O + glob patterns
Transport: stdio

Tools (6):
  detect_project_type, detect_framework, load_standards,
  resolve_standard_conflicts, get_active_standards, list_available_standards
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler

mcp = FastMCP(
    "standards-loader",
    instructions="Project type detection and coding standards loading with conflict resolution"
)

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = _PROJECT_ROOT / "policies"
ARCH_STANDARDS_DIR = _PROJECT_ROOT / "scripts" / "architecture" / "02-standards-system"
TEAM_STANDARDS_DIR = Path.home() / ".claude" / "policies" / "02-standards-system"
TEAM_STANDARDS_ALT = Path.home() / ".claude" / "standards"

# Priority constants
PRIORITY_CUSTOM = 4
PRIORITY_TEAM = 3
PRIORITY_FRAMEWORK = 2
PRIORITY_LANGUAGE = 1


# =============================================================================
# TOOL 1: DETECT PROJECT TYPE
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def detect_project_type(project_path: str = ".") -> str:
    """Detect the primary programming language of a project.

    Checks marker files: setup.py, pom.xml, package.json, tsconfig.json,
    go.mod, Cargo.toml, *.csproj

    Args:
        project_path: Path to project root directory
    """
    try:
        root = Path(project_path).resolve()

        if not root.exists():
            return to_json({"success": False, "error": f"Path not found: {project_path}"})

        # Python
        if any((root / f).exists() for f in ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile"]):
            lang = "python"
        # Java
        elif any((root / f).exists() for f in ["pom.xml", "build.gradle", "build.gradle.kts"]):
            lang = "java"
        # TypeScript (check before JS)
        elif (root / "tsconfig.json").exists():
            lang = "typescript"
        # JavaScript
        elif (root / "package.json").exists():
            lang = "javascript"
        # Go
        elif (root / "go.mod").exists():
            lang = "go"
        # Rust
        elif (root / "Cargo.toml").exists():
            lang = "rust"
        # C#
        elif list(root.glob("**/*.csproj"))[:1] or list(root.glob("**/*.sln"))[:1]:
            lang = "csharp"
        # Swift
        elif (root / "Package.swift").exists() or list(root.glob("**/*.xcodeproj"))[:1]:
            lang = "swift"
        # Kotlin
        elif list(root.glob("**/*.kt"))[:1]:
            lang = "kotlin"
        else:
            lang = "unknown"

        return to_json({
            "success": True,
            "project_type": lang,
            "project_path": str(root),
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 2: DETECT FRAMEWORK
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def detect_framework(project_path: str = ".", project_type: str = "") -> str:
    """Detect the primary framework within a project type.

    Args:
        project_path: Path to project root
        project_type: Language (auto-detected if empty)
    """
    try:
        root = Path(project_path).resolve()

        if not project_type:
            result = json.loads(detect_project_type(project_path))
            project_type = result.get("project_type", "unknown")

        framework = "unknown"

        if project_type == "python":
            framework = _detect_python_fw(root)
        elif project_type == "java":
            framework = _detect_java_fw(root)
        elif project_type in ("javascript", "typescript"):
            framework = _detect_js_fw(root)
        elif project_type == "swift":
            framework = "swiftui" if list(root.rglob("*View.swift"))[:1] else "uikit"

        return to_json({
            "success": True,
            "project_type": project_type,
            "framework": framework,
            "project_path": str(root),
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


def _detect_python_fw(root: Path) -> str:
    if (root / "manage.py").exists():
        return "django"
    # Check requirements.txt or pyproject.toml for framework hints
    for dep_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
        fp = root / dep_file
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore").lower()
                if "flask" in content:
                    return "flask"
                if "fastapi" in content:
                    return "fastapi"
                if "django" in content:
                    return "django"
                if "langgraph" in content or "langchain" in content:
                    return "langgraph"
            except Exception:
                pass
    return "unknown"


def _detect_java_fw(root: Path) -> str:
    for build_file in ["pom.xml", "build.gradle", "build.gradle.kts"]:
        fp = root / build_file
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore").lower()
                if "spring-boot" in content or "spring boot" in content:
                    return "spring-boot"
                if "spring" in content:
                    return "spring"
                if "quarkus" in content:
                    return "quarkus"
                if "micronaut" in content:
                    return "micronaut"
            except Exception:
                pass
    return "unknown"


def _detect_js_fw(root: Path) -> str:
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "react" in deps or "react-dom" in deps:
                return "react"
            if "@angular/core" in deps:
                return "angular"
            if "vue" in deps:
                return "vue"
            if "express" in deps:
                return "express"
            if "nestjs" in deps or "@nestjs/core" in deps:
                return "nestjs"
        except Exception:
            pass
    return "unknown"


# =============================================================================
# TOOL 3: LOAD STANDARDS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def load_standards(project_path: str = ".") -> str:
    """Load all applicable standards for a project with full traceability.

    Detection + loading pipeline:
    1. detect_project_type -> detect_framework
    2. Load custom standards (project-local, priority=4)
    3. Load team standards (global, priority=3)
    4. Load framework standards (built-in, priority=2)
    5. Load language standards (built-in, priority=1)
    6. Detect conflicts + resolve (higher priority wins)

    Args:
        project_path: Path to project root
    """
    try:
        root = Path(project_path).resolve()

        # Detect project
        pt_result = json.loads(detect_project_type(str(root)))
        project_type = pt_result.get("project_type", "unknown")

        fw_result = json.loads(detect_framework(str(root), project_type))
        framework = fw_result.get("framework", "unknown")

        all_standards = []
        traceability = {
            "project_type": project_type,
            "framework": framework,
            "sources_checked": [],
        }

        # 1. Custom standards (highest priority)
        custom = _load_from_dirs(
            [root / ".claude" / "standards", root / "standards"],
            "custom", PRIORITY_CUSTOM
        )
        all_standards.extend(custom)
        traceability["sources_checked"].append({
            "source": "custom", "priority": PRIORITY_CUSTOM, "loaded": len(custom)
        })

        # 2. Team standards
        team = _load_from_dirs(
            [TEAM_STANDARDS_DIR, TEAM_STANDARDS_ALT],
            "team", PRIORITY_TEAM
        )
        all_standards.extend(team)
        traceability["sources_checked"].append({
            "source": "team", "priority": PRIORITY_TEAM, "loaded": len(team)
        })

        # 3. Framework standards
        fw_standards = _load_framework_standards(project_type, framework)
        all_standards.extend(fw_standards)
        traceability["sources_checked"].append({
            "source": "framework", "priority": PRIORITY_FRAMEWORK, "loaded": len(fw_standards)
        })

        # 4. Language standards
        lang_standards = _load_language_standards(project_type)
        all_standards.extend(lang_standards)
        traceability["sources_checked"].append({
            "source": "language", "priority": PRIORITY_LANGUAGE, "loaded": len(lang_standards)
        })

        # 5. Detect conflicts
        conflicts = _detect_conflicts(all_standards)

        # 6. Resolve conflicts (higher priority wins)
        merged_rules = _resolve_conflicts(all_standards)

        return to_json({
            "success": True,
            "project_type": project_type,
            "framework": framework,
            "standards_loaded": len(all_standards),
            "standards_list": [
                {"id": s.get("id", ""), "source": s.get("source", ""),
                 "priority": s.get("priority", 0), "file": s.get("file", "")}
                for s in all_standards
            ],
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "merged_rules": merged_rules,
            "traceability": traceability,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


def _load_from_dirs(dirs, source, priority):
    """Load .md standard files from directories."""
    standards = []
    for d in dirs:
        if not d.exists():
            continue
        for md_file in sorted(d.rglob("*.md")):
            if md_file.name.lower() in ("readme.md", "changelog.md"):
                continue
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                standards.append({
                    "id": md_file.stem,
                    "source": source,
                    "priority": priority,
                    "file": str(md_file),
                    "content": content[:2000],  # First 2KB for rules extraction
                    "size_bytes": md_file.stat().st_size,
                    "rules": _extract_rules(content),
                })
            except Exception:
                continue
    return standards


def _load_framework_standards(project_type, framework):
    """Load built-in framework standards from architecture dir."""
    standards = []
    if framework == "unknown":
        return standards
    patterns = [
        f"{project_type}-{framework}-standards.md",
        f"{framework}-standards.md",
        f"{framework}/*.md",
    ]
    for pattern in patterns:
        for md_file in ARCH_STANDARDS_DIR.glob(pattern):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                standards.append({
                    "id": md_file.stem,
                    "source": "framework",
                    "priority": PRIORITY_FRAMEWORK,
                    "file": str(md_file),
                    "content": content[:2000],
                    "rules": _extract_rules(content),
                })
            except Exception:
                continue
    return standards


def _load_language_standards(project_type):
    """Load built-in language standards."""
    standards = []
    if project_type == "unknown":
        return standards
    patterns = [
        f"{project_type}-standards.md",
        f"common-standards-policy.md",
    ]
    for pattern in patterns:
        for md_file in ARCH_STANDARDS_DIR.glob(pattern):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                standards.append({
                    "id": md_file.stem,
                    "source": "language",
                    "priority": PRIORITY_LANGUAGE,
                    "file": str(md_file),
                    "content": content[:2000],
                    "rules": _extract_rules(content),
                })
            except Exception:
                continue
    # Also check policies dir
    policy_standards = POLICIES_DIR / "02-standards"
    if policy_standards.exists():
        for md_file in sorted(policy_standards.rglob("*.md")):
            if md_file.name.lower() == "readme.md":
                continue
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                standards.append({
                    "id": md_file.stem,
                    "source": "language",
                    "priority": PRIORITY_LANGUAGE,
                    "file": str(md_file),
                    "content": content[:2000],
                    "rules": _extract_rules(content),
                })
            except Exception:
                continue
    return standards


def _extract_rules(content: str) -> dict:
    """Extract rule-like key-value pairs from markdown content."""
    rules = {}
    import re
    # Match patterns like: - **rule_name**: value
    for match in re.finditer(r'-\s+\*\*(\w[\w\s-]*)\*\*\s*:\s*(.+)', content):
        key = match.group(1).strip().lower().replace(" ", "_").replace("-", "_")
        val = match.group(2).strip()
        rules[key] = val
    return rules


def _detect_conflicts(standards_list):
    """Detect conflicting rules between standards."""
    conflicts = []
    for i, std1 in enumerate(standards_list):
        rules1 = std1.get("rules", {})
        for std2 in standards_list[i + 1:]:
            rules2 = std2.get("rules", {})
            shared_keys = set(rules1.keys()) & set(rules2.keys())
            conflicting = [k for k in shared_keys if rules1[k] != rules2[k]]
            if conflicting:
                conflicts.append({
                    "standard1": std1.get("id", ""),
                    "standard2": std2.get("id", ""),
                    "conflicting_rules": conflicting,
                })
    return conflicts


def _resolve_conflicts(standards_list):
    """Resolve by applying lowest priority first, highest last (wins)."""
    sorted_stds = sorted(standards_list, key=lambda s: s.get("priority", 0))
    merged = {}
    for std in sorted_stds:
        rules = std.get("rules", {})
        for k, v in rules.items():
            merged[k] = v  # Later (higher priority) overwrites earlier
    return merged


# =============================================================================
# TOOL 4: RESOLVE CONFLICTS (standalone)
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def resolve_standard_conflicts(standards_json: str) -> str:
    """Resolve conflicts in a list of standards (higher priority wins).

    Args:
        standards_json: JSON array of standard objects with 'rules' and 'priority'
    """
    try:
        standards = json.loads(standards_json)
        conflicts = _detect_conflicts(standards)
        merged = _resolve_conflicts(standards)
        return to_json({
            "success": True,
            "conflicts": conflicts,
            "merged_rules": merged,
            "total_rules": len(merged),
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 5: GET ACTIVE STANDARDS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def get_active_standards(project_path: str = ".") -> str:
    """Get currently active standards summary for a project.

    Returns a lightweight summary without full content.

    Args:
        project_path: Path to project root
    """
    try:
        result = json.loads(load_standards(project_path))
        if not result.get("success"):
            return to_json(result)

        return to_json({
            "success": True,
            "project_type": result["project_type"],
            "framework": result["framework"],
            "total_loaded": result["standards_loaded"],
            "by_source": {
                s["source"]: s["loaded"]
                for s in result.get("traceability", {}).get("sources_checked", [])
            },
            "conflict_count": result["conflict_count"],
            "rule_count": len(result.get("merged_rules", {})),
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 6: LIST AVAILABLE STANDARDS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def list_available_standards(source: str = "all") -> str:
    """List all available standard files across all sources.

    Args:
        source: Filter by source - 'all', 'team', 'framework', 'language'
    """
    try:
        standards = []

        # Team standards
        if source in ("all", "team"):
            for d in [TEAM_STANDARDS_DIR, TEAM_STANDARDS_ALT]:
                if d.exists():
                    for f in sorted(d.rglob("*.md")):
                        if f.name.lower() != "readme.md":
                            standards.append({
                                "id": f.stem, "source": "team",
                                "priority": PRIORITY_TEAM, "file": str(f),
                                "size_kb": round(f.stat().st_size / 1024, 1),
                            })

        # Architecture standards
        if source in ("all", "framework", "language"):
            if ARCH_STANDARDS_DIR.exists():
                for f in sorted(ARCH_STANDARDS_DIR.rglob("*.md")):
                    if f.name.lower() != "readme.md":
                        standards.append({
                            "id": f.stem, "source": "architecture",
                            "priority": PRIORITY_FRAMEWORK, "file": str(f),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                        })

        # Policy standards
        if source in ("all", "language"):
            policy_dir = POLICIES_DIR / "02-standards"
            if policy_dir.exists():
                for f in sorted(policy_dir.rglob("*.md")):
                    if f.name.lower() != "readme.md":
                        standards.append({
                            "id": f.stem, "source": "policy",
                            "priority": PRIORITY_LANGUAGE, "file": str(f),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                        })

        return to_json({
            "success": True,
            "standards": standards,
            "count": len(standards),
            "source_filter": source,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# TOOL 7: RELOAD STANDARDS (invalidate cache on file changes)
# =============================================================================

# Standards cache with TTL
_standards_cache = {}
_cache_timestamp = 0
_CACHE_TTL = 300  # 5 minutes default
_file_watcher_active = False


def _get_watched_dirs():
    """Get list of directories to watch for standards changes."""
    dirs = []
    for d in [POLICIES_DIR, ARCH_STANDARDS_DIR, TEAM_STANDARDS_DIR, TEAM_STANDARDS_ALT]:
        if d.exists():
            dirs.append(d)
    return dirs


def _invalidate_cache():
    """Invalidate the standards cache."""
    global _standards_cache, _cache_timestamp
    _standards_cache = {}
    _cache_timestamp = 0


def _start_file_watcher():
    """Start watching standards directories for changes (if watchdog available)."""
    global _file_watcher_active
    if _file_watcher_active:
        return {"status": "already_running"}

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class StandardsChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith(".md"):
                    _invalidate_cache()

            def on_created(self, event):
                if event.src_path.endswith(".md"):
                    _invalidate_cache()

            def on_deleted(self, event):
                if event.src_path.endswith(".md"):
                    _invalidate_cache()

        observer = Observer()
        handler = StandardsChangeHandler()

        watched = []
        for watch_dir in _get_watched_dirs():
            observer.schedule(handler, str(watch_dir), recursive=True)
            watched.append(str(watch_dir))

        observer.daemon = True
        observer.start()
        _file_watcher_active = True

        return {"status": "started", "watching": watched}
    except ImportError:
        return {"status": "watchdog_not_installed", "fallback": "TTL-based cache (5 min)"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


@mcp.tool()
@mcp_tool_handler
def reload_standards(project_path: str = ".", start_watcher: bool = True) -> str:
    """Reload standards by invalidating cache and optionally starting file watcher.

    Invalidates the cached standards so next load_standards call fetches fresh data.
    Can also start a background file watcher (requires watchdog) that auto-invalidates
    cache when .md files in policies/ or standards/ directories change.

    Args:
        project_path: Path to project root
        start_watcher: If True, start file watcher for auto-reload
    """
    try:
        _invalidate_cache()

        watcher_status = {}
        if start_watcher:
            watcher_status = _start_file_watcher()

        # Reload standards immediately
        result = json.loads(load_standards(project_path))

        return to_json({
            "success": True,
            "reloaded": True,
            "standards_loaded": result.get("standards_loaded", 0),
            "project_type": result.get("project_type", "unknown"),
            "framework": result.get("framework", "unknown"),
            "watcher": watcher_status,
            "watched_dirs": [str(d) for d in _get_watched_dirs()],
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
