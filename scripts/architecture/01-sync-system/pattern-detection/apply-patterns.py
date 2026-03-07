#!/usr/bin/env python3
"""
Cross-Project Pattern Application
Suggests relevant patterns when starting work on a topic.

Usage:
  python apply-patterns.py <topic>

Examples:
  python apply-patterns.py authentication
  python apply-patterns.py "rest api"
  python apply-patterns.py database
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
import sys
import io
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding

PATTERNS_FILE = Path.home() / ".claude" / "memory" / "cross-project-patterns.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"


def log_action(action, context):
    """Log pattern application."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] pattern-detection | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def load_patterns():
    """Load patterns from file."""
    if not PATTERNS_FILE.exists():
        return None

    try:
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def find_relevant_patterns(topic):
    """Find patterns relevant to a topic."""
    patterns_data = load_patterns()

    if not patterns_data or not patterns_data.get('patterns'):
        return None

    topic_lower = topic.lower()
    matches = []

    # Search in pattern names and types
    for pattern in patterns_data['patterns']:
        score = 0

        # Exact match in name
        if topic_lower == pattern['name'].lower():
            score += 10
        # Partial match in name
        elif topic_lower in pattern['name'].lower():
            score += 5
        # Match in type
        elif topic_lower in pattern['type'].lower():
            score += 3

        # Also check keywords
        keywords = [
            'auth' if 'authentication' in pattern['type'] else '',
            'api' if 'api_style' in pattern['type'] else '',
            'lang' if 'language' in pattern['type'] else '',
            'front' if 'frontend' in pattern['type'] else '',
        ]

        for keyword in keywords:
            if keyword and keyword in topic_lower:
                score += 2

        if score > 0:
            matches.append((score, pattern))

    # Sort by score (highest first)
    matches.sort(key=lambda x: (x[0], x[1]['confidence']), reverse=True)

    return [m[1] for m in matches]


def apply_patterns(topic):
    """Apply relevant patterns and show suggestions."""
    patterns = find_relevant_patterns(topic)

    if not patterns:
        print(f"[BULB] No established patterns found for: {topic}")
        print("\n   This might be a new approach!")
        print("   Run pattern detection after completing this work:")
        print("   python ~/.claude/memory/detect-patterns.py")
        return

    print(f"[BULB] Based on your past projects, here are relevant patterns:")
    print("=" * 70)

    for i, pattern in enumerate(patterns[:5], 1):  # Show top 5
        confidence_bar = '█' * int(pattern['confidence'] * 10)
        strength = "STRONG" if pattern['confidence'] >= 0.8 else "MODERATE" if pattern['confidence'] >= 0.6 else "WEAK"

        print(f"\n{i}. {pattern['name'].upper()} ({strength} PATTERN)")
        print(f"   Confidence: [{confidence_bar:<10}] {pattern['confidence']:.0%}")
        print(f"   Category: {pattern['type'].replace('_', ' ').title()}")
        print(f"   Used in: {pattern['occurrences']} of your projects")
        print(f"   Projects: {', '.join(pattern['projects'][:3])}")
        if len(pattern['projects']) > 3:
            print(f"            ... and {len(pattern['projects']) - 3} more")

        # Specific suggestions based on pattern type
        if pattern['type'] == 'authentication':
            print(f"\n   [BULB] Suggestion: Consider using {pattern['name']} authentication")
            print(f"      You've successfully used this in {pattern['occurrences']} projects")

        elif pattern['type'] == 'api_style':
            print(f"\n   [BULB] Suggestion: Build a {pattern['name'].upper()} API")
            print(f"      This matches your established pattern across projects")

        elif pattern['type'] == 'languages':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} for implementation")
            print(f"      You have strong experience with this language")

        elif pattern['type'] == 'frontend':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} for the frontend")
            print(f"      Consistent with your project history")

        elif pattern['type'] == 'databases':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} as database")
            print(f"      You've worked with this in {pattern['occurrences']} projects")

    print("\n" + "=" * 70)
    print("[U+1F4DD] Note: These are suggestions based on your patterns.")
    print("   You can always choose a different approach!")

    log_action('applied', f'topic={topic} | {len(patterns)} patterns suggested')


def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    if len(sys.argv) < 2:
        print("Usage: python apply-patterns.py <topic>")
        print("\nExamples:")
        print("  python apply-patterns.py authentication")
        print("  python apply-patterns.py 'rest api'")
        print("  python apply-patterns.py database")
        sys.exit(0)

    topic = ' '.join(sys.argv[1:])
    apply_patterns(topic)


if __name__ == "__main__":
    main()
