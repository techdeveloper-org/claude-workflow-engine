"""
TypeScript/TSX regex-based parser (Strategy Pattern concrete implementation).

TypeScriptRegexParser extracts classes, methods (regular, arrow, and
standalone function declarations), and call edges from .ts and .tsx source
files using regex patterns.

ASCII-only (cp1252-safe for Windows).
"""

import re

from .base import AbstractLanguageParser
from .graph_model import make_call_edge, make_class_node, make_method_node

# Keywords that must not be treated as method names when matched by the
# broad method pattern.
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


# =========================================================================
# Concrete parser
# =========================================================================


class TypeScriptRegexParser(AbstractLanguageParser):
    """TypeScript/TSX parser using regex patterns.

    Covers:
    - Class declarations (exported, abstract, with extends/implements)
    - Regular method declarations inside classes
    - Arrow-function properties inside classes
    - Standalone function declarations (exported or not)
    - obj.method() call patterns

    Uses positional class tracking (_owner_at) to assign methods to
    their enclosing class.
    """

    # [export] [abstract] class ClassName [extends Base] [implements I1, ...] {
    _CLASS_PAT = re.compile(
        r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"
        r"(?:\s+extends\s+(\w+))?"
        r"(?:\s+implements\s+([\w,\s<>]+?))?"
        r"\s*\{",
        re.MULTILINE,
    )

    # [access modifiers] [async] methodName [<generics>](params)[: ReturnType] {
    _METHOD_PAT = re.compile(
        r"(?:(?:public|private|protected|static|async)\s+)*"
        r"(?:async\s+)?"
        r"(\w+)\s*"
        r"(?:<[^>]*>)?\s*"
        r"\(([^)]*)\)"
        r"(?:\s*:\s*[\w<>\[\]|&\s]+?)?"
        r"\s*\{",
        re.MULTILINE,
    )

    # name = [async] (params)[: ReturnType] =>
    _ARROW_PAT = re.compile(
        r"(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*[\w<>\[\]|&\s]+?)?\s*=>",
        re.MULTILINE,
    )

    # [export] [default] [async] function name [<generics>](params)
    _FUNC_PAT = re.compile(
        r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*" r"(?:<[^>]*>)?\s*\(([^)]*)\)",
        re.MULTILINE,
    )

    # receiver.method(
    _CALL_PAT = re.compile(r"(\w+)\.(\w+)\s*\(")

    @property
    def language(self):
        # type: () -> str
        return "typescript"

    @property
    def file_extensions(self):
        # type: () -> Set[str]
        return frozenset({".ts", ".tsx"})

    def parse_file(self, file_path, content):
        # type: (str, str) -> Dict[str, Any]
        """Parse a TypeScript/TSX source file.

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
        """Extract class definitions from TypeScript source.

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
        """Extract method/function definitions from TypeScript source.

        Args:
            content: Full source text.
            file_path: Relative path used for FQN construction.

        Returns:
            List of method node dicts.
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
                bases.append(m.group(2).strip())
            if m.group(3):
                bases.extend(
                    b.strip().split("<")[0]  # strip generics from interface names
                    for b in m.group(3).split(",")
                    if b.strip()
                )

            fqn = "%s::%s" % (rel_path, cls_name)
            line = content[: m.start()].count("\n") + 1
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
            class_fqn_map[cls_name] = fqn
            class_positions.append((m.start(), cls_name))

        # --- Regular method detection ---
        for m in self._METHOD_PAT.finditer(content):
            method_name = m.group(1)
            if method_name in _TS_KEYWORDS:
                continue

            params = _parse_ts_params(m.group(2))
            owner_name = _owner_at(class_positions, m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            line = content[: m.start()].count("\n") + 1
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

        # --- Arrow function properties ---
        existing_ids = {mth["id"] for mth in visitor.methods}
        for m in self._ARROW_PAT.finditer(content):
            method_name = m.group(1)
            if method_name in _TS_KEYWORDS:
                continue

            params = _parse_ts_params(m.group(2))
            owner_name = _owner_at(class_positions, m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            if fqn in existing_ids:
                continue
            existing_ids.add(fqn)

            line = content[: m.start()].count("\n") + 1
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
        for m in self._FUNC_PAT.finditer(content):
            func_name = m.group(1)
            params = _parse_ts_params(m.group(2))
            fqn = "%s::%s" % (rel_path, func_name)

            if fqn in existing_ids:
                continue
            existing_ids.add(fqn)

            line = content[: m.start()].count("\n") + 1
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


def _parse_ts_params(params_raw):
    """Parse a TypeScript parameter list string into a list of param names.

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
