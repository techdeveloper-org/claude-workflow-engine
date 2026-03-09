#!/usr/bin/env python3
"""Selective Sync for Claude Global Library.

Direct wrapper around hook-downloader.py sync-claude-global-library command.
Calls hook-downloader to selectively sync only skills and agents.

Purpose: Quick sync for claude-global-library updates (skills, agents).
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Run selective sync for claude-global-library."""
    script_dir = Path(__file__).parent
    hook_downloader = script_dir / 'hook-downloader.py'

    if not hook_downloader.exists():
        print(f"[ERROR] hook-downloader.py not found in {script_dir}")
        return 1

    try:
        # Call hook-downloader with selective sync parameter
        result = subprocess.run(
            [sys.executable, str(hook_downloader), 'sync-claude-global-library'],
            check=False
        )
        return result.returncode
    except Exception as e:
        print(f"[ERROR] Failed to run sync-claude-global-library: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
