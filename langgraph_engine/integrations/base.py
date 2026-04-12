"""
Abstract base for external service integrations.

Defines the Create -> Update -> Close lifecycle followed by all integrations
across pipeline Steps 8-12.

Version: 1.4.1
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional


class IntegrationState(Enum):
    """Lifecycle states for integrations."""

    DISABLED = "disabled"
    READY = "ready"
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    ERROR = "error"


class AbstractIntegration(ABC):
    """Abstract base class for external service integrations.

    Defines the Create -> Update -> Close lifecycle that all integrations
    follow across pipeline Steps 8-12:

        Step 8:  create()    - Create issue/artifact
        Step 9:  on_branch() - React to branch creation
        Step 10: update()    - Transition to in-progress
        Step 11: on_review() - Link PR, add review data
        Step 12: close()     - Transition to done/complete

    All concrete methods must be ASCII-safe in log messages.
    Implementations delegate to the existing workflow modules; they do not
    re-implement API logic.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialise with integration-specific configuration.

        Args:
            config: Dict containing at minimum an 'enabled' key (bool) and
                    any integration-specific keys needed by the concrete class.
        """
        self._config = config
        self._state: IntegrationState = IntegrationState.DISABLED
        # Artifact ID set by create(); e.g. Jira issue key or GitHub issue number.
        self._artifact_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Integration name used in registry and log messages.

        Returns:
            Lowercase string identifier, e.g. 'jira', 'figma', 'github'.
        """

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        """Return True when this integration is active via configuration."""
        return bool(self._config.get("enabled", False))

    @property
    def state(self) -> IntegrationState:
        """Current lifecycle state of this integration instance."""
        return self._state

    @property
    def artifact_id(self) -> Optional[str]:
        """Identifier of the artifact created in Step 8.

        Returns:
            String ID (e.g. 'PROJ-123' for Jira, issue number for GitHub),
            or None before create() has been called.
        """
        return self._artifact_id

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    @abstractmethod
    def create(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 8: Create the integration artifact.

        Args:
            context: Pipeline state dict with task/issue data.

        Returns:
            Dict with at minimum a 'success' key (bool) and the artifact
            identifier under an integration-specific key.
        """

    def on_branch(self, branch_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 9: React to branch creation.

        Default implementation is a no-op.  Override when the integration
        needs to perform an action after a branch is created (e.g. Jira
        keyed branch naming).

        Args:
            branch_name: The name of the branch that was created.
            context: Pipeline state dict.

        Returns:
            Dict with integration-specific result data.  Empty dict is
            acceptable when the integration has nothing to do at this step.
        """
        return {}

    @abstractmethod
    def update(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 10: Transition to in-progress state.

        Called at the start of the implementation step.

        Args:
            context: Pipeline state dict including the artifact ID.

        Returns:
            Dict with at minimum a 'success' key (bool).
        """

    @abstractmethod
    def on_review(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 11: Handle code review stage.

        Called after a PR is created.  Should link the PR to the artifact
        and/or add review data.

        Args:
            pr_data: Dict with pr_url, pr_number, and other PR metadata.
            context: Pipeline state dict.

        Returns:
            Dict with at minimum a 'success' key (bool).
        """

    @abstractmethod
    def close(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 12: Close/complete the integration artifact.

        Args:
            context: Pipeline state dict with closure details.

        Returns:
            Dict with at minimum a 'success' key (bool).
        """
