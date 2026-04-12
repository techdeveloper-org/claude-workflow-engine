"""
GitHub integration adapter.

Wraps Level3GitHubWorkflow (level3_steps8to12_github.py) behind the
AbstractIntegration lifecycle interface.

GitHub CI is enabled when ENABLE_CI=true/1 in the environment.

Version: 1.4.1
"""

import logging
import os
from typing import Any, Dict

from .base import AbstractIntegration, IntegrationState

logger = logging.getLogger(__name__)


class GitHubIntegration(AbstractIntegration):
    """GitHub lifecycle integration for Steps 8-12.

    Delegates all actual API work to Level3GitHubWorkflow.  This class is a
    thin adapter that maps the AbstractIntegration lifecycle to the existing
    step methods.

    Because GitHub workflow requires session_dir and repo_path at
    construction time these are passed via the config dict.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialise GitHub integration adapter.

        Args:
            config: Must contain 'enabled' (bool).  Optional keys:
                - 'session_dir' (str): passed to Level3GitHubWorkflow.
                - 'repo_path' (str): defaults to '.'.
        """
        super().__init__(config)
        self._workflow = None  # Lazy-initialised on first use.
        self._state = IntegrationState.READY if self.is_enabled else IntegrationState.DISABLED

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return integration name."""
        return "github"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workflow(self):
        """Lazy-load Level3GitHubWorkflow to avoid import-time side effects.

        Returns:
            Level3GitHubWorkflow instance, or None when unavailable.
        """
        if self._workflow is None:
            try:
                from ..level3_execution.steps8to12_github import Level3GitHubWorkflow  # type: ignore[import]

                session_dir = self._config.get("session_dir", ".")
                repo_path = self._config.get("repo_path", ".")
                self._workflow = Level3GitHubWorkflow(
                    session_dir=session_dir,
                    repo_path=repo_path,
                )
                logger.debug("[GitHubIntegration] Level3GitHubWorkflow loaded")
            except ImportError as exc:
                logger.warning("[GitHubIntegration] Level3GitHubWorkflow unavailable: %s", exc)
        return self._workflow

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def create(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 8: Create GitHub issue.

        Delegates to Level3GitHubWorkflow.step8_create_issue or equivalent
        orchestration in the workflow class.

        Args:
            context: Pipeline state with task title, description, label, etc.

        Returns:
            Dict with success (bool), issue_number, issue_url.
        """
        logger.info("[GitHubIntegration] create() - Step 8: create GitHub issue")

        if not self.is_enabled:
            return {"success": False, "reason": "GitHub integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3GitHubWorkflow unavailable"}

        try:
            title = context.get("issue_title", context.get("title", ""))
            description = context.get("issue_description", context.get("description", ""))
            label = context.get("label", os.environ.get("GITHUB_DEFAULT_LABEL", "feature"))

            result = workflow.step8_create_github_issue(
                title=title,
                description=description,
                label=label,
            )
            if result.get("success"):
                self._artifact_id = str(result.get("issue_number", ""))
                self._state = IntegrationState.CREATED
            else:
                self._state = IntegrationState.ERROR
            return result
        except Exception as exc:
            logger.error("[GitHubIntegration] create() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def on_branch(self, branch_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 9: Create the branch on the remote.

        Args:
            branch_name: Branch name to create.
            context: Pipeline state.

        Returns:
            Dict with success (bool), branch_name.
        """
        logger.info("[GitHubIntegration] on_branch() - Step 9: create branch %s", branch_name)

        if not self.is_enabled:
            return {"success": False, "reason": "GitHub integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3GitHubWorkflow unavailable"}

        try:
            result = workflow.step9_create_branch(branch_name=branch_name)
            return result
        except Exception as exc:
            logger.error("[GitHubIntegration] on_branch() failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def update(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 10: GitHub has no explicit in-progress transition.

        GitHub issues do not have workflow states.  This is a no-op that
        returns success to keep the lifecycle consistent.

        Args:
            context: Pipeline state (unused).

        Returns:
            Dict with success=True.
        """
        logger.debug("[GitHubIntegration] update() - Step 10: no-op for GitHub")
        if not self.is_enabled:
            return {"success": False, "reason": "GitHub integration not enabled"}
        self._state = IntegrationState.IN_PROGRESS
        return {"success": True, "reason": "GitHub has no in-progress state transition"}

    def on_review(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 11: Create and review pull request.

        Args:
            pr_data: Dict with pr_title, pr_body, branch_name, etc.
            context: Pipeline state.

        Returns:
            Dict with success (bool), pr_number, pr_url, merged (bool).
        """
        logger.info("[GitHubIntegration] on_review() - Step 11: create/review PR")

        if not self.is_enabled:
            return {"success": False, "reason": "GitHub integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3GitHubWorkflow unavailable"}

        try:
            result = workflow.step11_create_and_review_pr(
                pr_title=pr_data.get("pr_title", context.get("pr_title", "")),
                pr_body=pr_data.get("pr_body", context.get("pr_body", "")),
                branch_name=pr_data.get("branch_name", context.get("branch_name", "")),
                issue_number=int(self._artifact_id or 0),
            )
            if result.get("success"):
                self._state = IntegrationState.IN_REVIEW
            return result
        except Exception as exc:
            logger.error("[GitHubIntegration] on_review() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def close(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 12: Close GitHub issue.

        Args:
            context: Pipeline state with issue closure details.

        Returns:
            Dict with success (bool), closed (bool).
        """
        logger.info("[GitHubIntegration] close() - Step 12: close GitHub issue")

        if not self.is_enabled:
            return {"success": False, "reason": "GitHub integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3GitHubWorkflow unavailable"}

        try:
            issue_number = int(self._artifact_id or context.get("issue_number", 0))
            result = workflow.step12_close_issue(
                issue_number=issue_number,
                pr_number=context.get("pr_number", 0),
            )
            if result.get("success"):
                self._state = IntegrationState.DONE
            return result
        except Exception as exc:
            logger.error("[GitHubIntegration] close() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}
