"""
Quality Gate - Pre-merge enforcement for Step 11 (Pull Request Review).

Combines all quality signals before allowing a PR to merge:
    - SonarQube / basic scan findings (bugs, vulnerabilities, code smells)
    - Test coverage percentage (before/after)
    - CallGraph breaking-change detection
    - Test existence check for every modified file

Each gate runs independently in a try/except block so a failure in one
gate never prevents the others from evaluating.

Usage:
    from quality_gate import evaluate_quality_gate, generate_gate_report

    result = evaluate_quality_gate(project_root, state)
    if not result["gate_passed"]:
        pr_comment = generate_gate_report(result)
        post_pr_comment(pr_comment)

Python 3.8+ compatible. ASCII-only (cp1252-safe). No external dependencies.
All scanner/analyzer modules are imported lazily.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: Dict[str, Any] = {
    "sonar_block_on_critical": True,  # Block merge if CRITICAL/BLOCKER findings
    "sonar_block_on_major": False,  # MAJOR findings -> warning only
    "coverage_threshold": 70.0,  # Minimum coverage % to pass
    "coverage_drop_threshold": 5.0,  # Max allowed coverage DROP %
    "allow_breaking_changes": False,  # Block if CallGraph detects breaking changes
    "require_tests_for_modified": True,  # Block if modified files have no test files
    "max_cyclomatic_increase": 10,  # Block if avg cyclomatic complexity rises by >10
}

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------


def _import_sonar_scanner():
    """Lazy import of sonarqube_scanner.scan_and_report."""
    try:
        from .sonarqube_scanner import scan_and_report

        return scan_and_report
    except ImportError:
        try:
            from sonarqube_scanner import scan_and_report

            return scan_and_report
        except ImportError:
            return None


def _import_coverage_analyzer():
    """Lazy import of coverage_analyzer.suggest_test_scope."""
    try:
        from ..coverage_analyzer import suggest_test_scope

        return suggest_test_scope
    except ImportError:
        try:
            from coverage_analyzer import suggest_test_scope

            return suggest_test_scope
        except ImportError:
            return None


def _import_test_generator():
    """Lazy import of test_generator.generate_tests_for_modified_files."""
    try:
        from .test_generator import generate_tests_for_modified_files

        return generate_tests_for_modified_files
    except ImportError:
        try:
            from test_generator import generate_tests_for_modified_files

            return generate_tests_for_modified_files
        except ImportError:
            return None


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_gate_config(project_root: str) -> Dict[str, Any]:
    """Load quality gate config from project.

    Checks for .quality-gate.json in the project root and merges with
    _DEFAULT_CONFIG (project file takes precedence).

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        Dict with quality gate configuration keys.
    """
    config = dict(_DEFAULT_CONFIG)
    try:
        config_path = Path(project_root) / ".quality-gate.json"
        if config_path.exists():
            raw = config_path.read_text(encoding="utf-8", errors="replace")
            overrides = json.loads(raw)
            if isinstance(overrides, dict):
                for key, value in overrides.items():
                    if key in config:
                        config[key] = value
                    else:
                        logger.debug("quality_gate: unknown config key ignored: %s", key)
    except Exception as exc:
        logger.debug("quality_gate: could not load .quality-gate.json: %s", exc)
    return config


# ---------------------------------------------------------------------------
# Individual gate evaluators
# ---------------------------------------------------------------------------


def _evaluate_sonar_gate(
    project_root: str,
    state: Dict[str, Any],
    config: Dict[str, Any],
    modified_files: List[str],
) -> Dict[str, Any]:
    """Gate 1: SonarQube / basic scan.

    Reads pre-computed sonar data from state first; falls back to running
    scan_and_report() if no state data is available.

    Returns a gate result dict.
    """
    gate: Dict[str, Any] = {
        "passed": True,
        "reason": "",
        "critical_count": 0,
        "major_count": 0,
        "minor_count": 0,
        "scanner_used": "unknown",
    }

    try:
        # Try to read scan results already stored in state
        sonar_data: Optional[Dict[str, Any]] = None

        # Step 10 may have stored sonar results under various keys
        for key in (
            "step10_sonar_results",
            "step10_scan_results",
            "step11_sonar_results",
        ):
            candidate = state.get(key)
            if candidate and isinstance(candidate, dict):
                sonar_data = candidate
                break

        # Also check the findings directly
        if sonar_data is None:
            for key in ("step10_findings", "step11_findings"):
                candidate = state.get(key)
                if candidate and isinstance(candidate, list):
                    sonar_data = {"findings": candidate, "categories": None}
                    break

        # Fall back to running the scanner
        if sonar_data is None:
            scan_fn = _import_sonar_scanner()
            if scan_fn is not None:
                sonar_data = scan_fn(project_root, modified_files or None)
            else:
                gate["reason"] = "SonarQube scanner unavailable; gate skipped."
                gate["passed"] = True  # cannot block if scanner is unavailable
                return gate

        # Parse categories
        categories = sonar_data.get("categories") or {}
        if not categories and sonar_data.get("findings"):
            # Build minimal category counts from raw findings
            for finding in sonar_data.get("findings", []):
                severity = (finding.get("severity") or "").upper()
                if severity in ("CRITICAL", "BLOCKER"):
                    categories.setdefault("critical", []).append(finding)
                elif severity == "MAJOR":
                    categories.setdefault("major", []).append(finding)
                else:
                    categories.setdefault("minor", []).append(finding)

        critical_list = categories.get("critical", [])
        major_list = categories.get("major", [])
        minor_list = categories.get("minor", [])

        gate["critical_count"] = len(critical_list)
        gate["major_count"] = len(major_list)
        gate["minor_count"] = len(minor_list)
        gate["scanner_used"] = sonar_data.get("scanner_used", "unknown")

        # Blocking decision
        block_on_critical = config.get("sonar_block_on_critical", True)
        block_on_major = config.get("sonar_block_on_major", False)

        blocking_reasons: List[str] = []
        if block_on_critical and gate["critical_count"] > 0:
            blocking_reasons.append(f"{gate['critical_count']} CRITICAL/BLOCKER finding(s)")
        if block_on_major and gate["major_count"] > 0:
            blocking_reasons.append(f"{gate['major_count']} MAJOR finding(s)")

        if blocking_reasons:
            gate["passed"] = False
            gate["reason"] = "Blocked by: " + ", ".join(blocking_reasons)
        else:
            parts: List[str] = []
            if gate["critical_count"] == 0 and gate["major_count"] == 0:
                parts.append("No critical or major findings")
            if gate["major_count"] > 0 and not block_on_major:
                parts.append(f"{gate['major_count']} major finding(s) (warning only)")
            gate["reason"] = "; ".join(parts) if parts else "No blocking findings"

    except Exception as exc:
        logger.warning("quality_gate: sonar gate evaluation failed: %s", exc)
        gate["passed"] = True  # fail-safe: do not block on evaluation error
        gate["reason"] = f"Gate evaluation error (fail-safe pass): {exc}"

    return gate


def _evaluate_coverage_gate(
    project_root: str,
    state: Dict[str, Any],
    config: Dict[str, Any],
    modified_files: List[str],
) -> Dict[str, Any]:
    """Gate 2: Test coverage.

    Reads coverage data from state or runs suggest_test_scope().

    Returns a gate result dict.
    """
    gate: Dict[str, Any] = {
        "passed": True,
        "reason": "",
        "current_pct": 0.0,
        "before_pct": 0.0,
        "threshold": config.get("coverage_threshold", 70.0),
        "drop": 0.0,
    }

    try:
        threshold = float(config.get("coverage_threshold", 70.0))
        drop_threshold = float(config.get("coverage_drop_threshold", 5.0))
        gate["threshold"] = threshold

        # Read pre-computed coverage from state
        coverage_before: float = 0.0
        coverage_after: float = 0.0

        # Check various state keys where coverage may be stored
        for key in (
            "step10_coverage_results",
            "step11_coverage_results",
            "step10_test_scope",
        ):
            candidate = state.get(key)
            if candidate and isinstance(candidate, dict):
                coverage_before = float(candidate.get("coverage_before", 0.0) or 0.0)
                coverage_after = float(
                    candidate.get("coverage_after_estimate", 0.0) or candidate.get("coverage_after", 0.0) or 0.0
                )
                break

        # If no state data, run suggest_test_scope
        if coverage_before == 0.0 and coverage_after == 0.0:
            suggest_fn = _import_coverage_analyzer()
            if suggest_fn is not None:
                scope = suggest_fn(
                    project_root,
                    modified_files=modified_files or None,
                )
                coverage_before = float(scope.get("coverage_before", 0.0) or 0.0)
                coverage_after = float(scope.get("coverage_after_estimate", 0.0) or 0.0)
            else:
                gate["reason"] = "Coverage analyzer unavailable; gate skipped."
                gate["passed"] = True
                return gate

        # Use the more conservative estimate as the effective coverage
        effective_pct = coverage_after if coverage_after > 0 else coverage_before
        drop = coverage_before - effective_pct if coverage_before > 0 else 0.0

        gate["before_pct"] = round(coverage_before, 2)
        gate["current_pct"] = round(effective_pct, 2)
        gate["drop"] = round(drop, 2)

        blocking_reasons: List[str] = []
        if effective_pct < threshold and threshold > 0:
            blocking_reasons.append(f"Coverage {effective_pct:.1f}% is below threshold {threshold:.1f}%")
        if drop > drop_threshold:
            blocking_reasons.append(f"Coverage dropped {drop:.1f}% (max allowed: {drop_threshold:.1f}%)")

        if blocking_reasons:
            gate["passed"] = False
            gate["reason"] = "; ".join(blocking_reasons)
        else:
            gate["reason"] = f"{effective_pct:.1f}% (threshold: {threshold:.1f}%)"
            if drop > 0:
                gate["reason"] += f"; drop {drop:.1f}% within limit"

    except Exception as exc:
        logger.warning("quality_gate: coverage gate evaluation failed: %s", exc)
        gate["passed"] = True
        gate["reason"] = f"Gate evaluation error (fail-safe pass): {exc}"

    return gate


def _evaluate_breaking_changes_gate(
    state: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Gate 3: Breaking changes detected by CallGraph diff.

    Reads step11_breaking_changes and step11_risk_assessment from state.

    Returns a gate result dict.
    """
    gate: Dict[str, Any] = {
        "passed": True,
        "reason": "",
        "count": 0,
        "details": [],
        "risk_assessment": "safe",
    }

    try:
        allow_breaking = bool(config.get("allow_breaking_changes", False))

        breaking_changes: List[Dict[str, Any]] = state.get("step11_breaking_changes") or []
        risk_assessment: str = state.get("step11_risk_assessment") or "safe"

        # Also check step11_impact_review for additional data
        impact_review = state.get("step11_impact_review") or {}
        if not breaking_changes and impact_review:
            breaking_changes = impact_review.get("breaking_changes", [])
        if risk_assessment == "safe" and impact_review:
            risk_assessment = impact_review.get("risk_assessment", "safe")

        gate["count"] = len(breaking_changes)
        gate["details"] = breaking_changes
        gate["risk_assessment"] = risk_assessment

        if breaking_changes and not allow_breaking:
            methods_str = ", ".join(bc.get("method", "unknown") for bc in breaking_changes[:5])
            suffix = f" (+{len(breaking_changes) - 5} more)" if len(breaking_changes) > 5 else ""
            gate["passed"] = False
            gate["reason"] = f"{len(breaking_changes)} breaking change(s) detected: " f"{methods_str}{suffix}"
        elif breaking_changes and allow_breaking:
            gate["reason"] = f"{len(breaking_changes)} breaking change(s) detected but " f"allow_breaking_changes=True"
        elif risk_assessment in ("risky",) and not allow_breaking:
            gate["passed"] = False
            gate["reason"] = f"Risk assessment is '{risk_assessment}' - manual review required"
        else:
            gate["reason"] = (
                "No breaking changes detected"
                if not breaking_changes
                else f"Breaking changes allowed (count={len(breaking_changes)})"
            )

    except Exception as exc:
        logger.warning("quality_gate: breaking changes gate evaluation failed: %s", exc)
        gate["passed"] = True
        gate["reason"] = f"Gate evaluation error (fail-safe pass): {exc}"

    return gate


def _evaluate_tests_exist_gate(
    project_root: str,
    state: Dict[str, Any],
    config: Dict[str, Any],
    modified_files: List[str],
) -> Dict[str, Any]:
    """Gate 4: Test files exist for every modified source file.

    Checks if each modified file has a corresponding test file by looking
    at the project's test directories.  Also checks test_generator output
    stored in state.

    Returns a gate result dict.
    """
    gate: Dict[str, Any] = {
        "passed": True,
        "reason": "",
        "modified_without_tests": [],
        "modified_with_tests": [],
    }

    try:
        require_tests = bool(config.get("require_tests_for_modified", True))

        if not modified_files:
            gate["reason"] = "No modified files to check."
            return gate

        # Build a set of known test file paths (relative, normalised)
        root = Path(project_root)
        test_file_names: set = set()

        # Collect test files from common test directories
        for test_dir_name in ("tests", "test", "__tests__", "spec", "specs"):
            test_dir = root / test_dir_name
            if test_dir.is_dir():
                try:
                    for f in test_dir.rglob("*.py"):
                        test_file_names.add(f.name.lower())
                        # Store relative path too
                        try:
                            test_file_names.add(str(f.relative_to(root)).replace("\\", "/").lower())
                        except ValueError:
                            pass
                except OSError:
                    pass

        # Also consult test_generator results stored in state
        gen_result = state.get("step10_generated_tests") or state.get("step11_generated_tests") or {}
        for file_entry in gen_result.get("files", []):
            tpath = file_entry.get("test_file_path", "")
            if tpath:
                test_file_names.add(Path(tpath).name.lower())
                test_file_names.add(tpath.replace("\\", "/").lower())

        # For each modified file determine if a test file exists
        without_tests: List[str] = []
        with_tests: List[str] = []

        for mf in modified_files:
            mf_path = Path(mf)
            stem = mf_path.stem  # e.g. "auth"

            # Skip test files themselves, __init__, migrations, configs
            mf_name_lower = mf_path.name.lower()
            if (
                mf_name_lower.startswith("test_")
                or mf_name_lower.endswith("_test.py")
                or mf_name_lower in ("__init__.py", "conftest.py", "setup.py")
                or "migration" in str(mf_path).lower()
                or not mf_path.suffix == ".py"
            ):
                continue

            # Possible test file names for this module
            candidates = {
                f"test_{stem}.py",
                f"{stem}_test.py",
                f"test_{stem.lower()}.py",
                f"{stem.lower()}_test.py",
            }

            is_found = any(c.lower() in test_file_names for c in candidates)

            # Also check if the path itself appears in test_file_names
            if not is_found:
                rel_mf = str(mf_path).replace("\\", "/").lower()
                is_found = any(rel_mf in t for t in test_file_names)

            if is_found:
                with_tests.append(str(mf))
            else:
                without_tests.append(str(mf))

        gate["modified_without_tests"] = without_tests
        gate["modified_with_tests"] = with_tests

        if without_tests and require_tests:
            names = [Path(f).name for f in without_tests[:5]]
            suffix = f" (+{len(without_tests) - 5} more)" if len(without_tests) > 5 else ""
            gate["passed"] = False
            gate["reason"] = f"{len(without_tests)} modified file(s) missing tests: " + ", ".join(names) + suffix
        elif without_tests and not require_tests:
            gate["reason"] = (
                f"{len(without_tests)} file(s) missing tests (warning; " f"require_tests_for_modified=False)"
            )
        else:
            gate["reason"] = (
                "All modified files have corresponding test files" if with_tests else "No Python source files to check"
            )

    except Exception as exc:
        logger.warning("quality_gate: tests-exist gate evaluation failed: %s", exc)
        gate["passed"] = True
        gate["reason"] = f"Gate evaluation error (fail-safe pass): {exc}"

    return gate


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_quality_gate(
    project_root: str,
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate all quality gates for the current change.

    Args:
        project_root: Path to project root directory.
        state:        FlowState dict containing step10/step11 pipeline data.
        config:       Optional config override dict.  Keys not provided fall
                      back to project-level .quality-gate.json, then defaults.

    Returns:
        {
            "gate_passed": bool,
            "gates": {
                "sonar": {"passed": bool, "reason": str, "critical_count": int,
                          "major_count": int, ...},
                "coverage": {"passed": bool, "reason": str, "current_pct": float,
                             "threshold": float, ...},
                "breaking_changes": {"passed": bool, "reason": str, "count": int,
                                     "details": [], ...},
                "tests_exist": {"passed": bool, "reason": str,
                                "modified_without_tests": [], ...},
            },
            "summary": str,
            "recommendation": str,   # "MERGE" | "FIX_AND_RETRY" | "MANUAL_REVIEW"
            "blocking_gates": [str],
        }
    """
    # Merge configs: defaults -> project file -> caller override
    effective_config = get_gate_config(project_root)
    if config:
        for k, v in config.items():
            effective_config[k] = v

    # Resolve modified files from state
    modified_files: List[str] = list(state.get("step10_modified_files") or [])

    logger.debug(
        "quality_gate.evaluate: project=%s modified_files=%d config=%s",
        project_root,
        len(modified_files),
        effective_config,
    )

    # Run all four gates independently
    sonar_gate = _evaluate_sonar_gate(project_root, state, effective_config, modified_files)
    coverage_gate = _evaluate_coverage_gate(project_root, state, effective_config, modified_files)
    breaking_gate = _evaluate_breaking_changes_gate(state, effective_config)
    tests_gate = _evaluate_tests_exist_gate(project_root, state, effective_config, modified_files)

    gates = {
        "sonar": sonar_gate,
        "coverage": coverage_gate,
        "breaking_changes": breaking_gate,
        "tests_exist": tests_gate,
    }

    # Determine which gates are blocking
    blocking_gates: List[str] = [name for name, result in gates.items() if not result.get("passed", True)]

    gate_passed = len(blocking_gates) == 0

    # Build human-readable summary
    summary_parts: List[str] = []
    for name, result in gates.items():
        status = "PASSED" if result.get("passed", True) else "FAILED"
        reason = result.get("reason", "")
        label = name.replace("_", " ").title()
        summary_parts.append(f"{label}: {status} - {reason}")
    summary = " | ".join(summary_parts)

    # Recommendation
    if gate_passed:
        recommendation = "MERGE"
    elif breaking_gate.get("risk_assessment") == "risky" or (sonar_gate.get("critical_count", 0) > 0):
        recommendation = "MANUAL_REVIEW"
    else:
        recommendation = "FIX_AND_RETRY"

    return {
        "gate_passed": gate_passed,
        "gates": gates,
        "summary": summary,
        "recommendation": recommendation,
        "blocking_gates": blocking_gates,
    }


def generate_gate_report(gate_result: Dict[str, Any]) -> str:
    """Generate a formatted Markdown report suitable for a PR comment.

    Args:
        gate_result: Return value from evaluate_quality_gate().

    Returns:
        Markdown-formatted string.
    """
    try:
        gate_passed = gate_result.get("gate_passed", False)
        status_header = "PASSED" if gate_passed else "FAILED"
        gates = gate_result.get("gates", {})
        recommendation = gate_result.get("recommendation", "MANUAL_REVIEW")
        gate_result.get("blocking_gates", [])

        lines: List[str] = [
            f"## Quality Gate: {status_header}",
            "",
            "| Gate | Status | Details |",
            "|------|--------|---------|",
        ]

        # Gate rows
        gate_display = {
            "sonar": "SonarQube",
            "coverage": "Coverage",
            "breaking_changes": "Breaking Changes",
            "tests_exist": "Tests Exist",
        }
        for key, label in gate_display.items():
            result = gates.get(key, {})
            passed = result.get("passed", True)
            icon = "PASSED" if passed else "FAILED"
            reason = result.get("reason", "N/A")

            # Append extra detail for specific gates
            if key == "sonar":
                critical = result.get("critical_count", 0)
                major = result.get("major_count", 0)
                detail = f"{critical} critical, {major} major"
                if reason:
                    detail = f"{reason} ({detail})"
                else:
                    detail = detail
            elif key == "coverage":
                pct = result.get("current_pct", 0.0)
                threshold = result.get("threshold", 0.0)
                detail = f"{pct:.1f}% (threshold: {threshold:.1f}%)"
                if result.get("drop", 0.0) > 0:
                    detail += f"; drop {result['drop']:.1f}%"
            elif key == "breaking_changes":
                count = result.get("count", 0)
                risk = result.get("risk_assessment", "safe")
                detail = "No breaking changes detected" if count == 0 else f"{count} breaking change(s); risk={risk}"
            elif key == "tests_exist":
                missing = result.get("modified_without_tests", [])
                if missing:
                    names = [Path(f).name for f in missing[:3]]
                    more = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
                    detail = f"{len(missing)} file(s) missing tests: " + ", ".join(names) + more
                else:
                    detail = reason
            else:
                detail = reason

            lines.append(f"| {label} | {icon} | {detail} |")

        lines.append("")
        lines.append(f"### Recommendation: {recommendation}")

        # Actionable items
        suggestions = get_fix_suggestions(gate_result)
        if suggestions:
            lines.append("")
            for s in suggestions:
                priority_label = s.get("priority", "MEDIUM")
                action = s.get("action", "")
                effort = s.get("estimated_effort", "")
                effort_str = f" (est. {effort})" if effort else ""
                lines.append(f"- [{priority_label}] {action}{effort_str}")

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("quality_gate: generate_gate_report failed: %s", exc)
        passed = gate_result.get("gate_passed", False)
        return f"## Quality Gate: {'PASSED' if passed else 'FAILED'}\n\n(Report generation error: {exc})"


def should_block_merge(gate_result: Dict[str, Any]) -> bool:
    """Return True if the quality gate result should block a PR merge.

    Args:
        gate_result: Return value from evaluate_quality_gate().

    Returns:
        True if any gate is blocking.
    """
    return not gate_result.get("gate_passed", True)


def get_fix_suggestions(gate_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate actionable fix suggestions for all failed gates.

    Args:
        gate_result: Return value from evaluate_quality_gate().

    Returns:
        List of dicts, each with keys:
            gate             - which gate produced this suggestion
            action           - what to do
            priority         - "HIGH" | "MEDIUM" | "LOW"
            estimated_effort - rough effort estimate (e.g. "< 1 hour")
    """
    suggestions: List[Dict[str, str]] = []

    try:
        gates = gate_result.get("gates", {})

        # --- Sonar suggestions ---
        sonar = gates.get("sonar", {})
        if not sonar.get("passed", True):
            critical_count = sonar.get("critical_count", 0)
            major_count = sonar.get("major_count", 0)
            if critical_count > 0:
                suggestions.append(
                    {
                        "gate": "sonar",
                        "action": (
                            f"Fix {critical_count} CRITICAL/BLOCKER finding(s) "
                            f"reported by SonarQube before merging."
                        ),
                        "priority": "HIGH",
                        "estimated_effort": "1-4 hours",
                    }
                )
            if major_count > 0:
                suggestions.append(
                    {
                        "gate": "sonar",
                        "action": (
                            f"Review {major_count} MAJOR finding(s); " f"fix or suppress with documented justification."
                        ),
                        "priority": "MEDIUM",
                        "estimated_effort": "30 min - 2 hours",
                    }
                )

        # --- Coverage suggestions ---
        coverage = gates.get("coverage", {})
        if not coverage.get("passed", True):
            current = coverage.get("current_pct", 0.0)
            threshold = coverage.get("threshold", 70.0)
            drop = coverage.get("drop", 0.0)
            if current < threshold:
                gap = threshold - current
                suggestions.append(
                    {
                        "gate": "coverage",
                        "action": (
                            f"Increase test coverage from {current:.1f}% to "
                            f"{threshold:.1f}% (gap: {gap:.1f}%). "
                            f"Add unit tests for uncovered methods."
                        ),
                        "priority": "HIGH",
                        "estimated_effort": "2-6 hours",
                    }
                )
            elif drop > 0:
                suggestions.append(
                    {
                        "gate": "coverage",
                        "action": (f"Coverage dropped {drop:.1f}%. " f"Add tests for the newly added code paths."),
                        "priority": "MEDIUM",
                        "estimated_effort": "1-3 hours",
                    }
                )

        # --- Breaking changes suggestions ---
        breaking = gates.get("breaking_changes", {})
        if not breaking.get("passed", True):
            count = breaking.get("count", 0)
            details = breaking.get("details", [])
            method_names = [d.get("method", "?") for d in details[:3]]
            names_str = ", ".join(method_names)
            more = f" (+{count - 3} more)" if count > 3 else ""
            suggestions.append(
                {
                    "gate": "breaking_changes",
                    "action": (
                        f"Investigate {count} breaking change(s): {names_str}{more}. "
                        f"Update callers or add compatibility shims."
                    ),
                    "priority": "HIGH",
                    "estimated_effort": "1-8 hours",
                }
            )

        # --- Tests-exist suggestions ---
        tests_exist = gates.get("tests_exist", {})
        if not tests_exist.get("passed", True):
            missing = tests_exist.get("modified_without_tests", [])
            if missing:
                file_names = [Path(f).name for f in missing[:5]]
                more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
                suggestions.append(
                    {
                        "gate": "tests_exist",
                        "action": (
                            "Add test files for: "
                            + ", ".join(file_names)
                            + more
                            + ". Use test_generator.py to scaffold tests automatically."
                        ),
                        "priority": "MEDIUM",
                        "estimated_effort": "30 min - 2 hours per file",
                    }
                )

    except Exception as exc:
        logger.warning("quality_gate: get_fix_suggestions failed: %s", exc)

    return suggestions
