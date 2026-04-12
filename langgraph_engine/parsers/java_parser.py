"""
Java regex-based parser (Strategy Pattern concrete implementation).

JavaRegexParser extracts classes, methods, and call edges from Java source
files using regex patterns. Best-effort coverage of common patterns without
requiring an external Java parser.

ASCII-only (cp1252-safe for Windows).
"""

import re

from .base import AbstractLanguageParser
from .graph_model import make_call_edge, make_class_node, make_method_node

# =========================================================================
# Concrete parser
# =========================================================================


class JavaRegexParser(AbstractLanguageParser):
    """Java parser using regex patterns for class and method extraction.

    Covers: public/private/protected [abstract|final] class definitions,
    method declarations with visibility modifiers, and obj.method() calls.
    Uses positional class tracking to assign methods to their owner class.
    """

    # Matches: [visibility] [abstract|final] class ClassName
    #          [extends Base] [implements I1, I2] {
    _CLASS_PAT = re.compile(
        r"(?:public|private|protected)?\s*"
        r"(?:abstract\s+|final\s+)?"
        r"class\s+(\w+)"
        r"(?:\s+extends\s+(\w+))?"
        r"(?:\s+implements\s+([\w,\s]+?))?"
        r"\s*\{",
        re.MULTILINE,
    )

    # Matches: [visibility] [static] [final] [synchronized] ReturnType
    #          methodName(params) [throws ...] {
    _METHOD_PAT = re.compile(
        r"(?:public|private|protected)\s+"
        r"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?"
        r"(?:[\w<>\[\]]+)\s+"
        r"(\w+)\s*"
        r"\(([^)]*)\)"
        r"(?:\s+throws\s+[\w,\s]+)?"
        r"\s*\{",
        re.MULTILINE,
    )

    # Matches: receiver.method(
    _CALL_PAT = re.compile(r"(\w+)\.(\w+)\s*\(")

    @property
    def language(self):
        # type: () -> str
        return "java"

    @property
    def file_extensions(self):
        # type: () -> Set[str]
        return frozenset({".java"})

    def parse_file(self, file_path, content):
        # type: (str, str) -> Dict[str, Any]
        """Parse a Java source file.

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
        """Extract class definitions from Java source.

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
        """Extract method definitions from Java source.

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
                bases.extend(b.strip() for b in m.group(3).split(",") if b.strip())

            fqn = "%s::%s" % (rel_path, cls_name)
            line = content[: m.start()].count("\n") + 1
            visitor.classes.append(make_class_node(fqn, cls_name, rel_path, line, bases))
            class_fqn_map[cls_name] = fqn
            class_positions.append((m.start(), cls_name))

        # --- Method detection ---
        for m in self._METHOD_PAT.finditer(content):
            method_name = m.group(1)
            params_raw = m.group(2).strip()
            params = []
            if params_raw:
                for p in params_raw.split(","):
                    p = p.strip()
                    if p:
                        parts = p.split()
                        params.append(parts[-1] if parts else p)

            owner_name = _owner_at(class_positions, m.start())
            parent_fqn = class_fqn_map.get(owner_name) if owner_name else None

            if parent_fqn:
                fqn = "%s::%s.%s" % (rel_path, owner_name, method_name)
            else:
                fqn = "%s::%s" % (rel_path, method_name)

            line = content[: m.start()].count("\n") + 1

            visitor.methods.append(
                make_method_node(
                    fqn,
                    method_name,
                    rel_path,
                    line,
                    parent_class=parent_fqn,
                    params=params,
                    visibility="+",  # all captured methods have explicit visibility
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

    Scans class_positions (list of (start_pos, class_name)) and returns
    the last class whose definition started before pos.

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
