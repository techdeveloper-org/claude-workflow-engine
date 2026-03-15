"""
GitHub Facade - Simplified interface for all GitHub + Git operations.

Hides the complexity of MCP vs CLI routing, retry logic, and error handling
behind a clean, typed API.  Callers use GitHubFacade and never need to
interact with GitHubOperationRouter or GitOperations directly.

Design decisions:
- All methods return typed dataclass results, never raw dicts.
- All errors are caught internally; methods return success/failure objects
  and never raise exceptions to the caller.
- Operations are logged for an audit trail via loguru.
- Internally delegates to GitHubOperationRouter for all GitHub API calls
  (which itself handles MCP-primary / gh-CLI-fallback routing).
- Internally delegates to GitOperations for all local git commands.

Usage:
    from langgraph_engine.github_facade import GitHubFacade

    facade = GitHubFacade(repo_path="/path/to/repo")

    issue = facade.create_issue("Fix login bug", "Steps to reproduce...", ["bug"])
    if issue.success:
        print(f"Created #{issue.number} at {issue.url}")

    branch = facade.create_branch(f"issue-{issue.number}-fix-login", from_branch="main")
    pushed = facade.push_branch(branch.name)
    pr = facade.create_pr("Fix login bug", "Closes #42", branch.name, "main")
    merged = facade.merge_pr(pr.number)
    closed = facade.close_issue(issue.number, comment="Fixed in PR #" + str(pr.number))
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger

from .github_operation_router import GitHubOperationRouter
from .git_operations import GitOperations


# ---------------------------------------------------------------------------
# Typed result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class IssueResult:
    """Result returned by create_issue."""
    success: bool
    number: Optional[int] = None
    url: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class PRResult:
    """Result returned by create_pr."""
    success: bool
    number: Optional[int] = None
    url: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class MergeResult:
    """Result returned by merge_pr."""
    success: bool
    merged: bool = False
    error: Optional[str] = None


@dataclass
class BranchResult:
    """Result returned by create_branch."""
    success: bool
    name: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PushResult:
    """Result returned by push_branch."""
    success: bool
    branch: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# GitHubFacade
# ---------------------------------------------------------------------------

class GitHubFacade:
    """Simplified interface for all GitHub + Git operations.

    Hides MCP vs CLI routing, retry logic, and error handling.
    All methods return typed dataclass objects and never raise.
    """

    def __init__(
        self,
        repo_path: str = ".",
        token: Optional[str] = None,
        use_mcp: bool = True,
    ) -> None:
        """Initialise the facade.

        Args:
            repo_path: Absolute (or relative) path to the local git repository.
            token:     Optional GitHub PAT.  Falls back to GITHUB_TOKEN env var.
            use_mcp:   When True, try PyGithub MCP first and fall back to gh CLI.
        """
        self._repo_path = repo_path
        self._token = token or os.getenv("GITHUB_TOKEN")

        # GitHub API layer (MCP-primary, gh-CLI-fallback)
        try:
            self._router = GitHubOperationRouter(
                use_mcp=use_mcp,
                fallback_to_gh=True,
                token=self._token,
                repo_path=repo_path,
            )
            logger.info("[GitHubFacade] GitHubOperationRouter initialised")
        except Exception as exc:
            logger.error(f"[GitHubFacade] Router init failed: {exc}")
            self._router = None  # type: ignore[assignment]

        # Local git layer
        try:
            self._git = GitOperations(repo_path=repo_path)
            logger.info("[GitHubFacade] GitOperations initialised")
        except Exception as exc:
            logger.error(f"[GitHubFacade] GitOperations init failed: {exc}")
            self._git = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Issue operations
    # ------------------------------------------------------------------

    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
    ) -> IssueResult:
        """Create a GitHub issue.

        Args:
            title:    Issue title.
            body:     Issue body (markdown supported).
            labels:   Label names to apply.
            assignee: Username to assign.

        Returns:
            IssueResult with success flag, issue number, and URL.
        """
        logger.info(f"[GitHubFacade] create_issue: {title[:60]!r}")

        if self._router is None:
            return IssueResult(success=False, error="GitHub router not available")

        try:
            raw = self._router.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignee=assignee,
            )
            if raw.get("success"):
                logger.info(f"[GitHubFacade] create_issue OK -> #{raw.get('issue_number')}")
                return IssueResult(
                    success=True,
                    number=raw.get("issue_number"),
                    url=raw.get("issue_url"),
                    created_at=raw.get("created_at"),
                )
            err = raw.get("error", "Unknown error")
            logger.warning(f"[GitHubFacade] create_issue failed: {err}")
            return IssueResult(success=False, error=err)
        except Exception as exc:
            logger.error(f"[GitHubFacade] create_issue exception: {exc}")
            return IssueResult(success=False, error=str(exc))

    def close_issue(
        self,
        issue_number: int,
        comment: Optional[str] = None,
    ) -> bool:
        """Close a GitHub issue, optionally adding a comment first.

        Args:
            issue_number: The issue to close.
            comment:      Optional comment to post before closing.

        Returns:
            True when the issue was closed successfully, False otherwise.
        """
        logger.info(f"[GitHubFacade] close_issue #{issue_number}")

        if self._router is None:
            logger.error("[GitHubFacade] close_issue: router not available")
            return False

        try:
            raw = self._router.close_issue(issue_number, closing_comment=comment)
            if raw.get("success"):
                logger.info(f"[GitHubFacade] close_issue #{issue_number} OK")
                return True
            logger.warning(f"[GitHubFacade] close_issue #{issue_number} failed: {raw.get('error')}")
            return False
        except Exception as exc:
            logger.error(f"[GitHubFacade] close_issue exception: {exc}")
            return False

    # ------------------------------------------------------------------
    # Pull-request operations
    # ------------------------------------------------------------------

    def create_pr(
        self,
        title: str,
        body: str = "",
        head: str = "",
        base: str = "main",
        labels: Optional[List[str]] = None,
    ) -> PRResult:
        """Create a pull request.

        Args:
            title:  PR title.
            body:   PR description (markdown).
            head:   Source branch name.
            base:   Target branch name (default: main).
            labels: Label names to apply.

        Returns:
            PRResult with success flag, PR number, and URL.
        """
        logger.info(f"[GitHubFacade] create_pr: {title[:60]!r} ({head} -> {base})")

        if self._router is None:
            return PRResult(success=False, error="GitHub router not available")

        if not head:
            return PRResult(success=False, error="head branch name is required")

        try:
            raw = self._router.create_pull_request(
                title=title,
                body=body,
                head_branch=head,
                base_branch=base,
                labels=labels or [],
            )
            if raw.get("success"):
                logger.info(f"[GitHubFacade] create_pr OK -> #{raw.get('pr_number')}")
                return PRResult(
                    success=True,
                    number=raw.get("pr_number"),
                    url=raw.get("pr_url"),
                    created_at=raw.get("created_at"),
                )
            err = raw.get("error", "Unknown error")
            logger.warning(f"[GitHubFacade] create_pr failed: {err}")
            return PRResult(success=False, error=err)
        except Exception as exc:
            logger.error(f"[GitHubFacade] create_pr exception: {exc}")
            return PRResult(success=False, error=str(exc))

    def merge_pr(
        self,
        pr_number: int,
        commit_message: Optional[str] = None,
        delete_branch: bool = True,
    ) -> MergeResult:
        """Merge an open pull request.

        Args:
            pr_number:      PR number to merge.
            commit_message: Optional custom merge commit message.
            delete_branch:  Delete source branch after merge (default: True).

        Returns:
            MergeResult with success and merged flags.
        """
        logger.info(f"[GitHubFacade] merge_pr #{pr_number}")

        if self._router is None:
            return MergeResult(success=False, merged=False, error="GitHub router not available")

        try:
            raw = self._router.merge_pull_request(
                pr_number=pr_number,
                commit_message=commit_message,
                delete_branch=delete_branch,
            )
            if raw.get("success"):
                logger.info(f"[GitHubFacade] merge_pr #{pr_number} OK")
                return MergeResult(success=True, merged=bool(raw.get("merged", True)))
            err = raw.get("error", "Unknown error")
            logger.warning(f"[GitHubFacade] merge_pr #{pr_number} failed: {err}")
            return MergeResult(success=False, merged=False, error=err)
        except Exception as exc:
            logger.error(f"[GitHubFacade] merge_pr exception: {exc}")
            return MergeResult(success=False, merged=False, error=str(exc))

    # ------------------------------------------------------------------
    # Branch / git operations
    # ------------------------------------------------------------------

    def create_branch(
        self,
        name: str,
        from_branch: str = "main",
    ) -> BranchResult:
        """Create a new local-and-remote git branch.

        Args:
            name:        New branch name.
            from_branch: Base branch to branch off from (default: main).

        Returns:
            BranchResult with success flag and branch name.
        """
        logger.info(f"[GitHubFacade] create_branch {name!r} from {from_branch!r}")

        if self._git is None:
            return BranchResult(success=False, error="Git operations not available")

        try:
            raw = self._git.create_branch(branch_name=name, from_branch=from_branch)
            if raw.get("success"):
                logger.info(f"[GitHubFacade] create_branch {name!r} OK")
                return BranchResult(success=True, name=raw.get("branch", name))
            err = raw.get("error", "Unknown error")
            logger.warning(f"[GitHubFacade] create_branch {name!r} failed: {err}")
            return BranchResult(success=False, error=err)
        except Exception as exc:
            logger.error(f"[GitHubFacade] create_branch exception: {exc}")
            return BranchResult(success=False, error=str(exc))

    def push_branch(
        self,
        branch_name: str,
        force: bool = False,
    ) -> bool:
        """Push a local branch to the remote origin.

        Args:
            branch_name: Branch to push.
            force:       Force-push (use with extreme caution).

        Returns:
            True when push succeeded, False otherwise.
        """
        logger.info(f"[GitHubFacade] push_branch {branch_name!r}")

        if self._git is None:
            logger.error("[GitHubFacade] push_branch: git operations not available")
            return False

        try:
            raw = self._git.push_to_remote(branch=branch_name, force=force)
            if raw.get("success"):
                logger.info(f"[GitHubFacade] push_branch {branch_name!r} OK")
                return True
            logger.warning(f"[GitHubFacade] push_branch {branch_name!r} failed: {raw.get('error')}")
            return False
        except Exception as exc:
            logger.error(f"[GitHubFacade] push_branch exception: {exc}")
            return False
