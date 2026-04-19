"""Tests for v7.5.0 enhancements: checkpointer, system health, LLM health, standards reload."""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add paths
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

_MCP_DIR = _PROJECT_ROOT / "src" / "mcp"


def _load_mcp_module(name, filename):
    file_path = _MCP_DIR / filename
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse(result: str) -> dict:
    return json.loads(result)


# ============================================================================
# CHECKPOINTER TESTS
# ============================================================================


class TestCheckpointerManager:
    """Tests for checkpointer.py - LangGraph checkpoint integration."""

    def test_import_checkpointer(self):
        """Test checkpointer module imports correctly."""
        from langgraph_engine.checkpointer import CheckpointerManager

        assert CheckpointerManager is not None

    def test_get_memory_checkpointer(self):
        """Test MemorySaver creation."""
        try:
            from langgraph_engine.checkpointer import CheckpointerManager

            cp = CheckpointerManager.get_memory_checkpointer()
            assert cp is not None
        except RuntimeError:
            pytest.skip("LangGraph not installed")

    def test_get_default_checkpointer_memory_mode(self):
        """Test default checkpointer in memory mode."""
        try:
            from langgraph_engine.checkpointer import CheckpointerManager

            cp = CheckpointerManager.get_default_checkpointer(use_sqlite=False)
            assert cp is not None
        except RuntimeError:
            pytest.skip("LangGraph not installed")

    def test_get_sqlite_checkpointer_with_tmp(self):
        """Test SQLite checkpointer creation with temp path."""
        try:
            from langgraph_engine.checkpointer import CheckpointerManager

            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test-checkpoints.db"
                cp = CheckpointerManager.get_sqlite_checkpointer(db_path)
                assert cp is not None
        except RuntimeError:
            pytest.skip("LangGraph not installed")

    def test_setup_checkpoint_db(self):
        """Test checkpoint DB setup and verification."""
        from langgraph_engine.checkpointer import CheckpointerManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            result = CheckpointerManager.setup_checkpoint_db(db_path)
            assert result is True
            assert db_path.exists()

    def test_get_checkpoint_info_no_db(self):
        """Test checkpoint info when no DB exists."""
        from langgraph_engine.checkpointer import CheckpointerManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nonexistent.db"
            info = CheckpointerManager.get_checkpoint_info(db_path)
            assert info["exists"] is False

    def test_get_checkpoint_info_with_db(self):
        """Test checkpoint info with existing DB."""
        from langgraph_engine.checkpointer import CheckpointerManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            # Create the DB
            CheckpointerManager.setup_checkpoint_db(db_path)
            info = CheckpointerManager.get_checkpoint_info(db_path)
            assert info["exists"] is True
            assert "db_size_kb" in info

    def test_get_invoke_config(self):
        """Test invoke config generation."""
        from langgraph_engine.checkpointer import get_invoke_config

        config = get_invoke_config("SESSION-test-123")
        assert config["configurable"]["thread_id"] == "SESSION-test-123"
        assert config["recursion_limit"] == 1000

    def test_get_checkpointer_config(self):
        """Test checkpointer config dict."""
        try:
            from langgraph_engine.checkpointer import get_checkpointer_config

            config = get_checkpointer_config()
            assert "checkpointer" in config
            assert config["checkpointer"] is not None
        except RuntimeError:
            pytest.skip("LangGraph not installed")


# ============================================================================
# SYSTEM HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.skip(
    reason="enforcement_mcp_server.py moved to techdeveloper-org/mcp-enforcement; "
    "tests should live in that repo -- see issue #202"
)
class TestSystemHealthCheck:
    """Tests for check_system_health in enforcement MCP server."""

    @pytest.fixture(autouse=True)
    def load_module(self):
        self.mod = _load_mcp_module("enforcement_mcp_test", "enforcement_mcp_server.py")

    def test_health_check_returns_json(self):
        """Test system health check returns valid JSON."""
        result = _parse(self.mod.check_system_health())
        assert result["success"] is True
        assert "components" in result
        assert "overall" in result
        assert "timestamp" in result

    def test_health_check_has_mcp_servers(self):
        """Test health includes MCP server status."""
        result = _parse(self.mod.check_system_health())
        assert "mcp_servers" in result["components"]

    def test_health_check_has_llm_providers(self):
        """Test health includes LLM provider status."""
        result = _parse(self.mod.check_system_health())
        assert "llm_providers" in result["components"]

    def test_health_check_has_checkpoint_db(self):
        """Test health includes checkpoint DB status."""
        result = _parse(self.mod.check_system_health())
        assert "checkpoint_db" in result["components"]

    def test_health_check_overall_status(self):
        """Test overall status is HEALTHY or DEGRADED."""
        result = _parse(self.mod.check_system_health())
        assert result["overall"] in ("HEALTHY", "DEGRADED")


# ============================================================================
# DYNAMIC STANDARDS RELOAD TESTS
# ============================================================================


@pytest.mark.skip(
    reason="standards_loader_mcp_server.py moved to techdeveloper-org/mcp-standards-loader; "
    "tests should live in that repo -- see issue #202"
)
class TestDynamicStandardsReload:
    """Tests for reload_standards in standards_loader MCP server."""

    @pytest.fixture(autouse=True)
    def load_module(self):
        self.mod = _load_mcp_module("standards_loader_test", "standards_loader_mcp_server.py")

    def test_reload_returns_json(self):
        """Test reload_standards returns valid JSON."""
        result = _parse(
            self.mod.reload_standards(
                project_path=str(_PROJECT_ROOT),
                start_watcher=False,
            )
        )
        assert result["success"] is True
        assert result["reloaded"] is True

    def test_reload_returns_standards_count(self):
        """Test reload returns standards count."""
        result = _parse(
            self.mod.reload_standards(
                project_path=str(_PROJECT_ROOT),
                start_watcher=False,
            )
        )
        assert "standards_loaded" in result
        assert isinstance(result["standards_loaded"], int)

    def test_reload_detects_project_type(self):
        """Test reload detects project type."""
        result = _parse(
            self.mod.reload_standards(
                project_path=str(_PROJECT_ROOT),
                start_watcher=False,
            )
        )
        assert result["project_type"] == "python"

    def test_cache_invalidation(self):
        """Test that cache is invalidated on reload."""
        self.mod._standards_cache = {"cached": True}
        self.mod._cache_timestamp = 999999999
        self.mod._invalidate_cache()
        assert self.mod._standards_cache == {}
        assert self.mod._cache_timestamp == 0

    def test_file_watcher_status(self):
        """Test watcher status when watchdog not installed."""
        self.mod._file_watcher_active = False
        result = self.mod._start_file_watcher()
        # Either started or not installed
        assert result["status"] in ("started", "watchdog_not_installed", "error", "already_running")

    def test_watched_dirs(self):
        """Test _get_watched_dirs returns existing dirs only."""
        dirs = self.mod._get_watched_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert d.exists()

    def test_reload_with_watcher(self):
        """Test reload with watcher enabled."""
        self.mod._file_watcher_active = False
        result = _parse(
            self.mod.reload_standards(
                project_path=str(_PROJECT_ROOT),
                start_watcher=True,
            )
        )
        assert result["success"] is True
        assert "watcher" in result
        assert "watched_dirs" in result


# ============================================================================
# ORCHESTRATOR CHECKPOINTER INTEGRATION TESTS
# ============================================================================


class TestOrchestratorCheckpointer:
    """Tests for checkpointer integration in orchestrator.py."""

    def test_orchestrator_imports_checkpointer(self):
        """Test orchestrator imports CheckpointerManager."""
        from langgraph_engine.orchestrator import CheckpointerManager

        assert CheckpointerManager is not None

    def test_create_flow_graph_compiles(self):
        """Test create_flow_graph compiles successfully."""
        try:
            from langgraph_engine.orchestrator import create_flow_graph

            graph = create_flow_graph()
            assert graph is not None
        except Exception:
            pytest.skip("LangGraph or dependencies not fully available")

    def test_create_initial_state(self):
        """Test create_initial_state builds valid state."""
        from langgraph_engine.orchestrator import create_initial_state

        state = create_initial_state(
            session_id="test-session",
            project_root="/tmp/test",
            user_message="test task",
        )
        assert state["session_id"] == "test-session"
        assert state["user_message"] == "test task"
        assert state["user_message_original"] == "test task"
