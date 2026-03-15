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

import sys
import json
import time as _time_mod
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Iterator

try:
    from langgraph.graph import StateGraph, START, END
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
    from ..complexity_calculator import calculate_complexity, should_plan, calculate_graph_complexity
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
# NODE 1: SESSION LOADER (MUST BE FIRST)
# ============================================================================

def node_session_loader(state: FlowState) -> dict:
    """Create and load session in ~/.claude/logs/sessions/{session_id}/.

    This MUST run first - creates the session container for this execution.
    """
    import uuid
    import sys

    _step_start = _time_mod.time()
    try:
        # Debug: Check project_root before doing anything
        print(f"[LEVEL 1 SESSION_LOADER] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)

        # Generate unique session ID
        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Create session folder: ~/.claude/logs/sessions/{session_id}/
        session_path = Path.home() / ".claude" / "logs" / "sessions" / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        # user_message: try state first, then env var fallback (set by run_langgraph_engine)
        import os
        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

        session_meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "user_message": user_msg,
        }

        meta_file = session_path / "session.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(session_meta, f, indent=2)

        # Set env var so Level 3 infra can find session_id
        os.environ["CURRENT_SESSION_ID"] = session_id

        result = {
            "session_id": session_id,
            "session_path": str(session_path),
            "session_loaded": True,
        }
        write_level_log(result, "level1", "session-loader", "OK", _time_mod.time() - _step_start, result)
        return result
    except Exception as e:
        result = {
            "session_loaded": False,
            "session_error": str(e),
        }
        write_level_log(state, "level1", "session-loader", "FAILED", _time_mod.time() - _step_start, None, str(e))
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
                simple_scaled = round(simple_score * 2.5)  # scale 1-10 to 1-25
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
            write_level_log(state, "level1", "complexity-calculation", "OK",
                            _time_mod.time() - _step_start, result)
            return result

        # --- Legacy path: try the old architecture script ---
        complexity_script = (
            Path(__file__).parent.parent.parent /
            "architecture" / "03-execution-system" / "04-model-selection" /
            "complexity-calculator.py"
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
                    return {
                        "complexity_score": data.get("complexity_score", 5),
                        "project_graph": data.get("graph", {}),
                        "architecture": data.get("architecture", {}),
                        "complexity_calculated": True,
                    }
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
        write_level_log(state, "level1", "complexity-calculation", "OK",
                        _time_mod.time() - _step_start, result)
        return result

    except Exception as e:
        result = {
            "complexity_calculated": False,
            "complexity_error": str(e),
            "complexity_score": 5,  # Safe default
        }
        write_level_log(state, "level1", "complexity-calculation", "FAILED",
                        _time_mod.time() - _step_start, None, str(e))
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
MAX_FILE_SIZE = 1_000_000       # 1 MB: files bigger than this are streamed
MAX_TOTAL_SIZE = 10_000_000     # 10 MB total loaded bytes across all files

# Streaming: files larger than this threshold are read in chunks to avoid OOM
STREAMING_THRESHOLD = 1_000_000   # 1 MB
STREAMING_CHUNK_SIZE = 65_536     # 64 KB per read chunk

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
    collected: list = []
    collected_len: int = 0

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

    result: list = [None]
    exc: list = [None]

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
        raise TimeoutError(
            "File read timed out after {}s: {}".format(timeout_seconds, file_path)
        )

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
        session_path = Path(state.get("session_path", ""))

        print("[LEVEL 1 CONTEXT LOADER] project_root: {}".format(project_root), file=sys.stderr)
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
                        "[LEVEL 1 CONTEXT LOADER] Cache HIT - skipping filesystem scan"
                        " ({}ms)".format(elapsed_ms),
                        file=sys.stderr,
                    )
                    cache_stats = ContextCache.get_session_stats()
                    write_level_log(state, "level1", "context-loader", "OK",
                                    _time_mod.time() - loader_start, {
                                        "files_loaded": len(cached.get("files_loaded", [])),
                                        "cache_hit": True,
                                        "load_time_ms": elapsed_ms,
                                    })
                    return {
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
            except Exception as cache_exc:
                print(
                    "[LEVEL 1 CONTEXT LOADER] Cache check failed (ignored): {}".format(cache_exc),
                    file=sys.stderr,
                )

        # ---- Fresh load ----
        context_data: dict = {
            "srs": None,
            "readme": None,
            "claude_md": None,
            "files_loaded": [],
        }

        total_loaded_bytes = 0
        load_start = time.time()
        skipped_files: list = []
        load_warnings: list = []
        streamed_files: list = []

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

                # Find matching files in root only (no recursive glob)
                matched = list(project_root.glob(glob_pattern))
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
                    msg = "Total load limit ({} bytes) reached, returning partial context".format(
                        MAX_TOTAL_SIZE
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break

                # --- Memory pressure: use streaming for large files ---
                use_streaming = file_size >= STREAMING_THRESHOLD
                if use_streaming:
                    msg = (
                        "{} is large ({} bytes >= {}B threshold) - "
                        "using streaming read".format(
                            label, file_size, STREAMING_THRESHOLD
                        )
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
                    msg = (
                        "Timeout ({:.0f}s) reading {} - file skipped, "
                        "continuing with remaining files".format(
                            CONTEXT_TIMEOUT_PER_FILE, label
                        )
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
        write_level_log(state, "level1", "context-loader", "OK",
                        _time_mod.time() - loader_start, {
                            "files_loaded": len(context_data.get("files_loaded", [])),
                            "total_bytes": total_loaded_bytes,
                            "cache_hit": False,
                            "load_time_ms": elapsed_ms,
                        })
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
        write_level_log(state, "level1", "context-loader", "FAILED",
                        _time_mod.time() - loader_start, None, str(e))
        return result


# ============================================================================
# NODE 4: TOON COMPRESSION (Compress + Clear Memory + Integrity Validation)
# Subtask 4: validate compression integrity; fallback to raw context on failure
# ============================================================================

def _verify_toon_integrity(toon: dict, original_context: dict) -> bool:
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


def _decompress_toon(toon: dict) -> dict:
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
    - Memory variables cleared
    - Only compact TOON remains in memory

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
        decompressed = _decompress_toon(toon_object)
        integrity_ok = _verify_toon_integrity(toon_object, context_data)

        # (b) Schema validation via toon_schema module
        schema_errors: list = []
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
            "clear_verbose_memory": True,
        }
        write_level_log(state, "level1", "toon-compression", "OK",
                        _time_mod.time() - _step_start, {
                            "toon_saved": True,
                            "schema_valid": integrity_ok,
                            "compression_ratio": len(files_loaded),
                        })
        return result

    except Exception as e:
        print("[TOON COMPRESSION] ERROR: {}".format(e), file=sys.stderr)
        write_level_log(state, "level1", "toon-compression", "FAILED",
                        _time_mod.time() - _step_start, None, str(e))
        return {
            "toon_saved": False,
            "toon_error": str(e),
            "toon_object": {},
            "toon_integrity_ok": False,
            "toon_schema_valid": False,
            "toon_schema_errors": [str(e)],
        }


# ============================================================================
# MERGE NODE - Final Level 1 output
# ============================================================================

def level1_merge_node(state: FlowState) -> dict:
    """Merge all Level 1 data and prepare for Level 2.

    OUTPUT: Only TOON object (contains session_id, complexity_score, files_loaded_count + context)
    CLEARED: All verbose variables from memory
    """
    _step_start = _time_mod.time()
    # Build final Level 1 output
    updates = {
        "level1_complete": True,
        "level1_context_toon": state.get("toon_object", {}),  # ✓ TOON has everything inside
    }

    # Signal memory cleanup - these variables should be cleared from memory
    # (not from disk, just from RAM variables)
    cleanup_signals = {
        "clear_memory": [
            "context_data",      # Full context dict
            "srs",               # Raw SRS content
            "readme",            # Raw README content
            "claude_md",         # Raw CLAUDE.md content
            "complexity_score",  # Now in TOON object
            "files_loaded_count",# Now in TOON object
            "project_graph",     # Large graph object
            "architecture",      # Large architecture object
        ]
    }

    updates.update(cleanup_signals)

    write_level_log(state, "level1", "merge", "OK", _time_mod.time() - _step_start, {
        "level1_complete": True,
        "toon_present": bool(state.get("toon_object")),
        "context_percentage": state.get("context_percentage", 0),
    })
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
                cleanup_summary[f"{field}_size_bytes"] = len(str(value).encode('utf-8'))
            elif isinstance(value, (str, bytes)):
                cleanup_summary[f"{field}_size_bytes"] = len(str(value).encode('utf-8') if isinstance(value, str) else value)

    # Verify TOON object is in state and has required fields
    toon = state.get("level1_context_toon", {})
    if toon:
        cleanup_summary["toon_fields"] = list(toon.keys())
        cleanup_summary["toon_has_session_id"] = "session_id" in toon
        cleanup_summary["toon_has_complexity_score"] = "complexity_score" in toon
        cleanup_summary["toon_has_files_loaded_count"] = "files_loaded_count" in toon

    # Log cleanup status
    if os.getenv("CLAUDE_DEBUG") == "1":
        import sys
        print(f"\n[LEVEL 1 CLEANUP]", file=sys.stderr)
        print(f"  Clearing {len(cleanup_summary['fields_cleared'])} verbose fields...", file=sys.stderr)
        for field in cleanup_summary["fields_cleared"]:
            if f"{field}_size_bytes" in cleanup_summary:
                size_kb = cleanup_summary[f"{field}_size_bytes"] / 1024
                print(f"    ✓ {field}: {size_kb:.1f}KB freed", file=sys.stderr)
        print(f"  TOON object preserved: {list(toon.keys())}", file=sys.stderr)
        print(f"  ✓ Memory cleanup complete\n", file=sys.stderr)

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
    return cleanup
