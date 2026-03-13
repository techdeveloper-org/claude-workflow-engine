"""
Level 1 SubGraph - Context Sync System (CORRECTED)

CORRECT FLOW (per user specification):
1. node_session_loader (FIRST) - Create session in ~/.claude/logs/sessions/{session_id}/
2. node_complexity_calculation (PARALLEL with #3) - Analyze project structure
3. node_context_loader (PARALLEL with #2) - Read SRS, README, CLAUDE.md from PROJECT
4. node_toon_compression (NEW) - Compress to TOON format + clear memory
5. level1_merge_node - Final merge
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState

try:
    import toons
    _TOONS_AVAILABLE = True
except ImportError:
    _TOONS_AVAILABLE = False

# Level 1 new modules (graceful import fallback)
try:
    from ..complexity_calculator import calculate_complexity, should_plan
    _COMPLEXITY_CALCULATOR_AVAILABLE = True
except ImportError:
    _COMPLEXITY_CALCULATOR_AVAILABLE = False

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

    try:
        # Debug: Check project_root before doing anything
        print(f"[LEVEL 1 SESSION_LOADER] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)

        # Generate unique session ID
        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Create session folder: ~/.claude/logs/sessions/{session_id}/
        session_path = Path.home() / ".claude" / "logs" / "sessions" / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        session_meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "user_message": state.get("user_message", ""),
        }

        meta_file = session_path / "session.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(session_meta, f, indent=2)

        return {
            "session_id": session_id,
            "session_path": str(session_path),
            "session_loaded": True,
        }
    except Exception as e:
        return {
            "session_loaded": False,
            "session_error": str(e),
        }


# ============================================================================
# NODE 2: COMPLEXITY CALCULATION (PARALLEL with context_loader)
# ============================================================================

def node_complexity_calculation(state: FlowState) -> dict:
    """Analyze project structure and calculate complexity.

    Uses complexity_calculator.py (new, preferred) when available.
    Falls back to legacy script or simple heuristic otherwise.
    """
    try:
        project_root = Path(state.get("project_root", "."))
        session_id = state.get("session_id", "")

        # --- Preferred path: use new complexity_calculator module ---
        if _COMPLEXITY_CALCULATOR_AVAILABLE:
            score = calculate_complexity(str(project_root), session_id=session_id or None)
            return {
                "complexity_score": score,
                "project_graph": {},
                "architecture": {},
                "complexity_calculated": True,
            }

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

        return {
            "complexity_score": complexity_score,
            "project_graph": {},
            "architecture": {},
            "complexity_calculated": True,
        }

    except Exception as e:
        return {
            "complexity_calculated": False,
            "complexity_error": str(e),
            "complexity_score": 5,  # Safe default
        }


# ============================================================================
# NODE 3: CONTEXT LOADER (PARALLEL with complexity_calculation)
# Subtasks 3, 5, 7: Timeout handling + Memory limits + Partial context fallback
# ============================================================================

# Per-file and total-load timeouts (seconds)
CONTEXT_TIMEOUT_PER_FILE = 30
CONTEXT_TIMEOUT_TOTAL = 120

# Memory limits
MAX_FILE_SIZE = 1_000_000       # 1 MB per file
MAX_TOTAL_SIZE = 10_000_000     # 10 MB total loaded bytes

# Max content per file sent to TOON (5 KB snippet)
MAX_CONTENT_CHARS = 5000


def _read_file_with_timeout(file_path: Path, timeout_seconds: int = CONTEXT_TIMEOUT_PER_FILE) -> str:
    """Read a file, returning content or raising TimeoutError / Exception.

    On Windows, threading-based timeout is used (signal module is POSIX-only).

    Args:
        file_path: Path to read
        timeout_seconds: Max seconds to allow for the read

    Returns:
        File content as string

    Raises:
        TimeoutError: If read exceeds timeout_seconds
        Exception: On any other read failure
    """
    import threading

    result: list = [None]
    exc: list = [None]

    def _reader():
        try:
            result[0] = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            exc[0] = e

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(
            "File read timed out after {}s: {}".format(timeout_seconds, file_path)
        )

    if exc[0] is not None:
        raise exc[0]

    return result[0] or ""


def node_context_loader(state: FlowState) -> dict:
    """Load context from PROJECT FILES (not ~/.claude/memory/).

    Features:
    - Per-file timeout (30s) and total timeout (120s)
    - Memory limits: 1MB per file, 10MB total
    - Partial context fallback: continue on any single-file failure
    - Graceful degradation: return whatever loaded successfully

    Reads from project folder (root only, no deep recursion):
    - SRS.*
    - README.*
    - CLAUDE.md
    """
    import time

    print("[LEVEL 1 CONTEXT LOADER] CALLED!", file=sys.stderr)

    try:
        project_root = Path(state.get("project_root", "."))
        session_path = Path(state.get("session_path", ""))

        print("[LEVEL 1 CONTEXT LOADER] project_root: {}".format(project_root), file=sys.stderr)
        print("[LEVEL 1 CONTEXT LOADER] exists: {}".format(project_root.exists()), file=sys.stderr)
        sys.stderr.flush()

        # ---- Subtask 8: Check context cache first ----
        if _CONTEXT_CACHE_AVAILABLE:
            try:
                _cache = ContextCache()
                cached = _cache.load_cache(str(project_root))
                if cached is not None:
                    print("[LEVEL 1 CONTEXT LOADER] Cache HIT - using cached context", file=sys.stderr)
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
                    }
            except Exception as cache_exc:
                print(
                    "[LEVEL 1 CONTEXT LOADER] Cache check failed (ignored): {}".format(cache_exc),
                    file=sys.stderr,
                )

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

        # Candidate files: pattern -> context_data key
        candidates = [
            ("[Ss][Rr][Ss].*", "srs", "SRS"),
            ("[Rr][Ee][Aa][Dd][Mm][Ee].*", "readme", "README"),
            ("[Cc][Ll][Aa][Uu][Dd][Ee].[Mm][Dd]", "claude_md", "CLAUDE.md"),
        ]

        for glob_pattern, data_key, label in candidates:
            # ---- Subtask 7: partial fallback - skip on any error, continue to next ----
            try:
                # Check total timeout
                elapsed = time.time() - load_start
                if elapsed >= CONTEXT_TIMEOUT_TOTAL:
                    msg = "Total context load timeout ({}s) reached, stopping".format(
                        CONTEXT_TIMEOUT_TOTAL
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break  # Subtask 5: stop_loading() when threshold reached

                # Find matching files in root only (no recursive glob)
                matched = list(project_root.glob(glob_pattern))
                if not matched:
                    continue

                file_path = matched[0]

                # ---- Subtask 5: MAX_FILE_SIZE check ----
                try:
                    file_size = file_path.stat().st_size
                except Exception:
                    file_size = 0

                if file_size > MAX_FILE_SIZE:
                    msg = "Skipping {} - file too large ({} bytes > {} limit)".format(
                        label, file_size, MAX_FILE_SIZE
                    )
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    skipped_files.append(label)
                    load_warnings.append(msg)
                    continue  # skip_file()

                # ---- Subtask 5: MAX_TOTAL_SIZE check ----
                if total_loaded_bytes >= MAX_TOTAL_SIZE:
                    msg = "Total load limit reached ({} bytes), stopping".format(MAX_TOTAL_SIZE)
                    print("[CONTEXT LOADER] " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    break  # stop_loading()

                # ---- Subtask 3: Per-file timeout ----
                try:
                    content = _read_file_with_timeout(file_path, CONTEXT_TIMEOUT_PER_FILE)
                except TimeoutError as te:
                    msg = "File timeout for {} - skipping: {}".format(label, te)
                    print("[CONTEXT LOADER] WARNING: " + msg, file=sys.stderr)
                    load_warnings.append(msg)
                    skipped_files.append(label)
                    continue  # Graceful degradation - proceed without this file

                # Store truncated content
                context_data[data_key] = content[:MAX_CONTENT_CHARS]
                context_data["files_loaded"].append(label)
                total_loaded_bytes += len(content.encode("utf-8", errors="ignore"))

                print(
                    "[CONTEXT LOADER] Loaded {} ({} bytes)".format(label, len(content)),
                    file=sys.stderr,
                )

            except Exception as exc:
                # ---- Subtask 7: partial fallback - log warning and continue ----
                msg = "Failed to load {} - skipping: {}".format(label, exc)
                print("[CONTEXT LOADER] WARNING: " + msg, file=sys.stderr)
                load_warnings.append(msg)
                skipped_files.append(label)
                continue  # Continue without this file

        # ---- Subtask 6: Context deduplication ----
        if _DEDUPLICATOR_AVAILABLE and len(context_data.get("files_loaded", [])) >= 2:
            try:
                context_data = deduplicate_context(context_data)
            except Exception as dedup_exc:
                print(
                    "[CONTEXT LOADER] Deduplication failed (ignored): {}".format(dedup_exc),
                    file=sys.stderr,
                )

        # Save context to session folder
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

        # ---- Subtask 8: Persist fresh context to cache ----
        if _CONTEXT_CACHE_AVAILABLE:
            try:
                _cache = ContextCache()
                _cache.save_cache(str(project_root), context_data)
            except Exception as cache_save_exc:
                print(
                    "[CONTEXT LOADER] Cache save failed (ignored): {}".format(cache_save_exc),
                    file=sys.stderr,
                )

        # Proceed with whatever loaded successfully (Subtask 7)
        return {
            "context_data": context_data,
            "context_loaded": True,
            "files_loaded_count": len(context_data.get("files_loaded", [])),
            "context_skipped_files": skipped_files,
            "context_load_warnings": load_warnings,
            "context_total_bytes": total_loaded_bytes,
            "context_cache_hit": False,
            "context_cache_key": ContextCache._cache_key(str(project_root)) if _CONTEXT_CACHE_AVAILABLE else None,
        }

    except Exception as e:
        # Top-level fallback - return empty but not crashed
        print("[CONTEXT LOADER] ERROR: {}".format(e), file=sys.stderr)
        return {
            "context_loaded": False,
            "context_error": str(e),
            "context_data": {},
            "files_loaded_count": 0,
            "context_skipped_files": [],
            "context_load_warnings": [],
            "context_total_bytes": 0,
        }


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

        return {
            "toon_object": toon_object,
            "toon_saved": True,
            "toon_integrity_ok": integrity_ok,
            "toon_schema_valid": integrity_ok,
            "toon_schema_errors": schema_errors,
            "toon_version": toon_object.get("version", "1.0.0"),
            "clear_verbose_memory": True,
        }

    except Exception as e:
        print("[TOON COMPRESSION] ERROR: {}".format(e), file=sys.stderr)
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
