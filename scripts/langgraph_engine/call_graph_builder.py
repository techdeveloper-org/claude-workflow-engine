"""
Call Graph Builder - Proper class->method->method call stack mapping.

Builds a fully qualified call graph where:
- Nodes are classes and methods with FQN (e.g., module.py::ClassName.method1)
- Edges are method-to-method calls with line numbers
- Full call paths are recorded for impact analysis

This replaces the flat file-level graph and name-only call chains
with a proper call stack that tracks class context.

Usage:
    from call_graph_builder import CallGraphBuilder
    builder = CallGraphBuilder(project_root)
    graph = builder.build()
    # graph.nodes  -> list of ClassNode/MethodNode/FunctionNode
    # graph.edges  -> list of CallEdge (from_fqn -> to_fqn with line_number)
    # graph.call_paths -> list of full call chains
    # graph.impact_map -> {fqn: set of affected fqns}

Python 3.8+ compatible. ASCII-only (cp1252-safe).
"""

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


# =========================================================================
# Data Structures
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
    fqn, name, file_path, line, parent_class=None,
    params=None, return_type="", visibility="+",
    is_async=False, cyclomatic=1,
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
        is_async: Whether it's async
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
# AST Visitor - Maintains class context (unlike ast.walk)
# =========================================================================

class _CallGraphVisitor(ast.NodeVisitor):
    """AST visitor that tracks class/method hierarchy while walking the tree.

    Unlike ast.walk(), NodeVisitor.visit() is called in tree order,
    so we can maintain a stack of the current class/function context.
    """

    def __init__(self, file_path, rel_path):
        self.file_path = file_path
        self.rel_path = rel_path
        self.classes = []     # list of class node dicts
        self.methods = []     # list of method/function node dicts
        self.edges = []       # list of call edge dicts

        # Context stack: tracks current class/method nesting
        self._class_stack = []   # stack of class names
        self._func_stack = []    # stack of (fqn, node) tuples

    def _current_class_fqn(self):
        """Get FQN of current class, or None."""
        if not self._class_stack:
            return None
        return "%s::%s" % (self.rel_path, ".".join(self._class_stack))

    def _current_func_fqn(self):
        """Get FQN of current function/method, or None."""
        if not self._func_stack:
            return None
        return self._func_stack[-1][0]

    def _make_fqn(self, name):
        """Build FQN for a name in current context."""
        if self._class_stack:
            return "%s::%s.%s" % (
                self.rel_path,
                ".".join(self._class_stack),
                name,
            )
        return "%s::%s" % (self.rel_path, name)

    def visit_ClassDef(self, node):
        """Process class definition - push onto class stack."""
        class_name = node.name
        self._class_stack.append(class_name)

        fqn = self._current_class_fqn()
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                # e.g., module.ClassName
                parts = []
                current = base
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                bases.append(".".join(reversed(parts)))

        class_node = make_class_node(
            fqn=fqn,
            name=class_name,
            file_path=self.rel_path,
            line=node.lineno,
            bases=bases,
        )
        self.classes.append(class_node)

        # Add inheritance edges
        for base_name in bases:
            self.edges.append(make_call_edge(
                from_fqn=fqn,
                to_fqn=base_name,  # unresolved, will resolve later
                line=node.lineno,
                call_type="inheritance",
            ))

        # Visit children (methods inside this class)
        self.generic_visit(node)

        self._class_stack.pop()

    def visit_FunctionDef(self, node):
        """Process function/method definition."""
        self._process_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        """Process async function/method definition."""
        self._process_function(node, is_async=True)

    def _process_function(self, node, is_async):
        """Common handler for FunctionDef and AsyncFunctionDef."""
        name = node.name
        fqn = self._make_fqn(name)
        parent_class = self._current_class_fqn()

        # Determine visibility
        if name.startswith("__") and name.endswith("__"):
            visibility = "+"   # dunder = public interface
        elif name.startswith("_"):
            visibility = "-"   # private
        else:
            visibility = "+"

        # Extract parameters
        params = []
        for arg in node.args.args:
            if arg.arg == "self" or arg.arg == "cls":
                continue
            param_str = arg.arg
            if arg.annotation:
                ann = _annotation_to_str(arg.annotation)
                if ann:
                    param_str = "%s: %s" % (arg.arg, ann)
            params.append(param_str)

        # Extract return type
        return_type = ""
        if node.returns:
            return_type = _annotation_to_str(node.returns) or ""

        # Calculate basic cyclomatic complexity (branch count + 1)
        cyclomatic = _count_branches(node) + 1

        method_node = make_method_node(
            fqn=fqn,
            name=name,
            file_path=self.rel_path,
            line=node.lineno,
            parent_class=parent_class,
            params=params,
            return_type=return_type,
            visibility=visibility,
            is_async=is_async,
            cyclomatic=cyclomatic,
        )
        self.methods.append(method_node)

        # Register method in parent class
        if parent_class:
            for cls in self.classes:
                if cls["id"] == parent_class:
                    cls["methods"].append(fqn)
                    break

        # Push onto function stack and visit body for calls
        self._func_stack.append((fqn, node))
        self._extract_calls(node)
        self._func_stack.pop()

    def _extract_calls(self, func_node):
        """Walk the function body to find all Call nodes."""
        caller_fqn = self._current_func_fqn()
        if not caller_fqn:
            return

        for child in ast.walk(func_node):
            if not isinstance(child, ast.Call):
                continue

            line = getattr(child, "lineno", 0)
            call_info = self._resolve_call(child)
            if not call_info:
                continue

            callee_name, call_type = call_info
            self.edges.append(make_call_edge(
                from_fqn=caller_fqn,
                to_fqn=callee_name,
                line=line,
                call_type=call_type,
            ))

    def _resolve_call(self, call_node):
        """Resolve a Call AST node to a callee name and call type.

        Returns (callee_name, call_type) or None.
        """
        func = call_node.func

        if isinstance(func, ast.Name):
            # Direct call: func_name()
            name = func.id
            if name == "super":
                return (name, "super_call")
            return (name, "call")

        elif isinstance(func, ast.Attribute):
            # Method call: obj.method() or module.func()
            attr = func.attr
            # Try to get the object name for better resolution
            receiver = _get_receiver_name(func.value)
            if receiver == "self":
                # self.method() -> same class method
                parent = self._current_class_fqn()
                if parent:
                    return ("%s.%s" % (parent, attr), "method_call")
                return (attr, "method_call")
            elif receiver == "cls":
                parent = self._current_class_fqn()
                if parent:
                    return ("%s.%s" % (parent, attr), "method_call")
                return (attr, "method_call")
            elif receiver:
                # obj.method() or Module.method()
                return ("%s.%s" % (receiver, attr), "method_call")
            else:
                return (attr, "method_call")

        return None


# =========================================================================
# AST Helper Functions
# =========================================================================

def _annotation_to_str(node):
    """Convert an annotation AST node to a readable string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Attribute):
        val = _annotation_to_str(node.value)
        if val:
            return "%s.%s" % (val, node.attr)
        return node.attr
    elif isinstance(node, ast.Subscript):
        base = _annotation_to_str(node.value)
        # Python 3.8 uses Index wrapper, 3.9+ uses direct
        slice_node = node.slice
        if isinstance(slice_node, ast.Index):
            slice_node = slice_node.value
        inner = _annotation_to_str(slice_node)
        if base and inner:
            return "%s[%s]" % (base, inner)
        return base or ""
    elif isinstance(node, ast.Tuple):
        parts = [_annotation_to_str(e) for e in node.elts]
        return ", ".join(p for p in parts if p)
    return ""


def _get_receiver_name(node):
    """Extract the receiver name from an attribute access.

    e.g., for `self.method()` returns 'self',
          for `obj.method()` returns 'obj',
          for `module.Class.method()` returns 'module.Class'
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        parent = _get_receiver_name(node.value)
        if parent:
            return "%s.%s" % (parent, node.attr)
        return node.attr
    return None


def _count_branches(func_node):
    """Count branch points in a function for basic cyclomatic complexity."""
    count = 0
    for node in ast.walk(func_node):
        if isinstance(node, (ast.If, ast.While, ast.For)):
            count += 1
        elif isinstance(node, ast.ExceptHandler):
            count += 1
        elif isinstance(node, ast.BoolOp):
            # and/or add branches
            count += len(node.values) - 1
        elif isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.comprehension):
            count += 1
            # if guards in comprehension
            count += len(node.ifs)
    return count


# =========================================================================
# Regex Visitor - For non-Python languages (Java, TypeScript, Kotlin)
# =========================================================================

class _RegexVisitor:
    """Simple data holder for non-Python languages using regex parsing.

    Holds the same shape of data as _CallGraphVisitor so that
    CallGraph.add_file_results() works without modification.
    """

    def __init__(self, file_path, rel_path):
        self.file_path = file_path
        self.rel_path = rel_path
        self.classes = []   # list of class node dicts
        self.methods = []   # list of method/function node dicts
        self.edges = []     # list of call edge dicts


# =========================================================================
# Call Graph - Main Data Structure
# =========================================================================

class CallGraph:
    """Complete call graph for a project.

    Attributes:
        nodes: Dict of FQN -> node dict (classes, methods, functions)
        edges: List of call edge dicts
        classes: Dict of FQN -> class node
        methods: Dict of FQN -> method/function node
        files: Set of relative file paths analyzed
    """

    def __init__(self):
        self.nodes = {}       # fqn -> node dict
        self.classes = {}     # fqn -> class node
        self.methods = {}     # fqn -> method/function node
        self.edges = []       # list of call edge dicts
        self.files = set()    # relative file paths

        # Computed after build
        self._call_paths = None
        self._impact_map = None
        self._resolved_edges = None

    def add_file_results(self, visitor):
        """Merge results from a _CallGraphVisitor into this graph."""
        for cls in visitor.classes:
            self.classes[cls["id"]] = cls
            self.nodes[cls["id"]] = cls
        for method in visitor.methods:
            self.methods[method["id"]] = method
            self.nodes[method["id"]] = method
        self.edges.extend(visitor.edges)
        self.files.add(visitor.rel_path)

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
            resolved_to = self._resolve_target(
                to_name, edge["from"], name_to_fqns, class_name_to_fqn
            )
            new_edge = dict(edge)
            new_edge["to"] = resolved_to
            new_edge["resolved"] = resolved_to != to_name
            resolved.append(new_edge)

        self._resolved_edges = resolved
        return resolved

    def _resolve_target(self, target, caller_fqn, name_to_fqns, class_name_to_fqn):
        """Try to resolve a call target to a known FQN.

        Resolution strategy:
        1. If target already looks like a FQN (contains ::), keep it
        2. If target matches a known method name exactly, use it
        3. If target has dots (receiver.method), try to resolve receiver
        4. If multiple matches, prefer same-file methods
        5. Fall back to the unresolved name
        """
        # Already resolved
        if "::" in target:
            return target

        # Get caller's file for same-file preference
        caller_file = caller_fqn.split("::")[0] if "::" in caller_fqn else ""

        # Handle dotted targets like ClassName.method or self-resolved
        if "." in target:
            parts = target.rsplit(".", 1)
            method_name = parts[-1]
            # Check if it's already a full FQN-style reference
            if "::" in parts[0]:
                # e.g., module.py::Class.method - already resolved
                return target
            # Try to find the method in matching class
            if method_name in name_to_fqns:
                candidates = name_to_fqns[method_name]
                # Prefer same-file match
                same_file = [c for c in candidates if c.startswith(caller_file + "::")]
                if same_file:
                    return same_file[0]
                if len(candidates) == 1:
                    return candidates[0]
            return target

        # Simple name lookup
        if target in name_to_fqns:
            candidates = name_to_fqns[target]
            # Same file preference
            same_file = [c for c in candidates if c.startswith(caller_file + "::")]
            if same_file:
                return same_file[0]
            if len(candidates) == 1:
                return candidates[0]
            # Multiple candidates - return first (ambiguous)
            return candidates[0]

        # Check if it's a class name (constructor call)
        if target in class_name_to_fqn:
            class_fqn = class_name_to_fqn[target]
            # Look for __init__ method
            init_fqn = "%s.__init__" % class_fqn
            if init_fqn in self.methods:
                return init_fqn
            return class_fqn

        # Unresolved - external or builtin
        return target

    def get_edges(self):
        """Get resolved edges (or raw if not resolved yet)."""
        if self._resolved_edges is not None:
            return self._resolved_edges
        return self.edges

    def compute_call_paths(self, max_depth=15, max_paths=200):
        """Compute all call paths from entry points.

        Entry points: methods/functions not called by any other method.

        Returns list of path dicts:
        [{"id": "path_N", "path": [fqn1, fqn2, ...], "depth": N, "complexity": N}]
        """
        if self._call_paths is not None:
            return self._call_paths

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
                continue  # skip private as entry points
            if fqn not in all_callees:
                entry_points.append(fqn)

        # DFS from each entry point
        paths = []
        path_id = 0
        for entry in entry_points:
            if path_id >= max_paths:
                break
            # Iterative DFS with path tracking
            stack = [(entry, [entry], 0)]
            while stack and path_id < max_paths:
                current, path, depth = stack.pop()
                if depth >= max_depth:
                    continue

                callees = adjacency.get(current, [])
                if not callees or depth >= max_depth - 1:
                    # Leaf node or max depth - record path if non-trivial
                    if len(path) >= 2:
                        total_cx = sum(
                            self.methods.get(fqn, {}).get("cyclomatic", 1)
                            for fqn in path
                            if fqn in self.methods
                        )
                        paths.append({
                            "id": "path_%d" % path_id,
                            "path": list(path),
                            "depth": len(path),
                            "total_complexity": total_cx,
                        })
                        path_id += 1
                else:
                    for callee in callees:
                        if callee in path:
                            continue  # avoid cycles
                        if callee not in self.methods:
                            continue  # skip unresolved
                        stack.append((callee, path + [callee], depth + 1))

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
            "total_functions": sum(
                1 for m in self.methods.values() if m["type"] == "function"
            ),
            "total_call_edges": len(call_edges),
            "total_inheritance_edges": len(inheritance_edges),
            "resolved_edges": len(resolved),
            "unresolved_edges": len(call_edges) - len(resolved),
            "files_analyzed": len(self.files),
            "max_call_depth": self.get_max_call_depth(),
            "avg_cyclomatic": _safe_avg(
                [m.get("cyclomatic", 1) for m in self.methods.values()]
            ),
            "max_cyclomatic": max(
                (m.get("cyclomatic", 1) for m in self.methods.values()),
                default=0,
            ),
        }

    def to_dict(self):
        """Serialize the full call graph to a dict.

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
            "call_paths": paths[:100],  # limit output size
        }

    def to_json(self, indent=2):
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


def _safe_avg(values):
    """Calculate average, return 0.0 for empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


# =========================================================================
# Call Graph Builder - Main Entry Point
# =========================================================================

EXCLUDED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "dist", "build", ".tox", ".eggs", ".mypy_cache",
    ".pytest_cache", ".ruff_cache",
}

MAX_FILES = 300
MAX_FILE_SIZE_KB = 100


class CallGraphBuilder:
    """Builds a complete call graph from Python source files.

    Args:
        project_root: Path to project root directory.
        max_files: Maximum number of files to analyze.
    """

    def __init__(self, project_root, max_files=MAX_FILES):
        self.project_root = Path(project_root)
        self.max_files = max_files

    def build(self):
        """Build the complete call graph.

        Returns:
            CallGraph instance with all nodes, edges, and computed paths.
        """
        graph = CallGraph()
        py_files = self._discover_files()

        for py_file in py_files:
            visitor = self._analyze_file(py_file)
            if visitor:
                graph.add_file_results(visitor)

        # Resolve call targets to known FQNs
        graph.resolve_edges()

        return graph

    def _discover_files(self):
        """Find source files to analyze (Python, Java, TypeScript, Kotlin)."""
        found = []
        extensions = [".py", ".java", ".ts", ".tsx", ".kt"]
        for ext in extensions:
            pattern = "**/*" + ext
            for src_file in self.project_root.glob(pattern):
                if len(found) >= self.max_files:
                    break
                if any(part in EXCLUDED_DIRS for part in src_file.parts):
                    continue
                try:
                    size_kb = src_file.stat().st_size / 1024
                    if size_kb > MAX_FILE_SIZE_KB:
                        continue
                except OSError:
                    continue
                found.append(src_file)
            if len(found) >= self.max_files:
                break
        return found

    def _analyze_file(self, src_file):
        """Route a source file to the correct language parser.

        Returns a visitor object (or None on failure) whose .classes,
        .methods, and .edges attributes match the _CallGraphVisitor shape.
        """
        ext = src_file.suffix.lower()
        if ext == ".py":
            return self._analyze_python(src_file)
        elif ext == ".java":
            return self._analyze_java(src_file)
        elif ext in (".ts", ".tsx"):
            return self._analyze_typescript(src_file)
        elif ext == ".kt":
            return self._analyze_kotlin(src_file)
        return None

    def _analyze_python(self, py_file):
        """Parse a single Python file and extract call graph data.

        Returns a _CallGraphVisitor or None on parse failure.
        """
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, ValueError):
            return None

        try:
            rel_path = str(py_file.relative_to(self.project_root))
        except ValueError:
            rel_path = py_file.name

        # Normalize path separators
        rel_path = rel_path.replace("\\", "/")

        visitor = _CallGraphVisitor(str(py_file), rel_path)
        visitor.visit(tree)
        return visitor

    def _analyze_java(self, java_file):
        """Parse a Java file using regex for classes, methods, and calls.

        This is best-effort regex parsing; it will not catch every pattern
        but covers the common cases without requiring an external parser.

        Returns a _RegexVisitor or None on read failure.
        """
        try:
            source = java_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(java_file.relative_to(self.project_root)).replace(os.sep, "/")
        except (OSError, ValueError):
            try:
                rel_path = java_file.name
                source = java_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None

        visitor = _RegexVisitor(str(java_file), rel_path)

        # --- Class detection ---
        # Matches: public/private/protected [abstract|final] class ClassName
        #          [extends Base] [implements I1, I2]
        class_pat = re.compile(
            r'(?:public|private|protected)?\s*'
            r'(?:abstract\s+|final\s+)?'
            r'class\s+(\w+)'
            r'(?:\s+extends\s+(\w+))?'
            r'(?:\s+implements\s+([\w,\s]+?))?'
            r'\s*\{',
            re.MULTILINE,
        )

        # Track last seen class for method attribution (simple linear scan)
        # Map: class name -> FQN (only supports one top-level class per scan)
        class_fqn_map = {}
        current_class = None

        for m in class_pat.finditer(source):
            cls_name = m.group(1)
            bases = []
            if m.group(2):
                bases.append(m.group(2).strip())
            if m.group(3):
                bases.extend(
                    b.strip() for b in m.group(3).split(",") if b.strip()
                )

            fqn = "%s::%s" % (rel_path, cls_name)
            line = source[: m.start()].count("\n") + 1
            visitor.classes.append(
                make_class_node(fqn, cls_name, rel_path, line, bases)
            )
            class_fqn_map[cls_name] = fqn
            # Use first class as the default owner for methods found below
            if current_class is None:
                current_class = cls_name

        # --- Method detection ---
        # Matches: [visibility] [static] [final] ReturnType methodName(params)
        method_pat = re.compile(
            r'(?:public|private|protected)\s+'
            r'(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?'
            r'(?:[\w<>\[\]]+)\s+'
            r'(\w+)\s*'
            r'\(([^)]*)\)'
            r'(?:\s+throws\s+[\w,\s]+)?'
            r'\s*\{',
            re.MULTILINE,
        )

        # Walk the source keeping a rough idea of which class we are in
        # by tracking brace depth relative to each class definition start.
        # For simplicity: assign method to the last class seen before the method.
        class_positions = []
        for m in class_pat.finditer(source):
            cls_name = m.group(1)
            class_positions.append((m.start(), cls_name))

        def _owner_at(pos):
            """Return the class name that owns the code at position pos."""
            owner = None
            for cpos, cname in class_positions:
                if cpos <= pos:
                    owner = cname
            return owner

        for m in method_pat.finditer(source):
            method_name = m.group(1)
            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        # "Type varName" -> keep "varName" only
                        parts = p.split()
                        params.append(parts[-1] if parts else p)

            owner_name = _owner_at(m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            line = source[: m.start()].count("\n") + 1
            visibility = "+"  # all captured methods have explicit visibility keyword

            visitor.methods.append(make_method_node(
                fqn, method_name, rel_path, line,
                parent_class=parent_fqn,
                params=params,
                visibility=visibility,
            ))

            # Register method in parent class node
            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Call detection ---
        # Matches: receiver.method( patterns
        call_pat = re.compile(r'(\w+)\.(\w+)\s*\(')
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(make_call_edge(
                "unknown",
                "%s.%s" % (receiver, method),
                line,
                "method_call",
            ))

        return visitor

    def _analyze_typescript(self, ts_file):
        """Parse a TypeScript/TSX file using regex.

        Covers: classes, methods (regular and arrow), function declarations,
        and obj.method() call patterns.

        Returns a _RegexVisitor or None on read failure.
        """
        try:
            source = ts_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(ts_file.relative_to(self.project_root)).replace(os.sep, "/")
        except (OSError, ValueError):
            try:
                rel_path = ts_file.name
                source = ts_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None

        visitor = _RegexVisitor(str(ts_file), rel_path)

        # --- Class detection ---
        # Matches: [export] [abstract] class ClassName [extends Base] [implements I1]
        class_pat = re.compile(
            r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)'
            r'(?:\s+extends\s+(\w+))?'
            r'(?:\s+implements\s+([\w,\s<>]+?))?'
            r'\s*\{',
            re.MULTILINE,
        )

        class_fqn_map = {}
        class_positions = []

        for m in class_pat.finditer(source):
            cls_name = m.group(1)
            bases = []
            if m.group(2):
                bases.append(m.group(2).strip())
            if m.group(3):
                bases.extend(
                    b.strip().split("<")[0]  # strip generics
                    for b in m.group(3).split(",")
                    if b.strip()
                )

            fqn = "%s::%s" % (rel_path, cls_name)
            line = source[: m.start()].count("\n") + 1
            visitor.classes.append(
                make_class_node(fqn, cls_name, rel_path, line, bases)
            )
            class_fqn_map[cls_name] = fqn
            class_positions.append((m.start(), cls_name))

        def _owner_at(pos):
            owner = None
            for cpos, cname in class_positions:
                if cpos <= pos:
                    owner = cname
            return owner

        # --- Regular method detection ---
        # Matches: [access modifier] [async] methodName(params)[: ReturnType] {
        method_pat = re.compile(
            r'(?:(?:public|private|protected|static|async)\s+)*'
            r'(?:async\s+)?'
            r'(\w+)\s*'
            r'(?:<[^>]*>)?\s*'   # optional generics
            r'\(([^)]*)\)'
            r'(?:\s*:\s*[\w<>\[\]|&\s]+?)?'   # optional return type
            r'\s*\{',
            re.MULTILINE,
        )

        # Keywords that should not be treated as method names
        _TS_KEYWORDS = frozenset({
            "if", "else", "for", "while", "do", "switch", "try", "catch",
            "finally", "return", "new", "delete", "typeof", "void", "class",
            "import", "export", "function", "const", "let", "var", "of", "in",
        })

        for m in method_pat.finditer(source):
            method_name = m.group(1)
            if method_name in _TS_KEYWORDS:
                continue

            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        # "paramName: Type" -> keep "paramName"
                        params.append(p.split(":")[0].split("=")[0].strip())

            owner_name = _owner_at(m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            line = source[: m.start()].count("\n") + 1
            visibility = "-" if method_name.startswith("_") else "+"

            visitor.methods.append(make_method_node(
                fqn, method_name, rel_path, line,
                parent_class=parent_fqn,
                params=params,
                visibility=visibility,
            ))

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Arrow function properties in classes ---
        # Matches: methodName = (params) =>
        arrow_pat = re.compile(
            r'(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*[\w<>\[\]|&\s]+?)?\s*=>',
            re.MULTILINE,
        )
        for m in arrow_pat.finditer(source):
            method_name = m.group(1)
            if method_name in _TS_KEYWORDS:
                continue

            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        params.append(p.split(":")[0].split("=")[0].strip())

            owner_name = _owner_at(m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            # Skip if already added by method_pat
            existing_ids = {mth["id"] for mth in visitor.methods}
            if fqn in existing_ids:
                continue

            line = source[: m.start()].count("\n") + 1
            visitor.methods.append(make_method_node(
                fqn, method_name, rel_path, line,
                parent_class=parent_fqn,
                params=params,
                visibility="-" if method_name.startswith("_") else "+",
            ))

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Standalone function declarations ---
        func_pat = re.compile(
            r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*'
            r'(?:<[^>]*>)?\s*\(([^)]*)\)',
            re.MULTILINE,
        )
        for m in func_pat.finditer(source):
            func_name = m.group(1)
            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        params.append(p.split(":")[0].split("=")[0].strip())

            fqn = "%s::%s" % (rel_path, func_name)
            existing_ids = {mth["id"] for mth in visitor.methods}
            if fqn in existing_ids:
                continue

            line = source[: m.start()].count("\n") + 1
            visitor.methods.append(make_method_node(
                fqn, func_name, rel_path, line,
                parent_class=None,
                params=params,
                visibility="+",
            ))

        # --- Call detection ---
        call_pat = re.compile(r'(\w+)\.(\w+)\s*\(')
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(make_call_edge(
                "unknown",
                "%s.%s" % (receiver, method),
                line,
                "method_call",
            ))

        return visitor

    def _analyze_kotlin(self, kt_file):
        """Parse a Kotlin file using regex.

        Covers: class/data class/sealed class, fun methodName(params): Type,
        suspend fun, companion object, and obj.method() call patterns.

        Returns a _RegexVisitor or None on read failure.
        """
        try:
            source = kt_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(kt_file.relative_to(self.project_root)).replace(os.sep, "/")
        except (OSError, ValueError):
            try:
                rel_path = kt_file.name
                source = kt_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None

        visitor = _RegexVisitor(str(kt_file), rel_path)

        # --- Class detection ---
        # Matches: [modifiers] class/interface/object ClassName [: Base1, Base2]
        class_pat = re.compile(
            r'(?:(?:open|abstract|sealed|data|inner|enum|annotation|companion)\s+)*'
            r'(?:class|interface|object)\s+(\w+)'
            r'(?:\s*<[^>]*>)?'           # optional generics
            r'(?:[^{:]*:\s*([\w<>,\s()]+?))?'  # optional supertype list
            r'\s*[{(]',
            re.MULTILINE,
        )

        class_fqn_map = {}
        class_positions = []

        for m in class_pat.finditer(source):
            cls_name = m.group(1)
            bases = []
            if m.group(2):
                for b in m.group(2).split(","):
                    b = b.strip().split("<")[0].split("(")[0].strip()
                    if b:
                        bases.append(b)

            fqn = "%s::%s" % (rel_path, cls_name)
            line = source[: m.start()].count("\n") + 1
            visitor.classes.append(
                make_class_node(fqn, cls_name, rel_path, line, bases)
            )
            class_fqn_map[cls_name] = fqn
            class_positions.append((m.start(), cls_name))

        def _owner_at(pos):
            owner = None
            for cpos, cname in class_positions:
                if cpos <= pos:
                    owner = cname
            return owner

        # --- Function detection ---
        # Matches: [modifiers] fun [<generics>] functionName(params)[: ReturnType]
        fun_pat = re.compile(
            r'(?:(?:public|private|protected|internal|override|open|abstract'
            r'|suspend|inline|infix|operator|external|tailrec)\s+)*'
            r'fun\s+'
            r'(?:<[^>]*>\s*)?'       # optional generics before name
            r'(\w+)\s*'
            r'\(([^)]*)\)'
            r'(?:\s*:\s*[\w<>\[\]?!]+)?',  # optional return type
            re.MULTILINE,
        )

        _KT_KEYWORDS = frozenset({"if", "else", "for", "while", "when", "return"})

        for m in fun_pat.finditer(source):
            func_name = m.group(1)
            if func_name in _KT_KEYWORDS:
                continue

            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        # "paramName: Type = default" -> keep "paramName"
                        params.append(p.split(":")[0].split("=")[0].strip())

            owner_name = _owner_at(m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, func_name)
            else:
                fqn = "%s::%s" % (rel_path, func_name)

            line = source[: m.start()].count("\n") + 1
            visibility = "-" if func_name.startswith("_") else "+"

            visitor.methods.append(make_method_node(
                fqn, func_name, rel_path, line,
                parent_class=parent_fqn,
                params=params,
                visibility=visibility,
            ))

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Call detection ---
        call_pat = re.compile(r'(\w+)\.(\w+)\s*\(')
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(make_call_edge(
                "unknown",
                "%s.%s" % (receiver, method),
                line,
                "method_call",
            ))

        return visitor


# =========================================================================
# Integration helpers for existing code
# =========================================================================

def build_call_graph(project_path):
    """Convenience function to build a call graph from a project path.

    Args:
        project_path: String or Path to project root.

    Returns:
        CallGraph instance, or None on failure.
    """
    try:
        builder = CallGraphBuilder(project_path)
        return builder.build()
    except Exception:
        return None


def get_call_graph_metrics(project_path):
    """Get call graph metrics dict for integration with complexity calculator.

    Returns dict compatible with graph_metrics enrichment:
    {
        "method_call_depth": int,
        "method_call_count": int,
        "total_classes": int,
        "total_methods": int,
        "entry_points": list,
        "resolved_ratio": float,
        "avg_method_complexity": float,
        "max_method_complexity": int,
        "call_graph_available": bool,
    }
    """
    graph = build_call_graph(project_path)
    if graph is None:
        return {"call_graph_available": False}

    stats = graph.get_stats()

    # Find entry points (public methods not called by others)
    edges = graph.get_edges()
    all_callees = set()
    for edge in edges:
        if edge["type"] != "inheritance":
            all_callees.add(edge["to"])

    entry_points = []
    for fqn, method in graph.methods.items():
        if method["visibility"] == "+" and fqn not in all_callees:
            entry_points.append(fqn)

    total_call_edges = stats["total_call_edges"]
    resolved = stats["resolved_edges"]
    ratio = (resolved / total_call_edges) if total_call_edges > 0 else 0.0

    return {
        "method_call_depth": stats["max_call_depth"],
        "method_call_count": total_call_edges,
        "total_classes": stats["total_classes"],
        "total_methods": stats["total_methods"],
        "entry_points": sorted(entry_points)[:20],
        "resolved_ratio": round(ratio, 2),
        "avg_method_complexity": stats["avg_cyclomatic"],
        "max_method_complexity": stats["max_cyclomatic"],
        "call_graph_available": True,
    }


def get_impact_analysis(project_path, target_fqn):
    """Get impact analysis for a specific method/class.

    Args:
        project_path: Path to project root.
        target_fqn: FQN of the method to analyze (e.g., "module.py::Class.method")

    Returns:
        Dict with affected methods and call paths through the target.
    """
    graph = build_call_graph(project_path)
    if graph is None:
        return {"error": "Could not build call graph"}

    impact = graph.compute_impact_map()
    affected = impact.get(target_fqn, set())

    # Get call paths that include this target
    paths = graph.compute_call_paths()
    relevant_paths = [p for p in paths if target_fqn in p["path"]]

    return {
        "target": target_fqn,
        "directly_affected": sorted(affected),
        "affected_count": len(affected),
        "call_paths_through_target": relevant_paths[:20],
    }


# =========================================================================
# Backward compatibility: parsers/ package
# =========================================================================
#
# The language-specific parsing logic has been extracted into the
# parsers/ sub-package alongside this module:
#
#   parsers/__init__.py        - ParserRegistry (Abstract Factory)
#   parsers/base.py            - AbstractLanguageParser + _VisitorResult
#   parsers/graph_model.py     - CallGraph, make_class_node, make_method_node,
#                                make_call_edge
#   parsers/config.py          - MAX_FILES, MAX_FILE_SIZE_KB, SUPPORTED_EXTENSIONS
#   parsers/python_parser.py   - PythonASTParser  (.py  - full AST)
#   parsers/java_parser.py     - JavaRegexParser  (.java - regex)
#   parsers/typescript_parser.py - TypeScriptRegexParser (.ts, .tsx - regex)
#   parsers/kotlin_parser.py   - KotlinRegexParser (.kt  - regex)
#
# CallGraphBuilder._analyze_file() continues to use _RegexVisitor and the
# inline _analyze_java/_analyze_typescript/_analyze_kotlin methods defined
# above for internal builds.  New callers should use ParserRegistry from the
# parsers/ package directly.
#
# Example:
#   from scripts.langgraph_engine.parsers import ParserRegistry
#   parser = ParserRegistry.get_parser(".java")
#   visitor = parser.parse_file_to_visitor(file_path, content, rel_path)
# =========================================================================
