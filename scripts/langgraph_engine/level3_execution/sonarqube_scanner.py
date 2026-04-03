"""Backward-compat shim for sonarqube_scanner.py.

All scanning logic has been refactored into the sonarqube/ sub-package.
This file re-exports all public symbols so existing imports keep working.

Windows-safe: ASCII only, no Unicode characters.
"""

from .sonarqube import (  # noqa: F401
    SonarAutoFixer,
    SonarQubeScanner,
    aggregate_scan_result,
    categorize_findings,
    create_issues_for_findings,
    detect_sonar_installation,
    generate_fix_prompt,
    get_project_issues,
    get_project_measures,
    get_quality_gate_status,
    get_sonar_config,
    run_basic_scan,
    run_sonar_scan,
    scan_and_report,
)
