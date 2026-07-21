"""Unit tests for src/utils/import_manager.py -- ImportManager.get_skill() /
get_agent(), now routed through the ADR-1 local-path bridge (resolver.py).

Covers:
- Real local hit against the sibling claude-global-library (docker skill, agent.md)
- Resolver failure (LibrarySetupError) is swallowed -> None (unchanged public contract)
- Invalid resource name (ValueError) is swallowed -> None
- Return dict shape is unchanged: name, content, source, url
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import utils.import_manager as import_manager_module  # noqa: E402
from langgraph_engine.library.resolver import _reset_library_root_cache  # noqa: E402
from utils.import_manager import ImportManager  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_resolver_singleton():
    """Each test gets a fresh resolver singleton and a clean locate_library_root() cache."""
    import_manager_module._resolver = None
    _reset_library_root_cache()
    yield
    import_manager_module._resolver = None
    _reset_library_root_cache()


class TestGetSkillLocalHit:
    def test_docker_skill_resolves_locally_zero_network(self, monkeypatch):
        """Real integration: skills/docker/SKILL.md exists in the sibling checkout."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = ImportManager.get_skill("docker")

        mock_urlopen.assert_not_called()
        assert result is not None
        assert result["name"] == "docker"
        assert result["source"] == "local"
        assert "content" in result and len(result["content"]) > 0
        assert "url" in result

    def test_agent_resolves_locally(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = ImportManager.get_agent("python-backend-engineer")

        mock_urlopen.assert_not_called()
        assert result is not None
        assert result["source"] == "local"
        assert result["name"] == "python-backend-engineer"


class TestGetSkillFailureModes:
    def test_missing_skill_returns_none_not_exception(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        # Real sibling is present, but this skill name does not exist in it,
        # and GitHub fallback is disabled -> resolver raises LibrarySetupError
        # -> get_skill() must swallow it and return None (unchanged contract).
        result = ImportManager.get_skill("definitely-not-a-real-skill-xyz")
        assert result is None

    def test_invalid_name_returns_none(self):
        result = ImportManager.get_skill("../../etc/passwd")
        assert result is None

    def test_invalid_agent_name_returns_none(self):
        result = ImportManager.get_agent("Not_Valid_Name!!")
        assert result is None

    def test_library_setup_error_is_caught(self, tmp_path, monkeypatch):
        """Force an absent sibling + disabled fallback to exercise the raise/catch path directly."""
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(tmp_path / "does-not-exist"))
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        # Force resolver rebuild against a fake, non-sibling engine_root so the
        # real checkout isn't found as the default-layout fallback either.
        fake_engine_root = tmp_path / "claude-workflow-engine"
        fake_engine_root.mkdir()
        import_manager_module.PROJECT_ROOT = fake_engine_root
        try:
            result = ImportManager.get_skill("anything")
            assert result is None
        finally:
            import_manager_module.PROJECT_ROOT = _PROJECT_ROOT


class TestGetSkillGitHubFallback:
    def test_github_fallback_used_when_enabled_and_local_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_ALLOW_GITHUB_FALLBACK", "1")
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(tmp_path / "does-not-exist"))
        fake_engine_root = tmp_path / "claude-workflow-engine"
        fake_engine_root.mkdir()
        import_manager_module.PROJECT_ROOT = fake_engine_root
        try:
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value.__enter__.return_value.read.return_value = b"remote content"
                result = ImportManager.get_skill("some-remote-skill")
            assert result is not None
            assert result["source"] == "github"
            assert result["content"] == "remote content"
        finally:
            import_manager_module.PROJECT_ROOT = _PROJECT_ROOT
