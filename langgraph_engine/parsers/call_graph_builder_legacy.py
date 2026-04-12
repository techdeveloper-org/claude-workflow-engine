# ruff: noqa: F821
"""parsers/call_graph_builder_legacy.py - Legacy CallGraphBuilder class.

Extracted from call_graph_builder.py. Contains the builder orchestrator
and public convenience functions.

Windows-safe: ASCII only.
"""
import ast
import logging
import os
from pathlib import Path

from .graph_model import CallGraph

logger = logging.getLogger(__name__)


def _safe_avg(values):
    """Calculate average, return 0.0 for empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


# =========================================================================
# Call Graph Builder - Main Entry Point
# =========================================================================

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
            r"(?:public|private|protected)?\s*"
            r"(?:abstract\s+|final\s+)?"
            r"class\s+(\w+)"
            r"(?:\s+extends\s+(\w+))?"
            r"(?:\s+implements\s+([\w,\s]+?))?"
            r"\s*\{",
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
                bases.extend(b.strip() for b in m.group(3).split(",") if b.strip())

            fqn = "%s::%s" % (rel_path, cls_name)
            line = source[: m.start()].count("\n") + 1
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
            class_fqn_map[cls_name] = fqn
            # Use first class as the default owner for methods found below
            if current_class is None:
                current_class = cls_name

        # --- Method detection ---
        # Matches: [visibility] [static] [final] ReturnType methodName(params)
        method_pat = re.compile(
            r"(?:public|private|protected)\s+"
            r"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?"
            r"(?:[\w<>\[\]]+)\s+"
            r"(\w+)\s*"
            r"\(([^)]*)\)"
            r"(?:\s+throws\s+[\w,\s]+)?"
            r"\s*\{",
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

            visitor.methods.append(
                make_method_node(
                    fqn,
                    method_name,
                    rel_path,
                    line,
                    parent_class=parent_fqn,
                    params=params,
                    visibility=visibility,
                )
            )

            # Register method in parent class node
            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Call detection ---
        # Matches: receiver.method( patterns
        call_pat = re.compile(r"(\w+)\.(\w+)\s*\(")
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(
                make_call_edge(
                    "unknown",
                    "%s.%s" % (receiver, method),
                    line,
                    "method_call",
                )
            )

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
            r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"
            r"(?:\s+extends\s+(\w+))?"
            r"(?:\s+implements\s+([\w,\s<>]+?))?"
            r"\s*\{",
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
                bases.extend(b.strip().split("<")[0] for b in m.group(3).split(",") if b.strip())  # strip generics

            fqn = "%s::%s" % (rel_path, cls_name)
            line = source[: m.start()].count("\n") + 1
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
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
            r"(?:(?:public|private|protected|static|async)\s+)*"
            r"(?:async\s+)?"
            r"(\w+)\s*"
            r"(?:<[^>]*>)?\s*"  # optional generics
            r"\(([^)]*)\)"
            r"(?:\s*:\s*[\w<>\[\]|&\s]+?)?"  # optional return type
            r"\s*\{",
            re.MULTILINE,
        )

        # Keywords that should not be treated as method names
        _TS_KEYWORDS = frozenset(
            {
                "if",
                "else",
                "for",
                "while",
                "do",
                "switch",
                "try",
                "catch",
                "finally",
                "return",
                "new",
                "delete",
                "typeof",
                "void",
                "class",
                "import",
                "export",
                "function",
                "const",
                "let",
                "var",
                "of",
                "in",
            }
        )

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

            visitor.methods.append(
                make_method_node(
                    fqn,
                    method_name,
                    rel_path,
                    line,
                    parent_class=parent_fqn,
                    params=params,
                    visibility=visibility,
                )
            )

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Arrow function properties in classes ---
        # Matches: methodName = (params) =>
        arrow_pat = re.compile(
            r"(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*[\w<>\[\]|&\s]+?)?\s*=>",
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
            visitor.methods.append(
                make_method_node(
                    fqn,
                    method_name,
                    rel_path,
                    line,
                    parent_class=parent_fqn,
                    params=params,
                    visibility="-" if method_name.startswith("_") else "+",
                )
            )

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Standalone function declarations ---
        func_pat = re.compile(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*" r"(?:<[^>]*>)?\s*\(([^)]*)\)",
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
            visitor.methods.append(
                make_method_node(
                    fqn,
                    func_name,
                    rel_path,
                    line,
                    parent_class=None,
                    params=params,
                    visibility="+",
                )
            )

        # --- Call detection ---
        call_pat = re.compile(r"(\w+)\.(\w+)\s*\(")
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(
                make_call_edge(
                    "unknown",
                    "%s.%s" % (receiver, method),
                    line,
                    "method_call",
                )
            )

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
            r"(?:(?:open|abstract|sealed|data|inner|enum|annotation|companion)\s+)*"
            r"(?:class|interface|object)\s+(\w+)"
            r"(?:\s*<[^>]*>)?"  # optional generics
            r"(?:[^{:]*:\s*([\w<>,\s()]+?))?"  # optional supertype list
            r"\s*[{(]",
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
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
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
            r"(?:(?:public|private|protected|internal|override|open|abstract"
            r"|suspend|inline|infix|operator|external|tailrec)\s+)*"
            r"fun\s+"
            r"(?:<[^>]*>\s*)?"  # optional generics before name
            r"(\w+)\s*"
            r"\(([^)]*)\)"
            r"(?:\s*:\s*[\w<>\[\]?!]+)?",  # optional return type
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

            visitor.methods.append(
                make_method_node(
                    fqn,
                    func_name,
                    rel_path,
                    line,
                    parent_class=parent_fqn,
                    params=params,
                    visibility=visibility,
                )
            )

            if parent_fqn:
                for cls in visitor.classes:
                    if cls["id"] == parent_fqn:
                        cls["methods"].append(fqn)
                        break

        # --- Call detection ---
        call_pat = re.compile(r"(\w+)\.(\w+)\s*\(")
        for m in call_pat.finditer(source):
            receiver = m.group(1)
            method = m.group(2)
            line = source[: m.start()].count("\n") + 1
            visitor.edges.append(
                make_call_edge(
                    "unknown",
                    "%s.%s" % (receiver, method),
                    line,
                    "method_call",
                )
            )

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
#   from langgraph_engine.parsers import ParserRegistry
#   parser = ParserRegistry.get_parser(".java")
#   visitor = parser.parse_file_to_visitor(file_path, content, rel_path)
# =========================================================================
