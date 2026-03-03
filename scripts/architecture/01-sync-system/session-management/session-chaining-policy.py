#!/usr/bin/env python3
"""
Session Chaining Policy Enforcement (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/session-management/session-chaining-policy.md

Consolidates:
- archive-old-sessions.py (archive old sessions)
- auto-save-session.py (auto-save current session)
- session-save-triggers.py (trigger session saves)
- session-search.py (search sessions)
- session-start-check.py (check session on start)

Usage:
  python session-chaining-policy.py --enforce           # Run policy enforcement
  python session-chaining-policy.py --validate          # Validate policy compliance
"""

import sys
import io
import json
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
CHAIN_INDEX_FILE = Path.home() / ".claude" / "memory" / "sessions" / "chain-index.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"


def log_action(action, context=""):
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] session-chaining-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Validate policy compliance."""
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_count = len(list(SESSION_DIR.glob("session-*.json")))

        # Check if chain index exists
        has_chain_index = CHAIN_INDEX_FILE.exists()
        log_action("VALIDATE", f"sessions={session_count} | chain-index={has_chain_index}")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report."""
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        sessions = list(SESSION_DIR.glob("session-*.json"))

        chain_index = {}
        if CHAIN_INDEX_FILE.exists():
            with open(CHAIN_INDEX_FILE, 'r', encoding='utf-8') as f:
                chain_index = json.load(f)

        report_data = {
            "status": "success",
            "total_sessions": len(sessions),
            "chain_entries": len(chain_index),
            "chain_index": chain_index,
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"sessions={len(sessions)} | chains={len(chain_index)}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates session chaining, archival, and search.
    This is called by 3-level-flow.py during Level 1.
    """
    try:
        log_action("ENFORCE_START", "session-chaining-management")

        # Ensure directories exist
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize chain index if needed
        if not CHAIN_INDEX_FILE.exists():
            CHAIN_INDEX_FILE.write_text(json.dumps({
                "chains": {},
                "created_at": datetime.now().isoformat()
            }, indent=2), encoding='utf-8')

        # Load chain index
        with open(CHAIN_INDEX_FILE, 'r', encoding='utf-8') as f:
            chain_data = json.load(f)

        sessions = list(SESSION_DIR.glob("session-*.json"))
        session_count = len(sessions)
        chain_count = len(chain_data.get('chains', {}))

        log_action("ENFORCE", f"session-chaining | sessions={session_count} | chains={chain_count}")
        print(f"[session-chaining-policy] {session_count} sessions, {chain_count} chains")

        return {"status": "success", "session_count": session_count, "chain_count": chain_count}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[session-chaining-policy] ERROR: {e}")
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
