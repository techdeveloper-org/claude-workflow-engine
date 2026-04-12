"""
GitHub Operation Router - Hybrid MCP + gh CLI with intelligent fallback.

Routes all GitHub operations to:
1. PRIMARY: GitHub MCP (PyGithub) - Fast (~50-100ms)
2. FALLBACK: gh CLI (subprocess) - Reliable fallback

Features:
- 100% compatible with GitHubIntegration API
- Automatic fallback on MCP errors
- Logging for debugging and metrics
- Feature flags for progressive rollout
- ZERO breaking changes to existing code

Used by: level3_steps8to12_github.py, github_issue_manager.py, github_pr_workflow.py
Replaces: Direct GitHubIntegration usage
"""

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from langgraph_engine.github_integration import GitHubIntegration

try:
    from langgraph_engine.github_mcp import PYGITHUB_AVAILABLE, GitHubMCP
except ImportError:
    PYGITHUB_AVAILABLE = False
    logger.warning("[Router] github_mcp module not available")


class GitHubOperationRouter:
    """
    Routes GitHub operations to MCP or gh CLI with intelligent fallback.

    Interface: 100% compatible with GitHubIntegration
    Performance: 3-5x faster when MCP works
    Safety: Always has gh CLI fallback
    """

    def __init__(
        self, use_mcp: bool = True, fallback_to_gh: bool = True, token: Optional[str] = None, repo_path: str = "."
    ):
        """
        Initialize GitHub Operation Router.

        Args:
            use_mcp: Enable MCP (PyGithub) as primary backend
            fallback_to_gh: Use gh CLI as fallback (recommended: True)
            token: GitHub PAT for MCP (optional, checks GITHUB_TOKEN env var)
            repo_path: Local repository path
        """
        self.use_mcp = use_mcp
        self.fallback_to_gh = fallback_to_gh
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.repo_path = repo_path

        # Initialize MCP if enabled
        self.mcp = None
        if use_mcp and PYGITHUB_AVAILABLE:
            try:
                self.mcp = GitHubMCP(token=self.token, repo_path=repo_path)
                logger.info("[Router] GitHub MCP initialized (primary backend)")
            except Exception as e:
                logger.warning(f"[Router] MCP initialization failed: {e}")
                self.mcp = None
                if not fallback_to_gh:
                    raise RuntimeError("MCP initialization failed and fallback disabled")

        # Always initialize gh CLI as fallback
        try:
            self.gh_cli = GitHubIntegration(repo_path=repo_path)
            logger.info("[Router] gh CLI initialized (fallback backend)")
        except Exception as e:
            logger.error(f"[Router] gh CLI initialization failed: {e}")
            self.gh_cli = None

    # ===== ISSUE OPERATIONS =====

    def create_issue(
        self, title: str, body: str = "", labels: Optional[List[str]] = None, assignee: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a GitHub issue (MCP primary, gh CLI fallback).

        Returns:
            {
                "success": bool,
                "issue_number": int,
                "issue_url": str,
                "created_at": str
            }
        """
        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] create_issue: trying MCP (primary)")
                result = self.mcp.create_issue(title, body, labels, assignee)
                if result.get("success"):
                    logger.info(f"[Router] create_issue: MCP succeeded (#{result['issue_number']})")
                    return result
                else:
                    logger.warning(f"[Router] create_issue: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] create_issue: MCP error, {e}")

        # Fallback to gh CLI
        if self.fallback_to_gh and self.gh_cli:
            try:
                logger.info("[Router] create_issue: falling back to gh CLI")
                result = self.gh_cli.create_issue(title, body, labels, assignee)
                if result.get("success"):
                    logger.info(f"[Router] create_issue: gh CLI succeeded (#{result['issue_number']})")
                else:
                    logger.error(f"[Router] create_issue: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] create_issue: gh CLI error, {e}")
                return {"success": False, "error": str(e)}

        # No backends available
        return {"success": False, "error": "No GitHub backend available"}

    def add_issue_comment(self, issue_number: int, comment: str) -> Dict[str, Any]:
        """
        Add a comment to an issue (MCP primary, gh CLI fallback).

        Returns:
            {"success": bool, "comment_url": str}
        """
        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] add_issue_comment: trying MCP (primary)")
                result = self.mcp.add_issue_comment(issue_number, comment)
                if result.get("success"):
                    logger.info("[Router] add_issue_comment: MCP succeeded")
                    return result
                else:
                    logger.warning(f"[Router] add_issue_comment: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] add_issue_comment: MCP error, {e}")

        # Fallback to gh CLI
        if self.fallback_to_gh and self.gh_cli:
            try:
                logger.info("[Router] add_issue_comment: falling back to gh CLI")
                result = self.gh_cli.add_issue_comment(issue_number, comment)
                if result.get("success"):
                    logger.info("[Router] add_issue_comment: gh CLI succeeded")
                else:
                    logger.error(f"[Router] add_issue_comment: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] add_issue_comment: gh CLI error, {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "No GitHub backend available"}

    def close_issue(self, issue_number: int, closing_comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Close a GitHub issue (MCP primary, gh CLI fallback).

        Returns:
            {"success": bool, "closed_at": str}
        """
        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] close_issue: trying MCP (primary)")
                result = self.mcp.close_issue(issue_number, closing_comment)
                if result.get("success"):
                    logger.info("[Router] close_issue: MCP succeeded")
                    return result
                else:
                    logger.warning(f"[Router] close_issue: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] close_issue: MCP error, {e}")

        # Fallback to gh CLI
        if self.fallback_to_gh and self.gh_cli:
            try:
                logger.info("[Router] close_issue: falling back to gh CLI")
                result = self.gh_cli.close_issue(issue_number, closing_comment)
                if result.get("success"):
                    logger.info("[Router] close_issue: gh CLI succeeded")
                else:
                    logger.error(f"[Router] close_issue: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] close_issue: gh CLI error, {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "No GitHub backend available"}

    # ===== PULL REQUEST OPERATIONS =====

    def create_pull_request(
        self,
        title: str,
        body: str = "",
        head_branch: str = None,
        base_branch: str = "main",
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a pull request (MCP primary, gh CLI fallback).

        Returns:
            {
                "success": bool,
                "pr_number": int,
                "pr_url": str
            }
        """
        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] create_pull_request: trying MCP (primary)")
                result = self.mcp.create_pull_request(title, body, head_branch, base_branch, labels)
                if result.get("success"):
                    logger.info(f"[Router] create_pull_request: MCP succeeded (#{result['pr_number']})")
                    return result
                else:
                    logger.warning(f"[Router] create_pull_request: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] create_pull_request: MCP error, {e}")

        # Fallback to gh CLI
        if self.fallback_to_gh and self.gh_cli:
            try:
                logger.info("[Router] create_pull_request: falling back to gh CLI")
                result = self.gh_cli.create_pull_request(title, body, head_branch, base_branch, labels)
                if result.get("success"):
                    logger.info(f"[Router] create_pull_request: gh CLI succeeded (#{result['pr_number']})")
                else:
                    logger.error(f"[Router] create_pull_request: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] create_pull_request: gh CLI error, {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "No GitHub backend available"}

    def merge_pull_request(
        self, pr_number: int, commit_message: Optional[str] = None, delete_branch: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a pull request (CRITICAL: MCP primary, gh CLI fallback).

        IMPORTANT: This is a destructive operation. Always has fallback protection.

        Returns:
            {"success": bool, "merged": bool}
        """
        logger.warning(f"[Router] merge_pull_request: CRITICAL destructive operation on PR #{pr_number}")

        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] merge_pull_request: trying MCP (primary)")
                result = self.mcp.merge_pull_request(pr_number, commit_message, delete_branch)
                if result.get("success"):
                    logger.warning(f"[Router] merge_pull_request: MCP succeeded (PR #{pr_number} merged)")
                    return result
                else:
                    logger.warning(f"[Router] merge_pull_request: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] merge_pull_request: MCP error, {e}")

        # Fallback to gh CLI (MANDATORY for critical operation)
        if self.gh_cli:
            try:
                logger.info("[Router] merge_pull_request: falling back to gh CLI (CRITICAL)")
                result = self.gh_cli.merge_pull_request(pr_number, commit_message, delete_branch)
                if result.get("success"):
                    logger.warning(f"[Router] merge_pull_request: gh CLI succeeded (PR #{pr_number} merged)")
                else:
                    logger.error(f"[Router] merge_pull_request: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] merge_pull_request: gh CLI error (CRITICAL), {e}")
                return {"success": False, "error": str(e)}

        # No fallback available - this is critical
        error_msg = "No GitHub backend available for critical merge operation"
        logger.error(f"[Router] merge_pull_request: {error_msg}")
        return {"success": False, "error": error_msg}

    def add_pr_comment(self, pr_number: int, comment: str) -> Dict[str, Any]:
        """
        Add a comment to a pull request (MCP primary, gh CLI fallback).

        Returns:
            {"success": bool, "comment_url": str}
        """
        # Try MCP first
        if self.use_mcp and self.mcp:
            try:
                logger.info("[Router] add_pr_comment: trying MCP (primary)")
                result = self.mcp.add_pr_comment(pr_number, comment)
                if result.get("success"):
                    logger.info("[Router] add_pr_comment: MCP succeeded")
                    return result
                else:
                    logger.warning(f"[Router] add_pr_comment: MCP failed, {result.get('error')}")
            except Exception as e:
                logger.warning(f"[Router] add_pr_comment: MCP error, {e}")

        # Fallback to gh CLI
        if self.fallback_to_gh and self.gh_cli:
            try:
                logger.info("[Router] add_pr_comment: falling back to gh CLI")
                result = self.gh_cli.add_pr_comment(pr_number, comment)
                if result.get("success"):
                    logger.info("[Router] add_pr_comment: gh CLI succeeded")
                else:
                    logger.error(f"[Router] add_pr_comment: gh CLI failed, {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[Router] add_pr_comment: gh CLI error, {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "No GitHub backend available"}
