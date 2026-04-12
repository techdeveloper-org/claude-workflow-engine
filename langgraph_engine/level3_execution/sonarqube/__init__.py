"""
sonarqube package - Facade over SonarQube API and lightweight fallback scanner.

Public surface:
    SonarQubeScanner  - Main facade class (API-first + lightweight fallback)

Version: 1.4.1
"""

import logging
from typing import Any, Dict, List, Optional

from .api_client import get_project_issues  # noqa: F401
from .api_client import detect_sonar_installation, get_project_measures, get_quality_gate_status, run_sonar_scan
from .auto_fixer import SonarAutoFixer
from .config import get_sonar_config
from .lightweight_scanner import run_basic_scan
from .orchestrator import create_issues_for_findings, scan_and_report  # noqa: F401
from .result_aggregator import aggregate_scan_result  # noqa: F401
from .result_aggregator import categorize_findings, generate_fix_prompt

logger = logging.getLogger(__name__)

__all__ = [
    "SonarQubeScanner",
    "SonarAutoFixer",
    "run_basic_scan",
    "categorize_findings",
    "generate_fix_prompt",
]


class SonarQubeScanner:
    """Facade for SonarQube scanning.

    Strategy:
      1. If SonarQube API is reachable (and project_key known): use REST API.
      2. If sonar-scanner CLI is installed: run CLI scan.
      3. Fallback: lightweight AST + regex scanner (Python only, no SonarQube).

    All public methods return dicts and never raise.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialise scanner with optional config override.

        Args:
            config: Sonar config dict.  If None, reads from environment variables
                    via get_sonar_config().
        """
        self._config = config or get_sonar_config()
        self._auto_fixer = SonarAutoFixer()

    # ------------------------------------------------------------------
    # Primary scan entry points
    # ------------------------------------------------------------------

    def scan(
        self,
        project_root: str,
        modified_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the best available scan and return a full report.

        Automatically selects the scanning strategy:
          - API-first when SonarQube server is reachable.
          - CLI fallback when sonar-scanner is installed.
          - Lightweight fallback when neither is available.

        Args:
            project_root:   Absolute path to the project root directory.
            modified_files: Optional list of relative file paths to restrict
                            the scan scope.

        Returns:
            Dict with keys: scan_success, findings, summary, scan_duration_ms,
            error, api_used, cli_ran, sonar_installed, api_available,
            scanner_used, categories, measures, quality_gate.
        """
        logger.info("[SonarQubeScanner] scan() - project_root=%s", project_root)

        try:
            install_info = detect_sonar_installation()
            sonar_installed = install_info["installed"]
            api_available = install_info["api_available"]

            config = self._config
            project_key = config.get("project_key", "")

            measures: Dict[str, Any] = {}
            quality_gate: Dict[str, Any] = {}
            scanner_used = "basic"

            if api_available and project_key:
                scan_result = run_sonar_scan(project_root, modified_files, config=config)
                measures = get_project_measures(project_key=project_key, config=config)
                quality_gate = get_quality_gate_status(project_key=project_key, config=config)
                scanner_used = "sonarqube_api"
                logger.info(
                    "[SonarQubeScanner] API scan complete: %d findings",
                    len(scan_result.get("findings", [])),
                )
            elif sonar_installed:
                logger.debug(
                    "[SonarQubeScanner] API not available; using CLI for %s",
                    project_root,
                )
                scan_result = run_sonar_scan(project_root, modified_files, config=config)
                scanner_used = "sonarqube_cli"
            else:
                logger.debug("[SonarQubeScanner] SonarQube not available; using lightweight scanner")
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

        except Exception as exc:
            logger.error("[SonarQubeScanner] scan() failed: %s", exc)
            return {
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
                "error": str(exc),
                "api_used": False,
                "cli_ran": False,
                "sonar_installed": False,
                "api_available": False,
                "scanner_used": "none",
                "categories": {},
                "measures": {},
                "quality_gate": {},
            }

    def scan_basic(
        self,
        project_root: str,
        modified_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the lightweight scanner directly, bypassing SonarQube.

        Useful when you know SonarQube is unavailable and want to skip the
        detection overhead.

        Args:
            project_root:   Absolute path to the project root directory.
            modified_files: Optional list of relative file paths.

        Returns:
            Same schema as scan().
        """
        logger.info("[SonarQubeScanner] scan_basic() - project_root=%s", project_root)
        try:
            scan_result = run_basic_scan(project_root, modified_files)
            findings = scan_result.get("findings", [])
            categories = categorize_findings(findings)
            return {
                **scan_result,
                "sonar_installed": False,
                "api_available": False,
                "scanner_used": "basic",
                "categories": categories,
                "measures": {},
                "quality_gate": {},
            }
        except Exception as exc:
            logger.error("[SonarQubeScanner] scan_basic() failed: %s", exc)
            return {
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
                "error": str(exc),
                "api_used": False,
                "cli_ran": False,
                "sonar_installed": False,
                "api_available": False,
                "scanner_used": "none",
                "categories": {},
                "measures": {},
                "quality_gate": {},
            }

    # ------------------------------------------------------------------
    # Categorization and reporting helpers
    # ------------------------------------------------------------------

    def categorize(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Categorize a list of findings by severity and type.

        Args:
            findings: List of finding dicts.

        Returns:
            Dict with keys: critical, major, minor, by_type, auto_fixable,
            needs_review.
        """
        return categorize_findings(findings)

    def fix_prompt(self, finding: Dict[str, Any]) -> str:
        """Generate an LLM fix prompt for a single finding.

        Args:
            finding: A single finding dict.

        Returns:
            Prompt string ready for LLM consumption.
        """
        return generate_fix_prompt(finding)

    # ------------------------------------------------------------------
    # Auto-fix interface
    # ------------------------------------------------------------------

    def auto_fix(
        self,
        project_root: str,
        findings: List[Dict[str, Any]],
        max_iterations: int = 3,
    ) -> Dict[str, Any]:
        """Run the auto-fix loop on a list of findings.

        Applies template-based fixes where available, marks others for LLM
        review, and verifies via AST parse.

        Args:
            project_root:    Absolute path to the project root.
            findings:        List of finding dicts.
            max_iterations:  Max fix-verify iterations.

        Returns:
            Dict with keys: fixed (int), skipped (int), failed (int),
            fix_results (list), summary (str).
        """
        logger.info("[SonarQubeScanner] auto_fix() - %d findings", len(findings))
        return self._auto_fixer.run_fix_loop(
            project_root=project_root,
            findings=findings,
            max_iterations=max_iterations,
        )

    # ------------------------------------------------------------------
    # Installation detection
    # ------------------------------------------------------------------

    def detect(self) -> Dict[str, Any]:
        """Check SonarQube CLI and API availability.

        Returns:
            Dict with keys: installed, version, config_found, sonar_host_url,
            api_available, server_status.
        """
        try:
            return detect_sonar_installation()
        except Exception as exc:
            logger.error("[SonarQubeScanner] detect() failed: %s", exc)
            return {
                "installed": False,
                "version": None,
                "config_found": False,
                "sonar_host_url": None,
                "api_available": False,
                "server_status": "UNKNOWN",
            }
