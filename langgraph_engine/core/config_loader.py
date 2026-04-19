"""
Workflow Config Loader -- reads ~/.claude/workflow-config.json.

Two modes:
  1. load_workflow_config() -- injects values into os.environ (covers any
     remaining os.environ.get() call sites as a safety net).
  2. get_section(name)     -- returns raw JSON section dict so integration
     classes can read values directly without going through os.environ.

Priority for os.environ injection:
  existing os.environ > workflow-config.json (no-override mode)

Usage:
  from langgraph_engine.core.config_loader import load_workflow_config, get_section
  load_workflow_config()           # once at startup in 3-level-flow.py
  cfg = get_section("jira")        # direct dict access anywhere
"""

import json
import os
from pathlib import Path

_DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "workflow-config.json"

# Nested JSON key  ->  env var name  (kept for os.environ injection fallback)
_MAPPING: dict[str, str] = {
    "pipeline.hook_mode": "CLAUDE_HOOK_MODE",
    "pipeline.debug": "CLAUDE_DEBUG",
    "pipeline.llm_provider": "LLM_PROVIDER",
    "github.token": "GITHUB_TOKEN",
    "github.default_label": "GITHUB_DEFAULT_LABEL",
    "github.owner": "CLAUDE_GITHUB_OWNER",
    "jira.enabled": "ENABLE_JIRA",
    "jira.url": "JIRA_URL",
    "jira.user": "JIRA_USER",
    "jira.api_token": "JIRA_API_TOKEN",
    "jira.api_version": "JIRA_API_VERSION",
    "jira.auth_method": "JIRA_AUTH_METHOD",
    "jira.default_project": "JIRA_DEFAULT_PROJECT",
    "jira.default_issue_type": "JIRA_DEFAULT_ISSUE_TYPE",
    "jira.default_branch_prefix": "JIRA_DEFAULT_BRANCH_PREFIX",
    "jenkins.enabled": "ENABLE_JENKINS",
    "jenkins.url": "JENKINS_URL",
    "jenkins.user": "JENKINS_USER",
    "jenkins.api_token": "JENKINS_API_TOKEN",
    "jenkins.verify_ssl": "JENKINS_VERIFY_SSL",
    "figma.enabled": "ENABLE_FIGMA",
    "figma.access_token": "FIGMA_ACCESS_TOKEN",
    "figma.team_id": "FIGMA_TEAM_ID",
    "sonarqube.enabled": "ENABLE_SONARQUBE",
    "anthropic.api_key": "ANTHROPIC_API_KEY",
    "anthropic.model_fast": "ANTHROPIC_MODEL_FAST",
    "anthropic.model_balanced": "ANTHROPIC_MODEL_BALANCED",
    "anthropic.model_deep": "ANTHROPIC_MODEL_DEEP",
}

_CONFIG_CACHE: dict | None = None


def _load_raw(path: Path | None = None) -> dict:
    """Return the full parsed JSON config (cached after first read)."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    config_path = path or _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        _CONFIG_CACHE = {}
        return _CONFIG_CACHE
    try:
        _CONFIG_CACHE = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        import sys

        print(f"[config_loader] WARNING: could not read {config_path}: {exc}", file=sys.stderr)
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def get_section(name: str) -> dict:
    """Return the JSON config section for a named integration or service.

    Args:
        name: Top-level key in workflow-config.json, e.g. 'jira', 'jenkins'.

    Returns:
        Dict of config values for that section, or {} when not present.
    """
    return _load_raw().get(name, {})


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    """Recursively flatten nested dict to dot-separated keys."""
    out: dict[str, str] = {}
    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, full_key))
        else:
            out[full_key] = str(v)
    return out


def load_workflow_config(path: Path | None = None) -> dict[str, str]:
    """Load workflow-config.json and inject into os.environ (no-override).

    Covers any remaining os.environ.get() call sites that have not yet
    been migrated to use get_section() directly.

    Returns a dict of env-var-name -> value pairs that were injected.
    """
    raw = _load_raw(path)
    if not raw:
        return {}

    flat = _flatten(raw)
    injected: dict[str, str] = {}

    for json_key, env_key in _MAPPING.items():
        if json_key in flat and env_key not in os.environ:
            os.environ[env_key] = flat[json_key]
            injected[env_key] = flat[json_key]

    return injected
