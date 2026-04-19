#!/usr/bin/env python3
# BACKWARD-COMPAT SHIM
# Stop notification logic moved to hooks/stop_notifier/
# This file is invoked directly by Claude Code hooks.
import sys
from pathlib import Path as _Path

_HOOKS_DIR = _Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from stop_notifier.core import main  # noqa: E402

if __name__ == "__main__":
    main()
