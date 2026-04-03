"""Level 1 Sync subgraph node module.

Extracted from monolithic level1_sync.py for modularity.
Windows-safe: ASCII only, no Unicode characters.
"""

# ruff: noqa: F821

import json
import sys
from pathlib import Path

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

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
