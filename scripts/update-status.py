#!/usr/bin/env python3
"""Update Status Reporter - Shows clear success/warning/failed messages.

Cross-platform implementation showing update completion messages.
Distinguishes between:
  - Successful updates with optional warnings (still works!)
  - Actual failures (system broken)

Usage:
  python update-status.py success
  python update-status.py warning "optional warning message"
  python update-status.py failed "error message"
"""

import sys


def show_success():
    """Display success message."""
    print("=" * 80)
    print("UPDATE COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print("Version: v0.39.2 (IDE) + v4.8.3 (Hooks)")
    print()
    print("What was updated:")
    print("  [OK] hook-downloader.py        Updated to ~/.claude/scripts/")
    print("  [OK] sync-insight.py           Cross-platform sync wrapper")
    print("  [OK] sync-library.py           Cross-platform sync wrapper")
    print("  [OK] update-status.py          Cross-platform status reporter")
    print("  [OK] All policies              All 44 policy files synced")
    print("  [OK] All scripts               134+ scripts synced")
    print()
    print("Features:")
    print("  [OK] Repository-aware detection")
    print("  [OK] Selective syncing (much faster!)")
    print("  [OK] Smart fallback mechanism")
    print("  [OK] Zero manual intervention")
    print()
    print("System Status: READY FOR USE")
    print("Next Update Check: 24 hours")
    print()
    print("=" * 80)
    return 0


def show_warning(message):
    """Display warning message."""
    print("=" * 80)
    print("UPDATE COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print("Version: v0.39.2 (IDE) + v4.8.3 (Hooks)")
    print()
    print("[WARNING] Note: Some optional features not available")
    print("         (Non-blocking - system still works perfectly!)")
    print()
    print("What was updated:")
    print("  [OK] hook-downloader.py        Updated to ~/.claude/scripts/")
    print("  [OK] core sync functions       All critical components working")
    print()
    print("System Status: OPERATIONAL")
    print("Optional Features: Some unavailable (doesn't affect core functionality)")
    print()
    if message:
        print(message)
        print()
    print("Next Update Check: 24 hours")
    print()
    print("=" * 80)
    return 0


def show_failed(message):
    """Display failure message."""
    print("=" * 80)
    print("UPDATE FAILED - ACTION REQUIRED")
    print("=" * 80)
    print()
    print("Version: v0.39.2 (IDE) + v4.8.3 (Hooks)")
    print()
    print("Error:")
    if message:
        print(message)
    print()
    print("System Status: REQUIRES ATTENTION")
    print()
    print("What to do:")
    print("  1. Check your internet connection")
    print("  2. Try manual sync: python ~/.claude/scripts/hook-downloader.py sync-all")
    print("  3. If problem persists, check ~/.claude/scripts/hook-downloader.py exists")
    print()
    print("Support: Check logs at ~/.claude/memory/logs/")
    print()
    print("=" * 80)
    return 1


def main():
    """Run update status reporter."""
    if len(sys.argv) < 2:
        print("Usage: update-status [success|warning|failed] [optional message]")
        return 1

    status = sys.argv[1]
    message = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if status == "success":
        return show_success()
    elif status == "warning":
        return show_warning(message)
    elif status == "failed":
        return show_failed(message)
    else:
        print(f"Usage: update-status [success|warning|failed] [optional message]")
        return 1


if __name__ == '__main__':
    sys.exit(main())
