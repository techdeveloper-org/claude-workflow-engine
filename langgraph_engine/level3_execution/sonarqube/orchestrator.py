"""
sonarqube/orchestrator.py - High-level scan orchestration and GitHub integration.

Contains scan_and_report() and create_issues_for_findings() which orchestrate
the full scan pipeline and create GitHub issues for findings.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api_client import detect_sonar_installation, get_project_measures, get_quality_gate_status, run_sonar_scan
from .config import get_sonar_config
from .lightweight_scanner import run_basic_scan
from .result_aggregator import categorize_findings

logger = logging.getLogger(__name__)


def create_issues_for_findings(
    project_root: str,
    findings: List[Dict[str, Any]],
    max_issues: int = 5,
) -> Dict[str, Any]:
    """Create GitHub issues for Critical/Major SonarQube findings.

    Reuses the existing Level 3 GitHub infrastructure in this order:
      1. MCP github_create_issue tool (same as Step 8 in the pipeline).
      2. Level3GitHubWorkflow from level3_steps8to12_github.py.
      3. gh CLI as final fallback.

    At most *max_issues* GitHub issues are created per call to avoid spam.
    Only CRITICAL, BLOCKER, and MAJOR severity findings are promoted to issues.

    Args:
        project_root:  Path to the project root (used as cwd for gh CLI).
        findings:      List of finding dicts to consider.
        max_issues:    Hard cap on the number of issues created (default 5).

    Returns:
        Dict with keys:
            issues_created (int):   Number of GitHub issues created.
            issue_ids (list):       GitHub issue numbers as ints.
            skipped (int):          Findings not promoted to a GitHub issue.
            method_used (str):      "mcp", "workflow", "gh_cli", or "none".
    """
    result: Dict[str, Any] = {
        "issues_created": 0,
        "issue_ids": [],
        "skipped": 0,
        "method_used": "none",
    }

    # Filter to actionable severity levels
    actionable = [f for f in findings if f.get("severity", "").upper() in ("CRITICAL", "BLOCKER", "MAJOR")]
    result["skipped"] = len(findings) - len(actionable)

    if not actionable:
        logger.debug("No critical/major findings; no GitHub issues will be created")
        return result

    to_create = actionable[:max_issues]
    result["skipped"] += len(actionable) - len(to_create)

    # ------------------------------------------------------------------
    # Build issue payload for each finding
    # ------------------------------------------------------------------
    def _build_issue_payload(finding: Dict[str, Any]) -> Dict[str, str]:
        severity = finding.get("severity", "UNKNOWN")
        finding_type = finding.get("type", "UNKNOWN")
        file_path = finding.get("file", "unknown")
        line_no = finding.get("line", 0)
        rule = finding.get("rule", "")
        message = finding.get("message", "No message")
        title = f"[SonarQube] {severity} {finding_type}: {message[:80]}"
        body = (
            f"## SonarQube Finding\n\n"
            f"**Severity:** {severity}\n"
            f"**Type:** {finding_type}\n"
            f"**Rule:** {rule}\n"
            f"**File:** `{file_path}` (line {line_no})\n\n"
            f"### Message\n\n{message}\n\n"
            f"*Auto-detected by the Claude Workflow Engine SonarQube scanner.*"
        )
        return {"title": title, "body": body}

    # ------------------------------------------------------------------
    # Method 1: MCP github_create_issue tool
    # ------------------------------------------------------------------
    mcp_available = False
    try:
        from ..github_mcp import create_issue_via_mcp  # type: ignore[import]

        mcp_available = True
    except ImportError:
        pass

    if mcp_available:
        created = 0
        for finding in to_create:
            payload = _build_issue_payload(finding)
            try:
                issue_result = create_issue_via_mcp(  # type: ignore[possibly-undefined]
                    title=payload["title"],
                    body=payload["body"],
                    labels=["sonarqube", "auto-detected"],
                )
                issue_number = issue_result.get("number")
                if issue_number:
                    result["issue_ids"].append(int(issue_number))
                created += 1
            except Exception as exc:
                logger.debug("MCP issue creation failed: %s", exc)
                result["skipped"] += 1
        result["issues_created"] = created
        if created > 0:
            result["method_used"] = "mcp"
            return result

    # ------------------------------------------------------------------
    # Method 2: Level3GitHubWorkflow
    # ------------------------------------------------------------------
    workflow_available = False
    try:
        from .steps8to12_github import Level3GitHubWorkflow  # type: ignore[import]

        workflow_available = True
    except ImportError:
        pass

    if workflow_available:
        created = 0
        try:
            workflow = Level3GitHubWorkflow()  # type: ignore[possibly-undefined]
            for finding in to_create:
                payload = _build_issue_payload(finding)
                try:
                    issue_result = workflow.create_issue(
                        title=payload["title"],
                        body=payload["body"],
                        labels=["sonarqube", "auto-detected"],
                    )
                    issue_number = issue_result.get("number")
                    if issue_number:
                        result["issue_ids"].append(int(issue_number))
                    created += 1
                except Exception as exc:
                    logger.debug("Level3GitHubWorkflow issue creation failed: %s", exc)
                    result["skipped"] += 1
        except Exception as exc:
            logger.debug("Could not instantiate Level3GitHubWorkflow: %s", exc)
            workflow_available = False

        result["issues_created"] = created
        if created > 0:
            result["method_used"] = "workflow"
            return result

    # ------------------------------------------------------------------
    # Method 3: gh CLI fallback
    # ------------------------------------------------------------------
    try:
        check = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        gh_available = check.returncode == 0
    except Exception:
        gh_available = False

    if not gh_available:
        logger.debug(
            "gh CLI not available; skipping GitHub issue creation for %d findings",
            len(to_create),
        )
        result["skipped"] += len(to_create)
        return result

    created = 0
    for finding in to_create:
        payload = _build_issue_payload(finding)
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    payload["title"],
                    "--body",
                    payload["body"],
                    "--label",
                    "sonarqube",
                    "--label",
                    "auto-detected",
                ],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=30,
            )
            if proc.returncode == 0:
                url = proc.stdout.strip()
                try:
                    issue_number = int(url.rstrip("/").rsplit("/", 1)[-1])
                    result["issue_ids"].append(issue_number)
                except ValueError:
                    pass
                created += 1
                logger.debug(
                    "Created GitHub issue for %s:%d",
                    finding.get("file", ""),
                    finding.get("line", 0),
                )
            else:
                logger.debug(
                    "gh issue create failed (rc=%d): %s",
                    proc.returncode,
                    proc.stderr[:200],
                )
                result["skipped"] += 1
        except Exception as exc:
            logger.debug("gh CLI issue creation error: %s", exc)
            result["skipped"] += 1

    result["issues_created"] = created
    if created > 0:
        result["method_used"] = "gh_cli"
    return result


def scan_and_report(
    project_root: str,
    modified_files: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full scan pipeline: detect -> scan -> categorize -> report.

    Execution strategy:
      1. Get config from env vars + defaults.
      2. Check API availability.
      3. If API available: fetch issues + measures via REST API (preferred).
      4. If API not available but CLI installed: run CLI scan.
      5. If neither: run run_basic_scan() fallback.
      6. Categorize all findings and return combined report.

    Args:
        project_root:   Absolute path to the project root directory.
        modified_files: Optional list of relative file paths to restrict scope.
        config:         Sonar config dict.  If None, calls get_sonar_config().

    Returns:
        Combined dict containing all keys from run_sonar_scan plus:
            sonar_installed (bool):   Whether sonar-scanner CLI was found.
            api_available (bool):     Whether the SonarQube API responded.
            scanner_used (str):       "sonarqube_api", "sonarqube_cli", or "basic".
            categories (dict):        Output of categorize_findings().
            measures (dict):          Output of get_project_measures() if available.
            quality_gate (dict):      Output of get_quality_gate_status() if available.
    """
    if config is None:
        config = get_sonar_config()

    install_info = detect_sonar_installation()
    sonar_installed = install_info["installed"]
    api_available = install_info["api_available"]

    project_key = config.get("project_key", "")
    # Try sonar-project.properties if env not set
    if not project_key:
        props_path = Path(project_root) / "sonar-project.properties"
        if props_path.exists():
            try:
                for raw_line in props_path.read_text(encoding="utf-8").splitlines():
                    if raw_line.startswith("sonar.projectKey"):
                        _, _, project_key = raw_line.partition("=")
                        project_key = project_key.strip()
                        break
            except Exception as exc:
                logger.debug("Could not read sonar-project.properties: %s", exc)
        if project_key:
            config = dict(config)
            config["project_key"] = project_key

    measures: Dict[str, Any] = {}
    quality_gate: Dict[str, Any] = {}
    scanner_used = "basic"

    if api_available and project_key:
        # API-first: fetch everything from the REST API
        scan_result = run_sonar_scan(project_root, modified_files, config=config)
        measures = get_project_measures(project_key=project_key, config=config)
        quality_gate = get_quality_gate_status(project_key=project_key, config=config)
        scanner_used = "sonarqube_api"
    elif sonar_installed:
        # CLI fallback: trigger a new scan, results from report-task.txt + API
        logger.debug("SonarQube API not available; using CLI for %s", project_root)
        scan_result = run_sonar_scan(project_root, modified_files, config=config)
        scanner_used = "sonarqube_cli"
    else:
        # Basic fallback: no SonarQube at all
        logger.debug(
            "SonarQube not available; using lightweight basic scanner for %s",
            project_root,
        )
        scan_result = run_basic_scan(project_root, modified_files)
        scanner_used = "basic"

    findings = scan_result.get("findings", [])
    categories = categorize_findings(findings)

    return {
        **scan_result,
        "sonar_installed": sonar_installed,
        "api_available": api_available,
        "scanner_used": scanner_used,
        "categories": categories,
        "measures": measures,
        "quality_gate": quality_gate,
    }
