"""Tests for Level 1 Sync Package node functions.

Covers: node_session_loader, node_complexity_calculation, node_context_loader,
        level1_merge_node, cleanup_level1_memory, and the parallel topology contract.

All tests are offline (no real filesystem I/O beyond tempdir, no LangGraph,
no external services).  Each test sets up a minimal FlowState dict
and patches only the external dependencies that the node under test actually calls.

Python 3.8+ compatible - no walrus operator, no match, no | union types.
ASCII-only source (cp1252 safe for Windows terminals).

CHANGE LOG (v1.15.0):
  Fixed deprecated import path: subgraphs/level1_sync.py -> level1_sync/ package.
  Each submodule (session_loader, complexity_calculator, context_loader, routing)
  is imported individually; patch.object targets the specific submodule that owns
  the attribute being patched.
  Removed TestNodeToonCompression and TestNodeToonCompressionSchemaPath (TOON removed).
  Removed test_toon_preserved_flag from TestCleanupLevel1Memory (TOON field gone).
  Removed toon_object from level1_merge_node state dicts (no longer referenced).
"""

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: insert scripts/ into sys.path so package imports resolve.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

for _p in [str(_REPO_ROOT), str(_SCRIPTS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _stub_module(name, **attrs):
    """Register a stub module in sys.modules if not already present."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# ---------------------------------------------------------------------------
# Stub heavy optional dependencies BEFORE importing level1_sync modules.
# Order: parent packages must be registered before children.
# ---------------------------------------------------------------------------

_stub_module("langgraph")
_stub_module(
    "langgraph.graph",
    StateGraph=MagicMock(),
    START="__start__",
    END="__end__",
)
_stub_module("toons", dumps=json.dumps)

# langgraph_engine package WITH __path__ so sub-package imports resolve
_le_pkg = _stub_module("langgraph_engine")
_le_pkg.__path__ = [str(_REPO_ROOT / "langgraph_engine")]
_le_pkg.__package__ = "langgraph_engine"

# flow_state: FlowState is just dict in tests
_flow_state_mod = _stub_module("langgraph_engine.flow_state")
_flow_state_mod.FlowState = dict  # type: ignore

# step_logger: empty stub -> helpers.py falls back to no-op write_level_log
_stub_module("langgraph_engine.step_logger")

# Top-level complexity_calculator: empty stub -> ImportError in helpers.py ->
# _COMPLEXITY_CALCULATOR_AVAILABLE=False (tests patch when needed)
_stub_module("langgraph_engine.complexity_calculator")

# utils stub (path_resolver is imported by helpers.py; real file exists in src/)
# No stub needed -- helpers.py falls back gracefully if import fails.


# ---------------------------------------------------------------------------
# Import each level1_sync submodule now that stubs are registered.
# Each submodule is stored separately so patch.object targets the right owner.
# ---------------------------------------------------------------------------

_l1_session = importlib.import_module("langgraph_engine.level1_sync.session_loader")
_l1_complexity = importlib.import_module("langgraph_engine.level1_sync.complexity_calculator")
_l1_context = importlib.import_module("langgraph_engine.level1_sync.context_loader")
_l1_routing = importlib.import_module("langgraph_engine.level1_sync.routing")

# Ensure calculate_complexity sentinel exists for tests that patch it
if not hasattr(_l1_complexity, "calculate_complexity"):
    _l1_complexity.calculate_complexity = MagicMock(return_value=5)
if not hasattr(_l1_complexity, "should_plan"):
    _l1_complexity.should_plan = MagicMock(return_value=False)

# Convenience function aliases
node_session_loader = _l1_session.node_session_loader
node_complexity_calculation = _l1_complexity.node_complexity_calculation
node_context_loader = _l1_context.node_context_loader
level1_merge_node = _l1_routing.level1_merge_node
cleanup_level1_memory = _l1_routing.cleanup_level1_memory

# Helper function aliases (live in context_loader)
_stream_file_head = _l1_context._stream_file_head
_read_file_with_timeout = _l1_context._read_file_with_timeout


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _minimal_state(**extra):
    """Return a minimal FlowState-like dict for tests."""
    state = {
        "project_root": ".",
        "user_message": "test task",
    }
    state.update(extra)
    return state


def _tmp_telemetry():
    """Return a fresh temp dir Path for telemetry (avoids real dir creation)."""
    return Path(tempfile.mkdtemp())


# ===========================================================================
# 1. TestNodeSessionLoader
# ===========================================================================


class TestNodeSessionLoader(unittest.TestCase):
    """Tests for node_session_loader."""

    def _run(self, state=None):
        if state is None:
            state = _minimal_state()
        with tempfile.TemporaryDirectory() as tmpdir:
            _l1_session._LEVEL1_SESSION_LOGS_DIR = Path(tmpdir) / "sessions"
            _l1_session._LEVEL1_TELEMETRY_DIR = Path(tmpdir) / "telemetry"
            with patch.object(_l1_session, "write_level_log", MagicMock()):
                with patch.object(_l1_session, "_load_architecture_script", return_value=None):
                    return node_session_loader(state)

    def test_returns_session_id(self):
        """node_session_loader must return a session_id string."""
        result = self._run()
        self.assertIn("session_id", result)
        self.assertIsInstance(result["session_id"], str)
        self.assertTrue(result["session_id"].startswith("session-"))

    def test_session_loaded_true_on_success(self):
        """session_loaded must be True on a successful run."""
        result = self._run()
        self.assertTrue(result.get("session_loaded"))

    def test_graceful_on_missing_project_root(self):
        """Must not raise even when project_root is missing from state."""
        state = {"user_message": "hello"}
        result = self._run(state=state)
        self.assertIsInstance(result, dict)

    def test_session_id_format(self):
        """session_id must follow 'session-YYYYMMDD-HHMMSS-<hex8>' format."""
        result = self._run()
        pattern = r"^session-\d{8}-\d{6}-[0-9a-f]{8}$"
        self.assertRegex(result["session_id"], pattern)


# ===========================================================================
# 2. TestNodeComplexityCalculation
# ===========================================================================


class TestNodeComplexityCalculation(unittest.TestCase):
    """Tests for node_complexity_calculation."""

    def _run(self, state):
        with patch.object(_l1_complexity, "write_level_log", MagicMock()):
            with patch.object(_l1_complexity, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                return node_complexity_calculation(state)

    def test_returns_complexity_score(self):
        """Must return complexity_score integer on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                (Path(tmpdir) / "file{}.py".format(i)).write_text("x = 1")
            result = self._run(_minimal_state(project_root=tmpdir))
        self.assertIn("complexity_score", result)
        self.assertIsInstance(result["complexity_score"], int)
        self.assertTrue(1 <= result["complexity_score"] <= 10)

    def test_complexity_calculated_flag(self):
        """complexity_calculated must be True when calculation succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("pass\n")
            result = self._run(_minimal_state(project_root=tmpdir))
        self.assertTrue(result.get("complexity_calculated"))

    def test_combined_score_uses_calculator_when_available(self):
        """When _COMPLEXITY_CALCULATOR_AVAILABLE, combined_complexity_score is 1-25."""
        with patch.object(_l1_complexity, "_COMPLEXITY_CALCULATOR_AVAILABLE", True):
            with patch.object(_l1_complexity, "calculate_complexity", return_value=5):
                with patch.object(_l1_complexity, "calculate_graph_complexity", return_value=(10, {}, 3.0)):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        result = self._run(_minimal_state(project_root=tmpdir))
        combined = result.get("combined_complexity_score")
        self.assertIsNotNone(combined)
        self.assertTrue(
            1 <= combined <= 25,
            "combined_complexity_score must be 1-25, got {}".format(combined),
        )

    def test_fallback_heuristic_on_missing_calculator(self):
        """When _COMPLEXITY_CALCULATOR_AVAILABLE=False, falls back to .py file count."""
        with patch.object(_l1_complexity, "_COMPLEXITY_CALCULATOR_AVAILABLE", False):
            with tempfile.TemporaryDirectory() as tmpdir:
                for i in range(5):
                    (Path(tmpdir) / "m{}.py".format(i)).write_text("pass")
                result = self._run(_minimal_state(project_root=tmpdir))
        self.assertIn("complexity_score", result)
        self.assertIsInstance(result["complexity_score"], int)


# ===========================================================================
# 3. TestNodeContextLoader
# ===========================================================================


class TestNodeContextLoader(unittest.TestCase):
    """Tests for node_context_loader."""

    def _make_project(self, tmpdir, files=None):
        root = Path(tmpdir)
        defaults = {
            "README.md": "# Test Project",
            "CLAUDE.md": "# CLAUDE config",
        }
        content_map = defaults if files is None else files
        for name, content in content_map.items():
            (root / name).write_text(content, encoding="utf-8")
        return root

    def _run(self, state):
        with patch.object(_l1_context, "write_level_log", MagicMock()):
            with patch.object(_l1_context, "_CONTEXT_CACHE_AVAILABLE", False):
                with patch.object(_l1_context, "_DEDUPLICATOR_AVAILABLE", False):
                    with patch.object(_l1_context, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                        with patch.object(_l1_context, "_load_architecture_script", return_value=None):
                            return node_context_loader(state)

    def test_loads_readme_and_claude_md(self):
        """Must load README.md and CLAUDE.md into context_data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._make_project(tmpdir)
            result = self._run(_minimal_state(project_root=str(root)))
        self.assertTrue(result.get("context_loaded"))
        ctx = result.get("context_data", {})
        self.assertIsNotNone(ctx.get("readme"))
        self.assertIsNotNone(ctx.get("claude_md"))

    def test_directory_not_loaded_as_file(self):
        """A directory matching the glob must not be returned as context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create a directory named README.md to trigger the .is_file() guard
            readme_dir = root / "README.md"
            readme_dir.mkdir()
            result = self._run(_minimal_state(project_root=str(root)))
        ctx = result.get("context_data", {})
        self.assertFalse(bool(ctx.get("readme")))

    def test_graceful_on_empty_project(self):
        """Empty project directory must return context_loaded=True with no files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run(_minimal_state(project_root=tmpdir))
        self.assertTrue(result.get("context_loaded"))
        ctx = result.get("context_data", {})
        self.assertEqual(ctx.get("files_loaded", []), [])

    def test_returns_context_cache_hit_false_on_miss(self):
        """context_cache_hit must be False when cache is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run(_minimal_state(project_root=tmpdir))
        self.assertFalse(result.get("context_cache_hit", True))


# ===========================================================================
# 4. TestLevel1MergeNodeGap (Gap 1 observable PARTIAL warning)
# ===========================================================================


class TestLevel1MergeNodeGap(unittest.TestCase):
    """Tests for level1_merge_node - focuses on Gap 1 (PARTIAL observable warning)."""

    def _run(self, state):
        with patch.object(_l1_routing, "write_level_log", MagicMock()):
            with patch.object(_l1_routing, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                return level1_merge_node(state)

    def test_ok_status_when_both_branches_succeed(self):
        """level1_status must be OK when both complexity and context loaded."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=True,
        )
        result = self._run(state)
        self.assertEqual(result.get("level1_status"), "OK")

    def test_partial_status_when_context_missing(self):
        """level1_status must be PARTIAL when context_loaded is False."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=False,
        )
        result = self._run(state)
        self.assertEqual(result.get("level1_status"), "PARTIAL")

    def test_level1_complete_true_even_on_partial(self):
        """level1_complete must be True even when status is PARTIAL (anti-deadlock guarantee)."""
        state = _minimal_state(
            complexity_calculated=False,
            context_loaded=True,
        )
        result = self._run(state)
        self.assertEqual(result.get("level1_status"), "PARTIAL")
        self.assertTrue(
            result.get("level1_complete"),
            "level1_complete must be True on PARTIAL to prevent pipeline deadlock",
        )

    def test_partial_warning_printed_to_stderr(self):
        """Gap 1 fix: PARTIAL state must emit a warning to stderr."""
        import io

        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=False,
        )
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            self._run(state)
            output = mock_err.getvalue()
        self.assertIn("PARTIAL", output)

    def test_clear_memory_signal_present(self):
        """Merge node must emit clear_memory list for downstream cleanup."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=True,
        )
        result = self._run(state)
        self.assertIn("clear_memory", result)
        self.assertIsInstance(result["clear_memory"], list)
        self.assertGreater(len(result["clear_memory"]), 0)


# ===========================================================================
# 5. TestCleanupLevel1Memory
# ===========================================================================


class TestCleanupLevel1Memory(unittest.TestCase):
    """Tests for cleanup_level1_memory."""

    def _run(self, state):
        with patch.object(_l1_routing, "_load_architecture_script", return_value=None):
            return cleanup_level1_memory(state)

    def test_verbose_fields_set_to_none(self):
        """cleanup_level1_memory must null out context_data, srs, readme, claude_md."""
        state = _minimal_state(
            context_data={"srs": "SRS content", "readme": "README", "files_loaded": []},
            srs="SRS content",
            readme="# Readme",
            claude_md="# CLAUDE",
            project_graph={"nodes": []},
            architecture={"layers": []},
        )
        result = self._run(state)
        for field in ["context_data", "srs", "readme", "claude_md"]:
            self.assertIsNone(
                result.get(field),
                "Expected {} to be None after cleanup, got: {}".format(field, result.get(field)),
            )

    def test_size_bytes_recorded_for_non_empty_fields(self):
        """Cleanup summary must include *_size_bytes for non-empty fields."""
        state = _minimal_state(
            context_data={"files_loaded": ["README"]},
            readme="hello world",
        )
        result = self._run(state)
        summary = result.get("level1_cleanup_summary", {})
        self.assertIn("readme_size_bytes", summary)

    def test_cleanup_summary_present(self):
        """Cleanup must return level1_cleanup_summary for audit trail."""
        state = _minimal_state(context_data={"files_loaded": []})
        result = self._run(state)
        self.assertIn("level1_cleanup_summary", result)


# ===========================================================================
# 6. TestParallelTopology
# ===========================================================================


class TestParallelTopology(unittest.TestCase):
    """Verify parallel topology contract: complexity and context nodes are independent."""

    def test_complexity_node_does_not_require_context_loaded(self):
        """node_complexity_calculation must succeed without context_loaded in state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _minimal_state(project_root=tmpdir)
            state.pop("context_loaded", None)
            with patch.object(_l1_complexity, "write_level_log", MagicMock()):
                with patch.object(_l1_complexity, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                    result = node_complexity_calculation(state)
        self.assertIn("complexity_score", result)

    def test_context_node_does_not_require_complexity_calculated(self):
        """node_context_loader must succeed without complexity_calculated in state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _minimal_state(project_root=tmpdir)
            state.pop("complexity_calculated", None)
            with patch.object(_l1_context, "write_level_log", MagicMock()):
                with patch.object(_l1_context, "_CONTEXT_CACHE_AVAILABLE", False):
                    with patch.object(_l1_context, "_DEDUPLICATOR_AVAILABLE", False):
                        with patch.object(_l1_context, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                            with patch.object(_l1_context, "_load_architecture_script", return_value=None):
                                result = node_context_loader(state)
        self.assertIn("context_loaded", result)

    def test_merge_node_accepts_partial_parallel_output(self):
        """level1_merge_node must return a valid dict when one parallel branch is missing."""
        state = _minimal_state(
            complexity_calculated=True,
            # context branch did NOT complete (no context_loaded key)
        )
        with patch.object(_l1_routing, "write_level_log", MagicMock()):
            with patch.object(_l1_routing, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                result = level1_merge_node(state)
        self.assertIn("level1_complete", result)
        self.assertTrue(result["level1_complete"])


# ===========================================================================
# 7. TestStreamFileHead
# ===========================================================================


class TestStreamFileHead(unittest.TestCase):
    """Tests for _stream_file_head helper."""

    def test_reads_full_small_file(self):
        """Small file content is returned fully when under max_chars."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write("hello world")
            tf_path = Path(tf.name)
        try:
            result = _stream_file_head(tf_path, max_chars=100)
            self.assertEqual(result, "hello world")
        finally:
            try:
                tf_path.unlink()
            except OSError:
                pass

    def test_truncates_at_max_chars(self):
        """Content longer than max_chars is truncated to max_chars."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write("A" * 200)
            tf_path = Path(tf.name)
        try:
            result = _stream_file_head(tf_path, max_chars=50)
            self.assertEqual(len(result), 50)
        finally:
            try:
                tf_path.unlink()
            except OSError:
                pass

    def test_empty_file_returns_empty_string(self):
        """Empty file returns empty string without error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf_path = Path(tf.name)
        try:
            result = _stream_file_head(tf_path, max_chars=100)
            self.assertEqual(result, "")
        finally:
            try:
                tf_path.unlink()
            except OSError:
                pass


# ===========================================================================
# 8. TestReadFileWithTimeout
# ===========================================================================


class TestReadFileWithTimeout(unittest.TestCase):
    """Tests for _read_file_with_timeout helper."""

    def test_reads_normal_file(self):
        """Normal file read completes within timeout and returns content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write("content here")
            tf_path = Path(tf.name)
        try:
            result = _read_file_with_timeout(tf_path, timeout_seconds=5)
            self.assertEqual(result, "content here")
        finally:
            try:
                tf_path.unlink()
            except OSError:
                pass

    def test_streaming_mode_returns_content(self):
        """use_streaming=True returns file content via _stream_file_head."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write("streamed content")
            tf_path = Path(tf.name)
        try:
            result = _read_file_with_timeout(tf_path, timeout_seconds=5, use_streaming=True, max_chars=100)
            self.assertEqual(result, "streamed content")
        finally:
            try:
                tf_path.unlink()
            except OSError:
                pass

    def test_raises_on_missing_file(self):
        """Missing file causes an exception to propagate from the reader thread."""
        tf_path = Path(tempfile.mkdtemp()) / "nonexistent_file_xyz.txt"
        with self.assertRaises(Exception):
            _read_file_with_timeout(tf_path, timeout_seconds=5)


if __name__ == "__main__":
    unittest.main()
