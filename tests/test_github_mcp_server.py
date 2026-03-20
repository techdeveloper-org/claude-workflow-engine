"""Tests for GitHub MCP Server (src/mcp/github_mcp_server.py).

Note: Most tests use mocking since GitHub API calls require authentication.
Integration tests require GITHUB_TOKEN env var.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import sys
import importlib.util

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"

def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # Register so patches work
    spec.loader.exec_module(mod)
    return mod

_gh_mod = _load_module("github_mcp_server", _MCP_DIR / "github_mcp_server.py")

github_create_issue = _gh_mod.github_create_issue
github_close_issue = _gh_mod.github_close_issue
github_add_comment = _gh_mod.github_add_comment
github_create_pr = _gh_mod.github_create_pr
github_merge_pr = _gh_mod.github_merge_pr
github_list_issues = _gh_mod.github_list_issues
github_get_pr_status = _gh_mod.github_get_pr_status

# Compatibility shims: these helpers were refactored into base.clients and base.response.
# _get_repo_info -> GitHubApiClient._parse_remote
# _get_token     -> GitHubApiClient._resolve_token
# _json          -> to_json (imported in the module as to_json)
from base.clients import GitHubApiClient as _GitHubApiClient
_get_repo_info = _GitHubApiClient._parse_remote
_get_token = _GitHubApiClient._resolve_token
_json = _gh_mod.to_json

# Stub module-level cache attributes used by TestTokenResolution to reset state.
# The caching is now inside GitHubApiClient; setting these on the module is a no-op
# but prevents AttributeError on assignment.
if not hasattr(_gh_mod, "_github_token"):
    _gh_mod._github_token = None
if not hasattr(_gh_mod, "_github_client"):
    _gh_mod._github_client = None


def _parse(result: str) -> dict:
    """Parse JSON result from MCP tool."""
    return json.loads(result)


class TestRepoDetection:
    """Tests for repository auto-detection."""

    def test_get_repo_info_from_current_dir(self):
        """Test repo detection from current git repo."""
        owner, repo_name = _get_repo_info(".")
        # Current repo is claude-insight on GitHub
        assert owner is not None
        assert repo_name is not None

    def test_get_repo_info_invalid_dir(self):
        """Test repo detection from non-git directory."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            owner, repo_name = _get_repo_info(tmpdir)
            assert owner is None
            assert repo_name is None


class TestTokenResolution:
    """Tests for GitHub token resolution."""

    def test_token_from_env(self):
        """Test token resolution from environment variable."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-123"}):
            # Reset cached token
            _gh_mod._github_token = None
            _gh_mod._github_client = None
            token = _get_token()
            assert token == "test-token-123"
            # Reset
            _gh_mod._github_token = None
            _gh_mod._github_client = None


class TestGitHubIssues:
    """Tests for issue operations (mocked)."""

    @patch("github_mcp_server._get_github_repo")
    def test_create_issue(self, mock_get_repo):
        """Test creating an issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.html_url = "https://github.com/test/repo/issues/42"
        mock_issue.created_at.isoformat.return_value = "2026-03-15T10:00:00"
        mock_repo.create_issue.return_value = mock_issue
        mock_get_repo.return_value = mock_repo

        result = _parse(github_create_issue("Test issue", "Body text", "bug,high"))
        assert result["success"] is True
        assert result["issue_number"] == 42
        assert "issue_url" in result

    @patch("github_mcp_server._get_github_repo")
    def test_close_issue(self, mock_get_repo):
        """Test closing an issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_get_repo.return_value = mock_repo

        result = _parse(github_close_issue(42, "Fixed!", "."))
        assert result["success"] is True
        assert result["issue_number"] == 42
        assert result["state"] == "closed"

    @patch("github_mcp_server._get_github_repo")
    def test_add_comment_to_issue(self, mock_get_repo):
        """Test adding comment to issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_comment = MagicMock()
        mock_comment.html_url = "https://github.com/test/repo/issues/42#comment-1"
        mock_issue.create_comment.return_value = mock_comment
        mock_repo.get_issue.return_value = mock_issue
        mock_get_repo.return_value = mock_repo

        result = _parse(github_add_comment(42, "Nice work!", "issue"))
        assert result["success"] is True
        assert result["type"] == "issue"


class TestGitHubPRs:
    """Tests for pull request operations (mocked)."""

    @patch("github_mcp_server._get_github_repo")
    def test_create_pr(self, mock_get_repo):
        """Test creating a PR."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.number = 10
        mock_pr.html_url = "https://github.com/test/repo/pull/10"
        mock_pr.created_at.isoformat.return_value = "2026-03-15T10:00:00"
        mock_repo.create_pull.return_value = mock_pr
        mock_get_repo.return_value = mock_repo

        result = _parse(github_create_pr(
            "Add MCP servers", "## Summary\nMCP integration", "feature/mcp", "main"
        ))
        assert result["success"] is True
        assert result["pr_number"] == 10

    def test_create_pr_no_head(self):
        """Test PR creation without head branch fails gracefully."""
        result = _parse(github_create_pr("Test PR", head=""))
        assert result["success"] is False
        assert "head branch" in result["error"].lower()

    @patch("github_mcp_server._get_github_repo")
    def test_get_pr_status(self, mock_get_repo):
        """Test getting PR status."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.number = 10
        mock_pr.title = "Test PR"
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False
        mock_pr.head.ref = "feature/test"
        mock_pr.base.ref = "main"
        mock_pr.head.sha = "abc123"
        mock_pr.review_comments = 2
        mock_pr.commits = 3
        mock_repo.get_pull.return_value = mock_pr

        # Mock commit status
        mock_commit = MagicMock()
        mock_commit.get_statuses.return_value = []
        mock_repo.get_commit.return_value = mock_commit

        mock_get_repo.return_value = mock_repo

        result = _parse(github_get_pr_status(10))
        assert result["success"] is True
        assert result["pr_number"] == 10
        assert result["mergeable"] is True

    @patch("github_mcp_server._get_github_repo")
    def test_merge_not_mergeable(self, mock_get_repo):
        """Test merging a non-mergeable PR."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.mergeable = False
        mock_repo.get_pull.return_value = mock_pr
        mock_get_repo.return_value = mock_repo

        result = _parse(github_merge_pr(10))
        assert result["success"] is False
        assert "not mergeable" in result["error"]


class TestJsonFormat:
    """Tests for consistent JSON response format."""

    def test_json_helper(self):
        """Test _json helper returns valid JSON."""
        result = json.loads(_json({"key": "value", "num": 42}))
        assert result["key"] == "value"
        assert result["num"] == 42
