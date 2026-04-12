"""
Result aggregator for SonarQube package.

Normalizes and categorizes findings from both the SonarQube REST API
(api_client.py) and the lightweight scanner (lightweight_scanner.py) into
a standard format consumed by the rest of the pipeline.

Public functions:
    aggregate_scan_result()  - Merge measures + gate into a scan result dict.
    categorize_findings()    - Bucket findings by severity, type, fixability.
    generate_fix_prompt()    - Build an LLM fix prompt for a single finding.

Version: 1.4.1
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CONTEXT_LINES = 10  # Lines of code context to include in fix prompts.


def _read_lines_around(file_path: str, line_no: int, context: int = _CONTEXT_LINES) -> str:
    """Read source lines around a given line number.

    Args:
        file_path: Absolute or relative path to the source file.
        line_no:   1-based line number of interest.
        context:   Number of lines before and after to include.

    Returns:
        Multi-line string with the target line marked by '>>>'.
        Returns empty string when the file cannot be read.
    """
    if not file_path or line_no <= 0:
        return ""

    try:
        path = Path(file_path)
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        logger.debug("Could not read %s for context: %s", file_path, exc)
        return ""

    start = max(0, line_no - context - 1)
    end = min(len(lines), line_no + context)
    snippet_lines: List[str] = []
    for idx in range(start, end):
        prefix = ">>>" if (idx + 1) == line_no else "   "
        snippet_lines.append("{} {:4d}: {}".format(prefix, idx + 1, lines[idx]))

    return "\n".join(snippet_lines)


# ---------------------------------------------------------------------------
# Auto-fixable rule set (rules where an LLM can likely produce a safe fix)
# ---------------------------------------------------------------------------

_AUTO_FIXABLE_RULES = frozenset(
    {
        # Python (lightweight scanner rules)
        "python:bare-except",
        "python:unused-import",
        "python:hardcoded-credentials",
        "python:todo-comment",
        "python:eval-exec",
        # Python (SonarQube rule IDs)
        "python:S1481",  # unused local variable
        "python:S1854",  # useless assignment
        "python:S1192",  # string literals duplicated
        "python:S2095",  # resource not closed
        "python:S1172",  # unused method parameter
        "python:S125",  # commented-out code
        # Multi-language
        "common-java:InlineComments",
        "Web:BoldAndItalicTagsCheck",
    }
)

# ---------------------------------------------------------------------------
# Public: aggregate_scan_result
# ---------------------------------------------------------------------------


def aggregate_scan_result(
    scan_result: Dict[str, Any],
    measures: Optional[Dict[str, Any]] = None,
    quality_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge API measures and quality gate data into a scan result dict.

    When measures are provided (from SonarQube REST API), the summary section
    of scan_result is replaced with richer data from the API.  Otherwise the
    existing summary is preserved.

    Args:
        scan_result:   Dict as returned by run_sonar_scan or run_basic_scan.
        measures:      Optional dict as returned by get_project_measures.
        quality_gate:  Optional dict as returned by get_quality_gate_status.

    Returns:
        Merged dict containing all original keys plus enriched summary.
    """
    result = dict(scan_result)

    if measures:
        quality_gate_str = measures.get("quality_gate", "UNKNOWN")
        if quality_gate_str == "OK":
            gate_label = "PASSED"
        elif quality_gate_str == "ERROR":
            gate_label = "FAILED"
        else:
            gate_label = "UNKNOWN"

        coverage = measures.get("coverage", -1.0)
        result["summary"] = {
            "bugs": measures.get("bugs", 0),
            "vulnerabilities": measures.get("vulnerabilities", 0),
            "code_smells": measures.get("code_smells", 0),
            "coverage_pct": coverage if coverage >= 0 else None,
            "quality_gate": gate_label,
        }
        logger.debug("[aggregate_scan_result] Using API measures: %s", result["summary"])

    if quality_gate:
        result["quality_gate_detail"] = quality_gate

    return result


# ---------------------------------------------------------------------------
# Public: categorize_findings
# ---------------------------------------------------------------------------


def categorize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Categorize findings by severity and type for pipeline consumption.

    Args:
        findings: List of finding dicts as returned by run_sonar_scan,
                  get_project_issues, or run_basic_scan.

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

    for finding in findings:
        severity = finding.get("severity", "").upper()
        finding_type = finding.get("type", "UNKNOWN")
        rule = finding.get("rule", "")

        # -- Severity buckets --
        if severity in ("CRITICAL", "BLOCKER"):
            critical.append(finding)
        elif severity == "MAJOR":
            major.append(finding)
        else:
            minor.append(finding)

        # -- Type grouping --
        if finding_type in by_type:
            by_type[finding_type].append(finding)
        else:
            by_type.setdefault(finding_type, []).append(finding)

        # -- Auto-fixable vs needs-review --
        is_vulnerability = finding_type == "VULNERABILITY"
        is_complex_bug = (
            finding_type == "BUG" and severity in ("CRITICAL", "BLOCKER", "MAJOR") and rule not in _AUTO_FIXABLE_RULES
        )

        if is_vulnerability or is_complex_bug:
            needs_review.append(finding)
        elif finding_type == "CODE_SMELL" or rule in _AUTO_FIXABLE_RULES:
            auto_fixable.append(finding)
        else:
            # Simple bugs (null checks, unused vars) -> auto_fixable
            message = finding.get("message", "").lower()
            _SIMPLE_PATTERNS = (
                "null",
                "unused",
                "import",
                "empty catch",
                "todo",
                "deprecated",
            )
            if any(pat in message for pat in _SIMPLE_PATTERNS):
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


# ---------------------------------------------------------------------------
# Public: generate_fix_prompt
# ---------------------------------------------------------------------------


def generate_fix_prompt(finding: Dict[str, Any]) -> str:
    """Generate an LLM fix prompt for a single SonarQube finding.

    Reads up to _CONTEXT_LINES lines of source context around the finding's
    line number and produces a focused prompt instructing the LLM how to fix
    the issue.

    Args:
        finding: A single finding dict from run_sonar_scan, get_project_issues,
                 or run_basic_scan.

    Returns:
        A prompt string ready to be sent to an LLM.
    """
    file_path = finding.get("file", "")
    line_no = finding.get("line", 0)
    rule = finding.get("rule", "")
    message = finding.get("message", "")
    severity = finding.get("severity", "UNKNOWN")
    finding_type = finding.get("type", "UNKNOWN")

    code_context = _read_lines_around(file_path, line_no)

    # Build a rule-specific suggested approach.
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
            "rename it to '_' or use '_unused' as a convention."
        )
    elif "except" in message.lower() or "exception" in rule_lower:
        approach = (
            "Narrow the exception type being caught. "
            "Replace bare 'except:' with 'except SpecificException as exc:' "
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
            "Move the credential to an environment variable or a secrets "
            "manager. Read it with os.getenv() and never commit it to source "
            "control."
        )
    elif "todo" in message.lower() or "fixme" in message.lower():
        approach = (
            "Implement the TODO/FIXME or convert it to a tracked GitHub issue " "and remove the comment from the code."
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

    parts = [
        "Fix the following SonarQube {} {} finding.".format(severity, finding_type),
        "",
        "File:     {}".format(file_path),
        "Line:     {}".format(line_no),
        "Rule:     {}".format(rule),
        "Severity: {}".format(severity),
        "Message:  {}".format(message),
        "",
    ]

    if code_context:
        parts += [
            "Code context (line marked with >>>):",
            "```",
            code_context,
            "```",
            "",
        ]

    parts += [
        "Suggested approach:",
        approach,
        "",
        "Instructions:",
        "1. Apply the minimal change needed to resolve the finding.",
        "2. Do not alter logic or formatting outside the affected area.",
        "3. Add or update a unit test if the change affects testable behaviour.",
        "4. Output only the corrected file content.",
    ]

    return "\n".join(parts)
