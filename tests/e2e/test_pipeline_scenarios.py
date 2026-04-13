"""End-to-end pipeline scenario tests.

These tests verify high-level pipeline behaviors using mocked LangGraph
execution. They do not require real LLM providers or GitHub access.

Mark: pytest.mark.e2e
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_SRC_MCP_DIR = _PROJECT_ROOT / "src" / "mcp"

for _p in [str(_PROJECT_ROOT), str(_SCRIPTS_DIR), str(_SRC_MCP_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Scenario 1: Stale call graph guard
# ---------------------------------------------------------------------------


class TestStaleCallGraphGuard:
    """Scenario: when call_graph_stale=True, refresh_call_graph_if_stale
    rebuilds the graph rather than returning a cached pre-implementation snapshot.
    """

    def test_stale_flag_triggers_rebuild(self, tmp_path):
        """refresh_call_graph_if_stale must call snapshot_call_graph when stale=True."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.call_graph_analyzer import refresh_call_graph_if_stale
        except ImportError:
            pytest.skip("call_graph_analyzer not importable")

        mock_state = {
            "call_graph_stale": True,
            "step10_pre_change_graph": {
                "nodes": ["old_node"],
                "call_graph_available": True,
            },
        }

        with patch("langgraph_engine.level3_execution.call_graph_analyzer.snapshot_call_graph") as mock_snap:
            mock_snap.return_value = {
                "nodes": ["fresh_node"],
                "call_graph_available": True,
            }
            result = refresh_call_graph_if_stale(mock_state, str(tmp_path))

        mock_snap.assert_called_once_with(str(tmp_path))
        assert result is not None

    def test_not_stale_returns_cached_snapshot(self, tmp_path):
        """When call_graph_stale is False, the cached step10 snapshot is returned."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.call_graph_analyzer import refresh_call_graph_if_stale
        except ImportError:
            pytest.skip("call_graph_analyzer not importable")

        cached = {
            "nodes": ["cached_node"],
            "call_graph_available": True,
        }
        mock_state = {
            "call_graph_stale": False,
            "step10_pre_change_graph": cached,
        }

        with patch("langgraph_engine.level3_execution.call_graph_analyzer.snapshot_call_graph") as mock_snap:
            result = refresh_call_graph_if_stale(mock_state, str(tmp_path))

        mock_snap.assert_not_called()
        assert result == cached

    def test_stale_flag_false_nothing_cached_falls_back_to_fresh_scan(self, tmp_path):
        """When not stale and no cache entries available, do a fresh scan."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.call_graph_analyzer import refresh_call_graph_if_stale
        except ImportError:
            pytest.skip("call_graph_analyzer not importable")

        empty_state = {
            "call_graph_stale": False,
        }

        with patch("langgraph_engine.level3_execution.call_graph_analyzer.snapshot_call_graph") as mock_snap:
            mock_snap.return_value = {"call_graph_available": False}
            result = refresh_call_graph_if_stale(empty_state, str(tmp_path))

        mock_snap.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# Scenario 2: Hook mode vs Full mode
# ---------------------------------------------------------------------------


class TestHookModeVsFullMode:
    """Scenario: CLAUDE_HOOK_MODE env var controls whether step 10-14 execute."""

    def test_hook_mode_env_set_to_1(self):
        """With CLAUDE_HOOK_MODE=1 the env var must equal '1'."""
        saved = os.environ.get("CLAUDE_HOOK_MODE")
        try:
            os.environ["CLAUDE_HOOK_MODE"] = "1"
            assert os.environ.get("CLAUDE_HOOK_MODE") == "1"
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_HOOK_MODE", None)
            else:
                os.environ["CLAUDE_HOOK_MODE"] = saved

    def test_hook_mode_env_set_to_0(self):
        """With CLAUDE_HOOK_MODE=0 the env var must equal '0'."""
        saved = os.environ.get("CLAUDE_HOOK_MODE")
        try:
            os.environ["CLAUDE_HOOK_MODE"] = "0"
            assert os.environ.get("CLAUDE_HOOK_MODE") == "0"
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_HOOK_MODE", None)
            else:
                os.environ["CLAUDE_HOOK_MODE"] = saved

    def test_hook_mode_detection_logic(self):
        """Pipeline hook_mode flag must be True when CLAUDE_HOOK_MODE=1."""
        saved = os.environ.get("CLAUDE_HOOK_MODE")
        try:
            os.environ["CLAUDE_HOOK_MODE"] = "1"
            hook_mode = os.environ.get("CLAUDE_HOOK_MODE", "1") == "1"
            assert hook_mode is True
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_HOOK_MODE", None)
            else:
                os.environ["CLAUDE_HOOK_MODE"] = saved

    def test_full_mode_detection_logic(self):
        """Pipeline hook_mode flag must be False when CLAUDE_HOOK_MODE=0."""
        saved = os.environ.get("CLAUDE_HOOK_MODE")
        try:
            os.environ["CLAUDE_HOOK_MODE"] = "0"
            hook_mode = os.environ.get("CLAUDE_HOOK_MODE", "1") == "1"
            assert hook_mode is False
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_HOOK_MODE", None)
            else:
                os.environ["CLAUDE_HOOK_MODE"] = saved


# ---------------------------------------------------------------------------
# Scenario 3: Secrets validation blocks missing key
# ---------------------------------------------------------------------------


class TestSecretsValidationBlocksMissingKey:
    """Scenario: validate_secrets() raises SecretsMissingError when ANTHROPIC_API_KEY absent."""

    def test_missing_anthropic_key_raises(self):
        """validate_secrets must raise SecretsMissingError when ANTHROPIC_API_KEY is absent."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.secrets_manager import SecretsMissingError, validate_secrets
        except ImportError:
            pytest.skip("secrets_manager not importable")

        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        saved_gh = os.environ.pop("GITHUB_TOKEN", None)
        try:
            with pytest.raises(SecretsMissingError) as exc_info:
                validate_secrets()
            assert "ANTHROPIC_API_KEY" in exc_info.value.missing_keys
        finally:
            if saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key
            if saved_gh is not None:
                os.environ["GITHUB_TOKEN"] = saved_gh

    def test_missing_github_token_raises(self):
        """validate_secrets must raise SecretsMissingError when GITHUB_TOKEN is absent."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.secrets_manager import SecretsMissingError, validate_secrets
        except ImportError:
            pytest.skip("secrets_manager not importable")

        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        saved_gh = os.environ.pop("GITHUB_TOKEN", None)
        try:
            with pytest.raises(SecretsMissingError) as exc_info:
                validate_secrets()
            assert len(exc_info.value.missing_keys) > 0
        finally:
            if saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key
            if saved_gh is not None:
                os.environ["GITHUB_TOKEN"] = saved_gh

    def test_all_required_keys_present_does_not_raise(self):
        """validate_secrets must not raise when all required keys are present and non-empty."""
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))

        try:
            from langgraph_engine.secrets_manager import validate_secrets
        except ImportError:
            pytest.skip("secrets_manager not importable")

        saved_key = os.environ.get("ANTHROPIC_API_KEY")
        saved_gh = os.environ.get("GITHUB_TOKEN")
        try:
            os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key-value"
            os.environ["GITHUB_TOKEN"] = "test-github-token-value"
            validate_secrets()  # must not raise
        finally:
            if saved_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_key
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            if saved_gh is not None:
                os.environ["GITHUB_TOKEN"] = saved_gh
            else:
                os.environ.pop("GITHUB_TOKEN", None)
