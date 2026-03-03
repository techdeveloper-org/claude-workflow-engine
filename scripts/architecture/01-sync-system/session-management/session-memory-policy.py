#!/usr/bin/env python3
"""
Session Memory Policy Enforcement (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/session-management/session-memory-policy.md

Consolidates:
- session-loader.py (load session from disk)
- session-state.py (manage session state)
- protect-session-memory.py (protect session memory)

Usage:
  python session-memory-policy.py --enforce           # Run policy enforcement
  python session-memory-policy.py --validate          # Validate policy compliance
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

SESSION_DIR = Path.home() / ".claude" / "memory" / "sessions"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"


def log_action(action, context=""):
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] session-memory-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Validate policy compliance."""
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_count = len(list(SESSION_DIR.glob("session-*.json")))
        log_action("VALIDATE", f"session-count={session_count}")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report."""
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        sessions = list(SESSION_DIR.glob("session-*.json"))

        report_data = {
            "status": "success",
            "total_sessions": len(sessions),
            "sessions": [s.name for s in sessions],
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"sessions={len(sessions)}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates session memory management, loading, and protection.
    This is called by 3-level-flow.py during Level 1.
    """
    try:
        log_action("ENFORCE_START", "session-memory-management")

        # Ensure session directory exists
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        # Count sessions
        sessions = list(SESSION_DIR.glob("session-*.json"))
        session_count = len(sessions)

        # Protect session directory permissions (on Unix systems)
        if sys.platform != 'win32':
            os.chmod(SESSION_DIR, 0o700)

        log_action("ENFORCE", f"session-memory-protected | count={session_count}")
        print(f"[session-memory-policy] {session_count} sessions in memory")

        return {"status": "success", "session_count": session_count}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[session-memory-policy] ERROR: {e}")
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
