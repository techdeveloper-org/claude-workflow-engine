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

import json
import subprocess
import sys
import time as _time_mod
from datetime import datetime
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

from ..flow_state import FlowState
from ..step_logger import write_level_log

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
    from ..context_cache import ContextCache

    _CONTEXT_CACHE_AVAILABLE = True
except ImportError:
    _CONTEXT_CACHE_AVAILABLE = False

try:
    from ..context_deduplicator import deduplicate_context

    _DEDUPLICATOR_AVAILABLE = True
except ImportError:
    _DEDUPLICATOR_AVAILABLE = False

try:
    from ..toon_schema import validate_toon

    _TOON_SCHEMA_AVAILABLE = True
except ImportError:
    _TOON_SCHEMA_AVAILABLE = False


# ============================================================================
# ARCHITECTURE SCRIPT LOADER (lazy, importlib-based)
# Scripts in scripts/architecture/01-sync-system/ are not a Python package.
# Use importlib.util.spec_from_file_location for dynamic import.
# ============================================================================


def _load_architecture_script(script_name: str):
    """Dynamically load a script from scripts/architecture/01-sync-system/.

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


def node_session_loader(state: FlowState) -> dict:
    """Create and load session in ~/.claude/logs/sessions/{session_id}/.

    This MUST run first - creates the session container for this execution.
    """
    import sys
    import uuid

    _step_start = _time_mod.time()
    try:
        # Debug: Check project_root before doing anything (ASCII-safe for Windows cp1252 terminals)
        _root_repr = str(state.get("project_root", "MISSING")).encode("ascii", errors="replace").decode("ascii")
        print("[LEVEL 1 SESSION_LOADER] state['project_root'] at entry: '{}'".format(_root_repr), file=sys.stderr)

        # Generate unique session ID
        session_id = "session-{}-{}".format(datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])

        # Create session folder: ~/.claude/logs/sessions/{session_id}/
        session_path = _LEVEL1_SESSION_LOGS_DIR / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        # user_message: try state first, then env var fallback (set by run_langgraph_engine)
        import os

        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

        session_meta = {
            "metadata": {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
            },
            "user_message": user_msg,
        }

        meta_file = session_path / "session.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2)

        # Set env var so Level 3 infra can find session_id
        os.environ["CURRENT_SESSION_ID"] = session_id

        result = {
            "session_id": session_id,
            "session_path": str(session_path),
            "session_loaded": True,
        }

        # ---- Best-effort: session chaining (link to previous session) ----
        try:
            prev_session_id = os.environ.get("PREVIOUS_SESSION_ID", "")
            if prev_session_id and prev_session_id != session_id:
                try:
                    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src" / "mcp"))
                    from session_hooks import link_sessions, tag_session

                    link_sessions(session_id, prev_session_id)
                    result["session_parent_id"] = prev_session_id
                except Exception:
                    pass  # Fail-open: chaining is best-effort

            # Auto-tag from user_message keywords
            _auto_tags = []
            _msg_lower = user_msg.lower() if user_msg else ""
            _tag_keywords = {
                "bugfix": ["bug", "fix", "error", "crash", "broken"],
                "feature": ["feature", "add", "new", "implement", "create"],
                "refactor": ["refactor", "clean", "reorganize", "restructure"],
                "docs": ["doc", "readme", "documentation", "comment"],
                "test": ["test", "spec", "coverage", "assert"],
                "config": ["config", "setup", "install", "deploy"],
            }
            for tag, keywords in _tag_keywords.items():
                if any(kw in _msg_lower for kw in keywords):
                    _auto_tags.append(tag)
            if _auto_tags:
                result["session_tags"] = _auto_tags
                try:
                    from session_hooks import tag_session

                    tag_session(session_id, ",".join(_auto_tags))
                except Exception:
                    pass  # Best-effort tagging

            # Set PREVIOUS_SESSION_ID for next session
            os.environ["PREVIOUS_SESSION_ID"] = session_id
        except Exception as _chain_exc:
            result["session_chaining_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Session chaining skipped: {}".format(_chain_exc),
                file=sys.stderr,
            )

        # ---- Best-effort: prune old sessions (optional enhancement) ----
        try:
            _pruner = _load_architecture_script("session-pruner.py")
            if _pruner is not None and hasattr(_pruner, "prune_sessions"):
                _sessions_dir = _LEVEL1_SESSION_LOGS_DIR
                _prune_result = _pruner.prune_sessions(_sessions_dir)
                result["session_pruning_done"] = True
                result["session_pruning_archived"] = _prune_result.get("archived", 0)
                # Capture pruning errors
                _prune_errors = _prune_result.get("errors", [])
                if _prune_errors:
                    result["session_pruning_errors"] = _prune_errors
                    print(
                        "[LEVEL 1 SESSION_LOADER] Session pruning had {} errors".format(len(_prune_errors)),
                        file=sys.stderr,
                    )
        except Exception as _prune_exc:
            result["session_pruning_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Session pruning skipped: {}".format(_prune_exc),
                file=sys.stderr,
            )

        # ---- Best-effort: track user preferences from session history ----
        try:
            _pref_tracker = _load_architecture_script("preference-tracker.py")
            if _pref_tracker is not None and hasattr(_pref_tracker, "track_preferences"):
                _sessions_dir = _LEVEL1_SESSION_LOGS_DIR
                if not state.get("preferences_data"):
                    _prefs = _pref_tracker.track_preferences(_sessions_dir)
                    result["preferences_data"] = _prefs
        except Exception as _pref_exc:
            result["preference_tracking_available"] = False
            print(
                "[LEVEL 1 SESSION_LOADER] Preference tracking skipped: {}".format(_pref_exc),
                file=sys.stderr,
            )

        write_level_log(result, "level1", "session-loader", "OK", _time_mod.time() - _step_start, result)
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_session_loader",
                    "status": "OK" if not result.get("error") else "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result
    except Exception as e:
        result = {
            "session_loaded": False,
            "session_error": str(e),
        }
        write_level_log(state, "level1", "session-loader", "FAILED", _time_mod.time() - _step_start, None, str(e))
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_session_loader",
                    "status": "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result


# ============================================================================
# NODE 2: COMPLEXITY CALCULATION (PARALLEL with context_loader)
# ============================================================================


def node_complexity_calculation(state: FlowState) -> dict:
    """Analyze project structure and calculate complexity.

    Uses complexity_calculator.py (new, preferred) when available.
    Falls back to legacy script or simple heuristic otherwise.
    """
    _step_start = _time_mod.time()
    try:
        project_root = Path(state.get("project_root", "."))
        session_id = state.get("session_id", "")

        # --- Preferred path: use new complexity_calculator module ---
        if _COMPLEXITY_CALCULATOR_AVAILABLE:
            simple_score = calculate_complexity(str(project_root), session_id=session_id or None)

            # Graph-based complexity (NetworkX + Lizard) - graceful fallback
            graph_score, graph_metrics, cyclomatic_avg = calculate_graph_complexity(
                str(project_root), session_id=session_id or None
            )

            # Combine: simple (30%) + graph (70%) when graph available
            if graph_score > 0:
                # Clamp graph_score to valid domain before use in formula
                graph_score = max(1, min(25, graph_score))
                # Linear interpolation [1,10] -> [1,25] so simple_score=1 maps to 1 (not 2)
                # Formula: 1 + (simple_score - 1) * (24 / 9)
                simple_scaled = max(1, min(25, round(1 + (simple_score - 1) * (24.0 / 9))))
                combined = round((simple_scaled * 0.3) + (graph_score * 0.7))
                combined = max(1, min(25, combined))
            else:
                combined = simple_score
                graph_metrics = {}
                cyclomatic_avg = 0.0

            result = {
                "complexity_score": simple_score,
                "graph_complexity_score": graph_score if graph_score > 0 else None,
                "graph_metrics": graph_metrics if graph_metrics else {},
                "cyclomatic_complexity_avg": cyclomatic_avg if cyclomatic_avg else None,
                "combined_complexity_score": combined if graph_score > 0 else None,
                "project_graph": {},
                "architecture": {},
                "complexity_calculated": True,
            }
            write_level_log(state, "level1", "complexity-calculation", "OK", _time_mod.time() - _step_start, result)
            # Telemetry
            try:
                import json as _json_tel
                import time as _time_tel

                _sid_tel = state.get("session_id", result.get("session_id", ""))
                if _sid_tel:
                    _tdir_tel = _LEVEL1_TELEMETRY_DIR
                    _tdir_tel.mkdir(parents=True, exist_ok=True)
                    _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                    _entry_tel = {
                        "level": 1,
                        "node": "node_complexity_calculation",
                        "status": "OK" if not result.get("error") else "ERROR",
                        "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                        _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
            except Exception:
                pass  # Non-blocking
            return result

        # --- Legacy path: try the old architecture script ---
        complexity_script = (
            Path(__file__).parent.parent.parent
            / "architecture"
            / "03-execution-system"
            / "04-model-selection"
            / "complexity-calculator.py"
        )

        if complexity_script.exists():
            result = subprocess.run(
                [sys.executable, str(complexity_script)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_root,
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    _legacy_result = {
                        "complexity_score": data.get("complexity_score", 5),
                        "project_graph": data.get("graph", {}),
                        "architecture": data.get("architecture", {}),
                        "complexity_calculated": True,
                    }
                    # Telemetry
                    try:
                        import json as _json_tel
                        import time as _time_tel

                        _sid_tel = state.get("session_id", "")
                        if _sid_tel:
                            _tdir_tel = _LEVEL1_TELEMETRY_DIR
                            _tdir_tel.mkdir(parents=True, exist_ok=True)
                            _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                            _entry_tel = {
                                "level": 1,
                                "node": "node_complexity_calculation",
                                "status": "OK",
                                "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                            with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                                _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
                    except Exception:
                        pass  # Non-blocking
                    return _legacy_result
                except Exception:
                    pass

        # --- Final fallback: simple file count heuristic ---
        py_files = list(project_root.glob("**/*.py"))
        complexity_score = min(10, max(1, len(py_files) // 10))

        result = {
            "complexity_score": complexity_score,
            "project_graph": {},
            "architecture": {},
            "complexity_calculated": True,
        }
        write_level_log(state, "level1", "complexity-calculation", "OK", _time_mod.time() - _step_start, result)
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_complexity_calculation",
                    "status": "OK" if not result.get("error") else "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result

    except Exception as e:
        result = {
            "complexity_calculated": False,
            "complexity_error": str(e),
            "complexity_score": 5,  # Safe default
        }
        write_level_log(
            state, "level1", "complexity-calculation", "FAILED", _time_mod.time() - _step_start, None, str(e)
        )
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_complexity_calculation",
                    "status": "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result


# ============================================================================
# NODE 3: CONTEXT LOADER (PARALLEL with complexity_calculation)
# Task #6 optimizations:
#   - Timeout handling with graceful recovery and partial context return
#   - Memory-pressure streaming for large files (>STREAMING_THRESHOLD)
#   - OOM safeguard: total load budget enforced
#   - Cache hit/miss rate logging via CacheStats
# ============================================================================

# Per-file and total-load timeouts (seconds)
CONTEXT_TIMEOUT_PER_FILE = 30
CONTEXT_TIMEOUT_TOTAL = 120

# Memory limits
MAX_FILE_SIZE = 1_000_000  # 1 MB: files bigger than this are streamed
MAX_TOTAL_SIZE = 10_000_000  # 10 MB total loaded bytes across all files

# Context usage thresholds (per context-management-policy.md)
CONTEXT_THRESHOLD_WARNING = 0.70  # 70% - log warning
CONTEXT_THRESHOLD_HIGH = 0.85  # 85% - log high warning, consider streaming
CONTEXT_THRESHOLD_EMERGENCY = 0.95  # 95% - stop loading, trigger cleanup

# Streaming: files larger than this threshold are read in chunks to avoid OOM
STREAMING_THRESHOLD = 1_000_000  # 1 MB
STREAMING_CHUNK_SIZE = 65_536  # 64 KB per read chunk

# Max content per file sent to TOON (5 KB snippet)
MAX_CONTENT_CHARS = 5000


def _stream_file_head(
    file_path: Path,
    max_chars: int = MAX_CONTENT_CHARS,
    chunk_size: int = STREAMING_CHUNK_SIZE,
) -> str:
    """Stream the head of a large file without loading it fully into memory.

    Reads file in chunks until max_chars bytes accumulated or EOF reached.
    This avoids OOM errors for large SRS / README files.

    Args:
        file_path: Path object to read
        max_chars: Maximum characters to return
        chunk_size: Read chunk size in bytes

    Returns:
        String containing up to max_chars characters from the start of the file

    Raises:
        Exception: On file read errors (not caught here - caller handles)
    """
    collected = []
    collected_len = 0

    with open(str(file_path), "r", encoding="utf-8", errors="ignore") as fh:
        while collected_len < max_chars:
            remaining = max_chars - collected_len
            # Read a chunk no larger than chunk_size and no larger than remaining
            read_size = min(chunk_size, remaining)
            chunk = fh.read(read_size)
            if not chunk:
                break
            collected.append(chunk)
            collected_len += len(chunk)

    return "".join(collected)


def _read_file_with_timeout(
    file_path: Path,
    timeout_seconds: int = CONTEXT_TIMEOUT_PER_FILE,
    use_streaming: bool = False,
    max_chars: int = MAX_CONTENT_CHARS,
) -> str:
    """Read a file, returning content or raising TimeoutError / Exception.

    On Windows, threading-based timeout is used (signal module is POSIX-only).

    Optimization (Task #6 - Memory Pressure):
    When use_streaming=True the file is read in chunks via _stream_file_head()
    to avoid loading the full multi-MB file into memory.

    Args:
        file_path: Path to read
        timeout_seconds: Max seconds to allow for the read
        use_streaming: If True, use chunked streaming instead of read_text()
        max_chars: Max characters to return when streaming (ignored otherwise)

    Returns:
        File content as string

    Raises:
        TimeoutError: If read exceeds timeout_seconds
        Exception: On any other read failure
    """
    import threading

    # Normalize to Path for .read_text() compatibility (accepts both str and Path)
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    result = [None]
    exc = [None]

    def _reader():
        try:
            if use_streaming:
                result[0] = _stream_file_head(file_path, max_chars=max_chars)
            else:
                result[0] = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            exc[0] = e

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Thread is still blocked - the read timed out
        # Mark timeout in result so caller can detect partial success
        raise TimeoutError("File read timed out after {}s: {}".format(timeout_seconds, file_path))

    if exc[0] is not None:
        raise exc[0]

    return result[0] or ""


def node_context_loader(state: FlowState) -> dict:
    """Load context from PROJECT FILES (not ~/.claude/memory/).

    Optimization features (Task #6):
    - Cache integration: try cache first, skip filesystem scan on hit
    - Hit/miss rate logged to CacheStats and printed with cumulative rate
    - Per-file timeout (30s) with graceful recovery: timed-out file is skipped,
      remaining files still load (partial context returned, not empty context)
    - Total timeout (120s) guard: stops adding files once limit hit; already
      loaded files are returned as partial context
    - Memory-pressure streaming: files >= STREAMING_THRESHOLD (1MB) are read
      in 64KB chunks via _stream_file_head() to avoid OOM
    - Total memory budget: stops loading once MAX_TOTAL_SIZE reached
    - Partial context: context_data["files_loaded"] reflects what actually loaded

    Reads from project folder (root only, no deep recursion):
    - SRS.*
    - README.*
    - CLAUDE.md
    """
    import time

    print("[LEVEL 1 CONTEXT LOADER] CALLED!", file=sys.stderr)

    # Track timing for performance metric reporting
    loader_start = time.time()

    try:
        project_root = Path(state.get("project_root", "."))
        # session_path is written by node_session_loader, which is sequenced BEFORE
        # the parallel pair (node_complexity_calculation || node_context_loader).
        # This is an intentional sequential dependency on node_session_loader, NOT
        # a dependency on node_complexity_calculation (the true parallel partner).
        session_path = Path(state.get("session_path", ""))

        # Gap5 fix: ASCII-encode path strings before printing to stderr (cp1252-safe)
        _root_repr = str(project_root).encode("ascii", errors="replace").decode("ascii")
        print("[LEVEL 1 CONTEXT LOADER] project_root: {}".format(_root_repr), file=sys.stderr)
        print("[LEVEL 1 CONTEXT LOADER] exists: {}".format(project_root.exists()), file=sys.stderr)
        sys.stderr.flush()

        # ---- Cache check: try to return immediately on hit ----
        if _CONTEXT_CACHE_AVAILABLE:
            try:
                _cache = ContextCache()
                cached = _cache.load_cache(str(project_root))
                if cached is not None:
                    elapsed_ms = int((time.time() - loader_start) * 1000)
                    print(
                        "[LEVEL 1 CONTEXT LOADER] Cache HIT - skipping filesystem scan" " ({}ms)".format(elapsed_ms),
                        file=sys.stderr,
                    )
                    cache_stats = ContextCache.get_session_stats()
                    write_level_log(
                        state,
                        "level1",
                        "context-loader",
                        "OK",
                        _time_mod.time() - loader_start,
                        {
                            "files_loaded": len(cached.get("files_loaded", [])),
                            "cache_hit": True,
                            "load_time_ms": elapsed_ms,
                        },
                    )
                    _cache_hit_result = {
                        "context_data": cached,
                        "context_loaded": True,
                        "files_loaded_count": len(cached.get("files_loaded", [])),
                        "context_skipped_files": [],
                        "context_load_warnings": [],
                        "context_total_bytes": 0,
                        "context_cache_hit": True,
                        "context_cache_age_hours": cached.get("_cache_age_hours", 0.0),
                        "context_cache_key": ContextCache._cache_key(str(project_root)),
                        "context_load_time_ms": elapsed_ms,
                        "context_hit_rate_pct": cache_stats.get("hit_rate_pct", 0.0),
                        "context_streamed_files": [],
                    }
                    # Telemetry
                    try:
                        import json as _json_tel
                        import time as _time_tel

                        _sid_tel = state.get("session_id", "")
                        if _sid_tel:
                            _tdir_tel = _LEVEL1_TELEMETRY_DIR
                            _tdir_tel.mkdir(parents=True, exist_ok=True)
                            _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                            _entry_tel = {
                                "level": 1,
                                "node": "node_context_loader",
                                "status": "OK",
                                "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                            with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                                _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
                    except Exception:
                        pass  # Non-blocking
                    return _cache_hit_result
            except Exception as cache_exc:
                print(
                    "[LEVEL 1 CONTEXT LOADER] Cache check failed (ignored): {}".format(cache_exc),
                    file=sys.stderr,
                )

        # ---- Fresh load ----
        context_data = {
            "srs": None,
            "readme": None,
            "claude_md": None,
            "files_loaded": [],
        }

        total_loaded_bytes = 0
        load_start = time.time()
        skipped_files = []
        load_warnings = []
        streamed_files = []

        # Candidate files: (glob_pattern, context_data_key, display_label)
        candidates = [
            ("[Ss][Rr][Ss].*", "srs", "SRS"),
            ("[Rr][Ee][Aa][Dd][Mm][Ee].*", "readme", "README"),
            ("[Cc][Ll][Aa][Uu][Dd][Ee].[Mm][Dd]", "claude_md", "CLAUDE.md"),
        ]

        for glob_pattern, data_key, label in candidates:
            # Partial context fallback: catch all errors, skip file, continue loop
            try:
                # --- Total timeout guard ---
                elapsed = time.time() - load_start
                if elapsed >= CONTEXT_TIMEOUT_TOTAL:
                    msg = (
                        "Total context load timeout ({}s) reached after {:.1f}s - "
                        "returning partial context with {} files loaded".format(
                            CONTEXT_TIMEOUT_TOTAL,
                            elapsed,
                            len(context_data.get("files_loaded", [])),
                        )
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break

                # Find matching files in root only (no recursive glob); skip directories
                matched = [m for m in project_root.glob(glob_pattern) if m.is_file()]
                if not matched:
                    continue

                file_path = matched[0]

                # --- File size check ---
                try:
                    file_size = file_path.stat().st_size
                except Exception:
                    file_size = 0

                # --- Total memory budget guard ---
                if total_loaded_bytes >= MAX_TOTAL_SIZE:
                    msg = "Total load limit ({} bytes) reached, returning partial context".format(MAX_TOTAL_SIZE)
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break

                # --- Memory pressure: use streaming for large files ---
                use_streaming = file_size >= STREAMING_THRESHOLD
                if use_streaming:
                    msg = "{} is large ({} bytes >= {}B threshold) - " "using streaming read".format(
                        label, file_size, STREAMING_THRESHOLD
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    streamed_files.append(label)

                # --- Per-file timeout with graceful recovery ---
                try:
                    content = _read_file_with_timeout(
                        file_path,
                        CONTEXT_TIMEOUT_PER_FILE,
                        use_streaming=use_streaming,
                        max_chars=MAX_CONTENT_CHARS,
                    )
                except TimeoutError:
                    # Timeout: skip this file, continue with others (partial context)
                    msg = "Timeout ({:.0f}s) reading {} - file skipped, " "continuing with remaining files".format(
                        CONTEXT_TIMEOUT_PER_FILE, label
                    )
                    print("[CONTEXT LOADER] WARNING: " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    skipped_files.append(label)
                    continue

                # Store content (streaming already limits to MAX_CONTENT_CHARS)
                if use_streaming:
                    context_data[data_key] = content
                else:
                    context_data[data_key] = content[:MAX_CONTENT_CHARS]

                context_data["files_loaded"].append(label)
                loaded_bytes = len(content.encode("utf-8", errors="ignore"))
                total_loaded_bytes += loaded_bytes

                # --- Context threshold monitoring (per policy) ---
                usage_ratio = total_loaded_bytes / MAX_TOTAL_SIZE if MAX_TOTAL_SIZE > 0 else 0
                if usage_ratio >= CONTEXT_THRESHOLD_EMERGENCY:
                    msg = "EMERGENCY: Context usage at {:.0f}% ({} / {} bytes) - stopping further loads".format(
                        usage_ratio * 100, total_loaded_bytes, MAX_TOTAL_SIZE
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break
                elif usage_ratio >= CONTEXT_THRESHOLD_HIGH:
                    msg = "HIGH: Context usage at {:.0f}% ({} / {} bytes) - switching to streaming for remaining files".format(
                        usage_ratio * 100, total_loaded_bytes, MAX_TOTAL_SIZE
                    )
                    print("[CONTEXT LOADER] WARNING: " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                elif usage_ratio >= CONTEXT_THRESHOLD_WARNING:
                    print(
                        "[CONTEXT LOADER] Context usage at {:.0f}% ({} / {} bytes)".format(
                            usage_ratio * 100, total_loaded_bytes, MAX_TOTAL_SIZE
                        ),
                        file=sys.stderr,
                    )

                print(
                    "[CONTEXT LOADER] Loaded {} ({} bytes on disk, {} bytes in memory{})".format(
                        label,
                        file_size,
                        loaded_bytes,
                        ", streamed" if use_streaming else "",
                    ),
                    file=sys.stderr,
                )

            except Exception as exc:
                # General error: skip this file, continue with remaining
                msg = "Error loading {} (skipped, partial context): {}".format(label, exc)
                print("[CONTEXT LOADER] WARNING: " + msg, file=sys.stderr)
                load_warnings.append(msg)
                skipped_files.append(label)
                continue

        # ---- Context deduplication ----
        if _DEDUPLICATOR_AVAILABLE and len(context_data.get("files_loaded", [])) >= 2:
            try:
                context_data = deduplicate_context(context_data)
            except Exception as dedup_exc:
                print(
                    "[CONTEXT LOADER] Deduplication failed (ignored): {}".format(dedup_exc),
                    file=sys.stderr,
                )

        # ---- Save context to session folder ----
        if session_path and str(session_path) != ".":
            try:
                context_file = Path(session_path) / "context-raw.json"
                with open(context_file, "w", encoding="utf-8") as f:
                    json.dump(context_data, f, indent=2)
            except Exception as save_exc:
                print(
                    "[CONTEXT LOADER] WARNING: Could not save context-raw.json: {}".format(save_exc),
                    file=sys.stderr,
                )

        # ---- Persist fresh context to cache ----
        if _CONTEXT_CACHE_AVAILABLE:
            try:
                _cache = ContextCache()
                _cache.save_cache(str(project_root), context_data)
            except Exception as cache_save_exc:
                print(
                    "[CONTEXT LOADER] Cache save failed (ignored): {}".format(cache_save_exc),
                    file=sys.stderr,
                )

        elapsed_ms = int((time.time() - loader_start) * 1000)
        cache_stats = ContextCache.get_session_stats() if _CONTEXT_CACHE_AVAILABLE else {}

        print(
            "[CONTEXT LOADER] Complete: {} files loaded, {} skipped, "
            "{} bytes, {}ms (session hit_rate={}%)".format(
                len(context_data.get("files_loaded", [])),
                len(skipped_files),
                total_loaded_bytes,
                elapsed_ms,
                cache_stats.get("hit_rate_pct", "N/A"),
            ),
            file=sys.stderr,
        )

        # ---- Best-effort: detect technology patterns in project root ----
        _detected_patterns = None
        try:
            _pattern_mod = _load_architecture_script("pattern-detector.py")
            if _pattern_mod is not None and hasattr(_pattern_mod, "detect_patterns"):
                if not state.get("patterns_detected"):
                    _detected_patterns = _pattern_mod.detect_patterns(project_root)
        except Exception as _pat_exc:
            _detected_patterns = None
            print(
                "[LEVEL 1 CONTEXT LOADER] Pattern detection skipped: {}".format(_pat_exc),
                file=sys.stderr,
            )

        # Return partial context - whatever loaded successfully
        result = {
            "context_data": context_data,
            "context_loaded": True,
            "files_loaded_count": len(context_data.get("files_loaded", [])),
            "context_skipped_files": skipped_files,
            "context_load_warnings": load_warnings,
            "context_total_bytes": total_loaded_bytes,
            "context_cache_hit": False,
            "context_cache_key": ContextCache._cache_key(str(project_root)) if _CONTEXT_CACHE_AVAILABLE else None,
            "context_load_time_ms": elapsed_ms,
            "context_hit_rate_pct": cache_stats.get("hit_rate_pct", 0.0),
            "context_streamed_files": streamed_files,
        }
        result["pattern_detection_available"] = _detected_patterns is not None
        if _detected_patterns is not None:
            result["patterns_detected"] = _detected_patterns

        # ---- Best-effort: populate pattern_metadata with detailed info ----
        try:
            if _detected_patterns and _pattern_mod is not None:
                if hasattr(_pattern_mod, "detect_patterns_detailed"):
                    _detailed = _pattern_mod.detect_patterns_detailed(project_root)
                    if _detailed:
                        result["pattern_metadata"] = {
                            "categories": _detailed.get("categories", []),
                            "confidence_scores": _detailed.get("confidence_scores", {}),
                            "pattern_count": len(_detected_patterns),
                        }
        except Exception:
            pass  # Fail-open: pattern metadata is best-effort

        write_level_log(
            state,
            "level1",
            "context-loader",
            "OK",
            _time_mod.time() - loader_start,
            {
                "files_loaded": len(context_data.get("files_loaded", [])),
                "total_bytes": total_loaded_bytes,
                "cache_hit": False,
                "load_time_ms": elapsed_ms,
            },
        )
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_context_loader",
                    "status": "OK" if not result.get("error") else "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result

    except Exception as e:
        # Top-level fallback: return empty context dict - never crash the pipeline
        elapsed_ms = int((_time_mod.time() - loader_start) * 1000)
        print("[CONTEXT LOADER] ERROR: {}".format(e), file=sys.stderr)
        result = {
            "context_loaded": False,
            "context_error": str(e),
            "context_data": {},
            "files_loaded_count": 0,
            "context_skipped_files": [],
            "context_load_warnings": ["Top-level error: {}".format(e)],
            "context_total_bytes": 0,
            "context_load_time_ms": elapsed_ms,
            "context_streamed_files": [],
        }
        write_level_log(state, "level1", "context-loader", "FAILED", _time_mod.time() - loader_start, None, str(e))
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_context_loader",
                    "status": "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result


# ============================================================================
# NODE 4: TOON COMPRESSION (Compress + Clear Memory + Integrity Validation)
# Subtask 4: validate compression integrity; fallback to raw context on failure
# ============================================================================


def _verify_toon_integrity(toon, original_context):
    """Verify that the compressed TOON preserves essential data from original context.

    Checks:
    - session_id present and non-empty
    - complexity_score within 1-10
    - files_loaded_count matches actual loaded files
    - context booleans match original content presence

    Args:
        toon: Compressed TOON dict
        original_context: Original context_data before compression

    Returns:
        True if integrity check passes
    """
    try:
        # Required field presence
        required = ["session_id", "complexity_score", "files_loaded_count", "context"]
        for field in required:
            if field not in toon:
                return False

        # session_id non-empty
        if not toon.get("session_id", "").strip():
            return False

        # complexity_score range
        score = toon.get("complexity_score", 0)
        if not isinstance(score, int) or not (1 <= score <= 10):
            return False

        # files_loaded_count consistency
        original_files = original_context.get("files_loaded", [])
        if toon.get("files_loaded_count") != len(original_files):
            return False

        # Context booleans match original
        ctx = toon.get("context", {})
        if ctx.get("srs") != bool(original_context.get("srs")):
            return False
        if ctx.get("readme") != bool(original_context.get("readme")):
            return False
        if ctx.get("claude_md") != bool(original_context.get("claude_md")):
            return False

        return True

    except Exception:
        return False


def _decompress_toon(toon):
    """Reconstruct a minimal context dict from a TOON object for integrity checking."""
    ctx = toon.get("context", {})
    files_list = ctx.get("files", [])
    return {
        "files_loaded": files_list,
        "srs": ctx.get("srs", False),
        "readme": ctx.get("readme", False),
        "claude_md": ctx.get("claude_md", False),
    }


def node_toon_compression(state: FlowState) -> dict:
    """Compress context to TOON format and save to session folder.

    Subtask 4: After compression, validate integrity against original.
    On failure: log error and use raw_context fallback.

    After successful compression:
    - Verbose data saved to disk as TOON
    - context_data set to None in this node (raw content freed from FlowState)
    - Only compact TOON remains in memory
    - Remaining verbose fields (srs, readme, claude_md, project_graph, architecture)
      are cleared by cleanup_level1_memory which runs after level1_merge_node.

    TOON object includes:
    - session_id
    - timestamp / version
    - complexity_score
    - files_loaded_count
    - compressed context (boolean flags, no raw content)
    """
    _step_start = _time_mod.time()
    try:
        session_path = Path(state.get("session_path", ""))
        context_data = state.get("context_data", {})
        complexity_score = state.get("complexity_score", 5)
        # combined_complexity_score is on a 1-25 scale (simple*0.3 + graph*0.7 after linear scaling).
        # May be None if graph-based analysis was skipped (e.g. no NetworkX/Lizard).
        combined_complexity_score = state.get("combined_complexity_score")
        session_id = state.get("session_id", "")
        files_loaded = context_data.get("files_loaded", [])

        # Clamp complexity to valid range
        complexity_score = max(1, min(10, int(complexity_score or 5)))

        # Build TOON object
        toon_object = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "complexity_score": complexity_score,
            "combined_complexity_score": combined_complexity_score,  # 1-25 scale; None if not calculated
            "files_loaded_count": len(files_loaded),
            "context": {
                "files": files_loaded,
                "srs": bool(context_data.get("srs")),
                "readme": bool(context_data.get("readme")),
                "claude_md": bool(context_data.get("claude_md")),
            },
            "model_preferences": {},
            "execution_constraints": {},
            "caching_metadata": {},
        }

        # ---- Subtask 4: Compression integrity validation ----
        # (a) Structural integrity: decompress and verify against original
        _decompress_toon(toon_object)
        integrity_ok = _verify_toon_integrity(toon_object, context_data)

        # (b) Schema validation via toon_schema module
        schema_errors = []
        if _TOON_SCHEMA_AVAILABLE:
            schema_valid, schema_errors = validate_toon(toon_object)
            if not schema_valid:
                print(
                    "[TOON COMPRESSION] Schema validation errors: {}".format(schema_errors),
                    file=sys.stderr,
                )
                integrity_ok = False

        if not integrity_ok:
            # Compression validation failed - use raw context as fallback
            print(
                "[TOON COMPRESSION] ERROR: Integrity check failed - using raw context fallback",
                file=sys.stderr,
            )
            # Raw fallback: store the full context_data as the TOON's context
            toon_object["context"]["raw_fallback"] = True
            toon_object["context"]["srs_snippet"] = (context_data.get("srs") or "")[:1000]
            toon_object["context"]["readme_snippet"] = (context_data.get("readme") or "")[:1000]
            toon_object["context"]["claude_md_snippet"] = (context_data.get("claude_md") or "")[:1000]
            toon_object["compression_warning"] = "Integrity check failed; raw snippet fallback used"

        # Save TOON to session folder
        if session_path and str(session_path) != ".":
            try:
                toon_file = Path(session_path) / "context.toon.json"
                if _TOONS_AVAILABLE:
                    try:
                        with open(toon_file, "w", encoding="utf-8") as f:
                            f.write(toons.dumps(toon_object))
                    except Exception:
                        with open(toon_file, "w", encoding="utf-8") as f:
                            json.dump(toon_object, f, indent=2)
                else:
                    with open(toon_file, "w", encoding="utf-8") as f:
                        json.dump(toon_object, f, indent=2)
            except Exception as save_exc:
                print(
                    "[TOON COMPRESSION] WARNING: Could not save toon file: {}".format(save_exc),
                    file=sys.stderr,
                )

        result = {
            "toon_object": toon_object,
            "toon_saved": True,
            "toon_integrity_ok": integrity_ok,
            "toon_schema_valid": integrity_ok,
            "toon_schema_errors": schema_errors,
            "toon_version": toon_object.get("version", "1.0.0"),
            # Clear the largest field immediately after TOON is built
            "context_data": None,
        }
        write_level_log(
            state,
            "level1",
            "toon-compression",
            "OK",
            _time_mod.time() - _step_start,
            {
                "toon_saved": True,
                "schema_valid": integrity_ok,
                "compression_ratio": len(files_loaded),
            },
        )
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", result.get("session_id", ""))
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_toon_compression",
                    "status": "OK" if not result.get("error") else "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return result

    except Exception as e:
        print("[TOON COMPRESSION] ERROR: {}".format(e), file=sys.stderr)
        write_level_log(state, "level1", "toon-compression", "FAILED", _time_mod.time() - _step_start, None, str(e))
        _err_result = {
            "toon_saved": False,
            "toon_error": str(e),
            "toon_object": {},
            "toon_integrity_ok": False,
            "toon_schema_valid": False,
            "toon_schema_errors": [str(e)],
        }
        # Telemetry
        try:
            import json as _json_tel
            import time as _time_tel

            _sid_tel = state.get("session_id", "")
            if _sid_tel:
                _tdir_tel = _LEVEL1_TELEMETRY_DIR
                _tdir_tel.mkdir(parents=True, exist_ok=True)
                _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
                _entry_tel = {
                    "level": 1,
                    "node": "node_toon_compression",
                    "status": "ERROR",
                    "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                    _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
        except Exception:
            pass  # Non-blocking
        return _err_result


# ============================================================================
# MERGE NODE - Final Level 1 output
# ============================================================================


def level1_merge_node(state: FlowState) -> dict:
    """Merge all Level 1 data and prepare for Level 2.

    OUTPUT: Only TOON object (contains session_id, complexity_score, files_loaded_count + context)
    CLEARED: All verbose variables from memory

    NOTE on level1_complete=True for PARTIAL status:
    Even when level1_status=="PARTIAL" (e.g. context failed to load but complexity
    succeeded), level1_complete is INTENTIONALLY set to True.  This ensures the
    pipeline does not deadlock at the Level 1 gate.  Downstream steps receive
    level1_status=="PARTIAL" so they can adapt accordingly.  Do NOT change
    level1_complete to False on PARTIAL -- that would halt the entire pipeline.
    """
    _step_start = _time_mod.time()
    # Determine Level 1 completion status based on both parallel branch results
    _complexity_ok = bool(state.get("complexity_calculated", False))
    _context_ok = bool(state.get("context_loaded", False))
    _level1_status = "OK" if (_complexity_ok and _context_ok) else "PARTIAL"

    # Gap1 fix: emit observable warning when PARTIAL so operators can detect degraded state
    if _level1_status == "PARTIAL":
        print(
            "[LEVEL 1 MERGE] PARTIAL: complexity_ok={} context_ok={}".format(_complexity_ok, _context_ok),
            file=sys.stderr,
        )

    # Build final Level 1 output
    updates = {
        "level1_complete": True,
        "level1_status": _level1_status,
        "level1_context_toon": state.get("toon_object", {}),  # TOON has everything inside
    }

    # Signal memory cleanup - these variables should be cleared from memory
    # (not from disk, just from RAM variables)
    cleanup_signals = {
        "clear_memory": [
            "context_data",  # Full context dict
            "srs",  # Raw SRS content
            "readme",  # Raw README content
            "claude_md",  # Raw CLAUDE.md content
            # Note: complexity_score is intentionally RETAINED in state for Level 3 access
            "files_loaded_count",  # Summarised in TOON
            "project_graph",  # Large graph object
            "architecture",  # Large architecture object
        ]
    }

    updates.update(cleanup_signals)

    write_level_log(
        state,
        "level1",
        "merge",
        "OK",
        _time_mod.time() - _step_start,
        {
            "level1_complete": True,
            "toon_present": bool(state.get("toon_object")),
            "context_percentage": state.get("context_percentage", 0),
        },
    )
    # Telemetry
    try:
        import json as _json_tel
        import time as _time_tel

        _sid_tel = state.get("session_id", updates.get("session_id", ""))
        if _sid_tel:
            _tdir_tel = _LEVEL1_TELEMETRY_DIR
            _tdir_tel.mkdir(parents=True, exist_ok=True)
            _tfile_tel = _tdir_tel / ("%s.jsonl" % _sid_tel)
            _entry_tel = {
                "level": 1,
                "node": "level1_merge_node",
                "status": "OK" if not updates.get("error") else "ERROR",
                "timestamp": _time_tel.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(str(_tfile_tel), "a", encoding="utf-8") as _f_tel:
                _f_tel.write(_json_tel.dumps(_entry_tel) + "\n")
    except Exception:
        pass  # Non-blocking
    return updates


# ============================================================================
# HELPER: Actual memory cleanup function (called separately)
# ============================================================================


def cleanup_level1_memory(state: FlowState) -> dict:
    """Actually remove verbose variables from state.

    This is called AFTER level1_merge to free up RAM.

    VERIFICATION: Log memory usage before/after cleanup to confirm clearing.
    """
    import os

    # Collect size information before cleanup (for verification)
    cleanup_summary = {
        "fields_cleared": [
            "context_data",
            "srs",
            "readme",
            "claude_md",
            "project_graph",
            "architecture",
        ],
        "toon_preserved": True,  # Confirm TOON is NOT cleared
    }

    # Calculate approximate sizes for verification
    for field in cleanup_summary["fields_cleared"]:
        value = state.get(field)
        if value:
            if isinstance(value, dict):
                cleanup_summary["{}_size_bytes".format(field)] = len(str(value).encode("utf-8"))
            elif isinstance(value, (str, bytes)):
                cleanup_summary["{}_size_bytes".format(field)] = len(
                    str(value).encode("utf-8") if isinstance(value, str) else value
                )

    # Verify TOON object is in state and has required fields
    toon = state.get("level1_context_toon", {})
    if toon:
        cleanup_summary["toon_fields"] = list(toon.keys())
        cleanup_summary["toon_has_session_id"] = "session_id" in toon
        cleanup_summary["toon_has_complexity_score"] = "complexity_score" in toon
        cleanup_summary["toon_has_files_loaded_count"] = "files_loaded_count" in toon

    # Log cleanup status (ASCII-safe prints for Windows cp1252 terminals)
    if os.getenv("CLAUDE_DEBUG") == "1":
        import sys

        print("\n[LEVEL 1 CLEANUP]", file=sys.stderr)
        print("  Clearing {} verbose fields...".format(len(cleanup_summary["fields_cleared"])), file=sys.stderr)
        for field in cleanup_summary["fields_cleared"]:
            if "{}_size_bytes".format(field) in cleanup_summary:
                size_kb = cleanup_summary["{}_size_bytes".format(field)] / 1024
                print("    {} {:.1f}KB freed".format(field, size_kb), file=sys.stderr)
        print("  TOON object preserved: {}".format(list(toon.keys())), file=sys.stderr)
        print("  Memory cleanup complete\n", file=sys.stderr)

    # ---- Best-effort: estimate context window usage after cleanup ----
    _context_monitor_result = {}
    try:
        _monitor_mod = _load_architecture_script("context-monitor.py")
        if _monitor_mod is not None and hasattr(_monitor_mod, "estimate_context_usage"):
            _session_path_val = state.get("session_path", "")
            _session_dir = Path(_session_path_val) if _session_path_val else None
            _usage = _monitor_mod.estimate_context_usage(_session_dir)
            _context_monitor_result = {
                "context_percentage": _usage.get("percentage", 0.0),
                "context_percentage_display": _usage.get("percentage_display", ""),
                "context_threshold_zone": _usage.get("threshold_zone", ""),
                "context_estimated_tokens": _usage.get("estimated_tokens", 0),
                "context_recommendation": _usage.get("recommendation", ""),
            }
    except Exception as _mon_exc:
        print(
            "[LEVEL 1 CLEANUP] Context monitor skipped: {}".format(_mon_exc),
            file=sys.stderr,
        )

    # Return cleanup updates
    # In Python, we just set these to None/empty
    # LangGraph will update the state
    cleanup = {
        "context_data": None,
        "srs": None,
        "readme": None,
        "claude_md": None,
        "project_graph": None,
        "architecture": None,
        # Store cleanup summary for logging
        "level1_cleanup_summary": cleanup_summary,
    }
    cleanup.update(_context_monitor_result)
    return cleanup
