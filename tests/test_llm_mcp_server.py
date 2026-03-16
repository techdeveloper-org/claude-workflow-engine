"""Tests for LLM Provider MCP Server (src/mcp/llm_mcp_server.py)."""

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

_llm_mod = _load_module("llm_mcp_server", _MCP_DIR / "llm_mcp_server.py")

llm_generate = _llm_mod.llm_generate
llm_list_models = _llm_mod.llm_list_models
llm_health_check = _llm_mod.llm_health_check


def _parse(result: str) -> dict:
    """Parse JSON result from MCP tool."""
    return json.loads(result)


class TestLLMGenerate:
    """Tests for llm_generate tool."""

    @patch("llm_mcp_server._get_llm_module")
    def test_generate_success(self, mock_get_module):
        """Test successful LLM generation."""
        mock_call = MagicMock(return_value="Hello, world!")
        mock_get_module.return_value = {
            "llm_call": mock_call,
            "get_active_providers": lambda: ["ollama"],
            "provider_chain": [],
            "default_temps": {"fast": 0.1, "balanced": 0.3, "deep": 0.4},
        }

        result = _parse(llm_generate("Say hello", "fast"))
        assert result["success"] is True
        assert result["response"] == "Hello, world!"
        assert result["model"] == "fast"

    @patch("llm_mcp_server._get_llm_module")
    def test_generate_all_providers_fail(self, mock_get_module):
        """Test when all providers fail."""
        mock_call = MagicMock(return_value=None)
        mock_get_module.return_value = {
            "llm_call": mock_call,
            "get_active_providers": lambda: [],
            "provider_chain": [],
            "default_temps": {"fast": 0.1},
        }

        result = _parse(llm_generate("Test", "fast"))
        assert result["success"] is False
        assert "failed" in result["error"].lower()

    @patch("llm_mcp_server._get_llm_module")
    def test_generate_specific_provider(self, mock_get_module):
        """Test generation with specific provider."""
        mock_provider = MagicMock()
        mock_provider.name = "ollama"
        mock_provider.call.return_value = "Ollama response"

        mock_get_module.return_value = {
            "llm_call": MagicMock(),
            "get_active_providers": lambda: ["ollama"],
            "provider_chain": [mock_provider],
            "default_temps": {"fast": 0.1},
        }

        result = _parse(llm_generate("Test", "fast", "ollama"))
        assert result["success"] is True
        assert result["response"] == "Ollama response"
        assert result["provider"] == "ollama"

    @patch("llm_mcp_server._get_llm_module")
    def test_generate_unavailable_provider(self, mock_get_module):
        """Test requesting unavailable provider."""
        mock_get_module.return_value = {
            "llm_call": MagicMock(),
            "get_active_providers": lambda: [],
            "provider_chain": [],
            "default_temps": {"fast": 0.1},
        }

        result = _parse(llm_generate("Test", "fast", "nonexistent"))
        assert result["success"] is False
        assert "not available" in result["error"]

    @patch("llm_mcp_server._get_llm_module")
    def test_generate_module_error(self, mock_get_module):
        """Test when LLM module fails to import."""
        mock_get_module.return_value = {"error": "Module not found"}

        result = _parse(llm_generate("Test"))
        assert result["success"] is False
        assert "not available" in result["error"]


class TestLLMListModels:
    """Tests for llm_list_models tool."""

    @patch("llm_mcp_server._get_llm_module")
    def test_list_models(self, mock_get_module):
        """Test listing available models."""
        mock_provider = MagicMock()
        mock_provider.name = "ollama"
        mock_provider.is_available.return_value = True
        mock_provider._model_fast = "qwen2.5:7b"
        mock_provider._model_deep = "qwen2.5:14b"

        mock_get_module.return_value = {
            "llm_call": MagicMock(),
            "get_active_providers": lambda: ["ollama"],
            "provider_chain": [mock_provider],
            "default_temps": {},
        }

        result = _parse(llm_list_models())
        assert result["success"] is True
        assert result["active_count"] == 1
        assert len(result["providers"]) == 1
        assert result["providers"][0]["name"] == "ollama"
        assert "model_tiers" in result

    @patch("llm_mcp_server._get_llm_module")
    def test_list_models_module_error(self, mock_get_module):
        """Test listing when module not available."""
        mock_get_module.return_value = {"error": "Import failed"}

        result = _parse(llm_list_models())
        assert result["success"] is False


class TestLLMHealthCheck:
    """Tests for llm_health_check tool."""

    @patch("llm_mcp_server._get_llm_module")
    def test_health_check_healthy(self, mock_get_module):
        """Test health check with healthy providers."""
        mock_provider = MagicMock()
        mock_provider.name = "ollama"
        mock_provider.is_available.return_value = True
        mock_provider._endpoint = "http://localhost:11434/api/generate"

        mock_get_module.return_value = {
            "llm_call": MagicMock(),
            "get_active_providers": lambda: ["ollama"],
            "provider_chain": [mock_provider],
            "default_temps": {},
        }

        result = _parse(llm_health_check())
        assert result["success"] is True
        assert result["healthy"] is True
        assert result["providers"]["ollama"]["available"] is True

    @patch("llm_mcp_server._get_llm_module")
    def test_health_check_no_providers(self, mock_get_module):
        """Test health check with no available providers."""
        mock_provider = MagicMock()
        mock_provider.name = "ollama"
        mock_provider.is_available.return_value = False

        mock_get_module.return_value = {
            "llm_call": MagicMock(),
            "get_active_providers": lambda: [],
            "provider_chain": [mock_provider],
            "default_temps": {},
        }

        result = _parse(llm_health_check())
        assert result["success"] is True
        assert result["healthy"] is False


class TestJsonFormat:
    """Tests for consistent JSON response format."""

    @patch("llm_mcp_server._get_llm_module")
    def test_all_tools_return_valid_json(self, mock_get_module):
        """Verify all tools return valid JSON with success field."""
        mock_get_module.return_value = {
            "llm_call": MagicMock(return_value=None),
            "get_active_providers": lambda: [],
            "provider_chain": [],
            "default_temps": {"fast": 0.1},
        }

        tools = [
            lambda: llm_generate("test"),
            llm_list_models,
            llm_health_check,
        ]
        for tool_fn in tools:
            result = json.loads(tool_fn())
            assert "success" in result
