"""
Jira integration adapter.

Wraps Level3JiraWorkflow (level3_steps8to12_jira.py) behind the
AbstractIntegration lifecycle interface.

Only active when ENABLE_JIRA=1 and JIRA_URL/JIRA_USER/JIRA_API_TOKEN are set.

Version: 1.4.1
"""

import logging
import os
from typing import Any, Dict

from .base import AbstractIntegration, IntegrationState

logger = logging.getLogger(__name__)


class JiraIntegration(AbstractIntegration):
    """Jira lifecycle integration for Steps 8-12.

    Delegates all actual API work to Level3JiraWorkflow.  This class is a
    thin adapter that maps the AbstractIntegration lifecycle to the existing
    step methods on that workflow class.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialise Jira integration adapter.

        Args:
            config: Must contain 'enabled' (bool).
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
        return "jira"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workflow(self):
        """Lazy-load Level3JiraWorkflow to avoid import-time side effects.

        Returns:
            Level3JiraWorkflow instance, or None when unavailable.
        """
        if self._workflow is None:
            try:
                from ..level3_execution.steps8to12_jira import Level3JiraWorkflow  # type: ignore[import]

                self._workflow = Level3JiraWorkflow()
                logger.debug("[JiraIntegration] Level3JiraWorkflow loaded")
            except ImportError as exc:
                logger.warning("[JiraIntegration] Level3JiraWorkflow unavailable: %s", exc)
        return self._workflow

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def create(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 8: Create Jira issue and cross-link to GitHub issue.

        Delegates to Level3JiraWorkflow.step8_create_jira_issue.

        Args:
            context: Pipeline state.  Expected keys:
                - title (str): Issue title.
                - description (str): Issue description.
                - label (str): Issue label/type (bug, feature, task...).
                - github_issue_url (str): URL of the GitHub issue.
                - github_issue_number (int): GitHub issue number.

        Returns:
            Dict with success (bool), jira_issue_key, jira_issue_url.
        """
        logger.info("[JiraIntegration] create() - Step 8: create Jira issue")

        if not self.is_enabled:
            return {"success": False, "reason": "Jira integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3JiraWorkflow unavailable"}

        try:
            result = workflow.step8_create_jira_issue(
                title=context.get("title", context.get("issue_title", "")),
                description=context.get("description", context.get("issue_description", "")),
                label=context.get("label", os.environ.get("JIRA_DEFAULT_ISSUE_TYPE", "task")),
                github_issue_url=context.get("github_issue_url", ""),
                github_issue_number=int(context.get("github_issue_number", 0)),
            )
            if result.get("success"):
                self._artifact_id = result.get("jira_issue_key", "")
                self._state = IntegrationState.CREATED
            else:
                self._state = IntegrationState.ERROR
            return result
        except Exception as exc:
            logger.error("[JiraIntegration] create() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def on_branch(self, branch_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 9: Return a Jira-keyed branch name.

        Delegates to Level3JiraWorkflow.step9_get_branch_name to build a
        branch name in the format label/JIRA-KEY (e.g. feature/PROJ-123).

        Args:
            branch_name: The default branch name (may be overridden).
            context: Pipeline state.  Uses 'label' key.

        Returns:
            Dict with success (bool), jira_branch_name (str).
        """
        logger.info("[JiraIntegration] on_branch() - Step 9: derive Jira branch name")

        if not self.is_enabled:
            return {"success": False, "reason": "Jira integration not enabled"}

        if not self._artifact_id:
            return {"success": False, "reason": "No Jira issue key (create() not called)"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3JiraWorkflow unavailable"}

        try:
            jira_branch = workflow.step9_get_branch_name(
                jira_issue_key=self._artifact_id,
                label=context.get("label", os.environ.get("JIRA_DEFAULT_BRANCH_PREFIX", "feature")),
            )
            return {
                "success": bool(jira_branch),
                "jira_branch_name": jira_branch,
                "jira_issue_key": self._artifact_id,
            }
        except Exception as exc:
            logger.error("[JiraIntegration] on_branch() failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def update(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 10: Transition Jira issue to 'In Progress'.

        Delegates to Level3JiraWorkflow.step10_start_progress.

        Args:
            context: Pipeline state.  Uses 'jira_issue_key' key or falls
                     back to self._artifact_id.

        Returns:
            Dict with success (bool), transitioned (bool).
        """
        issue_key = context.get("jira_issue_key", self._artifact_id or "")
        logger.info("[JiraIntegration] update() - Step 10: start progress on %s", issue_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Jira integration not enabled"}

        if not issue_key:
            return {"success": False, "reason": "No Jira issue key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3JiraWorkflow unavailable"}

        try:
            result = workflow.step10_start_progress(jira_issue_key=issue_key)
            if result.get("success"):
                self._state = IntegrationState.IN_PROGRESS
            return result
        except Exception as exc:
            logger.error("[JiraIntegration] update() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def on_review(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 11: Link PR to Jira issue and transition to 'In Review'.

        Delegates to Level3JiraWorkflow.step11_link_pr_and_transition.

        Args:
            pr_data: Dict with pr_url (str), pr_number (int).
            context: Pipeline state.  Uses 'jira_issue_key' or artifact_id.

        Returns:
            Dict with success (bool), linked (bool), transitioned (bool).
        """
        issue_key = context.get("jira_issue_key", self._artifact_id or "")
        logger.info("[JiraIntegration] on_review() - Step 11: link PR to %s", issue_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Jira integration not enabled"}

        if not issue_key:
            return {"success": False, "reason": "No Jira issue key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3JiraWorkflow unavailable"}

        try:
            result = workflow.step11_link_pr_and_transition(
                jira_issue_key=issue_key,
                pr_url=pr_data.get("pr_url", ""),
                pr_number=int(pr_data.get("pr_number", 0)),
            )
            if result.get("success"):
                self._state = IntegrationState.IN_REVIEW
            return result
        except Exception as exc:
            logger.error("[JiraIntegration] on_review() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def close(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 12: Transition Jira issue to 'Done' with closing summary.

        Delegates to Level3JiraWorkflow.step12_close_jira_issue.

        Args:
            context: Pipeline state.  Expected keys:
                - jira_issue_key (str): Overrides self._artifact_id.
                - pr_number (int): PR that resolved the issue.
                - files_modified (list): List of modified file paths.
                - approach_taken (str): Implementation approach summary.

        Returns:
            Dict with success (bool), closed (bool), transitioned (bool).
        """
        issue_key = context.get("jira_issue_key", self._artifact_id or "")
        logger.info("[JiraIntegration] close() - Step 12: close Jira issue %s", issue_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Jira integration not enabled"}

        if not issue_key:
            return {"success": False, "reason": "No Jira issue key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3JiraWorkflow unavailable"}

        try:
            result = workflow.step12_close_jira_issue(
                jira_issue_key=issue_key,
                pr_number=int(context.get("pr_number", 0)),
                files_modified=context.get("files_modified", []),
                approach_taken=context.get("approach_taken", ""),
            )
            if result.get("success"):
                self._state = IntegrationState.DONE
            return result
        except Exception as exc:
            logger.error("[JiraIntegration] close() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}
