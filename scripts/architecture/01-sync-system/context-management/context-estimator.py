#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Context Usage Estimator
Estimates context window usage based on observable metrics

Since we can't access Claude Code's internal context tracking,
we estimate based on:
- Message count
- File reads
- Tool calls
- Session duration

Usage:
    python context-estimator.py [--session-dir DIR]

Examples:
    python context-estimator.py
    python context-estimator.py --session-dir /path/to/session
"""

import sys
import os
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows encoding issues
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Estimation weights (tuned based on observation)
WEIGHTS = {
    "message_count": 1.5,      # Each message ~1.5% context
    "file_read": 3.0,          # Each file read ~3% context
    "large_file_read": 8.0,    # Large file (>500 lines) ~8% context
    "tool_call": 1.0,          # Each tool call ~1% context
    "mcp_response": 2.0,       # Each MCP response ~2% context
    "session_age_minutes": 0.1, # Long sessions accumulate context
}

# Thresholds
THRESHOLDS = {
    "light_cleanup": 70,
    "moderate_cleanup": 85,
    "aggressive_cleanup": 90,
}

def log_policy_hit(action, context):
    """Log a policy execution event to the policy hits log file.

    Args:
        action (str): The action being logged (e.g., 'estimated').
        context (str): Additional context about the action.
    """
    log_file = os.path.expanduser("~/.claude/memory/logs/policy-hits.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] context-estimator | {action} | {context}\n"

    try:
        with open(log_file, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log: {e}", file=sys.stderr)

def get_session_metrics():
    """Collect observable session metrics from log files.

    Parses the policy hits log to count recent activity within the last 2 hours,
    including messages, file reads, tool calls, and MCP responses. Session
    start time is detected from the earliest log entry in this window.

    Returns:
        dict: Session metrics dictionary with keys:
            - message_count (int): Number of messages in current session.
            - file_reads (int): Number of file read operations.
            - large_file_reads (int): Number of large file read operations.
            - tool_calls (int): Number of tool call operations.
            - mcp_responses (int): Number of MCP response entries.
            - session_start (datetime or None): Session start timestamp.
            - session_duration_minutes (float): Session duration in minutes.
    """
    metrics = {
        "message_count": 0,
        "file_reads": 0,
        "large_file_reads": 0,
        "tool_calls": 0,
        "mcp_responses": 0,
        "session_start": None,
        "session_duration_minutes": 0,
    }

    # Try to detect session metrics from environment/logs
    # This is an estimation - adjust based on actual usage patterns

    # Check logs for recent activity
    log_file = os.path.expanduser("~/.claude/memory/logs/policy-hits.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

                # Count recent activity (last 2 hours)
                cutoff_time = datetime.now() - timedelta(hours=2)

                for line in lines[-500:]:  # Check last 500 log entries
                    try:
                        # Parse timestamp
                        if line.startswith('['):
                            timestamp_str = line[1:20]  # [YYYY-MM-DD HH:MM:SS]
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                            if timestamp > cutoff_time:
                                # Count different types of activity
                                if 'session-memory' in line:
                                    metrics["message_count"] += 1
                                if 'file-read' in line or 'Read' in line:
                                    metrics["file_reads"] += 1
                                if 'tool-call' in line or 'Bash' in line or 'Grep' in line:
                                    metrics["tool_calls"] += 1
                                if 'mcp' in line.lower():
                                    metrics["mcp_responses"] += 1

                                # Track session start
                                if metrics["session_start"] is None or timestamp < metrics["session_start"]:
                                    metrics["session_start"] = timestamp
                    except:
                        continue

        except Exception as e:
            print(f"Warning: Could not read logs: {e}", file=sys.stderr)

    # Calculate session duration
    if metrics["session_start"]:
        duration = datetime.now() - metrics["session_start"]
        metrics["session_duration_minutes"] = duration.total_seconds() / 60

    # Heuristic: Assume some baseline activity if logs are empty
    if metrics["message_count"] == 0:
        # Fresh session or no logs - assume minimal context
        metrics["message_count"] = 1

    return metrics

def estimate_context_percentage(metrics):
    """Estimate context window usage percentage based on observable session metrics.

    Uses a weighted formula to estimate context consumption:
    context% = (messages * 1.5) + (file_reads * 3.0) + (large_files * 8.0)
               + (tool_calls * 1.0) + (mcp_responses * 2.0)
               + (session_age_minutes * 0.1)

    The result is capped at 100%. Very fresh sessions (under 5 minutes) get a
    50% reduction with a minimum floor of 10%.

    Args:
        metrics (dict): Session metrics as returned by get_session_metrics().

    Returns:
        float: Estimated context usage percentage, rounded to 1 decimal place,
            in the range [10.0, 100.0].
    """

    estimated = (
        metrics["message_count"] * WEIGHTS["message_count"] +
        metrics["file_reads"] * WEIGHTS["file_read"] +
        metrics["large_file_reads"] * WEIGHTS["large_file_read"] +
        metrics["tool_calls"] * WEIGHTS["tool_call"] +
        metrics["mcp_responses"] * WEIGHTS["mcp_response"] +
        metrics["session_duration_minutes"] * WEIGHTS["session_age_minutes"]
    )

    # Cap at 100%
    estimated = min(estimated, 100)

    # Apply decay for very fresh sessions
    if metrics["session_duration_minutes"] < 5:
        estimated = max(estimated * 0.5, 10)  # Fresh sessions start at ~10%

    return round(estimated, 1)

def get_recommended_action(context_percent):
    """Return recommended cleanup action based on the estimated context percentage.

    Thresholds:
    - >= aggressive_cleanup (90%): Critical urgency, red level.
    - >= moderate_cleanup (85%): High urgency, yellow level.
    - >= light_cleanup (70%): Medium urgency, yellow level.
    - < light_cleanup: No action needed, green level.

    Args:
        context_percent (float): Estimated context usage percentage.

    Returns:
        dict: Recommendation dictionary with keys:
            - level (str): Urgency level ('none', 'light', 'moderate', 'aggressive').
            - action (str): Human-readable action description.
            - urgency (str): Urgency string ('low', 'medium', 'high', 'critical').
            - color (str): Display color ('green', 'yellow', 'red').
    """
    if context_percent >= THRESHOLDS["aggressive_cleanup"]:
        return {
            "level": "aggressive",
            "action": "CRITICAL: Immediate cleanup required",
            "urgency": "critical",
            "color": "red",
        }
    elif context_percent >= THRESHOLDS["moderate_cleanup"]:
        return {
            "level": "moderate",
            "action": "HIGH: Cleanup recommended soon",
            "urgency": "high",
            "color": "yellow",
        }
    elif context_percent >= THRESHOLDS["light_cleanup"]:
        return {
            "level": "light",
            "action": "MEDIUM: Consider cleanup",
            "urgency": "medium",
            "color": "yellow",
        }
    else:
        return {
            "level": "none",
            "action": "OK: No cleanup needed",
            "urgency": "low",
            "color": "green",
        }

def save_estimate(context_percent, metrics):
    """Save the current context estimate to the estimate file.

    The estimate file is read by other monitoring scripts and daemons.

    Args:
        context_percent (float): Estimated context usage percentage.
        metrics (dict): Session metrics used to produce the estimate.
    """
    estimate_file = os.path.expanduser("~/.claude/memory/.context-estimate")

    data = {
        "timestamp": datetime.now().isoformat(),
        "context_percent": context_percent,
        "metrics": metrics,
        "recommendation": get_recommended_action(context_percent),
    }

    try:
        with open(estimate_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save estimate: {e}", file=sys.stderr)

def load_previous_estimate():
    """Load the previously saved context estimate from file.

    Handles both the current JSON format and the legacy plain float format.

    Returns:
        dict or None: Previously saved estimate dictionary with 'context_percent',
            'timestamp', 'metrics', and 'recommendation' keys, or None if no
            previous estimate exists or the file cannot be read.
    """
    estimate_file = os.path.expanduser("~/.claude/memory/.context-estimate")

    if not os.path.exists(estimate_file):
        return None

    try:
        with open(estimate_file, 'r') as f:
            data = json.load(f)
            # Handle legacy float format
            if isinstance(data, (int, float)):
                return {
                    "context_percent": float(data),
                    "timestamp": datetime.now().isoformat(),
                    "metrics": {},
                    "recommendation": get_recommended_action(float(data))
                }
            return data
    except:
        return None

def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    print("\n" + "=" * 70)
    print("[CHART] CONTEXT USAGE ESTIMATOR")
    print("=" * 70)

    # Get session metrics
    print("\n[SEARCH] Collecting session metrics...")
    metrics = get_session_metrics()

    print("\n[U+1F4C8] Session Activity:")
    print(f"   Messages: {metrics['message_count']}")
    print(f"   File Reads: {metrics['file_reads']}")
    print(f"   Tool Calls: {metrics['tool_calls']}")
    print(f"   MCP Responses: {metrics['mcp_responses']}")
    print(f"   Session Duration: {metrics['session_duration_minutes']:.1f} minutes")

    # Estimate context percentage
    context_percent = estimate_context_percentage(metrics)

    print("\n" + "=" * 70)
    print(f"[CHART] ESTIMATED CONTEXT USAGE: {context_percent}%")
    print("=" * 70)

    # Get recommendation
    recommendation = get_recommended_action(context_percent)

    print(f"\n[TARGET] Status: {recommendation['action']}")
    print(f"   Level: {recommendation['level'].upper()}")
    print(f"   Urgency: {recommendation['urgency'].upper()}")

    # Compare with previous estimate
    prev_estimate = load_previous_estimate()
    if prev_estimate:
        prev_percent = prev_estimate['context_percent']
        change = context_percent - prev_percent

        print(f"\n[U+1F4C8] Change from last check:")
        print(f"   Previous: {prev_percent}%")
        print(f"   Current: {context_percent}%")
        print(f"   Delta: {change:+.1f}%")

    # Save current estimate
    save_estimate(context_percent, metrics)

    # Log estimation
    log_policy_hit("estimated", f"{context_percent}% (level={recommendation['level']})")

    print("\n" + "=" * 70)
    print("[CHECK] Estimate saved to: ~/.claude/memory/.context-estimate")
    print("=" * 70)

    # Exit code indicates urgency
    if context_percent >= THRESHOLDS["aggressive_cleanup"]:
        sys.exit(2)  # Critical
    elif context_percent >= THRESHOLDS["light_cleanup"]:
        sys.exit(1)  # Warning
    else:
        sys.exit(0)  # OK

if __name__ == "__main__":
    main()
