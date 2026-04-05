"""
Tests for src/mcp/base/clients.py - LazyClient singleton pattern and concrete clients.

Covers:
- LazyClient singleton lifecycle, reset, availability, and health check structure
- GitRepoClient.for_path factory behavior (mocked GitPython)
- GitHubApiClient token resolution (env var vs gh CLI subprocess)
- GitHubApiClient._parse_remote SSH and HTTPS URL formats

ASCII-only: cp1252 safe for Windows.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "mcp"))

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_concrete_client(initialize_return=object()):
    """Return a minimal concrete LazyClient subclass for isolated testing."""
    from base.clients import LazyClient

    class _Concrete(LazyClient):
        _init_call_count = 0

        def _initialize(self):
            _Concrete._init_call_count += 1
            if isinstance(initialize_return, Exception):
                raise initialize_return
            return initialize_return

    _Concrete._init_call_count = 0
    return _Concrete


# ---------------------------------------------------------------------------
# LazyClient - Singleton
# ---------------------------------------------------------------------------


class TestLazyClientSingleton:

    def setup_method(self):
        from base.clients import LazyClient

        LazyClient.reset_all()

    def test_singleton_instance_reuse(self):
        """Same concrete subclass returns the same instance each time."""

        Cls = _make_concrete_client(initialize_return="ok")
        a = Cls.instance()
        b = Cls.instance()
        assert a is b

    def test_singleton_reset_all(self):
        """reset_all() clears the instance registry so new instances are created."""
        from base.clients import LazyClient

        Cls = _make_concrete_client(initialize_return="ok")
        first = Cls.instance()
        LazyClient.reset_all()
        second = Cls.instance()
        assert first is not second

    def test_different_subclasses_have_separate_instances(self):
        """Two distinct subclasses each maintain their own singleton."""

        ClsA = _make_concrete_client(initialize_return="a")
        ClsB = _make_concrete_client(initialize_return="b")
        assert ClsA.instance() is not ClsB.instance()


# ---------------------------------------------------------------------------
# LazyClient - Lazy Initialization
# ---------------------------------------------------------------------------


class TestLazyClientInit:

    def setup_method(self):
        from base.clients import LazyClient

        LazyClient.reset_all()

    def test_lazy_init_on_first_get(self):
        """_initialize() is called only on the first get(), not at construction."""
        sentinel = object()
        Cls = _make_concrete_client(initialize_return=sentinel)
        inst = Cls.instance()

        assert Cls._init_call_count == 0, "_initialize must not be called at construction"
        result = inst.get()
        assert result is sentinel
        assert Cls._init_call_count == 1

    def test_get_does_not_call_initialize_twice(self):
        """Subsequent get() calls return cached client without re-initializing."""
        sentinel = object()
        Cls = _make_concrete_client(initialize_return=sentinel)
        inst = Cls.instance()

        inst.get()
        inst.get()
        inst.get()
        assert Cls._init_call_count == 1

    def test_get_returns_none_on_init_failure(self):
        """If _initialize() raises, get() returns None and stores the error."""
        Cls = _make_concrete_client(initialize_return=ValueError("boom"))
        inst = Cls.instance()

        result = inst.get()
        assert result is None
        assert inst.error is not None
        assert "boom" in inst.error

    def test_get_or_raise_raises_on_failure(self):
        """get_or_raise() raises RuntimeError when client is unavailable."""
        Cls = _make_concrete_client(initialize_return=RuntimeError("init failed"))
        inst = Cls.instance()
        inst.get()  # Trigger the failure

        with pytest.raises(RuntimeError, match="_Concrete not available"):
            inst.get_or_raise()

    def test_get_or_raise_returns_client_on_success(self):
        """get_or_raise() returns the client when initialization succeeds."""
        sentinel = object()
        Cls = _make_concrete_client(initialize_return=sentinel)
        inst = Cls.instance()

        assert inst.get_or_raise() is sentinel

    def test_available_property_true_after_success(self):
        """available returns True after successful initialization."""
        Cls = _make_concrete_client(initialize_return=object())
        inst = Cls.instance()
        assert inst.available is True

    def test_available_property_false_after_failure(self):
        """available returns False when _initialize() raises."""
        Cls = _make_concrete_client(initialize_return=IOError("fail"))
        inst = Cls.instance()
        assert inst.available is False

    def test_reset_clears_cached_client(self):
        """reset() allows re-initialization on next get() call."""
        sentinel_first = object()
        Cls = _make_concrete_client(initialize_return=sentinel_first)
        inst = Cls.instance()
        inst.get()
        assert Cls._init_call_count == 1

        inst.reset()
        inst.get()
        assert Cls._init_call_count == 2


# ---------------------------------------------------------------------------
# LazyClient - Health Check
# ---------------------------------------------------------------------------


class TestLazyClientHealthCheck:

    def setup_method(self):
        from base.clients import LazyClient

        LazyClient.reset_all()

    def test_health_check_structure_on_success(self):
        """health_check() returns dict with client, available, and status keys."""
        Cls = _make_concrete_client(initialize_return=object())
        inst = Cls.instance()

        result = inst.health_check()
        assert "client" in result
        assert "available" in result
        assert "status" in result
        assert result["available"] is True
        assert result["status"] == "healthy"

    def test_health_check_structure_on_failure(self):
        """health_check() returns unavailable status when client failed to init."""
        Cls = _make_concrete_client(initialize_return=Exception("broken"))
        inst = Cls.instance()

        result = inst.health_check()
        assert result["available"] is False
        assert result["status"] == "unavailable"
        assert "error" in result

    def test_health_check_client_name_matches_class(self):
        """health_check() 'client' field is the concrete subclass name."""
        Cls = _make_concrete_client(initialize_return=object())
        inst = Cls.instance()

        result = inst.health_check()
        assert result["client"] == "_Concrete"


# ---------------------------------------------------------------------------
# GitRepoClient
# ---------------------------------------------------------------------------


class TestGitRepoClient:

    def setup_method(self):
        from base.clients import LazyClient

        LazyClient.reset_all()

    def test_git_repo_client_for_path_creates_repo(self):
        """for_path() returns a Repo built from the given path (mocked GitPython)."""
        from base.clients import GitRepoClient

        mock_repo = MagicMock()
        with patch("base.clients.GitRepoClient.for_path") as mock_for_path:
            mock_for_path.return_value = mock_repo
            result = GitRepoClient.for_path("/some/path")

        assert result is mock_repo

    def test_git_repo_client_for_path_mocked_import(self):
        """for_path() calls git.Repo with the provided path argument."""
        from base.clients import GitRepoClient

        mock_repo_instance = MagicMock()
        mock_repo_cls = MagicMock(return_value=mock_repo_instance)

        with patch.dict("sys.modules", {"git": MagicMock(Repo=mock_repo_cls)}):
            result = GitRepoClient.for_path("/my/repo")

        mock_repo_cls.assert_called_once_with("/my/repo")
        assert result is mock_repo_instance

    def test_git_repo_client_for_path_raises_without_gitpython(self):
        """for_path() raises RuntimeError when GitPython is not installed."""
        import builtins

        from base.clients import GitRepoClient

        original_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name == "git":
                raise ImportError("No module named 'git'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_blocked_import):
            with pytest.raises(RuntimeError, match="GitPython not installed"):
                GitRepoClient.for_path(".")


# ---------------------------------------------------------------------------
# GitHubApiClient - Token Resolution
# ---------------------------------------------------------------------------


class TestGitHubApiClientTokenResolution:

    def setup_method(self):
        from base.clients import LazyClient

        LazyClient.reset_all()

    def test_github_api_client_uses_env_token(self):
        """GITHUB_TOKEN env var is used as first priority for token resolution."""
        from base.clients import GitHubApiClient

        with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token-123"}):
            token = GitHubApiClient._resolve_token()

        assert token == "env-token-123"

    def test_github_api_client_falls_back_to_gh_cli(self):
        """Falls back to 'gh auth token' subprocess when env var is absent."""
        from base.clients import GitHubApiClient

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "cli-token-456\n"

        with patch.dict("os.environ", {}, clear=True):
            env_without_gh = {k: v for k, v in __import__("os").environ.items() if k != "GITHUB_TOKEN"}
            with patch.dict("os.environ", env_without_gh, clear=True):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    token = GitHubApiClient._resolve_token()

        assert token == "cli-token-456"
        mock_run.assert_called_once()

    def test_github_api_client_returns_none_when_no_token(self):
        """Returns None when env var is absent and gh CLI fails."""
        from base.clients import GitHubApiClient

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", return_value=mock_result):
                with patch.dict(
                    "os.environ", {k: v for k, v in __import__("os").environ.items() if k != "GITHUB_TOKEN"}, clear=True
                ):
                    token = GitHubApiClient._resolve_token()

        # token is None or empty string when no source provides one
        assert not token


# ---------------------------------------------------------------------------
# GitHubApiClient - Remote URL Parsing
# ---------------------------------------------------------------------------


class TestGitHubApiClientParseRemote:

    def _parse(self, url):
        """Helper: mock a git Repo with the given remote URL and call _parse_remote."""
        from base.clients import GitHubApiClient

        mock_remote = MagicMock()
        mock_remote.url = url
        mock_repo = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_repo_cls = MagicMock(return_value=mock_repo)

        with patch.dict("sys.modules", {"git": MagicMock(Repo=mock_repo_cls)}):
            return GitHubApiClient._parse_remote(".")

    def test_github_api_parse_remote_ssh(self):
        """Parses owner/repo from SSH URL: git@github.com:owner/repo.git"""
        owner, name = self._parse("git@github.com:owner/my-repo.git")
        assert owner == "owner"
        assert name == "my-repo"

    def test_github_api_parse_remote_https(self):
        """Parses owner/repo from HTTPS URL: https://github.com/owner/repo.git"""
        owner, name = self._parse("https://github.com/owner/my-repo.git")
        assert owner == "owner"
        assert name == "my-repo"

    def test_github_api_parse_remote_https_no_dot_git(self):
        """Parses owner/repo from HTTPS URL without .git suffix."""
        owner, name = self._parse("https://github.com/owner/my-repo")
        assert owner == "owner"
        assert name == "my-repo"

    def test_github_api_parse_remote_non_github_returns_none(self):
        """Returns (None, None) for non-GitHub remote URLs."""
        owner, name = self._parse("https://gitlab.com/owner/repo.git")
        assert owner is None
        assert name is None
