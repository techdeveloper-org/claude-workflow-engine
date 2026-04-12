"""
Kotlin regex-based parser (Strategy Pattern concrete implementation).

KotlinRegexParser extracts classes, functions, and call edges from .kt
source files using regex patterns. Covers class/interface/object/data class
declarations, fun function definitions (including suspend, override, etc.),
and obj.method() call patterns.

ASCII-only (cp1252-safe for Windows).
"""

import re

from .base import AbstractLanguageParser
from .graph_model import make_call_edge, make_class_node, make_method_node

# Keywords that must not be treated as function names when matched by the
# broad fun pattern (e.g., control flow that shares syntax).
_KT_KEYWORDS = frozenset({"if", "else", "for", "while", "when", "return"})


# =========================================================================
# Concrete parser
# =========================================================================


class KotlinRegexParser(AbstractLanguageParser):
    """Kotlin parser using regex patterns for class and function extraction.

    Covers:
    - class / interface / object / data class / sealed class declarations
    - fun function definitions with optional modifiers (suspend, override,
      internal, open, abstract, inline, infix, operator, etc.)
    - Optional generics before function name
    - Optional return type annotation
    - obj.method() call patterns

    Uses positional class tracking (_owner_at) to assign functions to
    their enclosing class/object.
    """

    # [modifiers] class|interface|object ClassName [<generics>]
    #             [: SuperType1, SuperType2] { or (
    _CLASS_PAT = re.compile(
        r"(?:(?:open|abstract|sealed|data|inner|enum|annotation|companion)\s+)*"
        r"(?:class|interface|object)\s+(\w+)"
        r"(?:\s*<[^>]*>)?"
        r"(?:[^{:]*:\s*([\w<>,\s()]+?))?"
        r"\s*[{(]",
        re.MULTILINE,
    )

    # [modifiers] fun [<generics>] functionName(params)[: ReturnType]
    _FUN_PAT = re.compile(
        r"(?:(?:public|private|protected|internal|override|open|abstract"
        r"|suspend|inline|infix|operator|external|tailrec)\s+)*"
        r"fun\s+"
        r"(?:<[^>]*>\s*)?"
        r"(\w+)\s*"
        r"\(([^)]*)\)"
        r"(?:\s*:\s*[\w<>\[\]?!]+)?",
        re.MULTILINE,
    )

    # receiver.method(
    _CALL_PAT = re.compile(r"(\w+)\.(\w+)\s*\(")

    @property
    def language(self):
        # type: () -> str
        return "kotlin"

    @property
    def file_extensions(self):
        # type: () -> Set[str]
        return frozenset({".kt"})

    def parse_file(self, file_path, content):
        # type: (str, str) -> Dict[str, Any]
        """Parse a Kotlin source file.

        Args:
            file_path: Absolute or relative path (used as rel_path).
            content: Full source text.

        Returns:
            Dict with keys 'classes', 'methods', 'calls', 'imports'.
        """
        visitor = self._parse_to_visitor(file_path, content, file_path)
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
            _VisitorResult instance (has .classes, .methods, .edges, .rel_path).
        """
        effective_rel = rel_path or file_path
        return self._parse_to_visitor(file_path, content, effective_rel)

    def extract_classes(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract class/interface/object definitions from Kotlin source.

        Args:
            content: Full source text.
            file_path: Relative path used for FQN construction.

        Returns:
            List of class node dicts.
        """
        visitor = self._parse_to_visitor(file_path, content, file_path)
        return visitor.classes

    def extract_methods(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract function definitions from Kotlin source.

        Args:
            content: Full source text.
            file_path: Relative path used for FQN construction.

        Returns:
            List of method/function node dicts.
        """
        visitor = self._parse_to_visitor(file_path, content, file_path)
        return visitor.methods

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _parse_to_visitor(self, file_path, content, rel_path):
        """Run all regex passes over content and return a _VisitorResult."""
        visitor = self._make_visitor(rel_path, file_path)

        class_fqn_map = {}
        class_positions = []

        # --- Class detection ---
        for m in self._CLASS_PAT.finditer(content):
            cls_name = m.group(1)
            bases = []
            if m.group(2):
                for b in m.group(2).split(","):
                    # Strip generics and constructor parens: "Base<T>(arg)" -> "Base"
                    b = b.strip().split("<")[0].split("(")[0].strip()
                    if b:
                        bases.append(b)

            fqn = "%s::%s" % (rel_path, cls_name)
            line = content[: m.start()].count("\n") + 1
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
            class_fqn_map[cls_name] = fqn
            class_positions.append((m.start(), cls_name))

        # --- Function detection ---
        for m in self._FUN_PAT.finditer(content):
            func_name = m.group(1)
            if func_name in _KT_KEYWORDS:
                continue

            params = _parse_kt_params(m.group(2))
            owner_name = _owner_at(class_positions, m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, func_name)
            else:
                fqn = "%s::%s" % (rel_path, func_name)

            line = content[: m.start()].count("\n") + 1
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
        for m in self._CALL_PAT.finditer(content):
            receiver = m.group(1)
            method = m.group(2)
            line = content[: m.start()].count("\n") + 1
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
# Module-level helpers
# =========================================================================


def _owner_at(class_positions, pos):
    """Return the class name that owns the code at byte position pos.

    Args:
        class_positions: List of (int, str) tuples sorted by appearance.
        pos: Character offset in the source string.

    Returns:
        Class name string, or None if no class precedes pos.
    """
    owner = None
    for cpos, cname in class_positions:
        if cpos <= pos:
            owner = cname
    return owner


def _parse_kt_params(params_raw):
    """Parse a Kotlin parameter list string into a list of param names.

    Strips type annotations and default values, keeping only the
    parameter name for each comma-separated entry.

    Args:
        params_raw: Raw string content between the parentheses.

    Returns:
        List of parameter name strings (may be empty).
    """
    params = []
    if not params_raw:
        return params
    for p in params_raw.split(","):
        p = p.strip()
        if p:
            # "paramName: Type = default" -> "paramName"
            params.append(p.split(":")[0].split("=")[0].strip())
    return params
