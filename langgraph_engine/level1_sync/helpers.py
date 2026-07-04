"""Level 1 Sync System - Shared helpers and common imports.

Canonical location for Level 1 shared constants, imports, and helper
functions used by all Level 1 node modules.

Windows-safe: ASCII only, no Unicode characters.

# v1.15.2: removed `import toons` try/except block (_TOONS_AVAILABLE) and
#           `from .toon_schema import validate_toon` try/except block
#           (_TOON_SCHEMA_AVAILABLE).  Both modules were deleted in v1.15.2 and
#           neither flag was read by any live caller.
"""

# ruff: noqa: F401

import subprocess
import time as _time_mod  # noqa: F401 -- used by node modules via import
from datetime import datetime  # noqa: F401 -- used by node modules via import
from pathlib import Path

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
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

# Shared utility: step logger
try:
    from ..step_logger import write_level_log  # noqa: F401
except ImportError:

    def write_level_log(*args, **kwargs):
        pass


# Structured logger: optional-enhancement load misses are logged, never swallowed.
try:
    from ..core.logger_factory import get_logger

    _ARCH_LOADER_LOGGER = get_logger(__name__)
except ImportError:
    import logging as _logging

    _ARCH_LOADER_LOGGER = _logging.getLogger(__name__)


# ============================================================================
# ARCHITECTURE SCRIPT LOADER (lazy, importlib-based)
# Scripts in level1_sync/architecture/ are not a Python package.
# Use importlib.util.spec_from_file_location for dynamic import.
# ============================================================================


def _load_architecture_script(script_name):
    """Dynamically load a script from level1_sync/architecture/.

    Resolves the path tolerantly so the hyphen->underscore module rename
    cannot silently disable an optional enhancement: the name is tried as
    given, then with hyphens converted to underscores, then via a glob on
    the stem, across both the canonical architecture/ directory and the
    legacy scripts/architecture/01-sync-system/ directory. A miss or an
    import failure is logged at WARNING and returns None so the caller can
    degrade gracefully -- the failure is never swallowed silently.

    Args:
        script_name: filename without path, e.g. "pattern_detector.py".

    Returns:
        Loaded module object, or None if it cannot be found or imported.
    """
    import importlib.util

    stem = script_name.replace("-", "_").replace(".py", "")
    arch_dir = Path(__file__).parent / "architecture"
    legacy_dir = Path(__file__).parent.parent.parent / "scripts" / "architecture" / "01-sync-system"

    script_path = None
    for base in (arch_dir, legacy_dir):
        for candidate in (base / script_name, base / (stem + ".py")):
            if candidate.exists():
                script_path = candidate
                break
        if script_path is not None:
            break
    if script_path is None:
        for base in (arch_dir, legacy_dir):
            matches = sorted(base.glob(stem + "*.py")) if base.exists() else []
            if matches:
                script_path = matches[0]
                break
    if script_path is None:
        _ARCH_LOADER_LOGGER.warning(f"level1_sync architecture script not found: {script_name}")
        return None

    try:
        spec = importlib.util.spec_from_file_location(stem, str(script_path))
        if spec is None or spec.loader is None:
            _ARCH_LOADER_LOGGER.warning(f"level1_sync architecture script has no import spec: {script_path}")
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # noqa: BLE001 - plugin boundary: an optional enhancement must never crash the pipeline
        _ARCH_LOADER_LOGGER.warning(f"level1_sync architecture script failed to import {script_path}: {exc}")
        return None
