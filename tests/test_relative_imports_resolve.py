"""Static regression guard: every relative import in the engine must resolve
to a real file/package on disk.

Written after finding 8 broken relative imports across the engine this
session (wrong dot-count for the importing file's actual package depth --
e.g. "from ..routing.kg_router import route_task" written from a file two
packages deeper than the "from .." depth accounts for). Each one silently
disabled a real feature via a surrounding try/except ImportError/Exception
block -- KG-based routing, standards wiring, crash-recovery signal handlers,
Step 11's breaking-change Q&A, Step 10's coverage analysis and dependency
graph enhancement, and the MCP-based GitHub issue-creation path all
silently never ran, with no test ever catching it because every unit test
imported the target module directly (bypassing the broken relative import
entirely) rather than importing the *importing* module in its real package
context.

This test walks every .py file under langgraph_engine/, src/, and scripts/,
resolves every `from .N import X` statement's target against the actual
directory tree, and fails if the target doesn't exist. It intentionally
does NOT execute the imports (which would require every optional dependency
installed) -- it only checks that the dotted path resolves to a real file
or package on disk, which is exactly the class of bug found here.

Two known, pre-existing, zero-impact exceptions are allow-listed (see
_KNOWN_MISSING_MODULES): modules that genuinely do not exist anywhere in
the codebase (not a wrong-depth bug) and whose only call sites already
handle the ImportError with either a full working inline fallback or a
confirmed zero-caller dead code path.
"""

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SEARCH_ROOTS = ["langgraph_engine", "src", "scripts"]

# (file_relpath, lineno, module) -- genuinely missing modules, not depth bugs.
# sonarqube_integration: referenced only in the IntegrationRegistry factory,
#   wrapped in try/except ImportError -> logs a warning and returns None;
#   zero call sites anywhere (real SonarQube functionality lives in the
#   separate level3_execution/sonarqube/ package instead).
# remaining_steps: referenced only in steps8to12_github.py, wrapped in
#   try/except ImportError with a full working inline fallback
#   implementation of _llm_call_with_retry defined right there -- the
#   except branch IS the real, working code path, not a degraded one.
_KNOWN_MISSING_MODULES = {
    ("langgraph_engine/integrations/__init__.py", "sonarqube_integration"),
    ("langgraph_engine/level3_execution/steps8to12_github.py", "remaining_steps"),
}


def _resolve_relative_import(file_path: Path, level: int, module: str):
    """Resolve a `from .N import X` statement to the dotted path it targets.

    Returns None if the import climbs above the search root entirely.
    """
    parts = file_path.with_suffix("").parts
    pkg_parts = list(parts[:-1])
    up = level - 1
    if up > len(pkg_parts):
        return None
    target_pkg = pkg_parts[: len(pkg_parts) - up] if up > 0 else pkg_parts
    if module:
        target_pkg = target_pkg + module.split(".")
    return target_pkg


def _target_exists_on_disk(pkg_parts) -> bool:
    """True if pkg_parts resolves to a real package directory or a real .py file."""
    if not pkg_parts:
        return False
    candidate_dir = _REPO_ROOT / Path(*pkg_parts)
    candidate_file = _REPO_ROOT / Path(*pkg_parts[:-1], pkg_parts[-1] + ".py")
    return candidate_dir.is_dir() or candidate_file.is_file()


def _collect_broken_relative_imports():
    broken = []
    for root_name in _SEARCH_ROOTS:
        root = _REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for py_file in root.rglob("*.py"):
            if "__pycache__" in py_file.parts or ".venv" in py_file.parts:
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
            except SyntaxError:
                continue

            rel_file = py_file.relative_to(_REPO_ROOT)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.ImportFrom) and node.level and node.level > 0):
                    continue
                module = node.module or ""
                if (str(rel_file).replace("\\", "/"), module) in _KNOWN_MISSING_MODULES:
                    continue
                pkg_parts = _resolve_relative_import(py_file, node.level, module)
                if pkg_parts is None or not _target_exists_on_disk(pkg_parts):
                    broken.append(f"{rel_file}:{node.lineno}  from {'.' * node.level}{module} import ...")
    return broken


def test_all_relative_imports_resolve_to_real_files():
    broken = _collect_broken_relative_imports()
    if broken:
        pytest.fail(
            "Found relative imports whose target does not exist on disk "
            "(wrong dot-count for the importing file's package depth -- "
            "see this test's module docstring for the bug class this catches):\n" + "\n".join(broken)
        )
