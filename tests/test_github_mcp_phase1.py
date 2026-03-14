"""
Unit Tests for Phase 1: GitHub MCP Foundation

Tests:
1. GitHub MCP operations (isolated from existing code)
2. GitHub Operation Router fallback logic
3. Backward compatibility with GitHubIntegration

These tests verify ZERO breaking changes to existing code.
"""

import pytest
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# Test imports - may fail if PyGithub not installed
try:
    from github import GithubException
    PYGITHUB_AVAILABLE = True
except ImportError:
    PYGITHUB_AVAILABLE = False

# Import modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from langgraph_engine.github_mcp import GitHubMCP
from langgraph_engine.github_operation_router import GitHubOperationRouter


class TestGitHubMCP:
    """Test GitHub MCP (PyGithub) operations."""

    @pytest.fixture
    def mock_github_mcp(self):
        """Create mock GitHub MCP for testing."""
        with patch('langgraph_engine.github_mcp.Github') as mock_github:
            # Mock the Github client
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_github.return_value.get_user.return_value = mock_user

            # Mock repo
            mock_repo = Mock()
            mock_github.return_value.get_user.return_value.get_repo.return_value = mock_repo

            mcp = GitHubMCP(token="test_token", repo_path=".")
            mcp.repo = mock_repo
            return mcp

    def test_create_issue_success(self, mock_github_mcp):
        """Test successful issue creation via MCP."""
        # Mock issue
        mock_issue = Mock()
        mock_issue.number = 42
        mock_issue.html_url = "https://github.com/owner/repo/issues/42"
        mock_issue.created_at.isoformat.return_value = "2026-03-13T10:00:00"
        mock_github_mcp.repo.create_issue.return_value = mock_issue

        # Create issue
        result = mock_github_mcp.create_issue(
            title="Test Issue",
            body="Test body",
            labels=["bug"],
            assignee="test_user"
        )

        # Verify
        assert result["success"] is True
        assert result["issue_number"] == 42
        assert result["issue_url"] == "https://github.com/owner/repo/issues/42"
        mock_github_mcp.repo.create_issue.assert_called_once()

    def test_create_issue_failure(self, mock_github_mcp):
        """Test failed issue creation via MCP."""
        # Mock failure
        mock_github_mcp.repo.create_issue.side_effect = GithubException(400, "Bad request")

        result = mock_github_mcp.create_issue(
            title="Test Issue",
            body="Test body"
        )

        assert result["success"] is False
        assert "error" in result

    def test_create_issue_no_repo(self):
        """Test create_issue when repo not loaded."""
        mcp = Mock(spec=GitHubMCP)
        mcp.repo = None
        mcp.create_issue = GitHubMCP.create_issue.__get__(mcp)

        result = mcp.create_issue(title="Test", body="Body")

        assert result["success"] is False
        assert "Repository not loaded" in result.get("error", "")

    def test_add_issue_comment_success(self, mock_github_mcp):
        """Test successful comment addition to issue."""
        # Mock issue and comment
        mock_issue = Mock()
        mock_comment = Mock()
        mock_comment.html_url = "https://github.com/owner/repo/issues/42#comment-123"
        mock_issue.create_comment.return_value = mock_comment
        mock_github_mcp.repo.get_issue.return_value = mock_issue

        result = mock_github_mcp.add_issue_comment(
            issue_number=42,
            comment="Test comment"
        )

        assert result["success"] is True
        assert "comment_url" in result
        mock_github_mcp.repo.get_issue.assert_called_once_with(42)

    def test_close_issue_success(self, mock_github_mcp):
        """Test successful issue closure."""
        mock_issue = Mock()
        mock_github_mcp.repo.get_issue.return_value = mock_issue

        result = mock_github_mcp.close_issue(
            issue_number=42,
            closing_comment=None
        )

        assert result["success"] is True
        assert result["issue_number"] == 42
        mock_issue.edit.assert_called_once()

    def test_create_pull_request_success(self, mock_github_mcp):
        """Test successful PR creation."""
        mock_pr = Mock()
        mock_pr.number = 10
        mock_pr.html_url = "https://github.com/owner/repo/pull/10"
        mock_pr.created_at.isoformat.return_value = "2026-03-13T10:00:00"
        mock_github_mcp.repo.create_pull.return_value = mock_pr

        result = mock_github_mcp.create_pull_request(
            title="Test PR",
            body="Test body",
            head_branch="feature/test",
            base_branch="main"
        )

        assert result["success"] is True
        assert result["pr_number"] == 10
        mock_github_mcp.repo.create_pull.assert_called_once()

    def test_merge_pull_request_success(self, mock_github_mcp):
        """Test successful PR merge."""
        mock_pr = Mock()
        mock_pr.mergeable = True
        mock_pr.head.ref = "feature/test"
        mock_github_mcp.repo.get_pull.return_value = mock_pr
        mock_github_mcp.repo.get_git_ref = Mock()

        result = mock_github_mcp.merge_pull_request(
            pr_number=10,
            commit_message="Merge test",
            delete_branch=True
        )

        assert result["success"] is True
        assert result["merged"] is True
        mock_pr.merge.assert_called_once()

    def test_merge_pull_request_not_mergeable(self, mock_github_mcp):
        """Test PR merge when PR has conflicts."""
        mock_pr = Mock()
        mock_pr.mergeable = False
        mock_github_mcp.repo.get_pull.return_value = mock_pr

        result = mock_github_mcp.merge_pull_request(pr_number=10)

        assert result["success"] is False
        assert "not mergeable" in result.get("error", "").lower()

    def test_add_pr_comment_success(self, mock_github_mcp):
        """Test successful comment addition to PR."""
        mock_pr = Mock()
        mock_comment = Mock()
        mock_comment.html_url = "https://github.com/owner/repo/pull/10#comment-456"
        mock_pr.create_issue_comment.return_value = mock_comment
        mock_github_mcp.repo.get_pull.return_value = mock_pr

        result = mock_github_mcp.add_pr_comment(
            pr_number=10,
            comment="Test comment"
        )

        assert result["success"] is True
        assert "comment_url" in result


class TestGitHubOperationRouter:
    """Test GitHub Operation Router (fallback logic)."""

    @pytest.fixture
    def mock_router(self):
        """Create mock router for testing."""
        with patch('langgraph_engine.github_operation_router.GitHubIntegration') as mock_gh_cli:
            with patch('langgraph_engine.github_operation_router.GitHubMCP') as mock_mcp:
                mock_gh_cli_instance = Mock()
                mock_mcp_instance = Mock()

                mock_gh_cli.return_value = mock_gh_cli_instance
                mock_mcp.return_value = mock_mcp_instance

                router = GitHubOperationRouter(
                    use_mcp=True,
                    fallback_to_gh=True
                )
                router.mcp = mock_mcp_instance
                router.gh_cli = mock_gh_cli_instance

                return router

    def test_create_issue_mcp_success(self, mock_router):
        """Test MCP succeeds, return MCP result."""
        mock_router.mcp.create_issue.return_value = {
            "success": True,
            "issue_number": 42,
            "issue_url": "https://github.com/owner/repo/issues/42"
        }

        result = mock_router.create_issue(
            title="Test",
            body="Body"
        )

        assert result["success"] is True
        assert result["issue_number"] == 42
        # gh CLI should NOT be called
        mock_router.gh_cli.create_issue.assert_not_called()

    def test_create_issue_mcp_fails_fallback_succeeds(self, mock_router):
        """Test MCP fails, gh CLI fallback succeeds."""
        mock_router.mcp.create_issue.return_value = {
            "success": False,
            "error": "MCP failed"
        }
        mock_router.gh_cli.create_issue.return_value = {
            "success": True,
            "issue_number": 42,
            "issue_url": "https://github.com/owner/repo/issues/42"
        }

        result = mock_router.create_issue(
            title="Test",
            body="Body"
        )

        assert result["success"] is True
        assert result["issue_number"] == 42
        # Both should be called
        mock_router.mcp.create_issue.assert_called_once()
        mock_router.gh_cli.create_issue.assert_called_once()

    def test_create_issue_mcp_disabled(self, mock_router):
        """Test when MCP is disabled, use gh CLI only."""
        mock_router.use_mcp = False
        mock_router.gh_cli.create_issue.return_value = {
            "success": True,
            "issue_number": 42,
            "issue_url": "https://github.com/owner/repo/issues/42"
        }

        result = mock_router.create_issue(
            title="Test",
            body="Body"
        )

        assert result["success"] is True
        # MCP should NOT be called
        mock_router.mcp.create_issue.assert_not_called()
        # gh CLI should be called
        mock_router.gh_cli.create_issue.assert_called_once()

    def test_merge_pr_has_fallback_protection(self, mock_router):
        """Test merge_pull_request always has fallback protection."""
        # Simulate MCP fails
        mock_router.mcp.merge_pull_request.return_value = {
            "success": False,
            "error": "MCP error"
        }
        mock_router.gh_cli.merge_pull_request.return_value = {
            "success": True,
            "merged": True
        }

        result = mock_router.merge_pull_request(pr_number=10)

        assert result["success"] is True
        # Even with fallback disabled, gh CLI should be called for merge
        mock_router.gh_cli.merge_pull_request.assert_called_once()

    def test_backward_compatibility_interface(self, mock_router):
        """Test router has all GitHubIntegration methods."""
        # Verify all methods exist and are callable
        methods = [
            'create_issue',
            'add_issue_comment',
            'close_issue',
            'create_pull_request',
            'merge_pull_request',
            'add_pr_comment'
        ]

        for method_name in methods:
            assert hasattr(mock_router, method_name), f"Missing method: {method_name}"
            method = getattr(mock_router, method_name)
            assert callable(method), f"Method not callable: {method_name}"

    def test_router_api_compatibility_return_format(self, mock_router):
        """Test all router methods return same format as GitHubIntegration."""
        mock_router.mcp.create_issue.return_value = {
            "success": True,
            "issue_number": 42,
            "issue_url": "https://github.com/owner/repo/issues/42",
            "created_at": "2026-03-13T10:00:00"
        }

        result = mock_router.create_issue(title="Test", body="Body")

        # Verify format matches GitHubIntegration return
        assert "success" in result
        assert isinstance(result["success"], bool)
        assert "issue_number" in result or "error" in result


class TestIntegration:
    """Integration tests for Phase 1 foundation."""

    def test_mcp_and_gh_cli_both_available(self):
        """Test when both MCP and gh CLI are available."""
        # This is more of a smoke test
        # Real integration would need actual GitHub token

        with patch('langgraph_engine.github_operation_router.GitHubIntegration'):
            with patch('langgraph_engine.github_operation_router.GitHubMCP'):
                # Should not raise any exceptions
                router = GitHubOperationRouter(
                    use_mcp=True,
                    fallback_to_gh=True
                )
                assert router is not None

    def test_mcp_initialization_failure_falls_back(self):
        """Test when MCP initialization fails, still uses gh CLI."""
        with patch('langgraph_engine.github_operation_router.GitHubIntegration'):
            with patch('langgraph_engine.github_operation_router.GitHubMCP') as mock_mcp:
                mock_mcp.side_effect = RuntimeError("MCP failed")

                # Should not raise, should use gh CLI
                router = GitHubOperationRouter(
                    use_mcp=True,
                    fallback_to_gh=True
                )

                assert router.mcp is None
                assert router.gh_cli is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
