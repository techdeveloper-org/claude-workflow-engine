"""
Parser configuration constants.

Centralises all limits and extension sets so that CallGraphBuilder
and each language parser read from a single source of truth.

ASCII-only (cp1252-safe for Windows).
"""

# Maximum number of source files to analyse in one build pass.
MAX_FILES = 300

# Files larger than this are skipped to avoid memory spikes.
MAX_FILE_SIZE_KB = 100

# All file extensions recognised by the parser registry.
SUPPORTED_EXTENSIONS = frozenset({".py", ".java", ".ts", ".tsx", ".kt"})

# Directories that are never descended into during file discovery.
EXCLUDED_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "dist", "build", ".tox", ".eggs", ".mypy_cache",
    ".pytest_cache", ".ruff_cache",
})
