"""
Auto-fixer for SonarQube findings.

Wraps the standalone sonar_auto_fixer module behind a SonarAutoFixer class
that provides a clean, injectable interface consumed by SonarQubeScanner.

The underlying sonar_auto_fixer module implements:
  - Template-based fixes for common Python rules (bare-except, unused-import,
    hardcoded-credentials, todo-comment, eval-exec).
  - AST parse verification after each fix to prevent broken code.
  - Backup (.bak) creation before modifying files.
  - A fix-verify iteration loop with a configurable max_iterations cap.

This wrapper adds:
  - Lazy import of sonar_auto_fixer to avoid import-time side effects.
  - Consistent error handling (never raises, always returns a result dict).
  - Logging using the project logger.

Version: 1.4.1
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SonarAutoFixer:
    """Auto-fixer that applies template fixes and generates LLM instructions.

    Delegates all implementation to the standalone sonar_auto_fixer module
    (langgraph_engine/sonar_auto_fixer.py).  This class is a thin
    adapter that provides the interface expected by SonarQubeScanner.
    """

    def __init__(self) -> None:
        """Initialise the auto-fixer adapter."""
        self._module = None  # Lazy-loaded on first use.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_module(self):
        """Lazy-load the sonar_auto_fixer module.

        Returns:
            The sonar_auto_fixer module, or None when unavailable.
        """
        if self._module is None:
            try:
                from .. import sonar_auto_fixer  # type: ignore[import]

                self._module = sonar_auto_fixer
                logger.debug("[SonarAutoFixer] sonar_auto_fixer loaded")
            except ImportError as exc:
                logger.warning("[SonarAutoFixer] sonar_auto_fixer unavailable: %s", exc)
        return self._module

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def plan_fixes(
        self,
        findings: List[Dict[str, Any]],
        max_fixes: int = 10,
    ) -> List[Dict[str, Any]]:
        """Priority-sort findings and return those selected for fixing.

        Findings are ordered by severity (BLOCKER > CRITICAL > MAJOR >
        MINOR > INFO) and capped at max_fixes.

        Args:
            findings:  List of finding dicts.
            max_fixes: Maximum number of findings to include in the plan.

        Returns:
            Ordered list of findings to fix.  Empty list when the module is
            unavailable.
        """
        module = self._get_module()
        if module is None:
            logger.debug("[SonarAutoFixer] plan_fixes: module unavailable")
            return findings[:max_fixes]

        try:
            return module.plan_fixes(findings=findings, max_fixes=max_fixes)
        except Exception as exc:
            logger.error("[SonarAutoFixer] plan_fixes() failed: %s", exc)
            return findings[:max_fixes]

    def generate_fix_instruction(
        self,
        finding: Dict[str, Any],
        source_context: str = "",
    ) -> Dict[str, Any]:
        """Generate a fix instruction for a single finding.

        Args:
            finding:        A single finding dict.
            source_context: Optional source snippet for additional context.

        Returns:
            Dict with keys: file (str), line (int), instruction (str),
            fix_type (str - 'auto' or 'llm'), template_fix (str).
            Returns a minimal error dict when the module is unavailable.
        """
        module = self._get_module()
        if module is None:
            return {
                "file": finding.get("file", ""),
                "line": finding.get("line", 0),
                "instruction": "sonar_auto_fixer module unavailable",
                "fix_type": "llm",
                "template_fix": "",
            }

        try:
            return module.generate_fix_instruction(
                finding=finding,
                source_context=source_context,
            )
        except Exception as exc:
            logger.error("[SonarAutoFixer] generate_fix_instruction() failed: %s", exc)
            return {
                "file": finding.get("file", ""),
                "line": finding.get("line", 0),
                "instruction": str(exc),
                "fix_type": "llm",
                "template_fix": "",
            }

    def apply_template_fix(
        self,
        file_path: str,
        fix: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply a template-based fix to a file.

        Creates a .bak backup and verifies the result with AST parse.

        Args:
            file_path: Absolute path to the file to modify.
            fix:       Fix instruction dict as returned by
                       generate_fix_instruction.

        Returns:
            Dict with keys: applied (bool), file (str), error (str).
        """
        module = self._get_module()
        if module is None:
            return {
                "applied": False,
                "file": file_path,
                "error": "sonar_auto_fixer module unavailable",
            }

        try:
            return module.apply_template_fix(file_path=file_path, fix=fix)
        except Exception as exc:
            logger.error("[SonarAutoFixer] apply_template_fix() failed: %s", exc)
            return {"applied": False, "file": file_path, "error": str(exc)}

    def run_fix_loop(
        self,
        project_root: str,
        findings: List[Dict[str, Any]],
        max_iterations: int = 3,
    ) -> Dict[str, Any]:
        """Run the full fix-verify iteration loop.

        Plans, applies, and verifies fixes in up to max_iterations passes.
        Only template-fixable issues (fix_type == 'auto') are applied
        automatically; LLM-only findings are returned in the result for
        downstream processing.

        Args:
            project_root:    Absolute path to the project root.
            findings:        List of finding dicts.
            max_iterations:  Maximum number of fix-verify passes.

        Returns:
            Dict with keys: fixed (int), skipped (int), failed (int),
            fix_results (list), summary (str).
        """
        logger.info(
            "[SonarAutoFixer] run_fix_loop() - %d findings, max_iter=%d",
            len(findings),
            max_iterations,
        )

        module = self._get_module()
        if module is None:
            return {
                "fixed": 0,
                "skipped": len(findings),
                "failed": 0,
                "fix_results": [],
                "summary": "sonar_auto_fixer module unavailable",
            }

        try:
            return module.run_fix_loop(
                project_root=project_root,
                findings=findings,
                max_iterations=max_iterations,
            )
        except Exception as exc:
            logger.error("[SonarAutoFixer] run_fix_loop() failed: %s", exc)
            return {
                "fixed": 0,
                "skipped": len(findings),
                "failed": 0,
                "fix_results": [],
                "summary": str(exc),
            }

    def get_fix_summary(self, fix_result: Dict[str, Any]) -> str:
        """Format a fix result as a markdown summary string.

        Args:
            fix_result: Dict as returned by run_fix_loop.

        Returns:
            Markdown-formatted summary string.
        """
        module = self._get_module()
        if module is None:
            return "Auto-fixer unavailable."

        try:
            return module.get_fix_summary(fix_result)
        except Exception as exc:
            logger.error("[SonarAutoFixer] get_fix_summary() failed: %s", exc)
            return str(exc)
