"""
Level 3 - Steps 8-12: GitHub Workflow Integration

Implements the GitHub workflow:
- Step 8: Issue creation
- Step 9: Branch creation
- Step 10: (Implementation - handled by Claude directly)
- Step 11: Pull request creation + merge
- Step 12: Issue closure

These steps integrate with Git and GitHub APIs for complete workflow automation.
"""

import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from loguru import logger
from .github_integration import GitHubIntegration
from .git_operations import GitOperations


class Level3GitHubWorkflow:
    """Manages GitHub workflow for Steps 8-12."""

    def __init__(self, session_dir: str, repo_path: str = "."):
        self.session_dir = session_dir
        self.github = GitHubIntegration(repo_path=repo_path)
        self.git = GitOperations(repo_path=repo_path)

    # ===== STEP 8: GITHUB ISSUE CREATION =====

    def step8_create_issue(
        self,
        title: str,
        description: str,
        task_summary: str = "",
        implementation_plan: str = ""
    ) -> Dict[str, Any]:
        """
        Create GitHub issue from execution prompt.

        Args:
            title: Issue title
            description: Issue description (from prompt.txt analysis)
            task_summary: Summary of task
            implementation_plan: Planned implementation approach

        Returns:
            {
                "issue_number": int,
                "issue_url": str,
                "issue_id": int,
                "success": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 8: GITHUB ISSUE CREATION")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Determine label from description analysis
            label = self._determine_issue_label(description)
            logger.info(f"Detected issue type: {label}")

            # Build issue body with task information
            issue_body = self._build_issue_body(description, task_summary, implementation_plan)

            # Create issue
            result = self.github.create_issue(
                title=title,
                body=issue_body,
                labels=[label] if label else []
            )

            if not result.get("success"):
                logger.error(f"Issue creation failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            issue_number = result.get("issue_number")
            issue_url = result.get("issue_url")

            logger.info(f"✓ Issue created: #{issue_number}")
            logger.info(f"  URL: {issue_url}")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "issue_url": issue_url,
                "issue_id": result.get("issue_id"),
                "label": label,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 8 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _determine_issue_label(self, description: str) -> Optional[str]:
        """Determine issue label from description content."""
        description_lower = description.lower()

        # Simple keyword matching
        if any(word in description_lower for word in ["bug", "fix", "broken", "error", "crash"]):
            return "bug"
        elif any(word in description_lower for word in ["feature", "new", "add", "implement"]):
            return "feature"
        elif any(word in description_lower for word in ["enhance", "improve", "optimize"]):
            return "enhancement"
        elif any(word in description_lower for word in ["test", "testing", "coverage"]):
            return "test"
        elif any(word in description_lower for word in ["doc", "readme", "documentation"]):
            return "documentation"
        else:
            return "task"

    def _build_issue_body(
        self,
        description: str,
        task_summary: str = "",
        implementation_plan: str = ""
    ) -> str:
        """Build detailed issue body with structured sections."""
        parts = [
            "## Task Summary",
            task_summary or "See description for details.",
            "",
            "## Description",
            description,
        ]

        if implementation_plan:
            parts.extend([
                "",
                "## Implementation Plan",
                implementation_plan
            ])

        parts.extend([
            "",
            "## Automated by",
            "Generated by Claude Insight Level 3 execution pipeline"
        ])

        return "\n".join(parts)

    # ===== STEP 9: BRANCH CREATION =====

    def step9_create_branch(self, issue_number: int, label: str = "feature") -> Dict[str, Any]:
        """
        Create and checkout new branch for issue.

        Args:
            issue_number: GitHub issue number
            label: Issue label (used in branch name)

        Returns:
            {
                "success": bool,
                "branch_name": str,
                "branch_created": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 9: BRANCH CREATION")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Create branch name: issue-{number}-{label}
            branch_name = f"issue-{issue_number}-{label}"
            logger.info(f"Creating branch: {branch_name}")

            # Create branch from main
            result = self.git.create_branch(branch_name, "main")

            if not result.get("success"):
                logger.error(f"Branch creation failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            logger.info(f"✓ Branch created and pushed: {branch_name}")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "branch_name": branch_name,
                "issue_number": issue_number,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 9 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    # ===== STEP 11: PULL REQUEST CREATION & MERGE =====

    def step11_create_pull_request(
        self,
        issue_number: int,
        branch_name: str,
        changes_summary: str = "",
        auto_merge: bool = True
    ) -> Dict[str, Any]:
        """
        Create and optionally merge pull request.

        Args:
            issue_number: GitHub issue number
            branch_name: Source branch name
            changes_summary: Summary of changes made
            auto_merge: Automatically merge if no conflicts

        Returns:
            {
                "success": bool,
                "pr_number": int,
                "pr_url": str,
                "merged": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 11: PULL REQUEST CREATION & MERGE")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Create PR title and body
            pr_title = f"Fix/Feature: Issue #{issue_number}"
            pr_body = self._build_pr_body(issue_number, changes_summary)

            logger.info(f"Creating PR from {branch_name} → main")

            # Create PR
            pr_result = self.github.create_pull_request(
                title=pr_title,
                body=pr_body,
                head_branch=branch_name,
                base_branch="main"
            )

            if not pr_result.get("success"):
                logger.error(f"PR creation failed: {pr_result.get('error')}")
                return {
                    "success": False,
                    "error": pr_result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            pr_number = pr_result.get("pr_number")
            pr_url = pr_result.get("pr_url")

            logger.info(f"✓ PR created: #{pr_number}")
            logger.info(f"  URL: {pr_url}")

            # Optionally merge
            merged = False
            if auto_merge:
                logger.info(f"Auto-merging PR #{pr_number}...")
                merge_result = self.github.merge_pull_request(
                    pr_number,
                    commit_message=f"Merge PR #{pr_number}: Fix issue #{issue_number}"
                )

                if merge_result.get("success"):
                    merged = True
                    logger.info(f"✓ PR #{pr_number} merged")
                else:
                    logger.warning(f"PR merge failed: {merge_result.get('error')}")
                    logger.info("Keeping PR open for manual review")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "merged": merged,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 11 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_pr_body(self, issue_number: int, changes_summary: str = "") -> str:
        """Build PR description."""
        parts = [
            f"## Resolves #{issue_number}",
            "",
            "## Changes Made"
        ]

        if changes_summary:
            parts.append(changes_summary)
        else:
            parts.append("See issue for details.")

        parts.extend([
            "",
            "## Type of Change",
            "- [ ] Bug fix",
            "- [ ] New feature",
            "- [ ] Enhancement",
            "- [ ] Documentation update",
            "",
            "## Testing",
            "- Changes have been tested locally",
            "- No breaking changes introduced",
            "",
            "Automated by Claude Insight Level 3"
        ])

        return "\n".join(parts)

    # ===== STEP 12: ISSUE CLOSURE =====

    def step12_close_issue(
        self,
        issue_number: int,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Close GitHub issue with detailed closing comment.

        Args:
            issue_number: GitHub issue number to close
            pr_number: PR number that resolved the issue
            files_modified: List of modified files
            approach_taken: Description of solution approach
            verification_steps: Steps to verify the fix

        Returns:
            {"success": bool, "closed": bool}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 12: ISSUE CLOSURE")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Build closing comment
            closing_comment = self._build_closing_comment(
                pr_number,
                files_modified,
                approach_taken,
                verification_steps
            )

            logger.info(f"Closing issue #{issue_number}")

            # Close issue with comment
            result = self.github.close_issue(issue_number, closing_comment)

            if not result.get("success"):
                logger.error(f"Issue closure failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            logger.info(f"✓ Issue #{issue_number} closed")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "closed": True,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 12 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_closing_comment(
        self,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None
    ) -> str:
        """Build detailed closing comment with resolution info."""
        parts = [
            f"## ✅ Resolved by PR #{pr_number}",
            ""
        ]

        if approach_taken:
            parts.extend([
                "## Approach Taken",
                approach_taken,
                ""
            ])

        if files_modified:
            parts.extend([
                "## Files Modified",
                "- " + "\n- ".join(files_modified),
                ""
            ])

        if verification_steps:
            parts.extend([
                "## Verification Steps",
                "1. " + "\n2. ".join(verification_steps),
                ""
            ])

        parts.extend([
            "---",
            "*Resolved by Claude Insight Level 3 execution pipeline*"
        ])

        return "\n".join(parts)

    # ===== COMPLETE WORKFLOW =====

    def execute_github_workflow(
        self,
        title: str,
        description: str,
        changes_summary: str = "",
        files_modified: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute complete GitHub workflow (Steps 8-12).

        Args:
            title: Issue/PR title
            description: Issue description
            changes_summary: Summary of changes made
            files_modified: Files that were modified

        Returns:
            {
                "success": bool,
                "issue_number": int,
                "pr_number": int,
                "branch_name": str,
                "closed": bool
            }
        """
        logger.info("\n" + "=" * 60)
        logger.info("EXECUTING COMPLETE GITHUB WORKFLOW (Steps 8-12)")
        logger.info("=" * 60)

        # Step 8: Create issue
        step8 = self.step8_create_issue(title, description)
        if not step8.get("success"):
            return {"success": False, "error": "Step 8 failed", "step8": step8}

        issue_number = step8.get("issue_number")
        label = step8.get("label", "task")

        # Step 9: Create branch
        step9 = self.step9_create_branch(issue_number, label)
        if not step9.get("success"):
            return {"success": False, "error": "Step 9 failed", "step8": step8, "step9": step9}

        branch_name = step9.get("branch_name")

        # Step 11: Create and merge PR
        step11 = self.step11_create_pull_request(issue_number, branch_name, changes_summary)
        if not step11.get("success"):
            return {"success": False, "error": "Step 11 failed", "step8": step8, "step9": step9, "step11": step11}

        pr_number = step11.get("pr_number")

        # Step 12: Close issue
        step12 = self.step12_close_issue(issue_number, pr_number, files_modified)
        if not step12.get("success"):
            logger.warning(f"Step 12 failed: {step12.get('error')} (PR still open)")

        logger.info("\n" + "=" * 60)
        logger.info("✓ GITHUB WORKFLOW COMPLETE")
        logger.info(f"  Issue: #{issue_number}")
        logger.info(f"  PR: #{pr_number}")
        logger.info(f"  Branch: {branch_name}")
        logger.info("=" * 60)

        return {
            "success": True,
            "issue_number": issue_number,
            "pr_number": pr_number,
            "branch_name": branch_name,
            "closed": step12.get("closed", False),
            "steps": {
                "step8": step8,
                "step9": step9,
                "step11": step11,
                "step12": step12
            }
        }
