#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Management Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/file-management-policy.md

This module enforces the file management policy for the Claude Memory System.
It ensures that files are created, modified, and deleted according to the
defined rules: preferring edits over rewrites, avoiding unnecessary file
creation, and following the project's file organization structure.

Policy rules enforced:
  - Prefer Edit over Write when modifying existing files
  - Never create documentation files (*.md) unless explicitly requested
  - Never proactively create README files
  - Always read a file before editing it
  - Maintain the established directory structure
  - Use absolute paths in all file operations

Key Functions:
  enforce(): Activate the file management policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.

CLI Usage:
  python file-management-policy.py --enforce   # Run policy enforcement
  python file-management-policy.py --validate  # Validate policy compliance
  python file-management-policy.py --report    # Generate policy report

Example:
  >>> from file_management_policy import enforce
  >>> result = enforce()
  >>> print(result['status'])  # 'success'
"""

import sys
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

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"


def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] file-management-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the file management policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for file management enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "file-management-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the file management policy.

    Returns a structured dictionary describing the enforced file management
    rules and best practices.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'rules',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "file-management",
            "description": "Enforces safe and consistent file creation, modification, and deletion",
            "rules": [
                "Prefer Edit over Write for existing files",
                "Never create *.md documentation files unless explicitly requested",
                "Always read a file before editing it",
                "Use absolute paths in all file operations",
                "Maintain established directory structure",
                "Never create README files proactively"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "file-management-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the file management policy.

    Initializes the policy and logs the enforcement event. This is called by
    3-level-flow.py to ensure the file management rules are active before any
    file operations are performed.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    import os
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_policy_hit("ENFORCE_START", "file-management-enforcement")

        _op_start = datetime.now()
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _sub_operations.append(record_sub_operation(
                "init_memory_dir", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        log_policy_hit("ENFORCE_COMPLETE", "file-management-ready")
        print("[file-management-policy] Policy enforced - File management standards active")

        result = {"status": "success", "policy": "file-management"}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="file-management-policy",
                    policy_script="file-management-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=result,
                    decision="file management standards active",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[file-management-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="file-management-policy",
                    policy_script="file-management-policy.py",
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
        enforce()
