#!/usr/bin/env python3
"""
Common Standards Policy Enforcement (v2.0)

Maps to: policies/02-standards-system/common-standards-policy.md

This module enforces 12 categories of common coding standards (~65 real rules)
applicable to ALL projects. Standards are language-agnostic best practices
loaded into JSON before any code generation begins.

Categories (12 total, ~65 rules):
  1. naming_conventions   (7 rules)
  2. error_handling       (6 rules)
  3. logging_standards    (5 rules)
  4. security_basics      (6 rules)
  5. code_organization    (5 rules)
  6. api_design           (6 rules)
  7. database             (5 rules)
  8. constants            (5 rules)
  9. testing              (5 rules)
  10. documentation       (5 rules)
  11. git_standards       (5 rules)
  12. file_organization   (5 rules)

Key Functions:
  enforce(): Load and initialize the common standards file.
  validate(): Check that the standards file exists and is valid.
  report(): Generate a summary report of loaded standards.

CLI Usage:
  python common-standards-policy.py --enforce           # Run policy enforcement
  python common-standards-policy.py --validate          # Validate policy compliance
  python common-standards-policy.py --report            # Generate standards report

Example:
  >>> from common_standards_policy import enforce
  >>> result = enforce()
  >>> print(result['standards_count'])  # 7
"""

import sys
import io
import json
from pathlib import Path
from datetime import datetime

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id, get_session_id

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
STANDARDS_FILE = Path.home() / ".claude" / "memory" / "standards" / "common-standards.json"

# Current standards version - bump when rules change
STANDARDS_VERSION = "2.0.0"


def _needs_upgrade(filepath):
    """Check if existing JSON needs upgrade to real rules format."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stds = data.get('standards', {})
        if not stds:
            return True
        first_val = next(iter(stds.values()))
        # Old format had plain strings, new format has dicts with rules
        if isinstance(first_val, str):
            return True
        if data.get('version', '0') != STANDARDS_VERSION:
            return True
        return False
    except Exception:
        return True


def _build_common_standards():
    """Build 12-category common standards with real enforcement rules.

    Returns:
        dict: 12 standard categories, each with description and rules list.
              Total: ~65 rules across all categories.
    """
    return {
        "naming_conventions": {
            "description": "Naming conventions for all code",
            "rules": [
                "Variables and functions: camelCase",
                "Classes and types: PascalCase",
                "Constants: UPPER_SNAKE_CASE",
                "Database tables/columns: snake_case",
                "API endpoints: kebab-case plural nouns",
                "Booleans: prefix with is/has/can/should",
                "NEVER use abbreviations unless universally known (id, url, api)"
            ]
        },
        "error_handling": {
            "description": "Standard error handling patterns",
            "rules": [
                "NEVER swallow exceptions silently (empty catch blocks)",
                "Catch specific exception types, not generic Exception/Error",
                "Include context in error messages (what operation failed)",
                "Log errors at the handling point with stack trace",
                "Use appropriate error codes/status for each error type",
                "NEVER expose internal details (stack traces, SQL) to end users"
            ]
        },
        "logging_standards": {
            "description": "Structured logging requirements",
            "rules": [
                "Use structured logging (key-value pairs, not free text)",
                "Include correlation/request ID in all log entries",
                "Use appropriate log levels (ERROR for failures, INFO for events)",
                "NEVER log sensitive data (passwords, tokens, PII)",
                "NEVER log at DEBUG level in production by default"
            ]
        },
        "security_basics": {
            "description": "Security fundamentals for all code",
            "rules": [
                "NEVER hardcode secrets, passwords, or API keys in source code",
                "Validate ALL external input (user input, API parameters, file uploads)",
                "Use parameterized queries for ALL database operations",
                "Apply principle of least privilege for all access control",
                "NEVER commit secrets to version control (.env, credentials)",
                "Sanitize output to prevent injection (XSS, SQL injection)"
            ]
        },
        "code_organization": {
            "description": "Code structure and modularity",
            "rules": [
                "Each class/module has a single, clear responsibility (SRP)",
                "Extract shared logic into reusable functions/utilities (DRY)",
                "Separate business logic from data access and presentation",
                "Keep functions small and focused (one task per function)",
                "Avoid circular dependencies between modules"
            ]
        },
        "api_design": {
            "description": "RESTful API design standards",
            "rules": [
                "Use plural nouns for resource names (/users not /user)",
                "Use standard HTTP methods (GET, POST, PUT, DELETE)",
                "Return appropriate HTTP status codes",
                "Support pagination for list endpoints",
                "Version APIs in the URL path (/api/v1/)",
                "Use consistent response envelope/wrapper"
            ]
        },
        "database": {
            "description": "Database design and query standards",
            "rules": [
                "Use snake_case for all table and column names",
                "Use database migrations for ALL schema changes (never manual)",
                "Add indexes on frequently queried columns",
                "Use parameterized queries (NEVER concatenate SQL strings)",
                "Include audit columns (created_at, updated_at) on all tables"
            ]
        },
        "constants": {
            "description": "Constants organization and naming",
            "rules": [
                "NO magic numbers in code (use named constants)",
                "NO magic strings in code (use named constants)",
                "Centralize related constants in dedicated files/classes",
                "Centralize all user-facing messages (for i18n readiness)",
                "NEVER duplicate constant definitions"
            ]
        },
        "testing": {
            "description": "Testing approach and standards",
            "rules": [
                "Write unit tests for business logic",
                "Write integration tests for API endpoints and data access",
                "NEVER use production data in tests",
                "Use descriptive test names that explain the scenario",
                "Each test should be independent (no shared state between tests)"
            ]
        },
        "documentation": {
            "description": "Code documentation requirements",
            "rules": [
                "Comments explain WHY, not WHAT the code does",
                "Document all public APIs with request/response examples",
                "Every project has a README with setup and run instructions",
                "Keep documentation close to the code it describes",
                "Update documentation when changing functionality"
            ]
        },
        "git_standards": {
            "description": "Git workflow and commit standards",
            "rules": [
                "Write meaningful commit messages describing the change",
                "Use conventional commit format (feat/fix/refactor: description)",
                "Create feature branches for new work (never commit directly to main)",
                "Write PR descriptions explaining what and why",
                "NEVER commit generated files, build artifacts, or secrets"
            ]
        },
        "file_organization": {
            "description": "File and project structure",
            "rules": [
                "Group related files by feature/domain",
                "Separate configuration files from application code",
                "Keep a clear, documented project entry point",
                "Use consistent file naming conventions across the project",
                "Separate test files from source files"
            ]
        }
    }


def log_action(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] common-standards-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Check that the common standards file exists and is parseable.

    Reads the standards JSON file and verifies it contains at least one
    standard definition. Logs the result to the policy-hits log.

    Returns:
        bool: True if the file exists and loads successfully, False otherwise.
    """
    try:
        if STANDARDS_FILE.exists():
            with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            standard_count = len(data.get('standards', {}))
            log_action("VALIDATE", f"standards-loaded | count={standard_count}")
            return True
        log_action("VALIDATE", "standards-file-missing")
        return False
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report listing all loaded common standards.

    Reads the standards file and returns a structured dictionary suitable for
    JSON output, including the total count and list of standard names.

    Returns:
        dict: Report containing 'status', 'total_standards', 'standards' (list),
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        if not STANDARDS_FILE.exists():
            return {"status": "error", "message": "standards-file-not-found"}

        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        report_data = {
            "status": "success",
            "total_standards": len(data.get('standards', {})),
            "standards": list(data.get('standards', {}).keys()),
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"standards={len(data.get('standards', {}))}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """Load and initialize the common coding standards.

    Creates the standards directory and file if they do not exist, then reads
    the standards data and reports the count. Called by 3-level-flow.py during
    Level 2 standards enforcement.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'standards_count' int.
              On error, 'message' key contains the exception string.
    """
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_action("ENFORCE_START", "common-standards-loading")

        # Ensure directory exists
        _op_start = datetime.now()
        STANDARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Initialize or upgrade standards file with real rules
        if not STANDARDS_FILE.exists() or _needs_upgrade(STANDARDS_FILE):
            standards_data = {
                "version": STANDARDS_VERSION,
                "standards": _build_common_standards(),
                "total_rules": 0,
                "loaded_at": datetime.now().isoformat()
            }
            total = 0
            for cat in standards_data["standards"].values():
                total += len(cat.get("rules", []))
            standards_data["total_rules"] = total
            STANDARDS_FILE.write_text(json.dumps(standards_data, indent=2), encoding='utf-8')
        try:
            _sub_operations.append(record_sub_operation(
                "init_standards_file", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        # Load standards and count real rules
        _op_start = datetime.now()
        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        standard_count = len(data.get('standards', {}))
        # Count actual rules across all categories
        total_rules = data.get('total_rules', 0)
        if total_rules == 0:
            for cat in data.get('standards', {}).values():
                if isinstance(cat, dict):
                    total_rules += len(cat.get('rules', []))
                else:
                    total_rules += 1  # legacy format
        try:
            _sub_operations.append(record_sub_operation(
                "load_standards", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"standards_count": standard_count, "total_rules": total_rules}
            ))
        except Exception:
            pass

        log_action("ENFORCE", f"common-standards-loaded | categories={standard_count} | rules={total_rules}")
        # Output in format 3-level-flow.py parses
        print(f"Common Standards: {standard_count}")
        print(f"Common Rules Loaded: {total_rules}")

        result = {"status": "success", "standards_count": standard_count, "total_rules": total_rules}
        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="common-standards-policy",
                policy_script="common-standards-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results=result,
                decision=f"loaded {standard_count} categories, {total_rules} rules",
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=_sub_operations if _sub_operations else None
            )
        except Exception:
            pass
        return result
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[common-standards-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="common-standards-policy",
                policy_script="common-standards-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results=error_result,
                decision=f"error: {str(e)}",
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=_sub_operations if _sub_operations else None
            )
        except Exception:
            pass
        return error_result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
    else:
        # Default: run enforcement
        enforce()
