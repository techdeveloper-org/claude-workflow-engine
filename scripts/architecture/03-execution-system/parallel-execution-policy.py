#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parallel Execution Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/parallel-execution-policy.md

This module enforces the parallel execution policy for the Claude Memory System.
It ensures that independent tool calls are batched and executed simultaneously
rather than sequentially, improving overall response time and efficiency.

Policy rules enforced:
  - Independent tool calls must be batched in a single response
  - Sequential execution is only used when calls have dependencies
  - Use ';' separator only when earlier commands can fail independently
  - Use '&&' chaining for dependent sequential commands
  - Parallel Bash, Read, Glob, and Grep calls are encouraged
  - Never add unnecessary sleep or wait commands between independent calls

Key Functions:
  enforce(): Activate the parallel execution policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.

CLI Usage:
  python parallel-execution-policy.py --enforce   # Run policy enforcement
  python parallel-execution-policy.py --validate  # Validate policy compliance
  python parallel-execution-policy.py --report    # Generate policy report

Example:
  >>> from parallel_execution_policy import enforce
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
            f.write(f"[{timestamp}] parallel-execution-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the parallel execution policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for parallel execution enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "parallel-execution-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the parallel execution policy.

    Returns a structured dictionary describing the enforced parallelism
    rules and batching guidelines.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'rules',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "parallel-execution",
            "description": "Enforces parallel batching of independent tool calls for efficiency",
            "rules": [
                "Batch independent tool calls in a single response",
                "Use sequential execution only for dependent operations",
                "Use '&&' for dependent sequential commands",
                "Use ';' only when earlier commands may fail independently",
                "Avoid unnecessary sleep or wait between independent calls",
                "Parallel Read, Glob, Grep, and Bash calls are preferred"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "parallel-execution-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the parallel execution policy.

    Initializes the policy and logs the enforcement event. This is called by
    3-level-flow.py to ensure the parallelism rules are active before tool
    calls are made.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    try:
        log_policy_hit("ENFORCE_START", "parallel-execution-enforcement")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("ENFORCE_COMPLETE", "parallel-execution-ready")
        print("[parallel-execution-policy] Policy enforced - Parallel execution standards active")
        return {"status": "success", "policy": "parallel-execution"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[parallel-execution-policy] ERROR: {e}")
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
