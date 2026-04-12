"""
Lightweight fallback scanner for SonarQube package.

Provides run_basic_scan() - an AST + regex-based Python code scanner that
runs without any SonarQube installation.  Used as the final fallback when
neither the SonarQube REST API nor the sonar-scanner CLI is available.

Checks performed:
  - Bare except: clauses
  - eval() / exec() usage
  - Hardcoded credentials / secrets (regex heuristic)
  - TODO / FIXME / HACK comments
  - Unused imports (basic AST walk)
  - Functions longer than 50 lines
  - Cyclomatic complexity > 10 (rough AST estimate)

Only Python (.py) files are analysed.

Returns dicts with the same schema as api_client.run_sonar_scan so that the
rest of the pipeline can treat both sources identically.

Version: 1.4.1
"""

import ast
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Directories to skip during file discovery.
_SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", "dist", "build"}

# Compiled regex patterns (module-level to avoid recompiling per file).
_RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
_RE_EVAL_EXEC = re.compile(r"\beval\s*\(|\bexec\s*\(")
_RE_CREDENTIALS = re.compile(r"(?i)(password|passwd|secret|api_key|apikey|token|auth)\s*=\s*[\"'][^\"']{4,}[\"']")
_RE_TODO = re.compile(r"#\s*(TODO|FIXME|HACK)\b", re.IGNORECASE)


def _scan_file_lines(rel_path: str, lines: List[str]) -> List[Dict[str, Any]]:
    """Run line-by-line regex checks on a single file.

    Args:
        rel_path: Relative path string used in finding dicts.
        lines:    Lines of the file (as returned by str.splitlines()).

    Returns:
        List of finding dicts for this file.
    """
    findings: List[Dict[str, Any]] = []

    for lineno, raw_line in enumerate(lines, start=1):
        if _RE_BARE_EXCEPT.match(raw_line):
            findings.append(
                {
                    "file": rel_path,
                    "line": lineno,
                    "severity": "MAJOR",
                    "type": "BUG",
                    "rule": "python:bare-except",
                    "message": ("Bare 'except:' clause catches all exceptions " "including SystemExit"),
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": [],
                }
            )

        if _RE_EVAL_EXEC.search(raw_line):
            findings.append(
                {
                    "file": rel_path,
                    "line": lineno,
                    "severity": "CRITICAL",
                    "type": "VULNERABILITY",
                    "rule": "python:eval-exec",
                    "message": "Use of eval()/exec() is a security risk",
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": ["security"],
                }
            )

        if _RE_CREDENTIALS.search(raw_line):
            findings.append(
                {
                    "file": rel_path,
                    "line": lineno,
                    "severity": "BLOCKER",
                    "type": "VULNERABILITY",
                    "rule": "python:hardcoded-credentials",
                    "message": "Potential hardcoded credential or secret detected",
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": ["security", "credentials"],
                }
            )

        if _RE_TODO.search(raw_line):
            findings.append(
                {
                    "file": rel_path,
                    "line": lineno,
                    "severity": "INFO",
                    "type": "CODE_SMELL",
                    "rule": "python:todo-comment",
                    "message": "TODO/FIXME/HACK comment: {}".format(raw_line.strip()[:100]),
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": [],
                }
            )

    return findings


def _scan_file_ast(rel_path: str, source: str, lines: List[str]) -> List[Dict[str, Any]]:
    """Run AST-based checks on a single file.

    Checks:
      - Unused imports (names imported but not referenced elsewhere).
      - Function length > 50 lines.
      - Cyclomatic complexity > 10.

    Args:
        rel_path: Relative path string used in finding dicts.
        source:   Full source text of the file.
        lines:    Lines of the file (for usage counting).

    Returns:
        List of finding dicts for this file.  Returns empty list on
        SyntaxError so the caller can continue with other files.
    """
    findings: List[Dict[str, Any]] = []

    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        logger.debug("Syntax error in %s; skipping AST checks", rel_path)
        return findings

    # -- Unused imports --
    import_names: Dict[str, int] = {}  # bound_name -> lineno
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

    for name, imp_lineno in import_names.items():
        other_lines = [line for idx, line in enumerate(lines, 1) if idx != imp_lineno]
        usage_count = sum(1 for line in other_lines if re.search(r"\b" + re.escape(name) + r"\b", line))
        if usage_count == 0:
            findings.append(
                {
                    "file": rel_path,
                    "line": imp_lineno,
                    "severity": "MINOR",
                    "type": "CODE_SMELL",
                    "rule": "python:unused-import",
                    "message": "Unused import: '{}'".format(name),
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": [],
                }
            )

    # -- Function length and cyclomatic complexity --
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_start = node.lineno
        func_end = getattr(node, "end_lineno", func_start)
        func_len = func_end - func_start + 1

        if func_len > 50:
            findings.append(
                {
                    "file": rel_path,
                    "line": func_start,
                    "severity": "MAJOR",
                    "type": "CODE_SMELL",
                    "rule": "python:function-too-long",
                    "message": ("Function '{}' is {} lines long (threshold: 50)".format(node.name, func_len)),
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": [],
                }
            )

        # Rough cyclomatic complexity: count branching nodes.
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
            findings.append(
                {
                    "file": rel_path,
                    "line": func_start,
                    "severity": "MAJOR",
                    "type": "CODE_SMELL",
                    "rule": "python:cognitive-complexity",
                    "message": (
                        "Function '{}' has estimated cyclomatic complexity of "
                        "{} (threshold: 10)".format(node.name, complexity)
                    ),
                    "status": "",
                    "effort": "",
                    "debt": "",
                    "tags": [],
                }
            )

    return findings


def _resolve_target_files(
    root_path: Path,
    modified_files: Optional[List[str]],
) -> List[Path]:
    """Resolve the list of Python files to scan.

    Args:
        root_path:      Resolved project root Path.
        modified_files: Optional list of relative file paths.  When None, all
                        .py files under root_path are discovered.

    Returns:
        Filtered list of Path objects (non-existent paths are excluded).
    """
    if modified_files is not None:
        candidates = [root_path / f for f in modified_files if f.endswith(".py") and (root_path / f).exists()]
    else:
        candidates = list(root_path.rglob("*.py"))

    return [p for p in candidates if not any(part in _SKIP_DIRS for part in p.parts)]


def run_basic_scan(
    project_root: str,
    modified_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Lightweight code scan without SonarQube using AST and regex.

    This is the final fallback used when neither the SonarQube REST API nor
    the sonar-scanner CLI is available.  It analyses only Python files.

    Args:
        project_root:   Absolute path to the project root directory.
        modified_files: Optional list of relative paths to restrict the scan.
                        When omitted all .py files under project_root are
                        scanned.

    Returns:
        Dict with the same schema as api_client.run_sonar_scan:
            scan_success (bool), findings (list), summary (dict),
            scan_duration_ms (int), error (str | None),
            api_used (bool), cli_ran (bool).
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
            "error": "project_root does not exist: {}".format(project_root),
            "api_used": False,
            "cli_ran": False,
        }

    target_files = _resolve_target_files(root_path, modified_files)
    logger.debug(
        "[run_basic_scan] Scanning %d Python files under %s",
        len(target_files),
        project_root,
    )

    all_findings: List[Dict[str, Any]] = []

    for file_path in target_files:
        rel_path = str(file_path.relative_to(root_path))

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Could not read %s: %s", file_path, exc)
            continue

        lines = source.splitlines()

        all_findings.extend(_scan_file_lines(rel_path, lines))
        all_findings.extend(_scan_file_ast(rel_path, source, lines))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    bugs = sum(1 for f in all_findings if f["type"] == "BUG")
    vulnerabilities = sum(1 for f in all_findings if f["type"] == "VULNERABILITY")
    code_smells = sum(1 for f in all_findings if f["type"] == "CODE_SMELL")
    quality_gate = "PASSED" if (bugs == 0 and vulnerabilities == 0) else "FAILED"

    logger.debug(
        "[run_basic_scan] Done in %dms: %d bugs, %d vulns, %d smells",
        elapsed_ms,
        bugs,
        vulnerabilities,
        code_smells,
    )

    return {
        "scan_success": True,
        "findings": all_findings,
        "summary": {
            "bugs": bugs,
            "vulnerabilities": vulnerabilities,
            "code_smells": code_smells,
            "coverage_pct": None,
            "quality_gate": quality_gate,
        },
        "scan_duration_ms": elapsed_ms,
        "error": None,
        "api_used": False,
        "cli_ran": False,
    }
