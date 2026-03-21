"""
Integration feature-flag configuration.

Reads ENABLE_* environment variables and returns per-integration config
dicts consumed by AbstractIntegration subclasses.

Version: 1.4.1
"""

import os
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Integration flag definitions
# ---------------------------------------------------------------------------

# Each entry maps an integration name to its environment variable and default.
# All integrations default to disabled. Set ENABLE_CI=true to enable GitHub Actions CI.
INTEGRATION_FLAGS: Dict[str, Dict[str, Any]] = {
    "github": {
        "enabled": False,
        "env_var": "ENABLE_CI",
        "default": "false",
    },
    "jira": {
        "enabled": False,
        "env_var": "ENABLE_JIRA",
        "default": "0",
    },
    "figma": {
        "enabled": False,
        "env_var": "ENABLE_FIGMA",
        "default": "0",
    },
    "jenkins": {
        "enabled": False,
        "env_var": "ENABLE_JENKINS",
        "default": "0",
    },
    "sonarqube": {
        "enabled": False,
        "env_var": "ENABLE_SONARQUBE",
        "default": "0",
    },
}

# Truthy string values recognised as enabled.
_TRUTHY: frozenset = frozenset({"1", "true", "yes", "on"})


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_integration_config(name: str) -> Dict[str, Any]:
    """Return the resolved configuration dict for a named integration.

    Reads the corresponding environment variable to determine whether the
    integration is enabled.  Returns the full flags dict augmented with the
    resolved 'enabled' value so callers do not need to re-check env vars.

    Args:
        name: Integration name, e.g. 'jira', 'figma', 'github'.

    Returns:
        Dict with at minimum 'name' and 'enabled' keys plus any extra flags
        defined in INTEGRATION_FLAGS.  Returns a minimal disabled config when
        the name is not registered.
    """
    flags = INTEGRATION_FLAGS.get(name, {})
    env_var = flags.get("env_var", "")
    default = flags.get("default", "0")
    raw_value = os.environ.get(env_var, default).strip().lower()
    enabled = raw_value in _TRUTHY
    return {
        "name": name,
        "enabled": enabled,
        "env_var": env_var,
        "default": default,
    }


def get_enabled_integrations() -> List[str]:
    """Return the names of all currently enabled integrations.

    Returns:
        List of integration name strings whose env vars resolve to truthy.
    """
    return [
        name
        for name in INTEGRATION_FLAGS
        if get_integration_config(name).get("enabled")
    ]


def is_integration_enabled(name: str) -> bool:
    """Quick helper to check whether a single integration is enabled.

    Args:
        name: Integration name.

    Returns:
        True when the integration's env var is set to a truthy value.
    """
    return get_integration_config(name).get("enabled", False)
