"""Tests for Vector DB MCP Server (src/mcp/vector_db_mcp_server.py)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import importlib.util

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"


def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Mock qdrant_client and sentence_transformers before loading module
_mock_qdrant = MagicMock()
_mock_st = MagicMock()
sys.modules["qdrant_client"] = _mock_qdrant
sys.modules["qdrant_client.models"] = MagicMock()
sys.modules["sentence_transformers"] = _mock_st

_vec_mod = _load_module("vector_db_mcp_server", _MCP_DIR / "vector_db_mcp_server.py")


def _parse(result: str) -> dict:
    return json.loads(result)


class TestVectorHealthCheck:
    """Tests for vector_health_check tool."""

    def test_health_check_returns_json(self):
        """Test health check returns valid JSON."""
        # Reset global state
        _vec_mod._qdrant_client = None
        _vec_mod._embedding_model = None
        result = _parse(_vec_mod.vector_health_check())
        assert "qdrant_available" in result
        assert "embeddings_available" in result
        assert "db_path" in result

    def test_health_check_with_no_qdrant(self):
        """Test health when Qdrant is unavailable."""
        _vec_mod._qdrant_client = None
        _vec_mod._QDRANT_AVAILABLE = False
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=None):
            result = _parse(_vec_mod.vector_health_check())
            assert result["qdrant_available"] is False


class TestVectorCollectionStats:
    """Tests for vector_get_collection_stats tool."""

    def test_stats_no_qdrant(self):
        """Test stats when Qdrant unavailable."""
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=None):
            result = _parse(_vec_mod.vector_get_collection_stats())
            assert result["success"] is False
            assert "not available" in result["error"]

    def test_stats_all_collections(self):
        """Test stats for all collections."""
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 10
        mock_info.vectors_count = 10
        mock_info.status = "green"
        mock_client.get_collection.return_value = mock_info

        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client):
            result = _parse(_vec_mod.vector_get_collection_stats("all"))
            assert result["success"] is True
            assert "tool_calls" in result["collections"]
            assert "sessions" in result["collections"]
            assert "flow_traces" in result["collections"]
            assert "node_decisions" in result["collections"]
            assert result["total_points"] == 40  # 10 per 4 collections


class TestVectorIndexToolCall:
    """Tests for vector_index_tool_call tool."""

    def test_index_no_qdrant(self):
        """Test indexing when Qdrant unavailable."""
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=None):
            result = _parse(_vec_mod.vector_index_tool_call(
                tool_name="Read", status="success"
            ))
            assert result["success"] is False

    def test_index_tool_call_success(self):
        """Test successful tool call indexing."""
        mock_client = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1] * 384

        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_index_tool_call(
                tool_name="Edit",
                status="success",
                duration_ms=150,
                project="claude-insight",
                complexity=5,
                session_id="SESSION-001",
                description="Edited orchestrator.py",
            ))
            assert result["success"] is True
            assert result["collection"] == "tool_calls"
            assert result["tool_name"] == "Edit"
            mock_client.upsert.assert_called_once()


class TestVectorIndexSession:
    """Tests for vector_index_session tool."""

    def test_index_session_success(self):
        """Test successful session indexing."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_index_session(
                session_id="SESSION-001",
                project="claude-insight",
                summary="MCP migration session",
                tool_count=42,
                context_pct=65.5,
            ))
            assert result["success"] is True
            assert result["collection"] == "sessions"


class TestVectorIndexFlowTrace:
    """Tests for vector_index_flow_trace tool."""

    def test_index_flow_trace_success(self):
        """Test successful flow trace indexing."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_index_flow_trace(
                session_id="SESSION-001",
                level="level3",
                step="step5_skill_selection",
                status="OK",
                context_pct=30.0,
                description="Selected langgraph-core skill",
            ))
            assert result["success"] is True
            assert result["collection"] == "flow_traces"


class TestVectorSearch:
    """Tests for vector search tools."""

    def test_search_similar_no_qdrant(self):
        """Test search when Qdrant unavailable."""
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=None):
            result = _parse(_vec_mod.vector_search_similar(
                query="tool calls that failed"
            ))
            assert result["success"] is False

    def test_search_unknown_collection(self):
        """Test search in unknown collection."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client):
            result = _parse(_vec_mod.vector_search_similar(
                query="test", collection="nonexistent"
            ))
            assert result["success"] is False
            assert "Unknown collection" in result["error"]

    def test_search_similar_success(self):
        """Test successful semantic search."""
        mock_client = MagicMock()
        mock_hit = MagicMock()
        mock_hit.id = 12345
        mock_hit.score = 0.92
        mock_hit.payload = {"tool_name": "Edit", "status": "success"}
        mock_client.search.return_value = [mock_hit]

        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_search_similar(
                query="edit operations",
                collection="tool_calls",
                limit=5,
            ))
            assert result["success"] is True
            assert result["total_matches"] == 1
            assert result["matches"][0]["score"] == 0.92

    def test_search_sessions_delegates(self):
        """Test search_sessions delegates to search_similar."""
        mock_client = MagicMock()
        mock_client.search.return_value = []
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_search_sessions(
                query="MCP migration"
            ))
            assert result["success"] is True
            assert result["collection"] == "sessions"

    def test_search_traces_with_filter(self):
        """Test search_traces with level filter."""
        mock_client = MagicMock()
        mock_client.search.return_value = []
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_search_traces(
                query="encoding failures",
                level="level_minus1",
            ))
            assert result["success"] is True


class TestVectorDeleteCollection:
    """Tests for vector_delete_collection tool."""

    def test_delete_unknown_collection(self):
        """Test deleting unknown collection."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client):
            result = _parse(_vec_mod.vector_delete_collection("nonexistent"))
            assert result["success"] is False

    def test_delete_and_recreate(self):
        """Test delete recreates empty collection."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client):
            result = _parse(_vec_mod.vector_delete_collection("tool_calls"))
            assert result["success"] is True
            assert result["action"] == "deleted_and_recreated"
            mock_client.delete_collection.assert_called_once_with("tool_calls")
            mock_client.create_collection.assert_called_once()


class TestVectorBulkIndex:
    """Tests for vector_bulk_index tool."""

    def test_bulk_index_invalid_json(self):
        """Test bulk index with invalid JSON."""
        mock_client = MagicMock()
        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client):
            result = _parse(_vec_mod.vector_bulk_index(
                collection="tool_calls",
                records_json="not valid json"
            ))
            assert result["success"] is False

    def test_bulk_index_success(self):
        """Test successful bulk indexing."""
        mock_client = MagicMock()
        records = [
            {"text": "Edit file success", "tool_name": "Edit", "status": "success"},
            {"text": "Read file blocked", "tool_name": "Read", "status": "blocked"},
        ]

        with patch.object(_vec_mod, "_get_qdrant_client", return_value=mock_client), \
             patch.object(_vec_mod, "_embed_text", return_value=[0.1] * 384):
            result = _parse(_vec_mod.vector_bulk_index(
                collection="tool_calls",
                records_json=json.dumps(records),
            ))
            assert result["success"] is True
            assert result["indexed"] == 2
            assert result["errors"] == 0


class TestCollectionDefinitions:
    """Tests for collection configuration."""

    def test_all_collections_defined(self):
        """Test all 3 collections are defined."""
        assert "tool_calls" in _vec_mod.COLLECTIONS
        assert "sessions" in _vec_mod.COLLECTIONS
        assert "flow_traces" in _vec_mod.COLLECTIONS

    def test_collection_dimensions(self):
        """Test all collections use 384-dim vectors (MiniLM)."""
        for name, config in _vec_mod.COLLECTIONS.items():
            assert config["size"] == 384, f"{name} should use 384-dim vectors"
            assert config["distance"] == "Cosine"
