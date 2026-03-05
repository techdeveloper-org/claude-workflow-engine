#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update Context Usage Tracker
Manually updates actual context usage for monitoring

Since scripts can't access Claude Code's internal context,
Claude will manually update this file with actual token usage

Usage:
    python update-context-usage.py --tokens-used USED --tokens-total TOTAL

Examples:
    python update-context-usage.py --tokens-used 103780 --tokens-total 200000
    python update-context-usage.py --tokens-used 150000 --tokens-total 200000
"""

import sys
import os
import json
from datetime import datetime

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Thresholds (matching policy)
THRESHOLDS = {
    "light_cleanup": 70,
    "moderate_cleanup": 85,
    "aggressive_cleanup": 90,
}

def log_policy_hit(action, context):
    """Log a context tracker policy event to the policy hits log file.

    Args:
        action (str): The action label (e.g., 'updated').
        context (str): Additional context string describing the action.
    """
    log_file = os.path.expanduser("~/.claude/memory/logs/policy-hits.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] context-tracker | {action} | {context}\n"

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write log: {e}", file=sys.stderr)

def get_recommended_action(context_percent):
    """Return the recommended cleanup action for the given context percentage.

    Args:
        context_percent (float): Current context usage percentage.

    Returns:
        dict: Recommendation dictionary with keys:
            - level (str): Urgency level ('none', 'light', 'moderate', 'aggressive').
            - action (str): Action identifier string.
            - message (str): Human-readable status message.
            - urgency (str): Urgency string ('low', 'medium', 'high', 'critical').
    """
    if context_percent >= THRESHOLDS["aggressive_cleanup"]:
        return {
            "level": "aggressive",
            "action": "full-compact",
            "message": "CRITICAL: Full compact required NOW!",
            "urgency": "critical",
        }
    elif context_percent >= THRESHOLDS["moderate_cleanup"]:
        return {
            "level": "moderate",
            "action": "auto-compact",
            "message": "HIGH: Auto-compact recommended",
            "urgency": "high",
        }
    elif context_percent >= THRESHOLDS["light_cleanup"]:
        return {
            "level": "light",
            "action": "light-cleanup",
            "message": "MEDIUM: Light cleanup suggested",
            "urgency": "medium",
        }
    else:
        return {
            "level": "none",
            "action": "none",
            "message": "OK: No cleanup needed",
            "urgency": "low",
        }

def update_context_usage(tokens_used, tokens_total):
    """Save actual token counts to the context usage tracking file.

    Calculates the context percentage, derives a cleanup recommendation,
    writes all data to ~/.claude/memory/.context-usage as JSON, and prints
    a formatted status summary to stdout.

    Args:
        tokens_used (int): Number of tokens currently consumed.
        tokens_total (int): Total token limit (e.g., 200000).

    Returns:
        bool: True if the tracking file was written successfully, False otherwise.
    """

    # Calculate percentage
    context_percent = round((tokens_used / tokens_total) * 100, 1)

    # Get recommendation
    recommendation = get_recommended_action(context_percent)

    # Prepare data
    data = {
        "timestamp": datetime.now().isoformat(),
        "tokens_used": tokens_used,
        "tokens_total": tokens_total,
        "tokens_remaining": tokens_total - tokens_used,
        "context_percent": context_percent,
        "recommendation": recommendation,
    }

    # Save to tracking file
    tracking_file = os.path.expanduser("~/.claude/memory/.context-usage")

    try:
        with open(tracking_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print("\n" + "=" * 70)
        print("[CHART] CONTEXT USAGE UPDATED")
        print("=" * 70)
        print(f"\nTokens Used: {tokens_used:,} / {tokens_total:,}")
        print(f"Context: {context_percent}%")
        print(f"Remaining: {data['tokens_remaining']:,} tokens")
        print(f"\n[TARGET] {recommendation['message']}")
        print(f"   Action: {recommendation['action']}")
        print(f"   Urgency: {recommendation['urgency'].upper()}")
        print("\n" + "=" * 70)

        # Log update
        log_policy_hit("updated", f"{context_percent}%, action={recommendation['action']}")

        return True

    except Exception as e:
        print(f"[CROSS] Error saving context usage: {e}", file=sys.stderr)
        return False

def get_current_usage():
    """Get current context usage if available"""
    tracking_file = os.path.expanduser("~/.claude/memory/.context-usage")

    if not os.path.exists(tracking_file):
        return None

    try:
        with open(tracking_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def show_current_usage():
    """Show current tracked usage"""
    data = get_current_usage()

    if not data:
        print("\n[WARNING]️  No context usage data available")
        print("   Run with --tokens-used and --tokens-total to update")
        return

    print("\n" + "=" * 70)
    print("[CHART] CURRENT CONTEXT USAGE")
    print("=" * 70)
    print(f"\nLast Updated: {data['timestamp']}")
    print(f"Tokens Used: {data['tokens_used']:,} / {data['tokens_total']:,}")
    print(f"Context: {data['context_percent']}%")
    print(f"Remaining: {data['tokens_remaining']:,} tokens")

    rec = data['recommendation']
    print(f"\n[TARGET] {rec['message']}")
    print(f"   Action: {rec['action']}")
    print(f"   Urgency: {rec['urgency'].upper()}")
    print("\n" + "=" * 70)

def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Update actual context usage tracking"
    )
    parser.add_argument(
        '--tokens-used',
        type=int,
        help='Tokens currently used'
    )
    parser.add_argument(
        '--tokens-total',
        type=int,
        default=200000,
        help='Total token limit (default: 200000)'
    )
    parser.add_argument(
        '--show',
        action='store_true',
        help='Show current tracked usage'
    )

    if len(sys.argv) < 2:
        sys.exit(0)
    args = parser.parse_args()

    # Show current usage
    if args.show or (not args.tokens_used):
        show_current_usage()
        return

    # Update usage
    if args.tokens_used:
        success = update_context_usage(args.tokens_used, args.tokens_total)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
