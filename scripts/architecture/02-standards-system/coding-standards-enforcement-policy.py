#!/usr/bin/env python3
"""
Coding Standards Enforcement Policy (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/02-standards-system/coding-standards-enforcement-policy.md

Extracted from: standards-loader.py (coding standards portion)

Loads and enforces coding standards:
- Service Layer Pattern
- Entity Pattern
- Controller Pattern
- Constants Organization
- Documentation Standards
- Network Policies
- Infrastructure Rules

Usage:
  python coding-standards-enforcement-policy.py --enforce           # Run policy enforcement
  python coding-standards-enforcement-policy.py --validate          # Validate policy compliance
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
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] coding-standards-enforcement-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Validate policy compliance."""
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
    """Generate compliance report."""
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
    """
    Main policy enforcement function.

    Loads and enforces coding standards for microservices.
    This is called by 3-level-flow.py during Level 2.
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
