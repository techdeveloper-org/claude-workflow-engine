"""
Build Dependency Resolver - Improves CallGraph edge resolution via build file analysis.

Parses project build files to discover internal and external dependencies, builds
CallGraph sub-graphs for internal dependencies with local source, merges them into
the main graph, and re-runs edge resolution to improve coverage.

Supported build systems:
  - python-pip      : requirements.txt
  - python-pyproject: pyproject.toml (PEP 517/518/621)
  - python-setup    : setup.py / setup.cfg
  - python-pipenv   : Pipfile
  - maven           : pom.xml
  - gradle          : build.gradle / build.gradle.kts
  - npm             : package.json
  - go              : go.mod
  - cargo           : Cargo.toml

Dependency classifications:
  - internal        : user-owned package with local source found on disk
  - external_known  : well-known third-party library
  - external_unknown: unrecognized, may or may not be local
  - needs_user_input: cannot confirm; user question generated

Public API:
  detect_build_system(project_root)         -> dict
  parse_dependencies(project_root)          -> dict
  resolve_internal_deps(project_root, deps) -> dict
  enhance_call_graph(graph, resolved_deps)  -> dict
  get_unresolved_questions(project_root, deps_result) -> list
  resolve_and_enhance(project_root, graph)  -> dict

All public functions are fail-safe (catch all exceptions and return safe fallbacks).
Uses standard logging (not loguru). ASCII-only source. Python 3.8+ compatible.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Well-known external dependency sets
# ---------------------------------------------------------------------------

PYTHON_WELL_KNOWN = frozenset([
    "flask", "django", "fastapi", "sqlalchemy", "alembic", "celery",
    "redis", "pymongo", "motor", "psycopg2", "aiohttp", "httpx",
    "requests", "urllib3", "boto3", "botocore", "pydantic", "marshmallow",
    "pytest", "unittest", "mock", "coverage", "mypy", "pylint", "flake8",
    "black", "isort", "setuptools", "wheel", "pip", "virtualenv",
    "numpy", "pandas", "scipy", "matplotlib", "sklearn", "tensorflow",
    "torch", "keras", "transformers", "langchain", "langgraph", "openai",
    "anthropic", "loguru", "structlog", "python-dotenv", "pydantic-settings",
    "uvicorn", "gunicorn", "starlette", "typer", "click", "rich",
    "jinja2", "werkzeug", "itsdangerous", "markupsafe", "cryptography",
    "paramiko", "fabric", "ansible", "docker", "kubernetes", "boto",
    "google-cloud", "azure", "stripe", "twilio", "sendgrid", "pillow",
    "lxml", "beautifulsoup4", "scrapy", "selenium", "playwright",
    "sqlmodel", "tortoise-orm", "databases", "aiosqlite", "aiomysql",
    "asyncpg", "influxdb", "elasticsearch", "qdrant-client", "pinecone",
    "mcp", "fastmcp", "httpcore", "certifi", "charset-normalizer",
    "packaging", "tomli", "tomllib", "yaml", "pyyaml", "toml",
])

JAVA_WELL_KNOWN = frozenset([
    "org.springframework", "org.hibernate", "org.apache", "com.google",
    "com.fasterxml.jackson", "junit", "org.mockito", "org.slf4j",
    "ch.qos.logback", "log4j", "commons-lang", "commons-io",
    "commons-collections", "guava", "lombok", "javax", "jakarta",
    "io.micronaut", "io.quarkus", "org.projectlombok", "net.sf",
    "org.bouncycastle", "io.netty", "com.squareup", "okhttp3",
    "retrofit2", "com.zaxxer", "mysql", "postgresql", "h2database",
    "flyway", "liquibase", "mapstruct", "modelmapper",
])

NODE_WELL_KNOWN = frozenset([
    "express", "koa", "hapi", "fastify", "nest", "next", "nuxt",
    "react", "vue", "angular", "svelte", "webpack", "vite", "rollup",
    "babel", "typescript", "eslint", "prettier", "jest", "mocha",
    "chai", "sinon", "supertest", "axios", "got", "node-fetch",
    "lodash", "ramda", "moment", "dayjs", "date-fns", "uuid",
    "bcrypt", "jsonwebtoken", "passport", "helmet", "cors", "morgan",
    "body-parser", "multer", "sharp", "jimp", "socket.io", "ws",
    "mongoose", "sequelize", "typeorm", "prisma", "knex", "objection",
    "redis", "ioredis", "amqplib", "kafkajs", "dotenv", "yargs",
    "commander", "chalk", "ora", "inquirer", "nodemon", "pm2",
])

GO_WELL_KNOWN = frozenset([
    "github.com/gin-gonic", "github.com/gorilla", "github.com/labstack",
    "github.com/go-chi", "github.com/stretchr", "github.com/sirupsen",
    "go.uber.org", "github.com/pkg/errors", "github.com/spf13",
    "github.com/google", "google.golang.org", "golang.org/x",
])

RUST_WELL_KNOWN = frozenset([
    "serde", "tokio", "actix-web", "axum", "warp", "rocket",
    "reqwest", "hyper", "tonic", "prost", "diesel", "sqlx",
    "anyhow", "thiserror", "log", "tracing", "clap", "structopt",
    "chrono", "uuid", "rand", "regex", "rayon", "crossbeam",
])

# ---------------------------------------------------------------------------
# 1. detect_build_system
# ---------------------------------------------------------------------------

def detect_build_system(project_root: Any) -> Dict[str, Any]:
    """Detect the build system used in a project directory.

    Checks for build files in priority order:
    maven > gradle > npm > go > cargo > python-pyproject > python-pip >
    python-setup > python-pipenv

    Args:
        project_root: Path-like or str pointing to the project root directory.

    Returns:
        Dict with:
            build_system (str)   - one of: maven, gradle, npm, go, cargo,
                                   python-pyproject, python-pip, python-setup,
                                   python-pipenv, unknown
            build_files (list)   - list of detected build file paths (str)
            error (str|None)     - error message if detection failed
    """
    try:
        root = Path(project_root)
        if not root.exists():
            return {"build_system": "unknown", "build_files": [],
                    "error": f"Project root does not exist: {project_root}"}

        detected_files: List[str] = []
        build_system = "unknown"

        # Priority-ordered checks
        checks = [
            ("maven",            ["pom.xml"]),
            ("gradle",           ["build.gradle", "build.gradle.kts",
                                  "settings.gradle", "settings.gradle.kts"]),
            ("npm",              ["package.json"]),
            ("go",               ["go.mod"]),
            ("cargo",            ["Cargo.toml"]),
            ("python-pyproject", ["pyproject.toml"]),
            ("python-pip",       ["requirements.txt", "requirements-dev.txt",
                                  "requirements-test.txt"]),
            ("python-setup",     ["setup.py", "setup.cfg"]),
            ("python-pipenv",    ["Pipfile"]),
        ]

        for system, filenames in checks:
            found = []
            for fname in filenames:
                candidate = root / fname
                if candidate.is_file():
                    found.append(str(candidate))
            if found:
                if build_system == "unknown":
                    build_system = system
                detected_files.extend(found)

        logger.debug(
            "[BuildDepResolver] detect_build_system: system=%s files=%s",
            build_system, detected_files
        )
        return {"build_system": build_system, "build_files": detected_files, "error": None}

    except Exception as exc:
        logger.exception("[BuildDepResolver] detect_build_system failed")
        return {"build_system": "unknown", "build_files": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# 2. parse_dependencies
# ---------------------------------------------------------------------------

def parse_dependencies(project_root: Any) -> Dict[str, Any]:
    """Parse build files and classify all dependencies.

    Args:
        project_root: Path-like or str pointing to the project root.

    Returns:
        Dict with:
            build_system (str)
            internal (list[dict])          - [{name, hint_path, version}]
            external_known (list[dict])    - [{name, version, registry}]
            external_unknown (list[dict])  - [{name, version}]
            needs_user_input (list[dict])  - [{name, version, reason}]
            total_deps (int)
            internal_count (int)
            external_count (int)
            error (str|None)
    """
    try:
        root = Path(project_root)
        bs_result = detect_build_system(root)
        build_system = bs_result["build_system"]

        raw_deps = _parse_raw_deps(root, build_system, bs_result["build_files"])

        internal: List[Dict] = []
        external_known: List[Dict] = []
        external_unknown: List[Dict] = []
        needs_user_input: List[Dict] = []

        for dep in raw_deps:
            classification = _classify_dep(root, dep, build_system)
            if classification == "internal":
                internal.append(dep)
            elif classification == "external_known":
                external_known.append(dep)
            elif classification == "needs_user_input":
                needs_user_input.append(dep)
            else:
                external_unknown.append(dep)

        total = len(raw_deps)
        logger.info(
            "[BuildDepResolver] parse_dependencies: system=%s total=%d "
            "internal=%d ext_known=%d ext_unknown=%d needs_input=%d",
            build_system, total, len(internal), len(external_known),
            len(external_unknown), len(needs_user_input)
        )

        return {
            "build_system": build_system,
            "internal": internal,
            "external_known": external_known,
            "external_unknown": external_unknown,
            "needs_user_input": needs_user_input,
            "total_deps": total,
            "internal_count": len(internal),
            "external_count": len(external_known) + len(external_unknown),
            "error": None,
        }

    except Exception as exc:
        logger.exception("[BuildDepResolver] parse_dependencies failed")
        return {
            "build_system": "unknown",
            "internal": [], "external_known": [], "external_unknown": [],
            "needs_user_input": [], "total_deps": 0,
            "internal_count": 0, "external_count": 0,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# 3. resolve_internal_deps
# ---------------------------------------------------------------------------

def resolve_internal_deps(
    project_root: Any,
    internal_deps: List[Dict],
) -> Dict[str, Any]:
    """Build CallGraph sub-graphs for internal dependencies with local source.

    For each internal dependency that has a ``hint_path`` entry pointing to a
    local directory containing Python/Java/etc. source files, this function
    instantiates a ``CallGraphBuilder`` and builds a sub-graph.

    Args:
        project_root: Path-like or str pointing to the project root.
        internal_deps: List of internal dep dicts as returned by
            ``parse_dependencies`` (each must have at minimum a ``name`` key;
            optional ``hint_path`` key speeds up lookup).

    Returns:
        Dict with:
            resolved (list[dict]) - [{name, path, classes, methods, graph}]
            failed (list[dict])   - [{name, reason}]
            error (str|None)
    """
    try:
        root = Path(project_root)
        resolved: List[Dict] = []
        failed: List[Dict] = []

        CallGraphBuilder = _import_call_graph_builder(root)
        if CallGraphBuilder is None:
            msg = "Could not import CallGraphBuilder - skipping sub-graph resolution"
            logger.warning("[BuildDepResolver] %s", msg)
            for dep in internal_deps:
                failed.append({"name": dep.get("name", "?"), "reason": msg})
            return {"resolved": resolved, "failed": failed, "error": msg}

        for dep in internal_deps:
            dep_name = dep.get("name", "?")
            try:
                hint = dep.get("hint_path")
                if hint:
                    dep_path = Path(hint)
                    if not dep_path.is_absolute():
                        dep_path = root / dep_path
                else:
                    dep_path = _find_local_source(root, dep_name)

                if dep_path is None or not dep_path.exists():
                    failed.append({
                        "name": dep_name,
                        "reason": f"Local source path not found for '{dep_name}'"
                    })
                    continue

                if not _dir_has_code(dep_path):
                    failed.append({
                        "name": dep_name,
                        "reason": f"No source files found under '{dep_path}'"
                    })
                    continue

                logger.debug(
                    "[BuildDepResolver] Building sub-graph for '%s' at '%s'",
                    dep_name, dep_path
                )
                builder = CallGraphBuilder(project_root=str(dep_path))
                sub_graph = builder.build()

                stats = sub_graph.get_stats() if hasattr(sub_graph, "get_stats") else {}
                resolved.append({
                    "name": dep_name,
                    "path": str(dep_path),
                    "classes": stats.get("total_classes", 0),
                    "methods": stats.get("total_methods", 0),
                    "graph": sub_graph,
                })
                logger.info(
                    "[BuildDepResolver] Sub-graph for '%s': %d classes, %d methods",
                    dep_name, stats.get("total_classes", 0), stats.get("total_methods", 0)
                )

            except Exception as dep_exc:
                logger.warning(
                    "[BuildDepResolver] Failed to build sub-graph for '%s': %s",
                    dep_name, dep_exc
                )
                failed.append({"name": dep_name, "reason": str(dep_exc)})

        return {"resolved": resolved, "failed": failed, "error": None}

    except Exception as exc:
        logger.exception("[BuildDepResolver] resolve_internal_deps failed")
        return {"resolved": [], "failed": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# 4. enhance_call_graph
# ---------------------------------------------------------------------------

def enhance_call_graph(
    graph: Any,
    resolved_deps: List[Dict],
) -> Dict[str, Any]:
    """Merge dependency sub-graphs into main graph and re-run edge resolution.

    After merging, resets the graph's internal caches and calls
    ``graph.resolve_edges()`` to improve edge coverage.

    Args:
        graph: A ``CallGraph`` instance (from call_graph_builder.py).
        resolved_deps: List of resolved dep dicts as returned by
            ``resolve_internal_deps``; each dict must have a ``graph`` key.

    Returns:
        Dict with:
            before_resolved (int)   - resolved edge count before merge
            after_resolved (int)    - resolved edge count after merge
            improvement_pct (float) - percentage-point improvement
            new_classes (int)       - classes added from sub-graphs
            new_methods (int)       - methods added from sub-graphs
            error (str|None)
    """
    try:
        if graph is None:
            return {
                "before_resolved": 0, "after_resolved": 0,
                "improvement_pct": 0.0, "new_classes": 0, "new_methods": 0,
                "error": "graph is None",
            }

        # Snapshot before state
        before_stats = graph.get_stats() if hasattr(graph, "get_stats") else {}
        before_resolved = before_stats.get("resolved_edges", 0)
        before_total = before_stats.get("total_call_edges", 1)
        before_classes = before_stats.get("total_classes", 0)
        before_methods = before_stats.get("total_methods", 0)

        new_classes = 0
        new_methods = 0

        for dep_info in resolved_deps:
            sub_graph = dep_info.get("graph")
            if sub_graph is None:
                continue
            dep_name = dep_info.get("name", "?")
            try:
                _merge_sub_graph(graph, sub_graph, dep_name)
                sub_stats = sub_graph.get_stats() if hasattr(sub_graph, "get_stats") else {}
                new_classes += sub_stats.get("total_classes", 0)
                new_methods += sub_stats.get("total_methods", 0)
            except Exception as merge_exc:
                logger.warning(
                    "[BuildDepResolver] merge failed for '%s': %s", dep_name, merge_exc
                )

        # Invalidate caches before re-resolution
        for attr in ("_call_paths", "_impact_map", "_resolved_edges"):
            if hasattr(graph, attr):
                setattr(graph, attr, None)

        # Re-run edge resolution
        if hasattr(graph, "resolve_edges"):
            graph.resolve_edges()

        after_stats = graph.get_stats() if hasattr(graph, "get_stats") else {}
        after_resolved = after_stats.get("resolved_edges", 0)
        after_total = after_stats.get("total_call_edges", 1)

        before_pct = (before_resolved / max(before_total, 1)) * 100.0
        after_pct = (after_resolved / max(after_total, 1)) * 100.0
        improvement = after_pct - before_pct

        logger.info(
            "[BuildDepResolver] enhance_call_graph: resolved edges %d->%d "
            "(%.1f%% -> %.1f%%, +%.1f pct pts), +%d classes, +%d methods",
            before_resolved, after_resolved, before_pct, after_pct, improvement,
            new_classes, new_methods
        )

        return {
            "before_resolved": before_resolved,
            "after_resolved": after_resolved,
            "improvement_pct": round(improvement, 2),
            "new_classes": new_classes,
            "new_methods": new_methods,
            "error": None,
        }

    except Exception as exc:
        logger.exception("[BuildDepResolver] enhance_call_graph failed")
        return {
            "before_resolved": 0, "after_resolved": 0,
            "improvement_pct": 0.0, "new_classes": 0, "new_methods": 0,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# 5. get_unresolved_questions
# ---------------------------------------------------------------------------

def get_unresolved_questions(
    project_root: Any,
    deps_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Generate actionable user questions for unresolvable dependencies.

    Args:
        project_root: Path-like or str pointing to the project root.
        deps_result: Result dict from ``parse_dependencies``.

    Returns:
        List of question dicts, each with:
            dependency (str)   - dependency name
            question (str)     - human-readable question
            suggestion (str)   - suggested resolution action
            options (list[str])- possible answer choices
    """
    try:
        root = Path(project_root)
        questions: List[Dict] = []

        needs_input = deps_result.get("needs_user_input", [])
        external_unknown = deps_result.get("external_unknown", [])
        build_system = deps_result.get("build_system", "unknown")

        for dep in needs_input:
            q = _build_question(root, dep, build_system, reason="needs_input")
            if q:
                questions.append(q)

        for dep in external_unknown:
            q = _build_question(root, dep, build_system, reason="unknown")
            if q:
                questions.append(q)

        logger.debug(
            "[BuildDepResolver] get_unresolved_questions: %d questions generated",
            len(questions)
        )
        return questions

    except Exception as exc:
        logger.exception("[BuildDepResolver] get_unresolved_questions failed")
        return []


# ---------------------------------------------------------------------------
# 6. resolve_and_enhance (convenience pipeline)
# ---------------------------------------------------------------------------

def resolve_and_enhance(
    project_root: Any,
    graph: Any,
) -> Dict[str, Any]:
    """Full pipeline: parse deps -> resolve internals -> enhance graph -> questions.

    Args:
        project_root: Path-like or str pointing to the project root.
        graph: A ``CallGraph`` instance to enhance.

    Returns:
        Dict with:
            deps_result    (dict)  - output of parse_dependencies
            resolve_result (dict)  - output of resolve_internal_deps
            enhance_result (dict)  - output of enhance_call_graph
            questions      (list)  - output of get_unresolved_questions
            error          (str|None)
    """
    try:
        deps_result = parse_dependencies(project_root)

        resolve_result = resolve_internal_deps(
            project_root, deps_result.get("internal", [])
        )

        enhance_result = enhance_call_graph(
            graph, resolve_result.get("resolved", [])
        )

        questions = get_unresolved_questions(project_root, deps_result)

        return {
            "deps_result": deps_result,
            "resolve_result": resolve_result,
            "enhance_result": enhance_result,
            "questions": questions,
            "error": None,
        }

    except Exception as exc:
        logger.exception("[BuildDepResolver] resolve_and_enhance failed")
        return {
            "deps_result": {}, "resolve_result": {}, "enhance_result": {},
            "questions": [], "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Private helpers - build file parsers
# ---------------------------------------------------------------------------

def _parse_raw_deps(
    root: Path,
    build_system: str,
    build_files: List[str],
) -> List[Dict]:
    """Dispatch to the appropriate parser for the detected build system."""
    if build_system == "maven":
        return _parse_maven_deps(root, build_files)
    if build_system == "gradle":
        return _parse_gradle_deps(root, build_files)
    if build_system == "npm":
        return _parse_npm_deps(root, build_files)
    if build_system == "go":
        return _parse_go_deps(root, build_files)
    if build_system == "cargo":
        return _parse_cargo_deps(root, build_files)
    if build_system == "python-pyproject":
        return _read_pyproject_deps(root, build_files)
    if build_system in ("python-pip",):
        return _parse_python_deps(root, build_files)
    if build_system in ("python-setup",):
        return _parse_python_deps(root, build_files)
    if build_system == "python-pipenv":
        return _parse_python_deps(root, build_files)
    return []


def _parse_python_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse requirements.txt, setup.py/cfg, Pipfile for Python deps."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file():
            continue
        fname = path.name.lower()

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if fname in ("requirements.txt", "requirements-dev.txt",
                     "requirements-test.txt"):
            for line in content.splitlines():
                parsed = _parse_req_line(line)
                if parsed and parsed["name"] not in seen:
                    seen.add(parsed["name"])
                    deps.append(parsed)

        elif fname == "pipfile":
            # Simple TOML-like parse for [packages] and [dev-packages]
            in_section = False
            for line in content.splitlines():
                stripped = line.strip()
                if re.match(r"^\[(packages|dev-packages)\]", stripped, re.IGNORECASE):
                    in_section = True
                    continue
                if stripped.startswith("[") and not re.match(
                    r"^\[(packages|dev-packages)\]", stripped, re.IGNORECASE
                ):
                    in_section = False
                if in_section and "=" in stripped and not stripped.startswith("#"):
                    name = stripped.split("=")[0].strip().strip('"').strip("'")
                    if name and name not in seen:
                        seen.add(name)
                        deps.append({"name": name, "version": "*", "source": "Pipfile"})

        elif fname in ("setup.py", "setup.cfg"):
            # Rough extraction of install_requires lines
            for line in content.splitlines():
                stripped = line.strip().strip("'\"").strip(",")
                if stripped and not stripped.startswith("#"):
                    parsed = _parse_req_line(stripped)
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

    return deps


def _read_pyproject_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse pyproject.toml using tomllib (3.11+) or tomli or regex fallback."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "pyproject.toml":
            continue

        try:
            # Try tomllib (Python 3.11+)
            import importlib
            tomllib = None
            try:
                tomllib = importlib.import_module("tomllib")
            except ImportError:
                try:
                    tomllib = importlib.import_module("tomli")
                except ImportError:
                    pass

            if tomllib is not None:
                with open(path, "rb") as f:
                    data = tomllib.load(f)

                # PEP 621 dependencies
                project_deps = (
                    data.get("project", {}).get("dependencies", [])
                )
                # Poetry dependencies
                poetry_deps = (
                    data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                )

                for dep_str in project_deps:
                    parsed = _parse_req_line(dep_str)
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

                for dep_name in poetry_deps:
                    if dep_name.lower() == "python":
                        continue
                    if dep_name not in seen:
                        seen.add(dep_name)
                        ver = poetry_deps[dep_name]
                        deps.append({
                            "name": dep_name,
                            "version": ver if isinstance(ver, str) else "*",
                            "source": "pyproject.toml",
                        })
            else:
                # Regex fallback for Python 3.8/3.9/3.10 without tomli
                content = path.read_text(encoding="utf-8", errors="replace")
                # Match quoted dependency strings under [project] dependencies
                for m in re.finditer(r'"([a-zA-Z0-9_.-]+[^"]*)"', content):
                    parsed = _parse_req_line(m.group(1))
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

        except Exception as exc:
            logger.debug("[BuildDepResolver] pyproject.toml parse error: %s", exc)

    return deps


def _parse_req_line(line: str) -> Optional[Dict]:
    """Parse a single requirements.txt-style dependency line.

    Handles: name, name==1.0, name>=1.0, name[extra], name @ url,
    -r other.txt (skipped), # comments (stripped).
    """
    line = line.strip()
    # Strip inline comments
    if "#" in line:
        line = line[:line.index("#")].strip()
    if not line:
        return None
    # Skip options (-r, -c, --index-url, etc.)
    if line.startswith("-"):
        return None
    # Skip VCS URLs
    if line.startswith(("git+", "hg+", "svn+", "bzr+")):
        return None
    # Strip extras like name[security]
    name_match = re.match(r"^([A-Za-z0-9_.-]+)", line)
    if not name_match:
        return None
    name = name_match.group(1).lower().replace("_", "-")
    # Extract version specifier
    ver_match = re.search(r"([><=!~^]+[\s]*[\w.*]+)", line)
    version = ver_match.group(1).strip() if ver_match else "*"
    return {"name": name, "version": version, "source": "requirements"}


def _parse_maven_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse pom.xml for Maven dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "pom.xml":
            continue
        try:
            tree = ET.parse(str(path))
            root_el = tree.getroot()
            # Strip namespace
            ns_match = re.match(r"\{([^}]+)\}", root_el.tag)
            ns = "{" + ns_match.group(1) + "}" if ns_match else ""

            for dep_el in root_el.iter(f"{ns}dependency"):
                group_id = dep_el.findtext(f"{ns}groupId", "").strip()
                artifact_id = dep_el.findtext(f"{ns}artifactId", "").strip()
                version = dep_el.findtext(f"{ns}version", "*").strip()
                name = f"{group_id}:{artifact_id}" if group_id else artifact_id
                if name and name not in seen:
                    seen.add(name)
                    deps.append({
                        "name": name, "version": version,
                        "source": "pom.xml",
                        "_group_id": group_id, "_artifact_id": artifact_id,
                    })
        except Exception as exc:
            logger.debug("[BuildDepResolver] pom.xml parse error: %s", exc)

    return deps


def _parse_gradle_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse build.gradle for Gradle dependencies (best-effort line parsing)."""
    deps: List[Dict] = []
    seen: set = set()

    dep_pattern = re.compile(
        r"""(?:implementation|api|compile|testImplementation|runtimeOnly|compileOnly)\s*['"(]([^'")\s]+)['")]""",
        re.IGNORECASE
    )

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or "build.gradle" not in path.name:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for m in dep_pattern.finditer(content):
                coord = m.group(1).strip()
                # Maven-style: group:artifact:version
                parts = coord.split(":")
                name = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
                version = parts[2] if len(parts) >= 3 else "*"
                if name not in seen:
                    seen.add(name)
                    deps.append({"name": name, "version": version, "source": "build.gradle"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] build.gradle parse error: %s", exc)

    return deps


def _parse_npm_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse package.json for npm/yarn dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "package.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, version in data.get(section, {}).items():
                    clean_name = name.lower()
                    if clean_name not in seen:
                        seen.add(clean_name)
                        deps.append({
                            "name": clean_name, "version": version,
                            "source": "package.json",
                        })
        except Exception as exc:
            logger.debug("[BuildDepResolver] package.json parse error: %s", exc)

    return deps


def _parse_go_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse go.mod for Go module dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    require_pattern = re.compile(r"^\s+([^\s]+)\s+([^\s]+)")

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "go.mod":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            in_require = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("require ("):
                    in_require = True
                    continue
                if in_require and stripped == ")":
                    in_require = False
                    continue
                if in_require:
                    m = require_pattern.match(line)
                    if m:
                        name, version = m.group(1), m.group(2)
                        if name not in seen:
                            seen.add(name)
                            deps.append({"name": name, "version": version, "source": "go.mod"})
                elif stripped.startswith("require ") and not stripped.endswith("("):
                    parts = stripped[len("require "):].split()
                    if len(parts) >= 2:
                        name, version = parts[0], parts[1]
                        if name not in seen:
                            seen.add(name)
                            deps.append({"name": name, "version": version, "source": "go.mod"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] go.mod parse error: %s", exc)

    return deps


def _parse_cargo_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse Cargo.toml for Rust crate dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "Cargo.toml":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped in ("[dependencies]", "[dev-dependencies]",
                               "[build-dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("[") and "dependencies" not in stripped:
                    in_deps = False
                if in_deps and "=" in stripped and not stripped.startswith("#"):
                    name = stripped.split("=")[0].strip().strip('"').strip("'")
                    ver_part = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    # Handle table format: { version = "1.0" }
                    ver_match = re.search(r'version\s*=\s*["\']([^"\']+)', ver_part)
                    version = ver_match.group(1) if ver_match else ver_part.strip("{} ")
                    if name and name not in seen:
                        seen.add(name)
                        deps.append({"name": name, "version": version, "source": "Cargo.toml"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] Cargo.toml parse error: %s", exc)

    return deps


# ---------------------------------------------------------------------------
# Private helpers - classification and source lookup
# ---------------------------------------------------------------------------

def _classify_dep(root: Path, dep: Dict, build_system: str) -> str:
    """Classify a dependency as internal/external_known/external_unknown/needs_user_input."""
    name = dep.get("name", "").lower()
    if not name:
        return "external_unknown"

    # Check internal first (local source exists)
    local_path = _find_local_source(root, name)
    if local_path is not None:
        dep["hint_path"] = str(local_path)
        return "internal"

    # Check well-known external sets
    if build_system in ("python-pip", "python-pyproject", "python-setup", "python-pipenv"):
        clean = name.replace("-", "").replace("_", "").lower()
        for known in PYTHON_WELL_KNOWN:
            if clean == known.replace("-", "").replace("_", "").lower():
                return "external_known"

    elif build_system == "maven":
        group = dep.get("_group_id", "").lower()
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "gradle":
        group = name.split(":")[0].lower() if ":" in name else name.lower()
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "npm":
        for known in NODE_WELL_KNOWN:
            if name == known.lower() or name.startswith(f"@{known.lower()}"):
                return "external_known"

    elif build_system == "go":
        for known in GO_WELL_KNOWN:
            if name.startswith(known.lower()):
                return "external_known"
        # Standard library (golang.org/x, etc. already in set; plain std = external_known)
        if "/" not in name:
            return "external_known"

    elif build_system == "cargo":
        for known in RUST_WELL_KNOWN:
            if name == known.lower():
                return "external_known"

    # Short names without path separators are likely external but ambiguous
    if len(name) <= 3 or ("/" not in name and "." not in name and ":" not in name):
        return "external_unknown"

    # Longer unknown names with path-like structure may be internal
    return "needs_user_input"


def _find_local_source(root: Path, dep_name: str) -> Optional[Path]:
    """Try to locate a local source directory for a dependency name."""
    # Normalize: replace hyphens/dots with underscores for directory lookup
    candidates = [
        dep_name,
        dep_name.replace("-", "_"),
        dep_name.replace(".", "_"),
        dep_name.replace("-", ""),
    ]
    # Only look at the package name part (after last slash or colon)
    for sep in ("/", ":", "."):
        if sep in dep_name:
            suffix = dep_name.split(sep)[-1]
            candidates.append(suffix)
            candidates.append(suffix.replace("-", "_"))

    search_dirs = [root, root / "src", root / "lib", root / "packages",
                   root / "modules", root / "vendor", root.parent]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for cand in candidates:
            candidate_path = search_dir / cand
            if candidate_path.is_dir() and _dir_has_code(candidate_path):
                return candidate_path

    return None


def _dir_has_code(path: Path) -> bool:
    """Return True if the directory contains at least one source file."""
    code_extensions = {".py", ".java", ".kt", ".js", ".ts", ".go", ".rs", ".scala"}
    try:
        for child in path.rglob("*"):
            if child.suffix.lower() in code_extensions:
                return True
    except Exception:
        pass
    return False


def _detect_maven_project_group(root: Path) -> Optional[str]:
    """Extract groupId from root pom.xml for internal dep detection."""
    pom = root / "pom.xml"
    if not pom.is_file():
        return None
    try:
        tree = ET.parse(str(pom))
        root_el = tree.getroot()
        ns_match = re.match(r"\{([^}]+)\}", root_el.tag)
        ns = "{" + ns_match.group(1) + "}" if ns_match else ""
        group_el = root_el.find(f"{ns}groupId")
        if group_el is not None:
            return group_el.text.strip()
    except Exception:
        pass
    return None


def _build_question(
    root: Path,
    dep: Dict,
    build_system: str,
    reason: str,
) -> Optional[Dict]:
    """Build an actionable question dict for a dependency that needs user input."""
    name = dep.get("name", "?")
    version = dep.get("version", "*")

    if reason == "needs_input":
        question = (
            f"Is '{name}' (v{version}) an internal package with local source code, "
            f"or an external third-party library?"
        )
        suggestion = (
            f"If internal: provide the local path to '{name}' source relative to "
            f"project root. If external: add '{name}' to your well-known externals list."
        )
        options = [
            f"Internal - local path: <provide path>",
            f"External third-party library",
            f"Skip / not relevant",
        ]
    else:
        question = (
            f"The dependency '{name}' (v{version}) could not be classified. "
            f"Is this a known external library or an internal package?"
        )
        suggestion = (
            f"Search for '{name}' on your package registry. "
            f"If it is internal, provide a local path."
        )
        options = [
            f"External - well-known library",
            f"Internal - local path: <provide path>",
            f"Unknown / ignore",
        ]

    return {
        "dependency": name,
        "question": question,
        "suggestion": suggestion,
        "options": options,
    }


# ---------------------------------------------------------------------------
# Private helpers - graph merging
# ---------------------------------------------------------------------------

def _merge_sub_graph(main_graph: Any, sub_graph: Any, dep_name: str) -> None:
    """Merge nodes, classes, methods, and edges from sub_graph into main_graph."""
    # Merge nodes dict
    if hasattr(main_graph, "nodes") and hasattr(sub_graph, "nodes"):
        for fqn, node in sub_graph.nodes.items():
            if fqn not in main_graph.nodes:
                main_graph.nodes[fqn] = node

    # Merge classes dict
    if hasattr(main_graph, "classes") and hasattr(sub_graph, "classes"):
        for fqn, cls in sub_graph.classes.items():
            if fqn not in main_graph.classes:
                main_graph.classes[fqn] = cls

    # Merge methods dict
    if hasattr(main_graph, "methods") and hasattr(sub_graph, "methods"):
        for fqn, method in sub_graph.methods.items():
            if fqn not in main_graph.methods:
                main_graph.methods[fqn] = method

    # Merge edges list (avoid duplicates via set of tuples)
    if hasattr(main_graph, "edges") and hasattr(sub_graph, "edges"):
        existing_keys: set = set()
        for edge in main_graph.edges:
            caller = edge.get("caller", "")
            callee = edge.get("callee", "")
            existing_keys.add((caller, callee))

        for edge in sub_graph.edges:
            caller = edge.get("caller", "")
            callee = edge.get("callee", "")
            if (caller, callee) not in existing_keys:
                main_graph.edges.append(edge)
                existing_keys.add((caller, callee))

    # Merge files set
    if hasattr(main_graph, "files") and hasattr(sub_graph, "files"):
        main_graph.files.update(sub_graph.files)

    logger.debug(
        "[BuildDepResolver] Merged sub-graph for '%s' into main graph", dep_name
    )


# ---------------------------------------------------------------------------
# Private helpers - CallGraphBuilder import (4 strategies)
# ---------------------------------------------------------------------------

def _import_call_graph_builder(root: Path) -> Optional[Any]:
    """Import CallGraphBuilder using 4 fallback strategies.

    1. Relative package import (scripts.langgraph_engine.call_graph_builder)
    2. Sibling module import (call_graph_builder)
    3. sys.path manipulation + import
    4. importlib.util with absolute path
    """
    # Strategy 1: package import
    try:
        from scripts.langgraph_engine.call_graph_builder import CallGraphBuilder
        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 2: sibling import (same directory)
    try:
        from call_graph_builder import CallGraphBuilder
        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 3: sys.path manipulation
    try:
        import sys
        engine_dir = str(Path(__file__).parent)
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        from call_graph_builder import CallGraphBuilder
        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 4: importlib.util with absolute path
    try:
        import importlib.util
        module_path = Path(__file__).parent / "call_graph_builder.py"
        if not module_path.exists():
            # Try relative to project root
            module_path = root / "scripts" / "langgraph_engine" / "call_graph_builder.py"
        if module_path.exists():
            spec = importlib.util.spec_from_file_location(
                "call_graph_builder", str(module_path)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "CallGraphBuilder", None)
    except Exception as exc:
        logger.debug("[BuildDepResolver] importlib strategy failed: %s", exc)

    logger.warning("[BuildDepResolver] All 4 CallGraphBuilder import strategies failed")
    return None
