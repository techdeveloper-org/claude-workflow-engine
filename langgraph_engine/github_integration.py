"""
GitHub Integration - gh CLI wrapper for Level 3 automation.

Provides:
- Issue creation with labels and description
- Pull request creation and merge
- Issue closure with comments
- GitHub metadata tracking

Uses: gh CLI (GitHub CLI) - already authenticated via keyring
No need for GITHUB_TOKEN environment variable!
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class GitHubIntegration:
    """Manages GitHub operations for Level 3 automation using gh CLI."""

    def __init__(self, token: Optional[str] = None, repo_path: str = "."):
        """
        Initialize GitHub integration.

        Args:
            token: (Ignored) gh CLI uses keyring authentication automatically
            repo_path: Local repository path (for git operations)
        """
        self.repo_path = Path(repo_path)

        # Verify gh CLI is available
        try:
            result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("gh CLI not authenticated. Run: gh auth login")
            logger.info("[x] gh CLI authenticated and ready")
        except FileNotFoundError:
            raise RuntimeError("gh CLI not installed. Install from: https://cli.github.com")
        except Exception as e:
            raise RuntimeError(f"gh CLI error: {e}")

        # Get repo info from git remote
        self.owner, self.repo_name = self._get_repo_info()

    def _get_repo_info(self) -> tuple:
        """Get owner and repo name from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise RuntimeError("Cannot get git remote URL")

            remote_url = result.stdout.strip()

            # Parse owner/repo from URL
            if "github.com" not in remote_url:
                raise RuntimeError(f"Not a GitHub repository: {remote_url}")

            if remote_url.startswith("git@"):
                # git@github.com:owner/repo.git
                parts = remote_url.split(":")[-1].replace(".git", "").split("/")
            else:
                # https://github.com/owner/repo.git
                parts = remote_url.rstrip("/").replace(".git", "").split("/")[-2:]

            owner, repo_name = parts[0], parts[1]
            logger.info(f"[x] Repository detected: {owner}/{repo_name}")
            return owner, repo_name

        except Exception as e:
            logger.error(f"Cannot detect repository: {e}")
            return None, None

    # ===== ISSUE OPERATIONS =====

    def create_issue(
        self, title: str, body: str = "", labels: Optional[List[str]] = None, assignee: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a GitHub issue using gh CLI.

        Args:
            title: Issue title
            body: Issue description (markdown supported)
            labels: List of label names (e.g., ["bug", "critical"])
            assignee: Username to assign to (optional)

        Returns:
            {
                "success": bool,
                "issue_number": int,
                "issue_url": str,
                "created_at": str
            }
        """
        if not self.owner or not self.repo_name:
            logger.error("No repository configured")
            return {"success": False, "error": "No repository"}

        logger.info(f"Creating issue: {title[:50]}...")

        try:
            cmd = [
                "gh",
                "issue",
                "create",
                "--repo",
                f"{self.owner}/{self.repo_name}",
                "--title",
                title,
                "--body",
                body,
            ]

            # Add labels if provided
            if labels:
                for label in labels:
                    cmd.extend(["--label", label])

            # Add assignee if provided
            if assignee:
                cmd.extend(["--assignee", assignee])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Issue creation failed: {error_msg}")
                return {"success": False, "error": error_msg}

            # gh issue create outputs the issue URL on stdout
            issue_url = result.stdout.strip()

            # Extract issue number from URL (e.g., https://github.com/owner/repo/issues/42)
            issue_number = None
            if "/issues/" in issue_url:
                try:
                    issue_number = int(issue_url.rstrip("/").split("/")[-1])
                except ValueError:
                    pass

            logger.info(f"Issue created: #{issue_number}")

            return {
                "success": True,
                "issue_number": issue_number,
                "issue_url": issue_url,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Issue creation failed: {e}")
            return {"success": False, "error": str(e)}

    def add_issue_comment(self, issue_number: int, comment: str) -> Dict[str, Any]:
        """
        Add a comment to an issue using gh CLI.

        Args:
            issue_number: GitHub issue number
            comment: Comment text (markdown supported)

        Returns:
            {"success": bool, "comment_url": str}
        """
        if not self.owner or not self.repo_name:
            return {"success": False, "error": "No repository"}

        logger.info(f"Adding comment to issue #{issue_number}")

        try:
            cmd = [
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                f"{self.owner}/{self.repo_name}",
                "--body",
                comment,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Comment failed: {error_msg}")
                return {"success": False, "error": error_msg}

            logger.info(f"[x] Comment added to issue #{issue_number}")

            return {
                "success": True,
                "comment_url": f"https://github.com/{self.owner}/{self.repo_name}/issues/{issue_number}",
            }

        except Exception as e:
            logger.error(f"Comment failed: {e}")
            return {"success": False, "error": str(e)}

    def close_issue(self, issue_number: int, closing_comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Close a GitHub issue using gh CLI.

        Args:
            issue_number: GitHub issue number
            closing_comment: Optional comment to add before closing

        Returns:
            {"success": bool, "closed_at": str}
        """
        if not self.owner or not self.repo_name:
            return {"success": False, "error": "No repository"}

        logger.info(f"Closing issue #{issue_number}")

        try:
            # Add closing comment if provided
            if closing_comment:
                comment_result = self.add_issue_comment(issue_number, closing_comment)
                if not comment_result.get("success"):
                    logger.warning(f"Could not add closing comment: {comment_result.get('error')}")

            # Close the issue
            cmd = ["gh", "issue", "close", str(issue_number), "--repo", f"{self.owner}/{self.repo_name}"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Issue closure failed: {error_msg}")
                return {"success": False, "error": error_msg}

            logger.info(f"[x] Issue #{issue_number} closed")

            return {"success": True, "issue_number": issue_number, "closed_at": datetime.now().isoformat()}

        except Exception as e:
            logger.error(f"Issue closure failed: {e}")
            return {"success": False, "error": str(e)}

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
        Create a pull request using gh CLI.

        Args:
            title: PR title
            body: PR description (markdown)
            head_branch: Source branch
            base_branch: Target branch (default: main)
            labels: List of label names

        Returns:
            {
                "success": bool,
                "pr_number": int,
                "pr_url": str
            }
        """
        if not self.owner or not self.repo_name:
            return {"success": False, "error": "No repository"}

        if not head_branch:
            logger.error("head_branch required")
            return {"success": False, "error": "head_branch required"}

        logger.info(f"Creating PR: {title[:50]}...")

        try:
            cmd = [
                "gh",
                "pr",
                "create",
                "--repo",
                f"{self.owner}/{self.repo_name}",
                "--head",
                head_branch,
                "--base",
                base_branch,
                "--title",
                title,
                "--body",
                body,
            ]

            # Add labels if provided
            if labels:
                for label in labels:
                    cmd.extend(["--label", label])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"PR creation failed: {error_msg}")
                return {"success": False, "error": error_msg}

            # gh pr create outputs the PR URL on stdout
            pr_url = result.stdout.strip()

            # Extract PR number from URL (e.g., https://github.com/owner/repo/pull/5)
            pr_number = None
            if "/pull/" in pr_url:
                try:
                    pr_number = int(pr_url.rstrip("/").split("/")[-1])
                except ValueError:
                    pass

            logger.info(f"PR created: #{pr_number}")

            return {"success": True, "pr_number": pr_number, "pr_url": pr_url, "created_at": datetime.now().isoformat()}

        except Exception as e:
            logger.error(f"PR creation failed: {e}")
            return {"success": False, "error": str(e)}

    def merge_pull_request(
        self, pr_number: int, commit_message: Optional[str] = None, delete_branch: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a pull request using gh CLI.

        Args:
            pr_number: PR number
            commit_message: Custom merge commit message
            delete_branch: Delete source branch after merge

        Returns:
            {"success": bool, "merged": bool}
        """
        if not self.owner or not self.repo_name:
            return {"success": False, "error": "No repository"}

        logger.info(f"Merging PR #{pr_number}")

        try:
            cmd = [
                "gh",
                "pr",
                "merge",
                str(pr_number),
                "--repo",
                f"{self.owner}/{self.repo_name}",
                "--squash",  # Squash commits
            ]

            if commit_message:
                cmd.extend(["--body", commit_message])

            if delete_branch:
                cmd.append("--delete-branch")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"PR merge failed: {error_msg}")
                return {"success": False, "error": error_msg}

            logger.info(f"[x] PR #{pr_number} merged")

            return {"success": True, "merged": True}

        except Exception as e:
            logger.error(f"PR merge failed: {e}")
            return {"success": False, "error": str(e)}

    def add_pr_comment(self, pr_number: int, comment: str) -> Dict[str, Any]:
        """Add a comment to a pull request using gh CLI."""
        if not self.owner or not self.repo_name:
            return {"success": False, "error": "No repository"}

        logger.info(f"Adding comment to PR #{pr_number}")

        try:
            cmd = ["gh", "pr", "comment", str(pr_number), "--repo", f"{self.owner}/{self.repo_name}", "--body", comment]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"PR comment failed: {error_msg}")
                return {"success": False, "error": error_msg}

            return {
                "success": True,
                "comment_url": f"https://github.com/{self.owner}/{self.repo_name}/pull/{pr_number}",
            }

        except Exception as e:
            logger.error(f"PR comment failed: {e}")
            return {"success": False, "error": str(e)}
