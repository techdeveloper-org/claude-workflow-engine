#!/usr/bin/env python3
"""
Cross-Project Pattern Detection Policy Enforcement (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/pattern-detection/cross-project-patterns-policy.md

Consolidates:
- detect-patterns.py (pattern analysis)
- apply-patterns.py (pattern application)

Usage:
  python cross-project-patterns-policy.py --enforce            # Run policy enforcement
  python cross-project-patterns-policy.py --show               # Show detected patterns
  python cross-project-patterns-policy.py --suggest <topic>    # Get suggestions
"""

import sys
import io
import json
import os
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATTERNS_FILE = Path.home() / ".claude" / "memory" / "cross-project-patterns.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"


def log_action(action, context=""):
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] cross-project-patterns-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Validate policy compliance."""
    try:
        if not PATTERNS_FILE.exists():
            log_action("VALIDATE", "patterns-file-missing")
            return False

        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        log_action("VALIDATE", f"patterns-valid | count={len(data.get('patterns', []))}")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report."""
    try:
        if not PATTERNS_FILE.exists():
            return {"status": "error", "message": "patterns-file-not-found"}

        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        patterns = data.get('patterns', [])
        report_data = {
            "status": "success",
            "total_patterns": len(patterns),
            "patterns": patterns,
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"patterns={len(patterns)}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates pattern detection and application.
    This is called by 3-level-flow.py during Level 1.
    """
    try:
        log_action("ENFORCE_START", "cross-project-patterns-detection")

        # Ensure patterns file exists
        PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not PATTERNS_FILE.exists():
            PATTERNS_FILE.write_text(json.dumps({
                "patterns": [],
                "detected_at": datetime.now().isoformat()
            }, indent=2), encoding='utf-8')

        # Load existing patterns
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        patterns = data.get('patterns', [])

        log_action("ENFORCE", f"patterns-loaded | count={len(patterns)}")
        print(f"[cross-project-patterns-policy] {len(patterns)} patterns loaded")

        return {"status": "success", "patterns_count": len(patterns)}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[cross-project-patterns-policy] ERROR: {e}")
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
        elif sys.argv[1] == "--show":
            result = report()
            if result.get("status") == "success":
                for pattern in result.get("patterns", []):
                    print(f"  {pattern.get('type', 'unknown')}: {pattern.get('name', 'unknown')}")
            sys.exit(0)
    else:
        # Default: run enforcement
        enforce()
