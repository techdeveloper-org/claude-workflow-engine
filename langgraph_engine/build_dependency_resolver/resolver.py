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

import logging
from pathlib import Path
from typing import Any, Dict, List

# D6: Well-known external dependency sets moved to registries.py leaf module.
# Helper functions live in parsers.py; imported here at top level so static
# analysis (ruff) can see the call graph -- previously hidden by a noqa: F821
# suppressor which masked 4 NameError bugs at runtime.
from .parsers import (
    _build_question,
    _classify_dep,
    _dir_has_code,
    _find_local_source,
    _import_call_graph_builder,
    _merge_sub_graph,
    _parse_raw_deps,
)

# Backward-compat re-exports: callers that still do
# `from langgraph_engine.build_dependency_resolver.resolver import PYTHON_WELL_KNOWN`
# continue to work even though the registries have moved to registries.py.
from .registries import (  # noqa: F401
    GO_WELL_KNOWN,
    JAVA_WELL_KNOWN,
    NODE_WELL_KNOWN,
    PYTHON_WELL_KNOWN,
    RUST_WELL_KNOWN,
)

logger = logging.getLogger(__name__)

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
            return {
                "build_system": "unknown",
                "build_files": [],
                "error": f"Project root does not exist: {project_root}",
            }

        detected_files: List[str] = []
        build_system = "unknown"

        # Priority-ordered checks
        checks = [
            ("maven", ["pom.xml"]),
            ("gradle", ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"]),
            ("npm", ["package.json"]),
            ("go", ["go.mod"]),
            ("cargo", ["Cargo.toml"]),
            ("python-pyproject", ["pyproject.toml"]),
            ("python-pip", ["requirements.txt", "requirements-dev.txt", "requirements-test.txt"]),
            ("python-setup", ["setup.py", "setup.cfg"]),
            ("python-pipenv", ["Pipfile"]),
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

        # D15: collect all detected system names (plural) for multi-build-file projects
        all_systems: List[str] = []
        for system, filenames in checks:
            for fname in filenames:
                if (root / fname).is_file():
                    if system not in all_systems:
                        all_systems.append(system)
                    break

        logger.debug("[BuildDepResolver] detect_build_system: system=%s files=%s", build_system, detected_files)
        return {
            "build_system": build_system,  # singular: primary system (backward compat)
            "build_systems": all_systems,  # plural: all detected systems (D15)
            "build_files": detected_files,
            "error": None,
        }

    except Exception as exc:
        logger.exception("[BuildDepResolver] detect_build_system failed")
        return {"build_system": "unknown", "build_systems": [], "build_files": [], "error": str(exc)}


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
            build_system,
            total,
            len(internal),
            len(external_known),
            len(external_unknown),
            len(needs_user_input),
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
            "internal": [],
            "external_known": [],
            "external_unknown": [],
            "needs_user_input": [],
            "total_deps": 0,
            "internal_count": 0,
            "external_count": 0,
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
                    failed.append({"name": dep_name, "reason": f"Local source path not found for '{dep_name}'"})
                    continue

                if not _dir_has_code(dep_path):
                    failed.append({"name": dep_name, "reason": f"No source files found under '{dep_path}'"})
                    continue

                logger.debug("[BuildDepResolver] Building sub-graph for '%s' at '%s'", dep_name, dep_path)
                builder = CallGraphBuilder(project_root=str(dep_path))
                sub_graph = builder.build()

                stats = sub_graph.get_stats() if hasattr(sub_graph, "get_stats") else {}
                resolved.append(
                    {
                        "name": dep_name,
                        "path": str(dep_path),
                        "classes": stats.get("total_classes", 0),
                        "methods": stats.get("total_methods", 0),
                        "graph": sub_graph,
                    }
                )
                logger.info(
                    "[BuildDepResolver] Sub-graph for '%s': %d classes, %d methods",
                    dep_name,
                    stats.get("total_classes", 0),
                    stats.get("total_methods", 0),
                )

            except Exception as dep_exc:
                logger.warning("[BuildDepResolver] Failed to build sub-graph for '%s': %s", dep_name, dep_exc)
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
                "before_resolved": 0,
                "after_resolved": 0,
                "improvement_pct": 0.0,
                "new_classes": 0,
                "new_methods": 0,
                "error": "graph is None",
            }

        # Snapshot before state (D8: capture class/method counts for delta tracking)
        before_stats = graph.get_stats() if hasattr(graph, "get_stats") else {}
        before_resolved = before_stats.get("resolved_edges", 0)
        before_total = before_stats.get("total_call_edges", 1)
        before_classes = before_stats.get("total_classes", 0)
        before_methods = before_stats.get("total_methods", 0)

        for dep_info in resolved_deps:
            sub_graph = dep_info.get("graph")
            if sub_graph is None:
                continue
            dep_name = dep_info.get("name", "?")
            try:
                _merge_sub_graph(graph, sub_graph, dep_name)
            except Exception as merge_exc:
                logger.warning("[BuildDepResolver] merge failed for '%s': %s", dep_name, merge_exc)

        # Invalidate caches before re-resolution (D7: use delattr, not setattr None)
        for attr in ("_call_paths", "_impact_map", "_resolved_edges"):
            if hasattr(graph, attr):
                try:
                    delattr(graph, attr)
                except AttributeError:
                    pass  # Already removed or slot-based -- safe to ignore

        # Re-run edge resolution
        if not hasattr(graph, "resolve_edges"):
            logger.warning("[BuildDepResolver] graph has no resolve_edges method -- skipping re-resolution")
        else:
            graph.resolve_edges()

        after_stats = graph.get_stats() if hasattr(graph, "get_stats") else {}
        after_resolved = after_stats.get("resolved_edges", 0)
        after_total = after_stats.get("total_call_edges", 1)

        # D8: compute actual deltas from before/after graph stats
        new_classes = after_stats.get("total_classes", 0) - before_classes
        new_methods = after_stats.get("total_methods", 0) - before_methods

        before_pct = (before_resolved / max(before_total, 1)) * 100.0
        after_pct = (after_resolved / max(after_total, 1)) * 100.0
        improvement = after_pct - before_pct

        logger.info(
            "[BuildDepResolver] enhance_call_graph: resolved edges %d->%d "
            "(%.1f%% -> %.1f%%, +%.1f pct pts), +%d classes, +%d methods",
            before_resolved,
            after_resolved,
            before_pct,
            after_pct,
            improvement,
            new_classes,
            new_methods,
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
            "before_resolved": 0,
            "after_resolved": 0,
            "improvement_pct": 0.0,
            "new_classes": 0,
            "new_methods": 0,
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

        logger.debug("[BuildDepResolver] get_unresolved_questions: %d questions generated", len(questions))
        return questions

    except Exception:
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

        resolve_result = resolve_internal_deps(project_root, deps_result.get("internal", []))

        enhance_result = enhance_call_graph(graph, resolve_result.get("resolved", []))

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
            "deps_result": {},
            "resolve_result": {},
            "enhance_result": {},
            "questions": [],
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Private helpers - build file parsers
# ---------------------------------------------------------------------------
