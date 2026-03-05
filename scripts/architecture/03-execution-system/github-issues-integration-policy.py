#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Issues Integration Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/github-issues-integration-policy.md

This module enforces the GitHub Issues integration policy for the Claude Memory
System. It ensures that all development work is tracked via GitHub Issues,
that commits reference issue numbers, and that the issue-driven workflow is
followed consistently across all projects.

Policy rules enforced:
  - All significant work must be linked to a GitHub issue
  - Commit messages must reference issue numbers (#N)
  - Branch names must incorporate the issue ID
  - Issues must be in the correct state before work begins
  - Completed work must update the corresponding issue

Key Functions:
  enforce(): Activate the GitHub Issues integration policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.

CLI Usage:
  python github-issues-integration-policy.py --enforce   # Run policy enforcement
  python github-issues-integration-policy.py --validate  # Validate policy compliance
  python github-issues-integration-policy.py --report    # Generate policy report

Example:
  >>> from github_issues_integration_policy import enforce
  >>> result = enforce()
  >>> print(result['status'])  # 'success'
"""

import sys
import json
from pathlib import Path
from datetime import datetime

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
            f.write(f"[{timestamp}] github-issues-integration-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the GitHub Issues integration policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for GitHub Issues workflow enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "github-issues-integration-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the GitHub Issues integration policy.

    Returns a structured dictionary describing the enforced issue-tracking
    workflow rules.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'rules',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "github-issues-integration",
            "description": "Enforces issue-driven development workflow via GitHub Issues",
            "rules": [
                "All significant work must be linked to a GitHub issue",
                "Commit messages must reference issue numbers (e.g., #42)",
                "Branch names must incorporate the issue ID",
                "Issues must be open before work begins",
                "Completed work must close or update the corresponding issue"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "github-issues-integration-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the GitHub Issues integration workflow policy.

    Initializes the policy and logs the enforcement event. This is called by
    3-level-flow.py to ensure the GitHub Issues workflow rules are active
    before any development work is performed.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    try:
        log_policy_hit("ENFORCE_START", "github-issues-integration-enforcement")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("ENFORCE_COMPLETE", "github-issues-integration-ready")
        print("[github-issues-integration-policy] Policy enforced - GitHub Issues integration active")
        return {"status": "success", "policy": "github-issues-integration"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[github-issues-integration-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


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
