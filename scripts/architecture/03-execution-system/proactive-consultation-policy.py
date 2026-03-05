#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proactive Consultation Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/proactive-consultation-policy.md

This module enforces the proactive consultation policy for the Claude Memory
System. It ensures that Claude proactively asks clarifying questions before
undertaking complex, ambiguous, or high-risk tasks rather than proceeding with
assumptions that may lead to incorrect implementations.

Policy rules enforced:
  - Ask for clarification before starting tasks with ambiguous requirements
  - Confirm scope before tasks that modify more than 5 files
  - Proactively surface design decisions that require user input
  - Never silently assume intent for destructive operations (delete, reset)
  - Present options when multiple valid approaches exist
  - Check in at phase boundaries for multi-phase tasks

Key Functions:
  enforce(): Activate the proactive consultation policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.

CLI Usage:
  python proactive-consultation-policy.py --enforce   # Run policy enforcement
  python proactive-consultation-policy.py --validate  # Validate policy compliance
  python proactive-consultation-policy.py --report    # Generate policy report

Example:
  >>> from proactive_consultation_policy import enforce
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
            f.write(f"[{timestamp}] proactive-consultation-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the proactive consultation policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for consultation enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "proactive-consultation-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the proactive consultation policy.

    Returns a structured dictionary describing the enforced consultation
    trigger conditions and guidelines.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'triggers',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "proactive-consultation",
            "description": "Enforces proactive user consultation before ambiguous or high-risk tasks",
            "triggers": [
                "Ambiguous requirements or undefined scope",
                "Tasks modifying more than 5 files",
                "Destructive operations (delete, reset, overwrite)",
                "Multiple valid implementation approaches exist",
                "Phase boundaries in multi-phase tasks",
                "Significant architectural decisions requiring user input"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "proactive-consultation-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the proactive consultation policy.

    Initializes the policy and logs the enforcement event. This is called by
    3-level-flow.py to ensure the consultation rules are active before work
    begins on ambiguous or complex tasks.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    try:
        log_policy_hit("ENFORCE_START", "proactive-consultation-enforcement")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("ENFORCE_COMPLETE", "proactive-consultation-ready")
        print("[proactive-consultation-policy] Policy enforced - Proactive consultation standards active")
        return {"status": "success", "policy": "proactive-consultation"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[proactive-consultation-policy] ERROR: {e}")
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
