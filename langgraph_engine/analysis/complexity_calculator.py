"""Complexity Calculator - Project complexity scoring for Level 1 context sync.

Produces a 1-10 complexity score based on:
  - File count (Python + total)
  - Lines of code (LOC)
  - Dependency count (requirements.txt / pyproject.toml / package.json)

Scoring matrix:
  1-3  : < 5 files  OR < 500 LOC    (trivial / micro project)
  4-7  : 5-100 files AND 500-5000 LOC  (typical project)
  8-10 : > 100 files OR > 5000 LOC  (large / enterprise project)

Usage:
    from langgraph_engine.analysis.complexity_calculator import calculate_complexity, should_plan
    score = calculate_complexity("/path/to/project")
    plan_needed = should_plan(score, task_type="refactoring")
"""

import json
import sys
from pathlib import Path
from typing import Optional

from langgraph_engine.core.logger_factory import get_logger

try:
    from langgraph_engine.engine_logging.error_logger import ErrorLogger
except ImportError:
    ErrorLogger = None  # type: ignore

_LOG = get_logger(__name__)


# ============================================================================
# SCORING CONSTANTS
# ============================================================================

FILE_TINY = 5
FILE_SMALL = 20
FILE_MEDIUM = 100

LOC_TINY = 500
LOC_SMALL = 2000
LOC_MEDIUM = 5000

DEP_NONE = 0
DEP_FEW = 10
DEP_MANY = 30

PLAN_THRESHOLD_DEFAULT = 6
PLAN_THRESHOLD_BUG_FIX = 4
PLAN_THRESHOLD_REFACTOR = 1


# ============================================================================
# MAIN CALCULATION
# ============================================================================


def calculate_complexity(project_path: str, session_id: Optional[str] = None) -> int:
    """Calculate project complexity score.

    Args:
        project_path: Absolute path to project root
        session_id: Optional session ID for error logging

    Returns:
        Integer 1-10 complexity score.
    """
    logger = None
    if session_id and ErrorLogger:
        try:
            logger = ErrorLogger(session_id)
        except Exception as le:
            _LOG.debug(f"[complexity] ErrorLogger init failed: {le}")

    path = Path(project_path)
    if not path.exists():
        if logger:
            logger.log_error(
                "Level 1",
                "Project path does not exist: " + str(project_path),
                severity="WARNING",
                error_type="PathNotFound",
                recovery_action="Using default complexity score 3",
            )
        return 3

    try:

        def _is_excluded(p: Path) -> bool:
            excluded_dirs = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".tox", "dist", "build"}
            return any(part in excluded_dirs for part in p.parts)

        py_files = [f for f in path.rglob("*.py") if not _is_excluded(f)]

        total_loc = 0
        for py_file in py_files:
            try:
                lines = py_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                code_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
                total_loc += len(code_lines)
            except OSError as exc:
                _LOG.debug(f"[complexity] py file read skipped: {exc}")

        dep_count = _count_dependencies(path)

        file_score = _file_score(len(py_files))
        loc_score = _loc_score(total_loc)
        dep_score = _dep_score(dep_count)

        raw_score = (file_score * 0.40) + (loc_score * 0.45) + (dep_score * 0.15)
        score = int(round(raw_score))
        score = max(1, min(10, score))

        if logger:
            logger.log_validation_result(
                "Level 1",
                "Complexity calculation",
                True,
                details=("py_files={}, loc={}, deps={}, score={}".format(len(py_files), total_loc, dep_count, score)),
            )

        return score

    except Exception as exc:
        if logger:
            logger.log_error(
                "Level 1",
                "Complexity calculation failed: " + str(exc),
                severity="ERROR",
                error_type="CalculationError",
                recovery_action="Returning default score 5",
            )
        return 5


# ============================================================================
# SCORING HELPERS
# ============================================================================


def _file_score(py_file_count: int) -> int:
    """Map file count to 1-10 score."""
    if py_file_count < FILE_TINY:
        return 2
    elif py_file_count < FILE_SMALL:
        return 4
    elif py_file_count < FILE_MEDIUM:
        return 6
    else:
        return 9


def _loc_score(loc: int) -> int:
    """Map lines of code to 1-10 score."""
    if loc < LOC_TINY:
        return 2
    elif loc < LOC_SMALL:
        return 4
    elif loc < LOC_MEDIUM:
        return 6
    else:
        return 9


def _dep_score(dep_count: int) -> int:
    """Map dependency count to 1-10 score."""
    if dep_count == DEP_NONE:
        return 1
    elif dep_count < DEP_FEW:
        return 4
    elif dep_count < DEP_MANY:
        return 6
    else:
        return 9


def _count_dependencies(project_root: Path) -> int:
    """Count declared dependencies from common manifests."""
    dep_count = 0

    req_txt = project_root / "requirements.txt"
    if req_txt.exists():
        try:
            lines = req_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
            dep_count += sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))
        except OSError as exc:
            _LOG.debug(f"[complexity] requirements.txt read skipped: {exc}")

    pyproject = project_root / "pyproject.toml"
    if pyproject.exists() and dep_count == 0:
        try:
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            in_deps = False
            for ln in content.splitlines():
                stripped = ln.strip()
                if stripped.startswith("[project.dependencies]") or stripped.startswith("dependencies"):
                    in_deps = True
                elif stripped.startswith("[") and in_deps:
                    in_deps = False
                elif in_deps and stripped.startswith('"') or (in_deps and stripped.startswith("'")):
                    dep_count += 1
        except OSError as exc:
            _LOG.debug(f"[complexity] pyproject.toml read skipped: {exc}")

    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            dep_count += len(data.get("dependencies", {}))
            dep_count += len(data.get("devDependencies", {}))
        except (OSError, ValueError) as exc:
            _LOG.debug(f"[complexity] package.json read skipped: {exc}")

    return dep_count


# ============================================================================
# PLANNING DECISION
# ============================================================================


def should_plan(complexity_score: int, task_type: str = "general") -> bool:
    """Determine whether the task requires a planning phase.

    Args:
        complexity_score: 1-10 score returned by calculate_complexity()
        task_type: Task category: "general", "bug_fix", "refactoring", "feature", etc.

    Returns:
        True if a plan phase should be executed before implementation.
    """
    task_lower = task_type.lower().strip()

    if "refactor" in task_lower:
        return True

    if "bug" in task_lower or "fix" in task_lower or "hotfix" in task_lower:
        return complexity_score >= PLAN_THRESHOLD_BUG_FIX

    return complexity_score >= PLAN_THRESHOLD_DEFAULT


# ============================================================================
# DETAILED REPORT
# ============================================================================


def complexity_report(project_path: str) -> dict:
    """Generate a detailed complexity report dict.

    Args:
        project_path: Path to project root

    Returns:
        Dict with all metrics and the final score.
    """
    path = Path(project_path)
    if not path.exists():
        return {"error": "Path not found", "score": 3}

    def _is_excluded(p: Path) -> bool:
        excluded_dirs = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".tox", "dist", "build"}
        return any(part in excluded_dirs for part in p.parts)

    py_files = [f for f in path.rglob("*.py") if not _is_excluded(f)]
    total_loc = 0
    for pf in py_files:
        try:
            lines = pf.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_loc += sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))
        except OSError as exc:
            _LOG.debug(f"[complexity] py file read skipped: {exc}")

    dep_count = _count_dependencies(path)
    score = calculate_complexity(project_path)

    return {
        "project_path": str(path),
        "py_file_count": len(py_files),
        "lines_of_code": total_loc,
        "dependency_count": dep_count,
        "file_score": _file_score(len(py_files)),
        "loc_score": _loc_score(total_loc),
        "dep_score": _dep_score(dep_count),
        "complexity_score": score,
        "plan_required_general": should_plan(score, "general"),
        "plan_required_bug_fix": should_plan(score, "bug_fix"),
        "plan_required_refactor": should_plan(score, "refactoring"),
    }


def _extract_method_call_stack(project_root: Path) -> dict:
    """Extract method call relationships using proper call graph builder.

    Args:
        project_root: Path to project root

    Returns:
        Dict with call graph metrics, or empty dict on failure.
    """
    try:
        from langgraph_engine.parsers.call_graph_builder_legacy import get_call_graph_metrics

        return get_call_graph_metrics(str(project_root))
    except (ImportError, Exception):
        return {}


def calculate_graph_complexity(
    project_path: str,
    session_id: Optional[str] = None,
    tech_stack: Optional[list] = None,
):
    """Calculate graph-based complexity using code-graph-analyzer.

    Uses NetworkX for dependency graph analysis and Lizard for cyclomatic
    complexity. Returns a 1-25 score, graph metrics dict, and avg cyclomatic.

    Gracefully degrades to (0, {}, 0.0) if networkx/lizard unavailable.

    Args:
        project_path: Absolute path to project root.
        session_id: Optional session ID for logging.
        tech_stack: Optional list of technology names.

    Returns:
        Tuple of (graph_score: int, graph_metrics: dict, cyclomatic_avg: float).
        graph_score=0 means graph analysis was unavailable.
    """
    try:
        project_root = Path(project_path)

        local_graph_cache = project_root / ".claude-graph" / "graph-analysis.json"
        if local_graph_cache.exists():
            try:
                cached = json.loads(local_graph_cache.read_text(encoding="utf-8"))
                if "graph_complexity_score" in cached and "graph_metrics" in cached:
                    graph_score = cached["graph_complexity_score"]
                    graph_metrics = cached["graph_metrics"]
                    cyclomatic_avg = cached.get("cyclomatic_metrics", {}).get("avg_cyclomatic", 0.0)

                    call_stack = _extract_method_call_stack(project_root)
                    if call_stack and call_stack.get("call_graph_available"):
                        graph_metrics["method_call_depth"] = call_stack.get("method_call_depth", 0)
                        graph_metrics["method_call_count"] = call_stack.get("method_call_count", 0)
                        graph_metrics["total_classes"] = call_stack.get("total_classes", 0)
                        graph_metrics["total_methods"] = call_stack.get("total_methods", 0)
                        graph_metrics["entry_points"] = call_stack.get("entry_points", [])
                        graph_metrics["resolved_ratio"] = call_stack.get("resolved_ratio", 0.0)
                        graph_metrics["avg_method_complexity"] = call_stack.get("avg_method_complexity", 0.0)
                        graph_metrics["max_method_complexity"] = call_stack.get("max_method_complexity", 0)

                    return graph_score, graph_metrics, cyclomatic_avg
            except (json.JSONDecodeError, KeyError):
                pass

        analyzer_dir = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "architecture"
            / "03-execution-system"
            / "00-code-graph-analysis"
        )
        analyzer_module = analyzer_dir / "code-graph-analyzer.py"

        if not analyzer_module.exists():
            return 0, {}, 0.0

        import importlib.util

        spec = importlib.util.spec_from_file_location("code_graph_analyzer", str(analyzer_module))
        if spec is None or spec.loader is None:
            return 0, {}, 0.0

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not getattr(mod, "HAS_NETWORKX", False):
            return 0, {}, 0.0

        analyzer = mod.CodeGraphAnalyzer(
            project_path,
            tech_stack=tech_stack or [],
            session_id=session_id or "unknown",
        )
        graph_score = analyzer.run()
        analyzer.save()

        graph_metrics = analyzer.metrics or {}
        cyclomatic_avg = (analyzer.cyclomatic or {}).get("avg_cyclomatic", 0.0)

        try:
            local_graph_cache.parent.mkdir(parents=True, exist_ok=True)
            result_data = {
                "version": "1.2.0",
                "analyzed_at": __import__("datetime").datetime.now().isoformat(),
                "project_dir": str(project_root),
                "files_analyzed": len(analyzer.files),
                "graph_metrics": graph_metrics,
                "cyclomatic_metrics": analyzer.cyclomatic or {},
                "graph_complexity_score": graph_score,
            }
            local_graph_cache.write_text(json.dumps(result_data, indent=2, default=str), encoding="utf-8")
        except OSError as exc:
            _LOG.debug(f"[complexity] graph cache write skipped: {exc}")

        call_stack = _extract_method_call_stack(project_root)
        if call_stack and call_stack.get("call_graph_available"):
            graph_metrics["method_call_depth"] = call_stack.get("method_call_depth", 0)
            graph_metrics["method_call_count"] = call_stack.get("method_call_count", 0)
            graph_metrics["total_classes"] = call_stack.get("total_classes", 0)
            graph_metrics["total_methods"] = call_stack.get("total_methods", 0)
            graph_metrics["entry_points"] = call_stack.get("entry_points", [])
            graph_metrics["resolved_ratio"] = call_stack.get("resolved_ratio", 0.0)
            graph_metrics["avg_method_complexity"] = call_stack.get("avg_method_complexity", 0.0)
            graph_metrics["max_method_complexity"] = call_stack.get("max_method_complexity", 0)

        return graph_score, graph_metrics, cyclomatic_avg

    except Exception as exc:
        logger = None
        if session_id and ErrorLogger:
            try:
                logger = ErrorLogger(session_id)
            except Exception as le:
                _LOG.debug(f"[complexity] ErrorLogger init failed: {le}")
        if logger:
            logger.log_error(
                "Level 1",
                "Graph complexity calculation failed: " + str(exc),
                severity="WARNING",
                error_type="GraphAnalysisError",
                recovery_action="Using simple score only (graph_score=0)",
            )
        return 0, {}, 0.0


if __name__ == "__main__":
    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    report = complexity_report(project_dir)
    print(json.dumps(report, indent=2))
