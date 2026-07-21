"""standards/selector.py -- Standard Selector for project type and framework detection.

Moved from langgraph_engine/standard_selector.py to the standards/ domain package.
Backward-compat shim at the original location re-exports from here.

Implements:
- Project type detection (Python, Java, JavaScript, Go, etc.)
- Framework detection within each language
- Custom standards loading (project-local + team-global)
- Conflict detection and resolution with priority ordering

Priority ordering (higher number wins conflicts):
  custom=4 > team=3 > framework=2 > language=1

Windows-safe: ASCII only (cp1252 compatible).
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from langgraph_engine.core.logger_factory import get_logger
from langgraph_engine.engine_logging.error_logger import ErrorLogger
from langgraph_engine.patterns import memoize

logger = get_logger(__name__)

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home, get_policies_dir

    _STANDARD_SELECTOR_POLICIES_DIR = get_policies_dir()
    _STANDARD_SELECTOR_CLAUDE_HOME = get_claude_home()
except ImportError:
    _STANDARD_SELECTOR_POLICIES_DIR = Path.home() / ".claude" / "policies"
    _STANDARD_SELECTOR_CLAUDE_HOME = Path.home() / ".claude"


PRIORITY_CUSTOM = 4
PRIORITY_TEAM = 3
PRIORITY_FRAMEWORK = 2
PRIORITY_LANGUAGE = 1

# project_type -> bundled language-standards filename under docs/.
# Only languages with an actual standards doc are listed here; project
# types absent from this map ("unknown") simply yield no language
# standards until a doc for them is added.
_LANGUAGE_STANDARDS_FILES = {
    "python": "02-backend-standards.md",
    "javascript": "06-typescript-standards.md",
    "typescript": "06-typescript-standards.md",
    "go": "07-go-standards.md",
    "rust": "08-rust-standards.md",
    "java": "java-standards.md",
    "csharp": "csharp-standards.md",
}


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

    if (
        (root / "setup.py").exists()
        or (root / "pyproject.toml").exists()
        or (root / "requirements.txt").exists()
        or (root / "Pipfile").exists()
        or list(root.glob("**/*.py"))[:1]
    ):
        return "python"

    if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return "java"

    if (root / "tsconfig.json").exists():
        return "typescript"

    if (root / "package.json").exists():
        return "javascript"

    if (root / "go.mod").exists():
        return "go"

    if (root / "Cargo.toml").exists():
        return "rust"

    cs_files = list(root.glob("**/*.csproj"))
    sln_files = list(root.glob("**/*.sln"))
    if cs_files or sln_files:
        return "csharp"

    return "unknown"


@memoize(ttl_seconds=3600)
def detect_framework(project_path: str, project_type: str) -> str:
    """Detect the primary framework used within a project type.

    Results are cached per (project_path, project_type) pair for 1 hour.
    Use detect_framework.cache_clear() to flush the cache manually.

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


def _detect_python_framework(root: Path) -> str:
    """Detect Python web framework from requirements and source files."""
    requirements_files = [
        root / "requirements.txt",
        root / "requirements" / "base.txt",
        root / "requirements" / "prod.txt",
    ]

    all_text = ""
    for req_file in requirements_files:
        if req_file.exists():
            try:
                all_text += req_file.read_text(encoding="utf-8", errors="replace").lower()
            except OSError as exc:
                logger.debug(f"[standards] requirements read skipped: {exc}")

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            all_text += pyproject.read_text(encoding="utf-8", errors="replace").lower()
        except OSError as exc:
            logger.debug(f"[standards] pyproject.toml read skipped: {exc}")

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

    if (root / "manage.py").exists():
        return "django"

    if "langgraph" in all_text:
        return "langgraph"
    if "langchain" in all_text:
        return "langchain"
    if "celery" in all_text:
        return "celery"
    if "scrapy" in all_text:
        return "scrapy"

    app_py = root / "app.py"
    if app_py.exists():
        try:
            content = app_py.read_text(encoding="utf-8", errors="replace")
            if "from flask" in content or "import flask" in content:
                return "flask"
            if "from fastapi" in content or "import fastapi" in content:
                return "fastapi"
        except OSError as exc:
            logger.debug(f"[standards] app.py read skipped: {exc}")

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
        except OSError as exc:
            logger.debug(f"[standards] pom.xml read skipped: {exc}")

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
            except OSError as exc:
                logger.debug(f"[standards] build.gradle read skipped: {exc}")

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
    except (OSError, ValueError) as exc:
        logger.debug(f"[standards] package.json read skipped: {exc}")

    return "unknown"


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
                custom.append(
                    {
                        "id": "custom_{}".format(md_file.stem),
                        "source": "custom_standards",
                        "file": str(md_file),
                        "content": content,
                        "priority": PRIORITY_CUSTOM,
                    }
                )
            except OSError as exc:
                logger.debug(f"[standards] custom standard read skipped: {exc}")

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
        _STANDARD_SELECTOR_POLICIES_DIR / "02-standards-system",
        _STANDARD_SELECTOR_CLAUDE_HOME / "standards",
    ]

    for standards_dir in search_dirs:
        if not standards_dir.exists():
            continue
        for md_file in standards_dir.glob("**/*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                team.append(
                    {
                        "id": "team_{}".format(md_file.stem),
                        "source": "team_standards",
                        "file": str(md_file),
                        "content": content,
                        "priority": PRIORITY_TEAM,
                    }
                )
            except OSError as exc:
                logger.debug(f"[standards] team standard read skipped: {exc}")

    return team


def load_framework_standards(project_type: str, framework: str) -> List[Dict[str, Any]]:
    """Load built-in framework standards (bundled with Claude Workflow Engine).

    Looks in docs/ for a framework-specific standards file, e.g.
    docs/python-flask-standards.md or docs/flask-standards.md. No such
    files are bundled yet -- every standards doc under docs/ covers a
    language as a whole, not a specific framework -- so this returns
    empty until a framework-specific doc is added. Language-level
    fallback is handled separately by load_language_standards().

    Args:
        project_type: Language string.
        framework: Framework string.

    Returns:
        List of standard dicts.
    """
    built_in: List[Dict[str, Any]] = []

    arch_dir = Path(__file__).parent.parent.parent / "docs"
    if not arch_dir.exists():
        return built_in

    candidate_names = [
        "{}-{}-standards.md".format(project_type, framework),
        "{}-standards.md".format(framework),
    ]

    for name in candidate_names:
        candidate = arch_dir / name
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                built_in.append(
                    {
                        "id": "framework_{}".format(candidate.stem),
                        "source": "framework_standards",
                        "file": str(candidate),
                        "content": content,
                        "priority": PRIORITY_FRAMEWORK,
                    }
                )
                break
            except OSError as exc:
                logger.debug(f"[standards] framework standard read skipped: {exc}")

    return built_in


def load_language_standards(project_type: str) -> List[Dict[str, Any]]:
    """Load language-level standards (lowest priority).

    Looks up project_type in _LANGUAGE_STANDARDS_FILES and reads the
    matching file from docs/ if one is bundled for that language.

    Args:
        project_type: Language string.

    Returns:
        List of standard dicts.
    """
    lang: List[Dict[str, Any]] = []

    filename = _LANGUAGE_STANDARDS_FILES.get(project_type)
    if not filename:
        return lang

    candidate = Path(__file__).parent.parent.parent / "docs" / filename
    if candidate.exists():
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
            lang.append(
                {
                    "id": "language_{}".format(project_type),
                    "source": "language_standards",
                    "file": str(candidate),
                    "content": content,
                    "priority": PRIORITY_LANGUAGE,
                }
            )
        except OSError as exc:
            logger.debug(f"[standards] language standard read skipped: {exc}")

    return lang


def select_standards(project_path: str, session_id: str = "default") -> Dict[str, Any]:
    """Select and load all applicable standards for a project.

    Detection order:
      1. detect_project_type()
      2. detect_framework()
      3. load_custom_standards()    (priority=4 - highest precedence)
      4. load_team_standards()      (priority=3)
      5. load_framework_standards() (priority=2)
      6. load_language_standards()  (priority=1 - lowest precedence)
      7. detect_conflicts() + resolve_conflicts()

    Args:
        project_path: Absolute path to project root.
        session_id:   Session identifier for ErrorLogger.

    Returns:
        Dict with keys:
          - project_type: str
          - framework: str
          - standards_list: List[Dict]
          - merged_rules: Dict
          - conflicts: List[Dict]
          - total_loaded: int
          - traceability: Dict
    """
    logger = ErrorLogger(session_id)
    traceability: Dict[str, Any] = {
        "project_path": project_path,
        "session_id": session_id,
        "detection_steps": [],
        "sources_checked": [],
        "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
    }

    project_type = detect_project_type(project_path)
    framework = detect_framework(project_path, project_type)

    traceability["project_type"] = project_type
    traceability["framework"] = framework
    traceability["detection_steps"].append(
        "detect_project_type() -> '{}' (checked setup.py, pom.xml, "
        "package.json, tsconfig.json, go.mod, Cargo.toml, *.csproj)".format(project_type)
    )
    traceability["detection_steps"].append(
        "detect_framework() -> '{}' (checked requirements.txt, "
        "pyproject.toml, pom.xml, build.gradle, package.json deps)".format(framework)
    )

    logger.log_decision(
        step="Standard Selector",
        decision="Project detected",
        reasoning="Marker files analyzed in {}".format(project_path),
        chosen_option="{}/{}".format(project_type, framework),
    )

    all_standards: List[Dict[str, Any]] = []

    custom_loaded = load_custom_standards(project_path)
    all_standards.extend(custom_loaded)
    traceability["sources_checked"].append(
        {
            "source": "custom_standards",
            "priority": PRIORITY_CUSTOM,
            "loaded": len(custom_loaded),
            "locations": [".claude/standards/*.md", "standards/*.md"],
        }
    )

    team_loaded = load_team_standards(project_path)
    all_standards.extend(team_loaded)
    traceability["sources_checked"].append(
        {
            "source": "team_standards",
            "priority": PRIORITY_TEAM,
            "loaded": len(team_loaded),
            "locations": ["~/.claude/policies/02-standards-system/**/*.md", "~/.claude/standards/*.md"],
        }
    )

    framework_loaded = load_framework_standards(project_type, framework)
    all_standards.extend(framework_loaded)
    traceability["sources_checked"].append(
        {
            "source": "framework_standards",
            "priority": PRIORITY_FRAMEWORK,
            "loaded": len(framework_loaded),
            "locations": [
                "docs/{}-{}-standards.md".format(project_type, framework),
                "docs/{}-standards.md".format(framework),
            ],
        }
    )

    language_loaded = load_language_standards(project_type)
    all_standards.extend(language_loaded)
    traceability["sources_checked"].append(
        {
            "source": "language_standards",
            "priority": PRIORITY_LANGUAGE,
            "loaded": len(language_loaded),
            "locations": [
                "docs/{}".format(_LANGUAGE_STANDARDS_FILES.get(project_type, "<no doc bundled for this language>"))
            ],
        }
    )

    logger.log_decision(
        step="Standard Selector",
        decision="Loaded {} standards from all sources".format(len(all_standards)),
        reasoning=(
            "custom({}) > team({}) > framework({}) > language({})".format(
                len(custom_loaded), len(team_loaded), len(framework_loaded), len(language_loaded)
            )
        ),
        chosen_option="standards_loaded",
    )

    conflicts = detect_conflicts(all_standards)
    merged_rules = resolve_conflicts(all_standards)

    traceability["conflicts_detected"] = len(conflicts)
    traceability["merged_rules_keys"] = list(merged_rules.keys()) if merged_rules else []

    if conflicts:
        logger.log_error(
            step="Standard Selector",
            error_message="{} conflict(s) detected between standards".format(len(conflicts)),
            severity="WARNING",
            error_type="StandardsConflict",
            recovery_action="Higher numeric priority wins: custom(4) > team(3) > framework(2) > language(1)",
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
        "traceability": traceability,
    }


def compare_standards(std1: Dict[str, Any], std2: Dict[str, Any]) -> List[str]:
    """Compare two standard dicts and find rule keys that conflict.

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
        return conflicting

    for top_key in set(rules1.keys()) & set(rules2.keys()):
        sub1 = rules1.get(top_key, {})
        sub2 = rules2.get(top_key, {})

        if isinstance(sub1, dict) and isinstance(sub2, dict):
            for sub_key in set(sub1.keys()) & set(sub2.keys()):
                if sub1[sub_key] != sub2[sub_key]:
                    conflicting.append("{}.{}".format(top_key, sub_key))
        elif sub1 != sub2:
            conflicting.append(top_key)

    return conflicting


def detect_conflicts(standards_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find conflicting rules between standards.

    Args:
        standards_list: List of standard dicts.

    Returns:
        List of conflict records: [{standard1, standard2, conflicts: [rule_path, ...]}]
    """
    conflicts: List[Dict[str, Any]] = []

    for i, std1 in enumerate(standards_list):
        for std2 in standards_list[i + 1 :]:
            conflicting_rules = compare_standards(std1, std2)
            if conflicting_rules:
                conflicts.append(
                    {
                        "standard1": std1.get("id", "std_{}".format(i)),
                        "standard2": std2.get("id", "std_{}".format(i + 1)),
                        "conflicts": conflicting_rules,
                    }
                )

    return conflicts


def resolve_conflicts(standards_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve conflicts by applying standards in priority order.

    Priority ordering (higher numeric value = higher precedence):
      custom=4 > team=3 > framework=2 > language=1

    Args:
        standards_list: List of standard dicts each with a ``priority`` int field.

    Returns:
        Merged rules dict with conflicts resolved (higher-priority source wins).
    """

    def _priority_key(std: Dict[str, Any]) -> int:
        raw = std.get("priority", 0)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    sorted_standards = sorted(standards_list, key=_priority_key)

    merged: Dict[str, Any] = {}

    for std in sorted_standards:
        rules = std.get("rules", {})
        if not rules:
            continue
        _deep_merge(merged, rules)

    return merged


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Deep merge override into base in-place.

    Args:
        base:     Target dict (modified in-place).
        override: Source dict with values to apply on top.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
