"""
Level 3 - TODO Executor

Executes a list of TODO items produced by todo_decomposer, calling
orchestrator_agent_caller.py as a subprocess for each TODO.

Supports resume via a sidecar checkpoint file (session_dir/todo_checkpoint.json)
that is read on entry and updated after each TODO completes.

Environment:
  STEP0_TODO_EXEC_TIMEOUT  seconds to wait per TODO subprocess (default: 300)
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ORCHESTRATOR_CALLER_PATH = Path(__file__).resolve().parent / "orchestrator_agent_caller.py"
_TODO_EXEC_TIMEOUT = int(os.getenv("STEP0_TODO_EXEC_TIMEOUT", "300"))
_CHECKPOINT_FILENAME = "todo_checkpoint.json"

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def _load_checkpoint(checkpoint_path):
    """Load sidecar checkpoint file. Returns (completed_ids set, results dict)."""
    try:
        path = Path(checkpoint_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            completed = set(data.get("completed_ids", []))
            results = data.get("results", {})
            return completed, results
    except Exception as exc:
        logger.debug("[todo_executor] checkpoint load failed (ignored): %s", exc)
    return set(), {}


def _save_checkpoint(checkpoint_path, completed_ids, results):
    """Write sidecar checkpoint file atomically. Never raises."""
    try:
        path = Path(checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "completed_ids": sorted(completed_ids),
            "results": results,
        }
        path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("[todo_executor] checkpoint save failed (ignored): %s", exc)


def _resolve_checkpoint_path(session_dir):
    """Return absolute path for the checkpoint sidecar file."""
    if session_dir:
        return str(Path(session_dir) / _CHECKPOINT_FILENAME)
    return str(Path(tempfile.gettempdir()) / _CHECKPOINT_FILENAME)


# ---------------------------------------------------------------------------
# Per-TODO execution
# ---------------------------------------------------------------------------


def _execute_single_todo(todo_item):
    """Call orchestrator_agent_caller.py for one TODO item.

    Returns a result dict with status, llm_response, and error fields.
    Never raises.
    """
    todo_id = todo_item.get("id", "unknown")
    todo_prompt = todo_item.get("prompt", "")
    prompt_file = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as tf:
            tf.write(todo_prompt)
            prompt_file = tf.name

        cmd = [
            sys.executable,
            str(_ORCHESTRATOR_CALLER_PATH),
            "--orchestration-prompt-file",
            prompt_file,
        ]

        logger.info("[todo_executor] Executing TODO %s via orchestrator_agent_caller", todo_id)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TODO_EXEC_TIMEOUT,
        )

        stdout = proc.stdout or ""
        stderr_preview = (proc.stderr or "")[:200]

        if proc.returncode != 0 and not stdout.strip():
            return {
                "status": "FAILED",
                "todo_id": todo_id,
                "result": None,
                "error": "subprocess exit %d: %s" % (proc.returncode, stderr_preview),
            }

        parsed = {}
        try:
            if stdout.strip():
                parsed = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            parsed = {"llm_response": stdout.strip()}

        return {
            "status": "SUCCESS",
            "todo_id": todo_id,
            "result": parsed,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "todo_id": todo_id,
            "result": None,
            "error": "subprocess timed out after %ds" % _TODO_EXEC_TIMEOUT,
        }
    except Exception as exc:
        return {
            "status": "FAILED",
            "todo_id": todo_id,
            "result": None,
            "error": str(exc),
        }
    finally:
        if prompt_file:
            try:
                Path(prompt_file).unlink(missing_ok=True)
            except OSError as exc:
                logger.debug(f"todo_executor: temp prompt file cleanup skipped: {exc}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_todo_list(
    state: Dict[str, Any],
    todo_list: List[Dict[str, Any]],
    checkpoint_manager: Optional[Any] = None,
    step_number: int = 0,
) -> List[Dict[str, Any]]:
    """Execute a list of TODO items, resuming from sidecar checkpoint if present.

    For each TODO in todo_list:
      - Skips items whose ID already appears in the checkpoint's completed_ids.
      - Calls orchestrator_agent_caller.py as a subprocess with the TODO prompt.
      - Saves the sidecar checkpoint after each completion.

    Args:
        state: FlowState dict providing session_dir and project_root.
        todo_list: List of TODO dicts from todo_decomposer.
        checkpoint_manager: Reserved for future use; ignored when None.
        step_number: Pipeline step number used in log messages.

    Returns:
        List of per-TODO result dicts, each containing todo_id, status,
        result, and error fields.
    """
    session_dir = state.get("session_dir", "") or ""
    checkpoint_path = _resolve_checkpoint_path(session_dir)

    completed_ids, checkpoint_results = _load_checkpoint(checkpoint_path)
    if completed_ids:
        logger.info(
            "[todo_executor] step=%d Resume: %d already completed TODOs",
            step_number,
            len(completed_ids),
        )

    execution_results: List[Dict[str, Any]] = []

    for todo_item in todo_list:
        todo_id = todo_item.get("id", "")

        if todo_id and todo_id in completed_ids:
            logger.info("[todo_executor] step=%d Skipping completed TODO %s", step_number, todo_id)
            skipped_result = checkpoint_results.get(todo_id, {})
            execution_results.append(
                {
                    "status": "SKIPPED",
                    "todo_id": todo_id,
                    "result": skipped_result,
                    "error": None,
                }
            )
            continue

        item_result = _execute_single_todo(todo_item)
        execution_results.append(item_result)

        if todo_id:
            completed_ids.add(todo_id)
            checkpoint_results[todo_id] = item_result.get("result") or {}
            _save_checkpoint(checkpoint_path, completed_ids, checkpoint_results)

        logger.info(
            "[todo_executor] step=%d TODO %s -> %s",
            step_number,
            todo_id,
            item_result.get("status", "UNKNOWN"),
        )

    return execution_results
