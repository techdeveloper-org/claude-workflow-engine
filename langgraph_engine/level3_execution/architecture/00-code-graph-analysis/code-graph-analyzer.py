"""
Code Graph Analyzer - Step 3.0.1
==================================

Builds a dependency graph from actual source code and calculates structural
complexity metrics. Combines with keyword complexity using:

    FINAL_COMPLEXITY = (keyword * 0.3) + (graph * 0.7)

Policy: policies/03-execution-system/00-code-graph-analysis/code-graph-analysis-policy.md

Usage (standalone):
    python code-graph-analyzer.py /path/to/project [session_id] [tech_stack_csv]

Usage (programmatic via complexity_calculator.py):
    from code_graph_analyzer import CodeGraphAnalyzer, HAS_NETWORKX

    analyzer = CodeGraphAnalyzer(project_path, tech_stack=["Python"], session_id="S-001")
    score = analyzer.run()   # returns int 1-25
    analyzer.save()          # writes graph-analysis.json to session dir

Scoring (0-25 accumulation, then clamped 1-25):
    Factor 1 - Graph Size          (0-5)
    Factor 2 - Dependency Density  (0-5)
    Factor 3 - Max Betweenness     (0-5)
    Factor 4 - Average Fan-Out     (0-5)
    Factor 5 - Longest Path        (0-5)

Python 3.8+ compatible.
ASCII-only source (cp1252-safe for Windows).

Dependencies:
    networkx  - required for graph analysis  (pip install networkx)
    lizard    - optional for cyclomatic metrics (pip install lizard)
"""

import ast
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]

try:
    import lizard  # type: ignore[import]

    HAS_LIZARD = True
except ImportError:
    HAS_LIZARD = False
    lizard = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILES = 500  # Performance safety limit
MAX_FILE_SIZE_KB = 100  # Skip files larger than this
TIMEOUT_SECONDS = 10  # Hard analysis timeout

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".tox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage_html",
    "htmlcov",
}

# Extension to language mapping
LANG_EXTENSIONS = {
    "Python": [".py"],
    "Java": [".java"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
    "TypeScript": [".ts", ".tsx"],
    "Go": [".go"],
    "Kotlin": [".kt"],
    "Rust": [".rs"],
    "CSharp": [".cs"],
    "CPP": [".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"],
}

# Default extensions when tech_stack is unknown
DEFAULT_EXTENSIONS = [".py", ".java", ".js", ".ts", ".go"]

# Session dir for saving output (matches complexity_calculator.py expectation)
SESSION_BASE = Path.home() / ".claude" / "memory" / "logs" / "sessions"


# ---------------------------------------------------------------------------
# File Discovery
# ---------------------------------------------------------------------------


def _is_excluded(path: Path) -> bool:
    """Return True if any part of path is in the excluded directories set."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def _get_target_extensions(tech_stack: List[str]) -> List[str]:
    """Resolve file extensions to scan based on detected tech stack."""
    extensions = []
    stack_lower = [t.lower() for t in tech_stack]
    for lang, exts in LANG_EXTENSIONS.items():
        if lang.lower() in stack_lower or any(lang.lower() in s for s in stack_lower):
            extensions.extend(exts)
    if not extensions:
        extensions = DEFAULT_EXTENSIONS
    return list(set(extensions))


def discover_files(project_root: Path, tech_stack: List[str]) -> List[Path]:
    """Walk project directory and return up to MAX_FILES source files.

    Args:
        project_root: Absolute path to project root.
        tech_stack: List of detected language/framework names.

    Returns:
        List of Path objects for discovered source files.
    """
    target_exts = set(_get_target_extensions(tech_stack))
    found = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune excluded directories in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        for fname in filenames:
            if len(found) >= MAX_FILES:
                break
            fpath = Path(dirpath) / fname
            if fpath.suffix not in target_exts:
                continue
            if _is_excluded(fpath):
                continue
            try:
                size_kb = fpath.stat().st_size / 1024
                if size_kb > MAX_FILE_SIZE_KB:
                    continue
            except OSError:
                continue
            found.append(fpath)

        if len(found) >= MAX_FILES:
            break

    return found


# ---------------------------------------------------------------------------
# Import / Dependency Extraction
# ---------------------------------------------------------------------------


def _extract_python_imports(source: str, filename: str) -> List[Tuple[str, str]]:
    """Parse Python source with ast and extract import edges.

    Returns list of (importer, importee) string pairs.
    """
    edges = []
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return edges

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Take only the top-level module name
                top_module = alias.name.split(".")[0]
                edges.append((filename, top_module))

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_module = node.module.split(".")[0]
                edges.append((filename, top_module))

    return edges


def _extract_java_imports(source: str, filename: str) -> List[Tuple[str, str]]:
    """Extract Java import edges using regex."""
    edges = []
    pattern = re.compile(r"import\s+(?:static\s+)?[\w.]+\.(\w+);")
    for match in pattern.finditer(source):
        edges.append((filename, match.group(1)))
    # Inheritance
    for match in re.finditer(r"\bextends\s+(\w+)", source):
        edges.append((filename, match.group(1)))
    for match in re.finditer(r"\bimplements\s+([\w,\s]+)", source):
        for iface in match.group(1).split(","):
            iface = iface.strip()
            if iface:
                edges.append((filename, iface))
    return edges


def _extract_js_ts_imports(source: str, filename: str) -> List[Tuple[str, str]]:
    """Extract JavaScript/TypeScript import edges using regex."""
    edges = []
    # ES6: import X from 'module' or import { X } from 'module'
    for match in re.finditer(r"import\s+.*?from\s+['\"](.+?)['\"]", source, re.DOTALL):
        module = match.group(1).split("/")[-1].split(".")[0]
        edges.append((filename, module))
    # CommonJS: require('module')
    for match in re.finditer(r"require\s*\(\s*['\"](.+?)['\"]\s*\)", source):
        module = match.group(1).split("/")[-1].split(".")[0]
        edges.append((filename, module))
    return edges


def _extract_go_imports(source: str, filename: str) -> List[Tuple[str, str]]:
    """Extract Go import edges using regex."""
    edges = []
    # Single import
    for match in re.finditer(r'import\s+"([^"]+)"', source):
        pkg = match.group(1).split("/")[-1]
        edges.append((filename, pkg))
    # Import block: import ( "pkg1" "pkg2" )
    block_match = re.search(r"import\s*\(([^)]+)\)", source, re.DOTALL)
    if block_match:
        block = block_match.group(1)
        for m in re.finditer(r'"([^"]+)"', block):
            pkg = m.group(1).split("/")[-1]
            edges.append((filename, pkg))
    return edges


def _extract_generic_imports(source: str, filename: str) -> List[Tuple[str, str]]:
    """Fallback: generic import pattern matching for unsupported languages."""
    edges = []
    for match in re.finditer(r"import\s+[\w.]+", source):
        token = match.group(0).split()[-1].split(".")[-1]
        if token:
            edges.append((filename, token))
    return edges


def extract_edges(file_path: Path, project_root: Path) -> List[Tuple[str, str]]:
    """Extract dependency edges from a single source file.

    Args:
        file_path: Absolute path to source file.
        project_root: Used to produce relative node labels.

    Returns:
        List of (source_node, target_node) string pairs.
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    try:
        rel_name = str(file_path.relative_to(project_root))
    except ValueError:
        rel_name = file_path.name

    suffix = file_path.suffix.lower()

    if suffix == ".py":
        return _extract_python_imports(source, rel_name)
    elif suffix == ".java":
        return _extract_java_imports(source, rel_name)
    elif suffix in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
        return _extract_js_ts_imports(source, rel_name)
    elif suffix == ".go":
        return _extract_go_imports(source, rel_name)
    else:
        return _extract_generic_imports(source, rel_name)


# ---------------------------------------------------------------------------
# Cyclomatic Complexity via lizard (optional)
# ---------------------------------------------------------------------------


def compute_cyclomatic(files: List[Path]) -> Dict[str, Any]:
    """Run lizard on discovered files and return summary metrics.

    Returns dict with avg_cyclomatic, max_cyclomatic, total_functions.
    Returns empty dict with zeros when lizard is not installed.
    """
    if not HAS_LIZARD or not files:
        return {"avg_cyclomatic": 0.0, "max_cyclomatic": 0, "total_functions": 0}

    try:
        complexities = []
        for fpath in files:
            try:
                result = lizard.analyze_file(str(fpath))
                for func in result.function_list:
                    complexities.append(func.cyclomatic_complexity)
            except Exception:
                continue

        if not complexities:
            return {"avg_cyclomatic": 0.0, "max_cyclomatic": 0, "total_functions": 0}

        avg = sum(complexities) / len(complexities)
        return {
            "avg_cyclomatic": round(avg, 2),
            "max_cyclomatic": max(complexities),
            "total_functions": len(complexities),
        }
    except Exception:
        return {"avg_cyclomatic": 0.0, "max_cyclomatic": 0, "total_functions": 0}


# ---------------------------------------------------------------------------
# Graph Metrics Calculation
# ---------------------------------------------------------------------------


def build_graph(files: List[Path], project_root: Path) -> Optional[Any]:
    """Build a directed dependency graph from the discovered files.

    Returns a networkx.DiGraph or None if networkx is unavailable.
    """
    if not HAS_NETWORKX:
        return None

    graph = nx.DiGraph()

    # Add all source files as nodes first
    for fpath in files:
        try:
            node_label = str(fpath.relative_to(project_root))
        except ValueError:
            node_label = fpath.name
        graph.add_node(node_label)

    # Add edges from import analysis
    for fpath in files:
        edges = extract_edges(fpath, project_root)
        for src, dst in edges:
            if src != dst:
                graph.add_edge(src, dst)

    return graph


def compute_graph_metrics(graph: Any) -> Dict[str, Any]:
    """Calculate all NetworkX graph metrics required by the policy.

    Args:
        graph: A networkx.DiGraph instance.

    Returns:
        Dict matching the graph_metrics schema in the policy output.
    """
    if graph is None or not HAS_NETWORKX:
        return {
            "total_nodes": 0,
            "total_edges": 0,
            "density": 0.0,
            "max_betweenness": 0.0,
            "max_pagerank": 0.0,
            "avg_fan_out": 0.0,
            "longest_path": 0,
            "connected_components": 0,
            "avg_clustering": 0.0,
        }

    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()

    if n_nodes == 0:
        return {
            "total_nodes": 0,
            "total_edges": 0,
            "density": 0.0,
            "max_betweenness": 0.0,
            "max_pagerank": 0.0,
            "avg_fan_out": 0.0,
            "longest_path": 0,
            "connected_components": 0,
            "avg_clustering": 0.0,
        }

    # Density
    density = nx.density(graph)

    # Betweenness centrality (expensive on large graphs; limit)
    try:
        if n_nodes > 200:
            # Use approximate betweenness for large graphs
            betweenness = nx.betweenness_centrality(graph, k=min(n_nodes, 50), normalized=True)
        else:
            betweenness = nx.betweenness_centrality(graph, normalized=True)
        max_betweenness = max(betweenness.values()) if betweenness else 0.0
    except Exception:
        max_betweenness = 0.0

    # PageRank
    try:
        pagerank = nx.pagerank(graph, max_iter=100, tol=1.0e-4)
        max_pagerank = max(pagerank.values()) if pagerank else 0.0
    except Exception:
        max_pagerank = 0.0

    # Average fan-out (mean out-degree)
    out_degrees = [d for _, d in graph.out_degree()]
    avg_fan_out = sum(out_degrees) / len(out_degrees) if out_degrees else 0.0

    # Longest path (DAG only; falls back to 0 on cycles)
    longest_path = 0
    try:
        longest_path = nx.dag_longest_path_length(graph)
    except nx.NetworkXUnfeasible:
        # Graph has cycles; skip longest path
        longest_path = 0
    except Exception:
        longest_path = 0

    # Weakly connected components
    try:
        connected_components = nx.number_weakly_connected_components(graph)
    except Exception:
        connected_components = 1

    # Average clustering (for undirected view)
    try:
        undirected = graph.to_undirected()
        avg_clustering = nx.average_clustering(undirected)
    except Exception:
        avg_clustering = 0.0

    return {
        "total_nodes": n_nodes,
        "total_edges": n_edges,
        "density": round(density, 4),
        "max_betweenness": round(max_betweenness, 4),
        "max_pagerank": round(max_pagerank, 4),
        "avg_fan_out": round(avg_fan_out, 3),
        "longest_path": longest_path,
        "connected_components": connected_components,
        "avg_clustering": round(avg_clustering, 4),
    }


def identify_bottleneck_files(graph: Any, top_n: int = 5) -> List[str]:
    """Return the top N files by betweenness centrality (bottleneck files).

    Args:
        graph: networkx.DiGraph
        top_n: Number of top files to return.

    Returns:
        List of relative file path strings sorted by centrality descending.
    """
    if graph is None or not HAS_NETWORKX:
        return []

    try:
        n = graph.number_of_nodes()
        if n == 0:
            return []
        k = min(n, 50)
        if n > 200:
            centrality = nx.betweenness_centrality(graph, k=k, normalized=True)
        else:
            centrality = nx.betweenness_centrality(graph, normalized=True)
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return [node for node, _ in sorted_nodes[:top_n]]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Scoring Formula (per policy Phase 6)
# ---------------------------------------------------------------------------


def _factor_graph_size(n_nodes: int) -> int:
    """Factor 1: Graph Size (0-5)."""
    if n_nodes > 100:
        return 5
    elif n_nodes > 50:
        return 4
    elif n_nodes > 20:
        return 3
    elif n_nodes > 10:
        return 2
    elif n_nodes > 5:
        return 1
    return 0


def _factor_density(density: float) -> int:
    """Factor 2: Dependency Density (0-5)."""
    if density > 0.20:
        return 5
    elif density > 0.15:
        return 4
    elif density > 0.10:
        return 3
    elif density > 0.05:
        return 2
    elif density > 0.02:
        return 1
    return 0


def _factor_betweenness(max_betweenness: float) -> int:
    """Factor 3: Max Betweenness Centrality (0-5)."""
    if max_betweenness > 0.5:
        return 5
    elif max_betweenness > 0.3:
        return 4
    elif max_betweenness > 0.2:
        return 3
    elif max_betweenness > 0.1:
        return 2
    elif max_betweenness > 0.05:
        return 1
    return 0


def _factor_fan_out(avg_fan_out: float) -> int:
    """Factor 4: Average Fan-Out / Coupling (0-5)."""
    if avg_fan_out > 10:
        return 5
    elif avg_fan_out > 7:
        return 4
    elif avg_fan_out > 5:
        return 3
    elif avg_fan_out > 3:
        return 2
    elif avg_fan_out > 1:
        return 1
    return 0


def _factor_longest_path(longest_path: int) -> int:
    """Factor 5: Longest Dependency Chain (0-5)."""
    if longest_path > 10:
        return 5
    elif longest_path > 7:
        return 4
    elif longest_path > 5:
        return 3
    elif longest_path > 3:
        return 2
    elif longest_path > 1:
        return 1
    return 0


def score_from_metrics(metrics: Dict[str, Any]) -> int:
    """Calculate the graph_complexity_score (1-25) from graph metrics.

    Accumulates all five factors (each 0-5) then clamps to 1-25.

    Args:
        metrics: Dict from compute_graph_metrics().

    Returns:
        Integer 1-25 graph complexity score.
    """
    score = 0
    score += _factor_graph_size(metrics.get("total_nodes", 0))
    score += _factor_density(metrics.get("density", 0.0))
    score += _factor_betweenness(metrics.get("max_betweenness", 0.0))
    score += _factor_fan_out(metrics.get("avg_fan_out", 0.0))
    score += _factor_longest_path(metrics.get("longest_path", 0))

    # Clamp 1-25 (minimum 1 for any analysed project)
    return max(1, min(25, score))


# ---------------------------------------------------------------------------
# CodeGraphAnalyzer - Main class used by complexity_calculator.py
# ---------------------------------------------------------------------------


class CodeGraphAnalyzer:
    """Analyzes a project codebase and produces a graph-based complexity score.

    Interface contract (matches complexity_calculator.py expectations):
        analyzer = CodeGraphAnalyzer(project_path, tech_stack, session_id)
        score    = analyzer.run()       # int 1-25
        analyzer.save()                 # writes graph-analysis.json
        analyzer.metrics                # dict of graph metrics
        analyzer.cyclomatic             # dict with avg_cyclomatic
        analyzer.files                  # list of Path objects analyzed

    Args:
        project_path: Absolute path string to project root.
        tech_stack: List of detected technology names (e.g. ["Python", "Flask"]).
        session_id: Identifier for saving output in the session directory.
    """

    def __init__(
        self,
        project_path: str,
        tech_stack: Optional[List[str]] = None,
        session_id: str = "unknown",
    ) -> None:
        self.project_path = project_path
        self.project_root = Path(project_path)
        self.tech_stack = tech_stack or []
        self.session_id = session_id

        # Populated by run()
        self.files: List[Path] = []
        self.metrics: Dict[str, Any] = {}
        self.cyclomatic: Dict[str, Any] = {}
        self._graph_score: int = 0
        self._bottleneck_files: List[str] = []
        self._graph: Any = None
        self._ran: bool = False

    def run(self) -> int:
        """Execute the full graph analysis pipeline.

        Returns:
            Integer graph_complexity_score in range 1-25.
            Returns 0 if networkx is unavailable.
        """
        if not HAS_NETWORKX:
            return 0

        if not self.project_root.exists():
            return 0

        try:
            # Phase 1: File Discovery
            self.files = discover_files(self.project_root, self.tech_stack)
            if not self.files:
                self._graph_score = 1
                self._ran = True
                return 1

            # Phase 2 + 3: Extract edges and build graph
            self._graph = build_graph(self.files, self.project_root)

            # Phase 4: Compute graph metrics
            self.metrics = compute_graph_metrics(self._graph)

            # Identify bottleneck files
            self._bottleneck_files = identify_bottleneck_files(self._graph)

            # Phase 5: Cyclomatic complexity (optional lizard)
            self.cyclomatic = compute_cyclomatic(self.files)

            # Enrich metrics with cyclomatic data for consistent output schema
            self.metrics["avg_cyclomatic"] = self.cyclomatic.get("avg_cyclomatic", 0.0)
            self.metrics["max_cyclomatic"] = self.cyclomatic.get("max_cyclomatic", 0)

            # Phase 6: Score calculation
            self._graph_score = score_from_metrics(self.metrics)
            self._ran = True
            return self._graph_score

        except Exception:
            self._graph_score = 0
            self._ran = True
            return 0

    def save(self) -> None:
        """Write the analysis result to the session directory.

        Output path:
            ~/.claude/memory/logs/sessions/{session_id}/graph-analysis.json

        Also writes a copy to:
            {project_root}/.claude-graph/graph-analysis.json
        """
        if not self._ran:
            return

        result = {
            "version": "1.2.0",
            "session_id": self.session_id,
            "analyzed_at": datetime.now().isoformat(),
            "project_dir": str(self.project_root),
            "tech_stack": self.tech_stack,
            "files_analyzed": len(self.files),
            "graph_metrics": self.metrics,
            "cyclomatic_metrics": self.cyclomatic,
            "graph_complexity_score": self._graph_score,
            "top_bottleneck_files": self._bottleneck_files,
            "analysis_available": HAS_NETWORKX,
        }

        # Write to session directory
        session_dir = SESSION_BASE / self.session_id
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / "graph-analysis.json"
            session_file.write_text(
                json.dumps(result, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

        # Write to project local cache for fast future reads
        try:
            local_cache_dir = self.project_root / ".claude-graph"
            local_cache_dir.mkdir(parents=True, exist_ok=True)
            local_cache_file = local_cache_dir / "graph-analysis.json"
            local_cache_file.write_text(
                json.dumps(result, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    def summary(self) -> str:
        """Return a one-line human-readable summary of the analysis."""
        if not self._ran:
            return "Not yet analyzed"
        n = self.metrics.get("total_nodes", 0)
        e = self.metrics.get("total_edges", 0)
        d = self.metrics.get("density", 0.0)
        bottleneck = self._bottleneck_files[0] if self._bottleneck_files else "none"
        return "{} files, {} deps, density={:.3f}, score={}, bottleneck={}".format(
            n, e, d, self._graph_score, bottleneck
        )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def _cli_main(args: List[str]) -> None:
    """Command-line interface for standalone execution.

    Usage:
        python code-graph-analyzer.py /path/to/project [session_id] [tech_stack_csv]
    """
    if len(args) < 1:
        print("Usage: code-graph-analyzer.py <project_path> [session_id] [tech_stack_csv]")
        sys.exit(1)

    project_path = args[0]
    session_id = args[1] if len(args) > 1 else "cli-session"
    tech_stack = args[2].split(",") if len(args) > 2 else []

    if not HAS_NETWORKX:
        result = {
            "error": "networkx not installed",
            "hint": "pip install networkx",
            "graph_complexity_score": 0,
            "analysis_available": False,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    analyzer = CodeGraphAnalyzer(project_path, tech_stack=tech_stack, session_id=session_id)
    score = analyzer.run()
    analyzer.save()

    output = {
        "graph_complexity_score": score,
        "graph_metrics_summary": analyzer.summary(),
        "graph_metrics": analyzer.metrics,
        "cyclomatic_metrics": analyzer.cyclomatic,
        "top_bottleneck_files": analyzer._bottleneck_files,
        "files_analyzed": len(analyzer.files),
        "analysis_available": True,
        "lizard_available": HAS_LIZARD,
    }
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    _cli_main(sys.argv[1:])
