"""Comprehensive Error Logging System for Claude Workflow Engine.

Provides centralized error logging with:
- Timestamp + severity tracking
- Session-based file logging
- Error audit trail
- Pretty-printed console output
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ErrorLogger:
    """Comprehensive error logging system with file persistence."""

    SEVERITY_DEBUG = "DEBUG"
    SEVERITY_INFO = "INFO"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_ERROR = "ERROR"
    SEVERITY_CRITICAL = "CRITICAL"

    def __init__(self, session_id: str, log_base_dir: str = "~/.claude/logs"):
        """Initialize error logger for a session.

        Args:
            session_id: Unique session identifier
            log_base_dir: Base directory for logs
        """
        self.session_id = session_id
        self.log_dir = Path(log_base_dir).expanduser() / "sessions" / session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.error_file = self.log_dir / "errors.log"
        self.decision_file = self.log_dir / "decisions.log"
        self.audit_file = self.log_dir / "audit.json"

        self.errors: List[Dict] = []
        self.decisions: List[Dict] = []

    def log_error(
        self,
        step: str,
        error_message: str,
        severity: str = "ERROR",
        error_type: Optional[str] = None,
        recovery_action: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> None:
        """Log an error with full context.

        Args:
            step: Which step/node failed (e.g., "Level -1", "Step 1")
            error_message: Description of the error
            severity: One of DEBUG, INFO, WARNING, ERROR, CRITICAL
            error_type: Type of error (e.g., "NetworkError", "ValidationError")
            recovery_action: What action was taken (e.g., "Retried 3 times")
            context: Additional context dict
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "severity": severity,
            "message": error_message,
            "error_type": error_type or "Unknown",
            "recovery_action": recovery_action,
            "context": context or {},
        }

        self.errors.append(entry)
        self._append_to_file(self.error_file, self._format_error_entry(entry))
        self._print_error(entry)

    def log_decision(
        self,
        step: str,
        decision: str,
        reasoning: str,
        options: Optional[List[str]] = None,
        chosen_option: Optional[str] = None,
    ) -> None:
        """Log a decision point in execution.

        Args:
            step: Which step made the decision
            decision: What was decided
            reasoning: Why this decision was made
            options: Available options (if any)
            chosen_option: Which option was chosen
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "decision": decision,
            "reasoning": reasoning,
            "options": options or [],
            "chosen_option": chosen_option,
        }

        self.decisions.append(entry)
        self._append_to_file(self.decision_file, self._format_decision_entry(entry))

        print(f"[BLUE] [{step}] DECISION: {decision}")
        print(f"   Reasoning: {reasoning}")
        if chosen_option:
            print(f"   Chosen: {chosen_option}")

    def log_validation_result(
        self,
        step: str,
        check_name: str,
        passed: bool,
        details: Optional[str] = None,
    ) -> None:
        """Log validation check result.

        Args:
            step: Which step performed validation
            check_name: Name of check (e.g., "Unicode fix", "Compression validation")
            passed: Whether check passed
            details: Additional details
        """
        symbol = "[OK]" if passed else "[FAIL]"
        status = "PASS" if passed else "FAIL"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "check": check_name,
            "status": status,
            "passed": passed,
            "details": details,
        }

        self._append_to_file(self.error_file, self._format_validation_entry(entry))

        print(f"{symbol} [{step}] {check_name}: {status}")
        if details:
            print(f"   Details: {details}")

    def log_retry_attempt(
        self,
        step: str,
        attempt: int,
        max_attempts: int,
        status: str,
        reason: Optional[str] = None,
    ) -> None:
        """Log retry attempt information.

        Args:
            step: Which step is retrying
            attempt: Current attempt number
            max_attempts: Maximum allowed attempts
            status: Result of attempt (SUCCESS, FAILED)
            reason: Why retry is happening
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "status": status,
            "reason": reason,
        }

        log_line = f"[{entry['timestamp']}] [{step}] RETRY ATTEMPT {attempt}/{max_attempts}: {status}"
        if reason:
            log_line += f" ({reason})"
        self._append_to_file(self.error_file, log_line)

        print(f"[refresh] [{step}] Retry {attempt}/{max_attempts}: {status}")
        if reason:
            print(f"   Reason: {reason}")

    def log_backup_restore(
        self,
        operation: str,
        file_path: str,
        success: bool,
        backup_path: Optional[str] = None,
    ) -> None:
        """Log file backup/restore operations.

        Args:
            operation: "backup" or "restore"
            file_path: Original file path
            success: Whether operation succeeded
            backup_path: Path to backup file
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "file": file_path,
            "backup": backup_path,
            "success": success,
        }

        symbol = "[OK]" if success else "[FAIL]"
        log_line = f"[{entry['timestamp']}] {symbol} {operation.upper()} {file_path}"
        if backup_path:
            log_line += f" -> {backup_path}"

        self._append_to_file(self.error_file, log_line)
        print(f"{symbol} {operation.upper()}: {file_path}")

    def get_error_summary(self) -> Dict:
        """Get summary of all errors logged.

        Returns:
            Dict with error statistics
        """
        by_severity = {}
        for error in self.errors:
            sev = error["severity"]
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "total_errors": len(self.errors),
            "by_severity": by_severity,
            "critical_errors": [e for e in self.errors if e["severity"] == "CRITICAL"],
        }

    def get_decision_summary(self) -> Dict:
        """Get summary of all decisions logged.

        Returns:
            Dict with decision statistics
        """
        return {
            "total_decisions": len(self.decisions),
            "decisions": self.decisions,
        }

    def save_audit_trail(self) -> Path:
        """Save complete audit trail to JSON file.

        Returns:
            Path to audit file
        """
        audit_data = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "errors": self.errors,
            "decisions": self.decisions,
            "summary": {
                "total_errors": len(self.errors),
                "total_decisions": len(self.decisions),
                "error_summary": self.get_error_summary(),
            },
        }

        self.audit_file.write_text(json.dumps(audit_data, indent=2))
        return self.audit_file

    @staticmethod
    def _format_error_entry(entry: Dict) -> str:
        """Format error entry for logging."""
        timestamp = entry["timestamp"]
        step = entry["step"]
        severity = entry["severity"]
        message = entry["message"]
        error_type = entry["error_type"]

        line = f"[{timestamp}] [{step}] [{severity}] ({error_type}) {message}"

        if entry.get("recovery_action"):
            line += f"\n  -> Recovery: {entry['recovery_action']}"

        if entry.get("context"):
            line += f"\n  -> Context: {json.dumps(entry['context'])}"

        return line

    @staticmethod
    def _format_decision_entry(entry: Dict) -> str:
        """Format decision entry for logging."""
        timestamp = entry["timestamp"]
        step = entry["step"]
        decision = entry["decision"]
        reasoning = entry["reasoning"]

        line = f"[{timestamp}] [{step}] DECISION: {decision}\n"
        line += f"  Reasoning: {reasoning}"

        if entry.get("options"):
            line += f"\n  Options: {', '.join(entry['options'])}"

        if entry.get("chosen_option"):
            line += f"\n  Chosen: {entry['chosen_option']}"

        return line

    @staticmethod
    def _format_validation_entry(entry: Dict) -> str:
        """Format validation entry for logging."""
        timestamp = entry["timestamp"]
        step = entry["step"]
        check = entry["check"]
        status = entry["status"]

        line = f"[{timestamp}] [{step}] VALIDATION: {check} = {status}"

        if entry.get("details"):
            line += f"\n  Details: {entry['details']}"

        return line

    def _append_to_file(self, file_path: Path, content: str) -> None:
        """Safely append content to file."""
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
        except Exception as e:
            print(f"[FAIL] Failed to write to log file {file_path}: {e}", file=sys.stderr)

    @staticmethod
    def _print_error(entry: Dict) -> None:
        """Print error to console with formatting."""
        severity = entry["severity"]
        step = entry["step"]
        message = entry["message"]

        severity_symbols = {
            "DEBUG": "[search]",
            "INFO": "[i]",
            "WARNING": "[WARN]",
            "ERROR": "[FAIL]",
            "CRITICAL": "[RED]",
        }

        symbol = severity_symbols.get(severity, "[?]")

        print(f"{symbol} [{step}] {severity}: {message}")

        if entry.get("error_type") and entry["error_type"] != "Unknown":
            print(f"   Type: {entry['error_type']}")

        if entry.get("recovery_action"):
            print(f"   Recovery: {entry['recovery_action']}")


def create_logger(session_id: str) -> ErrorLogger:
    """Create a new error logger instance.

    Args:
        session_id: Unique session ID

    Returns:
        ErrorLogger instance
    """
    return ErrorLogger(session_id)
