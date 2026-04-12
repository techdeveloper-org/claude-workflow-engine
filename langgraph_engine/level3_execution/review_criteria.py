"""
Review Criteria - Code quality rules, test coverage, and documentation requirements.

Provides a structured checklist that Step 11 (Pull Request & Code Review) applies
before approving a PR merge. The criteria are organised into three domains:

1. Code Quality   - PEP 8 compliance, type hints, no bare except, function length
2. Test Coverage  - Test files present, coverage ratio, assertion count
3. Documentation  - Docstrings present, README updated, CHANGELOG entry

Usage:
    from .review_criteria import ReviewCriteria, CriteriaResult

    criteria = ReviewCriteria()
    result = criteria.evaluate(
        files_changed=["src/services/user_service.py", "tests/test_user_service.py"],
        pr_title="Add user authentication",
        pr_body="Implements JWT login flow",
        diff_text="..."   # optional raw diff
    )

    if result.passed:
        print("PR approved - all criteria met")
    else:
        for issue in result.issues:
            print(f"  FAIL [{issue['domain']}] {issue['message']}")
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

DOMAIN_CODE_QUALITY = "code_quality"
DOMAIN_TEST_COVERAGE = "test_coverage"
DOMAIN_DOCUMENTATION = "documentation"

SEVERITY_BLOCKING = "blocking"  # PR cannot merge
SEVERITY_WARNING = "warning"  # PR can merge with caveat
SEVERITY_INFO = "info"  # Informational only


# ---------------------------------------------------------------------------
# Thresholds (easy to tune)
# ---------------------------------------------------------------------------

MAX_FUNCTION_LINES = 80  # Functions longer than this trigger a warning
MAX_FILE_LINES = 500  # Files larger than this trigger a warning
MIN_COVERAGE_RATIO = 0.70  # 70% of changed source files must have test counterpart
MIN_ASSERTIONS_PER_FILE = 2  # Test files need at least this many assert statements
MIN_DOCSTRING_RATIO = 0.50  # 50% of public functions must have docstrings


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CriteriaIssue:
    """Single criterion violation."""

    domain: str  # DOMAIN_CODE_QUALITY | DOMAIN_TEST_COVERAGE | DOMAIN_DOCUMENTATION
    rule_id: str  # Short identifier, e.g. "CQ001"
    severity: str  # blocking | warning | info
    message: str  # Human-readable description
    file_path: str = ""  # File that triggered the issue (if applicable)
    suggestion: str = ""  # Recommended fix


@dataclass
class CriteriaResult:
    """Aggregated review result."""

    passed: bool
    score: float  # 0.0 - 1.0 (fraction of rules that passed)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    domain_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "issues": self.issues,
            "warnings": self.warnings,
            "summary": self.summary,
            "domain_scores": self.domain_scores,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

REVIEW_RULES: List[Dict[str, Any]] = [
    # ---- Code Quality ----
    {
        "id": "CQ001",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_BLOCKING,
        "name": "No bare except clauses",
        "description": "Bare 'except:' without exception type hides errors.",
        "suggestion": "Replace 'except:' with 'except Exception as e:' or a specific exception type.",
    },
    {
        "id": "CQ002",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_WARNING,
        "name": "Type hints on public functions",
        "description": f"At least {int(MIN_DOCSTRING_RATIO * 100)}% of public functions should have type hints.",
        "suggestion": "Add type hints to function signatures (PEP 484).",
    },
    {
        "id": "CQ003",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_WARNING,
        "name": "Function length",
        "description": f"Functions longer than {MAX_FUNCTION_LINES} lines are hard to maintain.",
        "suggestion": "Refactor long functions into smaller, single-responsibility helpers.",
    },
    {
        "id": "CQ004",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_BLOCKING,
        "name": "No hardcoded secrets",
        "description": "Passwords, tokens, or API keys must not be hardcoded in source files.",
        "suggestion": "Move secrets to environment variables or a secrets manager.",
    },
    {
        "id": "CQ005",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_WARNING,
        "name": "File length",
        "description": f"Files longer than {MAX_FILE_LINES} lines reduce readability.",
        "suggestion": "Split large files into smaller modules with clear responsibilities.",
    },
    {
        "id": "CQ006",
        "domain": DOMAIN_CODE_QUALITY,
        "severity": SEVERITY_INFO,
        "name": "ASCII-safe encoding",
        "description": "Python source files should use only ASCII characters (cp1252 safe on Windows).",
        "suggestion": "Replace non-ASCII characters (emojis, special symbols) with ASCII equivalents.",
    },
    # ---- Test Coverage ----
    {
        "id": "TC001",
        "domain": DOMAIN_TEST_COVERAGE,
        "severity": SEVERITY_BLOCKING,
        "name": "Test file coverage",
        "description": f"At least {int(MIN_COVERAGE_RATIO * 100)}% of changed source files must have a corresponding test file.",
        "suggestion": "Create test files under tests/ that cover the changed source modules.",
    },
    {
        "id": "TC002",
        "domain": DOMAIN_TEST_COVERAGE,
        "severity": SEVERITY_WARNING,
        "name": "Assertion count",
        "description": f"Each test file should contain at least {MIN_ASSERTIONS_PER_FILE} assert statements.",
        "suggestion": "Add meaningful assertions that verify expected behaviour.",
    },
    {
        "id": "TC003",
        "domain": DOMAIN_TEST_COVERAGE,
        "severity": SEVERITY_INFO,
        "name": "Test naming convention",
        "description": "Test functions should be named test_<behaviour_under_test>.",
        "suggestion": "Rename test functions to clearly describe what they test.",
    },
    # ---- Documentation ----
    {
        "id": "DC001",
        "domain": DOMAIN_DOCUMENTATION,
        "severity": SEVERITY_WARNING,
        "name": "Module docstrings",
        "description": "Each Python module should have a module-level docstring.",
        "suggestion": "Add a triple-quoted docstring at the top of each .py file.",
    },
    {
        "id": "DC002",
        "domain": DOMAIN_DOCUMENTATION,
        "severity": SEVERITY_WARNING,
        "name": "Function docstrings",
        "description": f"At least {int(MIN_DOCSTRING_RATIO * 100)}% of public functions should have docstrings.",
        "suggestion": "Add docstrings to all public functions describing purpose, args, and returns.",
    },
    {
        "id": "DC003",
        "domain": DOMAIN_DOCUMENTATION,
        "severity": SEVERITY_INFO,
        "name": "PR description completeness",
        "description": "PR body should describe what changed and why (min 50 characters).",
        "suggestion": "Expand the PR description to explain the motivation and approach.",
    },
]


# ---------------------------------------------------------------------------
# ReviewCriteria
# ---------------------------------------------------------------------------


class ReviewCriteria:
    """
    Evaluates a pull request against a structured set of review criteria.

    Can work with:
    - File paths only (for presence/structure checks)
    - File content (for deep analysis)
    - PR metadata (title, body)
    - Raw diff text (optional)
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else None
        self.rules = REVIEW_RULES

    # =========================================================================
    # PUBLIC
    # =========================================================================

    def evaluate(
        self,
        files_changed: List[str],
        pr_title: str = "",
        pr_body: str = "",
        diff_text: str = "",
    ) -> CriteriaResult:
        """
        Run all review criteria against the provided PR data.

        Args:
            files_changed: List of file paths changed in the PR (relative or absolute).
            pr_title:      PR title string.
            pr_body:       PR description/body text.
            diff_text:     Raw diff text (optional, enables deeper analysis).

        Returns:
            CriteriaResult with passed, score, issues, warnings, and domain_scores.
        """
        from datetime import datetime

        logger.info("[ReviewCriteria] Starting PR review evaluation...")
        logger.info(f"[ReviewCriteria] Files changed: {len(files_changed)}")

        all_issues: List[CriteriaIssue] = []
        all_warnings: List[CriteriaIssue] = []

        # -- Code Quality checks --
        cq_issues, cq_warnings = self._evaluate_code_quality(files_changed, diff_text)
        all_issues.extend(cq_issues)
        all_warnings.extend(cq_warnings)

        # -- Test Coverage checks --
        tc_issues, tc_warnings = self._evaluate_test_coverage(files_changed)
        all_issues.extend(tc_issues)
        all_warnings.extend(tc_warnings)

        # -- Documentation checks --
        dc_issues, dc_warnings = self._evaluate_documentation(files_changed, pr_body)
        all_issues.extend(dc_issues)
        all_warnings.extend(dc_warnings)

        # -- Compute scores --
        total_rules = len(self.rules)
        total_violations = len(all_issues) + len(all_warnings)
        passed_count = total_rules - total_violations
        overall_score = max(0.0, passed_count / total_rules) if total_rules > 0 else 1.0

        domain_scores = self._compute_domain_scores(all_issues, all_warnings)

        # -- Determine pass/fail --
        has_blocking = any(i.severity == SEVERITY_BLOCKING for i in all_issues)
        passed = not has_blocking

        summary = self._build_summary(
            passed=passed,
            issues=all_issues,
            warnings=all_warnings,
            score=overall_score,
        )

        logger.info(f"[ReviewCriteria] Result: {'PASSED' if passed else 'FAILED'} (score={overall_score:.2f})")

        return CriteriaResult(
            passed=passed,
            score=overall_score,
            issues=[self._issue_to_dict(i) for i in all_issues],
            warnings=[self._issue_to_dict(w) for w in all_warnings],
            summary=summary,
            domain_scores=domain_scores,
            timestamp=datetime.now().isoformat(),
        )

    def get_checklist(self) -> List[Dict[str, Any]]:
        """Return all rules as a human-readable checklist."""
        return [
            {
                "id": r["id"],
                "domain": r["domain"],
                "severity": r["severity"],
                "name": r["name"],
                "description": r["description"],
                "suggestion": r["suggestion"],
            }
            for r in self.rules
        ]

    # =========================================================================
    # PRIVATE: CODE QUALITY
    # =========================================================================

    def _evaluate_code_quality(
        self, files: List[str], diff_text: str
    ) -> Tuple[List[CriteriaIssue], List[CriteriaIssue]]:
        issues: List[CriteriaIssue] = []
        warnings: List[CriteriaIssue] = []

        py_files = [f for f in files if f.endswith(".py")]

        for file_path in py_files:
            content = self._read_file(file_path)
            if content is None:
                continue

            # CQ001 - bare except
            if re.search(r"^\s*except\s*:", content, re.MULTILINE):
                issues.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ001",
                        severity=SEVERITY_BLOCKING,
                        message="Bare 'except:' clause found",
                        file_path=file_path,
                        suggestion="Use 'except Exception as e:' or a specific exception type",
                    )
                )

            # CQ002 - type hints ratio (light heuristic on def lines)
            def_lines = re.findall(r"^\s*def [a-z]", content, re.MULTILINE)
            typed_lines = re.findall(r"^\s*def [a-z].*->", content, re.MULTILINE)
            if def_lines and len(typed_lines) / len(def_lines) < MIN_DOCSTRING_RATIO:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ002",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Low type hint coverage: {len(typed_lines)}/{len(def_lines)} "
                            f"public functions have return type hints"
                        ),
                        file_path=file_path,
                        suggestion="Add -> ReturnType to function signatures",
                    )
                )

            # CQ003 - function length
            long_fns = self._find_long_functions(content, MAX_FUNCTION_LINES)
            for fn_name in long_fns:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ003",
                        severity=SEVERITY_WARNING,
                        message=f"Function '{fn_name}' exceeds {MAX_FUNCTION_LINES} lines",
                        file_path=file_path,
                        suggestion="Refactor into smaller helper functions",
                    )
                )

            # CQ004 - hardcoded secrets (simple pattern matching)
            secret_match = self._detect_hardcoded_secrets(content)
            if secret_match:
                issues.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ004",
                        severity=SEVERITY_BLOCKING,
                        message=f"Possible hardcoded secret: '{secret_match}'",
                        file_path=file_path,
                        suggestion="Move to environment variable: os.environ.get('SECRET_KEY')",
                    )
                )

            # CQ005 - file length
            line_count = len(content.splitlines())
            if line_count > MAX_FILE_LINES:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ005",
                        severity=SEVERITY_WARNING,
                        message=f"File has {line_count} lines (limit {MAX_FILE_LINES})",
                        file_path=file_path,
                        suggestion="Split into smaller focused modules",
                    )
                )

            # CQ006 - ASCII safety (non-ASCII chars outside string literals)
            non_ascii = re.findall(r"[^\x00-\x7F]", content)
            if non_ascii:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_CODE_QUALITY,
                        rule_id="CQ006",
                        severity=SEVERITY_INFO,
                        message=f"Non-ASCII characters found: {list(set(non_ascii))[:5]}",
                        file_path=file_path,
                        suggestion="Replace non-ASCII chars with ASCII equivalents for Windows cp1252 safety",
                    )
                )

        return issues, warnings

    # =========================================================================
    # PRIVATE: TEST COVERAGE
    # =========================================================================

    def _evaluate_test_coverage(self, files: List[str]) -> Tuple[List[CriteriaIssue], List[CriteriaIssue]]:
        issues: List[CriteriaIssue] = []
        warnings: List[CriteriaIssue] = []

        # Identify source files (non-test .py)
        source_files = [
            f
            for f in files
            if f.endswith(".py") and not any(seg in f for seg in ["test_", "_test", "/tests/", "\\tests\\"])
        ]
        test_files = [
            f
            for f in files
            if f.endswith(".py") and any(seg in f for seg in ["test_", "_test", "/tests/", "\\tests\\"])
        ]

        # TC001 - coverage ratio
        if source_files:
            covered = 0
            for src in source_files:
                base = Path(src).stem  # e.g. "user_service"
                has_test = any(base in tf for tf in test_files)
                if has_test:
                    covered += 1

            ratio = covered / len(source_files)
            if ratio < MIN_COVERAGE_RATIO:
                uncovered = [f for f in source_files if not any(Path(f).stem in tf for tf in test_files)]
                issues.append(
                    CriteriaIssue(
                        domain=DOMAIN_TEST_COVERAGE,
                        rule_id="TC001",
                        severity=SEVERITY_BLOCKING,
                        message=(
                            f"Test coverage too low: {covered}/{len(source_files)} source files "
                            f"have tests ({ratio:.0%}, minimum {MIN_COVERAGE_RATIO:.0%})"
                        ),
                        suggestion=f"Add tests for: {uncovered[:3]}",
                    )
                )

        # TC002 - assertion count per test file
        for tf in test_files:
            content = self._read_file(tf)
            if content is None:
                continue
            assertion_count = len(re.findall(r"\bassert\b", content))
            if assertion_count < MIN_ASSERTIONS_PER_FILE:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_TEST_COVERAGE,
                        rule_id="TC002",
                        severity=SEVERITY_WARNING,
                        message=(f"Only {assertion_count} assertion(s) found " f"(minimum {MIN_ASSERTIONS_PER_FILE})"),
                        file_path=tf,
                        suggestion="Add more assertions to verify expected outcomes",
                    )
                )

        # TC003 - test naming convention
        for tf in test_files:
            content = self._read_file(tf)
            if content is None:
                continue
            bad_names = re.findall(r"^\s*def ((?!test_)[a-zA-Z]\w*)\(", content, re.MULTILINE)
            # Filter out setUp/tearDown/etc.
            bad_names = [n for n in bad_names if not n.startswith(("setUp", "tearDown", "_"))]
            if bad_names:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_TEST_COVERAGE,
                        rule_id="TC003",
                        severity=SEVERITY_INFO,
                        message=f"Non-standard test names: {bad_names[:3]}",
                        file_path=tf,
                        suggestion="Rename to test_<behaviour_under_test>(self)",
                    )
                )

        return issues, warnings

    # =========================================================================
    # PRIVATE: DOCUMENTATION
    # =========================================================================

    def _evaluate_documentation(
        self, files: List[str], pr_body: str
    ) -> Tuple[List[CriteriaIssue], List[CriteriaIssue]]:
        issues: List[CriteriaIssue] = []
        warnings: List[CriteriaIssue] = []

        py_files = [f for f in files if f.endswith(".py")]

        for file_path in py_files:
            content = self._read_file(file_path)
            if content is None:
                continue

            # DC001 - module docstring
            # First non-empty, non-comment line should be a docstring
            stripped = content.lstrip()
            if not stripped.startswith('"""') and not stripped.startswith("'''"):
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_DOCUMENTATION,
                        rule_id="DC001",
                        severity=SEVERITY_WARNING,
                        message="Missing module-level docstring",
                        file_path=file_path,
                        suggestion='Add """Module description...""" at the top of the file',
                    )
                )

            # DC002 - function docstrings ratio
            # Count public functions (def <name> where name doesn't start with _)
            pub_fns = re.findall(r"^\s*def ([a-zA-Z][^_]\w*)\s*\(", content, re.MULTILINE)
            # Functions with a docstring immediately after def
            doc_fns = re.findall(r'^\s*def \w+\([^)]*\)[^:]*:\s*\n\s+"""', content, re.MULTILINE)
            if pub_fns and len(doc_fns) / len(pub_fns) < MIN_DOCSTRING_RATIO:
                warnings.append(
                    CriteriaIssue(
                        domain=DOMAIN_DOCUMENTATION,
                        rule_id="DC002",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Low docstring coverage: {len(doc_fns)}/{len(pub_fns)} " f"public functions documented"
                        ),
                        file_path=file_path,
                        suggestion='Add """...""" immediately after each def statement',
                    )
                )

        # DC003 - PR description completeness
        if len(pr_body.strip()) < 50:
            warnings.append(
                CriteriaIssue(
                    domain=DOMAIN_DOCUMENTATION,
                    rule_id="DC003",
                    severity=SEVERITY_INFO,
                    message=f"PR description too short ({len(pr_body.strip())} chars, min 50)",
                    suggestion="Expand PR body to explain what changed and why",
                )
            )

        return issues, warnings

    # =========================================================================
    # PRIVATE: HELPERS
    # =========================================================================

    def _read_file(self, file_path: str) -> Optional[str]:
        """Read file content from disk. Returns None if file not accessible."""
        try:
            p = Path(file_path)
            if not p.is_absolute() and self.project_root:
                p = self.project_root / file_path
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.debug(f"[ReviewCriteria] Cannot read {file_path}: {exc}")
        return None

    @staticmethod
    def _find_long_functions(content: str, max_lines: int) -> List[str]:
        """Find function names that exceed max_lines."""
        long_fns = []
        lines = content.splitlines()
        current_fn: Optional[str] = None
        fn_start: int = 0

        for i, line in enumerate(lines):
            fn_match = re.match(r"^(\s*)def (\w+)\s*\(", line)
            if fn_match:
                # Check if previous function was too long
                if current_fn and (i - fn_start) > max_lines:
                    long_fns.append(current_fn)
                current_fn = fn_match.group(2)
                fn_start = i
                len(fn_match.group(1))

        # Check last function
        if current_fn and (len(lines) - fn_start) > max_lines:
            long_fns.append(current_fn)

        return long_fns

    @staticmethod
    def _detect_hardcoded_secrets(content: str) -> Optional[str]:
        """
        Detect potential hardcoded secrets using pattern matching.
        Returns the matched pattern string or None.
        """
        secret_patterns = [
            r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{6,}["\']',
            r'(?:api_key|apikey|api_secret)\s*=\s*["\'][^"\']{8,}["\']',
            r'(?:secret_key|secret)\s*=\s*["\'][^"\']{8,}["\']',
            r'(?:token|access_token)\s*=\s*["\'][^"\']{8,}["\']',
            r'(?:private_key)\s*=\s*["\'][^"\']{8,}["\']',
        ]
        for pattern in secret_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Truncate the actual value for safe logging
                return match.group(0)[:50]
        return None

    def _compute_domain_scores(
        self,
        issues: List[CriteriaIssue],
        warnings: List[CriteriaIssue],
    ) -> Dict[str, float]:
        """Compute per-domain pass rates."""
        domains = [DOMAIN_CODE_QUALITY, DOMAIN_TEST_COVERAGE, DOMAIN_DOCUMENTATION]
        scores = {}

        for domain in domains:
            domain_rules = [r for r in self.rules if r["domain"] == domain]
            if not domain_rules:
                scores[domain] = 1.0
                continue
            domain_violations = sum(1 for item in (issues + warnings) if item.domain == domain)
            scores[domain] = max(0.0, (len(domain_rules) - domain_violations) / len(domain_rules))

        return scores

    @staticmethod
    def _build_summary(
        passed: bool,
        issues: List[CriteriaIssue],
        warnings: List[CriteriaIssue],
        score: float,
    ) -> str:
        status = "PASSED" if passed else "FAILED"
        blocking = [i for i in issues if i.severity == SEVERITY_BLOCKING]
        parts = [
            f"Review {status} | Score: {score:.0%}",
            f"Blocking issues: {len(blocking)}",
            f"Warnings: {len(warnings)}",
        ]
        if blocking:
            parts.append("Blocking: " + "; ".join(i.message[:60] for i in blocking[:3]))
        return " | ".join(parts)

    @staticmethod
    def _issue_to_dict(issue: CriteriaIssue) -> Dict[str, Any]:
        return {
            "domain": issue.domain,
            "rule_id": issue.rule_id,
            "severity": issue.severity,
            "message": issue.message,
            "file_path": issue.file_path,
            "suggestion": issue.suggestion,
        }
