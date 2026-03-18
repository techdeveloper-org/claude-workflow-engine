"""
SonarQube Auto-Fixer

Takes SonarQube/basic scan findings and generates fix instructions for Claude
to apply.  Implements a fix-verify loop that:

  1. Plans which findings to address (priority-sorted, capped at max_fixes).
  2. Generates Claude-compatible fix instructions per finding.
  3. Applies template-based fixes directly for common patterns.
  4. Re-scans to verify fixes reduced the finding count.
  5. Iterates up to max_iterations times if new issues appear.

Finding schema (from sonarqube_scanner.py):
    {
        "file":     str,   # relative path from project root
        "line":     int,   # 1-based line number
        "severity": str,   # CRITICAL | BLOCKER | MAJOR | MINOR | INFO
        "type":     str,   # BUG | VULNERABILITY | CODE_SMELL
        "rule":     str,   # e.g. "python:bare-except"
        "message":  str,   # human-readable description
    }

All functions are fail-safe: they never raise; errors are returned in the
result dict or logged at DEBUG level.

ASCII-only source (cp1252 safe for Windows).
Python 3.8+ compatible.
"""

from __future__ import annotations

import ast
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority constants
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: Dict[str, int] = {
    "BLOCKER": 0,
    "CRITICAL": 1,
    "MAJOR": 2,
    "MINOR": 3,
    "INFO": 4,
    "UNKNOWN": 5,
}

_TYPE_ORDER: Dict[str, int] = {
    "BUG": 0,
    "VULNERABILITY": 1,
    "CODE_SMELL": 2,
    "UNKNOWN": 3,
}

# Rules that have deterministic template fixes (no LLM required)
_TEMPLATE_RULES = {
    "python:bare-except",
    "python:unused-import",
    "python:hardcoded-credentials",
    "python:todo-comment",
    "python:eval-exec",
}

# Rules that need LLM guidance only (no safe auto-edit)
_LLM_ONLY_RULES = {
    "python:function-too-long",
    "python:cognitive-complexity",
}


# ---------------------------------------------------------------------------
# 1. plan_fixes
# ---------------------------------------------------------------------------

def plan_fixes(
    findings: List[Dict[str, Any]],
    max_fixes: int = 10,
) -> List[Dict[str, Any]]:
    """Plan which findings to fix and in what order.

    Priority: CRITICAL > BLOCKER > MAJOR > MINOR
    Within same severity: BUG > VULNERABILITY > CODE_SMELL

    Args:
        findings:  List of finding dicts from the scanner.
        max_fixes: Maximum number of findings to return (default 10).

    Returns:
        List of finding dicts sorted by priority, capped at max_fixes.
    """
    if not findings:
        return []

    def _sort_key(f: Dict[str, Any]) -> tuple:
        sev = str(f.get("severity", "UNKNOWN")).upper()
        ftype = str(f.get("type", "UNKNOWN")).upper()
        return (
            _SEVERITY_ORDER.get(sev, 5),
            _TYPE_ORDER.get(ftype, 3),
            str(f.get("file", "")),
            int(f.get("line", 0)),
        )

    sorted_findings = sorted(findings, key=_sort_key)
    return sorted_findings[:max_fixes]


# ---------------------------------------------------------------------------
# 2. generate_fix_instruction
# ---------------------------------------------------------------------------

def generate_fix_instruction(
    finding: Dict[str, Any],
    source_context: str = "",
) -> Dict[str, Any]:
    """Generate a Claude-compatible fix instruction for one finding.

    For a known template rule the function also supplies the exact code
    replacement so the caller can apply it without an LLM.

    Args:
        finding:        A single finding dict.
        source_context: Optional pre-read source text of the affected file.
                        When provided, the function reads the specific line
                        directly instead of re-reading the file.

    Returns:
        Dict with keys:
            file (str):           Relative file path.
            line (int):           1-based line number.
            instruction (str):    Human-readable fix instruction.
            fix_type (str):       "auto" if a template fix is available,
                                  "llm" if an LLM is required.
            template_fix (str | None): The replacement line (or None for
                                       llm-type fixes).
    """
    file_path = str(finding.get("file", ""))
    line_no = int(finding.get("line", 0))
    rule = str(finding.get("rule", ""))
    message = str(finding.get("message", ""))
    severity = str(finding.get("severity", "UNKNOWN"))
    finding_type = str(finding.get("type", "UNKNOWN"))

    # Retrieve the specific source line if we have content
    source_line = ""
    if source_context and line_no > 0:
        lines = source_context.splitlines()
        if 0 < line_no <= len(lines):
            source_line = lines[line_no - 1]
    elif file_path and line_no > 0:
        source_line = _read_line(file_path, line_no)

    rule_lower = rule.lower()
    fix_type = "llm"
    template_fix: Optional[str] = None
    instruction = ""

    # ------------------------------------------------------------------
    # bare_except  ->  except Exception:
    # ------------------------------------------------------------------
    if "bare-except" in rule_lower:
        fix_type = "auto"
        if source_line:
            # Replace "except:" with "except Exception:" preserving indent
            template_fix = source_line.rstrip().replace("except:", "except Exception:", 1)
        else:
            template_fix = None
        instruction = (
            "Replace the bare 'except:' clause with 'except Exception:' "
            "(or a more specific exception type if the context is known). "
            "Bare except clauses also catch SystemExit and KeyboardInterrupt, "
            "which should not be silently swallowed."
        )

    # ------------------------------------------------------------------
    # eval_usage  ->  comment with warning + suggest ast.literal_eval
    # ------------------------------------------------------------------
    elif "eval-exec" in rule_lower or "eval" in rule_lower:
        fix_type = "auto"
        if source_line:
            indent = len(source_line) - len(source_line.lstrip())
            indent_str = source_line[:indent]
            template_fix = (
                indent_str
                + "# WARNING: eval/exec removed - use ast.literal_eval() for data "
                "or importlib for dynamic imports\n"
                + source_line
            )
        else:
            template_fix = None
        instruction = (
            "Remove or replace eval()/exec(). "
            "For parsing data literals use ast.literal_eval(). "
            "For dynamic imports use importlib.import_module(). "
            "Add a comment explaining why the safer alternative is used."
        )

    # ------------------------------------------------------------------
    # unused_import  ->  remove the line
    # ------------------------------------------------------------------
    elif "unused-import" in rule_lower:
        fix_type = "auto"
        # Signal removal by returning an empty string sentinel
        template_fix = ""  # empty string = delete this line
        instruction = (
            "Remove the unused import. "
            "If the import is needed at runtime for its side-effects "
            "(e.g. Django app registration), add a comment explaining why."
        )

    # ------------------------------------------------------------------
    # todo_fixme  ->  flag only, no code change
    # ------------------------------------------------------------------
    elif "todo" in rule_lower or "todo" in message.lower():
        fix_type = "llm"
        template_fix = None
        instruction = (
            "Review this TODO/FIXME/HACK comment. "
            "Either implement the described change, convert it to a tracked "
            "GitHub issue and remove the comment, or remove it entirely if "
            "it is no longer relevant."
        )

    # ------------------------------------------------------------------
    # hardcoded_password  ->  replace with os.environ.get("VAR_NAME")
    # ------------------------------------------------------------------
    elif "hardcoded-credentials" in rule_lower or "credential" in rule_lower:
        # Extract the variable name from the source line if possible
        var_name = _extract_var_name(source_line)
        env_var = var_name.upper() if var_name else "SECRET_VALUE"
        fix_type = "auto"
        if source_line and var_name:
            indent = len(source_line) - len(source_line.lstrip())
            indent_str = source_line[:indent]
            template_fix = (
                indent_str
                + f'{var_name} = os.environ.get("{env_var}", "")'
            )
        else:
            template_fix = None
        instruction = (
            f"Move the hardcoded credential to an environment variable. "
            f"Replace the literal with os.environ.get(\"{env_var}\") "
            f"and document the variable in .env.example. "
            f"Never commit credentials to source control."
        )

    # ------------------------------------------------------------------
    # function_too_long  ->  suggest split (no auto-fix)
    # ------------------------------------------------------------------
    elif "function-too-long" in rule_lower:
        fix_type = "llm"
        template_fix = None
        instruction = (
            "This function exceeds the 50-line threshold. "
            "Extract cohesive blocks into well-named helper functions. "
            "Use the Single Responsibility Principle as a guide: "
            "each helper should do exactly one thing. "
            "Consider whether parts of the logic belong in a separate class."
        )

    # ------------------------------------------------------------------
    # cognitive / cyclomatic complexity  ->  suggest refactor (no auto-fix)
    # ------------------------------------------------------------------
    elif "complexity" in rule_lower or "complexity" in message.lower():
        fix_type = "llm"
        template_fix = None
        instruction = (
            "Reduce cyclomatic/cognitive complexity. "
            "Strategies: "
            "(1) Replace long if/elif chains with a dispatch dict or strategy pattern. "
            "(2) Use early returns to flatten nesting. "
            "(3) Extract nested loops and conditions into named helper functions. "
            "(4) Replace complex boolean expressions with descriptive variables."
        )

    # ------------------------------------------------------------------
    # vulnerability (generic)
    # ------------------------------------------------------------------
    elif finding_type == "VULNERABILITY":
        fix_type = "llm"
        template_fix = None
        instruction = (
            f"Security vulnerability detected: {message}. "
            "Consult the OWASP guidelines for rule '{rule}'. "
            "Do not suppress this finding without documented justification. "
            "Review the affected code carefully before applying any change."
        )

    # ------------------------------------------------------------------
    # fallback
    # ------------------------------------------------------------------
    else:
        fix_type = "llm"
        template_fix = None
        instruction = (
            f"Fix the {severity} {finding_type} finding: {message}. "
            "Apply the minimal change needed. "
            "Do not alter logic or formatting outside the affected area. "
            "Add or update a unit test if the change affects testable behaviour."
        )

    return {
        "file": file_path,
        "line": line_no,
        "instruction": instruction,
        "fix_type": fix_type,
        "template_fix": template_fix,
    }


# ---------------------------------------------------------------------------
# 3. apply_template_fix
# ---------------------------------------------------------------------------

def apply_template_fix(
    file_path: str,
    fix: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply a template-based fix directly to a file.

    Only for fix_type="auto" fixes.  Creates a .bak backup before editing.
    Verifies the file parses correctly after the edit; restores from backup
    if ast.parse fails.

    Args:
        file_path: Absolute or relative path to the file to modify.
        fix:       Fix instruction dict as returned by generate_fix_instruction.

    Returns:
        Dict with keys:
            applied (bool):         True if the fix was written to disk.
            backup_created (bool):  True if a .bak file was created.
            error (str | None):     Error message if applied is False.
    """
    result: Dict[str, Any] = {
        "applied": False,
        "backup_created": False,
        "error": None,
    }

    if fix.get("fix_type") != "auto":
        result["error"] = "fix_type is not 'auto'; skipping apply"
        return result

    template_fix = fix.get("template_fix")
    if template_fix is None:
        result["error"] = "template_fix is None; nothing to apply"
        return result

    line_no = int(fix.get("line", 0))
    if line_no <= 0:
        result["error"] = f"invalid line number: {line_no}"
        return result

    p = Path(file_path)
    if not p.exists():
        result["error"] = f"file does not exist: {file_path}"
        return result

    # Read original content
    try:
        original_text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = f"could not read file: {exc}"
        return result

    original_lines = original_text.splitlines(keepends=True)
    if line_no > len(original_lines):
        result["error"] = (
            f"line {line_no} is out of range "
            f"(file has {len(original_lines)} lines)"
        )
        return result

    # Create backup
    backup_path = p.with_suffix(p.suffix + ".bak")
    try:
        shutil.copy2(str(p), str(backup_path))
        result["backup_created"] = True
    except Exception as exc:
        result["error"] = f"could not create backup: {exc}"
        return result

    # Build new content
    idx = line_no - 1  # 0-based index
    if template_fix == "":
        # Empty string sentinel -> delete the line
        new_lines = original_lines[:idx] + original_lines[idx + 1:]
    else:
        # Replace the line; preserve the original line ending
        original_ending = ""
        orig_line = original_lines[idx]
        if orig_line.endswith("\r\n"):
            original_ending = "\r\n"
        elif orig_line.endswith("\n"):
            original_ending = "\n"
        elif orig_line.endswith("\r"):
            original_ending = "\r"

        new_line = template_fix.rstrip("\r\n") + original_ending
        new_lines = original_lines[:idx] + [new_line] + original_lines[idx + 1:]

    new_text = "".join(new_lines)

    # Verify parse (Python files only)
    if p.suffix == ".py":
        try:
            ast.parse(new_text, filename=str(p))
        except SyntaxError as exc:
            # Restore from backup
            try:
                shutil.copy2(str(backup_path), str(p))
            except Exception:
                pass
            result["error"] = (
                f"syntax error after applying fix (restored from backup): {exc}"
            )
            return result

    # Write new content
    try:
        p.write_text(new_text, encoding="utf-8")
        result["applied"] = True
    except Exception as exc:
        # Attempt to restore from backup
        try:
            shutil.copy2(str(backup_path), str(p))
        except Exception:
            pass
        result["error"] = f"could not write file: {exc}"

    return result


# ---------------------------------------------------------------------------
# 4. run_fix_loop
# ---------------------------------------------------------------------------

def run_fix_loop(
    project_root: str,
    findings: List[Dict[str, Any]],
    max_iterations: int = 3,
) -> Dict[str, Any]:
    """Run the fix-verify loop.

    Steps per iteration:
        1. Plan fixes from current findings list.
        2. Apply template fixes (auto-fixable ones).
        3. Re-scan to verify fixes worked (uses run_basic_scan - fast).
        4. If new issues found, repeat (up to max_iterations).
        5. Stop early if no progress (same count after fix attempt).

    Args:
        project_root:    Absolute path to the project root directory.
        findings:        Initial list of findings to work through.
        max_iterations:  Maximum fix-verify cycles (default 3).

    Returns:
        Dict with keys:
            iterations (int):            Number of iterations completed.
            findings_initial (int):      Count at the start.
            findings_fixed (int):        Count resolved by auto-fixes.
            findings_remaining (int):    Count after all iterations.
            fixes_applied (list):        Per-fix result records.
            llm_fixes_needed (list):     Findings requiring LLM intervention.
            success (bool):              True if all auto-fixable findings resolved.
    """
    # Lazy import to avoid circular dependency
    try:
        from scripts.langgraph_engine import sonarqube_scanner as _scanner
    except ImportError:
        try:
            import sonarqube_scanner as _scanner  # type: ignore[no-redef]
        except ImportError:
            _scanner = None  # type: ignore[assignment]

    result: Dict[str, Any] = {
        "iterations": 0,
        "findings_initial": len(findings),
        "findings_fixed": 0,
        "findings_remaining": len(findings),
        "fixes_applied": [],
        "llm_fixes_needed": [],
        "success": False,
    }

    if not findings:
        result["success"] = True
        return result

    current_findings = list(findings)
    initial_count = len(findings)
    all_fixes_applied: List[Dict[str, Any]] = []
    llm_needed: List[Dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        result["iterations"] = iteration
        prev_count = len(current_findings)

        # Step 1: plan
        planned = plan_fixes(current_findings, max_fixes=10)
        if not planned:
            break

        # Step 2: generate and apply template fixes
        iteration_applied = 0
        iteration_llm: List[Dict[str, Any]] = []

        for finding in planned:
            fix_instruction = generate_fix_instruction(finding)

            fix_record: Dict[str, Any] = {
                "file": finding.get("file", ""),
                "line": finding.get("line", 0),
                "rule": finding.get("rule", ""),
                "severity": finding.get("severity", ""),
                "fix_type": fix_instruction["fix_type"],
                "applied": False,
                "error": None,
            }

            if fix_instruction["fix_type"] == "auto":
                # Resolve absolute file path
                abs_path = _resolve_abs_path(project_root, finding.get("file", ""))
                apply_result = apply_template_fix(abs_path, fix_instruction)
                fix_record["applied"] = apply_result["applied"]
                fix_record["error"] = apply_result.get("error")
                if apply_result["applied"]:
                    iteration_applied += 1
            else:
                iteration_llm.append(finding)

            all_fixes_applied.append(fix_record)

        # Accumulate unique LLM-needed findings (avoid duplicates)
        _seen_llm = {
            (f.get("file"), f.get("line"), f.get("rule"))
            for f in llm_needed
        }
        for f in iteration_llm:
            key = (f.get("file"), f.get("line"), f.get("rule"))
            if key not in _seen_llm:
                llm_needed.append(f)
                _seen_llm.add(key)

        # Step 3: re-scan to verify
        new_count = prev_count
        if iteration_applied > 0 and _scanner is not None:
            try:
                scan_result = _scanner.run_basic_scan(project_root)
                if scan_result.get("scan_success"):
                    current_findings = scan_result.get("findings", [])
                    new_count = len(current_findings)
                else:
                    logger.debug(
                        "Re-scan failed on iteration %d: %s",
                        iteration,
                        scan_result.get("error"),
                    )
            except Exception as exc:
                logger.debug("Re-scan error on iteration %d: %s", iteration, exc)
        elif iteration_applied == 0:
            # Nothing was auto-applied; no point re-scanning
            break

        # Step 4: stop if no progress
        if new_count >= prev_count and iteration_applied > 0:
            logger.debug(
                "No progress in iteration %d (%d -> %d findings); stopping",
                iteration,
                prev_count,
                new_count,
            )
            break

        # Stop if all findings resolved
        if new_count == 0:
            break

    # Build final counts
    final_remaining = len(current_findings) if _scanner is not None else len(findings)
    fixed_count = max(0, initial_count - final_remaining)

    # Determine success: all auto-fixable findings resolved
    auto_fixable_in_plan = sum(
        1 for r in all_fixes_applied if r.get("fix_type") == "auto"
    )
    auto_fixes_applied = sum(
        1 for r in all_fixes_applied if r.get("applied") is True
    )
    success = (auto_fixable_in_plan > 0 and auto_fixes_applied == auto_fixable_in_plan)

    result["findings_fixed"] = fixed_count
    result["findings_remaining"] = final_remaining
    result["fixes_applied"] = all_fixes_applied
    result["llm_fixes_needed"] = llm_needed
    result["success"] = success

    return result


# ---------------------------------------------------------------------------
# 5. get_fix_summary
# ---------------------------------------------------------------------------

def get_fix_summary(fix_result: Dict[str, Any]) -> str:
    """Generate a human-readable summary of the fix loop results.

    Suitable for logging and PR comment bodies.

    Args:
        fix_result: The dict returned by run_fix_loop.

    Returns:
        Formatted multi-line summary string.
    """
    iterations = int(fix_result.get("iterations", 0))
    initial = int(fix_result.get("findings_initial", 0))
    fixed = int(fix_result.get("findings_fixed", 0))
    remaining = int(fix_result.get("findings_remaining", 0))
    success = bool(fix_result.get("success", False))
    fixes_applied = fix_result.get("fixes_applied", [])
    llm_needed = fix_result.get("llm_fixes_needed", [])

    auto_count = sum(1 for f in fixes_applied if f.get("fix_type") == "auto")
    auto_ok = sum(1 for f in fixes_applied if f.get("applied") is True)
    auto_failed = auto_count - auto_ok

    lines: List[str] = [
        "## SonarQube Auto-Fix Summary",
        "",
        f"- **Initial findings:** {initial}",
        f"- **Auto-fixed:** {fixed}",
        f"- **Remaining:** {remaining}",
        f"- **Iterations:** {iterations}",
        f"- **Status:** {'SUCCESS' if success else 'PARTIAL / NEEDS REVIEW'}",
        "",
    ]

    if fixes_applied:
        lines.append("### Template Fixes Applied")
        lines.append("")
        applied_records = [f for f in fixes_applied if f.get("applied") is True]
        if applied_records:
            for rec in applied_records:
                lines.append(
                    f"- `{rec.get('file', 'unknown')}` "
                    f"line {rec.get('line', '?')} "
                    f"({rec.get('severity', '?')} {rec.get('rule', '?')})"
                )
        else:
            lines.append("- None applied successfully")
        lines.append("")

    if auto_failed > 0:
        lines.append("### Template Fixes That Failed")
        lines.append("")
        failed_records = [
            f for f in fixes_applied
            if f.get("fix_type") == "auto" and not f.get("applied")
        ]
        for rec in failed_records:
            err = rec.get("error") or "unknown error"
            lines.append(
                f"- `{rec.get('file', 'unknown')}` "
                f"line {rec.get('line', '?')}: {err}"
            )
        lines.append("")

    if llm_needed:
        lines.append("### Findings Requiring Manual / LLM Review")
        lines.append("")
        for finding in llm_needed:
            sev = finding.get("severity", "?")
            ftype = finding.get("type", "?")
            ffile = finding.get("file", "unknown")
            fline = finding.get("line", "?")
            msg = finding.get("message", "")
            lines.append(f"- **{sev} {ftype}** `{ffile}`:{fline} - {msg}")
        lines.append("")

    if remaining == 0:
        lines.append("> All findings resolved by auto-fix loop.")
    elif success:
        lines.append("> All auto-fixable findings resolved. Manual review needed for the rest.")
    else:
        lines.append("> Some auto-fixes could not be applied. See failures above.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_line(file_path: str, line_no: int) -> str:
    """Read a single line from a file (1-based).  Returns empty string on error."""
    try:
        p = Path(file_path)
        if not p.exists():
            return ""
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if 0 < line_no <= len(lines):
            return lines[line_no - 1]
    except Exception as exc:
        logger.debug("Could not read line %d from %s: %s", line_no, file_path, exc)
    return ""


def _extract_var_name(source_line: str) -> str:
    """Extract the left-hand side variable name from an assignment line.

    Example: '    password = "secret"' -> 'password'

    Returns empty string if extraction fails.
    """
    try:
        stripped = source_line.strip()
        if "=" in stripped:
            lhs = stripped.split("=", 1)[0].strip()
            # Accept simple identifiers only
            if lhs.isidentifier():
                return lhs
    except Exception:
        pass
    return ""


def _resolve_abs_path(project_root: str, relative_path: str) -> str:
    """Join project_root and relative_path into an absolute string path."""
    try:
        root = Path(project_root)
        full = root / relative_path
        return str(full)
    except Exception:
        return relative_path
