"""Level 1 Sync System - Shared helpers and common imports.

Canonical location for Level 1 shared constants, imports, and helper
functions used by all Level 1 node modules.

Windows-safe: ASCII only, no Unicode characters.
"""

# ruff: noqa: F401

import subprocess
import time as _time_mod  # noqa: F401 -- used by node modules via import
from datetime import datetime  # noqa: F401 -- used by node modules via import
from pathlib import Path

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_session_logs_dir, get_telemetry_dir

    _LEVEL1_SESSION_LOGS_DIR = get_session_logs_dir()
    _LEVEL1_TELEMETRY_DIR = get_telemetry_dir()
except ImportError:
    _LEVEL1_SESSION_LOGS_DIR = Path.home() / ".claude" / "logs" / "sessions"
    _LEVEL1_TELEMETRY_DIR = Path.home() / ".claude" / "logs" / "telemetry"

try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


try:
    import toons  # noqa: F401

    _TOONS_AVAILABLE = True
except ImportError:
    _TOONS_AVAILABLE = False

# Level 1 new modules (graceful import fallback)
try:
    from ..complexity_calculator import calculate_complexity, calculate_graph_complexity, should_plan  # noqa: F401

    _COMPLEXITY_CALCULATOR_AVAILABLE = True
except ImportError:
    _COMPLEXITY_CALCULATOR_AVAILABLE = False

    def calculate_graph_complexity(*args, **kwargs):
        return 0, {}, 0.0


try:
    from .context_cache import ContextCache  # noqa: F401

    _CONTEXT_CACHE_AVAILABLE = True
except ImportError:
    _CONTEXT_CACHE_AVAILABLE = False

try:
    from .context_deduplicator import deduplicate_context  # noqa: F401

    _DEDUPLICATOR_AVAILABLE = True
except ImportError:
    _DEDUPLICATOR_AVAILABLE = False

try:
    from .toon_schema import validate_toon  # noqa: F401

    _TOON_SCHEMA_AVAILABLE = True
except ImportError:
    _TOON_SCHEMA_AVAILABLE = False

# Shared utility: step logger
try:
    from ..step_logger import write_level_log  # noqa: F401
except ImportError:

    def write_level_log(*args, **kwargs):
        pass


# ============================================================================
# ARCHITECTURE SCRIPT LOADER (lazy, importlib-based)
# Scripts in level1_sync/architecture/ are not a Python package.
# Use importlib.util.spec_from_file_location for dynamic import.
# ============================================================================


def _load_architecture_script(script_name):
    """Dynamically load a script from level1_sync/architecture/.

    Returns the loaded module, or None if the file does not exist or
    fails to import.  All failures are silently swallowed so that the
    pipeline is never blocked by an optional enhancement.

    Args:
        script_name: filename without path, e.g. "pattern-detector.py"

    Returns:
        Loaded module object, or None on any failure.
    """
    try:
        import importlib.util

        # Try level-based location first (canonical)
        script_path = Path(__file__).parent / "architecture" / script_name
        if not script_path.exists():
            # Fallback to legacy location
            script_path = Path(__file__).parent.parent.parent / "architecture" / "01-sync-system" / script_name
        if not script_path.exists():
            return None
        # Convert filename to a valid Python module name
        module_name = script_name.replace("-", "_").replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, str(script_path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None
