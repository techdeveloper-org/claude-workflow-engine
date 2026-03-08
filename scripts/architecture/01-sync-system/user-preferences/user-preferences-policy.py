#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
User Preferences Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/user-preferences/user-preferences-policy.md

Consolidates 4 scripts (871+ lines):
- load-preferences.py (155 lines) - Load preferences from disk
- preference-detector.py (240 lines) - Detect preferences from logs
- track-preference.py (154 lines) - Track and learn preferences
- preference-auto-tracker.py (322 lines) - Auto-track daemon

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python user-preferences-policy.py --enforce           # Run policy enforcement
  python user-preferences-policy.py --validate          # Validate compliance
  python user-preferences-policy.py --report            # Generate report
  python user-preferences-policy.py <category>          # Get specific preference
  python user-preferences-policy.py --has <category>    # Check if preference exists
  python user-preferences-policy.py --track <cat> <val> # Track a preference
  python user-preferences-policy.py --detect [--json]   # Detect preferences from logs
"""

import sys
import io
import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta

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

PREFS_FILE = Path.home() / ".claude" / "memory" / "user-preferences.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
DAEMON_LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "preference-tracker-daemon.log"

# Preference detection patterns (from preference-detector.py)
PREFERENCE_PATTERNS = {
    "testing": {
        "skip": ["skip test", "no test", "skip testing", "without test", "don't need test"],
        "include": ["write test", "add test", "include test", "with test", "test case"],
        "tdd": ["tdd", "test driven", "test first"],
    },
    "api_style": {
        "rest": ["rest api", "restful", "rest endpoint", "use rest"],
        "graphql": ["graphql", "use graphql", "graph ql"],
        "grpc": ["grpc", "use grpc"],
    },
    "commit_frequency": {
        "frequent": ["commit often", "frequent commit", "small commit", "commit each"],
        "milestone": ["commit milestone", "commit phase", "commit when done", "big commit"],
        "feature": ["commit per feature", "feature commit"],
    },
    "documentation": {
        "inline": ["inline doc", "doc comment", "comment code", "document inline"],
        "separate": ["separate doc", "readme", "doc file", "external doc"],
        "minimal": ["minimal doc", "no doc", "skip doc", "light doc"],
    },
    "error_handling": {
        "verbose": ["verbose error", "detailed error", "full error", "show all error"],
        "minimal": ["minimal error", "simple error", "basic error", "hide error"],
        "user_friendly": ["user friendly error", "friendly error", "nice error"],
    },
    "code_style": {
        "verbose": ["verbose", "explicit", "detailed code", "full variable name"],
        "concise": ["concise", "short", "compact code", "brief"],
        "functional": ["functional", "immutable", "pure function"],
    },
}


def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] user-preferences-policy | {action} | {context}\n"

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log: {e}", file=sys.stderr)


def log_daemon(action, message):
    """Log a preference-tracker daemon activity to both daemon log and policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'AUTO-TRACK').
        message (str): Descriptive message for the log entry.
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] PREF-TRACKER-DAEMON | {action} | {message}\n"

        DAEMON_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DAEMON_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)

        log_policy_hit(action, message)
    except Exception as e:
        print(f"Warning: Could not log: {e}", file=sys.stderr)


def load_preferences():
    """Load the current preferences JSON from disk.

    Returns:
        dict: Parsed preferences data, or None if the file does not exist
              or cannot be parsed.
    """
    if not PREFS_FILE.exists():
        return None

    try:
        with open(PREFS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_preferences(prefs):
    """Write preferences dict to the preferences file, updating last_updated timestamp.

    Args:
        prefs (dict): Preferences dict with metadata sub-dict containing
                      a 'last_updated' field.
    """
    prefs['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, indent=2, ensure_ascii=False)


def get_preference(category):
    """Retrieve the learned value for a specific preference category.

    Args:
        category (str): The preference key to look up (e.g., 'testing',
                        'api_style', 'commit_frequency').

    Returns:
        The stored preference value, or None if not learned yet.
    """
    prefs = load_preferences()
    if not prefs:
        return None

    for cat_name in ['technology_preferences', 'language_preferences', 'workflow_preferences']:
        if cat_name in prefs and category in prefs[cat_name]:
            return prefs[cat_name][category]

    return None


def has_preference(category):
    """Check whether a preference has been learned for the given category.

    Args:
        category (str): The preference key to check.

    Returns:
        bool: True if a value has been learned for category, False otherwise.
    """
    value = get_preference(category)
    return value is not None


def show_all_preferences():
    """Print all learned preferences grouped by category to stdout."""
    prefs = load_preferences()
    if not prefs:
        print("[CROSS] No preferences file found")
        return

    print("[TARGET] Global User Preferences")
    print("=" * 60)

    # Technology Preferences
    if 'technology_preferences' in prefs:
        print("\n[U+1F4F1] Technology Preferences:")
        tech = prefs['technology_preferences']
        for key, value in tech.items():
            if value:
                print(f"  [CHECK] {key}: {value}")
            else:
                print(f"  - {key}: (not set)")

    # Language Preferences
    if 'language_preferences' in prefs:
        print("\n[U+1F4BB] Language Preferences:")
        lang = prefs['language_preferences']
        for key, value in lang.items():
            if value:
                print(f"  [CHECK] {key}: {value}")
            else:
                print(f"  - {key}: (not set)")

    # Workflow Preferences
    if 'workflow_preferences' in prefs:
        print("\n[GEAR] Workflow Preferences:")
        workflow = prefs['workflow_preferences']
        for key, value in workflow.items():
            if value:
                print(f"  [CHECK] {key}: {value}")
            else:
                print(f"  - {key}: (not set)")

    # Metadata
    if 'metadata' in prefs:
        print("\n[CHART] Statistics:")
        meta = prefs['metadata']
        print(f"  Total preferences learned: {meta.get('total_preferences_learned', 0)}")
        print(f"  Learning threshold: {meta.get('learning_threshold', 3)}")
        if meta.get('last_updated'):
            print(f"  Last updated: {meta['last_updated']}")

    print("\n" + "=" * 60)


def analyze_logs_for_preferences():
    """Scan the last 500 policy-hits log entries to detect user preference signals.

    Matches log lines against PREFERENCE_PATTERNS keyword lists.

    Returns:
        dict: Maps category name to a sub-dict of {value: count} pairs.
              Empty dict if the log file does not exist or cannot be read.
    """
    policy_log_file = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"

    if not policy_log_file.exists():
        return {}

    detected_preferences = {}

    try:
        with open(policy_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

            # Analyze last 500 log entries
            for line in lines[-500:]:
                line_lower = line.lower()

                for category, patterns in PREFERENCE_PATTERNS.items():
                    for value, keywords in patterns.items():
                        for keyword in keywords:
                            if keyword in line_lower:
                                if category not in detected_preferences:
                                    detected_preferences[category] = {}

                                if value not in detected_preferences[category]:
                                    detected_preferences[category][value] = 0

                                detected_preferences[category][value] += 1
                                break

    except Exception as e:
        print(f"Warning: Could not analyze logs: {e}", file=sys.stderr)

    return detected_preferences


def get_strongest_preference(category_prefs):
    """Return the most frequently detected preference value for a category.

    Args:
        category_prefs (dict): Mapping of value -> count for one category.

    Returns:
        tuple: (strongest_value, count) where strongest_value is the key
               with the highest count. Returns (None, 0) for empty input.
    """
    if not category_prefs:
        return None, 0

    max_count = 0
    strongest = None

    for value, count in category_prefs.items():
        if count > max_count:
            max_count = count
            strongest = value

    return strongest, max_count


def load_existing_preferences():
    """Load the current learned preferences from the preferences file.

    Returns:
        dict: Parsed preferences dict, or empty dict if missing or unreadable.
    """
    if not PREFS_FILE.exists():
        return {}

    try:
        with open(PREFS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def should_track_preference(category, value, count):
    """Determine whether a detected preference signal meets the tracking threshold.

    Args:
        category (str): The preference category name.
        value (str): The detected preference value.
        count (int): Number of times the signal was observed.

    Returns:
        bool: True if count >= 2 (minimum observation threshold).
    """
    return count >= 2


def track_preference(category, value):
    """Record a preference choice and promote it to global if threshold is reached.

    Appends the choice to learning_data. Once the same value is observed
    >= learning_threshold times, it is saved as the global preference for
    the category.

    Args:
        category (str): The preference category to track.
        value (str): The observed preference value.

    Returns:
        bool: True if tracking succeeded, False if category is unknown or
              preferences file is missing.
    """
    prefs = load_preferences()
    if not prefs:
        print("Error: Preferences file not initialized", file=sys.stderr)
        return False

    threshold = prefs.get('metadata', {}).get('learning_threshold', 3)

    # Validate category exists
    if category not in prefs.get('learning_data', {}):
        print(f"Error: Unknown category '{category}'", file=sys.stderr)
        print(f"Valid categories: {', '.join(prefs.get('learning_data', {}).keys())}", file=sys.stderr)
        return False

    # Add this choice to learning data
    prefs['learning_data'][category].append({
        'value': value,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

    # Count occurrences of this value
    value_count = sum(1 for item in prefs['learning_data'][category] if item['value'] == value)

    # Check if we've reached the learning threshold
    if value_count >= threshold:
        if category in prefs.get('technology_preferences', {}):
            current_pref = prefs['technology_preferences'].get(category)
            if current_pref != value:
                prefs['technology_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_policy_hit("TRACKED", f"{category}={value}")
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")

        elif category in prefs.get('language_preferences', {}):
            current_pref = prefs['language_preferences'].get(category)
            if current_pref != value:
                prefs['language_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_policy_hit("TRACKED", f"{category}={value}")
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")

        elif category in prefs.get('workflow_preferences', {}):
            current_pref = prefs['workflow_preferences'].get(category)
            if current_pref != value:
                prefs['workflow_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_policy_hit("TRACKED", f"{category}={value}")
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")
    else:
        print(f"[CHART] Choice recorded: {category} = {value}")
        print(f"   ({value_count}/{threshold} times observed)")

    save_preferences(prefs)
    return True


def process_detected_preferences(detection_result):
    """Process the output of analyze_logs_for_preferences and track strong signals.

    Args:
        detection_result (dict): Output from the detection step with 'detected'
                                 and 'existing' sub-dicts.

    Returns:
        int: Number of new preferences successfully tracked.
    """
    if not detection_result:
        return 0

    detected = detection_result.get("detected", {})
    existing = detection_result.get("existing", {})

    tracked_count = 0

    for category, values in detected.items():
        if not values:
            continue

        max_count = 0
        strongest_value = None

        for value, count in values.items():
            if count > max_count:
                max_count = count
                strongest_value = value

        if max_count >= 2:
            already_learned = False

            if category in existing:
                existing_val = existing[category]
                if isinstance(existing_val, dict):
                    already_learned = existing_val.get(category) == strongest_value
                else:
                    already_learned = existing_val == strongest_value

            if not already_learned:
                log_daemon("AUTO-TRACK", f"Tracking: {category}={strongest_value} (count={max_count})")
                if track_preference(category, strongest_value):
                    tracked_count += 1

    return tracked_count


def validate():
    """Check that the user preferences policy preconditions are met.

    Ensures the preferences file directory exists and is writable.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        log_policy_hit("VALIDATE", "user-preferences-ready")
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE_SUCCESS", "user-preferences-validated")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the user preferences policy.

    Returns:
        dict: Contains 'status', 'policy', 'total_preferences',
              'categories', and 'timestamp'.
              Returns {'status': 'error', ...} on failure.
    """
    try:
        prefs = load_preferences()
        pref_count = 0
        if prefs:
            pref_count = sum(len(cat) for cat in [
                prefs.get('technology_preferences', {}),
                prefs.get('language_preferences', {}),
                prefs.get('workflow_preferences', {})
            ])

        report_data = {
            "status": "success",
            "policy": "user-preferences",
            "total_preferences": pref_count,
            "categories": ["technology_preferences", "language_preferences", "workflow_preferences"],
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "user-preferences-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the user preferences policy.

    Consolidates preference loading, detection, and tracking from 4 old scripts:
    - load-preferences.py: Load preferences
    - preference-detector.py: Detect preferences
    - track-preference.py: Track and learn
    - preference-auto-tracker.py: Auto-track daemon

    Creates the preferences file with empty defaults if it does not exist,
    then loads and counts all currently learned preferences.

    Returns:
        dict: Contains 'status' ('success' or 'error') and
              'preferences_count'. On error, contains 'message'.
    """
    try:
        log_policy_hit("ENFORCE_START", "user-preferences-enforcement")

        # Ensure preferences file exists
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not PREFS_FILE.exists():
            initial_prefs = {
                "technology_preferences": {},
                "language_preferences": {},
                "workflow_preferences": {},
                "learning_data": {k: [] for k in PREFERENCE_PATTERNS.keys()},
                "metadata": {
                    "total_preferences_learned": 0,
                    "learning_threshold": 3,
                    "created_at": datetime.now().isoformat(),
                    "last_updated": None
                }
            }
            PREFS_FILE.write_text(json.dumps(initial_prefs, indent=2, ensure_ascii=False), encoding='utf-8')

        # Load preferences
        prefs = load_preferences()
        if prefs:
            pref_count = sum(len(cat) for cat in [
                prefs.get('technology_preferences', {}),
                prefs.get('language_preferences', {}),
                prefs.get('workflow_preferences', {})
            ])
        else:
            pref_count = 0

        log_policy_hit("ENFORCE_COMPLETE", f"user-preferences-ready | preferences={pref_count}")
        print(f"[user-preferences-policy] Policy enforced - {pref_count} preferences loaded")

        return {"status": "success", "preferences_count": pref_count}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[user-preferences-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            # Output JSON to stdout so callers (3-level-flow.py) can parse it
            if result and isinstance(result, dict):
                print(json.dumps(result))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--detect":
            is_json = "--json" in sys.argv
            detected = analyze_logs_for_preferences()
            existing = load_existing_preferences()

            if is_json:
                output = {
                    "detected": detected,
                    "existing": existing,
                    "timestamp": datetime.now().isoformat(),
                }
                print(json.dumps(output, indent=2))
            else:
                print("\n" + "=" * 70)
                print("[SEARCH] USER PREFERENCE DETECTION")
                print("=" * 70)

                if not detected:
                    print("\n[WARNING] No preferences detected in recent logs")
                else:
                    print("\n[CHART] Detected Preferences:")
                    for category, values in detected.items():
                        strongest, count = get_strongest_preference(values)
                        print(f"\n[U+1F4CC] {category.replace('_', ' ').title()}:")

                        for value, val_count in sorted(values.items(), key=lambda x: x[1], reverse=True):
                            marker = "[CHECK]" if value == strongest else "  "
                            learned = "[CHECK] LEARNED" if category in existing and existing.get(category) == value else ""
                            trackable = "-> TRACKABLE" if should_track_preference(category, value, val_count) else ""

                            print(f"   {marker} {value}: {val_count} occurrences {learned} {trackable}")

                print("\n" + "=" * 70)
        elif sys.argv[1] == "--track" and len(sys.argv) >= 4:
            category = sys.argv[2]
            value = sys.argv[3]
            track_preference(category, value)
        elif sys.argv[1] == "--has" and len(sys.argv) >= 3:
            category = sys.argv[2]
            if has_preference(category):
                print("yes")
                sys.exit(0)
            else:
                print("no")
                sys.exit(1)
        else:
            # Get specific preference
            category = sys.argv[1]
            value = get_preference(category)

            if value:
                print(value)
                sys.exit(0)
            else:
                sys.exit(1)
    else:
        # No arguments - show all preferences
        show_all_preferences()
