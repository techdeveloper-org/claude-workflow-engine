"""
integrations package - Lifecycle adapters for external service integrations.

Provides:
    IntegrationRegistry  - Factory + registry for all integration adapters.
    AbstractIntegration  - Base class (re-exported from base).
    IntegrationState     - State enum (re-exported from base).

Usage:
    from langgraph_engine.integrations import IntegrationRegistry

    registry = IntegrationRegistry(session_dir=".", repo_path=".")
    github = registry.get("github")
    result = github.create(context)

Version: 1.4.1
"""

import logging
from typing import Any, Dict, List, Optional

from .base import AbstractIntegration, IntegrationState
from .config import get_enabled_integrations, get_integration_config
from .figma_integration import FigmaIntegration
from .github_integration import GitHubIntegration
from .jenkins_integration import JenkinsIntegration
from .jira_integration import JiraIntegration

logger = logging.getLogger(__name__)

__all__ = [
    "IntegrationRegistry",
    "AbstractIntegration",
    "IntegrationState",
    "GitHubIntegration",
    "JiraIntegration",
    "FigmaIntegration",
    "JenkinsIntegration",
    "get_integration_config",
    "get_enabled_integrations",
]


class IntegrationRegistry:
    """Factory and registry for all integration lifecycle adapters.

    Instantiates each integration on demand (lazy) and caches the instance
    for the lifetime of the registry object.  All integrations share the
    same session context passed at construction time.

    Registered integrations:
        github    - Always enabled (GitHubIntegration).
        jira      - Enabled via ENABLE_JIRA=1 (JiraIntegration).
        figma     - Enabled via ENABLE_FIGMA=1 (FigmaIntegration).
        jenkins   - Enabled via ENABLE_JENKINS=1 (JenkinsIntegration).
        sonarqube - Enabled via ENABLE_SONARQUBE=1 (SonarQubeIntegration).
    """

    def __init__(
        self,
        session_dir: str = ".",
        repo_path: str = ".",
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise the registry with shared session context.

        Args:
            session_dir:  Path to the current session directory.  Passed to
                          integrations that require it (e.g. GitHubIntegration).
            repo_path:    Path to the local repository root.
            extra_config: Optional extra key-value pairs merged into each
                          integration's config dict.
        """
        self._session_dir = session_dir
        self._repo_path = repo_path
        self._extra_config = extra_config or {}
        self._instances: Dict[str, AbstractIntegration] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_config(self, name: str) -> Dict[str, Any]:
        """Build the config dict for a named integration.

        Merges the feature-flag config with session context and extra config.

        Args:
            name: Integration name.

        Returns:
            Config dict for the integration constructor.
        """
        cfg = get_integration_config(name)
        cfg["session_dir"] = self._session_dir
        cfg["repo_path"] = self._repo_path
        cfg.update(self._extra_config)
        return cfg

    def _create_instance(self, name: str) -> Optional[AbstractIntegration]:
        """Instantiate a fresh integration adapter by name.

        Args:
            name: Integration name.

        Returns:
            AbstractIntegration subclass instance, or None when unknown.
        """
        config = self._build_config(name)

        try:
            if name == "github":
                from .github_integration import GitHubIntegration

                return GitHubIntegration(config)

            if name == "jira":
                from .jira_integration import JiraIntegration

                return JiraIntegration(config)

            if name == "figma":
                from .figma_integration import FigmaIntegration

                return FigmaIntegration(config)

            if name == "jenkins":
                from .jenkins_integration import JenkinsIntegration

                return JenkinsIntegration(config)

            if name == "sonarqube":
                from .sonarqube_integration import SonarQubeIntegration

                return SonarQubeIntegration(config)

        except ImportError as exc:
            logger.warning(
                "[IntegrationRegistry] Could not import '%s' integration: %s",
                name,
                exc,
            )
        except Exception as exc:
            logger.error(
                "[IntegrationRegistry] Failed to create '%s' integration: %s",
                name,
                exc,
            )

        logger.debug("[IntegrationRegistry] Unknown or unavailable integration: '%s'", name)
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[AbstractIntegration]:
        """Return a cached integration instance, creating it on first access.

        Args:
            name: Integration name ('github', 'jira', 'figma', 'jenkins',
                  'sonarqube').

        Returns:
            AbstractIntegration instance, or None when unavailable.
        """
        if name not in self._instances:
            instance = self._create_instance(name)
            if instance is not None:
                self._instances[name] = instance
            else:
                return None
        return self._instances[name]

    def get_enabled(self) -> List[AbstractIntegration]:
        """Return instances for all currently enabled integrations.

        Instantiates and caches each enabled integration on first call.

        Returns:
            List of AbstractIntegration instances whose env var is truthy.
        """
        enabled_names = get_enabled_integrations()
        result: List[AbstractIntegration] = []
        for name in enabled_names:
            instance = self.get(name)
            if instance is not None:
                result.append(instance)
        return result

    def enabled_names(self) -> List[str]:
        """Return the names of currently enabled integrations.

        Returns:
            List of integration name strings.
        """
        return get_enabled_integrations()

    def reset(self, name: Optional[str] = None) -> None:
        """Clear cached integration instance(s).

        Useful in tests to force re-creation of integration objects.

        Args:
            name: Specific integration to reset, or None to reset all.
        """
        if name is not None:
            self._instances.pop(name, None)
        else:
            self._instances.clear()
