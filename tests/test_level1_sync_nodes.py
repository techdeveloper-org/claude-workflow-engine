"""Tests for scripts/langgraph_engine/subgraphs/level1_sync.py

Covers: node_session_loader, node_complexity_calculation, node_context_loader,
        node_toon_compression, level1_merge_node, cleanup_level1_memory,
        and the parallel topology contract.

All tests are offline (no real filesystem I/O beyond tempdir, no LangGraph,
no Qdrant, no external services).  Each test sets up a minimal FlowState dict
and patches only the external dependencies that the node under test actually
calls.

Python 3.8+ compatible - no walrus operator, no match, no | union types.
ASCII-only source (cp1252 safe for Windows terminals).
"""

import importlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: insert scripts/ into sys.path so that
# "import langgraph_engine.subgraphs.level1_sync" resolves correctly.
# Relative imports inside level1_sync (from ..flow_state etc.) require
# the module to be imported as part of the langgraph_engine package.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _stub_module(name, **attrs):
    """Register a stub module in sys.modules if not already present.
    Returns the module (new or existing).
    """
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# ---------------------------------------------------------------------------
# Stub heavy optional dependencies BEFORE importing the package.
# Order matters: parent packages must be registered before children.
# ---------------------------------------------------------------------------

_stub_module("langgraph")
_stub_module(
    "langgraph.graph",
    StateGraph=MagicMock(),
    START="__start__",
    END="__end__",
)
_stub_module("toons", dumps=json.dumps)

# langgraph_engine package stubs (parent first)
_stub_module("langgraph_engine")

# flow_state: FlowState is just dict in tests
_flow_state_mod = _stub_module("langgraph_engine.flow_state")
_flow_state_mod.FlowState = dict  # type: ignore

# step_logger: write_level_log is a no-op
_step_logger_mod = _stub_module("langgraph_engine.step_logger")
_step_logger_mod.write_level_log = MagicMock()

# subgraphs package stub (needed for the relative import chain)
_stub_module("langgraph_engine.subgraphs")

# Optional feature modules - stub them WITHOUT the expected functions so that
# the graceful try/except ImportError blocks in level1_sync fire and set
# _COMPLEXITY_CALCULATOR_AVAILABLE=False etc.  Intentionally empty stubs.
_stub_module("langgraph_engine.complexity_calculator")
_stub_module("langgraph_engine.context_cache")
_stub_module("langgraph_engine.context_deduplicator")
_stub_module("langgraph_engine.toon_schema")

# utils stub (used by path_resolver import at module top)
_stub_module("utils")
_stub_module(
    "utils.path_resolver",
    get_session_logs_dir=MagicMock(return_value=Path(tempfile.mkdtemp()) / "sessions"),
    get_telemetry_dir=MagicMock(return_value=Path(tempfile.mkdtemp()) / "telemetry"),
)

# ---------------------------------------------------------------------------
# Import the module under test.
# We must use importlib with the correct package so relative imports work.
# ---------------------------------------------------------------------------

_L1_SPEC = importlib.util.spec_from_file_location(
    "langgraph_engine.subgraphs.level1_sync",
    str(_SCRIPTS_DIR / "langgraph_engine" / "subgraphs" / "level1_sync.py"),
    submodule_search_locations=[],
)
_L1_MOD = importlib.util.module_from_spec(_L1_SPEC)
# Set __package__ so relative imports (from ..flow_state) resolve correctly
_L1_MOD.__package__ = "langgraph_engine.subgraphs"
sys.modules["langgraph_engine.subgraphs.level1_sync"] = _L1_MOD
_L1_SPEC.loader.exec_module(_L1_MOD)

_L1 = _L1_MOD

# ---------------------------------------------------------------------------
# Post-import sentinel injection:
# When _COMPLEXITY_CALCULATOR_AVAILABLE=False (our default), the module's
# try/except only defines calculate_graph_complexity as a fallback stub.
# calculate_complexity and should_plan have NO fallback in the module.
# We add them as sentinels here so patch.object can find and replace them
# in tests that simulate the calculator-available path.
# ---------------------------------------------------------------------------
if not hasattr(_L1, "calculate_complexity"):
    _L1.calculate_complexity = MagicMock(return_value=5)
if not hasattr(_L1, "should_plan"):
    _L1.should_plan = MagicMock(return_value=False)
# validate_toon has no fallback when _TOON_SCHEMA_AVAILABLE=False; add sentinel
# so patch.object can find it in tests that exercise the schema-available path.
if not hasattr(_L1, "validate_toon"):
    _L1.validate_toon = MagicMock(return_value=(True, []))

# Convenience aliases
node_session_loader = _L1.node_session_loader
node_complexity_calculation = _L1.node_complexity_calculation
node_context_loader = _L1.node_context_loader
node_toon_compression = _L1.node_toon_compression
level1_merge_node = _L1.level1_merge_node
cleanup_level1_memory = _L1.cleanup_level1_memory
_verify_toon_integrity = _L1._verify_toon_integrity
_decompress_toon = _L1._decompress_toon
_stream_file_head = _L1._stream_file_head
_read_file_with_timeout = _L1._read_file_with_timeout


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
            _L1._LEVEL1_SESSION_LOGS_DIR = Path(tmpdir) / "sessions"
            _L1._LEVEL1_TELEMETRY_DIR = Path(tmpdir) / "telemetry"
            with patch.object(_L1, "write_level_log", MagicMock()):
                with patch.object(_L1, "_load_architecture_script", return_value=None):
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
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
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
            result = self._run(_minimal_state(project_root=tmpdir))
        self.assertTrue(result.get("complexity_calculated"))

    def test_combined_score_uses_calculator_when_available(self):
        """When _COMPLEXITY_CALCULATOR_AVAILABLE, combined_complexity_score is 1-25."""
        # Both functions must be patched at the module level because the node
        # calls them via direct name reference (calculate_complexity(...) etc.)
        with patch.object(_L1, "_COMPLEXITY_CALCULATOR_AVAILABLE", True):
            with patch.object(_L1, "calculate_complexity", return_value=5):
                with patch.object(_L1, "calculate_graph_complexity", return_value=(10, {}, 3.0)):
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
        with patch.object(_L1, "_COMPLEXITY_CALCULATOR_AVAILABLE", False):
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
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_CONTEXT_CACHE_AVAILABLE", False):
                with patch.object(_L1, "_DEDUPLICATOR_AVAILABLE", False):
                    with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                        with patch.object(_L1, "_load_architecture_script", return_value=None):
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
        """A directory matching the glob must not be returned as context (Gap 4 guard)."""
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
# 4. TestNodeToonCompression
# ===========================================================================


class TestNodeToonCompression(unittest.TestCase):
    """Tests for node_toon_compression and its integrity helpers."""

    def _make_context_data(self, srs=None, readme="# R", claude_md="# C"):
        files = []
        if srs:
            files.append("SRS")
        if readme:
            files.append("README")
        if claude_md:
            files.append("CLAUDE.md")
        return {
            "srs": srs,
            "readme": readme,
            "claude_md": claude_md,
            "files_loaded": files,
        }

    def _run(self, state):
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_TOON_SCHEMA_AVAILABLE", False):
                with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                    return node_toon_compression(state)

    def test_toon_saved_true_on_success(self):
        """toon_saved must be True when compression succeeds."""
        ctx = self._make_context_data()
        state = _minimal_state(
            session_id="session-test-abc",
            complexity_score=5,
            context_data=ctx,
        )
        result = self._run(state)
        self.assertTrue(result.get("toon_saved"))

    def test_toon_object_has_required_fields(self):
        """Compressed toon_object must have session_id, complexity_score, files_loaded_count, context."""
        ctx = self._make_context_data()
        state = _minimal_state(
            session_id="session-test-abc",
            complexity_score=3,
            context_data=ctx,
        )
        result = self._run(state)
        toon = result.get("toon_object", {})
        for field in ["session_id", "complexity_score", "files_loaded_count", "context"]:
            self.assertIn(field, toon, "toon_object missing field: {}".format(field))

    def test_context_data_cleared_after_compression(self):
        """context_data must be set to None in the returned dict."""
        ctx = self._make_context_data()
        state = _minimal_state(
            session_id="session-test-abc",
            complexity_score=5,
            context_data=ctx,
        )
        result = self._run(state)
        self.assertIsNone(result.get("context_data"))

    def test_integrity_check_ok(self):
        """_verify_toon_integrity returns True for a well-formed TOON."""
        original = self._make_context_data()
        toon = {
            "session_id": "session-test-abc",
            "complexity_score": 5,
            "files_loaded_count": len(original["files_loaded"]),
            "context": {
                "srs": bool(original["srs"]),
                "readme": bool(original["readme"]),
                "claude_md": bool(original["claude_md"]),
            },
        }
        self.assertTrue(_verify_toon_integrity(toon, original))

    def test_integrity_check_fails_on_missing_session_id(self):
        """_verify_toon_integrity must return False when session_id is absent."""
        original = self._make_context_data()
        toon = {
            "complexity_score": 5,
            "files_loaded_count": len(original["files_loaded"]),
            "context": {},
        }
        self.assertFalse(_verify_toon_integrity(toon, original))

    def test_fallback_on_integrity_failure(self):
        """When integrity check fails, raw_fallback key must appear in toon context.

        Integrity fails when session_id is empty string: _verify_toon_integrity
        checks `if not toon.get('session_id', '').strip(): return False`.
        Passing session_id='' in state causes the node to produce an empty-string
        session_id in the TOON, triggering the raw-fallback branch.
        """
        ctx = self._make_context_data(readme="# R", claude_md="# C")
        # session_id="" forces empty-string in TOON -> integrity check fails
        state = _minimal_state(
            session_id="",
            complexity_score=5,
            context_data=ctx,
        )
        result = self._run(state)
        toon = result.get("toon_object", {})
        ctx_out = toon.get("context", {})
        self.assertIn("raw_fallback", ctx_out)


# ===========================================================================
# 5. TestLevel1MergeNodeGap (Gap 1 observable PARTIAL warning)
# ===========================================================================


class TestLevel1MergeNodeGap(unittest.TestCase):
    """Tests for level1_merge_node - focuses on Gap 1 (PARTIAL observable warning)."""

    def _run(self, state):
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                return level1_merge_node(state)

    def test_ok_status_when_both_branches_succeed(self):
        """level1_status must be OK when both complexity and context loaded."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=True,
            toon_object={
                "session_id": "s",
                "complexity_score": 5,
                "files_loaded_count": 0,
                "context": {},
            },
        )
        result = self._run(state)
        self.assertEqual(result.get("level1_status"), "OK")

    def test_partial_status_when_context_missing(self):
        """level1_status must be PARTIAL when context_loaded is False."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=False,
            toon_object={},
        )
        result = self._run(state)
        self.assertEqual(result.get("level1_status"), "PARTIAL")

    def test_level1_complete_true_even_on_partial(self):
        """level1_complete must be True even when status is PARTIAL (anti-deadlock guarantee)."""
        state = _minimal_state(
            complexity_calculated=False,
            context_loaded=True,
            toon_object={},
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
            toon_object={},
        )
        # Patch sys.stderr globally; level1_merge_node uses print(..., file=sys.stderr)
        # which looks up sys.stderr at call time.
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            self._run(state)
            output = mock_err.getvalue()
        self.assertIn("PARTIAL", output)

    def test_clear_memory_signal_present(self):
        """Merge node must emit clear_memory list for downstream cleanup."""
        state = _minimal_state(
            complexity_calculated=True,
            context_loaded=True,
            toon_object={},
        )
        result = self._run(state)
        self.assertIn("clear_memory", result)
        self.assertIsInstance(result["clear_memory"], list)
        self.assertGreater(len(result["clear_memory"]), 0)


# ===========================================================================
# 6. TestCleanupLevel1Memory
# ===========================================================================


class TestCleanupLevel1Memory(unittest.TestCase):
    """Tests for cleanup_level1_memory."""

    def _run(self, state):
        with patch.object(_L1, "_load_architecture_script", return_value=None):
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
            level1_context_toon={
                "session_id": "s1",
                "complexity_score": 5,
                "files_loaded_count": 0,
                "context": {},
            },
        )
        result = self._run(state)
        for field in ["context_data", "srs", "readme", "claude_md"]:
            self.assertIsNone(
                result.get(field),
                "Expected {} to be None after cleanup, got: {}".format(field, result.get(field)),
            )

    def test_toon_preserved_flag(self):
        """cleanup_level1_memory must report toon_preserved=True in summary."""
        state = _minimal_state(
            level1_context_toon={
                "session_id": "s1",
                "complexity_score": 5,
                "files_loaded_count": 0,
                "context": {},
            },
        )
        result = self._run(state)
        summary = result.get("level1_cleanup_summary", {})
        self.assertTrue(summary.get("toon_preserved"))

    def test_size_bytes_recorded_for_non_empty_fields(self):
        """Cleanup summary must include *_size_bytes for non-empty fields."""
        state = _minimal_state(
            context_data={"files_loaded": ["README"]},
            readme="hello world",
            level1_context_toon={},
        )
        result = self._run(state)
        summary = result.get("level1_cleanup_summary", {})
        self.assertIn("readme_size_bytes", summary)


# ===========================================================================
# 7. TestParallelTopology
# ===========================================================================


class TestParallelTopology(unittest.TestCase):
    """Verify parallel topology contract: complexity and context nodes are independent."""

    def test_complexity_node_does_not_require_context_loaded(self):
        """node_complexity_calculation must succeed without context_loaded in state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _minimal_state(project_root=tmpdir)
            state.pop("context_loaded", None)
            with patch.object(_L1, "write_level_log", MagicMock()):
                with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                    result = node_complexity_calculation(state)
        self.assertIn("complexity_score", result)

    def test_context_node_does_not_require_complexity_calculated(self):
        """node_context_loader must succeed without complexity_calculated in state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _minimal_state(project_root=tmpdir)
            state.pop("complexity_calculated", None)
            with patch.object(_L1, "write_level_log", MagicMock()):
                with patch.object(_L1, "_CONTEXT_CACHE_AVAILABLE", False):
                    with patch.object(_L1, "_DEDUPLICATOR_AVAILABLE", False):
                        with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                            with patch.object(_L1, "_load_architecture_script", return_value=None):
                                result = node_context_loader(state)
        self.assertIn("context_loaded", result)

    def test_merge_node_accepts_partial_parallel_output(self):
        """level1_merge_node must return a valid dict when one parallel branch is missing."""
        state = _minimal_state(
            complexity_calculated=True,
            # context branch did NOT complete (no context_loaded key)
            toon_object={},
        )
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                result = level1_merge_node(state)
        self.assertIn("level1_complete", result)
        self.assertTrue(result["level1_complete"])


# ===========================================================================
# 8. TestStreamFileHead
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
# 9. TestReadFileWithTimeout
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


# ===========================================================================
# 10. TestNodeToonCompressionSchemaPath
# ===========================================================================


class TestNodeToonCompressionSchemaPath(unittest.TestCase):
    """Tests node_toon_compression with _TOON_SCHEMA_AVAILABLE=True."""

    def _run(self, state, schema_return):
        with patch.object(_L1, "write_level_log", MagicMock()):
            with patch.object(_L1, "_TOON_SCHEMA_AVAILABLE", True):
                with patch.object(_L1, "validate_toon", return_value=schema_return):
                    with patch.object(_L1, "_LEVEL1_TELEMETRY_DIR", _tmp_telemetry()):
                        return node_toon_compression(state)

    def _make_state(self):
        return _minimal_state(
            session_id="session-schema-test",
            complexity_score=4,
            context_data={
                "srs": None,
                "readme": "# R",
                "claude_md": "# C",
                "files_loaded": ["README", "CLAUDE.md"],
            },
        )

    def test_schema_valid_true_on_pass(self):
        """toon_schema_valid is True when validate_toon returns (True, [])."""
        result = self._run(self._make_state(), schema_return=(True, []))
        self.assertTrue(result.get("toon_schema_valid"))
        self.assertEqual(result.get("toon_schema_errors"), [])

    def test_schema_errors_propagated_on_fail(self):
        """When validate_toon returns (False, errors), toon_schema_valid is False
        and raw_fallback appears in the toon context."""
        errors = ["missing required field: project_name"]
        result = self._run(self._make_state(), schema_return=(False, errors))
        self.assertFalse(result.get("toon_schema_valid"))
        toon = result.get("toon_object", {})
        self.assertIn("raw_fallback", toon.get("context", {}))

    def test_combined_complexity_score_in_toon(self):
        """combined_complexity_score from state is stored in toon_object."""
        state = self._make_state()
        state["combined_complexity_score"] = 18
        result = self._run(state, schema_return=(True, []))
        toon = result.get("toon_object", {})
        self.assertEqual(toon.get("combined_complexity_score"), 18)


if __name__ == "__main__":
    unittest.main()
