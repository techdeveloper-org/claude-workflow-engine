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
