# -*- coding: utf-8 -*-
"""
context_monitor.py - Level 1 Sync System: Context Window Usage Monitor

Estimates current context window usage from session data and tracks
context percentage across a conversation. Provides threshold-based
recommendations aligned with the context-management-policy.

Policy Reference: policies/01-sync-system/context-management/context-management-policy.md

Usage:
    python context_monitor.py                     # Estimate context from default session dir
    python context_monitor.py <session_dir>       # Estimate context from specific dir
    python context_monitor.py --json              # Output as JSON

Import usage:
    from context_monitor import estimate_context_usage
    info = estimate_context_usage(session_dir)
    # info["estimated_tokens"], info["percentage"], info["recommendation"]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONSTANTS (from context-management-policy.md)
# ============================================================================

# Approximate tokens per character for plain text (English, UTF-8)
CHARS_PER_TOKEN = 4.0

# Maximum context window size in tokens
MAX_CONTEXT_TOKENS = 200_000

# Reserve for Claude's response generation
RESERVE_FOR_RESPONSE = 20_000

# Usable token budget
USABLE_TOKENS = MAX_CONTEXT_TOKENS - RESERVE_FOR_RESPONSE

# Threshold zones
GREEN_THRESHOLD = 0.70  # 0 - 70%  -> OPTIMAL
YELLOW_THRESHOLD = 0.85  # 70 - 85% -> CAUTION
ORANGE_THRESHOLD = 0.95  # 85 - 95% -> ALERT
# Above 0.95              -> CRITICAL


# ============================================================================
# CORE FUNCTION
# ============================================================================


def estimate_context_usage(
    session_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Estimate context window usage from session data files.

    Reads session files in session_dir, counts approximate token usage,
    and returns a structured report with usage percentage and recommendation.

    Args:
        session_dir: Path to the session directory to analyse.
                     Defaults to ~/.claude/logs/sessions/ (most recent session).

    Returns:
        A dict with keys:
            - estimated_tokens (int): Approximate tokens currently in context.
            - max_tokens (int): Maximum context window size.
            - usable_tokens (int): Tokens available for use (excluding response reserve).
            - percentage (float): Fraction of usable tokens consumed (0.0 - 1.0+).
            - percentage_display (str): Human-readable percentage, e.g. "72.4%".
            - threshold_zone (str): "GREEN", "YELLOW", "ORANGE", or "RED".
            - recommendation (str): Action recommendation based on current usage.
            - files_analysed (int): Number of files read.
            - session_dir (str): Directory that was analysed.
            - timestamp (str): ISO timestamp of the estimate.
    """
    # Resolve the session directory
    resolved_dir = _resolve_session_dir(session_dir)

    # Gather text content from session files
    files_data = _read_session_files(resolved_dir)
    total_chars = sum(len(content) for content in files_data.values())
    estimated_tokens = _chars_to_tokens(total_chars)

    # Calculate usage ratios
    percentage = estimated_tokens / USABLE_TOKENS if USABLE_TOKENS > 0 else 0.0
    zone = _classify_zone(percentage)
    recommendation = _build_recommendation(zone, percentage, estimated_tokens)

    return {
        "estimated_tokens": estimated_tokens,
        "max_tokens": MAX_CONTEXT_TOKENS,
        "usable_tokens": USABLE_TOKENS,
        "percentage": round(percentage, 4),
        "percentage_display": f"{percentage * 100:.1f}%",
        "threshold_zone": zone,
        "recommendation": recommendation,
        "files_analysed": len(files_data),
        "session_dir": str(resolved_dir),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _resolve_session_dir(session_dir: Optional[Path]) -> Path:
    """Return the session directory to analyse, falling back to defaults."""
    if session_dir is not None:
        return Path(session_dir)

    # Default 1: most recent session inside ~/.claude/logs/sessions/
    sessions_root = Path.home() / ".claude" / "logs" / "sessions"
    if sessions_root.exists():
        subdirs = sorted(
            (d for d in sessions_root.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if subdirs:
            return subdirs[0]

    # Default 2: the sessions root itself
    if sessions_root.exists():
        return sessions_root

    # Default 3: current working directory
    return Path.cwd()


def _read_session_files(directory: Path) -> Dict[str, str]:
    """Read all text files in the directory (non-recursive) and return {path: content}."""
    if not directory.exists():
        return {}

    content_map: Dict[str, str] = {}
    text_extensions = {".md", ".txt", ".json", ".log", ".py", ".yaml", ".yml"}

    for item in directory.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() not in text_extensions:
            continue
        try:
            text = item.read_text(encoding="utf-8", errors="replace")
            content_map[str(item)] = text
        except OSError:
            pass

    return content_map


def _chars_to_tokens(char_count: int) -> int:
    """Approximate token count from character count."""
    return max(0, int(char_count / CHARS_PER_TOKEN))


def _classify_zone(percentage: float) -> str:
    """Return the threshold zone name for the given usage percentage."""
    if percentage < GREEN_THRESHOLD:
        return "GREEN"
    if percentage < YELLOW_THRESHOLD:
        return "YELLOW"
    if percentage < ORANGE_THRESHOLD:
        return "ORANGE"
    return "RED"


def _build_recommendation(zone: str, percentage: float, estimated_tokens: int) -> str:
    """Build a human-readable recommendation string for the given zone."""
    pct_str = f"{percentage * 100:.1f}%"
    remaining = max(0, USABLE_TOKENS - estimated_tokens)

    if zone == "GREEN":
        return (
            f"Context is OPTIMAL at {pct_str}. " f"Approximately {remaining:,} tokens remaining. " "No action needed."
        )
    if zone == "YELLOW":
        return (
            f"Context is at CAUTION level ({pct_str}). "
            f"Approximately {remaining:,} tokens remaining. "
            "Consider compressing large files and archiving old sessions."
        )
    if zone == "ORANGE":
        return (
            f"Context is at ALERT level ({pct_str}). "
            f"Approximately {remaining:,} tokens remaining. "
            "Perform aggressive cleanup: archive sessions older than 24 hours, "
            "reduce file cache to essentials, compress all files."
        )
    # RED
    return (
        f"Context is CRITICAL ({pct_str}). "
        f"Approximately {remaining:,} tokens remaining. "
        "EMERGENCY CLEANUP required: delete all non-current sessions, "
        "clear all caches, load files on-demand only."
    )


# ============================================================================
# MULTI-SESSION TRACKING
# ============================================================================


def track_context_over_sessions(
    sessions_root: Optional[Path] = None,
    last_n: int = 10,
) -> List[Dict[str, Any]]:
    """Estimate context usage across the most recent N sessions.

    Args:
        sessions_root: Root directory containing session subdirectories.
                       Defaults to ~/.claude/logs/sessions/.
        last_n: How many recent sessions to include.

    Returns:
        List of estimate dicts, ordered from oldest to newest.
    """
    if sessions_root is None:
        sessions_root = Path.home() / ".claude" / "logs" / "sessions"

    sessions_root = Path(sessions_root)
    if not sessions_root.exists():
        return []

    subdirs = sorted(
        (d for d in sessions_root.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    recent = subdirs[:last_n]
    # Oldest first for display
    recent.reverse()

    results = []
    for session_dir in recent:
        info = estimate_context_usage(session_dir)
        results.append(info)

    return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def _print_human(info: Dict[str, Any]) -> None:
    """Print a human-readable context usage report."""
    zone = info["threshold_zone"]
    zone_labels = {
        "GREEN": "OPTIMAL",
        "YELLOW": "CAUTION",
        "ORANGE": "ALERT",
        "RED": "CRITICAL",
    }
    print("\nContext Window Usage Report")
    print("=" * 50)
    print(f"  Session Dir:     {info['session_dir']}")
    print(f"  Timestamp:       {info['timestamp']}")
    print(f"  Files Analysed:  {info['files_analysed']}")
    print(f"  Estimated Tokens: {info['estimated_tokens']:,}")
    print(f"  Usable Budget:   {info['usable_tokens']:,}")
    print(f"  Usage:           {info['percentage_display']}")
    print(f"  Zone:            {zone} ({zone_labels.get(zone, zone)})")
    print("\n  Recommendation:")
    print(f"    {info['recommendation']}")
    print()


def main() -> int:
    """CLI entry point for context_monitor.py."""
    parser = argparse.ArgumentParser(description="Estimate Claude context window usage from session data.")
    parser.add_argument(
        "session_dir",
        nargs="?",
        default=None,
        help="Path to session directory to analyse (default: most recent session)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--track",
        action="store_true",
        help="Show context usage across last N sessions",
    )
    parser.add_argument(
        "--last-n",
        type=int,
        default=10,
        help="Number of recent sessions to include in --track mode (default: 10)",
    )
    args = parser.parse_args()

    if args.track:
        sessions_root = Path(args.session_dir) if args.session_dir else None
        history = track_context_over_sessions(sessions_root, last_n=args.last_n)
        if args.json:
            print(json.dumps(history, indent=2))
        else:
            print(f"\nContext Usage - Last {args.last_n} Sessions")
            print("=" * 60)
            for item in history:
                name = Path(item["session_dir"]).name
                print(f"  {name:<40} {item['percentage_display']:>8}  [{item['threshold_zone']}]")
            print()
        return 0

    session_dir = Path(args.session_dir) if args.session_dir else None
    info = estimate_context_usage(session_dir)

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        _print_human(info)

    return 0


if __name__ == "__main__":
    sys.exit(main())
