"""
Call Graph Analyzer - Pipeline-ready analysis functions for Steps 2, 10, 11.

Provides three main analysis functions that consume CallGraph data from
call_graph_builder.py and return structured dicts suitable for LangGraph
pipeline steps.

Functions:
    analyze_impact_before_change  - Step 2 (Plan): pre-change risk assessment
    get_implementation_context    - Step 10 (Implement): call paths + entry points
    review_change_impact          - Step 11 (Review): diff two call graph snapshots
    snapshot_call_graph           - Helper: capture pre-change snapshot

All functions are fail-safe: they return a fallback dict with
call_graph_available=False on any error rather than raising.

Python 3.8+ compatible. ASCII-only (cp1252-safe).
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of call_graph_builder (same directory)
# ---------------------------------------------------------------------------

def _import_builder():
    """Lazy import of call_graph_builder.  Returns module or None."""
    try:
        import importlib
        import sys

        # Allow import from same directory without modifying sys.path permanently
        _dir = str(Path(__file__).parent)
        if _dir not in sys.path:
            sys.path.insert(0, _dir)

        mod = importlib.import_module("call_graph_builder")
        return mod
    except Exception as exc:
        logger.warning("call_graph_builder import failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rel_file(fqn):
    """Extract the relative file path from a FQN (left of '::')."""
    if "::" in fqn:
        return fqn.split("::")[0]
    return ""


def _classify_risk(caller_count):
    """Classify risk level based on number of callers.

    low:    0-2 callers
    medium: 3-7 callers
    high:   8+ callers
    """
    if caller_count <= 2:
        return "low"
    if caller_count <= 7:
        return "medium"
    return "high"


def _methods_in_files(graph, file_set):
    """Return list of method FQNs whose file is in file_set."""
    result = []
    for fqn, method in graph.methods.items():
        if method.get("file", "").replace("\\", "/") in file_set:
            result.append(fqn)
    return result


def _normalize_file_set(project_root, target_files):
    """Normalize target_files to a set of relative posix paths."""
    if not target_files:
        return set()

    root = Path(project_root) if project_root else Path(".")
    normalized = set()
    for tf in target_files:
        p = Path(tf)
        # Try to make relative
        try:
            rel = p.relative_to(root)
            normalized.add(str(rel).replace("\\", "/"))
        except ValueError:
            # Already relative or absolute without common root
            normalized.add(str(p).replace("\\", "/"))
    return normalized


def _find_test_files(project_root, affected_fqns, file_set):
    """Find test files that reference any affected module.

    Searches project_root for files matching test_*.py or *_test.py that
    import names derived from the affected file paths.
    """
    test_files = []
    if not project_root:
        return test_files

    root = Path(project_root)
    # Collect module stems from affected FQNs
    affected_modules = set()
    for fqn in affected_fqns:
        stem = _rel_file(fqn)
        if stem:
            # Convert path to module-like identifier
            name = Path(stem).stem  # just filename without .py
            affected_modules.add(name)

    if not affected_modules:
        return test_files

    try:
        for py_file in root.rglob("*.py"):
            name = py_file.name
            if not (name.startswith("test_") or name.endswith("_test.py")):
                continue
            # Read the file and check for imports of affected modules
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for mod in affected_modules:
                if mod in content:
                    try:
                        rel = str(py_file.relative_to(root)).replace("\\", "/")
                    except ValueError:
                        rel = py_file.name
                    test_files.append(rel)
                    break
    except Exception as exc:
        logger.debug("Test file search failed: %s", exc)

    return sorted(set(test_files))


def _build_cross_file_deps(graph, file_set):
    """Build cross-file dependency list: other files calling into target files.

    Returns list of dicts:
        {"from_file": str, "to_file": str, "edge_count": int}
    """
    from collections import defaultdict

    counter = defaultdict(int)  # (from_file, to_file) -> count

    edges = graph.get_edges()
    for edge in edges:
        if edge.get("type") == "inheritance":
            continue
        from_file = _rel_file(edge["from"])
        to_file = _rel_file(edge["to"])
        if not from_file or not to_file:
            continue
        if to_file in file_set and from_file not in file_set:
            counter[(from_file, to_file)] += 1

    result = []
    for (from_f, to_f), count in sorted(counter.items(), key=lambda x: -x[1]):
        result.append({"from_file": from_f, "to_file": to_f, "edge_count": count})
    return result


def _avg_cyclomatic(graph):
    """Return average cyclomatic complexity across all methods."""
    values = [m.get("cyclomatic", 1) for m in graph.methods.values()]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _avg_cyclomatic_for_files(graph, file_set):
    """Return average cyclomatic complexity for methods in the given files."""
    values = [
        m.get("cyclomatic", 1)
        for m in graph.methods.values()
        if m.get("file", "").replace("\\", "/") in file_set
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _fallback(call_graph_available=False, extra=None):
    """Return a minimal fallback dict."""
    result = {"call_graph_available": call_graph_available}
    if extra:
        result.update(extra)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_impact_before_change(
    project_root,
    target_files=None,
    task_description="",
):
    """Analyze impact of planned changes before implementation (Step 2 - Plan).

    Builds a CallGraph for the project, then assesses the risk of changing
    the specified target_files by examining callers, dependencies, and
    cross-file coupling.

    Args:
        project_root: Path to the project root directory (str or Path).
        target_files: Optional list of file paths (absolute or relative) to
            analyze. When None, a summary of the whole graph is returned.
        task_description: Optional human-readable description for log context.

    Returns:
        dict with keys:
            target_files        - list of normalized relative paths analyzed
            affected_methods    - list of {"fqn", "callers_count", "risk"}
            affected_test_files - list of test file paths that reference targets
            risk_level          - "low" | "medium" | "high"
            safe_change_zones   - list of FQNs with 0 callers (leaf methods)
            danger_zones        - list of {"fqn", "callers_count"}
            cross_file_deps     - list of {"from_file", "to_file", "edge_count"}
            summary             - one-line human-readable summary
            call_graph_available - bool
    """
    try:
        mod = _import_builder()
        if mod is None:
            return _fallback(extra={
                "target_files": list(target_files) if target_files else [],
                "affected_methods": [],
                "affected_test_files": [],
                "risk_level": "low",
                "safe_change_zones": [],
                "danger_zones": [],
                "cross_file_deps": [],
                "summary": "Call graph unavailable - could not import builder.",
            })

        logger.debug(
            "analyze_impact_before_change: project=%s files=%s task=%s",
            project_root, target_files, task_description[:60] if task_description else "",
        )

        graph = mod.build_call_graph(project_root)
        if graph is None:
            return _fallback(extra={
                "target_files": list(target_files) if target_files else [],
                "affected_methods": [],
                "affected_test_files": [],
                "risk_level": "low",
                "safe_change_zones": [],
                "danger_zones": [],
                "cross_file_deps": [],
                "summary": "Could not build call graph for project.",
            })

        # Normalize target files to relative posix paths
        file_set = _normalize_file_set(project_root, target_files)
        norm_targets = sorted(file_set)

        # Determine which methods live in target files
        if file_set:
            target_methods = _methods_in_files(graph, file_set)
        else:
            # No specific files: analyze all methods
            target_methods = list(graph.methods.keys())

        # Compute impact map (callers per method)
        impact_map = graph.compute_impact_map()

        affected_methods = []
        safe_change_zones = []
        danger_zones = []

        for fqn in target_methods:
            callers = impact_map.get(fqn, set())
            n = len(callers)
            risk = _classify_risk(n)
            affected_methods.append({
                "fqn": fqn,
                "callers_count": n,
                "risk": risk,
            })
            if n == 0:
                safe_change_zones.append(fqn)
            elif n >= 5:
                danger_zones.append({"fqn": fqn, "callers_count": n})

        # Sort for deterministic output
        affected_methods.sort(key=lambda x: -x["callers_count"])
        safe_change_zones.sort()
        danger_zones.sort(key=lambda x: -x["callers_count"])

        # Overall risk: highest risk among affected methods
        if danger_zones:
            overall_risk = "high"
        elif any(m["callers_count"] >= 3 for m in affected_methods):
            overall_risk = "medium"
        else:
            overall_risk = "low"

        # Find test files
        all_affected_fqns = [m["fqn"] for m in affected_methods]
        test_files = _find_test_files(project_root, all_affected_fqns, file_set)

        # Cross-file dependencies
        cross_file_deps = _build_cross_file_deps(graph, file_set)

        # Build summary
        n_methods = len(affected_methods)
        n_danger = len(danger_zones)
        n_safe = len(safe_change_zones)
        if file_set:
            summary = (
                "%d method(s) in %d target file(s): risk=%s, "
                "%d safe zones, %d danger zones, %d cross-file deps."
                % (n_methods, len(file_set), overall_risk,
                   n_safe, n_danger, len(cross_file_deps))
            )
        else:
            summary = (
                "Full project: %d method(s) analyzed: risk=%s, "
                "%d safe zones, %d danger zones."
                % (n_methods, overall_risk, n_safe, n_danger)
            )

        return {
            "target_files": norm_targets,
            "affected_methods": affected_methods,
            "affected_test_files": test_files,
            "risk_level": overall_risk,
            "safe_change_zones": safe_change_zones,
            "danger_zones": danger_zones,
            "cross_file_deps": cross_file_deps,
            "summary": summary,
            "call_graph_available": True,
        }

    except Exception as exc:
        logger.error("analyze_impact_before_change failed: %s", exc, exc_info=True)
        return _fallback(extra={
            "target_files": list(target_files) if target_files else [],
            "affected_methods": [],
            "affected_test_files": [],
            "risk_level": "low",
            "safe_change_zones": [],
            "danger_zones": [],
            "cross_file_deps": [],
            "summary": "Analysis failed: %s" % str(exc),
        })


def get_implementation_context(
    project_root,
    target_files=None,
):
    """Gather call graph context needed during implementation (Step 10 - Implement).

    Builds a CallGraph and extracts call paths through target files, the
    entry points that eventually reach those files, and the test scope to
    run after changes.

    Args:
        project_root: Path to the project root directory (str or Path).
        target_files: Optional list of file paths to focus on. When None,
            context for the full project is returned.

    Returns:
        dict with keys:
            call_paths_through_targets - list of {"path": [...], "depth": int}
                                         (up to 15 paths)
            entry_points_affected      - list of FQNs that are entry points
                                         leading to target code
            cross_file_dependencies    - dict of {module_stem: [dep_stems]}
            suggested_test_scope       - list of test file paths
            stats                      - {"total_classes", "total_methods",
                                          "max_depth"}
            call_graph_available       - bool
    """
    try:
        mod = _import_builder()
        if mod is None:
            return _fallback(extra={
                "call_paths_through_targets": [],
                "entry_points_affected": [],
                "cross_file_dependencies": {},
                "suggested_test_scope": [],
                "stats": {"total_classes": 0, "total_methods": 0, "max_depth": 0},
            })

        logger.debug(
            "get_implementation_context: project=%s files=%s",
            project_root, target_files,
        )

        graph = mod.build_call_graph(project_root)
        if graph is None:
            return _fallback(extra={
                "call_paths_through_targets": [],
                "entry_points_affected": [],
                "cross_file_dependencies": {},
                "suggested_test_scope": [],
                "stats": {"total_classes": 0, "total_methods": 0, "max_depth": 0},
            })

        file_set = _normalize_file_set(project_root, target_files)

        # Determine target method FQNs
        if file_set:
            target_methods = set(_methods_in_files(graph, file_set))
        else:
            target_methods = set(graph.methods.keys())

        # Get call paths that pass through any target method
        all_paths = graph.compute_call_paths()
        paths_through = []
        for p in all_paths:
            path_fqns = set(p.get("path", []))
            if path_fqns & target_methods:
                paths_through.append({
                    "path": p["path"],
                    "depth": p.get("depth", len(p["path"])),
                })
        # Limit to 15
        paths_through = paths_through[:15]

        # Entry points: methods that are in call paths through targets AND
        # are not called by anyone else (i.e., they are path roots)
        edges = graph.get_edges()
        all_callees = set()
        for edge in edges:
            if edge.get("type") != "inheritance":
                all_callees.add(edge["to"])

        entry_points_affected = []
        for p in paths_through:
            if p["path"]:
                first = p["path"][0]
                if first in graph.methods and first not in all_callees:
                    entry_points_affected.append(first)

        entry_points_affected = sorted(set(entry_points_affected))

        # Cross-file dependencies: module -> list of modules it depends on
        # (within target scope or whole project if no target)
        cross_file_deps_raw = {}  # type: Dict[str, Set[str]]
        for edge in edges:
            if edge.get("type") == "inheritance":
                continue
            from_file = _rel_file(edge["from"])
            to_file = _rel_file(edge["to"])
            if not from_file or not to_file or from_file == to_file:
                continue

            # Focus: either from or to must be in target set (if set given)
            if file_set and from_file not in file_set and to_file not in file_set:
                continue

            from_stem = Path(from_file).stem
            to_stem = Path(to_file).stem
            if from_stem not in cross_file_deps_raw:
                cross_file_deps_raw[from_stem] = set()
            cross_file_deps_raw[from_stem].add(to_stem)

        cross_file_dependencies = {
            k: sorted(v) for k, v in sorted(cross_file_deps_raw.items())
        }

        # Suggested test scope: test files for affected modules
        all_affected_fqns = list(target_methods)
        test_scope = _find_test_files(project_root, all_affected_fqns, file_set)

        # Stats
        g_stats = graph.get_stats()
        stats = {
            "total_classes": g_stats.get("total_classes", 0),
            "total_methods": g_stats.get("total_methods", 0),
            "max_depth": g_stats.get("max_call_depth", 0),
        }

        return {
            "call_paths_through_targets": paths_through,
            "entry_points_affected": entry_points_affected,
            "cross_file_dependencies": cross_file_dependencies,
            "suggested_test_scope": test_scope,
            "stats": stats,
            "call_graph_available": True,
        }

    except Exception as exc:
        logger.error("get_implementation_context failed: %s", exc, exc_info=True)
        return _fallback(extra={
            "call_paths_through_targets": [],
            "entry_points_affected": [],
            "cross_file_dependencies": {},
            "suggested_test_scope": [],
            "stats": {"total_classes": 0, "total_methods": 0, "max_depth": 0},
        })


def review_change_impact(
    project_root,
    modified_files,
    pre_change_snapshot=None,
):
    """Review the impact of changes made during implementation (Step 11 - Review).

    Builds the current CallGraph and compares it against a pre-change
    snapshot (produced by snapshot_call_graph) to detect structural
    changes: new call edges, removed edges, orphaned methods, and potential
    breaking changes.

    Args:
        project_root:        Path to the project root directory (str or Path).
        modified_files:      List of files that were modified during Step 10.
        pre_change_snapshot: Optional dict from CallGraph.to_dict() captured
                             before Step 10 via snapshot_call_graph(). When
                             None, only the current state is analyzed.

    Returns:
        dict with keys:
            new_edges         - list of {"from", "to", "type"} added edges
            removed_edges     - list of {"from", "to", "type"} removed edges
            orphaned_methods  - list of FQNs no longer called by anyone
            breaking_changes  - list of {"method", "reason", "callers"} entries
            cyclomatic_change - {"before_avg", "after_avg", "delta"}
            max_call_depth    - int
            risk_assessment   - "safe" | "caution" | "risky"
            summary           - one-line human-readable summary
            call_graph_available - bool
    """
    try:
        mod = _import_builder()
        if mod is None:
            return _fallback(extra={
                "new_edges": [],
                "removed_edges": [],
                "orphaned_methods": [],
                "breaking_changes": [],
                "cyclomatic_change": {"before_avg": 0.0, "after_avg": 0.0, "delta": 0.0},
                "max_call_depth": 0,
                "risk_assessment": "safe",
                "summary": "Call graph unavailable - could not import builder.",
            })

        logger.debug(
            "review_change_impact: project=%s modified=%s snapshot=%s",
            project_root, modified_files,
            "present" if pre_change_snapshot else "absent",
        )

        graph = mod.build_call_graph(project_root)
        if graph is None:
            return _fallback(extra={
                "new_edges": [],
                "removed_edges": [],
                "orphaned_methods": [],
                "breaking_changes": [],
                "cyclomatic_change": {"before_avg": 0.0, "after_avg": 0.0, "delta": 0.0},
                "max_call_depth": 0,
                "risk_assessment": "safe",
                "summary": "Could not build call graph for project.",
            })

        file_set = _normalize_file_set(project_root, modified_files)

        # ---- Current graph edges and methods --------------------------------
        current_edges = graph.get_edges()
        # Key: (from, to, type) for set comparison
        current_edge_keys = set()
        for e in current_edges:
            if e.get("type") != "inheritance":
                current_edge_keys.add((e["from"], e["to"], e.get("type", "call")))

        # Reverse map: callee -> set of callers (current)
        current_callers = {}  # type: Dict[str, Set[str]]
        for e in current_edges:
            if e.get("type") != "inheritance":
                callee = e["to"]
                if callee not in current_callers:
                    current_callers[callee] = set()
                current_callers[callee].add(e["from"])

        # ---- Pre-change snapshot edges and methods --------------------------
        pre_edge_keys = set()  # type: Set[tuple]
        pre_methods = {}  # type: Dict[str, Any]  # fqn -> method node
        pre_avg_cyclomatic = 0.0

        if pre_change_snapshot and isinstance(pre_change_snapshot, dict):
            snapshot_edges = pre_change_snapshot.get("edges", [])
            for e in snapshot_edges:
                if e.get("type") != "inheritance":
                    pre_edge_keys.add((e["from"], e["to"], e.get("type", "call")))

            nodes = pre_change_snapshot.get("nodes", {})
            for m in nodes.get("methods", []):
                fqn = m.get("id") or m.get("fqn", "")
                if fqn:
                    pre_methods[fqn] = m

            # Average cyclomatic from snapshot
            cx_values = [m.get("cyclomatic", 1) for m in pre_methods.values()]
            if cx_values:
                pre_avg_cyclomatic = round(sum(cx_values) / len(cx_values), 2)

        # ---- Diff: new and removed edges ------------------------------------
        added_keys = current_edge_keys - pre_edge_keys
        removed_keys = pre_edge_keys - current_edge_keys

        new_edges = [
            {"from": f, "to": t, "type": tp}
            for f, t, tp in sorted(added_keys)
        ]
        removed_edges = [
            {"from": f, "to": t, "type": tp}
            for f, t, tp in sorted(removed_keys)
        ]

        # ---- Orphaned methods: in modified files, no longer called ----------
        # A method is orphaned when it exists now but has no callers AND
        # it was called in the snapshot.
        pre_callees = set(k[1] for k in pre_edge_keys)
        current_callees = set(k[1] for k in current_edge_keys)

        orphaned_methods = []
        for fqn in graph.methods:
            mfile = graph.methods[fqn].get("file", "").replace("\\", "/")
            if file_set and mfile not in file_set:
                continue
            # Was called before but is no longer called
            if fqn in pre_callees and fqn not in current_callees:
                orphaned_methods.append(fqn)

        orphaned_methods.sort()

        # ---- Breaking changes: methods in modified files that have callers
        # but whose signature appears to have changed.
        # Signature change heuristic: params list differs between snapshot
        # and current graph.
        breaking_changes = []
        for fqn, method in graph.methods.items():
            mfile = method.get("file", "").replace("\\", "/")
            if file_set and mfile not in file_set:
                continue

            pre_method = pre_methods.get(fqn)
            if pre_method is None:
                continue  # new method, not breaking

            # Check params change
            old_params = pre_method.get("params", [])
            new_params = method.get("params", [])
            if old_params != new_params:
                callers = current_callers.get(fqn, set())
                n_callers = len(callers)
                if n_callers > 0:
                    breaking_changes.append({
                        "method": fqn,
                        "reason": "signature_changed",
                        "callers": n_callers,
                    })

        breaking_changes.sort(key=lambda x: -x["callers"])

        # ---- Cyclomatic change ----------------------------------------------
        after_avg = _avg_cyclomatic_for_files(graph, file_set) if file_set else _avg_cyclomatic(graph)
        delta = round(after_avg - pre_avg_cyclomatic, 2)
        cyclomatic_change = {
            "before_avg": pre_avg_cyclomatic,
            "after_avg": after_avg,
            "delta": delta,
        }

        # ---- Max call depth (current) ---------------------------------------
        max_call_depth = graph.get_max_call_depth()

        # ---- Risk assessment ------------------------------------------------
        n_breaking = len(breaking_changes)
        n_removed = len(removed_edges)
        n_orphaned = len(orphaned_methods)
        complexity_raised = delta > 2.0

        if n_breaking > 0 or (n_removed > 5 and n_orphaned > 2):
            risk_assessment = "risky"
        elif complexity_raised or n_orphaned > 0 or n_removed > 0:
            risk_assessment = "caution"
        else:
            risk_assessment = "safe"

        # ---- Summary --------------------------------------------------------
        summary = (
            "Change review: +%d edges, -%d edges, %d orphaned, "
            "%d breaking changes, cyclomatic delta=%.1f -> risk=%s."
            % (
                len(new_edges), n_removed, n_orphaned,
                n_breaking, delta, risk_assessment,
            )
        )

        return {
            "new_edges": new_edges,
            "removed_edges": removed_edges,
            "orphaned_methods": orphaned_methods,
            "breaking_changes": breaking_changes,
            "cyclomatic_change": cyclomatic_change,
            "max_call_depth": max_call_depth,
            "risk_assessment": risk_assessment,
            "summary": summary,
            "call_graph_available": True,
        }

    except Exception as exc:
        logger.error("review_change_impact failed: %s", exc, exc_info=True)
        return _fallback(extra={
            "new_edges": [],
            "removed_edges": [],
            "orphaned_methods": [],
            "breaking_changes": [],
            "cyclomatic_change": {"before_avg": 0.0, "after_avg": 0.0, "delta": 0.0},
            "max_call_depth": 0,
            "risk_assessment": "safe",
            "summary": "Review failed: %s" % str(exc),
        })


def snapshot_call_graph(project_root):
    """Capture the current call graph state as a dict for later diffing.

    Call this before Step 10 starts and pass the result to
    review_change_impact() as pre_change_snapshot.

    Args:
        project_root: Path to the project root directory (str or Path).

    Returns:
        dict from CallGraph.to_dict() (version, stats, nodes, edges,
        call_paths), or {"call_graph_available": False} on failure.
    """
    try:
        mod = _import_builder()
        if mod is None:
            return {"call_graph_available": False}

        graph = mod.build_call_graph(project_root)
        if graph is None:
            return {"call_graph_available": False}

        result = graph.to_dict()
        result["call_graph_available"] = True
        return result

    except Exception as exc:
        logger.error("snapshot_call_graph failed: %s", exc, exc_info=True)
        return {"call_graph_available": False}
