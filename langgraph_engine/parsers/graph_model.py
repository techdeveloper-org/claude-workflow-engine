"""
Call graph data model.

Contains the CallGraph class and its factory helpers (make_class_node,
make_method_node, make_call_edge).  Extracted verbatim from
call_graph_builder.py so that parsers and consumers can import from a
single place without circular dependencies.

ASCII-only (cp1252-safe for Windows).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transitive call-path exploration limits
# ---------------------------------------------------------------------------
# compute_call_paths() previously hard-coded max_depth=15 and max_paths=200
# which silently truncated analysis of any call chain longer than 15 hops.
# Issue #207 raised the defaults and made both configurable via env vars so
# operators can tune per project without editing source.
#   CLAUDE_CG_MAX_DEPTH  (default 30) -- deeper covers most real codebases
#   CLAUDE_CG_MAX_PATHS  (default 500) -- permits wider fanout capture
# Callers may also pass explicit max_depth / max_paths kwargs which override
# the env defaults for a single call.


def _env_int(name, default):
    """Parse an int env var; fall back to default on missing/invalid value."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


DEFAULT_MAX_DEPTH = _env_int("CLAUDE_CG_MAX_DEPTH", 30)
DEFAULT_MAX_PATHS = _env_int("CLAUDE_CG_MAX_PATHS", 500)

# =========================================================================
# Node / Edge factory helpers
# =========================================================================


def make_class_node(fqn, name, file_path, line, bases=None):
    """Create a class node dict.

    Args:
        fqn: Fully qualified name (e.g., module.py::ClassName)
        name: Simple class name
        file_path: Relative path to file
        line: Line number of class definition
        bases: List of parent class names
    """
    return {
        "id": fqn,
        "type": "class",
        "name": name,
        "file": file_path,
        "line": line,
        "bases": bases or [],
        "methods": [],  # populated later with method FQNs
    }


def make_method_node(
    fqn,
    name,
    file_path,
    line,
    parent_class=None,
    params=None,
    return_type="",
    visibility="+",
    is_async=False,
    cyclomatic=1,
):
    """Create a method/function node dict.

    Args:
        fqn: Fully qualified name (e.g., module.py::ClassName.method)
        name: Simple method name
        file_path: Relative path to file
        line: Line number
        parent_class: FQN of parent class (None for standalone functions)
        params: List of parameter strings
        return_type: Return type annotation string
        visibility: + (public) or - (private)
        is_async: Whether it is async
        cyclomatic: Cyclomatic complexity of this method
    """
    return {
        "id": fqn,
        "type": "method" if parent_class else "function",
        "name": name,
        "file": file_path,
        "line": line,
        "parent_class": parent_class,
        "params": params or [],
        "return_type": return_type,
        "visibility": visibility,
        "is_async": is_async,
        "cyclomatic": cyclomatic,
    }


def make_call_edge(from_fqn, to_fqn, line, call_type="call"):
    """Create a call edge dict.

    Args:
        from_fqn: Caller FQN
        to_fqn: Callee FQN (or best-effort name if unresolved)
        line: Line number of the call
        call_type: 'call', 'method_call', 'inheritance', 'super_call'
    """
    return {
        "from": from_fqn,
        "to": to_fqn,
        "line": line,
        "type": call_type,
    }


# =========================================================================
# Helpers
# =========================================================================


def _safe_avg(values):
    """Calculate average, return 0.0 for empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


# =========================================================================
# CallGraph - main data structure
# =========================================================================


class CallGraph:
    """Complete call graph for a project.

    Attributes:
        nodes: Dict of FQN -> node dict (classes, methods, functions)
        edges: List of call edge dicts
        classes: Dict of FQN -> class node
        methods: Dict of FQN -> method/function node
        files: Set of relative file paths analysed
    """

    def __init__(self):
        self.nodes = {}  # fqn -> node dict
        self.classes = {}  # fqn -> class node
        self.methods = {}  # fqn -> method/function node
        self.edges = []  # list of call edge dicts
        self.files = set()  # relative file paths

        # Computed after build
        self._call_paths = None
        self._impact_map = None
        self._resolved_edges = None

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def add_file_results(self, visitor):
        """Merge results from a parser visitor into this graph.

        The visitor object must expose .classes, .methods, .edges, and
        .rel_path attributes (matching the shape produced by all concrete
        parsers in the parsers/ package).
        """
        for cls in visitor.classes:
            self.classes[cls["id"]] = cls
            self.nodes[cls["id"]] = cls
        for method in visitor.methods:
            self.methods[method["id"]] = method
            self.nodes[method["id"]] = method
        self.edges.extend(visitor.edges)
        self.files.add(visitor.rel_path)

    # ------------------------------------------------------------------
    # Edge resolution
    # ------------------------------------------------------------------

    def resolve_edges(self):
        """Resolve unqualified callee names to FQNs where possible.

        After all files are processed, try to match call targets
        to known method/function definitions.
        """
        # Build lookup: simple name -> list of FQNs
        name_to_fqns = {}
        for fqn, node in self.methods.items():
            name = node["name"]
            if name not in name_to_fqns:
                name_to_fqns[name] = []
            name_to_fqns[name].append(fqn)

        # Also map class names
        class_name_to_fqn = {}
        for fqn, cls in self.classes.items():
            class_name_to_fqn[cls["name"]] = fqn

        resolved = []
        for edge in self.edges:
            to_name = edge["to"]
            resolved_to = self._resolve_target(to_name, edge["from"], name_to_fqns, class_name_to_fqn)
            new_edge = dict(edge)
            new_edge["to"] = resolved_to
            new_edge["resolved"] = resolved_to != to_name
            resolved.append(new_edge)

        self._resolved_edges = resolved
        return resolved

    def _resolve_target(self, target, caller_fqn, name_to_fqns, class_name_to_fqn):
        """Try to resolve a call target to a known FQN.

        Resolution strategy:
        1. If target already looks like a FQN (contains ::), keep it.
        2. If target has dots (receiver.method), try to resolve receiver.
        3. If target matches a known method name, prefer same-file methods.
        4. Check if it is a class name (constructor call).
        5. Fall back to the unresolved name.
        """
        # Already resolved
        if "::" in target:
            return target

        # Get caller file for same-file preference
        caller_file = caller_fqn.split("::")[0] if "::" in caller_fqn else ""

        # Handle dotted targets like ClassName.method
        if "." in target:
            parts = target.rsplit(".", 1)
            method_name = parts[-1]
            if "::" in parts[0]:
                return target
            if method_name in name_to_fqns:
                candidates = name_to_fqns[method_name]
                same_file = [c for c in candidates if c.startswith(caller_file + "::")]
                if same_file:
                    return same_file[0]
                if len(candidates) == 1:
                    return candidates[0]
            return target

        # Simple name lookup
        if target in name_to_fqns:
            candidates = name_to_fqns[target]
            same_file = [c for c in candidates if c.startswith(caller_file + "::")]
            if same_file:
                return same_file[0]
            if len(candidates) == 1:
                return candidates[0]
            return candidates[0]

        # Check if it is a class name (constructor call)
        if target in class_name_to_fqn:
            class_fqn = class_name_to_fqn[target]
            init_fqn = "%s.__init__" % class_fqn
            if init_fqn in self.methods:
                return init_fqn
            return class_fqn

        # Unresolved - external or builtin
        return target

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_edges(self):
        """Get resolved edges (or raw if not yet resolved)."""
        if self._resolved_edges is not None:
            return self._resolved_edges
        return self.edges

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def compute_call_paths(self, max_depth=None, max_paths=None):
        """Compute all call paths from entry points.

        Entry points are methods/functions not called by any other method.

        Args:
            max_depth: Maximum path depth to explore. Defaults to
                DEFAULT_MAX_DEPTH (30, overridable via CLAUDE_CG_MAX_DEPTH
                env var). Paths longer than this are truncated.
            max_paths: Maximum number of paths to emit. Defaults to
                DEFAULT_MAX_PATHS (500, overridable via CLAUDE_CG_MAX_PATHS
                env var). Emission stops once this many paths have been
                collected and a warning is logged.

        Returns list of path dicts:
        [{"id": "path_N", "path": [fqn1, fqn2, ...], "depth": N,
          "total_complexity": N}]

        Previously hard-coded at max_depth=15, max_paths=200 -- issue #207
        raised the defaults and made them configurable so deep call chains
        in larger codebases are no longer silently truncated.
        """
        if self._call_paths is not None:
            return self._call_paths

        # Resolve limits (explicit args override env defaults)
        if max_depth is None:
            max_depth = DEFAULT_MAX_DEPTH
        if max_paths is None:
            max_paths = DEFAULT_MAX_PATHS

        edges = self.get_edges()

        # Build adjacency: caller -> [callees]
        adjacency = {}
        for edge in edges:
            if edge["type"] == "inheritance":
                continue
            src = edge["from"]
            dst = edge["to"]
            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append(dst)

        # Find all callees
        all_callees = set()
        for targets in adjacency.values():
            all_callees.update(targets)

        # Entry points: defined methods not in callee set
        entry_points = []
        for fqn in self.methods:
            name = self.methods[fqn]["name"]
            if name.startswith("_") and not name.startswith("__"):
                continue  # skip private
            if fqn not in all_callees:
                entry_points.append(fqn)

        # DFS from each entry point
        paths = []
        path_id = 0
        for entry in entry_points:
            if path_id >= max_paths:
                break
            stack = [(entry, [entry], 0)]
            while stack and path_id < max_paths:
                current, path, depth = stack.pop()
                if depth >= max_depth:
                    continue

                callees = adjacency.get(current, [])
                if not callees or depth >= max_depth - 1:
                    if len(path) >= 2:
                        total_cx = sum(
                            self.methods.get(fqn, {}).get("cyclomatic", 1) for fqn in path if fqn in self.methods
                        )
                        paths.append(
                            {
                                "id": "path_%d" % path_id,
                                "path": list(path),
                                "depth": len(path),
                                "total_complexity": total_cx,
                            }
                        )
                        path_id += 1
                else:
                    for callee in callees:
                        if callee in path:
                            continue  # avoid cycles
                        if callee not in self.methods:
                            continue  # skip unresolved
                        stack.append((callee, path + [callee], depth + 1))

        # Emit a warning when exploration hit a hard cap so operators know
        # their results may be truncated. Keeps silent truncation visible
        # without changing the return shape.
        if path_id >= max_paths:
            logger.warning(
                "compute_call_paths: hit max_paths=%d limit; results truncated. "
                "Increase via CLAUDE_CG_MAX_PATHS env var or pass max_paths kwarg.",
                max_paths,
            )

        self._call_paths = paths
        return paths

    def compute_impact_map(self):
        """Build reverse dependency map: what is affected when X changes.

        Returns dict: {fqn: set of FQNs that call this method (transitively)}
        """
        if self._impact_map is not None:
            return self._impact_map

        edges = self.get_edges()

        # Reverse adjacency: callee -> [callers]
        reverse = {}
        for edge in edges:
            if edge["type"] == "inheritance":
                continue
            dst = edge["to"]
            src = edge["from"]
            if dst not in reverse:
                reverse[dst] = set()
            reverse[dst].add(src)

        # Transitive closure via BFS from each node
        impact = {}
        for fqn in self.methods:
            affected = set()
            queue = [fqn]
            visited = set()
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                callers = reverse.get(current, set())
                for caller in callers:
                    if caller not in visited:
                        affected.add(caller)
                        queue.append(caller)
            impact[fqn] = affected

        self._impact_map = impact
        return impact

    def get_max_call_depth(self):
        """Get the maximum call chain depth."""
        paths = self.compute_call_paths()
        if not paths:
            return 0
        return max(p["depth"] for p in paths)

    def get_stats(self):
        """Get summary statistics for the call graph."""
        edges = self.get_edges()
        call_edges = [e for e in edges if e["type"] != "inheritance"]
        inheritance_edges = [e for e in edges if e["type"] == "inheritance"]
        resolved = [e for e in call_edges if e.get("resolved", False)]

        return {
            "total_classes": len(self.classes),
            "total_methods": len(self.methods),
            "total_functions": sum(1 for m in self.methods.values() if m["type"] == "function"),
            "total_call_edges": len(call_edges),
            "total_inheritance_edges": len(inheritance_edges),
            "resolved_edges": len(resolved),
            "unresolved_edges": len(call_edges) - len(resolved),
            "files_analyzed": len(self.files),
            "max_call_depth": self.get_max_call_depth(),
            "avg_cyclomatic": _safe_avg([m.get("cyclomatic", 1) for m in self.methods.values()]),
            "max_cyclomatic": max(
                (m.get("cyclomatic", 1) for m in self.methods.values()),
                default=0,
            ),
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self):
        """Serialise the full call graph to a dict.

        This is the proper call stack format:
        - nodes: classes and methods with FQN, params, types
        - edges: method-to-method calls with line numbers
        - call_paths: full call chains with depth and complexity
        """
        edges = self.get_edges()
        paths = self.compute_call_paths()
        stats = self.get_stats()

        return {
            "version": "2.0.0",
            "stats": stats,
            "nodes": {
                "classes": list(self.classes.values()),
                "methods": list(self.methods.values()),
            },
            "edges": edges,
            "call_paths": paths[:100],
        }

    def to_json(self, indent=2):
        """Serialise to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
