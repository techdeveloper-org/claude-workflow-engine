"""Tests for Session Management MCP Server (src/mcp/session_mcp_server.py)."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
import importlib.util

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"

def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_sess_mod = _load_module("session_mcp_server", _MCP_DIR / "session_mcp_server.py")

session_save = _sess_mod.session_save
session_load = _sess_mod.session_load
session_list = _sess_mod.session_list
session_archive = _sess_mod.session_archive
session_query = _sess_mod.session_query


def _parse(result: str) -> dict:
    """Parse JSON result from MCP tool."""
    return json.loads(result)


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create a temporary session directory structure."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    state = tmp_path / ".state"
    state.mkdir()

    # Patch the module-level paths
    with patch.object(_sess_mod, "SESSIONS_PATH", sessions), \
         patch.object(_sess_mod, "STATE_PATH", state), \
         patch.object(_sess_mod, "MEMORY_PATH", tmp_path):
        yield tmp_path, sessions, state


class TestSessionSave:
    """Tests for session_save tool."""

    def test_save_summary(self, temp_session_dir):
        """Test saving a session summary."""
        _, sessions, _ = temp_session_dir
        result = _parse(session_save(
            "2026-03-15-14-30", "summary",
            "# Session Summary\n\nWorked on MCP servers.",
            "claude-insight"
        ))
        assert result["success"] is True
        assert result["data_type"] == "summary"

        # Verify file exists
        saved = sessions / "claude-insight" / "session-2026-03-15-14-30.md"
        assert saved.exists()
        assert "MCP servers" in saved.read_text(encoding="utf-8")

    def test_save_state(self, temp_session_dir):
        """Test saving session state as JSON."""
        _, _, state = temp_session_dir
        state_data = json.dumps({"current_task": "Build MCP", "step": 3})
        result = _parse(session_save("1", "state", state_data, "my-project"))
        assert result["success"] is True

        # Verify state file
        state_file = state / "my-project.json"
        assert state_file.exists()
        loaded = json.loads(state_file.read_text(encoding="utf-8"))
        assert loaded["current_task"] == "Build MCP"

    def test_save_context(self, temp_session_dir):
        """Test saving context snapshot."""
        result = _parse(session_save(
            "ctx-001", "context",
            json.dumps({"files": ["a.py", "b.py"]}),
            "test-project"
        ))
        assert result["success"] is True
        assert result["data_type"] == "context"

    def test_save_invalid_type(self, temp_session_dir):
        """Test saving with invalid data_type."""
        result = _parse(session_save("1", "invalid", "data", "test"))
        assert result["success"] is False
        assert "Unknown data_type" in result["error"]


class TestSessionLoad:
    """Tests for session_load tool."""

    def test_load_state(self, temp_session_dir):
        """Test loading session state."""
        _, _, state = temp_session_dir
        # Create state file
        state_file = state / "test-project.json"
        state_file.write_text(json.dumps({"task": "done"}), encoding="utf-8")

        result = _parse(session_load("", "state", "test-project"))
        assert result["success"] is True
        assert result["data"]["task"] == "done"

    def test_load_missing_state(self, temp_session_dir):
        """Test loading non-existent state returns empty."""
        result = _parse(session_load("", "state", "nonexistent"))
        assert result["success"] is True
        assert result["data"] == {}

    def test_load_summary_latest(self, temp_session_dir):
        """Test loading latest session summary."""
        _, sessions, _ = temp_session_dir
        proj = sessions / "test"
        proj.mkdir()
        (proj / "session-2026-03-14.md").write_text("Day 1", encoding="utf-8")
        (proj / "session-2026-03-15.md").write_text("Day 2", encoding="utf-8")

        result = _parse(session_load("", "summary", "test"))
        assert result["success"] is True
        assert "Day 2" in result["data"]

    def test_load_summary_by_id(self, temp_session_dir):
        """Test loading specific session by ID."""
        _, sessions, _ = temp_session_dir
        proj = sessions / "test"
        proj.mkdir()
        (proj / "session-abc.md").write_text("Specific session", encoding="utf-8")

        result = _parse(session_load("abc", "summary", "test"))
        assert result["success"] is True
        assert "Specific session" in result["data"]


class TestSessionList:
    """Tests for session_list tool."""

    def test_list_empty(self, temp_session_dir):
        """Test listing when no sessions exist."""
        result = _parse(session_list("nonexistent"))
        assert result["success"] is True
        assert result["count"] == 0

    def test_list_with_sessions(self, temp_session_dir):
        """Test listing sessions across projects."""
        _, sessions, _ = temp_session_dir
        for proj in ["proj-a", "proj-b"]:
            d = sessions / proj
            d.mkdir()
            (d / "session-001.md").write_text("test", encoding="utf-8")
            (d / "session-002.md").write_text("test", encoding="utf-8")

        result = _parse(session_list(""))
        assert result["success"] is True
        assert result["count"] == 4

    def test_list_with_limit(self, temp_session_dir):
        """Test limiting session list."""
        _, sessions, _ = temp_session_dir
        d = sessions / "test"
        d.mkdir()
        for i in range(10):
            (d / f"session-{i:03d}.md").write_text(f"session {i}", encoding="utf-8")

        result = _parse(session_list("test", 3))
        assert result["success"] is True
        assert result["count"] == 3


class TestSessionArchive:
    """Tests for session_archive tool."""

    def test_archive_no_old_sessions(self, temp_session_dir):
        """Test archiving when all sessions are fresh."""
        _, sessions, _ = temp_session_dir
        d = sessions / "test"
        d.mkdir()
        (d / "session-fresh.md").write_text("new", encoding="utf-8")

        result = _parse(session_archive(30))
        assert result["success"] is True
        assert result["count"] == 0


class TestSessionQuery:
    """Tests for session_query tool."""

    def test_query_by_keyword(self, temp_session_dir):
        """Test querying sessions by keyword."""
        _, sessions, _ = temp_session_dir
        d = sessions / "test"
        d.mkdir()
        (d / "session-mcp.md").write_text("Built MCP servers today", encoding="utf-8")
        (d / "session-other.md").write_text("Did something else", encoding="utf-8")

        result = _parse(session_query(json.dumps({"keyword": "MCP"})))
        assert result["success"] is True
        assert result["count"] == 1

    def test_query_by_project(self, temp_session_dir):
        """Test querying by project filter."""
        _, sessions, _ = temp_session_dir
        for proj in ["proj-a", "proj-b"]:
            d = sessions / proj
            d.mkdir()
            (d / "session-001.md").write_text("test", encoding="utf-8")

        result = _parse(session_query(json.dumps({"project": "proj-a"})))
        assert result["success"] is True
        assert result["count"] == 1
        assert result["results"][0]["project"] == "proj-a"

    def test_query_invalid_json(self, temp_session_dir):
        """Test query with invalid JSON filter."""
        result = _parse(session_query("not valid json"))
        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    def test_query_empty_filter(self, temp_session_dir):
        """Test query with empty filter."""
        result = _parse(session_query("{}"))
        assert result["success"] is True
