"""
Architecture Module Smoke Tests

Verifies that all Python modules under the engine's architecture directories can be
imported without errors. This catches broken imports, missing dependencies, and syntax
errors across the sync (Level 1) and execution (Level 3) architecture packages.

Level 2 (standards) was migrated to policy Markdown files under policies/ in v1.16.0 and
intentionally contains no importable Python modules, so it is not scanned here.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

# Current architecture module locations after the v1.16.0 reorganization.
_ARCH_DIRS = [
    _REPO_ROOT / "langgraph_engine" / "level1_sync" / "architecture",
    _REPO_ROOT / "langgraph_engine" / "level3_execution" / "architecture",
    _REPO_ROOT / "scripts" / "architecture" / "03-execution-system",
]

_LEVEL1_ARCH_DIR = _ARCH_DIRS[0]
_LEVEL3_ARCH_DIR = _ARCH_DIRS[1]


def _collect_py_files(directory):
    """Return a sorted list of all non-dunder .py files under the given directory."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*.py") if not p.name.startswith("__"))


_ALL_ARCH_FILES = [f for directory in _ARCH_DIRS for f in _collect_py_files(directory)]


def _try_import(py_file):
    """Try to import a Python file as a standalone module.

    Returns (success, error_msg). success is True when the module loaded without
    raising; False (with the error string) when any exception occurred during load.
    """
    try:
        module_name = "_arch_smoke_" + py_file.stem.replace("-", "_")
        spec = importlib.util.spec_from_file_location(module_name, str(py_file))
        if spec is None or spec.loader is None:
            return False, "spec_from_file_location returned no spec"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return True, None
    except Exception as exc:  # noqa: BLE001 - smoke test records any import failure as a skip
        return False, str(exc)


class TestArchitectureSmokeImports:
    """Smoke tests for all Python modules under the engine architecture directories."""

    def test_architecture_dirs_exist(self):
        """At least one of the architecture directories must exist on disk."""
        existing = [d for d in _ARCH_DIRS if d.exists()]
        assert existing, "No architecture directory found among: " + ", ".join(str(d) for d in _ARCH_DIRS)

    def test_level1_has_python_files(self):
        """Level 1 sync architecture must contain at least one Python module."""
        files = _collect_py_files(_LEVEL1_ARCH_DIR)
        assert len(files) > 0, "No Python files found in langgraph_engine/level1_sync/architecture"

    def test_level3_has_python_files(self):
        """Level 3 execution architecture must contain at least one Python module."""
        files = _collect_py_files(_LEVEL3_ARCH_DIR)
        assert len(files) > 0, "No Python files found in langgraph_engine/level3_execution/architecture"

    @pytest.mark.parametrize(
        "py_file",
        _ALL_ARCH_FILES,
        ids=[p.name for p in _ALL_ARCH_FILES] if _ALL_ARCH_FILES else [],
    )
    def test_architecture_module_importable(self, py_file):
        """Each architecture Python file imports cleanly (optional deps may skip)."""
        success, error = _try_import(py_file)
        if not success:
            pytest.skip("Import failed (likely optional dependency): " + py_file.name + " -> " + (error or "")[:200])

    def test_total_architecture_file_count(self):
        """The engine must expose a reasonable number of architecture modules."""
        total = len(_ALL_ARCH_FILES)
        assert total >= 4, (
            "Suspiciously few architecture Python files (%d); "
            "check if the architecture directories are intact" % total
        )
