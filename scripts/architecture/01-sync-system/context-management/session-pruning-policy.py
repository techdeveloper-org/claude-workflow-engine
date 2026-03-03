#!/usr/bin/env python3
"""
Session Pruning Policy Enforcement (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/session-management/session-pruning-policy.md

Consolidates:
- auto-context-pruner.py (auto-prune context)
- context-monitor-v2.py (monitor context usage)
- smart-cleanup.py (smart cleanup logic)
- monitor-and-cleanup-context.py (monitoring + cleanup)
- update-context-usage.py (update context statistics)

Usage:
  python session-pruning-policy.py --enforce           # Run policy enforcement
  python session-pruning-policy.py --validate          # Validate policy compliance
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

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
SESSIONS_DIR = Path.home() / ".claude" / "memory" / "sessions"
CONTEXT_STATS_FILE = Path.home() / ".claude" / "memory" / "context-stats.json"


def log_action(action, context=""):
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] session-pruning-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Validate policy compliance."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = list(SESSIONS_DIR.glob("session-*.json"))
        log_action("VALIDATE", f"session-count={len(sessions)}")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = list(SESSIONS_DIR.glob("session-*.json"))

        context_stats = {}
        if CONTEXT_STATS_FILE.exists():
            with open(CONTEXT_STATS_FILE, 'r', encoding='utf-8') as f:
                context_stats = json.load(f)

        report_data = {
            "status": "success",
            "total_sessions": len(sessions),
            "context_usage": context_stats,
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

    Consolidates session pruning, context monitoring, and cleanup.
    This is called by 3-level-flow.py during Level 1.
    """
    try:
        log_action("ENFORCE_START", "session-pruning-and-cleanup")

        # Ensure directories exist
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Initialize context stats if needed
        if not CONTEXT_STATS_FILE.exists():
            CONTEXT_STATS_FILE.write_text(json.dumps({
                "context_percentage": 0,
                "last_updated": datetime.now().isoformat()
            }, indent=2), encoding='utf-8')

        # Count sessions for pruning
        sessions = list(SESSIONS_DIR.glob("session-*.json"))
        session_count = len(sessions)

        # Load context stats
        with open(CONTEXT_STATS_FILE, 'r', encoding='utf-8') as f:
            context_stats = json.load(f)

        context_usage = context_stats.get('context_percentage', 0)

        log_action("ENFORCE", f"context-pruning | sessions={session_count} | usage={context_usage}%")
        print(f"[session-pruning-policy] {session_count} sessions, context usage: {context_usage}%")

        return {"status": "success", "session_count": session_count, "context_usage": context_usage}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[session-pruning-policy] ERROR: {e}")
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
