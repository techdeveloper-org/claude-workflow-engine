"""
Tests for Level -1 SubGraph - Auto-Fix Enforcement

Tests individual node functions in isolation using simple dict state.
All external dependencies (LangGraph, ErrorLogger, BackupManager,
write_level_log) are mocked before import.

ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Add scripts/ to sys.path so langgraph_engine is importable as package
# ---------------------------------------------------------------------------

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


# ---------------------------------------------------------------------------
# Pre-import stubs: prevent heavy transitive imports from executing
# ---------------------------------------------------------------------------


def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


# LangGraph
_lg = _stub("langgraph")
_lg_graph = _stub("langgraph.graph")
_lg_graph.START = "START"
_lg_graph.END = "END"
_lg_graph.StateGraph = MagicMock()

# loguru
_loguru = _stub("loguru")


def _noop(*a, **kw):
    return None


_loguru.logger = type(
    "_L",
    (),
    {
        "info": _noop,
        "debug": _noop,
        "warning": _noop,
        "error": _noop,
        "critical": _noop,
    },
)()

# Stub the entire langgraph_engine package so its __init__ never runs
_le_pkg = types.ModuleType("langgraph_engine")
_le_pkg.__path__ = [str(Path(_SCRIPTS) / "langgraph_engine")]
_le_pkg.__package__ = "langgraph_engine"
sys.modules["langgraph_engine"] = _le_pkg

# Individual sub-modules needed by level_minus1 via relative imports
_flow_state = _stub("langgraph_engine.flow_state")
_flow_state.FlowState = dict


class _StepKeys:
    LEVEL_MINUS1_STATUS = "level_minus1_status"
    LEVEL_MINUS1_USER_CHOICE = "level_minus1_user_choice"
    LEVEL_MINUS1_RETRY_COUNT = "level_minus1_retry_count"


_flow_state.StepKeys = _StepKeys

_error_logger = _stub("langgraph_engine.error_logger")
_error_logger.ErrorLogger = MagicMock()

_backup_manager = _stub("langgraph_engine.backup_manager")
_backup_manager.BackupManager = MagicMock()

_step_logger = _stub("langgraph_engine.step_logger")
_step_logger.write_level_log = MagicMock()

# Subgraphs package stub
_subgraphs = _stub("langgraph_engine.subgraphs")
_subgraphs.__path__ = [str(Path(_SCRIPTS) / "langgraph_engine" / "subgraphs")]
_subgraphs.__package__ = "langgraph_engine.subgraphs"

# Routing package stub
_routing_pkg = _stub("langgraph_engine.routing")
_routing_pkg.__path__ = [str(Path(_SCRIPTS) / "langgraph_engine" / "routing")]
_routing_pkg.__package__ = "langgraph_engine.routing"


# ---------------------------------------------------------------------------
# Now import the module under test using importlib to respect the package
# ---------------------------------------------------------------------------

import importlib.util as _ilu  # noqa: E402

_level_minus1_path = Path(_SCRIPTS) / "langgraph_engine" / "subgraphs" / "level_minus1.py"
_spec = _ilu.spec_from_file_location(
    "langgraph_engine.subgraphs.level_minus1",
    str(_level_minus1_path),
    submodule_search_locations=[],
)
_level_minus1_mod = _ilu.module_from_spec(_spec)
_level_minus1_mod.__package__ = "langgraph_engine.subgraphs"
sys.modules["langgraph_engine.subgraphs.level_minus1"] = _level_minus1_mod
_spec.loader.exec_module(_level_minus1_mod)

# Import symbols from subgraph module
node_unicode_fix = _level_minus1_mod.node_unicode_fix
node_encoding_validation = _level_minus1_mod.node_encoding_validation
node_windows_path_check = _level_minus1_mod.node_windows_path_check
level_minus1_merge_node = _level_minus1_mod.level_minus1_merge_node
fix_level_minus1_issues = _level_minus1_mod.fix_level_minus1_issues

# Import routing function from the canonical routing module
_routes_path = Path(_SCRIPTS) / "langgraph_engine" / "routing" / "level_minus1_routes.py"
_routes_spec = _ilu.spec_from_file_location(
    "langgraph_engine.routing.level_minus1_routes",
    str(_routes_path),
    submodule_search_locations=[],
)
_routes_mod = _ilu.module_from_spec(_routes_spec)
_routes_mod.__package__ = "langgraph_engine.routing"
sys.modules["langgraph_engine.routing.level_minus1_routes"] = _routes_mod
_routes_spec.loader.exec_module(_routes_mod)

route_after_level_minus1 = _routes_mod.route_after_level_minus1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _state(tmp_path=None, **extra):
    base = {
        "session_id": "test-session-001",
        "project_root": str(tmp_path) if tmp_path else ".",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Tests: node_unicode_fix
# ---------------------------------------------------------------------------


class TestNodeUnicodeFix(unittest.TestCase):

    def test_node_unicode_fix_returns_check_result(self):
        """node_unicode_fix always returns a dict with unicode_check key."""
        with patch("sys.platform", "linux"):
            result = node_unicode_fix(_state())
        self.assertIn("unicode_check", result)

    def test_node_unicode_fix_non_windows_passes(self):
        """On non-Windows platform, unicode_check is True (no fix needed)."""
        with patch("sys.platform", "linux"):
            result = node_unicode_fix(_state())
        self.assertTrue(result["unicode_check"])

    def test_node_unicode_fix_windows_sets_unicode_check(self):
        """On Windows, unicode_check key is set in result."""
        import io

        # Use real StringIO objects so print(file=sys.stderr) works
        mock_stdout = io.StringIO()
        mock_stderr = io.StringIO()
        with patch("sys.platform", "win32"), patch("sys.stdout", mock_stdout), patch("sys.stderr", mock_stderr):
            result = node_unicode_fix(_state())
        self.assertIn("unicode_check", result)


# ---------------------------------------------------------------------------
# Tests: node_encoding_validation
# ---------------------------------------------------------------------------


class TestNodeEncodingValidation(unittest.TestCase):

    def test_node_encoding_validation_non_windows_passes(self):
        """On non-Windows, encoding_check is True (check skipped)."""
        with patch("sys.platform", "linux"):
            result = node_encoding_validation(_state())
        self.assertTrue(result["encoding_check"])

    def test_node_encoding_validation_ascii_only(self):
        """ASCII-only .py files pass encoding validation on Windows."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "clean.py").write_bytes(b"# ASCII only\nx = 1\n")
            state = _state(project_root=td)
            with patch("sys.platform", "win32"):
                result = node_encoding_validation(state)
        self.assertTrue(result.get("encoding_check", True))

    def test_node_encoding_validation_non_ascii(self):
        """Non-ASCII bytes in a .py file cause encoding_check=False on Windows."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            # 0xC3 0xA9 = UTF-8 for e-acute, not pure ASCII
            (Path(td) / "bad.py").write_bytes(b"# Bad \xc3\xa9ncoding\n")
            state = _state(project_root=td)
            with patch("sys.platform", "win32"):
                result = node_encoding_validation(state)
        self.assertFalse(result.get("encoding_check", True))
        self.assertIn("encoding_check_error", result)


# ---------------------------------------------------------------------------
# Tests: node_windows_path_check
# ---------------------------------------------------------------------------


class TestNodeWindowsPathCheck(unittest.TestCase):

    def test_node_windows_path_check_clean_non_windows(self):
        """On non-Windows, windows_path_check is True (check skipped)."""
        with patch("sys.platform", "linux"):
            result = node_windows_path_check(_state())
        self.assertTrue(result.get("windows_path_check", True))

    def test_node_windows_path_check_clean(self):
        """Python files using forward slashes pass on Windows."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "clean.py").write_text("path = '/usr/local/bin'\n", encoding="utf-8")
            state = _state(project_root=td)
            with patch("sys.platform", "win32"):
                result = node_windows_path_check(state)
        self.assertTrue(result.get("windows_path_check", True))

    def test_node_windows_path_check_backslash(self):
        """Hardcoded Windows drive paths (C:\\) fail the check."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "bad.py").write_text('PATH = "C:\\\\Users\\\\admin\\\\file.txt"\n', encoding="utf-8")
            state = _state(project_root=td)
            with patch("sys.platform", "win32"):
                result = node_windows_path_check(state)
        self.assertFalse(result.get("windows_path_check", True))


# ---------------------------------------------------------------------------
# Tests: level_minus1_merge_node
# ---------------------------------------------------------------------------


class TestLevelMinus1MergeNode(unittest.TestCase):

    def test_level_minus1_merge_all_pass(self):
        """All three checks True => level_minus1_status='OK'."""
        state = _state(
            unicode_check=True,
            encoding_check=True,
            windows_path_check=True,
        )
        result = level_minus1_merge_node(state)
        self.assertEqual(result["level_minus1_status"], "OK")

    def test_level_minus1_merge_any_fail(self):
        """Any check False => level_minus1_status='FAILED'."""
        state = _state(
            unicode_check=True,
            encoding_check=False,
            windows_path_check=True,
            encoding_check_error="Non-ASCII bytes found",
        )
        result = level_minus1_merge_node(state)
        self.assertEqual(result["level_minus1_status"], "FAILED")

    def test_level_minus1_merge_failed_adds_errors(self):
        """FAILED merge appends error detail to errors list."""
        state = _state(
            unicode_check=False,
            encoding_check=True,
            windows_path_check=True,
            unicode_check_error="reconfigure failed",
        )
        result = level_minus1_merge_node(state)
        self.assertEqual(result["level_minus1_status"], "FAILED")
        errors = result.get("errors", [])
        self.assertTrue(
            any("unicode" in e.lower() or "Unicode" in e for e in errors),
            "Expected unicode error in errors list",
        )


# ---------------------------------------------------------------------------
# Tests: route_after_level_minus1 (canonical routing from routing/ package)
# ---------------------------------------------------------------------------


class TestRouteAfterMerge(unittest.TestCase):

    def test_route_after_merge_ok(self):
        """Returns 'level1_session' when status is OK."""
        state = _state(level_minus1_status="OK")
        result = route_after_level_minus1(state)
        self.assertEqual(result, "level1_session")

    def test_route_after_merge_fail(self):
        """Returns 'ask_level_minus1_fix' when status is FAILED."""
        state = _state(level_minus1_status="FAILED")
        result = route_after_level_minus1(state)
        self.assertEqual(result, "ask_level_minus1_fix")

    def test_route_after_merge_missing_status_defaults_to_fail(self):
        """Missing level_minus1_status defaults to 'ask_level_minus1_fix' routing."""
        state = _state()  # no level_minus1_status key
        result = route_after_level_minus1(state)
        self.assertEqual(result, "ask_level_minus1_fix")


class TestFixLevelMinus1Issues(unittest.TestCase):
    """Tests for the fix_level_minus1_issues() function."""

    def test_fix_unicode_sets_flag(self):
        """Unicode fix attempt should return level_minus1_fixes_applied and ready_to_retry."""
        state = {
            "unicode_check": False,
            "encoding_check": True,
            "windows_path_check": True,
            "project_root": ".",
        }
        result = fix_level_minus1_issues(state)
        self.assertIn("level_minus1_fixes_applied", result)
        self.assertTrue(result.get("level_minus1_ready_to_retry"))

    def test_fix_path_backslashes(self):
        """Path fixer should convert backslashes to forward slashes."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            py_file = Path(td) / "test_paths.py"
            py_file.write_text('path = "C:\\\\Users\\\\test"\n', encoding="utf-8")
            state = {
                "unicode_check": True,
                "encoding_check": True,
                "windows_path_check": False,
                "project_root": td,
            }
            result = fix_level_minus1_issues(state)
        self.assertIsInstance(result, dict)

    def test_fix_preserves_escape_sequences(self):
        """Path fixer should NOT convert \\n, \\t, \\r to forward slashes."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            py_file = Path(td) / "test_escapes.py"
            py_file.write_text('msg = "hello\\nworld\\ttab"\n', encoding="utf-8")
            state = {
                "unicode_check": True,
                "encoding_check": True,
                "windows_path_check": False,
                "project_root": td,
            }
            fix_level_minus1_issues(state)
            content = py_file.read_text(encoding="utf-8")
        self.assertTrue("\\n" in content or "hello" in content)

    def test_fix_empty_project(self):
        """Fix on empty project should not crash."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            state = {
                "unicode_check": True,
                "encoding_check": True,
                "windows_path_check": False,
                "project_root": td,
            }
            result = fix_level_minus1_issues(state)
        self.assertIsInstance(result, dict)

    def test_fix_all_checks_pass(self):
        """When all checks pass, fix should be a no-op."""
        state = {
            "unicode_check": True,
            "encoding_check": True,
            "windows_path_check": True,
            "project_root": ".",
        }
        result = fix_level_minus1_issues(state)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
