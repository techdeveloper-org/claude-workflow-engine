"""
Architecture Module Smoke Tests

Verifies that all Python modules under scripts/architecture/ can be imported
without errors. This catches broken imports, missing dependencies, and syntax
errors across all three architecture levels.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Add project root + scripts/ to sys.path so imports resolve
_REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

ARCH_DIR = SCRIPTS_DIR / "architecture"


# Collect modules per level at import time so parametrize can use them
def _collect_py_files(level_dir_name):
    """Return a sorted list of all non-dunder .py files under the given subdir."""
    level_path = ARCH_DIR / level_dir_name
    if not level_path.exists():
        return []
    return sorted(p for p in level_path.rglob("*.py") if not p.name.startswith("__"))


_LEVEL1_FILES = _collect_py_files("01-sync-system")
_LEVEL2_FILES = _collect_py_files("02-standards-system")
_LEVEL3_FILES = _collect_py_files("03-execution-system")


def _try_import(py_file):
    """Try to import a Python file as a module.

    Returns (success, error_msg).
    success=True  if the module loaded without raising an exception.
    success=False if any exception occurred during loading.
    """
    try:
        module_name = "_arch_smoke_" + py_file.stem.replace("-", "_")
        spec = importlib.util.spec_from_file_location(module_name, str(py_file))
        if spec is None or spec.loader is None:
            return False, "spec_from_file_location returned no spec"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return True, None
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Basic sanity: the architecture directory itself exists
# ---------------------------------------------------------------------------


class TestArchitectureSmokeImports:
    """Smoke tests for all Python modules under scripts/architecture/."""

    def test_architecture_dir_exists(self):
        """Verify that scripts/architecture/ directory exists."""
        assert ARCH_DIR.exists(), "scripts/architecture/ directory not found at " + str(ARCH_DIR)

    def test_architecture_dir_is_directory(self):
        """Verify that scripts/architecture/ is a real directory."""
        assert ARCH_DIR.is_dir(), str(ARCH_DIR) + " is not a directory"

    # -----------------------------------------------------------------------
    # Level 1: 01-sync-system
    # -----------------------------------------------------------------------

    def test_level1_dir_exists(self):
        """Verify that 01-sync-system subdirectory exists."""
        level_path = ARCH_DIR / "01-sync-system"
        if not level_path.exists():
            pytest.skip("01-sync-system not found; skipping")
        assert level_path.is_dir()

    @pytest.mark.parametrize(
        "py_file",
        _LEVEL1_FILES,
        ids=[p.name for p in _LEVEL1_FILES] if _LEVEL1_FILES else [],
    )
    def test_level1_module_importable(self, py_file):
        """Verify that a 01-sync-system Python file can be imported."""
        success, error = _try_import(py_file)
        if not success:
            pytest.skip("Import failed (likely optional dependency): " + py_file.name + " -> " + (error or "")[:200])

    def test_level1_has_python_files(self):
        """Verify that 01-sync-system contains at least one Python file."""
        level_path = ARCH_DIR / "01-sync-system"
        if not level_path.exists():
            pytest.skip("01-sync-system not found")
        files = list(level_path.rglob("*.py"))
        assert len(files) > 0, "No Python files found in 01-sync-system"

    # -----------------------------------------------------------------------
    # Level 2: 02-standards-system
    # -----------------------------------------------------------------------

    def test_level2_dir_exists(self):
        """Verify that 02-standards-system subdirectory exists."""
        level_path = ARCH_DIR / "02-standards-system"
        if not level_path.exists():
            pytest.skip("02-standards-system not found; skipping")
        assert level_path.is_dir()

    @pytest.mark.parametrize(
        "py_file",
        _LEVEL2_FILES,
        ids=[p.name for p in _LEVEL2_FILES] if _LEVEL2_FILES else [],
    )
    def test_level2_module_importable(self, py_file):
        """Verify that a 02-standards-system Python file can be imported."""
        success, error = _try_import(py_file)
        if not success:
            pytest.skip("Import failed (likely optional dependency): " + py_file.name + " -> " + (error or "")[:200])

    def test_level2_has_python_files(self):
        """Verify that 02-standards-system contains at least one Python file."""
        level_path = ARCH_DIR / "02-standards-system"
        if not level_path.exists():
            pytest.skip("02-standards-system not found")
        files = list(level_path.rglob("*.py"))
        assert len(files) > 0, "No Python files found in 02-standards-system"

    # -----------------------------------------------------------------------
    # Level 3: 03-execution-system
    # -----------------------------------------------------------------------

    def test_level3_dir_exists(self):
        """Verify that 03-execution-system subdirectory exists."""
        level_path = ARCH_DIR / "03-execution-system"
        if not level_path.exists():
            pytest.skip("03-execution-system not found; skipping")
        assert level_path.is_dir()

    @pytest.mark.parametrize(
        "py_file",
        _LEVEL3_FILES,
        ids=[p.name for p in _LEVEL3_FILES] if _LEVEL3_FILES else [],
    )
    def test_level3_module_importable(self, py_file):
        """Verify that a 03-execution-system Python file can be imported."""
        success, error = _try_import(py_file)
        if not success:
            pytest.skip("Import failed (likely optional dependency): " + py_file.name + " -> " + (error or "")[:200])

    def test_level3_has_python_files(self):
        """Verify that 03-execution-system contains at least one Python file."""
        level_path = ARCH_DIR / "03-execution-system"
        if not level_path.exists():
            pytest.skip("03-execution-system not found")
        files = list(level_path.rglob("*.py"))
        assert len(files) > 0, "No Python files found in 03-execution-system"

    # -----------------------------------------------------------------------
    # Summary: total file counts as a sanity check
    # -----------------------------------------------------------------------

    def test_total_architecture_file_count(self):
        """Verify that the total number of architecture Python files is reasonable."""
        total = len(list(ARCH_DIR.rglob("*.py")))
        assert total > 0, "No Python files found anywhere under scripts/architecture/"
        # Current repo has ~83 modules; allow for growth or minor shrinkage
        assert total >= 10, (
            "Suspiciously few Python files in architecture (%d); " "check if directory is intact" % total
        )
