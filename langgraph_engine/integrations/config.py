"""
Integration feature-flag configuration.

Reads ENABLE_* environment variables and returns per-integration config
dicts consumed by AbstractIntegration subclasses.

All defaults live in .env.example -- nothing is hardcoded here.
Missing env vars fall back to "0" (disabled) so the pipeline runs
safely without any integrations configured.

Version: 1.5.0
"""

import os
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Integration registry: maps name -> env var that enables it.
# Defaults for each var are defined in .env.example, not here.
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


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_integration_config(name: str) -> Dict[str, Any]:
    """Return the resolved configuration dict for a named integration.

    Reads the corresponding ENABLE_* environment variable.
    Falls back to disabled ("0") when the variable is not set.

    Args:
        name: Integration name, e.g. 'jira', 'figma', 'github'.

    Returns:
        Dict with 'name', 'enabled', and 'env_var' keys.
        Returns a minimal disabled config for unregistered names.
    """
    env_var = INTEGRATION_ENV_VARS.get(name, "")
    raw_value = os.environ.get(env_var, "0").strip().lower()
    is_enabled = raw_value in _TRUTHY
    return {
        "name": name,
        "enabled": is_enabled,
        "env_var": env_var,
    }


def get_enabled_integrations() -> List[str]:
    """Return the names of all currently enabled integrations.

    Returns:
        List of integration name strings whose env vars resolve to truthy.
    """
    return [name for name in INTEGRATION_ENV_VARS if get_integration_config(name).get("enabled")]


def is_integration_enabled(name: str) -> bool:
    """Quick helper to check whether a single integration is enabled.

    Args:
        name: Integration name.

    Returns:
        True when the integration's env var is set to a truthy value.
    """
    return get_integration_config(name).get("enabled", False)
