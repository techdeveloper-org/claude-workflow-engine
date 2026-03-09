#!/usr/bin/env python3
"""
Context Monitor v2.1 - Level 1 Sync System Policy

Monitor ACTUAL context usage from ~/.claude/memory/ and detect when limits approached.

Invoked by: 3-level-flow.py (Level 1 Sync System)

Version: 2.1.0
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

MEMORY_BASE = Path.home() / '.claude' / 'memory'
LOGS_DIR = MEMORY_BASE / 'logs'
SESSIONS_DIR = MEMORY_BASE / 'sessions'

# Context budget (estimate: 200KB = ~7000 tokens at 3.5 chars per token)
CONTEXT_BUDGET_KB = 200
CONTEXT_THRESHOLD_PERCENT = 85  # Alert when 85% full


def get_memory_size_kb(path: Path) -> float:
    """Calculate total size of directory in KB."""
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size / 1024

        for item in path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
        return total / 1024
    except Exception:
        return 0


def calculate_context_percentage() -> dict:
    """Calculate actual context usage percentage from memory logs."""
    try:
        # Get size of logs directory (main context usage)
        logs_size_kb = get_memory_size_kb(LOGS_DIR) if LOGS_DIR.exists() else 0

        # Get size of sessions directory (session context)
        sessions_size_kb = get_memory_size_kb(SESSIONS_DIR) if SESSIONS_DIR.exists() else 0

        # Total context used
        total_used_kb = logs_size_kb + sessions_size_kb

        # Calculate percentage
        percentage = (total_used_kb / CONTEXT_BUDGET_KB) * 100
        percentage = min(100, max(0, percentage))  # Clamp 0-100

        # Determine status
        if percentage > CONTEXT_THRESHOLD_PERCENT:
            status = "THRESHOLD_EXCEEDED"
            action = f"Context at {percentage:.1f}% - archive recommended"
        elif percentage > 70:
            status = "HIGH"
            action = f"Context at {percentage:.1f}% - monitor closely"
        else:
            status = "OK"
            action = f"Context at {percentage:.1f}% - normal"

        return {
            "percentage": percentage,
            "logs_size_kb": logs_size_kb,
            "sessions_size_kb": sessions_size_kb,
            "total_used_kb": total_used_kb,
            "budget_kb": CONTEXT_BUDGET_KB,
            "status": status,
            "action": action,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "percentage": 0.0,
            "logs_size_kb": 0,
            "sessions_size_kb": 0,
            "total_used_kb": 0,
            "budget_kb": CONTEXT_BUDGET_KB,
            "status": "ERROR",
            "action": f"Could not read context: {str(e)[:50]}",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


if __name__ == '__main__':
    # Parse arguments
    current_status = "--current-status" in sys.argv

    result = calculate_context_percentage()

    if current_status:
        # Return format expected by level1_sync.py
        output = {
            "status": "SUCCESS",
            "percentage": result["percentage"],
            "logs_size_kb": result["logs_size_kb"],
            "sessions_size_kb": result["sessions_size_kb"],
            "total_used_kb": result["total_used_kb"],
            "context_status": result["status"],
            "message": result["action"],
            "timestamp": result["timestamp"],
        }
    else:
        output = result

    # Output as JSON for LangGraph
    print(json.dumps(output))
