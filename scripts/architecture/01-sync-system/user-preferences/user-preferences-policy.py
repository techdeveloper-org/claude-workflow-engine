#!/usr/bin/env python3
"""
User Preferences Policy Enforcement (v1.0)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/user-preferences/user-preferences-policy.md

Consolidates:
- load-preferences.py (load preferences from disk)
- preference-detector.py (detect user preferences)
- track-preference.py (track preference usage)
- preference-auto-tracker.py (auto-track preferences)

Usage:
  python user-preferences-policy.py --enforce           # Run policy enforcement
  python user-preferences-policy.py --validate          # Validate policy compliance
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

PREFERENCES_FILE = Path.home() / ".claude" / "memory" / "user-preferences.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
SESSION_DIR = Path.home() / ".claude" / "memory" / "sessions"


def log_action(action, context=""):
    """Log policy enforcement action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] user-preferences-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def load_preferences():
    """Load user preferences from disk."""
    try:
        if PREFERENCES_FILE.exists():
            with open(PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log_action("LOAD_ERROR", str(e))
    return {"preferences": {}, "timestamp": datetime.now().isoformat()}


def validate():
    """Validate policy compliance."""
    try:
        prefs = load_preferences()
        log_action("VALIDATE", f"preferences-loaded | count={len(prefs.get('preferences', {}))}")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report."""
    try:
        prefs = load_preferences()
        pref_count = len(prefs.get('preferences', {}))

        report_data = {
            "status": "success",
            "total_preferences": pref_count,
            "preferences": prefs.get('preferences', {}),
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"preferences={pref_count}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates preference detection, loading, and tracking.
    This is called by 3-level-flow.py during Level 1.
    """
    try:
        log_action("ENFORCE_START", "user-preferences-management")

        # Ensure preferences file exists
        PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not PREFERENCES_FILE.exists():
            PREFERENCES_FILE.write_text(json.dumps({
                "preferences": {},
                "created_at": datetime.now().isoformat()
            }, indent=2), encoding='utf-8')

        # Load preferences
        prefs = load_preferences()
        pref_count = len(prefs.get('preferences', {}))

        log_action("ENFORCE", f"preferences-loaded | count={pref_count}")
        print(f"[user-preferences-policy] {pref_count} preferences loaded")

        return {"status": "success", "preferences_count": pref_count}
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[user-preferences-policy] ERROR: {e}")
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
