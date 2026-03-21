"""
Parsers package - Abstract Factory for language-specific parsers.

This package provides:
- AbstractLanguageParser: Strategy interface for all parsers
- ParserRegistry: Abstract Factory mapping extensions to parser instances
- Concrete parsers: Python (AST), Java/TypeScript/Kotlin (regex)
- CallGraph: Core data structure for call graph analysis
- Config constants: MAX_FILES, MAX_FILE_SIZE_KB, SUPPORTED_EXTENSIONS

Usage:
    from parsers import ParserRegistry

    parser = ParserRegistry.get_parser(".py")
    if parser:
        visitor = parser.parse_file_to_visitor(file_path, content, rel_path)

ASCII-only (cp1252-safe for Windows).
"""

from .base import AbstractLanguageParser
from .config import MAX_FILES, MAX_FILE_SIZE_KB, SUPPORTED_EXTENSIONS
from .graph_model import CallGraph
from .python_parser import PythonASTParser
from .java_parser import JavaRegexParser
from .typescript_parser import TypeScriptRegexParser
from .kotlin_parser import KotlinRegexParser


# =========================================================================
# Abstract Factory: ParserRegistry
# =========================================================================

class ParserRegistry:
    """Abstract Factory that maps file extensions to parser instances.

    Parsers are registered once at module load time via register().
    Callers use get_parser(extension) to obtain the right parser for a file.

    Design notes:
    - Each registered parser class is instantiated once (singleton per class).
    - A parser class may advertise multiple extensions (e.g. .ts and .tsx).
    - Registration is idempotent: re-registering the same class is a no-op.
    """

    # Extension string -> parser instance
    _parsers = {}   # type: dict

    @classmethod
    def register(cls, parser_class):
        """Register a parser class for all of its declared extensions.

        Args:
            parser_class: A concrete subclass of AbstractLanguageParser.
                          Must be instantiable with no arguments.

        Returns:
            None
        """
        instance = parser_class()
        for ext in instance.file_extensions:
            if ext not in cls._parsers:
                cls._parsers[ext] = instance

    @classmethod
    def get_parser(cls, file_extension):
        """Return the parser instance for a given file extension.

        Args:
            file_extension: String such as '.py', '.java', '.ts', '.tsx', '.kt'.
                            Must include the leading dot.

        Returns:
            AbstractLanguageParser instance, or None if unsupported.
        """
        return cls._parsers.get(file_extension)

    @classmethod
    def supported_extensions(cls):
        """Return the set of all registered file extensions.

        Returns:
            frozenset of extension strings (each with a leading dot).
        """
        return frozenset(cls._parsers.keys())

    @classmethod
    def can_parse(cls, file_path):
        """Return True if a parser exists for the given file path.

        Extracts the extension from file_path using a simple suffix check
        (splits on the last dot).  Works with both string paths and pathlib
        Path objects (via str conversion).

        Args:
            file_path: File path string or Path-like object.

        Returns:
            bool
        """
        path_str = str(file_path)
        dot_pos = path_str.rfind(".")
        if dot_pos == -1:
            return False
        ext = path_str[dot_pos:].lower()
        return ext in cls._parsers


# =========================================================================
# Built-in registrations (executed at import time)
# =========================================================================

ParserRegistry.register(PythonASTParser)
ParserRegistry.register(JavaRegexParser)
ParserRegistry.register(TypeScriptRegexParser)
ParserRegistry.register(KotlinRegexParser)


# =========================================================================
# Public API
# =========================================================================

__all__ = [
    "AbstractLanguageParser",
    "ParserRegistry",
    "CallGraph",
    "PythonASTParser",
    "JavaRegexParser",
    "TypeScriptRegexParser",
    "KotlinRegexParser",
    "MAX_FILES",
    "MAX_FILE_SIZE_KB",
    "SUPPORTED_EXTENSIONS",
]
