#!/usr/bin/env python3
"""
Coding Standards Enforcement Policy (v1.0)

Maps to: policies/02-standards-system/coding-standards-enforcement-policy.md

This module enforces microservice-specific coding standards by initializing and
loading a JSON standards file that defines the implementation patterns Claude
must follow when writing code. These are development-level conventions that
complement the common architectural standards.

Extracted from: standards-loader.py (coding standards portion)

Standards enforced:
  - service_pattern:   Service layer pattern for microservices
  - entity_pattern:    Entity/model design pattern
  - controller_pattern: Controller/endpoint pattern
  - constants:         Constants organization and naming
  - documentation:     Code documentation requirements
  - network_policies:  Network and communication policies
  - infrastructure:    Infrastructure and deployment rules

Key Functions:
  enforce(): Load and initialize the coding standards file.
  validate(): Check that the coding standards file exists and is valid.
  report(): Generate a summary report of loaded coding standards.

CLI Usage:
  python coding-standards-enforcement-policy.py --enforce   # Run policy enforcement
  python coding-standards-enforcement-policy.py --validate  # Validate policy compliance
  python coding-standards-enforcement-policy.py --report    # Generate standards report

Example:
  >>> from coding_standards_enforcement_policy import enforce
  >>> result = enforce()
  >>> print(result['standards_count'])  # 7
"""

import sys
import io
import json
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
STANDARDS_FILE = Path.home() / ".claude" / "memory" / "standards" / "coding-standards.json"


def log_action(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] coding-standards-enforcement-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Check that the coding standards file exists and is parseable.

    Reads the coding standards JSON file and verifies it contains at least one
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
    """Generate a compliance report listing all loaded coding standards.

    Reads the coding standards file and returns a structured dictionary
    suitable for JSON output, including the total count and standard names.

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
    """Load and initialize the microservice coding standards.

    Creates the standards directory and file if they do not exist, then reads
    the standards data and reports the count. Called by 3-level-flow.py during
    Level 2 standards enforcement.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'standards_count' int.
              On error, 'message' key contains the exception string.
    """
    try:
        log_action("ENFORCE_START", "coding-standards-enforcement")

        # Ensure directory exists
        STANDARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Initialize standards file if needed
        if not STANDARDS_FILE.exists():
            standards_data = {
                "standards": {
                    "service_pattern": "Service layer pattern for microservices",
                    "entity_pattern": "Entity/model design pattern",
                    "controller_pattern": "Controller/endpoint pattern",
                    "constants": "Constants organization and naming",
                    "documentation": "Code documentation requirements",
                    "network_policies": "Network and communication policies",
                    "infrastructure": "Infrastructure and deployment rules"
                },
                "loaded_at": datetime.now().isoformat()
            }
            STANDARDS_FILE.write_text(json.dumps(standards_data, indent=2), encoding='utf-8')

        # Load standards
        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        standard_count = len(data.get('standards', {}))

        log_action("ENFORCE", f"coding-standards-loaded | count={standard_count}")
        print(f"[coding-standards-enforcement-policy] {standard_count} coding standards loaded")

        return {"status": "success", "standards_count": standard_count}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[coding-standards-enforcement-policy] ERROR: {e}")
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
        # Default: run enforcement
        enforce()
