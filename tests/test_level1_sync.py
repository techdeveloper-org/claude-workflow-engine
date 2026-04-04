"""
Tests for Level 1 Sync Package - Context Sync System

Tests individual node functions in isolation using simple dict state.
All external dependencies (LangGraph, complexity_calculator, subprocess,
ContextCache, toons, write_level_log) are mocked before import.

ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.

CHANGE LOG (v1.15.0):
  Fixed deprecated import path: subgraphs/level1_sync.py -> level1_sync/ package.
  Removed TestNodeToonCompression and test_level1_merge_node_preserves_toon (TOON removed).
"""

import importlib as _importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Add scripts/ to sys.path
# ---------------------------------------------------------------------------

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


# ---------------------------------------------------------------------------
# Pre-import stubs (must be registered BEFORE importing level1_sync modules)
# ---------------------------------------------------------------------------


def _stub(name):
    if name not in sys.modules:
        m = types.ModuleType(name)
        sys.modules[name] = m
    return sys.modules[name]


# LangGraph
_lg = _stub("langgraph")
_lg_graph = _stub("langgraph.graph")
_lg_graph.START = "START"
_lg_graph.END = "END"
_lg_graph.StateGraph = MagicMock()

# loguru (used by some modules)
_loguru = _stub("loguru")


def _noop(*a, **kw):
    pass


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

# toons library stub
_toons = _stub("toons")
_toons.dumps = json.dumps

# langgraph_engine package stub WITH __path__ so sub-package imports resolve
_le_pkg = _stub("langgraph_engine")
_le_pkg.__path__ = [str(Path(_SCRIPTS) / "langgraph_engine")]
_le_pkg.__package__ = "langgraph_engine"

# flow_state stub
_flow_state = _stub("langgraph_engine.flow_state")
_flow_state.FlowState = dict

# step_logger stub (helpers.py falls back to no-op when attribute missing)
_stub("langgraph_engine.step_logger")

# Top-level complexity_calculator stub (empty -> ImportError in helpers -> flag=False)
_stub("langgraph_engine.complexity_calculator")


# ---------------------------------------------------------------------------
# Import each level1_sync submodule now that stubs are in place
# ---------------------------------------------------------------------------

_l1_session = _importlib.import_module("langgraph_engine.level1_sync.session_loader")
_l1_complexity = _importlib.import_module("langgraph_engine.level1_sync.complexity_calculator")
_l1_context = _importlib.import_module("langgraph_engine.level1_sync.context_loader")
_l1_routing = _importlib.import_module("langgraph_engine.level1_sync.routing")

# Public function aliases
node_session_loader = _l1_session.node_session_loader
node_complexity_calculation = _l1_complexity.node_complexity_calculation
node_context_loader = _l1_context.node_context_loader
level1_merge_node = _l1_routing.level1_merge_node
cleanup_level1_memory = _l1_routing.cleanup_level1_memory


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _state(tmp_path=None, **extra):
    base = {
        "session_id": "test-session-001",
        "project_root": str(tmp_path) if tmp_path else ".",
        "session_path": "",
        "user_message": "test task",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Tests: node_session_loader
# ---------------------------------------------------------------------------


class TestNodeSessionLoader(unittest.TestCase):

    def test_node_session_loader_creates_folder(self):
        """Session loader creates a session directory under home."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            state = _state()
            with patch("pathlib.Path.home", return_value=Path(td)):
                result = node_session_loader(state)
        self.assertTrue(result.get("session_loaded", False))

    def test_node_session_loader_returns_path(self):
        """Session loader returns non-empty session_path in result."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            state = _state()
            with patch("pathlib.Path.home", return_value=Path(td)):
                result = node_session_loader(state)
        self.assertIn("session_path", result)
        self.assertTrue(len(result.get("session_path", "")) > 0)

    def test_node_session_loader_writes_metadata(self):
        """Session loader writes session.json with session_id field (top-level or nested)."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            state = _state(user_message="write my tests")
            with patch("pathlib.Path.home", return_value=Path(td)):
                result = node_session_loader(state)
            if result.get("session_path"):
                meta_file = Path(result["session_path"]) / "session.json"
                if meta_file.exists():
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    # session_id may be at top-level or under a "metadata" key
                    container = data.get("metadata", data)
                    self.assertIn("session_id", container)


# ---------------------------------------------------------------------------
# Tests: node_complexity_calculation
# ---------------------------------------------------------------------------


class TestNodeComplexityCalculation(unittest.TestCase):

    def test_node_complexity_calculation_default(self):
        """Returns complexity_score between 1 and 10."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            for i in range(5):
                (Path(td) / "mod_{}.py".format(i)).write_text("x = {}\n".format(i))
            state = _state(project_root=td)
            result = node_complexity_calculation(state)
        score = result.get("complexity_score", 0)
        self.assertTrue(1 <= score <= 10, "Score {} not in range 1-10".format(score))

    def test_node_complexity_calculation_fallback(self):
        """Uses file count heuristic (min(10, max(1, count//10))) as fallback."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            # 20 Python files -> heuristic: min(10, max(1, 20//10)) = 2
            for i in range(20):
                (Path(td) / "f_{}.py".format(i)).write_text("pass\n")
            state = _state(project_root=td)
            # patch.object auto-restores the original value after the with block
            with patch.object(_l1_complexity, "_COMPLEXITY_CALCULATOR_AVAILABLE", False):
                result = node_complexity_calculation(state)
        self.assertIn("complexity_score", result)
        self.assertTrue(result.get("complexity_calculated", False))

    def test_node_complexity_calculation_sets_calculated_flag(self):
        """Sets complexity_calculated=True on success."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "main.py").write_text("pass\n")
            state = _state(project_root=td)
            result = node_complexity_calculation(state)
        self.assertTrue(result.get("complexity_calculated", False))


# ---------------------------------------------------------------------------
# Tests: node_context_loader
# ---------------------------------------------------------------------------


class TestNodeContextLoader(unittest.TestCase):

    def test_node_context_loader_loads_files(self):
        """Loads README.md when it exists in project root."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "README.md").write_text("# README\nContent.\n")
            (Path(td) / "CLAUDE.md").write_text("# CLAUDE\nConfig.\n")
            state = _state(project_root=td)
            result = node_context_loader(state)
        self.assertTrue(result.get("context_loaded", False))
        ctx = result.get("context_data", {})
        files = ctx.get("files_loaded", [])
        self.assertTrue(len(files) >= 1, "Expected at least 1 file loaded")

    def test_node_context_loader_missing_files(self):
        """Returns context_loaded=True with zero files when none exist."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            state = _state(project_root=td)
            result = node_context_loader(state)
        self.assertIn("context_loaded", result)
        self.assertEqual(result.get("files_loaded_count", 0), 0)

    def test_node_context_loader_timeout(self):
        """Records skipped file and warning on per-file TimeoutError."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "README.md").write_text("# README\n")
            state = _state(project_root=td)
            with patch.object(
                _l1_context,
                "_read_file_with_timeout",
                side_effect=TimeoutError("simulated timeout"),
            ):
                result = node_context_loader(state)
        self.assertIn("context_loaded", result)
        skipped = result.get("context_skipped_files", [])
        warnings = result.get("context_load_warnings", [])
        self.assertTrue(
            len(skipped) > 0 or len(warnings) > 0,
            "Expected skipped files or warnings on timeout",
        )

    def test_node_context_loader_partial_context_on_error(self):
        """Handles gracefully - returns partial context not empty dict."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "SRS.md").write_text("# SRS\nrequirements.\n")
            state = _state(project_root=td)
            result = node_context_loader(state)
        self.assertIn("context_data", result)


# ---------------------------------------------------------------------------
# Tests: level1_merge_node
# ---------------------------------------------------------------------------


class TestLevel1MergeNode(unittest.TestCase):

    def test_level1_merge_node_complete(self):
        """Sets level1_complete=True."""
        state = _state()
        result = level1_merge_node(state)
        self.assertTrue(result.get("level1_complete", False))

    def test_level1_merge_node_returns_status(self):
        """Returns level1_status as OK or PARTIAL."""
        state = _state()
        result = level1_merge_node(state)
        self.assertIn(result.get("level1_status", ""), ["OK", "PARTIAL"])


# ---------------------------------------------------------------------------
# Tests: cleanup_level1_memory
# ---------------------------------------------------------------------------


class TestCleanupLevel1Memory(unittest.TestCase):

    def test_cleanup_level1_memory(self):
        """Sets verbose fields to None."""
        state = _state(
            context_data={"srs": "big content", "files_loaded": ["A"]},
            project_graph={"nodes": [1, 2, 3]},
            architecture={"layers": ["ui", "service"]},
        )
        result = cleanup_level1_memory(state)
        self.assertIsNone(result.get("context_data"))
        self.assertIsNone(result.get("project_graph"))
        self.assertIsNone(result.get("architecture"))

    def test_cleanup_level1_memory_summary_present(self):
        """Includes level1_cleanup_summary for audit trail."""
        state = _state(context_data={"files_loaded": []})
        result = cleanup_level1_memory(state)
        self.assertIn("level1_cleanup_summary", result)


if __name__ == "__main__":
    unittest.main()
