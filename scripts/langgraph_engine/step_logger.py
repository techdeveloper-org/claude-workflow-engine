"""
Shared Step Logger - Per-level JSON logging for all pipeline levels.

Writes per-step JSON log files to {session_dir}/{level}-logs/{step_name}.json
so every level has a complete audit trail.

Used by: Level -1, Level 1, Level 2, Level 3
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


def write_level_log(
    state: dict,
    level: str,
    step_name: str,
    status: str,
    duration: float,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Write per-step JSON log to {session_dir}/{level}-logs/{step_name}.json.

    Args:
        state: Current flow state (for session_dir/session_path)
        level: Level identifier: "level-minus1", "level1", "level2", "level3"
        step_name: Human-readable step name (used as filename)
        status: OK / FAILED / TIMEOUT
        duration: Duration in seconds
        result: Step result dict (summarized, not full values)
        error: Error message if failed
    """
    session_dir = state.get("session_dir") or state.get("session_path", "")
    if not session_dir:
        return

    try:
        log_dir = Path(session_dir) / f"{level}-logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "step": step_name,
            "level": level,
            "status": status,
            "duration_ms": round(duration * 1000, 1),
            "timestamp": datetime.now().isoformat(),
            "session_id": state.get("session_id", ""),
        }

        if error:
            log_entry["error"] = error

        if result:
            log_entry["result_summary"] = _summarize_result(result)

        # Sanitize step_name for filename
        safe_name = step_name.replace(" ", "-").replace("/", "-").lower()
        log_file = log_dir / f"{safe_name}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, indent=2)

    except Exception:
        pass  # Logging failure is never fatal


def _summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize result dict values for compact logging."""
    summary = {}
    for k, v in result.items():
        if isinstance(v, bool):
            summary[k] = v
        elif isinstance(v, (int, float)):
            summary[k] = v
        elif isinstance(v, str):
            summary[k] = v[:200] if len(v) > 200 else v
        elif isinstance(v, list):
            summary[k] = f"[{len(v)} items]"
        elif isinstance(v, dict):
            summary[k] = f"{{{len(v)} keys}}"
        elif v is None:
            summary[k] = None
        else:
            summary[k] = str(type(v).__name__)
    return summary
