"""
Level 1 SubGraph - Context Sync System (CORRECTED)

CORRECT FLOW (per user specification):
1. node_session_loader (FIRST) - Create session in ~/.claude/logs/sessions/{session_id}/
2. node_complexity_calculation (PARALLEL with #3) - Analyze project structure
3. node_context_loader (PARALLEL with #2) - Read SRS, README, CLAUDE.md from PROJECT
4. node_toon_compression (NEW) - Compress to TOON format + clear memory
5. level1_merge_node - Final merge

Optimization features (Task #6):
- Cache integration with hit/miss rate logging (via CacheStats)
- Per-file and total timeouts with graceful partial-context recovery
- Memory-pressure streaming for files >1MB (chunked read, no full load)
- OOM safeguard: total load budget enforced across all files
"""

# ruff: noqa: F821, F401

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
    import toons

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
    from ..level1_sync.context_cache import ContextCache

    _CONTEXT_CACHE_AVAILABLE = True
except ImportError:
    _CONTEXT_CACHE_AVAILABLE = False

try:
    from ..level1_sync.context_deduplicator import deduplicate_context

    _DEDUPLICATOR_AVAILABLE = True
except ImportError:
    _DEDUPLICATOR_AVAILABLE = False

try:
    from ..level1_sync.toon_schema import validate_toon

    _TOON_SCHEMA_AVAILABLE = True
except ImportError:
    _TOON_SCHEMA_AVAILABLE = False


# ============================================================================
# ARCHITECTURE SCRIPT LOADER (lazy, importlib-based)
# Scripts in scripts/architecture/01-sync-system/ are not a Python package.
# Use importlib.util.spec_from_file_location for dynamic import.
# ============================================================================


def _load_architecture_script(script_name: str):
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

        # Try new level-based location first
        script_path = Path(__file__).parent.parent / "level1_sync" / "architecture" / script_name
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


# ============================================================================
# NODE 1: SESSION LOADER (MUST BE FIRST)
# ============================================================================
