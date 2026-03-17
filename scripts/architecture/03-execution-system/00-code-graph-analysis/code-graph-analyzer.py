#!/usr/bin/env python3
"""
Code Graph Analyzer - Step 3.0.1 (Pre-Flight)

Builds a dependency graph of the codebase and calculates graph-based
complexity score (1-25). Uses actual source code analysis instead of
keyword guessing.

Libraries:
  - ast (built-in): Python AST parsing for imports/calls/classes
  - networkx: Graph construction + algorithms (centrality, pagerank, density)
  - lizard: Multi-language cyclomatic complexity (Python/Java/JS/Go/C++)

Flow:
  Step 3.0.0 (Context Reader) -> tech_stack
  Step 3.0.1 (THIS) -> graph_complexity_score
  Step 3.0   (Prompt Generator) -> FINAL = (keyword*0.3) + (graph*0.7)

Version: 1.0.0
Author: Claude Insight System
"""

import sys
import os
import ast
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# Optional imports - graceful degradation
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    import lizard
    HAS_LIZARD = True
except ImportError:
    HAS_LIZARD = False


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_FILES = 500
MAX_FILE_SIZE = 100 * 1024  # 100KB

GRAPH_CACHE_FILE = 'graph-analysis.json'


def _get_graph_cache_dir(project_dir):
    """Get system temp-based cache directory for graph analysis.

    Uses the OS temp directory (e.g. %TEMP% on Windows, /tmp on Unix)
    with a project-specific subdirectory based on the project folder name.
    This avoids polluting the project directory with cache files.

    Args:
        project_dir: Path to the project root.

    Returns:
        Path: e.g. /tmp/.claude-graph-cache/claude-insight/
    """
    import tempfile
    project_name = Path(project_dir).resolve().name
    return Path(tempfile.gettempdir()) / '.claude-graph-cache' / project_name

SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env',
    'dist', 'build', '.tox', '.eggs', '.mypy_cache', '.pytest_cache',
    '.idea', '.vscode', '.settings', 'target', 'bin', 'obj',
    '.gradle', '.mvn', 'vendor', 'bower_components',
    '.claude-graph',  # legacy cache dir (skip if present)
}

LANGUAGE_EXTENSIONS = {
    'Python':     ['.py'],
    'Java':       ['.java'],
    'JavaScript': ['.js', '.jsx', '.mjs'],
    'TypeScript': ['.ts', '.tsx'],
    'Go':         ['.go'],
    'Rust':       ['.rs'],
    'C':          ['.c', '.h'],
    'C++':        ['.cpp', '.hpp', '.cc', '.cxx'],
}

# If tech_stack is empty/unknown, scan all common source extensions
ALL_SOURCE_EXTENSIONS = set()
for exts in LANGUAGE_EXTENSIONS.values():
    ALL_SOURCE_EXTENSIONS.update(exts)

MEMORY_BASE = Path.home() / '.claude' / 'memory'

# =============================================================================
# REPO-LEVEL CACHE
# =============================================================================

def get_cache_path(project_dir):
    """Get the path to the graph cache file in system temp directory."""
    return _get_graph_cache_dir(project_dir) / GRAPH_CACHE_FILE


def load_cached_graph(project_dir):
    """Load cached graph analysis from the repo.

    Cache at {tempdir}/.claude-graph-cache/{project}/graph-analysis.json.
    Returns cached data if file exists and is valid, None otherwise.
    """
    cache_file = get_cache_path(project_dir)
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding='utf-8'))
        if 'graph_complexity_score' in data and 'graph_metrics' in data:
            return data
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return None


def save_graph_to_repo(project_dir, result_data):
    """Save graph analysis to system temp directory.

    Uses OS temp dir (tempfile.gettempdir()) with project-specific subdirectory.
    E.g. %TEMP%/.claude-graph-cache/claude-insight/graph-analysis.json
    """
    try:
        cache_dir = _get_graph_cache_dir(project_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / GRAPH_CACHE_FILE
        cache_file.write_text(
            json.dumps(result_data, indent=2, default=str),
            encoding='utf-8'
        )
        return True
    except Exception as e:
        print(f"[WARN] Could not save graph to repo: {e}")
        return False


# =============================================================================
# PHASE 1: FILE DISCOVERY
# =============================================================================

def discover_files(project_dir, tech_stack=None):
    """Walk project directory and find source files matching the tech stack.

    Args:
        project_dir: Root directory to scan.
        tech_stack: List of technology names from context reader (e.g. ['Python', 'Flask']).

    Returns:
        list[Path]: Source file paths (max MAX_FILES).
    """
    # Determine which extensions to look for
    extensions = set()
    if tech_stack:
        for tech in tech_stack:
            tech_upper = tech.strip()
            for lang, exts in LANGUAGE_EXTENSIONS.items():
                if lang.lower() in tech_upper.lower() or tech_upper.lower() in lang.lower():
                    extensions.update(exts)
    # If no extensions matched, fall back to scanning all
    if not extensions:
        extensions = ALL_SOURCE_EXTENSIONS

    found = []
    project_path = Path(project_dir)

    for root, dirs, files in os.walk(project_path):
        # Prune skip directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith('.egg-info')]

        for fname in files:
            if len(found) >= MAX_FILES:
                return found

            fpath = Path(root) / fname
            # Check extension
            if fpath.suffix.lower() not in extensions:
                continue
            # Skip oversized files
            try:
                if fpath.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            found.append(fpath)

    return found


# =============================================================================
# PHASE 2: IMPORT/DEPENDENCY EXTRACTION
# =============================================================================

def extract_python_imports(file_path):
    """Parse a Python file using ast and extract import targets.

    Returns:
        list[str]: Module names imported by this file.
    """
    try:
        source = file_path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split('.')[0])
    return imports


def extract_python_classes_and_bases(file_path):
    """Extract class inheritance relationships from a Python file.

    Returns:
        list[tuple]: (class_name, base_class_name) pairs.
    """
    try:
        source = file_path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return []

    inheritance = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name):
                    inheritance.append((node.name, base.id))
                elif isinstance(base, ast.Attribute):
                    inheritance.append((node.name, base.attr))
    return inheritance


# Regex patterns for non-Python languages
_JAVA_IMPORT_RE = re.compile(r'^\s*import\s+([\w.]+)\s*;', re.MULTILINE)
_JAVA_EXTENDS_RE = re.compile(r'class\s+\w+\s+extends\s+(\w+)', re.MULTILINE)
_JAVA_IMPLEMENTS_RE = re.compile(r'implements\s+([\w\s,]+)', re.MULTILINE)

_JS_IMPORT_FROM_RE = re.compile(r'''import\s+.*?\s+from\s+['"]([^'"]+)['"]''', re.MULTILINE)
_JS_REQUIRE_RE = re.compile(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''', re.MULTILINE)
_JS_DYNAMIC_IMPORT_RE = re.compile(r'''import\s*\(\s*['"]([^'"]+)['"]\s*\)''', re.MULTILINE)

_GO_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r'import\s*\((.*?)\)', re.DOTALL)
_GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')

_RUST_USE_RE = re.compile(r'^\s*use\s+([\w:]+)', re.MULTILINE)
_C_INCLUDE_RE = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)


def extract_imports_regex(file_path, language):
    """Extract import/dependency targets using regex for non-Python languages.

    Args:
        file_path: Path to source file.
        language: One of 'Java', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'C', 'C++'.

    Returns:
        list[str]: Imported module/package names.
    """
    try:
        source = file_path.read_text(encoding='utf-8', errors='replace')
    except (OSError, UnicodeDecodeError):
        return []

    imports = []

    if language == 'Java':
        for match in _JAVA_IMPORT_RE.finditer(source):
            parts = match.group(1).split('.')
            # Use last 2 segments as module identifier
            imports.append('.'.join(parts[-2:]) if len(parts) >= 2 else parts[0])
        for match in _JAVA_EXTENDS_RE.finditer(source):
            imports.append(match.group(1))
        for match in _JAVA_IMPLEMENTS_RE.finditer(source):
            for iface in match.group(1).split(','):
                imports.append(iface.strip())

    elif language in ('JavaScript', 'TypeScript'):
        for match in _JS_IMPORT_FROM_RE.finditer(source):
            imports.append(match.group(1))
        for match in _JS_REQUIRE_RE.finditer(source):
            imports.append(match.group(1))
        for match in _JS_DYNAMIC_IMPORT_RE.finditer(source):
            imports.append(match.group(1))

    elif language == 'Go':
        for match in _GO_IMPORT_SINGLE_RE.finditer(source):
            imports.append(match.group(1).split('/')[-1])
        for block_match in _GO_IMPORT_BLOCK_RE.finditer(source):
            for line_match in _GO_IMPORT_LINE_RE.finditer(block_match.group(1)):
                imports.append(line_match.group(1).split('/')[-1])

    elif language == 'Rust':
        for match in _RUST_USE_RE.finditer(source):
            crate = match.group(1).split('::')[0]
            imports.append(crate)

    elif language in ('C', 'C++'):
        for match in _C_INCLUDE_RE.finditer(source):
            header = match.group(1)
            imports.append(header.replace('/', '.').replace('.h', ''))

    return imports


def detect_file_language(file_path):
    """Determine the programming language of a file from its extension.

    Returns:
        str or None: Language name.
    """
    suffix = file_path.suffix.lower()
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if suffix in exts:
            return lang
    return None


# =============================================================================
# PHASE 3 & 4: GRAPH CONSTRUCTION
# =============================================================================

def build_dependency_graph(files, project_dir):
    """Build a networkx DiGraph from source file dependencies.

    Each node is a relative file path. Edges represent import dependencies.

    Args:
        files: List of source file Paths.
        project_dir: Project root for relative path calculation.

    Returns:
        networkx.DiGraph: The dependency graph.
    """
    if not HAS_NETWORKX:
        return None

    graph = nx.DiGraph()
    project_path = Path(project_dir)

    # Map: module_name -> relative_file_path (for resolving imports to files)
    module_to_file = {}
    for fpath in files:
        rel = fpath.relative_to(project_path)
        rel_str = str(rel).replace('\\', '/')
        graph.add_node(rel_str)

        # Build module name from file path (for import resolution)
        # e.g. src/services/monitoring/metrics_collector.py -> metrics_collector
        stem = fpath.stem
        module_to_file[stem] = rel_str
        # Also map dotted path: src.services.monitoring.metrics_collector
        dotted = str(rel.with_suffix('')).replace('\\', '.').replace('/', '.')
        module_to_file[dotted] = rel_str
        # And last two segments: monitoring.metrics_collector
        parts = dotted.split('.')
        if len(parts) >= 2:
            module_to_file['.'.join(parts[-2:])] = rel_str

    # Extract dependencies and build edges
    for fpath in files:
        rel_str = str(fpath.relative_to(project_path)).replace('\\', '/')
        language = detect_file_language(fpath)

        if language == 'Python':
            imports = extract_python_imports(fpath)
            inheritance = extract_python_classes_and_bases(fpath)
            # Add inheritance edges with higher weight
            for _cls, base in inheritance:
                for mod_key, target_file in module_to_file.items():
                    if base.lower() in mod_key.lower() and target_file != rel_str:
                        graph.add_edge(rel_str, target_file, type='inheritance', weight=3)
                        break
        else:
            imports = extract_imports_regex(fpath, language) if language else []

        # Resolve imports to known project files
        for imp in imports:
            imp_lower = imp.lower()
            # Try direct match
            target = module_to_file.get(imp)
            if not target:
                # Try stem match (last part)
                imp_stem = imp.split('.')[-1]
                target = module_to_file.get(imp_stem)
            if not target:
                # Fuzzy: check if any module key contains the import
                for mod_key, mod_file in module_to_file.items():
                    if imp_lower in mod_key.lower():
                        target = mod_file
                        break

            if target and target != rel_str:
                if not graph.has_edge(rel_str, target):
                    graph.add_edge(rel_str, target, type='import', weight=1)

    return graph


# =============================================================================
# PHASE 5: METRICS CALCULATION
# =============================================================================

def calculate_graph_metrics(graph):
    """Calculate graph-based metrics using networkx algorithms.

    Args:
        graph: networkx.DiGraph.

    Returns:
        dict: Computed metrics.
    """
    if not graph or not HAS_NETWORKX or len(graph.nodes) == 0:
        return _empty_metrics()

    n_nodes = len(graph.nodes)
    n_edges = len(graph.edges)

    # Density
    density = nx.density(graph)

    # Degree centrality
    deg_centrality = nx.degree_centrality(graph)
    max_deg_centrality = max(deg_centrality.values()) if deg_centrality else 0

    # Betweenness centrality
    betweenness = nx.betweenness_centrality(graph)
    max_betweenness = max(betweenness.values()) if betweenness else 0
    top_bottleneck_node = max(betweenness, key=betweenness.get) if betweenness else None

    # PageRank (requires scipy - graceful fallback)
    try:
        pagerank = nx.pagerank(graph, max_iter=100)
        max_pagerank = max(pagerank.values()) if pagerank else 0
    except Exception:
        # scipy not installed or convergence failure - skip pagerank
        max_pagerank = 0

    # Average clustering (undirected view)
    try:
        avg_clustering = nx.average_clustering(graph.to_undirected())
    except (nx.NetworkXError, ZeroDivisionError):
        avg_clustering = 0

    # Connected components (weakly connected for DiGraph)
    try:
        n_components = nx.number_weakly_connected_components(graph)
    except nx.NetworkXError:
        n_components = 1

    # Fan-out: average out-degree
    out_degrees = [d for _, d in graph.out_degree()]
    avg_fan_out = sum(out_degrees) / max(n_nodes, 1)
    max_fan_out = max(out_degrees) if out_degrees else 0

    # Longest path (only for DAGs)
    longest_path = 0
    try:
        if nx.is_directed_acyclic_graph(graph):
            longest_path = nx.dag_longest_path_length(graph)
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        longest_path = 0

    # If graph has cycles, estimate depth via BFS from high-PageRank nodes
    if longest_path == 0 and n_edges > 0:
        try:
            # Use the highest-pagerank node as root for BFS depth estimate
            if top_bottleneck_node:
                lengths = nx.single_source_shortest_path_length(graph, top_bottleneck_node)
                longest_path = max(lengths.values()) if lengths else 0
        except (nx.NetworkXError, nx.NodeNotFound):
            longest_path = 0

    # Top bottleneck files (top 5 by betweenness centrality)
    sorted_bottlenecks = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)
    top_bottleneck_files = [node for node, _ in sorted_bottlenecks[:5] if betweenness.get(node, 0) > 0]

    return {
        'total_nodes': n_nodes,
        'total_edges': n_edges,
        'density': round(density, 4),
        'max_degree_centrality': round(max_deg_centrality, 4),
        'max_betweenness': round(max_betweenness, 4),
        'max_pagerank': round(max_pagerank, 4),
        'avg_fan_out': round(avg_fan_out, 2),
        'max_fan_out': max_fan_out,
        'longest_path': longest_path,
        'connected_components': n_components,
        'avg_clustering': round(avg_clustering, 4),
        'top_bottleneck_files': top_bottleneck_files,
    }


def _empty_metrics():
    """Return an empty metrics dict when analysis cannot run."""
    return {
        'total_nodes': 0, 'total_edges': 0, 'density': 0,
        'max_degree_centrality': 0, 'max_betweenness': 0,
        'max_pagerank': 0, 'avg_fan_out': 0, 'max_fan_out': 0,
        'longest_path': 0, 'connected_components': 0,
        'avg_clustering': 0, 'top_bottleneck_files': [],
    }


def calculate_cyclomatic_metrics(files):
    """Calculate cyclomatic complexity metrics using lizard.

    Args:
        files: List of source file Paths.

    Returns:
        dict: avg_cyclomatic, max_cyclomatic, total_functions.
    """
    if not HAS_LIZARD or not files:
        return {'avg_cyclomatic': 0, 'max_cyclomatic': 0, 'total_functions': 0}

    total_cc = 0
    max_cc = 0
    func_count = 0

    for fpath in files:
        try:
            result = lizard.analyze_file(str(fpath))
            for func in result.function_list:
                total_cc += func.cyclomatic_complexity
                max_cc = max(max_cc, func.cyclomatic_complexity)
                func_count += 1
        except Exception:
            continue

    avg_cc = round(total_cc / max(func_count, 1), 2)
    return {
        'avg_cyclomatic': avg_cc,
        'max_cyclomatic': max_cc,
        'total_functions': func_count,
    }


# =============================================================================
# PHASE 6: COMPLEXITY SCORE CALCULATION
# =============================================================================

def calculate_graph_complexity_score(metrics, cyclomatic):
    """Convert graph metrics into a 1-25 complexity score.

    Scoring factors (each 0-5, total 0-25):
      1. Graph size (file count)
      2. Dependency density
      3. Max betweenness centrality (bottleneck risk)
      4. Average fan-out / coupling
      5. Longest dependency chain depth

    Args:
        metrics: Dict from calculate_graph_metrics().
        cyclomatic: Dict from calculate_cyclomatic_metrics().

    Returns:
        int: Complexity score 1-25.
    """
    score = 0

    # Factor 1: Graph Size (0-5)
    nodes = metrics.get('total_nodes', 0)
    if nodes > 100:
        score += 5
    elif nodes > 50:
        score += 4
    elif nodes > 20:
        score += 3
    elif nodes > 10:
        score += 2
    elif nodes > 5:
        score += 1

    # Factor 2: Dependency Density (0-5)
    density = metrics.get('density', 0)
    if density > 0.20:
        score += 5
    elif density > 0.15:
        score += 4
    elif density > 0.10:
        score += 3
    elif density > 0.05:
        score += 2
    elif density > 0.02:
        score += 1

    # Factor 3: Bottleneck Risk - Max Betweenness Centrality (0-5)
    max_btwn = metrics.get('max_betweenness', 0)
    if max_btwn > 0.5:
        score += 5
    elif max_btwn > 0.3:
        score += 4
    elif max_btwn > 0.2:
        score += 3
    elif max_btwn > 0.1:
        score += 2
    elif max_btwn > 0.05:
        score += 1

    # Factor 4: Coupling - Average Fan-Out (0-5)
    avg_fo = metrics.get('avg_fan_out', 0)
    if avg_fo > 10:
        score += 5
    elif avg_fo > 7:
        score += 4
    elif avg_fo > 5:
        score += 3
    elif avg_fo > 3:
        score += 2
    elif avg_fo > 1:
        score += 1

    # Factor 5: Depth - Longest Path (0-5)
    longest = metrics.get('longest_path', 0)
    if longest > 10:
        score += 5
    elif longest > 7:
        score += 4
    elif longest > 5:
        score += 3
    elif longest > 3:
        score += 2
    elif longest > 1:
        score += 1

    # Bonus: High cyclomatic complexity amplifier (0-2 bonus)
    avg_cc = cyclomatic.get('avg_cyclomatic', 0)
    if avg_cc > 15:
        score += 2
    elif avg_cc > 8:
        score += 1

    return max(1, min(score, 25))


# =============================================================================
# MAIN CLASS
# =============================================================================

class CodeGraphAnalyzer:
    """Builds dependency graph of codebase and calculates structural complexity.

    Phases:
        1. File Discovery - walk project, filter by language
        2. Import Extraction - ast (Python) / regex (Java/JS/Go/Rust/C)
        3. Graph Construction - networkx DiGraph
        4. Metrics Calculation - centrality, coupling, fan-out, density
        5. Cyclomatic Complexity - via lizard (multi-language)
        6. Score Calculation - normalize to 1-25 scale
    """

    def __init__(self, project_dir, tech_stack=None, session_id=None):
        self.project_dir = Path(project_dir)
        self.tech_stack = tech_stack or []
        self.session_id = session_id or 'unknown'
        self.start_time = datetime.now()

        self.files = []
        self.graph = None
        self.metrics = _empty_metrics()
        self.cyclomatic = {'avg_cyclomatic': 0, 'max_cyclomatic': 0, 'total_functions': 0}
        self.graph_complexity_score = 1
        self._from_cache = False

    def run(self, force_regenerate=False):
        """Execute the analysis pipeline.

        If cached graph exists in repo and force_regenerate is False,
        reads from cache (instant). Otherwise builds fresh graph.

        Args:
            force_regenerate: If True, skip cache and rebuild from scratch.

        Returns:
            int: graph_complexity_score (1-25).
        """
        # Check repo-level cache first (unless forced regenerate)
        if not force_regenerate:
            cached = load_cached_graph(self.project_dir)
            if cached:
                self.graph_complexity_score = cached.get('graph_complexity_score', 1)
                self.metrics = cached.get('graph_metrics', _empty_metrics())
                self.cyclomatic = cached.get('cyclomatic_metrics', {
                    'avg_cyclomatic': 0, 'max_cyclomatic': 0, 'total_functions': 0
                })
                self.files = [None] * cached.get('files_analyzed', 0)
                self._from_cache = True
                print(f"[GRAPH] Cache HIT: score={self.graph_complexity_score}/25, "
                      f"{cached.get('files_analyzed', 0)} files "
                      f"(built {cached.get('analyzed_at', 'unknown')[:19]})")
                return self.graph_complexity_score

        if force_regenerate:
            print("[GRAPH] Force REGENERATE - rebuilding dependency graph...")
        else:
            print("[GRAPH] Cache MISS - building dependency graph...")

        if not HAS_NETWORKX:
            print("[GRAPH] networkx not installed - skipping graph analysis")
            return 1

        # Phase 1: Discover files
        self.files = discover_files(self.project_dir, self.tech_stack)
        if not self.files:
            print("[GRAPH] No source files found - returning score=1")
            return 1
        print(f"[GRAPH] Found {len(self.files)} source files")

        # Phase 2-4: Build dependency graph
        self.graph = build_dependency_graph(self.files, self.project_dir)

        # Phase 4: Calculate graph metrics
        self.metrics = calculate_graph_metrics(self.graph)
        print(f"[GRAPH] Graph: {self.metrics['total_nodes']} nodes, {self.metrics['total_edges']} edges, density={self.metrics['density']}")

        # Phase 5: Cyclomatic complexity
        self.cyclomatic = calculate_cyclomatic_metrics(self.files)
        if HAS_LIZARD:
            print(f"[GRAPH] Cyclomatic: avg={self.cyclomatic['avg_cyclomatic']}, max={self.cyclomatic['max_cyclomatic']}, functions={self.cyclomatic['total_functions']}")

        # Phase 6: Calculate score
        self.graph_complexity_score = calculate_graph_complexity_score(self.metrics, self.cyclomatic)
        print(f"[GRAPH] Graph Complexity Score: {self.graph_complexity_score}/25")

        if self.metrics.get('top_bottleneck_files'):
            print(f"[GRAPH] Top bottleneck: {self.metrics['top_bottleneck_files'][0]}")

        return self.graph_complexity_score

    def save(self):
        """Save analysis results to the system temp cache.

        Saves to {tempdir}/.claude-graph-cache/{project}/graph-analysis.json.
        Skips saving if results were loaded from cache (nothing new).
        """
        if self._from_cache:
            return True

        duration = (datetime.now() - self.start_time).total_seconds() * 1000

        result = {
            'version': '1.1.0',
            'analyzed_at': self.start_time.isoformat(),
            'duration_ms': int(duration),
            'project_dir': str(self.project_dir),
            'tech_stack': self.tech_stack,
            'files_analyzed': len(self.files),
            'graph_metrics': self.metrics,
            'cyclomatic_metrics': self.cyclomatic,
            'graph_complexity_score': self.graph_complexity_score,
        }

        saved = save_graph_to_repo(self.project_dir, result)
        if saved:
            print(f"[GRAPH] Saved to {_get_graph_cache_dir(self.project_dir) / GRAPH_CACHE_FILE}")
        return saved

    def build_trace_entry(self):
        """Build a flow-trace.json pipeline entry for Step 3.0.1."""
        duration = (datetime.now() - self.start_time).total_seconds() * 1000

        return {
            'step': 'LEVEL_3_STEP_0_CODE_GRAPH',
            'name': 'Code Graph Analysis (Pre-Flight)',
            'level': 3,
            'order': 0.1,
            'is_blocking': False,
            'timestamp': self.start_time.isoformat(),
            'duration_ms': int(duration),
            'input': {
                'project_dir': str(self.project_dir),
                'tech_stack': self.tech_stack,
                'session_id': self.session_id,
                'purpose': 'Build dependency graph and calculate structural complexity'
            },
            'policy': {
                'script': 'code-graph-analyzer.py',
                'version': '1.0.0',
                'libraries': {
                    'networkx': HAS_NETWORKX,
                    'lizard': HAS_LIZARD,
                },
                'rules_applied': [
                    'discover_source_files',
                    'extract_imports_ast_and_regex',
                    'build_dependency_digraph',
                    'calculate_centrality_metrics',
                    'calculate_cyclomatic_complexity',
                    'score_graph_complexity_1_25',
                ]
            },
            'policy_output': {
                'files_analyzed': len(self.files),
                'graph_complexity_score': self.graph_complexity_score,
                'graph_metrics': self.metrics,
                'cyclomatic_metrics': self.cyclomatic,
                'status': 'SUCCESS' if self.files else 'SKIPPED'
            },
            'decision': self._build_decision(),
            'passed_to_next': {
                'graph_complexity_score': self.graph_complexity_score,
                'graph_metrics_summary': (
                    f"{self.metrics['total_nodes']} files, "
                    f"{self.metrics['total_edges']} deps, "
                    f"density={self.metrics['density']}, "
                    f"bottleneck={self.metrics['top_bottleneck_files'][0] if self.metrics.get('top_bottleneck_files') else 'none'}"
                ),
                'top_bottleneck_files': self.metrics.get('top_bottleneck_files', []),
                'analysis_available': len(self.files) > 0,
            }
        }

    def _build_decision(self):
        """Build a human-readable decision summary."""
        if not self.files:
            return "No source files found. Graph complexity = 1 (minimal)."
        source = "CACHED" if self._from_cache else "ANALYZED"
        return (
            f"{source}: {len(self.files)} files -> "
            f"{self.metrics['total_nodes']} nodes, {self.metrics['total_edges']} edges. "
            f"Graph complexity = {self.graph_complexity_score}/25. "
            f"Bottleneck: {self.metrics['top_bottleneck_files'][0] if self.metrics.get('top_bottleneck_files') else 'none'}."
        )


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Entry point. Called by 3-level-flow.py as Step 3.0.1.

    Usage:
        python code-graph-analyzer.py <project_dir> <session_id> <tech_stack_csv>
        python code-graph-analyzer.py <project_dir> --regenerate [tech_stack_csv]
    """
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

    # Check for --regenerate flag (called by version-release-policy after doc updates)
    force_regenerate = '--regenerate' in sys.argv

    if force_regenerate:
        session_id = 'regenerate'
        tech_stack_csv = sys.argv[3] if len(sys.argv) > 3 else ''
    else:
        session_id = sys.argv[2] if len(sys.argv) > 2 else 'unknown'
        tech_stack_csv = sys.argv[3] if len(sys.argv) > 3 else ''

    tech_stack = [t.strip() for t in tech_stack_csv.split(',') if t.strip()] if tech_stack_csv else []

    analyzer = CodeGraphAnalyzer(project_dir, tech_stack, session_id)
    score = analyzer.run(force_regenerate=force_regenerate)

    # Save to repo-level cache
    analyzer.save()

    # Output trace entry as JSON (for 3-level-flow.py to parse)
    trace_entry = analyzer.build_trace_entry()
    print(json.dumps(trace_entry))

    return 0


if __name__ == '__main__':
    sys.exit(main())
