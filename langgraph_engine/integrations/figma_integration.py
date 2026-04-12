"""
Figma integration adapter.

Wraps Level3FigmaWorkflow (level3_figma_workflow.py) behind the
AbstractIntegration lifecycle interface.

Active when ENABLE_FIGMA=1 and FIGMA_ACCESS_TOKEN is set.
Pipeline steps for Figma: 3 (extract), 7 (inject tokens), 10, 11, 12.
The AbstractIntegration lifecycle (8->9->10->11->12) is mapped as:
  create()    -> Step 3/8: extract components from Figma file
  on_branch() -> no-op
  update()    -> Step 10: post "implementation started" comment
  on_review() -> Step 11: design fidelity review checklist
  close()     -> Step 12: post "implementation complete" comment

Version: 1.4.1
"""

import logging
from typing import Any, Dict, List, Optional

from .base import AbstractIntegration, IntegrationState

logger = logging.getLogger(__name__)


class FigmaIntegration(AbstractIntegration):
    """Figma design lifecycle integration for pipeline Steps 3/7/10/11/12.

    Delegates all actual API work to Level3FigmaWorkflow.  This adapter maps
    the AbstractIntegration lifecycle methods to the corresponding Figma
    workflow methods.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialise Figma integration adapter.

        Args:
            config: Must contain 'enabled' (bool).
        """
        super().__init__(config)
        self._workflow = None  # Lazy-initialised on first use.
        self._file_key: Optional[str] = None
        self._components: List[Dict[str, Any]] = []
        self._state = IntegrationState.READY if self.is_enabled else IntegrationState.DISABLED

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return integration name."""
        return "figma"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workflow(self):
        """Lazy-load Level3FigmaWorkflow to avoid import-time side effects.

        Returns:
            Level3FigmaWorkflow instance, or None when unavailable.
        """
        if self._workflow is None:
            try:
                from ..level3_execution.figma_workflow import Level3FigmaWorkflow  # type: ignore[import]

                self._workflow = Level3FigmaWorkflow()
                logger.debug("[FigmaIntegration] Level3FigmaWorkflow loaded")
            except ImportError as exc:
                logger.warning("[FigmaIntegration] Level3FigmaWorkflow unavailable: %s", exc)
        return self._workflow

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def create(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 8/3: Extract Figma components for task breakdown.

        Detects the Figma file key from the user message or reads it from
        context, then delegates to Level3FigmaWorkflow.step3_extract_components.

        Args:
            context: Pipeline state.  Expected keys:
                - figma_file_key (str): Explicit Figma file key.
                - user_message (str): Raw user prompt (used for URL detection
                  when figma_file_key is absent).

        Returns:
            Dict with success (bool), components (list), pages (list),
            total_components (int), figma_file_key (str).
        """
        logger.info("[FigmaIntegration] create() - extract Figma components")

        if not self.is_enabled:
            return {"success": False, "reason": "Figma integration not enabled"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3FigmaWorkflow unavailable"}

        # Resolve file key from context or detect from user message.
        file_key = context.get("figma_file_key", "")
        if not file_key:
            user_message = context.get("user_message", "")
            if user_message:
                file_key = workflow.detect_figma_url(user_message) or ""

        if not file_key:
            logger.debug("[FigmaIntegration] No Figma file key found; skipping component extraction")
            return {"success": False, "reason": "No Figma file key in context or user_message"}

        self._file_key = file_key
        self._artifact_id = file_key

        try:
            result = workflow.step3_extract_components(file_key=file_key)
            if result.get("success"):
                self._components = result.get("components", [])
                self._state = IntegrationState.CREATED
            else:
                self._state = IntegrationState.ERROR
            result["figma_file_key"] = file_key
            return result
        except Exception as exc:
            logger.error("[FigmaIntegration] create() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def extract_design_tokens(self, file_key: Optional[str] = None, node_ids: str = "") -> Dict[str, Any]:
        """Step 7: Extract design tokens for prompt injection.

        This is an additional non-lifecycle method exposed for Step 7 callers.

        Args:
            file_key: Figma file key.  Defaults to self._file_key.
            node_ids: Optional comma-separated Figma node IDs.

        Returns:
            Dict with success (bool), design_tokens (dict), prompt_snippet (str).
        """
        resolved_key = file_key or self._file_key or ""
        logger.info("[FigmaIntegration] extract_design_tokens() - file: %s", resolved_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Figma integration not enabled"}

        if not resolved_key:
            return {"success": False, "reason": "No Figma file key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3FigmaWorkflow unavailable"}

        try:
            return workflow.step7_extract_design_tokens(
                file_key=resolved_key,
                node_ids=node_ids,
            )
        except Exception as exc:
            logger.error("[FigmaIntegration] extract_design_tokens() failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def update(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 10: Post 'implementation started' comment to Figma file.

        Delegates to Level3FigmaWorkflow.step10_implementation_started.

        Args:
            context: Pipeline state.  Uses 'figma_file_key' or artifact_id.
                     Optionally uses 'figma_components' list.

        Returns:
            Dict with success (bool), comment_id (str).
        """
        file_key = context.get("figma_file_key", self._file_key or "")
        logger.info("[FigmaIntegration] update() - Step 10: post started comment to %s", file_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Figma integration not enabled"}

        if not file_key:
            return {"success": False, "reason": "No Figma file key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3FigmaWorkflow unavailable"}

        try:
            components = context.get("figma_components", self._components)
            result = workflow.step10_implementation_started(
                file_key=file_key,
                components=components if isinstance(components, list) else [],
            )
            if result.get("success"):
                self._state = IntegrationState.IN_PROGRESS
            return result
        except Exception as exc:
            logger.error("[FigmaIntegration] update() failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def on_review(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 11: Generate design fidelity review checklist.

        Delegates to Level3FigmaWorkflow.step11_design_review.

        Args:
            pr_data: Dict with pr_url (str), pr_number (int) - not used by
                     Figma but included for interface consistency.
            context: Pipeline state.  Uses 'figma_file_key' or artifact_id,
                     and optionally 'implementation_summary' (str).

        Returns:
            Dict with success (bool), review_items (list), checklist_text (str).
        """
        file_key = context.get("figma_file_key", self._file_key or "")
        logger.info("[FigmaIntegration] on_review() - Step 11: design review for %s", file_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Figma integration not enabled"}

        if not file_key:
            return {"success": False, "reason": "No Figma file key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3FigmaWorkflow unavailable"}

        try:
            result = workflow.step11_design_review(
                file_key=file_key,
                implementation_summary=context.get("implementation_summary", ""),
            )
            if result.get("success"):
                self._state = IntegrationState.IN_REVIEW
            return result
        except Exception as exc:
            logger.error("[FigmaIntegration] on_review() failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def close(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 12: Post 'implementation complete' comment to Figma file.

        Delegates to Level3FigmaWorkflow.step12_implementation_complete.

        Args:
            context: Pipeline state.  Expected keys:
                - figma_file_key (str): Overrides self._file_key.
                - pr_number (int): PR number.
                - pr_url (str): PR URL.

        Returns:
            Dict with success (bool), comment_id (str).
        """
        file_key = context.get("figma_file_key", self._file_key or "")
        logger.info("[FigmaIntegration] close() - Step 12: post complete comment to %s", file_key)

        if not self.is_enabled:
            return {"success": False, "reason": "Figma integration not enabled"}

        if not file_key:
            return {"success": False, "reason": "No Figma file key available"}

        workflow = self._get_workflow()
        if workflow is None:
            return {"success": False, "reason": "Level3FigmaWorkflow unavailable"}

        try:
            result = workflow.step12_implementation_complete(
                file_key=file_key,
                pr_number=int(context.get("pr_number", 0)),
                pr_url=context.get("pr_url", ""),
            )
            if result.get("success"):
                self._state = IntegrationState.DONE
            return result
        except Exception as exc:
            logger.error("[FigmaIntegration] close() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}
