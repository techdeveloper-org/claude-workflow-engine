"""
SonarQube configuration module.

Reads all SonarQube settings from environment variables and exposes typed
constants and a factory function.  This is the single source of truth for
configuration defaults across the sonarqube package.

ASCII-only source (cp1252 safe for Windows).
Python 3.8+ compatible.
"""

from __future__ import annotations

import os
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------

_ENV_HOST_URL = "SONAR_HOST_URL"
_ENV_TOKEN = "SONAR_TOKEN"
_ENV_PROJECT_KEY = "SONAR_PROJECT_KEY"
_ENV_ORGANIZATION = "SONAR_ORGANIZATION"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SONAR_URL = "http://localhost:9000"

# Default quality gate thresholds used by the pipeline quality_gate module.
DEFAULT_QUALITY_GATE: Dict[str, Any] = {
    "bugs": 0,
    "vulnerabilities": 0,
    "code_smells": 10,
    "coverage": 80.0,
    "duplicated_lines_density": 3.0,
}

# SonarQube metric keys fetched by get_project_measures.
METRIC_KEYS = "bugs,vulnerabilities,code_smells,coverage," "duplicated_lines_density,ncloc,sqale_rating,alert_status"

# Maximum page size supported by the SonarQube issues search API.
SONAR_MAX_PAGE_SIZE = 500

# HTTP timeout for all REST API calls (seconds).
SONAR_API_TIMEOUT = 15

# sonar-scanner CLI execution timeout (seconds).
SONAR_CLI_TIMEOUT = 300


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------


def get_sonar_config() -> Dict[str, Any]:
    """Return SonarQube configuration read from environment variables.

    Never raises; missing values are represented as empty strings or False.

    Environment variables:
        SONAR_HOST_URL       - Base URL of the SonarQube/SonarCloud server
                               (default: http://localhost:9000)
        SONAR_TOKEN          - Authentication token (user or project token)
        SONAR_PROJECT_KEY    - Project key for API calls
        SONAR_ORGANIZATION   - Organization key (required for SonarCloud)

    Returns:
        Dict with keys:
            host_url (str):       Server base URL.
            token (str):          Auth token, or empty string if not set.
            project_key (str):    Project key, or empty string if not set.
            organization (str):   Organization key, or empty string if not set.
            is_cloud (bool):      True when the host URL contains sonarcloud.io.
    """
    host_url = os.environ.get(_ENV_HOST_URL, DEFAULT_SONAR_URL)
    return {
        "host_url": host_url,
        "token": os.environ.get(_ENV_TOKEN, ""),
        "project_key": os.environ.get(_ENV_PROJECT_KEY, ""),
        "organization": os.environ.get(_ENV_ORGANIZATION, ""),
        "is_cloud": "sonarcloud.io" in host_url,
    }
