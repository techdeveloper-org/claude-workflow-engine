"""Level 1 Sync - Context Loader node.

Canonical location: langgraph_engine/level1_sync/context_loader.py
Windows-safe: ASCII only, no Unicode characters.
"""

import json
import sys
from pathlib import Path

try:
    from ..flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

from .helpers import (
    _CONTEXT_CACHE_AVAILABLE,
    _DEDUPLICATOR_AVAILABLE,
    _LEVEL1_TELEMETRY_DIR,
    _load_architecture_script,
    _time_mod,
    write_level_log,
)

# Conditional imports for cache and dedup
try:
    from .helpers import ContextCache
except ImportError:
    ContextCache = None  # type: ignore[assignment,misc]

try:
    from .helpers import deduplicate_context
except ImportError:
    deduplicate_context = None  # type: ignore[assignment]

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
    file_path,
    max_chars=MAX_CONTENT_CHARS,
    chunk_size=STREAMING_CHUNK_SIZE,
):
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
    file_path,
    timeout_seconds=CONTEXT_TIMEOUT_PER_FILE,
    use_streaming=False,
    max_chars=MAX_CONTENT_CHARS,
):
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


def node_context_loader(state):
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
        if _CONTEXT_CACHE_AVAILABLE and ContextCache is not None:
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
                    msg = "{} is large ({} bytes >= {}B threshold) - using streaming read".format(
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
                    msg = "Timeout ({:.0f}s) reading {} - file skipped, continuing with remaining files".format(
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
                    msg = (
                        "HIGH: Context usage at {:.0f}% ({} / {} bytes)"
                        " - switching to streaming for remaining files".format(
                            usage_ratio * 100, total_loaded_bytes, MAX_TOTAL_SIZE
                        )
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
        if (
            _DEDUPLICATOR_AVAILABLE
            and deduplicate_context is not None
            and len(context_data.get("files_loaded", [])) >= 2
        ):
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
        if _CONTEXT_CACHE_AVAILABLE and ContextCache is not None:
            try:
                _cache = ContextCache()
                _cache.save_cache(str(project_root), context_data)
            except Exception as cache_save_exc:
                print(
                    "[CONTEXT LOADER] Cache save failed (ignored): {}".format(cache_save_exc),
                    file=sys.stderr,
                )

        elapsed_ms = int((time.time() - loader_start) * 1000)
        cache_stats = (
            ContextCache.get_session_stats() if (_CONTEXT_CACHE_AVAILABLE and ContextCache is not None) else {}
        )

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
            "context_cache_key": (
                ContextCache._cache_key(str(project_root))
                if (_CONTEXT_CACHE_AVAILABLE and ContextCache is not None)
                else None
            ),
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
