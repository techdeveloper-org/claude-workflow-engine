"""Coverage Analyzer - Cross-reference CallGraph methods with existing test files.

Finds untested methods and prioritizes test generation by risk.
Uses AST scanning of test files (not pytest --cov) so no test execution is
required. Works entirely from source and test file inspection.

Usage:
    from langgraph_engine.analysis.coverage_analyzer import find_untested_methods

Python 3.8+ compatible. ASCII-only (cp1252-safe). No external dependencies.
"""

import ast
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Lazy import helpers - avoid import-time side effects
# ---------------------------------------------------------------------------


def _get_call_graph_builder():
    """Lazy import of CallGraphBuilder to avoid circular imports."""
    try:
        from langgraph_engine.parsers.call_graph_builder_legacy import CallGraphBuilder

        return CallGraphBuilder
    except ImportError:
        return None


def _build_graph(project_root):
    """Build a CallGraph for project_root, return None on failure."""
    try:
        CallGraphBuilder = _get_call_graph_builder()
        if CallGraphBuilder is None:
            return None
        builder = CallGraphBuilder(project_root)
        return builder.build()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Test directory discovery
# ---------------------------------------------------------------------------

_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
_TEST_FILE_PATTERNS = (
    re.compile(r"^test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r".*\.test\.py$"),
    re.compile(r".*_spec\.py$"),
)


def _find_test_dirs(project_root):
    """Find test directories under project_root."""
    root = Path(project_root)
    test_dirs = []

    for name in _TEST_DIR_NAMES:
        candidate = root / name
        if candidate.is_dir():
            test_dirs.append(candidate)

    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in {
                "__pycache__",
                "venv",
                ".venv",
                "node_modules",
                "dist",
                "build",
                ".tox",
                ".eggs",
            }:
                continue
            for name in _TEST_DIR_NAMES:
                candidate = child / name
                if candidate.is_dir() and candidate not in test_dirs:
                    test_dirs.append(candidate)
    except OSError:
        pass

    return test_dirs


def _is_test_file(path):
    """Return True if the filename looks like a test file."""
    name = Path(path).name
    for pattern in _TEST_FILE_PATTERNS:
        if pattern.match(name):
            return True
    return False


def _collect_test_files(test_dir):
    """Recursively collect *.py test files under test_dir."""
    files = []
    try:
        for py_file in Path(test_dir).rglob("*.py"):
            if _is_test_file(py_file):
                files.append(py_file)
    except OSError:
        pass
    return files


# ---------------------------------------------------------------------------
# AST scanner for test references
# ---------------------------------------------------------------------------


def find_test_references(test_dir):
    """Scan test files and extract which classes/methods they reference.

    Args:
        test_dir: Path to the directory containing test files.

    Returns:
        {
            "test_files": [str, ...],
            "references": {class_or_method_name: [test_files_that_reference_it]},
        }
    """
    result = {
        "test_files": [],
        "references": {},
    }

    try:
        test_files = _collect_test_files(test_dir)
        result["test_files"] = [str(f) for f in test_files]

        for tf in test_files:
            tf_str = str(tf)
            refs = _extract_references_from_file(tf)
            for name in refs:
                if name not in result["references"]:
                    result["references"][name] = []
                if tf_str not in result["references"][name]:
                    result["references"][name].append(tf_str)

    except Exception:
        pass

    return result


def _extract_references_from_file(test_file):
    """Extract referenced names from a single test file."""
    names = set()
    try:
        source = Path(test_file).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(test_file))
    except Exception:
        return names

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                names.add(name)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                names.add(name.split(".")[-1])

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fname = node.name
            if fname.startswith("test_"):
                inner = fname[5:]
                names.add(inner)
                for seg in inner.split("_"):
                    if seg and len(seg) > 2:
                        names.add(seg)

        elif isinstance(node, ast.Attribute):
            names.add(node.attr)

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.strip()
            if _looks_like_identifier(val):
                names.add(val)

        elif isinstance(node, ast.Name):
            names.add(node.id)

    return names


def _looks_like_identifier(s):
    """Return True if s could be a Python identifier (class or method name)."""
    if not s or len(s) < 2 or len(s) > 80:
        return False
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        return False
    if s in {"None", "True", "False", "self", "cls", "args", "kwargs"}:
        return False
    return True


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def _collect_all_references(project_root):
    """Collect all test references across all test directories."""
    test_dirs = _find_test_dirs(project_root)
    merged = {}

    for td in test_dirs:
        refs = find_test_references(td)
        for name, files in refs["references"].items():
            if name not in merged:
                merged[name] = []
            for f in files:
                if f not in merged[name]:
                    merged[name].append(f)

    return merged


def _is_method_tested(method_node, all_references):
    """Determine whether a method appears to be referenced in tests."""
    name = method_node.get("name", "")
    fqn = method_node.get("id", "")

    if name and name in all_references:
        return True

    parent = method_node.get("parent_class", "")
    if parent:
        cls_name = parent.split("::")[-1].split(".")[-1] if parent else ""
        if cls_name and cls_name in all_references:
            if name in all_references:
                return True

    if fqn:
        fqn_lower = fqn.lower()
        for ref_name in all_references:
            if ref_name.lower() in fqn_lower:
                return True

    return False


def find_untested_methods(project_root, call_graph=None):
    """Cross-reference CallGraph methods with existing test files.

    Args:
        project_root: Path to project root directory.
        call_graph:   Optional pre-built CallGraph instance.

    Returns:
        {
            "total_methods": int,
            "tested_methods": int,
            "untested_methods": int,
            "coverage_pct": float,
            "untested": [{"fqn": str, "name": str, "file": str, ...}],
            "tested": [{"fqn": str, "name": str}],
        }
    """
    empty = {
        "total_methods": 0,
        "tested_methods": 0,
        "untested_methods": 0,
        "coverage_pct": 0.0,
        "untested": [],
        "tested": [],
    }

    try:
        root = Path(project_root)

        if call_graph is None:
            call_graph = _build_graph(root)
        if call_graph is None:
            return empty

        edges = call_graph.get_edges()
        callers_count = {}
        for edge in edges:
            if edge.get("type") == "inheritance":
                continue
            callee = edge.get("to", "")
            callers_count[callee] = callers_count.get(callee, 0) + 1

        all_references = _collect_all_references(root)

        tested = []
        untested = []

        for fqn, method in call_graph.methods.items():
            method_name = method.get("name", "")

            if method_name.startswith("__") and method_name.endswith("__"):
                continue

            if _is_method_tested(method, all_references):
                tested.append({"fqn": fqn, "name": method_name})
            else:
                untested.append(
                    {
                        "fqn": fqn,
                        "name": method_name,
                        "file": method.get("file", ""),
                        "callers_count": callers_count.get(fqn, 0),
                        "cyclomatic": method.get("cyclomatic", 1),
                    }
                )

        total = len(tested) + len(untested)
        coverage_pct = (len(tested) / total * 100.0) if total > 0 else 0.0

        return {
            "total_methods": total,
            "tested_methods": len(tested),
            "untested_methods": len(untested),
            "coverage_pct": round(coverage_pct, 2),
            "untested": untested,
            "tested": tested,
        }

    except Exception:
        return empty


def prioritize_untested(untested_methods, call_graph=None):
    """Prioritize untested methods by risk score.

    Args:
        untested_methods: List of untested method dicts from find_untested_methods().
        call_graph:       Optional CallGraph instance.

    Returns:
        Sorted list (highest risk first) with "risk_score" field added.
    """
    if not untested_methods:
        return []

    scored = []
    try:
        for m in untested_methods:
            name = m.get("name", "")
            callers = m.get("callers_count", 0)
            cyclomatic = m.get("cyclomatic", 1)
            is_public = 1 if (name and not name.startswith("_")) else 0
            score = callers * 2.0 + cyclomatic * 1.5 + is_public * 3.0
            entry = dict(m)
            entry["risk_score"] = round(score, 2)
            scored.append(entry)

        scored.sort(key=lambda x: x["risk_score"], reverse=True)

    except Exception:
        pass

    return scored


def suggest_test_scope(project_root, modified_files=None, call_graph=None, max_tests=20):
    """Smart test scope suggestion combining coverage gaps + modified files.

    Args:
        project_root:   Path to project root.
        modified_files: Optional list of recently changed file paths.
        call_graph:     Optional pre-built CallGraph instance.
        max_tests:      Maximum number of methods to suggest.

    Returns:
        Dict with scope, methods_to_test, existing_tests_to_run, and coverage estimates.
    """
    empty = {
        "scope": "broad",
        "methods_to_test": [],
        "existing_tests_to_run": [],
        "estimated_new_tests": 0,
        "coverage_before": 0.0,
        "coverage_after_estimate": 0.0,
    }

    try:
        root = Path(project_root)

        if call_graph is None:
            call_graph = _build_graph(root)
        if call_graph is None:
            return empty

        coverage = find_untested_methods(root, call_graph=call_graph)
        coverage_before = coverage["coverage_pct"]
        all_untested = coverage["untested"]
        total_methods = coverage["total_methods"]

        modified_rel = set()
        if modified_files:
            for mf in modified_files:
                try:
                    rel = str(Path(mf).relative_to(root)).replace("\\", "/")
                    modified_rel.add(rel)
                except ValueError:
                    modified_rel.add(str(mf).replace("\\", "/"))

        all_references = _collect_all_references(root)
        existing_tests_to_run = _find_tests_for_modified_files(root, modified_rel, all_references)

        edges = call_graph.get_edges()
        callee_to_callers = {}
        for edge in edges:
            if edge.get("type") == "inheritance":
                continue
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if dst not in callee_to_callers:
                callee_to_callers[dst] = set()
            callee_to_callers[dst].add(src)

        modified_method_fqns = set()
        if modified_rel:
            for fqn, method in call_graph.methods.items():
                mfile = method.get("file", "").replace("\\", "/")
                if mfile in modified_rel:
                    modified_method_fqns.add(fqn)

        priority1 = []
        priority2 = []
        priority3 = []

        callers_of_modified = set()
        for fqn in modified_method_fqns:
            callers_of_modified.update(callee_to_callers.get(fqn, set()))

        for m in all_untested:
            fqn = m.get("fqn", "")
            mfile = m.get("file", "").replace("\\", "/")
            if modified_rel and mfile in modified_rel:
                priority1.append(m)
            elif fqn in callers_of_modified:
                priority2.append(m)
            else:
                priority3.append(m)

        priority1 = prioritize_untested(priority1, call_graph)
        priority2 = prioritize_untested(priority2, call_graph)
        priority3 = prioritize_untested(priority3, call_graph)

        methods_to_test = []
        for bucket in (priority1, priority2, priority3):
            for m in bucket:
                if len(methods_to_test) >= max_tests:
                    break
                methods_to_test.append(m)

        scope = "focused" if (modified_rel and priority1) else "broad"

        coverage_after = 0.0
        if total_methods > 0:
            current_tested = coverage["tested_methods"]
            future_tested = min(total_methods, current_tested + len(methods_to_test))
            coverage_after = round(future_tested / total_methods * 100.0, 2)

        return {
            "scope": scope,
            "methods_to_test": methods_to_test,
            "existing_tests_to_run": existing_tests_to_run,
            "estimated_new_tests": len(methods_to_test),
            "coverage_before": coverage_before,
            "coverage_after_estimate": coverage_after,
        }

    except Exception:
        return empty


def _find_tests_for_modified_files(root, modified_rel, all_references):
    """Return test file paths that appear to cover any of the modified files."""
    relevant = set()
    try:
        if not modified_rel:
            return []

        modified_stems = set()
        for rel_path in modified_rel:
            stem = Path(rel_path).stem
            modified_stems.add(stem)
            for prefix in ("service_", "manager_", "handler_"):
                if stem.startswith(prefix):
                    modified_stems.add(stem[len(prefix) :])

        test_dirs = _find_test_dirs(root)
        for td in test_dirs:
            for tf in _collect_test_files(td):
                tf_str = str(tf)
                tf_stem = Path(tf).stem.lower()

                for stem in modified_stems:
                    stem_lower = stem.lower()
                    if tf_stem == "test_" + stem_lower or tf_stem == stem_lower + "_test" or stem_lower in tf_stem:
                        relevant.add(tf_str)
                        break

                if tf_str in relevant:
                    continue
                refs = _extract_references_from_file(tf)
                for stem in modified_stems:
                    if stem in refs or stem.lower() in refs:
                        relevant.add(tf_str)
                        break

    except Exception:
        pass

    return sorted(relevant)


def generate_coverage_report(project_root, call_graph=None):
    """Full coverage analysis report.

    Args:
        project_root: Path to project root directory.
        call_graph:   Optional pre-built CallGraph instance.

    Returns:
        Coverage report dict with per-file stats and high-risk untested methods.
    """
    empty = {
        "total_methods": 0,
        "tested_methods": 0,
        "untested_methods": 0,
        "coverage_pct": 0.0,
        "by_file": {},
        "high_risk_untested": [],
        "fully_tested_files": [],
        "zero_coverage_files": [],
    }

    try:
        root = Path(project_root)

        if call_graph is None:
            call_graph = _build_graph(root)
        if call_graph is None:
            return empty

        coverage = find_untested_methods(root, call_graph=call_graph)

        by_file = {}

        for m in coverage["tested"]:
            fqn = m["fqn"]
            method_node = call_graph.methods.get(fqn, {})
            file_rel = method_node.get("file", "unknown")
            if file_rel not in by_file:
                by_file[file_rel] = {"methods": 0, "tested": 0, "untested": 0, "pct": 0.0}
            by_file[file_rel]["methods"] += 1
            by_file[file_rel]["tested"] += 1

        for m in coverage["untested"]:
            file_rel = m.get("file", "unknown")
            if file_rel not in by_file:
                by_file[file_rel] = {"methods": 0, "tested": 0, "untested": 0, "pct": 0.0}
            by_file[file_rel]["methods"] += 1
            by_file[file_rel]["untested"] += 1

        for file_rel, stats in by_file.items():
            total = stats["methods"]
            if total > 0:
                stats["pct"] = round(stats["tested"] / total * 100.0, 2)

        high_risk = prioritize_untested(coverage["untested"], call_graph)[:10]

        fully_tested = [f for f, s in by_file.items() if s["methods"] > 0 and s["pct"] >= 100.0]
        zero_coverage = [f for f, s in by_file.items() if s["methods"] > 0 and s["tested"] == 0]

        return {
            "total_methods": coverage["total_methods"],
            "tested_methods": coverage["tested_methods"],
            "untested_methods": coverage["untested_methods"],
            "coverage_pct": coverage["coverage_pct"],
            "by_file": by_file,
            "high_risk_untested": high_risk,
            "fully_tested_files": sorted(fully_tested),
            "zero_coverage_files": sorted(zero_coverage),
        }

    except Exception:
        return empty
