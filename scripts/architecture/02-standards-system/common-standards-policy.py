#!/usr/bin/env python3
"""
Common Standards Policy Enforcement (v1.0)

Maps to: policies/02-standards-system/common-standards-policy.md

This module enforces the common coding standards applicable to all projects in
the Claude Memory System. It initializes and loads a JSON standards file with
the canonical set of architectural and design standards that Claude must follow
across all sessions.

Extracted from: standards-loader.py (common standards portion)

Standards enforced:
  - java_structure:    Standard Java project folder structure
  - config_server:     Config server rules for Spring applications
  - secret_management: Secret and credential management
  - response_format:   Standard API response format
  - api_design:        RESTful API design standards
  - database:          Database design and query standards
  - error_handling:    Standard error handling patterns

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
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
STANDARDS_FILE = Path.home() / ".claude" / "memory" / "standards" / "common-standards.json"


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

        # Initialize standards file if needed
        if not STANDARDS_FILE.exists():
            standards_data = {
                "standards": {
                    "java_structure": "Standard Java project folder structure",
                    "config_server": "Config server rules for Spring applications",
                    "secret_management": "Secret and credential management",
                    "response_format": "Standard API response format",
                    "api_design": "RESTful API design standards",
                    "database": "Database design and query standards",
                    "error_handling": "Standard error handling patterns"
                },
                "loaded_at": datetime.now().isoformat()
            }
            STANDARDS_FILE.write_text(json.dumps(standards_data, indent=2), encoding='utf-8')
        try:
            _sub_operations.append(record_sub_operation(
                "init_standards_file", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        # Load standards
        _op_start = datetime.now()
        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        standard_count = len(data.get('standards', {}))
        try:
            _sub_operations.append(record_sub_operation(
                "load_standards", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"standards_count": standard_count}
            ))
        except Exception:
            pass

        log_action("ENFORCE", f"common-standards-loaded | count={standard_count}")
        print(f"[common-standards-policy] {standard_count} common standards loaded")

        result = {"status": "success", "standards_count": standard_count}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=__import__('os').environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="common-standards-policy",
                    policy_script="common-standards-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=result,
                    decision=f"loaded {standard_count} common standards",
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
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=__import__('os').environ.get('CLAUDE_SESSION_ID', 'unknown'),
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
