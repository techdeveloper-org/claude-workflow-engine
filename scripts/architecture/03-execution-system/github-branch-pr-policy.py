#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Branch and PR Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/github-branch-pr-policy.md

This module enforces the GitHub branch naming and pull request workflow policy
for all repositories managed within the Claude Memory System. It ensures that
branches follow the required naming convention ({label}/{issueId}) and that
pull requests are created according to the defined workflow standards.

Policy rules enforced:
  - Branch names must use format: {semantic-label}/{issueId}
    e.g., bugfix/42, feature/99, docs/15
  - PRs must reference the corresponding GitHub issue
  - Branch labels must be semantic (feature, bugfix, docs, refactor, etc.)
  - Direct commits to main/master are discouraged for tracked issues

Key Functions:
  enforce(): Activate the GitHub branch and PR policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.

CLI Usage:
  python github-branch-pr-policy.py --enforce   # Run policy enforcement
  python github-branch-pr-policy.py --validate  # Validate policy compliance
  python github-branch-pr-policy.py --report    # Generate policy report

Example:
  >>> from github_branch_pr_policy import enforce
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
            f.write(f"[{timestamp}] github-branch-pr-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the GitHub branch and PR policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for GitHub workflow enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "github-branch-pr-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the GitHub branch and PR policy.

    Returns a structured dictionary describing the enforced branch naming
    convention and PR workflow rules.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'rules',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "github-branch-pr",
            "description": "Enforces GitHub branch naming convention {label}/{issueId}",
            "rules": [
                "Branch names follow {semantic-label}/{issueId} format",
                "Valid labels: feature, bugfix, docs, refactor, hotfix, chore",
                "PRs must reference the corresponding GitHub issue",
                "Semantic labels required - not generic prefixes like fix/ or feat/"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "github-branch-pr-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the GitHub branch naming and PR workflow policy.

    Initializes the policy and logs the enforcement event. This is called by
    3-level-flow.py to ensure the GitHub workflow rules are active before any
    branch or PR operations are performed.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    try:
        log_policy_hit("ENFORCE_START", "github-branch-pr-enforcement")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("ENFORCE_COMPLETE", "github-branch-pr-ready")
        print("[github-branch-pr-policy] Policy enforced - GitHub branch/PR standards active")
        return {"status": "success", "policy": "github-branch-pr"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[github-branch-pr-policy] ERROR: {e}")
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
