"""
Import Manager for Claude Workflow Engine.

Provides a unified interface for loading resources from both the local project
and the remote GitHub repositories. Handles UTF-8 encoding setup for Windows
consoles before performing any network requests.

Resources are sourced from:
1. Local project modules - via Python's import system
2. claude-global-library - GitHub raw URLs (skills and agents)
3. claude-workflow-engine - GitHub raw URLs (architecture policies)

Module-level constants:
    GITHUB_BASE (str): Base GitHub raw-content URL prefix.
    GLOBAL_LIB_URL (str): Raw URL prefix for claude-global-library main branch.
    PROJECT_URL (str): Raw URL prefix for claude-workflow-engine main branch.
    PROJECT_ROOT (Path): Absolute path to the project root directory.
    SKILL_URLS (dict): Quick-reference URL map for common skills.
    AGENT_URLS (dict): Quick-reference URL map for common agents.
    POLICY_URLS (dict): Quick-reference URL map for policy README files.

Classes:
    ImportManager: Static utility class for loading remote and local resources.
"""

# Fix encoding for Windows console
import sys

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# GitHub base URLs (configurable via env vars for portability)
_GITHUB_OWNER = os.environ.get("CLAUDE_GITHUB_OWNER", "techdeveloper-org")
GITHUB_BASE = f"https://raw.githubusercontent.com/{_GITHUB_OWNER}"
GLOBAL_LIB_URL = os.environ.get("CLAUDE_GLOBAL_LIB_URL", f"{GITHUB_BASE}/claude-global-library/main")
PROJECT_URL = os.environ.get("CLAUDE_PROJECT_URL", f"{GITHUB_BASE}/claude-workflow-engine/main")

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Ensure the project root is importable so `langgraph_engine.library.resolver`
# (the ADR-1 local-path bridge) can be resolved regardless of caller's cwd.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph_engine.library.resolver import LibrarySetupError, build_default_resolver  # noqa: E402

_resolver = None  # lazily constructed module-level singleton -- keeps ImportManager's static-method ergonomics


def _get_resolver():
    """Return the module-level ``ResourceResolver`` singleton, building it on first use."""
    global _resolver
    if _resolver is None:
        _resolver = build_default_resolver(engine_root=PROJECT_ROOT)
    return _resolver


class ImportManager:
    """Unified import manager for local project modules and GitHub-hosted resources.

    All methods are static - no instance is required. Resources are fetched
    directly over HTTPS using urllib and decoded as UTF-8.

    GitHub base URLs used:
        Skills:  https://raw.../claude-global-library/main/skills/{name}/skill.md
        Agents:  https://raw.../claude-global-library/main/agents/{name}/agent.md
        Policies: https://raw.../claude-workflow-engine/main/scripts/architecture/{path}
    """

    @staticmethod
    def get_skill(skill_name: str) -> Optional[Dict]:
        """Load a skill definition via the ADR-1 local-path bridge.

        Resolves through the ``ResourceResolver`` chain: the sibling
        claude-global-library checkout first (no network call, tries
        ``SKILL.md`` then ``skill.md``), then an opt-in GitHub HTTP fallback
        (``CLAUDE_ALLOW_GITHUB_FALLBACK=1``), then a typed failure.

        Args:
            skill_name (str): Skill identifier matching the directory name
                in claude-global-library/skills/ (e.g. 'docker',
                'java-spring-boot-microservices').

        Returns:
            dict or None: On success, a dict with keys:
                name (str): The skill_name argument.
                content (str): Raw skill markdown content.
                source (str): 'local' or 'github'.
                url (str): The local file path or GitHub raw URL that was resolved.
            Returns None if the skill could not be resolved by any tier, or
            if skill_name fails the resolver's name-safety validation.
        """
        try:
            resource = _get_resolver().fetch_skill(skill_name)
        except LibrarySetupError as exc:
            logger.warning("ImportManager.get_skill('%s') failed: %s", skill_name, exc)
            return None
        except ValueError as exc:
            logger.warning("ImportManager.get_skill('%s') rejected: %s", skill_name, exc)
            return None
        return {"name": skill_name, "content": resource.content, "source": resource.source, "url": resource.path_or_url}

    @staticmethod
    def get_agent(agent_name: str) -> Optional[Dict]:
        """Load an agent definition via the ADR-1 local-path bridge.

        Resolves through the ``ResourceResolver`` chain: the sibling
        claude-global-library checkout first (no network call), then an
        opt-in GitHub HTTP fallback (``CLAUDE_ALLOW_GITHUB_FALLBACK=1``),
        then a typed failure.

        Args:
            agent_name (str): Agent identifier matching the directory name
                in claude-global-library/agents/ (e.g. 'orchestrator-agent',
                'devops-engineer').

        Returns:
            dict or None: On success, a dict with keys:
                name (str): The agent_name argument.
                content (str): Raw agent.md markdown content.
                source (str): 'local' or 'github'.
                url (str): The local file path or GitHub raw URL that was resolved.
            Returns None if the agent could not be resolved by any tier, or
            if agent_name fails the resolver's name-safety validation.
        """
        try:
            resource = _get_resolver().fetch_agent(agent_name)
        except LibrarySetupError as exc:
            logger.warning("ImportManager.get_agent('%s') failed: %s", agent_name, exc)
            return None
        except ValueError as exc:
            logger.warning("ImportManager.get_agent('%s') rejected: %s", agent_name, exc)
            return None
        return {"name": agent_name, "content": resource.content, "source": resource.source, "url": resource.path_or_url}

    @staticmethod
    def get_policy(policy_path: str) -> Optional[str]:
        """Load an architecture policy document from claude-workflow-engine on GitHub.

        Fetches a policy markdown file from the ``scripts/architecture/``
        directory of the claude-workflow-engine repository's main branch.

        Args:
            policy_path (str): Relative path within scripts/architecture/
                (e.g. '01-sync-system/context-management/README.md').

        Returns:
            str or None: Raw markdown content of the policy file, or None
                on HTTP error (file not found).
        """
        url = f"{PROJECT_URL}/scripts/architecture/{policy_path}"
        try:
            with urllib.request.urlopen(url) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError:
            return None

    @staticmethod
    def get_local_module(module_path: str) -> Any:
        """Load a local project module by dotted path.

        Uses Python's built-in import mechanism to load and return the module
        at the given dotted path. The module must be importable from the
        current sys.path (i.e. within the src/ package).

        Args:
            module_path (str): Dotted module path string
                (e.g. 'services.monitoring.metrics_collector').

        Returns:
            module: The imported Python module object.

        Raises:
            ImportError: If the module cannot be found or imported.
            AttributeError: If any intermediate component of the path is not
                an attribute of the parent module.
        """
        parts = module_path.split(".")
        module = __import__(module_path)
        for part in parts[1:]:
            module = getattr(module, part)
        return module

    @staticmethod
    def list_skills() -> Optional[list]:
        """Fetch and return the skills index from claude-global-library.

        Attempts to download ``skills/INDEX.md`` and returns its lines.

        Returns:
            list[str] or None: Lines from the INDEX.md file, or None if the
                file does not exist or cannot be fetched.
        """
        url = f"{GLOBAL_LIB_URL}/skills/INDEX.md"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode("utf-8")
                # Parse INDEX.md to extract skill list
                return content.split("\n")
        except urllib.error.HTTPError:
            return None

    @staticmethod
    def list_agents() -> Optional[list]:
        """Fetch and return the agents list from claude-global-library README.

        Attempts to download ``agents/README.md`` and returns its lines.

        Returns:
            list[str] or None: Lines from the README.md file, or None if the
                file does not exist or cannot be fetched.
        """
        url = f"{GLOBAL_LIB_URL}/agents/README.md"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode("utf-8")
                # Parse README.md to extract agent list
                return content.split("\n")
        except urllib.error.HTTPError:
            return None


# Quick reference URLs
SKILL_URLS = {
    "docker": f"{GLOBAL_LIB_URL}/skills/docker/skill.md",
    "kubernetes": f"{GLOBAL_LIB_URL}/skills/kubernetes/skill.md",
    "python-system-scripting": f"{GLOBAL_LIB_URL}/skills/system/python-system-scripting/SKILL.md",
    "java-spring-boot": f"{GLOBAL_LIB_URL}/skills/backend/java-spring-boot-microservices/SKILL.md",
}

AGENT_URLS = {
    "orchestrator": f"{GLOBAL_LIB_URL}/agents/orchestrator-agent/agent.md",
    "devops": f"{GLOBAL_LIB_URL}/agents/devops-engineer/agent.md",
    "qa-testing": f"{GLOBAL_LIB_URL}/agents/qa-testing-agent/agent.md",
    "spring-boot-microservices": f"{GLOBAL_LIB_URL}/agents/spring-boot-microservices/agent.md",
}

POLICY_URLS = {
    "sync-system": f"{PROJECT_URL}/scripts/architecture/01-sync-system/README.md",
    "standards-system": f"{PROJECT_URL}/scripts/architecture/02-standards-system/README.md",
    "execution-system": f"{PROJECT_URL}/scripts/architecture/03-execution-system/README.md",
}


if __name__ == "__main__":
    # Test
    print("Testing ImportManager...")

    # Test skill
    docker_skill = ImportManager.get_skill("docker")
    if docker_skill:
        print("[OK] Loaded skill: {} ({} bytes)".format(docker_skill["name"], len(docker_skill["content"])))
    else:
        print("[FAIL] Could not load docker skill")

    # Test agent
    orchestrator = ImportManager.get_agent("orchestrator-agent")
    if orchestrator:
        print("[OK] Loaded agent: {} ({} bytes)".format(orchestrator["name"], len(orchestrator["content"])))
    else:
        print("[FAIL] Could not load orchestrator agent")

    print("\nAvailable URLs:")
    print("Skills: {}".format(list(SKILL_URLS.keys())))
    print("Agents: {}".format(list(AGENT_URLS.keys())))
    print("Policies: {}".format(list(POLICY_URLS.keys())))
