"""
SonarQube REST API client.

Provides urllib-only (no SDK) wrappers for:
  - Low-level GET / POST helpers
  - Installation / server health detection
  - Issue fetching
  - Measures fetching
  - Quality gate status
  - Project creation
  - Full CLI + API scan orchestration

All functions are standalone and fail-safe: they never raise on network
errors; failures are logged at DEBUG level and returned as None / empty
structures.

ASCII-only source (cp1252 safe for Windows).
Python 3.8+ compatible.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    DEFAULT_SONAR_URL,
    METRIC_KEYS,
    SONAR_API_TIMEOUT,
    SONAR_CLI_TIMEOUT,
    SONAR_MAX_PAGE_SIZE,
    get_sonar_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal low-level helpers
# ---------------------------------------------------------------------------


def _build_auth_header(token: str) -> str:
    """Build an HTTP Basic auth header value from a SonarQube token.

    SonarQube uses HTTP Basic auth with the token as the username and an
    empty password: base64("token:").

    Args:
        token: SonarQube user or project authentication token.

    Returns:
        String suitable for use as an Authorization header value.
    """
    token_bytes = f"{token}:".encode("utf-8")
    return "Basic " + base64.b64encode(token_bytes).decode("ascii")


def _parse_report_task(report_task_path: Path) -> Dict[str, str]:
    """Parse .scannerwork/report-task.txt into a key->value dict."""
    result: Dict[str, str] = {}
    try:
        for raw_line in report_task_path.read_text(encoding="utf-8").splitlines():
            if "=" in raw_line:
                key, _, value = raw_line.partition("=")
                result[key.strip()] = value.strip()
    except Exception as exc:
        logger.debug("Could not parse report-task.txt: %s", exc)
    return result


# ---------------------------------------------------------------------------
# Public low-level API (used by higher-level functions in this module)
# ---------------------------------------------------------------------------


def sonar_api_get(
    endpoint: str,
    params: Optional[Dict[str, str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Call the SonarQube REST API via GET.

    Args:
        endpoint: API path, e.g. "/api/issues/search".
        params:   Optional query parameters dict.
        config:   Sonar config dict from get_sonar_config().  If None, calls
                  get_sonar_config() internally.

    Returns:
        Parsed JSON response dict, or None on any error.
    """
    if config is None:
        config = get_sonar_config()

    try:
        base = config["host_url"].rstrip("/")
        url = base + endpoint
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url)
        token = config.get("token", "")
        if token:
            req.add_header("Authorization", _build_auth_header(token))
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=SONAR_API_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        logger.debug("SonarQube API GET %s failed: HTTP %d", endpoint, exc.code)
        return None
    except urllib.error.URLError as exc:
        logger.debug("SonarQube API GET %s unreachable: %s", endpoint, exc.reason)
        return None
    except Exception as exc:
        logger.debug("SonarQube API GET %s error: %s", endpoint, exc)
        return None


def sonar_api_post(
    endpoint: str,
    data: Optional[Dict[str, str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Call the SonarQube REST API via POST.

    Args:
        endpoint: API path, e.g. "/api/projects/create".
        data:     Optional form data dict (sent as application/x-www-form-urlencoded).
        config:   Sonar config dict from get_sonar_config().  If None, calls
                  get_sonar_config() internally.

    Returns:
        Parsed JSON response dict, or None on any error.
    """
    if config is None:
        config = get_sonar_config()

    try:
        base = config["host_url"].rstrip("/")
        url = base + endpoint

        encoded_data = urllib.parse.urlencode(data or {}).encode("utf-8")
        req = urllib.request.Request(url, data=encoded_data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        token = config.get("token", "")
        if token:
            req.add_header("Authorization", _build_auth_header(token))

        with urllib.request.urlopen(req, timeout=SONAR_API_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}

    except urllib.error.HTTPError as exc:
        logger.debug("SonarQube API POST %s failed: HTTP %d", endpoint, exc.code)
        return None
    except urllib.error.URLError as exc:
        logger.debug("SonarQube API POST %s unreachable: %s", endpoint, exc.reason)
        return None
    except Exception as exc:
        logger.debug("SonarQube API POST %s error: %s", endpoint, exc)
        return None


def _sonar_issue_to_finding(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw SonarQube API issue dict to the pipeline finding schema."""
    component = issue.get("component", "")
    # Strip module prefix (e.g. "myapp:src/foo.py" -> "src/foo.py")
    file_path = component.split(":", 1)[-1] if ":" in component else component

    text_range = issue.get("textRange", {})
    line_no = text_range.get("startLine", issue.get("line", 0))

    return {
        "file": file_path,
        "line": line_no,
        "severity": issue.get("severity", "UNKNOWN"),
        "type": issue.get("type", "UNKNOWN"),
        "rule": issue.get("rule", ""),
        "message": issue.get("message", ""),
        "status": issue.get("status", ""),
        "effort": issue.get("effort", ""),
        "debt": issue.get("debt", ""),
        "tags": issue.get("tags", []),
    }


# ---------------------------------------------------------------------------
# Public API - installation / server detection
# ---------------------------------------------------------------------------


def detect_sonar_installation() -> Dict[str, Any]:
    """Check whether sonar-scanner CLI is installed and whether the API is reachable.

    Performs two independent checks:
      1. CLI check: runs ``sonar-scanner --version`` with a short timeout.
      2. API check: calls GET /api/system/status on the configured host URL.
         This succeeds even without sonar-scanner CLI as long as the server
         is running.

    Also reads sonar-project.properties for the host URL when SONAR_HOST_URL
    is not set in the environment.

    Returns:
        Dict with keys:
            installed (bool):        True if sonar-scanner CLI was found.
            version (str | None):    Reported CLI version string, or None.
            config_found (bool):     True if sonar-project.properties exists.
            sonar_host_url (str):    Resolved host URL.
            api_available (bool):    True if the SonarQube REST API responded.
            server_status (str):     "UP", "STARTING", "DOWN", or "UNKNOWN".
    """
    result: Dict[str, Any] = {
        "installed": False,
        "version": None,
        "config_found": False,
        "sonar_host_url": None,
        "api_available": False,
        "server_status": "UNKNOWN",
    }

    # 1. Check CLI availability
    try:
        proc = subprocess.run(
            ["sonar-scanner", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            result["installed"] = True
            for raw_line in (proc.stdout + proc.stderr).splitlines():
                if "sonarscanner" in raw_line.lower() or "sonar scanner" in raw_line.lower():
                    result["version"] = raw_line.strip()
                    break
    except FileNotFoundError:
        logger.debug("sonar-scanner not found in PATH")
    except subprocess.TimeoutExpired:
        logger.debug("sonar-scanner --version timed out")
    except Exception as exc:
        logger.debug("sonar-scanner check failed: %s", exc)

    # 2. Check for project config file
    config_path = Path("sonar-project.properties")
    result["config_found"] = config_path.exists()

    # 3. Determine host URL (env takes precedence over config file)
    config = get_sonar_config()
    host_url = config["host_url"] if config["host_url"] != DEFAULT_SONAR_URL else None

    if not host_url and result["config_found"]:
        try:
            for raw_line in config_path.read_text(encoding="utf-8").splitlines():
                if raw_line.startswith("sonar.host.url"):
                    _, _, host_url = raw_line.partition("=")
                    host_url = host_url.strip()
                    break
        except Exception as exc:
            logger.debug("Could not read sonar-project.properties: %s", exc)

    if not host_url:
        env_url = os.environ.get("SONAR_HOST_URL", "")
        host_url = env_url if env_url else DEFAULT_SONAR_URL

    result["sonar_host_url"] = host_url

    # 4. API health check: GET /api/system/status
    api_config = dict(config)
    api_config["host_url"] = host_url
    status_data = sonar_api_get("/api/system/status", config=api_config)
    if status_data is not None:
        server_status = status_data.get("status", "UNKNOWN")
        result["api_available"] = server_status == "UP"
        result["server_status"] = server_status
        logger.debug("SonarQube API at %s responded: status=%s", host_url, server_status)
    else:
        logger.debug("SonarQube API at %s not reachable", host_url)

    return result


# ---------------------------------------------------------------------------
# Public API - data retrieval
# ---------------------------------------------------------------------------


def get_project_issues(
    project_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    severities: Optional[List[str]] = None,
    types: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Get issues from the SonarQube API for a project.

    Calls GET /api/issues/search and returns all issues up to *page_size*.

    Args:
        project_key: Project key.  Falls back to SONAR_PROJECT_KEY env var.
        config:      Sonar config dict.  If None, calls get_sonar_config().
        severities:  Optional list of severity filters, e.g. ["CRITICAL", "MAJOR"].
        types:       Optional list of type filters, e.g. ["BUG", "VULNERABILITY"].
        page_size:   Maximum number of issues to return (max 500 per SonarQube
                     API page).

    Returns:
        List of finding dicts in the pipeline's standard format.
        Returns an empty list if the API is unavailable or the project has no
        issues.
    """
    if config is None:
        config = get_sonar_config()

    key = project_key or config.get("project_key", "")
    if not key:
        logger.debug("get_project_issues: no project_key available")
        return []

    params: Dict[str, str] = {
        "componentKeys": key,
        "ps": str(min(page_size, SONAR_MAX_PAGE_SIZE)),
    }
    if severities:
        params["severities"] = ",".join(severities)
    if types:
        params["types"] = ",".join(types)
    if config.get("organization"):
        params["organization"] = config["organization"]

    data = sonar_api_get("/api/issues/search", params=params, config=config)
    if data is None:
        return []

    raw_issues = data.get("issues", [])
    return [_sonar_issue_to_finding(issue) for issue in raw_issues]


def get_project_measures(
    project_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Get project quality measures from the SonarQube API.

    Calls GET /api/measures/component and returns a normalized dict of the
    most important quality metrics.

    Args:
        project_key: Project key.  Falls back to SONAR_PROJECT_KEY env var.
        config:      Sonar config dict.  If None, calls get_sonar_config().

    Returns:
        Dict with keys:
            bugs (int):            Number of open bug issues.
            vulnerabilities (int): Number of open vulnerability issues.
            code_smells (int):     Number of open code smell issues.
            coverage (float):      Test coverage percentage (0-100), or -1.0.
            duplications (float):  Duplicated lines density percentage, or -1.0.
            lines (int):           Total lines of code.
            quality_gate (str):    "OK", "ERROR", "WARN", or "UNKNOWN".
            raw (dict):            Raw metric key-value map from the API.
    """
    if config is None:
        config = get_sonar_config()

    key = project_key or config.get("project_key", "")

    default: Dict[str, Any] = {
        "bugs": 0,
        "vulnerabilities": 0,
        "code_smells": 0,
        "coverage": -1.0,
        "duplications": -1.0,
        "lines": 0,
        "quality_gate": "UNKNOWN",
        "raw": {},
    }

    if not key:
        logger.debug("get_project_measures: no project_key available")
        return default

    params: Dict[str, str] = {
        "component": key,
        "metricKeys": METRIC_KEYS,
    }
    if config.get("organization"):
        params["organization"] = config["organization"]

    data = sonar_api_get("/api/measures/component", params=params, config=config)
    if data is None:
        return default

    component = data.get("component", {})
    measures = component.get("measures", [])

    raw: Dict[str, str] = {}
    for m in measures:
        raw[m["metric"]] = m.get("value", "")

    def _int(key_name: str) -> int:
        try:
            return int(raw.get(key_name, 0) or 0)
        except (ValueError, TypeError):
            return 0

    def _float(key_name: str) -> float:
        try:
            return float(raw.get(key_name, -1.0) or -1.0)
        except (ValueError, TypeError):
            return -1.0

    alert_status = raw.get("alert_status", "UNKNOWN")
    if alert_status not in ("OK", "ERROR", "WARN"):
        alert_status = "UNKNOWN"

    return {
        "bugs": _int("bugs"),
        "vulnerabilities": _int("vulnerabilities"),
        "code_smells": _int("code_smells"),
        "coverage": _float("coverage"),
        "duplications": _float("duplicated_lines_density"),
        "lines": _int("ncloc"),
        "quality_gate": alert_status,
        "raw": raw,
    }


def get_quality_gate_status(
    project_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Get quality gate status from the SonarQube API.

    Calls GET /api/qualitygates/project_status and returns the gate result
    along with the individual condition outcomes.

    Args:
        project_key: Project key.  Falls back to SONAR_PROJECT_KEY env var.
        config:      Sonar config dict.  If None, calls get_sonar_config().

    Returns:
        Dict with keys:
            status (str):       "OK", "ERROR", "WARN", or "UNKNOWN".
            conditions (list):  List of condition dicts from the API.
            passed (bool):      True when status is "OK".
    """
    if config is None:
        config = get_sonar_config()

    key = project_key or config.get("project_key", "")

    default: Dict[str, Any] = {
        "status": "UNKNOWN",
        "conditions": [],
        "passed": False,
    }

    if not key:
        logger.debug("get_quality_gate_status: no project_key available")
        return default

    params: Dict[str, str] = {"projectKey": key}
    if config.get("organization"):
        params["organization"] = config["organization"]

    data = sonar_api_get("/api/qualitygates/project_status", params=params, config=config)
    if data is None:
        return default

    gate_data = data.get("projectStatus", {})
    status = gate_data.get("status", "UNKNOWN")
    if status not in ("OK", "ERROR", "WARN"):
        status = "UNKNOWN"

    return {
        "status": status,
        "conditions": gate_data.get("conditions", []),
        "passed": status == "OK",
    }


def create_sonar_project(
    project_key: str,
    project_name: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a SonarQube project via the API (first-time local setup).

    Calls POST /api/projects/create.  Most users will not need this because
    SonarCloud auto-creates projects and local SonarQube creates the project
    automatically on the first scan.

    Args:
        project_key:  Unique project key (e.g. "my-org_my-repo").
        project_name: Human-readable project name.
        config:       Sonar config dict.  If None, calls get_sonar_config().

    Returns:
        Dict with keys:
            created (bool):  True if the project was successfully created.
            key (str):       Project key.
            name (str):      Project name.
            error (str):     Error message if created is False.
    """
    if config is None:
        config = get_sonar_config()

    post_data: Dict[str, str] = {
        "project": project_key,
        "name": project_name,
    }
    if config.get("organization"):
        post_data["organization"] = config["organization"]

    data = sonar_api_post("/api/projects/create", data=post_data, config=config)
    if data is None:
        return {
            "created": False,
            "key": project_key,
            "name": project_name,
            "error": "API call failed or server unreachable",
        }

    project_data = data.get("project", {})
    if project_data:
        return {
            "created": True,
            "key": project_data.get("key", project_key),
            "name": project_data.get("name", project_name),
            "error": "",
        }

    errors = data.get("errors", [])
    error_msg = "; ".join(e.get("msg", "") for e in errors) if errors else "Unknown error"
    return {
        "created": False,
        "key": project_key,
        "name": project_name,
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# Public API - scan execution (CLI + API orchestration)
# ---------------------------------------------------------------------------


def run_sonar_scan(
    project_root: str,
    modified_files: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run sonar-scanner and return parsed findings.

    Execution strategy:
      1. Try the sonar-scanner CLI if installed.
      2. Always fetch results via the SonarQube REST API after the CLI scan,
         regardless of the CLI outcome.
      3. If the CLI is not installed but the API is reachable, fetch existing
         results from the last scan.

    If neither the CLI nor the API is available the function returns with
    ``scan_success=False`` and does not raise.

    Args:
        project_root:    Absolute path to the project root directory.
        modified_files:  Optional list of relative file paths to restrict
                         the scan scope.
        config:          Sonar config dict.  If None, calls get_sonar_config().

    Returns:
        Dict with keys:
            scan_success (bool):        True if results were obtained.
            findings (list):            List of finding dicts.
            summary (dict):             Aggregated counts + quality gate.
            scan_duration_ms (int):     Wall-clock time in milliseconds.
            error (str | None):         Error message if scan_success is False.
            api_used (bool):            True if results came from the REST API.
            cli_ran (bool):             True if sonar-scanner CLI was executed.
    """
    if config is None:
        config = get_sonar_config()

    empty_result: Dict[str, Any] = {
        "scan_success": False,
        "findings": [],
        "summary": {
            "bugs": 0,
            "vulnerabilities": 0,
            "code_smells": 0,
            "coverage_pct": None,
            "quality_gate": "UNKNOWN",
        },
        "scan_duration_ms": 0,
        "error": None,
        "api_used": False,
        "cli_ran": False,
    }

    install_info = detect_sonar_installation()
    root_path = Path(project_root)

    if not root_path.exists():
        result = dict(empty_result)
        result["error"] = f"project_root does not exist: {project_root}"
        return result

    scan_start = time.monotonic()

    # ------------------------------------------------------------------
    # Step 1: Run sonar-scanner CLI if available
    # ------------------------------------------------------------------
    cli_ran = False
    cli_error: Optional[str] = None

    if install_info["installed"]:
        cmd: List[str] = [
            "sonar-scanner",
            f"-Dsonar.projectBaseDir={root_path}",
        ]
        if modified_files:
            inclusions = ",".join(modified_files)
            cmd.append(f"-Dsonar.inclusions={inclusions}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(root_path),
                timeout=SONAR_CLI_TIMEOUT,
            )
            cli_ran = True
            if proc.returncode != 0:
                cli_error = f"sonar-scanner exited with code {proc.returncode}"
                logger.warning("sonar-scanner non-zero exit: %s", proc.stderr[:500])
        except subprocess.TimeoutExpired:
            cli_ran = True
            cli_error = f"sonar-scanner timed out after {SONAR_CLI_TIMEOUT} seconds"
            logger.warning("SonarQube scan timed out for %s", project_root)
        except Exception as exc:
            cli_ran = False
            cli_error = str(exc)
            logger.warning("SonarQube scan failed to start: %s", exc)

    # ------------------------------------------------------------------
    # Step 2: Resolve project key for API calls
    # Priority: env var > sonar-project.properties > report-task.txt
    # ------------------------------------------------------------------
    api_config = dict(config)
    project_key = api_config.get("project_key", "")

    if not project_key:
        props_path = root_path / "sonar-project.properties"
        if props_path.exists():
            try:
                for raw_line in props_path.read_text(encoding="utf-8").splitlines():
                    if raw_line.startswith("sonar.projectKey"):
                        _, _, project_key = raw_line.partition("=")
                        project_key = project_key.strip()
                        break
            except Exception as exc:
                logger.debug("Could not read sonar-project.properties: %s", exc)

    if not project_key and cli_ran:
        report_task_path = root_path / ".scannerwork" / "report-task.txt"
        report_info = _parse_report_task(report_task_path)
        project_key = report_info.get("projectKey", "")
        if not api_config.get("host_url") or api_config["host_url"] == DEFAULT_SONAR_URL:
            server_from_report = report_info.get("serverUrl", "")
            if server_from_report:
                api_config["host_url"] = server_from_report

    if project_key:
        api_config["project_key"] = project_key

    # ------------------------------------------------------------------
    # Step 3: Fetch results via REST API
    # ------------------------------------------------------------------
    api_used = False
    findings: List[Dict[str, Any]] = []
    measures: Dict[str, Any] = {}
    gate_status: Dict[str, Any] = {}

    if install_info["api_available"] and project_key:
        findings = get_project_issues(project_key=project_key, config=api_config)
        measures = get_project_measures(project_key=project_key, config=api_config)
        gate_status = get_quality_gate_status(project_key=project_key, config=api_config)
        api_used = True
        logger.debug(
            "Fetched %d issues via SonarQube API for project %s",
            len(findings),
            project_key,
        )
    elif cli_ran and not install_info["api_available"]:
        # CLI ran but API is not reachable; parse report-task.txt for minimal
        # quality gate info and leave findings empty
        report_task_path = root_path / ".scannerwork" / "report-task.txt"
        report_info = _parse_report_task(report_task_path)
        raw_gate = report_info.get("qualityGateStatus", "UNKNOWN")
        gate_status = {
            "status": raw_gate if raw_gate in ("OK", "WARN", "ERROR") else "UNKNOWN",
            "conditions": [],
            "passed": raw_gate == "OK",
        }

    elapsed_ms = int((time.monotonic() - scan_start) * 1000)

    # ------------------------------------------------------------------
    # Step 4: Build result dict
    # ------------------------------------------------------------------
    if api_used:
        scan_success = True
        error = None
    elif cli_ran and cli_error is None:
        scan_success = True
        error = None
    elif cli_ran and cli_error:
        scan_success = False
        error = cli_error
    elif not install_info["installed"] and not install_info["api_available"]:
        result = dict(empty_result)
        result["scan_duration_ms"] = elapsed_ms
        result["error"] = "sonar-scanner not installed and API not reachable"
        return result
    else:
        scan_success = False
        error = cli_error or "Unknown scan failure"

    # Build summary from API measures (preferred) or findings list
    if measures:
        quality_gate_str = measures.get("quality_gate", "UNKNOWN")
        summary: Dict[str, Any] = {
            "bugs": measures.get("bugs", 0),
            "vulnerabilities": measures.get("vulnerabilities", 0),
            "code_smells": measures.get("code_smells", 0),
            "coverage_pct": (measures.get("coverage") if measures.get("coverage", -1.0) >= 0 else None),
            "quality_gate": (
                "PASSED" if quality_gate_str == "OK" else ("FAILED" if quality_gate_str == "ERROR" else "UNKNOWN")
            ),
        }
    else:
        bugs = sum(1 for f in findings if f.get("type") == "BUG")
        vulnerabilities = sum(1 for f in findings if f.get("type") == "VULNERABILITY")
        code_smells = sum(1 for f in findings if f.get("type") == "CODE_SMELL")
        gate_str = gate_status.get("status", "UNKNOWN")
        summary = {
            "bugs": bugs,
            "vulnerabilities": vulnerabilities,
            "code_smells": code_smells,
            "coverage_pct": None,
            "quality_gate": ("PASSED" if gate_str == "OK" else ("FAILED" if gate_str == "ERROR" else "UNKNOWN")),
        }

    return {
        "scan_success": scan_success,
        "findings": findings,
        "summary": summary,
        "scan_duration_ms": elapsed_ms,
        "error": error,
        "api_used": api_used,
        "cli_ran": cli_ran,
    }
