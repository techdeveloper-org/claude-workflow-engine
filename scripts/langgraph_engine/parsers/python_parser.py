"""
Python AST parser (Strategy Pattern concrete implementation).

PythonASTParser wraps the _CallGraphVisitor AST NodeVisitor to extract
classes, methods, and call edges from Python source files.

ASCII-only (cp1252-safe for Windows).
"""

import ast
from typing import Any, Dict, List, Set

from .base import AbstractLanguageParser
from .graph_model import make_class_node, make_call_edge, make_method_node


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
# AST Visitor
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
# Concrete parser
# =========================================================================

class PythonASTParser(AbstractLanguageParser):
    """Python parser using ast.NodeVisitor for full FQN resolution.

    Extracts classes, methods, and call edges from .py source files.
    Uses the _CallGraphVisitor to walk the AST in tree order so that
    class/method context stacks are maintained correctly.
    """

    @property
    def language(self):
        # type: () -> str
        return "python"

    @property
    def file_extensions(self):
        # type: () -> Set[str]
        return frozenset({".py"})

    def parse_file(self, file_path, content):
        # type: (str, str) -> Dict[str, Any]
        """Parse a Python source file.

        Args:
            file_path: Absolute path (used as rel_path fallback).
            content: Full source text.

        Returns:
            Dict with keys 'classes', 'methods', 'calls', 'imports'.
        """
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError):
            return {"classes": [], "methods": [], "calls": [], "imports": []}

        visitor = _CallGraphVisitor(file_path, file_path)
        visitor.visit(tree)

        calls = [
            {
                "caller_fqn": e["from"],
                "callee_fqn": e["to"],
                "line": e["line"],
                "type": e["type"],
            }
            for e in visitor.edges
        ]

        return {
            "classes": visitor.classes,
            "methods": visitor.methods,
            "calls": calls,
            "imports": [],
        }

    def parse_file_to_visitor(self, file_path, content, rel_path=None):
        """Parse source and return a visitor-compatible result object.

        This is the primary entry point used by CallGraphBuilder._analyze_file().

        Args:
            file_path: Absolute path string.
            content: Source text.
            rel_path: Relative path for FQN construction. Defaults to file_path.

        Returns:
            _CallGraphVisitor instance (has .classes, .methods, .edges, .rel_path).
        """
        effective_rel = rel_path or file_path
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError):
            result = self._make_visitor(effective_rel, file_path)
            return result

        v = _CallGraphVisitor(file_path, effective_rel)
        v.visit(tree)
        return v

    def extract_classes(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract class definitions from Python source.

        Args:
            content: Full source text.
            file_path: Relative path used for FQN construction.

        Returns:
            List of class node dicts.
        """
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError):
            return []

        v = _CallGraphVisitor(file_path, file_path)
        v.visit(tree)
        return v.classes

    def extract_methods(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract method/function definitions from Python source.

        Args:
            content: Full source text.
            file_path: Relative path used for FQN construction.

        Returns:
            List of method/function node dicts.
        """
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError):
            return []

        v = _CallGraphVisitor(file_path, file_path)
        v.visit(tree)
        return v.methods
