"""
SonarQube Scanner Integration

Integrates SonarQube/SonarCloud scanning into the pipeline after Step 10
(implementation) to detect bugs, vulnerabilities, and code smells.

If sonar-scanner CLI is not installed the module degrades gracefully:
  - Returns {installed: False, scan_success: False} immediately
  - Logs at DEBUG level only (SonarQube is optional)
  - Never crashes or blocks the pipeline

For users without SonarQube a lightweight fallback scanner is provided
using Python stdlib (AST + regex) to catch basic issues.

All functions are standalone (no class state) so they can be imported and
called directly from the pipeline or from tests without any setup.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_lines_around(file_path: str, line: int, context: int = 10) -> str:
    """Return up to *context* lines before and after *line* from *file_path*.

    Args:
        file_path: Absolute or relative path to the source file.
        line:      1-based line number of the finding.
        context:   Number of lines to include on each side.

    Returns:
        A formatted code snippet string, or an empty string on read error.
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return ""
        all_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, line - 1 - context)
        end = min(len(all_lines), line - 1 + context + 1)
        snippet_lines = []
        for idx in range(start, end):
            marker = ">>>" if idx == line - 1 else "   "
            snippet_lines.append(f"{marker} {idx + 1:4d} | {all_lines[idx]}")
        return "\n".join(snippet_lines)
    except Exception as exc:
        logger.debug("Could not read context for %s:%d: %s", file_path, line, exc)
        return ""


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


def _fetch_sonar_issues(
    sonar_host_url: str,
    project_key: str,
    sonar_token: Optional[str],
    created_after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Call the SonarQube REST API to fetch issues for *project_key*.

    Lazy-imports *urllib* so there is no top-level dependency on network libs.

    Args:
        sonar_host_url:  Base URL of SonarQube/SonarCloud (e.g. http://localhost:9000).
        project_key:     Project key from sonar-project.properties.
        sonar_token:     Optional SONAR_TOKEN for authenticated requests.
        created_after:   ISO-8601 datetime string to filter recent issues only.

    Returns:
        List of issue dicts as returned by the SonarQube API.
    """
    try:
        import urllib.request
        import urllib.parse
        import base64

        params: Dict[str, str] = {
            "componentKeys": project_key,
            "ps": "500",
        }
        if created_after:
            params["createdAfter"] = created_after

        url = (
            sonar_host_url.rstrip("/")
            + "/api/issues/search?"
            + urllib.parse.urlencode(params)
        )

        req = urllib.request.Request(url)
        if sonar_token:
            token_bytes = f"{sonar_token}:".encode("utf-8")
            req.add_header(
                "Authorization",
                "Basic " + base64.b64encode(token_bytes).decode("ascii"),
            )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("issues", [])

    except Exception as exc:
        logger.debug("SonarQube API call failed: %s", exc)
        return []


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
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_sonar_installation() -> Dict[str, Any]:
    """Check whether sonar-scanner CLI is installed and configured.

    Runs ``sonar-scanner --version`` with a short timeout to avoid blocking
    the pipeline.  Also checks for *sonar-project.properties* in the working
    directory and reads SONAR_HOST_URL / SONAR_TOKEN from the environment.

    Returns:
        Dict with keys:
            installed (bool):       True if sonar-scanner CLI was found.
            version (str | None):   Reported version string, or None.
            config_found (bool):    True if sonar-project.properties exists.
            sonar_host_url (str | None): Value from env or config, or None.
    """
    result: Dict[str, Any] = {
        "installed": False,
        "version": None,
        "config_found": False,
        "sonar_host_url": None,
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
            # Extract version from output (e.g. "SonarScanner 5.0.1.3006")
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
    host_url = os.environ.get("SONAR_HOST_URL")
    if not host_url and result["config_found"]:
        try:
            for raw_line in config_path.read_text(encoding="utf-8").splitlines():
                if raw_line.startswith("sonar.host.url"):
                    _, _, host_url = raw_line.partition("=")
                    host_url = host_url.strip()
                    break
        except Exception as exc:
            logger.debug("Could not read sonar-project.properties: %s", exc)

    result["sonar_host_url"] = host_url or None
    return result


def run_sonar_scan(
    project_root: str,
    modified_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run sonar-scanner and return parsed findings.

    Executes the sonar-scanner CLI against *project_root*.  If
    *modified_files* is provided the scan is narrowed to those paths using
    ``-Dsonar.inclusions``.

    After the scan completes the function reads
    ``.scannerwork/report-task.txt`` to locate the project key and then
    calls the SonarQube REST API to retrieve issue details.

    If sonar-scanner is not installed the function returns immediately with
    ``scan_success=False`` and does **not** raise.

    Args:
        project_root:    Absolute path to the project root directory.
        modified_files:  Optional list of relative file paths to restrict
                         the scan scope.

    Returns:
        Dict with keys:
            scan_success (bool):     True if the scan completed without error.
            findings (list):         List of finding dicts (may be empty).
            summary (dict):          Aggregated bug/vulnerability/smell counts.
            scan_duration_ms (int):  Wall-clock scan time in milliseconds.
            error (str | None):      Error message if scan_success is False.
    """
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
    }

    # Guard: check installation first
    install_info = detect_sonar_installation()
    if not install_info["installed"]:
        logger.debug(
            "sonar-scanner not installed; skipping scan of %s", project_root
        )
        empty_result["error"] = "sonar-scanner not installed"
        return empty_result

    root_path = Path(project_root)
    if not root_path.exists():
        empty_result["error"] = f"project_root does not exist: {project_root}"
        return empty_result

    # Build CLI command
    cmd: List[str] = [
        "sonar-scanner",
        f"-Dsonar.projectBaseDir={root_path}",
    ]
    if modified_files:
        inclusions = ",".join(modified_files)
        cmd.append(f"-Dsonar.inclusions={inclusions}")

    scan_start = time.monotonic()
    scan_start_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(root_path),
            timeout=300,  # 5 minute timeout
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - scan_start) * 1000)
        result = dict(empty_result)
        result["scan_duration_ms"] = elapsed
        result["error"] = "sonar-scanner timed out after 300 seconds"
        logger.warning("SonarQube scan timed out for %s", project_root)
        return result
    except Exception as exc:
        elapsed = int((time.monotonic() - scan_start) * 1000)
        result = dict(empty_result)
        result["scan_duration_ms"] = elapsed
        result["error"] = str(exc)
        logger.warning("SonarQube scan failed: %s", exc)
        return result

    elapsed_ms = int((time.monotonic() - scan_start) * 1000)

    if proc.returncode != 0:
        result = dict(empty_result)
        result["scan_duration_ms"] = elapsed_ms
        result["error"] = f"sonar-scanner exited with code {proc.returncode}"
        logger.warning("sonar-scanner non-zero exit: %s", proc.stderr[:500])
        return result

    # Parse report-task.txt for project key and server URL
    report_task_path = root_path / ".scannerwork" / "report-task.txt"
    report_info = _parse_report_task(report_task_path)

    project_key = report_info.get("projectKey", "")
    server_url = report_info.get("serverUrl", install_info.get("sonar_host_url") or "")
    sonar_token = os.environ.get("SONAR_TOKEN")

    # Fetch issues from API
    raw_issues: List[Dict[str, Any]] = []
    if project_key and server_url:
        raw_issues = _fetch_sonar_issues(
            server_url, project_key, sonar_token, created_after=scan_start_iso
        )
    else:
        logger.debug(
            "Could not determine project key or server URL; "
            "issue list will be empty (check sonar-project.properties)"
        )

    findings = [_sonar_issue_to_finding(issue) for issue in raw_issues]

    # Build summary from findings
    bugs = sum(1 for f in findings if f["type"] == "BUG")
    vulnerabilities = sum(1 for f in findings if f["type"] == "VULNERABILITY")
    code_smells = sum(1 for f in findings if f["type"] == "CODE_SMELL")

    # Quality gate status from report-task.txt (if available)
    quality_gate_status = report_info.get("qualityGateStatus", "UNKNOWN")
    if quality_gate_status not in ("OK", "WARN", "ERROR"):
        quality_gate_status = "UNKNOWN"
    quality_gate = "PASSED" if quality_gate_status == "OK" else (
        "FAILED" if quality_gate_status == "ERROR" else "UNKNOWN"
    )

    return {
        "scan_success": True,
        "findings": findings,
        "summary": {
            "bugs": bugs,
            "vulnerabilities": vulnerabilities,
            "code_smells": code_smells,
            "coverage_pct": None,  # Requires coverage reports; not parsed here
            "quality_gate": quality_gate,
        },
        "scan_duration_ms": elapsed_ms,
        "error": None,
    }


def categorize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Categorize findings by severity and type for pipeline consumption.

    Args:
        findings: List of finding dicts as returned by ``run_sonar_scan``.

    Returns:
        Dict with keys:
            critical (list):      Findings with severity CRITICAL or BLOCKER.
            major (list):         Findings with severity MAJOR.
            minor (list):         Findings with severity MINOR or INFO.
            by_type (dict):       Findings grouped by type key.
            auto_fixable (list):  Findings Claude can likely fix automatically.
            needs_review (list):  Findings requiring human judgment.
    """
    critical: List[Dict[str, Any]] = []
    major: List[Dict[str, Any]] = []
    minor: List[Dict[str, Any]] = []

    by_type: Dict[str, List[Dict[str, Any]]] = {
        "BUG": [],
        "VULNERABILITY": [],
        "CODE_SMELL": [],
    }

    auto_fixable: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []

    # Rule patterns that are typically auto-fixable by an LLM
    _AUTO_FIXABLE_RULES = {
        # Python
        "python:S1481",   # unused local variable
        "python:S1854",   # useless assignment
        "python:S1192",   # string literals duplicated
        "python:S2095",   # resource not closed
        "python:S1172",   # unused method parameter
        "python:S125",    # commented-out code
        # General / multi-language
        "common-java:InlineComments",
        "Web:BoldAndItalicTagsCheck",
    }

    for finding in findings:
        severity = finding.get("severity", "").upper()
        finding_type = finding.get("type", "UNKNOWN")
        rule = finding.get("rule", "")

        # Severity buckets
        if severity in ("CRITICAL", "BLOCKER"):
            critical.append(finding)
        elif severity == "MAJOR":
            major.append(finding)
        else:
            minor.append(finding)

        # Type grouping
        if finding_type in by_type:
            by_type[finding_type].append(finding)
        else:
            by_type.setdefault(finding_type, []).append(finding)

        # Auto-fixable vs needs-review
        is_vulnerability = finding_type == "VULNERABILITY"
        is_complex_bug = (
            finding_type == "BUG"
            and severity in ("CRITICAL", "BLOCKER", "MAJOR")
            and rule not in _AUTO_FIXABLE_RULES
        )

        if is_vulnerability or is_complex_bug:
            needs_review.append(finding)
        elif finding_type == "CODE_SMELL" or rule in _AUTO_FIXABLE_RULES:
            auto_fixable.append(finding)
        else:
            # Simple bugs (null checks, unused vars) -> auto_fixable
            message = finding.get("message", "").lower()
            simple_patterns = (
                "null",
                "unused",
                "import",
                "empty catch",
                "todo",
                "deprecated",
            )
            if any(pat in message for pat in simple_patterns):
                auto_fixable.append(finding)
            else:
                needs_review.append(finding)

    return {
        "critical": critical,
        "major": major,
        "minor": minor,
        "by_type": by_type,
        "auto_fixable": auto_fixable,
        "needs_review": needs_review,
    }


def create_issues_for_findings(
    project_root: str,
    findings: List[Dict[str, Any]],
    max_issues: int = 5,
) -> Dict[str, Any]:
    """Auto-create GitHub issues for Critical/Major SonarQube findings.

    Uses the ``gh`` CLI (lazy import pattern) to create issues.  If ``gh``
    is not available or GitHub credentials are not configured the function
    returns gracefully with ``issues_created=0``.

    At most *max_issues* GitHub issues are created per call to avoid spam.
    Only CRITICAL and MAJOR severity findings are promoted to issues; lower
    severity findings are counted as skipped.

    Args:
        project_root:  Path to the project root (used for context only).
        findings:      List of finding dicts to consider.
        max_issues:    Hard cap on the number of issues created (default 5).

    Returns:
        Dict with keys:
            issues_created (int):  Number of GitHub issues actually created.
            issue_ids (list):      GitHub issue numbers as ints.
            skipped (int):         Findings not promoted to a GitHub issue.
    """
    result: Dict[str, Any] = {
        "issues_created": 0,
        "issue_ids": [],
        "skipped": 0,
    }

    # Filter to only actionable severity levels
    actionable = [
        f for f in findings
        if f.get("severity", "").upper() in ("CRITICAL", "BLOCKER", "MAJOR")
    ]
    skipped = len(findings) - len(actionable)
    result["skipped"] = skipped

    if not actionable:
        logger.debug("No critical/major findings; no GitHub issues will be created")
        return result

    # Check gh CLI availability
    try:
        check = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if check.returncode != 0:
            logger.debug("gh CLI not available; skipping GitHub issue creation")
            result["skipped"] += len(actionable)
            return result
    except Exception as exc:
        logger.debug("gh CLI check failed: %s; skipping issue creation", exc)
        result["skipped"] += len(actionable)
        return result

    created = 0
    for finding in actionable:
        if created >= max_issues:
            result["skipped"] += len(actionable) - created
            break

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

        try:
            proc = subprocess.run(
                [
                    "gh", "issue", "create",
                    "--title", title,
                    "--body", body,
                    "--label", "sonarqube",
                    "--label", "auto-detected",
                ],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=30,
            )
            if proc.returncode == 0:
                # Output is the issue URL; extract number from trailing segment
                url = proc.stdout.strip()
                try:
                    issue_number = int(url.rstrip("/").rsplit("/", 1)[-1])
                    result["issue_ids"].append(issue_number)
                except ValueError:
                    pass
                created += 1
                logger.debug("Created GitHub issue for %s:%d", file_path, line_no)
            else:
                logger.debug(
                    "gh issue create failed (rc=%d): %s",
                    proc.returncode,
                    proc.stderr[:200],
                )
                result["skipped"] += 1
        except Exception as exc:
            logger.debug("GitHub issue creation error: %s", exc)
            result["skipped"] += 1

    result["issues_created"] = created
    return result


def generate_fix_prompt(finding: Dict[str, Any]) -> str:
    """Generate a fix prompt for a single SonarQube finding.

    Reads up to 10 lines of source context around the finding's line number
    and produces a focused prompt instructing Claude (or another LLM) how to
    fix the issue.

    Args:
        finding: A single finding dict from ``run_sonar_scan`` or
                 ``run_basic_scan``.

    Returns:
        A prompt string ready to be sent to an LLM.
    """
    file_path = finding.get("file", "")
    line_no = finding.get("line", 0)
    rule = finding.get("rule", "")
    message = finding.get("message", "")
    severity = finding.get("severity", "UNKNOWN")
    finding_type = finding.get("type", "UNKNOWN")

    code_context = _read_lines_around(file_path, line_no, context=10)

    # Build a rule-specific suggested approach
    rule_lower = rule.lower()
    if "null" in rule_lower or "none" in message.lower():
        approach = (
            "Add a None/null check before dereferencing the value, "
            "or use the Optional/Maybe pattern to express nullability explicitly."
        )
    elif "unused" in rule_lower or "unused" in message.lower():
        approach = (
            "Remove the unused variable, parameter, or import. "
            "If the value is intentionally unused (e.g. loop variable), "
            "rename it to `_` or use `_unused` as a convention."
        )
    elif "except" in message.lower() or "exception" in rule_lower:
        approach = (
            "Narrow the exception type being caught. "
            "Replace bare `except:` with `except SpecificException as exc:` "
            "and handle or re-raise it explicitly."
        )
    elif "eval" in message.lower() or "exec" in message.lower():
        approach = (
            "Replace eval()/exec() with a safe alternative: "
            "ast.literal_eval() for data parsing, "
            "importlib for dynamic imports, "
            "or a strategy pattern for dynamic dispatch."
        )
    elif "password" in message.lower() or "credential" in message.lower():
        approach = (
            "Move the credential to an environment variable or a secrets manager. "
            "Read it with os.getenv() and never commit it to source control."
        )
    elif "todo" in message.lower() or "fixme" in message.lower():
        approach = (
            "Implement the TODO/FIXME or convert it to a tracked GitHub issue "
            "and remove the comment from the code."
        )
    elif "complexity" in message.lower():
        approach = (
            "Reduce cyclomatic complexity by extracting helper functions, "
            "using early returns to eliminate nesting, "
            "or replacing long if/elif chains with a dispatch table."
        )
    elif finding_type == "VULNERABILITY":
        approach = (
            "This is a security vulnerability. "
            "Consult the OWASP guidelines for the relevant rule. "
            "Do not suppress without a documented justification."
        )
    else:
        approach = (
            "Review the rule documentation and apply the recommended fix. "
            "Ensure the fix does not change observable behaviour."
        )

    prompt_parts = [
        f"Fix the following SonarQube {severity} {finding_type} finding.",
        "",
        f"File:     {file_path}",
        f"Line:     {line_no}",
        f"Rule:     {rule}",
        f"Severity: {severity}",
        f"Message:  {message}",
        "",
    ]

    if code_context:
        prompt_parts += [
            "Code context (line marked with >>>):",
            "```",
            code_context,
            "```",
            "",
        ]

    prompt_parts += [
        "Suggested approach:",
        approach,
        "",
        "Instructions:",
        "1. Apply the minimal change needed to resolve the finding.",
        "2. Do not alter logic or formatting outside the affected area.",
        "3. Add or update a unit test if the change affects testable behaviour.",
        "4. Output only the corrected file content.",
    ]

    return "\n".join(prompt_parts)


# ---------------------------------------------------------------------------
# Lightweight fallback scanner (no SonarQube required)
# ---------------------------------------------------------------------------

def run_basic_scan(
    project_root: str,
    modified_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Lightweight code scan without SonarQube using AST and regex.

    Checks for a fixed set of patterns that are commonly problematic:
      - Bare ``except:`` clauses
      - ``eval()`` / ``exec()`` usage
      - Hardcoded passwords / tokens (regex heuristic)
      - TODO / FIXME / HACK comments
      - Unused imports (basic AST walk)
      - Functions longer than 50 lines
      - Cyclomatic complexity > 10 (rough AST estimate)

    Only Python (``.py``) files are analysed.

    Args:
        project_root:   Absolute path to the project root directory.
        modified_files: Optional list of relative paths to restrict the scan.
                        When omitted all ``.py`` files under *project_root*
                        are scanned.

    Returns:
        Dict with the same schema as ``run_sonar_scan``:
            scan_success, findings, summary, scan_duration_ms, error.
    """
    start = time.monotonic()
    root_path = Path(project_root)

    if not root_path.exists():
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
            "error": f"project_root does not exist: {project_root}",
        }

    # Resolve target files
    if modified_files:
        target_files = [
            root_path / f for f in modified_files
            if f.endswith(".py") and (root_path / f).exists()
        ]
    else:
        target_files = list(root_path.rglob("*.py"))

    # Exclude virtual envs and common non-project dirs
    _SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", "dist", "build"}
    target_files = [
        p for p in target_files
        if not any(part in _SKIP_DIRS for part in p.parts)
    ]

    findings: List[Dict[str, Any]] = []

    # Regex patterns (compiled once)
    _RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
    _RE_EVAL_EXEC = re.compile(r"\beval\s*\(|\bexec\s*\(")
    _RE_CREDENTIALS = re.compile(
        r"(?i)(password|passwd|secret|api_key|apikey|token|auth)\s*=\s*[\"'][^\"']{4,}[\"']"
    )
    _RE_TODO = re.compile(r"#\s*(TODO|FIXME|HACK)\b", re.IGNORECASE)

    for file_path in target_files:
        rel_path = str(file_path.relative_to(root_path))

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Could not read %s: %s", file_path, exc)
            continue

        lines = source.splitlines()

        # --- Line-by-line regex checks ---
        for lineno, raw_line in enumerate(lines, start=1):
            if _RE_BARE_EXCEPT.match(raw_line):
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "severity": "MAJOR",
                    "type": "BUG",
                    "rule": "python:bare-except",
                    "message": "Bare 'except:' clause catches all exceptions including SystemExit",
                })

            if _RE_EVAL_EXEC.search(raw_line):
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "severity": "CRITICAL",
                    "type": "VULNERABILITY",
                    "rule": "python:eval-exec",
                    "message": "Use of eval()/exec() is a security risk",
                })

            if _RE_CREDENTIALS.search(raw_line):
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "severity": "BLOCKER",
                    "type": "VULNERABILITY",
                    "rule": "python:hardcoded-credentials",
                    "message": "Potential hardcoded credential or secret detected",
                })

            if _RE_TODO.search(raw_line):
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "severity": "INFO",
                    "type": "CODE_SMELL",
                    "rule": "python:todo-comment",
                    "message": f"TODO/FIXME/HACK comment: {raw_line.strip()[:100]}",
                })

        # --- AST-based checks ---
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            logger.debug("Syntax error in %s; skipping AST checks", file_path)
            continue

        # Unused imports (simple: names imported but not referenced in the file)
        import_names: Dict[str, int] = {}  # name -> lineno
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound_name = alias.asname if alias.asname else alias.name.split(".")[0]
                    import_names[bound_name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    bound_name = alias.asname if alias.asname else alias.name
                    if bound_name != "*":
                        import_names[bound_name] = node.lineno

        # Count name usages in the source (cheap proxy)
        for name, imp_lineno in import_names.items():
            # Count occurrences excluding the import line itself
            other_lines = [
                l for idx, l in enumerate(lines, 1) if idx != imp_lineno
            ]
            usage_count = sum(
                1 for l in other_lines
                if re.search(r"\b" + re.escape(name) + r"\b", l)
            )
            if usage_count == 0:
                findings.append({
                    "file": rel_path,
                    "line": imp_lineno,
                    "severity": "MINOR",
                    "type": "CODE_SMELL",
                    "rule": "python:unused-import",
                    "message": f"Unused import: '{name}'",
                })

        # Function length and cyclomatic complexity
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_start = node.lineno
                func_end = getattr(node, "end_lineno", func_start)
                func_len = func_end - func_start + 1

                if func_len > 50:
                    findings.append({
                        "file": rel_path,
                        "line": func_start,
                        "severity": "MAJOR",
                        "type": "CODE_SMELL",
                        "rule": "python:function-too-long",
                        "message": (
                            f"Function '{node.name}' is {func_len} lines long "
                            f"(threshold: 50)"
                        ),
                    })

                # Rough cyclomatic complexity: count branching nodes
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(
                        child,
                        (
                            ast.If,
                            ast.For,
                            ast.While,
                            ast.ExceptHandler,
                            ast.With,
                            ast.Assert,
                            ast.comprehension,
                        ),
                    ):
                        complexity += 1
                    elif isinstance(child, ast.BoolOp):
                        complexity += len(child.values) - 1

                if complexity > 10:
                    findings.append({
                        "file": rel_path,
                        "line": func_start,
                        "severity": "MAJOR",
                        "type": "CODE_SMELL",
                        "rule": "python:cognitive-complexity",
                        "message": (
                            f"Function '{node.name}' has estimated cyclomatic "
                            f"complexity of {complexity} (threshold: 10)"
                        ),
                    })

    elapsed_ms = int((time.monotonic() - start) * 1000)

    bugs = sum(1 for f in findings if f["type"] == "BUG")
    vulnerabilities = sum(1 for f in findings if f["type"] == "VULNERABILITY")
    code_smells = sum(1 for f in findings if f["type"] == "CODE_SMELL")
    quality_gate = "PASSED" if (bugs == 0 and vulnerabilities == 0) else "FAILED"

    return {
        "scan_success": True,
        "findings": findings,
        "summary": {
            "bugs": bugs,
            "vulnerabilities": vulnerabilities,
            "code_smells": code_smells,
            "coverage_pct": None,
            "quality_gate": quality_gate,
        },
        "scan_duration_ms": elapsed_ms,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def scan_and_report(
    project_root: str,
    modified_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Full scan pipeline: detect -> scan -> categorize -> report.

    Tries SonarQube first; if not installed falls back to ``run_basic_scan``.
    The returned dict combines the scan result with the categorized findings.

    Args:
        project_root:   Absolute path to the project root directory.
        modified_files: Optional list of relative file paths to restrict scope.

    Returns:
        Combined dict containing all keys from ``run_sonar_scan`` plus:
            sonar_installed (bool):    Whether sonar-scanner was found.
            scanner_used (str):        "sonarqube" or "basic".
            categories (dict):         Output of ``categorize_findings``.
    """
    install_info = detect_sonar_installation()
    sonar_installed = install_info["installed"]

    if sonar_installed:
        scan_result = run_sonar_scan(project_root, modified_files)
        scanner_used = "sonarqube"
    else:
        logger.debug(
            "SonarQube not installed; using lightweight basic scanner for %s",
            project_root,
        )
        scan_result = run_basic_scan(project_root, modified_files)
        scanner_used = "basic"

    findings = scan_result.get("findings", [])
    categories = categorize_findings(findings)

    return {
        **scan_result,
        "sonar_installed": sonar_installed,
        "scanner_used": scanner_used,
        "categories": categories,
    }
