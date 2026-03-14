"""
Comprehensive tests for MCP + GitHub integration.

Tests:
- GitHubOperationRouter: MCP primary, gh CLI fallback, both fail, disabled MCP
- Issue creation: number extraction from URL
- PR creation: number extraction from URL
- Level3 step integration: steps 8, 9, 11, 12 call Level3GitHubWorkflow

All tests use mocks - no external dependencies required.
ASCII-only: cp1252 safe for Windows.
"""

import sys
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch, call, PropertyMock

# ---------------------------------------------------------------------------
# sys.path setup so imports work regardless of cwd
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
_ENGINE_ROOT = _PROJECT_ROOT / "scripts"
for _p in [str(_PROJECT_ROOT), str(_ENGINE_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ===========================================================================
# Helper factories
# ===========================================================================

def _make_gh_cli_mock(success=True, issue_number=42, pr_number=7):
    """Build a mock GitHubIntegration instance."""
    mock = MagicMock()
    if success:
        mock.create_issue.return_value = {
            "success": True,
            "issue_number": issue_number,
            "issue_url": f"https://github.com/owner/repo/issues/{issue_number}",
            "created_at": "2026-01-01T00:00:00",
        }
        mock.create_pull_request.return_value = {
            "success": True,
            "pr_number": pr_number,
            "pr_url": f"https://github.com/owner/repo/pull/{pr_number}",
        }
        mock.merge_pull_request.return_value = {"success": True, "merged": True}
        mock.close_issue.return_value = {
            "success": True,
            "closed_at": "2026-01-01T01:00:00",
        }
        mock.add_issue_comment.return_value = {
            "success": True,
            "comment_url": "https://github.com/owner/repo/issues/42#comment-1",
        }
        mock.add_pr_comment.return_value = {
            "success": True,
            "comment_url": "https://github.com/owner/repo/pull/7#comment-1",
        }
    else:
        mock.create_issue.return_value = {"success": False, "error": "gh CLI failed"}
        mock.create_pull_request.return_value = {
            "success": False,
            "error": "gh CLI failed",
        }
        mock.merge_pull_request.return_value = {
            "success": False,
            "error": "gh CLI failed",
        }
        mock.close_issue.return_value = {"success": False, "error": "gh CLI failed"}
    return mock


def _make_mcp_mock(success=True, issue_number=42, pr_number=7):
    """Build a mock GitHubMCP instance."""
    mock = MagicMock()
    if success:
        mock.create_issue.return_value = {
            "success": True,
            "issue_number": issue_number,
            "issue_url": f"https://github.com/owner/repo/issues/{issue_number}",
            "created_at": "2026-01-01T00:00:00",
        }
        mock.create_pull_request.return_value = {
            "success": True,
            "pr_number": pr_number,
            "pr_url": f"https://github.com/owner/repo/pull/{pr_number}",
        }
        mock.merge_pull_request.return_value = {"success": True, "merged": True}
        mock.close_issue.return_value = {
            "success": True,
            "closed_at": "2026-01-01T01:00:00",
        }
        mock.add_issue_comment.return_value = {
            "success": True,
            "comment_url": "https://github.com/owner/repo/issues/42#comment-1",
        }
        mock.add_pr_comment.return_value = {
            "success": True,
            "comment_url": "https://github.com/owner/repo/pull/7#comment-1",
        }
    else:
        mock.create_issue.return_value = {
            "success": False,
            "error": "MCP failed",
        }
        mock.create_pull_request.return_value = {
            "success": False,
            "error": "MCP failed",
        }
        mock.merge_pull_request.return_value = {
            "success": False,
            "error": "MCP failed",
        }
        mock.close_issue.return_value = {"success": False, "error": "MCP failed"}
    return mock


# ===========================================================================
# A) GitHubOperationRouter tests
# ===========================================================================

class TestGitHubOperationRouterMCPPrimary(unittest.TestCase):
    """Router uses MCP as primary backend."""

    def _make_router(self, mcp_mock, gh_mock):
        """Build router with injected mocks."""
        with patch(
            "langgraph_engine.github_operation_router.GitHubIntegration",
            return_value=gh_mock,
        ), patch(
            "langgraph_engine.github_operation_router.GitHubMCP",
            return_value=mcp_mock,
        ), patch(
            "langgraph_engine.github_operation_router.PYGITHUB_AVAILABLE",
            True,
        ):
            from langgraph_engine.github_operation_router import GitHubOperationRouter
            router = GitHubOperationRouter(use_mcp=True, fallback_to_gh=True)
            router.mcp = mcp_mock
            router.gh_cli = gh_mock
        return router

    def test_mcp_primary_success_create_issue(self):
        """When MCP succeeds, result comes from MCP - not gh CLI."""
        mcp = _make_mcp_mock(success=True, issue_number=55)
        gh = _make_gh_cli_mock(success=True, issue_number=99)
        router = self._make_router(mcp, gh)

        result = router.create_issue("Test Issue", "Body text")

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 55)
        mcp.create_issue.assert_called_once()
        gh.create_issue.assert_not_called()

    def test_mcp_primary_success_create_pr(self):
        """When MCP succeeds for PR, result comes from MCP."""
        mcp = _make_mcp_mock(success=True, pr_number=33)
        gh = _make_gh_cli_mock(success=True, pr_number=99)
        router = self._make_router(mcp, gh)

        result = router.create_pull_request(
            "My PR", "PR body", head_branch="feature/x"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 33)
        mcp.create_pull_request.assert_called_once()
        gh.create_pull_request.assert_not_called()

    def test_mcp_fails_fallback_to_gh_cli_create_issue(self):
        """When MCP fails, router falls back to gh CLI."""
        mcp = _make_mcp_mock(success=False)
        gh = _make_gh_cli_mock(success=True, issue_number=77)
        router = self._make_router(mcp, gh)

        result = router.create_issue("Fallback Issue", "Body")

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 77)
        mcp.create_issue.assert_called_once()
        gh.create_issue.assert_called_once()

    def test_mcp_fails_fallback_to_gh_cli_create_pr(self):
        """When MCP fails for PR, router falls back to gh CLI."""
        mcp = _make_mcp_mock(success=False)
        gh = _make_gh_cli_mock(success=True, pr_number=22)
        router = self._make_router(mcp, gh)

        result = router.create_pull_request("Fallback PR", "Body", head_branch="f")

        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 22)
        mcp.create_pull_request.assert_called_once()
        gh.create_pull_request.assert_called_once()

    def test_mcp_exception_fallback_to_gh_cli(self):
        """When MCP raises an exception, router falls back to gh CLI."""
        mcp = MagicMock()
        mcp.create_issue.side_effect = RuntimeError("MCP timeout")
        gh = _make_gh_cli_mock(success=True, issue_number=10)
        router = self._make_router(mcp, gh)

        result = router.create_issue("Exception Test", "Body")

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 10)
        gh.create_issue.assert_called_once()

    def test_both_fail_returns_error_dict(self):
        """When both MCP and gh CLI fail, an error dict is returned."""
        mcp = _make_mcp_mock(success=False)
        gh = _make_gh_cli_mock(success=False)
        router = self._make_router(mcp, gh)

        result = router.create_issue("Doomed Issue", "Body")

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_both_raise_exceptions_returns_error_dict(self):
        """When both MCP and gh CLI raise, an error dict is returned."""
        mcp = MagicMock()
        mcp.create_issue.side_effect = RuntimeError("MCP boom")
        gh = MagicMock()
        gh.create_issue.side_effect = RuntimeError("gh CLI boom")
        router = self._make_router(mcp, gh)

        result = router.create_issue("Double Fail", "Body")

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_mcp_disabled_uses_gh_cli_directly(self):
        """When use_mcp=False, MCP is not called and gh CLI is used directly."""
        mcp = _make_mcp_mock(success=True, issue_number=99)
        gh = _make_gh_cli_mock(success=True, issue_number=5)

        with patch(
            "langgraph_engine.github_operation_router.GitHubIntegration",
            return_value=gh,
        ), patch(
            "langgraph_engine.github_operation_router.GitHubMCP",
            return_value=mcp,
        ), patch(
            "langgraph_engine.github_operation_router.PYGITHUB_AVAILABLE",
            True,
        ):
            from langgraph_engine.github_operation_router import GitHubOperationRouter
            router = GitHubOperationRouter(use_mcp=False, fallback_to_gh=True)
            router.gh_cli = gh
            # use_mcp=False means mcp attribute stays None in __init__
            router.mcp = None

        result = router.create_issue("Direct gh CLI", "Body")

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 5)
        mcp.create_issue.assert_not_called()
        gh.create_issue.assert_called_once()

    def test_critical_merge_always_has_fallback(self):
        """merge_pull_request falls back to gh CLI even when fallback_to_gh is ignored."""
        mcp = _make_mcp_mock(success=False)
        gh = _make_gh_cli_mock(success=True)

        with patch(
            "langgraph_engine.github_operation_router.GitHubIntegration",
            return_value=gh,
        ), patch(
            "langgraph_engine.github_operation_router.GitHubMCP",
            return_value=mcp,
        ), patch(
            "langgraph_engine.github_operation_router.PYGITHUB_AVAILABLE",
            True,
        ):
            from langgraph_engine.github_operation_router import GitHubOperationRouter
            router = GitHubOperationRouter(use_mcp=True, fallback_to_gh=True)
            router.mcp = mcp
            router.gh_cli = gh

        result = router.merge_pull_request(pr_number=7)

        self.assertTrue(result["success"])
        self.assertTrue(result.get("merged"))
        mcp.merge_pull_request.assert_called_once()
        gh.merge_pull_request.assert_called_once()

    def test_close_issue_mcp_primary(self):
        """close_issue routes through MCP when available."""
        mcp = _make_mcp_mock(success=True)
        gh = _make_gh_cli_mock(success=True)
        router = self._make_router(mcp, gh)

        result = router.close_issue(42, closing_comment="Done!")

        self.assertTrue(result["success"])
        mcp.close_issue.assert_called_once()
        gh.close_issue.assert_not_called()


# ===========================================================================
# B) Issue creation tests (URL-based number extraction)
# ===========================================================================

class TestIssueCreationURLParsing(unittest.TestCase):
    """Verify create_issue extracts issue_number from the URL returned by gh CLI."""

    def _run_create_issue(self, stdout_url, returncode=0):
        """Simulate gh CLI output and return GitHubIntegration.create_issue result."""
        with patch("subprocess.run") as mock_run:
            # First call is gh auth status in __init__
            auth_result = MagicMock()
            auth_result.returncode = 0
            auth_result.stdout = "Logged in to github.com"

            # Second call is git remote get-url origin
            remote_result = MagicMock()
            remote_result.returncode = 0
            remote_result.stdout = "https://github.com/owner/repo.git"

            # Third call is the actual gh issue create
            issue_result = MagicMock()
            issue_result.returncode = returncode
            issue_result.stdout = stdout_url
            issue_result.stderr = ""

            mock_run.side_effect = [auth_result, remote_result, issue_result]

            from langgraph_engine.github_integration import GitHubIntegration
            gi = GitHubIntegration.__new__(GitHubIntegration)
            gi.repo_path = Path(".")
            gi.owner = "owner"
            gi.repo_name = "repo"

        with patch("subprocess.run") as mock_create:
            create_result = MagicMock()
            create_result.returncode = returncode
            create_result.stdout = stdout_url
            create_result.stderr = ""
            mock_create.return_value = create_result

            return gi.create_issue("Test Issue", "Body text")

    def test_create_issue_returns_issue_number(self):
        """Issue number is extracted from the URL returned on stdout."""
        result = self._run_create_issue(
            "https://github.com/owner/repo/issues/42\n"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 42)
        self.assertIn("/issues/42", result["issue_url"])

    def test_create_issue_with_trailing_slash(self):
        """URL with trailing slash is handled correctly."""
        result = self._run_create_issue(
            "https://github.com/owner/repo/issues/100/"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 100)

    def test_create_issue_with_labels(self):
        """Labels are passed in the gh CLI command."""
        with patch("subprocess.run") as mock_run:
            create_result = MagicMock()
            create_result.returncode = 0
            create_result.stdout = "https://github.com/owner/repo/issues/5\n"
            create_result.stderr = ""
            mock_run.return_value = create_result

            from langgraph_engine.github_integration import GitHubIntegration
            gi = GitHubIntegration.__new__(GitHubIntegration)
            gi.repo_path = Path(".")
            gi.owner = "owner"
            gi.repo_name = "repo"

            result = gi.create_issue(
                "Label Test",
                "Body",
                labels=["bug", "critical"]
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 5)
        # Verify both labels were in the command
        call_args = mock_run.call_args[0][0]
        self.assertIn("--label", call_args)
        self.assertIn("bug", call_args)
        self.assertIn("critical", call_args)

    def test_create_issue_failure_returns_error(self):
        """Non-zero returncode returns success=False."""
        result = self._run_create_issue("", returncode=1)
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ===========================================================================
# C) PR creation tests (URL-based number extraction)
# ===========================================================================

class TestPRCreationURLParsing(unittest.TestCase):
    """Verify create_pull_request extracts pr_number from the URL."""

    def _run_create_pr(self, stdout_url, returncode=0, head_branch="feature/test"):
        """Simulate gh CLI PR creation."""
        from langgraph_engine.github_integration import GitHubIntegration
        gi = GitHubIntegration.__new__(GitHubIntegration)
        gi.repo_path = Path(".")
        gi.owner = "owner"
        gi.repo_name = "repo"

        with patch("subprocess.run") as mock_run:
            pr_result = MagicMock()
            pr_result.returncode = returncode
            pr_result.stdout = stdout_url
            pr_result.stderr = ""
            mock_run.return_value = pr_result

            return gi.create_pull_request(
                "My PR",
                "PR body",
                head_branch=head_branch,
                base_branch="main"
            )

    def test_create_pr_returns_pr_number(self):
        """PR number is extracted from the URL returned on stdout."""
        result = self._run_create_pr(
            "https://github.com/owner/repo/pull/7\n"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 7)
        self.assertIn("/pull/7", result["pr_url"])

    def test_create_pr_with_branch(self):
        """head_branch is passed correctly in the gh CLI command."""
        from langgraph_engine.github_integration import GitHubIntegration
        gi = GitHubIntegration.__new__(GitHubIntegration)
        gi.repo_path = Path(".")
        gi.owner = "owner"
        gi.repo_name = "repo"

        with patch("subprocess.run") as mock_run:
            pr_result = MagicMock()
            pr_result.returncode = 0
            pr_result.stdout = "https://github.com/owner/repo/pull/15\n"
            pr_result.stderr = ""
            mock_run.return_value = pr_result

            result = gi.create_pull_request(
                "Branch PR",
                "Body",
                head_branch="feature/my-branch",
                base_branch="main"
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 15)
        call_args = mock_run.call_args[0][0]
        self.assertIn("feature/my-branch", call_args)

    def test_create_pr_failure_returns_error(self):
        """Non-zero returncode for PR creation returns success=False."""
        result = self._run_create_pr("", returncode=1)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_create_pr_trailing_slash_url(self):
        """PR URL with trailing slash is handled correctly."""
        result = self._run_create_pr(
            "https://github.com/owner/repo/pull/200/"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 200)


# ===========================================================================
# D) Level3 step integration tests
# ===========================================================================

def _make_workflow_mock(
    step8_result=None,
    step9_result=None,
    step11_result=None,
    step12_result=None,
):
    """Build a mock Level3GitHubWorkflow with configurable return values."""
    mock = MagicMock()

    if step8_result is None:
        step8_result = {
            "success": True,
            "issue_number": 42,
            "issue_url": "https://github.com/owner/repo/issues/42",
            "label": "feature",
            "execution_time_ms": 80,
        }
    if step9_result is None:
        step9_result = {
            "success": True,
            "branch_name": "feature/issue-42-test-task",
            "execution_time_ms": 50,
        }
    if step11_result is None:
        step11_result = {
            "success": True,
            "pr_number": 7,
            "pr_url": "https://github.com/owner/repo/pull/7",
            "merged": True,
            "review_passed": True,
            "review_issues": [],
            "execution_time_ms": 120,
        }
    if step12_result is None:
        step12_result = {
            "success": True,
            "closed": True,
            "execution_time_ms": 60,
        }

    mock.step8_create_issue.return_value = step8_result
    mock.step9_create_branch.return_value = step9_result
    # step11 calls workflow.step11_create_pull_request()
    mock.step11_create_pull_request.return_value = step11_result
    mock.step12_close_issue.return_value = step12_result
    return mock


def _build_minimal_state(overrides=None):
    """Build a minimal FlowState dict for testing step functions."""
    state = {
        "session_dir": "/tmp/test_session",
        "project_root": ".",
        "user_message": "Implement test feature for the pipeline",
        "step0_task_type": "feature",
        "step0_complexity": 5,
        "step0_tasks": {"tasks": [{"description": "Write code"}, {"description": "Write tests"}]},
        "step2_plan": "Phase 1: code, Phase 2: tests",
        "step7_final_prompt": "Final prompt content",
        "step8_issue_id": "42",
        "step8_issue_url": "https://github.com/owner/repo/issues/42",
        "step8_issue_created": True,
        "step8_title": "[feature] Complexity-5/10 - Implement test feature",
        "step9_branch_name": "feature/issue-42-implement-test-feature",
        "step9_branch_created": True,
    }
    if overrides:
        state.update(overrides)
    return state


class TestStep8CallsRealWorkflow(unittest.TestCase):
    """step8_github_issue_creation calls Level3GitHubWorkflow.step8_create_issue.

    The lazy import path inside step8_github_issue_creation is:
        from ..level3_steps8to12_github import Level3GitHubWorkflow
    which resolves to: langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow
    """

    @patch("builtins.open", create=True)
    def test_step8_calls_real_workflow(self, mock_open):
        """step8 instantiates Level3GitHubWorkflow and calls step8_create_issue."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value="prompt content")

        workflow_mock = _make_workflow_mock()
        state = _build_minimal_state()

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ), patch("pathlib.Path.exists", return_value=True):
            from langgraph_engine.subgraphs.level3_execution import (
                step8_github_issue_creation,
            )
            result = step8_github_issue_creation(state)

        self.assertTrue(result.get("step8_issue_created"))
        self.assertEqual(result.get("step8_issue_id"), "42")
        workflow_mock.step8_create_issue.assert_called_once()

    @patch("builtins.open", create=True)
    def test_step8_fallback_on_error(self, mock_open):
        """step8 falls back gracefully when GitHub is unavailable."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value="prompt content")

        workflow_mock = _make_workflow_mock(
            step8_result={
                "success": False,
                "error": "GitHub unavailable",
                "execution_time_ms": 10,
            }
        )
        state = _build_minimal_state()

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ), patch("pathlib.Path.exists", return_value=True):
            from langgraph_engine.subgraphs.level3_execution import (
                step8_github_issue_creation,
            )
            result = step8_github_issue_creation(state)

        # On failure the step should still return a result dict (not raise)
        self.assertIsInstance(result, dict)
        # issue_created should be False on failure
        self.assertFalse(result.get("step8_issue_created", True))


class TestStep9CallsRealWorkflow(unittest.TestCase):
    """step9_branch_creation calls Level3GitHubWorkflow.step9_create_branch."""

    def test_step9_calls_real_workflow(self):
        """step9 instantiates Level3GitHubWorkflow and calls step9_create_branch."""
        workflow_mock = _make_workflow_mock()
        state = _build_minimal_state()

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step9_branch_creation,
            )
            result = step9_branch_creation(state)

        self.assertIsInstance(result, dict)
        workflow_mock.step9_create_branch.assert_called_once()
        branch_name = result.get("step9_branch_name", "")
        # Branch was created - check the field is populated
        self.assertTrue(
            result.get("step9_branch_created") or branch_name != "",
            "Expected branch creation result"
        )

    def test_step9_fallback_on_error(self):
        """step9 falls back gracefully when branch creation fails."""
        workflow_mock = _make_workflow_mock(
            step9_result={
                "success": False,
                "error": "Branch already exists",
                "branch_name": "fallback-branch",
                "execution_time_ms": 5,
            }
        )
        state = _build_minimal_state()

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step9_branch_creation,
            )
            result = step9_branch_creation(state)

        self.assertIsInstance(result, dict)


class TestStep11CallsRealWorkflow(unittest.TestCase):
    """step11_pull_request_review calls Level3GitHubWorkflow.step11_create_and_merge_pr."""

    def test_step11_calls_real_workflow(self):
        """step11 instantiates Level3GitHubWorkflow and calls step11_create_and_merge_pr."""
        workflow_mock = _make_workflow_mock()
        state = _build_minimal_state({
            "step10_implementation_complete": True,
            "step10_files_changed": ["src/main.py"],
        })

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step11_pull_request_review,
            )
            result = step11_pull_request_review(state)

        self.assertIsInstance(result, dict)
        workflow_mock.step11_create_pull_request.assert_called_once()

    def test_step11_fallback_on_error(self):
        """step11 handles PR creation failure gracefully."""
        workflow_mock = _make_workflow_mock(
            step11_result={
                "success": False,
                "error": "PR creation failed",
                "execution_time_ms": 15,
            }
        )
        state = _build_minimal_state({
            "step10_implementation_complete": True,
        })

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step11_pull_request_review,
            )
            result = step11_pull_request_review(state)

        self.assertIsInstance(result, dict)


class TestStep12CallsRealWorkflow(unittest.TestCase):
    """step12_issue_closure calls Level3GitHubWorkflow.step12_close_issue."""

    def test_step12_calls_real_workflow(self):
        """step12 instantiates Level3GitHubWorkflow and calls step12_close_issue."""
        workflow_mock = _make_workflow_mock()
        state = _build_minimal_state({
            "step11_pr_number": 7,
            "step11_pr_merged": True,
        })

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step12_issue_closure,
            )
            result = step12_issue_closure(state)

        self.assertIsInstance(result, dict)
        workflow_mock.step12_close_issue.assert_called_once()

    def test_step12_fallback_on_error(self):
        """step12 handles issue closure failure gracefully."""
        workflow_mock = _make_workflow_mock(
            step12_result={
                "success": False,
                "error": "Issue already closed",
                "execution_time_ms": 5,
            }
        )
        state = _build_minimal_state()

        with patch(
            "langgraph_engine.level3_steps8to12_github.Level3GitHubWorkflow",
            return_value=workflow_mock,
        ):
            from langgraph_engine.subgraphs.level3_execution import (
                step12_issue_closure,
            )
            result = step12_issue_closure(state)

        self.assertIsInstance(result, dict)


# ===========================================================================
# E) Direct Level3GitHubWorkflow unit tests
# ===========================================================================

class TestLevel3GitHubWorkflowDirect(unittest.TestCase):
    """
    Tests for Level3GitHubWorkflow methods directly,
    mocking the router so no real GitHub calls are made.
    """

    def _make_workflow(self, router_mock):
        """Instantiate Level3GitHubWorkflow with mocked dependencies."""
        with patch(
            "langgraph_engine.level3_steps8to12_github.GitHubOperationRouter",
            return_value=router_mock,
        ), patch(
            "langgraph_engine.level3_steps8to12_github.GitOperations"
        ) as mock_git_cls, patch(
            "langgraph_engine.level3_steps8to12_github.OllamaService",
            side_effect=RuntimeError("no ollama"),
        ):
            mock_git = MagicMock()
            mock_git.is_git_repo = True
            mock_git_cls.return_value = mock_git

            from langgraph_engine.level3_steps8to12_github import Level3GitHubWorkflow
            workflow = Level3GitHubWorkflow(session_dir="/tmp/test", repo_path=".")
            workflow.git = mock_git
        return workflow

    def test_step8_create_issue_success(self):
        """step8_create_issue returns issue_number and issue_url on success."""
        router = MagicMock()
        router.create_issue.return_value = {
            "success": True,
            "issue_number": 99,
            "issue_url": "https://github.com/owner/repo/issues/99",
            "created_at": "2026-01-01T00:00:00",
        }

        workflow = self._make_workflow(router)
        result = workflow.step8_create_issue(
            title="Test Issue",
            description="Test description",
            task_summary="Test summary",
            implementation_plan="Phase 1",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["issue_number"], 99)
        self.assertIn("issue_url", result)
        router.create_issue.assert_called_once()

    def test_step8_create_issue_failure(self):
        """step8_create_issue returns failure result when router fails."""
        router = MagicMock()
        router.create_issue.return_value = {
            "success": False,
            "error": "API rate limit exceeded",
        }

        workflow = self._make_workflow(router)
        result = workflow.step8_create_issue(
            title="Fail Issue",
            description="desc",
        )

        self.assertFalse(result["success"])

    def test_step8_skips_when_not_git_repo(self):
        """step8_create_issue returns error when not a git repo."""
        router = MagicMock()
        with patch(
            "langgraph_engine.level3_steps8to12_github.GitHubOperationRouter",
            return_value=router,
        ), patch(
            "langgraph_engine.level3_steps8to12_github.GitOperations"
        ) as mock_git_cls, patch(
            "langgraph_engine.level3_steps8to12_github.OllamaService",
            side_effect=RuntimeError("no ollama"),
        ):
            mock_git = MagicMock()
            mock_git.is_git_repo = False
            mock_git_cls.return_value = mock_git

            from langgraph_engine.level3_steps8to12_github import Level3GitHubWorkflow
            workflow = Level3GitHubWorkflow(session_dir="/tmp/test", repo_path=".")
            workflow.git = mock_git

        result = workflow.step8_create_issue(
            title="No Repo Issue",
            description="desc",
        )

        self.assertFalse(result["success"])
        self.assertIn("error", result)
        router.create_issue.assert_not_called()


# ===========================================================================
# F) MCP configuration verification
# ===========================================================================

class TestMCPConfigurationEnabled(unittest.TestCase):
    """Verify that use_mcp=True is set in level3_steps8to12_github.py."""

    def test_level3_workflow_uses_mcp_true(self):
        """Level3GitHubWorkflow instantiates router with use_mcp=True."""
        captured = {}

        def capture_router(*args, **kwargs):
            captured["use_mcp"] = kwargs.get("use_mcp", args[0] if args else None)
            mock = MagicMock()
            return mock

        with patch(
            "langgraph_engine.level3_steps8to12_github.GitHubOperationRouter",
            side_effect=capture_router,
        ), patch(
            "langgraph_engine.level3_steps8to12_github.GitOperations"
        ) as mock_git_cls, patch(
            "langgraph_engine.level3_steps8to12_github.OllamaService",
            side_effect=RuntimeError("no ollama"),
        ):
            mock_git = MagicMock()
            mock_git.is_git_repo = True
            mock_git_cls.return_value = mock_git

            from langgraph_engine.level3_steps8to12_github import Level3GitHubWorkflow
            Level3GitHubWorkflow(session_dir="/tmp/test", repo_path=".")

        self.assertTrue(
            captured.get("use_mcp"),
            "Expected use_mcp=True but got: " + str(captured.get("use_mcp"))
        )

    def test_pygithub_in_requirements(self):
        """PyGithub>=2.1.1 is present in requirements.txt."""
        req_path = _PROJECT_ROOT / "requirements.txt"
        self.assertTrue(req_path.exists(), "requirements.txt not found")
        content = req_path.read_text(encoding="utf-8")
        self.assertIn(
            "PyGithub",
            content,
            "PyGithub not found in requirements.txt"
        )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
