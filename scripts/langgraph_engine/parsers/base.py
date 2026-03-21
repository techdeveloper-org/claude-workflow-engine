"""
Abstract base class for language-specific parsers (Strategy Pattern).

Each concrete parser implements file parsing for its language.
The Abstract Factory (ParserRegistry in __init__.py) creates the right
parser instance based on file extension.

ASCII-only (cp1252-safe for Windows).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set


class AbstractLanguageParser(ABC):
    """Abstract base class for language-specific parsers.

    Concrete subclasses implement parse_file(), extract_classes(), and
    extract_methods() for their respective language.

    The parser returns a plain visitor-like object whose .classes,
    .methods, .edges, and .rel_path attributes are consumed by
    CallGraph.add_file_results().
    """

    # ------------------------------------------------------------------
    # Identity contract
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def language(self):
        # type: () -> str
        """Language name (e.g. 'python', 'java').

        Returns:
            str: lowercase language identifier.
        """

    @property
    @abstractmethod
    def file_extensions(self):
        # type: () -> Set[str]
        """Set of file extensions handled by this parser (e.g. {'.py'}).

        Returns:
            frozenset or set of strings, each starting with a dot.
        """

    # ------------------------------------------------------------------
    # Parsing contract
    # ------------------------------------------------------------------

    @abstractmethod
    def parse_file(self, file_path, content):
        # type: (str, str) -> Dict[str, Any]
        """Parse a source file and extract classes, methods, and calls.

        Args:
            file_path: Absolute path of the file (used for error context).
            content: Full source text of the file.

        Returns:
            A dict with keys:
            {
                "classes":  [{"name": ..., "fqn": ..., "methods": [...],
                               "file": ..., "line": ..., "bases": [...]}],
                "methods":  [{"name": ..., "fqn": ..., "class": ...,
                               "file": ..., "line": ...}],
                "calls":    [{"caller_fqn": ..., "callee_fqn": ...,
                               "line": ..., "type": ...}],
                "imports":  [{"module": ..., "name": ...}],
            }

            Note: for backward compatibility with CallGraph.add_file_results()
            the concrete parsers also expose the results on .classes,
            .methods, and .edges attributes of a visitor object returned
            by parse_file_to_visitor().
        """

    @abstractmethod
    def extract_classes(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract class definitions from source code.

        Args:
            content: Full source text.
            file_path: Relative path (used to build FQNs).

        Returns:
            List of class node dicts (compatible with make_class_node
            output from graph_model.py).
        """

    @abstractmethod
    def extract_methods(self, content, file_path):
        # type: (str, str) -> List[Dict[str, Any]]
        """Extract method/function definitions from source code.

        Args:
            content: Full source text.
            file_path: Relative path (used to build FQNs).

        Returns:
            List of method/function node dicts (compatible with
            make_method_node output from graph_model.py).
        """

    # ------------------------------------------------------------------
    # Shared helper: visitor-style result object
    # ------------------------------------------------------------------

    def _make_visitor(self, rel_path, file_path=""):
        """Create a simple namespace to hold parse results.

        The returned object has the same shape as the original
        _CallGraphVisitor and _RegexVisitor objects so that
        CallGraph.add_file_results() works unchanged.

        Args:
            rel_path: Relative path string stored on the visitor.
            file_path: Absolute path string stored on the visitor.

        Returns:
            A _VisitorResult instance.
        """
        return _VisitorResult(file_path=file_path or rel_path, rel_path=rel_path)


class _VisitorResult:
    """Plain namespace that holds the outputs of a single-file parse.

    Matches the interface expected by CallGraph.add_file_results().
    """

    def __init__(self, file_path, rel_path):
        self.file_path = file_path
        self.rel_path = rel_path
        self.classes = []   # list of class node dicts
        self.methods = []   # list of method/function node dicts
        self.edges = []     # list of call edge dicts
