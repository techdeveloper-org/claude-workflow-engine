#!/usr/bin/env python3
"""Selective Sync for Claude Insight Repository.

Direct wrapper around hook-downloader.py sync-claude-insight command.
Calls hook-downloader to selectively sync only claude-insight components.

Purpose: Quick sync for claude-insight updates (scripts, policies, dashboard).
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Run selective sync for claude-insight."""
    script_dir = Path(__file__).parent
    hook_downloader = script_dir / 'hook-downloader.py'

    if not hook_downloader.exists():
        print(f"[ERROR] hook-downloader.py not found in {script_dir}")
        return 1

    try:
        # Call hook-downloader with selective sync parameter
        result = subprocess.run(
            [sys.executable, str(hook_downloader), 'sync-claude-insight'],
            check=False
        )
        return result.returncode
    except Exception as e:
        print(f"[ERROR] Failed to run sync-claude-insight: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
