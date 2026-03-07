#!/usr/bin/env python3
"""
Global User Preference Tracker
Learns user preferences from repeated choices across sessions.

Usage:
  python track-preference.py <category> <value>

Examples:
  python track-preference.py testing skip
  python track-preference.py api_style REST
  python track-preference.py backend python
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


import json
import os
import sys
import io
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emojis

PREFS_FILE = Path.home() / ".claude" / "memory" / "user-preferences.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"


def load_preferences():
    """Load current preferences from file."""
    if not PREFS_FILE.exists():
        print(f"Error: Preferences file not found: {PREFS_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(PREFS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_preferences(prefs):
    """Save preferences back to file."""
    prefs['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(PREFS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, indent=2)


def log_preference_learned(category, value):
    """Log when a preference is learned."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] user-preferences | learned | {category}={value}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def track_preference(category, value):
    """
    Track a user preference choice.
    After threshold occurrences, save as global preference.
    """
    prefs = load_preferences()
    threshold = prefs['metadata']['learning_threshold']

    # Validate category exists
    if category not in prefs['learning_data']:
        print(f"Error: Unknown category '{category}'", file=sys.stderr)
        print(f"Valid categories: {', '.join(prefs['learning_data'].keys())}", file=sys.stderr)
        sys.exit(1)

    # Add this choice to learning data
    prefs['learning_data'][category].append({
        'value': value,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

    # Count occurrences of this value
    value_count = sum(1 for item in prefs['learning_data'][category] if item['value'] == value)

    # Check if we've reached the learning threshold
    if value_count >= threshold:
        # Determine which top-level category this belongs to
        if category in prefs['technology_preferences']:
            current_pref = prefs['technology_preferences'].get(category)
            if current_pref != value:
                prefs['technology_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_preference_learned(category, value)
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")

        elif category in prefs['language_preferences']:
            current_pref = prefs['language_preferences'].get(category)
            if current_pref != value:
                prefs['language_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_preference_learned(category, value)
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")

        elif category in prefs['workflow_preferences']:
            current_pref = prefs['workflow_preferences'].get(category)
            if current_pref != value:
                prefs['workflow_preferences'][category] = value
                prefs['metadata']['total_preferences_learned'] += 1
                log_preference_learned(category, value)
                print(f"[CHECK] Preference learned: {category} = {value}")
                print(f"   (Observed {value_count}x, threshold: {threshold})")
            else:
                print(f"[CHECK] Preference confirmed: {category} = {value}")
    else:
        print(f"[CHART] Choice recorded: {category} = {value}")
        print(f"   ({value_count}/{threshold} times observed)")

    save_preferences(prefs)


def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    if len(sys.argv) != 3:
        print("Usage: python track-preference.py <category> <value>")
        print("\nExamples:")
        print("  python track-preference.py testing skip")
        print("  python track-preference.py api_style REST")
        print("  python track-preference.py backend python")
        sys.exit(0)

    category = sys.argv[1]
    value = sys.argv[2]

    track_preference(category, value)


if __name__ == "__main__":
    main()
