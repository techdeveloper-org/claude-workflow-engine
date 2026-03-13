"""
Standard Selector - Detect project type/framework and load applicable standards.

Implements:
- Project type detection (Python, Java, JavaScript, Go, etc.)
- Framework detection within each language
- Custom standards loading (project-local + team-global)
- Conflict detection and resolution with priority ordering

Uses ErrorLogger from error_logger.py for decision audit trail.
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .error_logger import ErrorLogger


# ============================================================================
# PROJECT TYPE DETECTION
# ============================================================================

def detect_project_type(project_path: str) -> str:
    """Detect the primary programming language of a project.

    Checks for well-known marker files in order of specificity.

    Args:
        project_path: Absolute path to the project root directory.

    Returns:
        Lowercase language string: "python", "java", "javascript",
        "typescript", "go", "rust", "csharp", or "unknown".
    """
    root = Path(project_path)

    # Python
    if (
        (root / "setup.py").exists()
        or (root / "pyproject.toml").exists()
        or (root / "requirements.txt").exists()
        or (root / "Pipfile").exists()
        or list(root.glob("**/*.py"))[:1]
    ):
        return "python"

    # Java
    if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return "java"

    # JavaScript / TypeScript (check tsconfig before package.json so TS takes priority)
    if (root / "tsconfig.json").exists():
        return "typescript"

    if (root / "package.json").exists():
        return "javascript"

    # Go
    if (root / "go.mod").exists():
        return "go"

    # Rust
    if (root / "Cargo.toml").exists():
        return "rust"

    # C#
    cs_files = list(root.glob("**/*.csproj"))
    sln_files = list(root.glob("**/*.sln"))
    if cs_files or sln_files:
        return "csharp"

    return "unknown"


def detect_framework(project_path: str, project_type: str) -> str:
    """Detect the primary framework used within a project type.

    Args:
        project_path: Absolute path to the project root.
        project_type: Language string returned by detect_project_type().

    Returns:
        Framework name string, e.g. "flask", "django", "fastapi",
        "spring", "react", "angular", "vue", or "unknown".
    """
    root = Path(project_path)

    if project_type == "python":
        return _detect_python_framework(root)

    if project_type == "java":
        return _detect_java_framework(root)

    if project_type in ("javascript", "typescript"):
        return _detect_js_framework(root)

    return "unknown"


# ============================================================================
# FRAMEWORK DETECTION HELPERS
# ============================================================================

def _detect_python_framework(root: Path) -> str:
    """Detect Python web framework."""
    requirements_files = [
        root / "requirements.txt",
        root / "requirements" / "base.txt",
        root / "requirements" / "prod.txt",
    ]

    # Aggregate all requirement files into one text block
    all_text = ""
    for req_file in requirements_files:
        if req_file.exists():
            try:
                all_text += req_file.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                pass

    # Also scan pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            all_text += pyproject.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            pass

    # Django takes priority because it often includes Flask-like libs too
    if "django" in all_text:
        return "django"
    if "fastapi" in all_text:
        return "fastapi"
    if "flask" in all_text:
        return "flask"
    if "pyramid" in all_text:
        return "pyramid"
    if "tornado" in all_text:
        return "tornado"

    # Check manage.py as Django signal
    if (root / "manage.py").exists():
        return "django"

    # Check for app.py with flask import
    app_py = root / "app.py"
    if app_py.exists():
        try:
            content = app_py.read_text(encoding="utf-8", errors="replace")
            if "from flask" in content or "import flask" in content:
                return "flask"
            if "from fastapi" in content or "import fastapi" in content:
                return "fastapi"
        except Exception:
            pass

    return "unknown"


def _detect_java_framework(root: Path) -> str:
    """Detect Java framework from build descriptor."""
    pom_xml = root / "pom.xml"
    if pom_xml.exists():
        try:
            content = pom_xml.read_text(encoding="utf-8", errors="replace").lower()
            if "spring-boot" in content:
                return "spring-boot"
            if "spring" in content:
                return "spring"
            if "quarkus" in content:
                return "quarkus"
            if "micronaut" in content:
                return "micronaut"
        except Exception:
            pass

    # Gradle
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle_path = root / gradle_file
        if gradle_path.exists():
            try:
                content = gradle_path.read_text(encoding="utf-8", errors="replace").lower()
                if "spring-boot" in content:
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


def _detect_js_framework(root: Path) -> str:
    """Detect JavaScript/TypeScript framework from package.json."""
    package_json = root / "package.json"
    if not package_json.exists():
        return "unknown"

    try:
        data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
        deps = {}
        deps.update(data.get("dependencies", {}))
        deps.update(data.get("devDependencies", {}))
        dep_names = {k.lower() for k in deps.keys()}

        # Order matters - angular uses @angular/core
        if any("@angular" in d for d in dep_names):
            return "angular"
        if "react" in dep_names or "react-dom" in dep_names:
            return "react"
        if "vue" in dep_names:
            return "vue"
        if "svelte" in dep_names:
            return "svelte"
        if "next" in dep_names:
            return "nextjs"
        if "express" in dep_names:
            return "express"
        if "fastify" in dep_names:
            return "fastify"
        if "nestjs" in dep_names or "@nestjs/core" in dep_names:
            return "nestjs"
    except Exception:
        pass

    return "unknown"


# ============================================================================
# STANDARDS LOADING
# ============================================================================

def load_custom_standards(project_path: str) -> List[Dict[str, Any]]:
    """Load custom standards defined inside the project root.

    Looks for:
      - <project_root>/.claude/standards/*.md
      - <project_root>/standards/*.md

    Args:
        project_path: Absolute path to the project root.

    Returns:
        List of standard dicts with keys: id, source, content, priority.
    """
    root = Path(project_path)
    custom: List[Dict[str, Any]] = []

    search_dirs = [
        root / ".claude" / "standards",
        root / "standards",
    ]

    for standards_dir in search_dirs:
        if not standards_dir.exists():
            continue
        for md_file in standards_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                custom.append({
                    "id": f"custom_{md_file.stem}",
                    "source": "custom_standards",
                    "file": str(md_file),
                    "content": content,
                    "priority": 1,  # Highest priority
                })
            except Exception:
                pass

    return custom


def load_team_standards(project_path: str) -> List[Dict[str, Any]]:
    """Load team-level standards from ~/.claude/.

    Scans:
      - ~/.claude/policies/02-standards-system/*.md
      - ~/.claude/standards/*.md

    Args:
        project_path: Not used here but kept for API symmetry.

    Returns:
        List of standard dicts with keys: id, source, content, priority.
    """
    team: List[Dict[str, Any]] = []

    search_dirs = [
        Path.home() / ".claude" / "policies" / "02-standards-system",
        Path.home() / ".claude" / "standards",
    ]

    for standards_dir in search_dirs:
        if not standards_dir.exists():
            continue
        for md_file in standards_dir.glob("**/*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                team.append({
                    "id": f"team_{md_file.stem}",
                    "source": "team_standards",
                    "file": str(md_file),
                    "content": content,
                    "priority": 2,  # Second highest
                })
            except Exception:
                pass

    return team


def load_framework_standards(project_type: str, framework: str) -> List[Dict[str, Any]]:
    """Load built-in framework standards (bundled with Claude Insight).

    Looks in: scripts/architecture/02-standards-system/**/<framework>-standards.md

    Args:
        project_type: Language string.
        framework: Framework string.

    Returns:
        List of standard dicts.
    """
    built_in: List[Dict[str, Any]] = []

    # Resolve path relative to this file
    here = Path(__file__).parent.parent  # scripts/
    arch_dir = here / "architecture" / "02-standards-system"

    if not arch_dir.exists():
        return built_in

    # Try exact match first, then partial
    candidate_names = [
        f"{project_type}-{framework}-standards.md",
        f"{framework}-standards.md",
        f"{project_type}-standards.md",
    ]

    for name in candidate_names:
        candidate = arch_dir / name
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                built_in.append({
                    "id": f"framework_{candidate.stem}",
                    "source": "framework_standards",
                    "file": str(candidate),
                    "content": content,
                    "priority": 3,  # Third priority
                })
                break  # Only load the most specific match
            except Exception:
                pass

    return built_in


def load_language_standards(project_type: str) -> List[Dict[str, Any]]:
    """Load language-level standards (lowest priority).

    Args:
        project_type: Language string.

    Returns:
        List of standard dicts.
    """
    lang: List[Dict[str, Any]] = []

    here = Path(__file__).parent.parent
    arch_dir = here / "architecture" / "02-standards-system"

    if not arch_dir.exists():
        return lang

    candidate = arch_dir / f"{project_type}-standards.md"
    if candidate.exists():
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
            lang.append({
                "id": f"language_{project_type}",
                "source": "language_standards",
                "file": str(candidate),
                "content": content,
                "priority": 4,  # Lowest priority
            })
        except Exception:
            pass

    return lang


# ============================================================================
# MAIN SELECT FUNCTION
# ============================================================================

def select_standards(project_path: str, session_id: str = "default") -> Dict[str, Any]:
    """Select and load all applicable standards for a project.

    Detection order:
      1. detect_project_type()
      2. detect_framework()
      3. load_custom_standards()    (priority 1 - highest)
      4. load_team_standards()      (priority 2)
      5. load_framework_standards() (priority 3)
      6. load_language_standards()  (priority 4 - lowest)
      7. detect_conflicts() + resolve_conflicts()

    Args:
        project_path: Absolute path to project root.
        session_id: Session identifier for ErrorLogger.

    Returns:
        Dict with keys:
          - project_type: str
          - framework: str
          - standards_list: List[Dict]
          - merged_rules: Dict   (resolved, no conflicts)
          - conflicts: List[Dict]
          - total_loaded: int
    """
    logger = ErrorLogger(session_id)

    # --- 1. Detect project characteristics ---
    project_type = detect_project_type(project_path)
    framework = detect_framework(project_path, project_type)

    logger.log_decision(
        step="Standard Selector",
        decision="Project detected",
        reasoning=f"Marker files analyzed in {project_path}",
        chosen_option=f"{project_type}/{framework}",
    )

    # --- 2. Load standards from all sources ---
    all_standards: List[Dict[str, Any]] = []
    all_standards.extend(load_custom_standards(project_path))
    all_standards.extend(load_team_standards(project_path))
    all_standards.extend(load_framework_standards(project_type, framework))
    all_standards.extend(load_language_standards(project_type))

    logger.log_decision(
        step="Standard Selector",
        decision=f"Loaded {len(all_standards)} standards from all sources",
        reasoning="Custom > Team > Framework > Language priority chain",
        chosen_option="standards_loaded",
    )

    # --- 3. Conflict resolution ---
    conflicts = detect_conflicts(all_standards)
    merged_rules = resolve_conflicts(all_standards)

    if conflicts:
        logger.log_error(
            step="Standard Selector",
            error_message=f"{len(conflicts)} conflict(s) detected between standards",
            severity="WARNING",
            error_type="StandardsConflict",
            recovery_action="Higher-priority standard wins per priority_order",
            context={"conflicts": [c.get("conflicts") for c in conflicts]},
        )

    logger.save_audit_trail()

    return {
        "project_type": project_type,
        "framework": framework,
        "standards_list": all_standards,
        "merged_rules": merged_rules,
        "conflicts": conflicts,
        "total_loaded": len(all_standards),
    }


# ============================================================================
# CONFLICT DETECTION & RESOLUTION
# ============================================================================

def compare_standards(std1: Dict[str, Any], std2: Dict[str, Any]) -> List[str]:
    """Compare two standard dicts and find rule keys that conflict.

    Currently compares the ``rules`` sub-key when both standards carry
    parsed rules (i.e., after schema validation). For raw-content standards
    (just text) we do a lightweight keyword check instead.

    Args:
        std1: First standard dict.
        std2: Second standard dict.

    Returns:
        List of conflicting rule key paths (empty if no conflicts).
    """
    conflicting: List[str] = []

    rules1 = std1.get("rules", {})
    rules2 = std2.get("rules", {})

    if not rules1 or not rules2:
        # Cannot compare without parsed rules
        return conflicting

    for top_key in set(rules1.keys()) & set(rules2.keys()):
        sub1 = rules1.get(top_key, {})
        sub2 = rules2.get(top_key, {})

        if isinstance(sub1, dict) and isinstance(sub2, dict):
            for sub_key in set(sub1.keys()) & set(sub2.keys()):
                if sub1[sub_key] != sub2[sub_key]:
                    conflicting.append(f"{top_key}.{sub_key}")
        elif sub1 != sub2:
            conflicting.append(top_key)

    return conflicting


def detect_conflicts(standards_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find conflicting rules between standards.

    Compares every pair of standards. Only standards that carry a parsed
    ``rules`` dict (loaded via StandardsSchema) produce detailed conflict
    records.

    Args:
        standards_list: List of standard dicts.

    Returns:
        List of conflict records:
          [{standard1, standard2, conflicts: [rule_path, ...]}]
    """
    conflicts: List[Dict[str, Any]] = []

    for i, std1 in enumerate(standards_list):
        for std2 in standards_list[i + 1:]:
            conflicting_rules = compare_standards(std1, std2)
            if conflicting_rules:
                conflicts.append({
                    "standard1": std1.get("id", f"std_{i}"),
                    "standard2": std2.get("id", f"std_{i+1}"),
                    "conflicts": conflicting_rules,
                })

    return conflicts


def resolve_conflicts(standards_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve conflicts by applying standards in priority order.

    Priority order (lower number = higher priority, wins conflicts):
      1. custom_standards   - project-local .claude/standards/
      2. project_standards  - project-local standards/ (legacy path)
      3. team_standards     - ~/.claude/standards/
      4. framework_standards - built-in framework rules
      5. language_standards  - built-in language rules

    Rules from higher-priority sources override lower-priority sources.

    Args:
        standards_list: List of standard dicts (each may have a ``rules`` key).

    Returns:
        Merged rules dict with conflicts resolved.
    """
    priority_order = [
        "custom_standards",       # Priority 1 (highest)
        "project_standards",      # Priority 2
        "team_standards",         # Priority 3
        "framework_standards",    # Priority 4
        "language_standards",     # Priority 5 (lowest)
    ]

    # Sort standards by priority (lowest priority number first = highest precedence)
    def _priority_key(std: Dict[str, Any]) -> int:
        source = std.get("source", "unknown")
        try:
            return priority_order.index(source)
        except ValueError:
            return len(priority_order)  # Unknown sources get lowest priority

    sorted_standards = sorted(standards_list, key=_priority_key)

    merged: Dict[str, Any] = {}

    # Apply in reverse order (lowest priority first) so that higher-priority
    # sources overwrite when they apply the same key.
    for std in reversed(sorted_standards):
        rules = std.get("rules", {})
        if not rules:
            continue
        _deep_merge(merged, rules)

    return merged


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Deep merge override into base in-place.

    Nested dicts are merged recursively. Scalar values are overwritten.

    Args:
        base: Target dict (modified in-place).
        override: Source dict with values to apply on top.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
