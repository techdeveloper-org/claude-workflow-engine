"""
Integration feature-flag configuration.

Reads integration settings from workflow-config.json (via config_loader)
with os.environ as fallback for any value not present in the JSON file.

All defaults live in ~/.claude/workflow-config.json -- nothing is hardcoded here.
Missing config falls back to disabled so the pipeline runs safely without
any integrations configured.

Version: 1.6.0
"""

import os
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Integration registry: maps name -> env var that enables it (fallback only).
# Primary source is workflow-config.json via get_section().
# ---------------------------------------------------------------------------

INTEGRATION_ENV_VARS: Dict[str, str] = {
    "github": "ENABLE_CI",
    "jira": "ENABLE_JIRA",
    "figma": "ENABLE_FIGMA",
    "jenkins": "ENABLE_JENKINS",
    "sonarqube": "ENABLE_SONARQUBE",
}

# Truthy string values recognised as enabled.
_TRUTHY: frozenset = frozenset({"1", "true", "yes", "on"})

# Maps JSON section keys -> config dict keys consumed by integration classes.
_SECTION_CONFIG_KEYS: Dict[str, Dict[str, str]] = {
    "jira": {
        "url": "jira_url",
        "user": "jira_user",
        "api_token": "jira_api_token",
        "api_version": "jira_api_version",
        "auth_method": "jira_auth_method",
        "default_project": "jira_default_project",
        "default_issue_type": "jira_default_issue_type",
        "default_branch_prefix": "jira_default_branch_prefix",
    },
    "jenkins": {
        "url": "jenkins_url",
        "user": "jenkins_user",
        "api_token": "jenkins_api_token",
        "verify_ssl": "jenkins_verify_ssl",
    },
    "figma": {
        "access_token": "figma_access_token",
        "team_id": "figma_team_id",
    },
    "github": {
        "token": "github_token",
        "default_label": "github_default_label",
        "owner": "github_owner",
    },
}


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_integration_config(name: str) -> Dict[str, Any]:
    """Return the resolved configuration dict for a named integration.

    Reads enabled flag and all integration-specific values from
    workflow-config.json first, falling back to env vars when absent.

    Args:
        name: Integration name, e.g. 'jira', 'figma', 'github'.

    Returns:
        Dict with 'name', 'enabled', 'env_var', plus all integration-specific
        config keys (e.g. 'jira_url', 'jenkins_user') populated from JSON.
    """
    try:
        from langgraph_engine.core.config_loader import get_section

        section = get_section(name)
    except ImportError:
        section = {}

    env_var = INTEGRATION_ENV_VARS.get(name, "")

    # Resolve enabled flag: JSON section > env var > default False.
    if "enabled" in section:
        is_enabled = _is_truthy(str(section["enabled"]))
    else:
        is_enabled = _is_truthy(os.environ.get(env_var, "0"))

    cfg: Dict[str, Any] = {
        "name": name,
        "enabled": is_enabled,
        "env_var": env_var,
    }

    # Populate integration-specific keys from JSON section (config dict keys).
    key_map = _SECTION_CONFIG_KEYS.get(name, {})
    for json_key, config_key in key_map.items():
        value = section.get(json_key, "")
        if value:
            cfg[config_key] = str(value)

    return cfg


def get_enabled_integrations() -> List[str]:
    """Return the names of all currently enabled integrations."""
    return [name for name in INTEGRATION_ENV_VARS if get_integration_config(name).get("enabled")]


def is_integration_enabled(name: str) -> bool:
    """Quick helper to check whether a single integration is enabled."""
    return get_integration_config(name).get("enabled", False)
