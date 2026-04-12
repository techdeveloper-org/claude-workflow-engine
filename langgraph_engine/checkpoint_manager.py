"""
Checkpoint Manager - State persistence between steps.

Saves full FlowState after each step so execution can resume from any
completed checkpoint instead of restarting from the beginning.

Directory layout:
    ~/.claude/logs/sessions/{session_id}/checkpoints/
        step-01.json
        step-02.json
        ...
        latest.json  (copy of most recent)

Checkpoint payload schema:
    {
        "checkpoint_id": "{session_id}:step-{N}",
        "step": int,
        "timestamp": ISO-8601,
        "session_id": str,
        "success_status": bool,
        "error_message": str | null,
        "state": {...}
    }

Usage:
    from .checkpoint_manager import CheckpointManager

    cp = CheckpointManager(session_id)
    cp.save_checkpoint(step=3, state=state)
    cp.save_checkpoint(step=4, state=state, success_status=False,
                       error_message="LLM timeout")

    last_step, recovered_state = cp.get_last_checkpoint()
    metadata = cp.load_checkpoint_metadata(step=3)
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now().isoformat()


def _serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON-safe copy of state (drop non-serialisable values)."""
    safe: Dict[str, Any] = {}
    for key, value in state.items():
        try:
            json.dumps(value)  # probe
            safe[key] = value
        except (TypeError, ValueError):
            # Fall back to string representation
            try:
                safe[key] = str(value)
            except Exception:
                safe[key] = "<unserializable>"
    return safe


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Save and restore FlowState checkpoints per session."""

    CHECKPOINT_DIR_TEMPLATE = "~/.claude/logs/sessions/{session_id}/checkpoints"

    def __init__(self, session_id: str, base_dir: Optional[str] = None):
        """
        Initialise checkpoint manager.

        Args:
            session_id: Unique identifier for this execution session.
            base_dir:   Override default checkpoint base directory (optional).
        """
        self.session_id = session_id

        if base_dir:
            self.checkpoint_dir = Path(base_dir).expanduser() / session_id / "checkpoints"
        else:
            self.checkpoint_dir = Path(self.CHECKPOINT_DIR_TEMPLATE.format(session_id=session_id)).expanduser()

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"CheckpointManager ready: {self.checkpoint_dir}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _make_checkpoint_id(self, step: int) -> str:
        """Build a unique checkpoint identifier used for resume commands."""
        return f"{self.session_id}:step-{step:02d}"

    def _atomic_write(self, path: Path, content: str) -> None:
        """
        Write content to path atomically using a temp-file + rename pattern.

        On Windows, os.replace() is atomic for files on the same volume.
        Falls back to direct write if the temp file cannot be created.

        Raises:
            IOError: If both atomic write and fallback write fail.
        """
        dir_path = path.parent
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp_path, str(path))
            except Exception:
                # Clean up temp file if replace failed
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (OSError, PermissionError):
            # Fallback: direct write (non-atomic but better than nothing)
            path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_checkpoint(
        self,
        step: int,
        state: Dict[str, Any],
        success_status: bool = True,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Persist state after a step completes.

        The checkpoint file includes:
        - checkpoint_id: unique "{session_id}:step-{N}" key for resume
        - success_status: whether the step completed without errors
        - error_message: optional error description if success_status=False
        - full serialized FlowState

        Args:
            step:           Step number (0-14).
            state:          Current FlowState dict.
            success_status: True if step succeeded, False if it errored.
            error_message:  Optional error description for failed steps.

        Returns:
            True on success, False on failure.
        """
        try:
            safe_state = _serialize_state(state)
            checkpoint_id = self._make_checkpoint_id(step)
            checkpoint = {
                "checkpoint_id": checkpoint_id,
                "step": step,
                "timestamp": _now_iso(),
                "session_id": self.session_id,
                "success_status": success_status,
                "error_message": error_message,
                "state": safe_state,
            }

            payload = json.dumps(checkpoint, indent=2)

            path = self.checkpoint_dir / f"step-{step:02d}.json"
            self._atomic_write(path, payload)

            # Also write latest.json for quick access
            latest_path = self.checkpoint_dir / "latest.json"
            self._atomic_write(latest_path, payload)

            status_tag = "OK" if success_status else "FAILED"
            logger.info(f"[Checkpoint] Saved step {step} [{status_tag}] -> {path}")
            return True

        except IOError as e:
            logger.error(f"[Checkpoint] IOError saving step {step}: {e}")
            return False
        except PermissionError as e:
            logger.error(f"[Checkpoint] Permission denied saving step {step}: {e}")
            return False
        except OSError as e:
            logger.error(f"[Checkpoint] OS error saving step {step} (disk full?): {e}")
            return False
        except Exception as e:
            logger.error(f"[Checkpoint] Unexpected error saving step {step}: {e}")
            return False

    def load_checkpoint(self, step: int) -> Optional[Dict[str, Any]]:
        """
        Load state from a specific step checkpoint.

        Args:
            step: Step number to load.

        Returns:
            State dict, or None if checkpoint not found / corrupt.
        """
        path = self.checkpoint_dir / f"step-{step:02d}.json"
        if not path.exists():
            logger.debug(f"[Checkpoint] No checkpoint found for step {step}")
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(
                f"[Checkpoint] Loaded step {step} "
                f"(ts={data.get('timestamp')}, "
                f"success={data.get('success_status', 'unknown')})"
            )
            return data.get("state")
        except json.JSONDecodeError as e:
            logger.error(f"[Checkpoint] Corrupt JSON for step {step}: {e}")
            return None
        except IOError as e:
            logger.error(f"[Checkpoint] Failed to read step {step}: {e}")
            return None

    def load_checkpoint_metadata(self, step: int) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint metadata without the full state payload.

        Returns:
            Dict with checkpoint_id, step, timestamp, success_status, error_message,
            or None if not found.
        """
        path = self.checkpoint_dir / f"step-{step:02d}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "checkpoint_id": data.get("checkpoint_id", self._make_checkpoint_id(step)),
                "step": data.get("step", step),
                "timestamp": data.get("timestamp"),
                "session_id": data.get("session_id", self.session_id),
                "success_status": data.get("success_status", True),
                "error_message": data.get("error_message"),
            }
        except Exception as e:
            logger.error(f"[Checkpoint] Failed to load metadata for step {step}: {e}")
            return None

    def load_checkpoint_by_id(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Load state from a checkpoint using its checkpoint_id string.

        Supports format: "{session_id}:step-{N}" or just "step-{N}".

        Args:
            checkpoint_id: e.g. "my-session-123:step-05" or "step-05"

        Returns:
            State dict, or None.
        """
        # Parse step number from checkpoint_id
        try:
            if ":" in checkpoint_id:
                step_part = checkpoint_id.split(":")[-1]  # "step-05"
            else:
                step_part = checkpoint_id  # "step-05" or "05"

            if step_part.startswith("step-"):
                step = int(step_part[5:])
            else:
                step = int(step_part)
        except (ValueError, IndexError):
            logger.error(f"[Checkpoint] Cannot parse checkpoint_id: {checkpoint_id}")
            return None

        return self.load_checkpoint(step)

    def get_last_checkpoint(self) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        Find and return the most recently saved checkpoint.

        Returns:
            (step_number, state_dict) or (None, None) if no checkpoints exist.
        """
        checkpoint_files = sorted(self.checkpoint_dir.glob("step-*.json"))
        if not checkpoint_files:
            logger.info("[Checkpoint] No checkpoints found in session directory")
            return None, None

        last_file = checkpoint_files[-1]
        try:
            step_str = last_file.stem.split("-")[1]  # "step-03" -> "03"
            step = int(step_str)
        except (IndexError, ValueError):
            logger.warning(f"[Checkpoint] Unexpected filename format: {last_file.name}")
            return None, None

        state = self.load_checkpoint(step)
        return step, state

    def get_last_successful_checkpoint(self) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        Find the most recently saved checkpoint where success_status=True.

        Useful when you want to resume from a known-good state rather than
        the absolute last checkpoint (which may have been for a failed step).

        Returns:
            (step_number, state_dict) or (None, None) if none found.
        """
        checkpoint_files = sorted(self.checkpoint_dir.glob("step-*.json"), reverse=True)
        for f in checkpoint_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("success_status", True):
                    step_str = f.stem.split("-")[1]
                    step = int(step_str)
                    return step, data.get("state")
            except Exception:
                continue

        return None, None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """
        Return metadata list of all saved checkpoints (no state payloads).

        Returns:
            List of dicts: [{checkpoint_id, step, timestamp, success_status, path}, ...]
        """
        result = []
        for f in sorted(self.checkpoint_dir.glob("step-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(
                    {
                        "checkpoint_id": data.get("checkpoint_id", self._make_checkpoint_id(data.get("step", 0))),
                        "step": data.get("step"),
                        "timestamp": data.get("timestamp"),
                        "success_status": data.get("success_status", True),
                        "error_message": data.get("error_message"),
                        "path": str(f),
                    }
                )
            except Exception:
                pass
        return result

    def delete_checkpoint(self, step: int) -> bool:
        """
        Remove a specific checkpoint file.

        Args:
            step: Step number to remove.

        Returns:
            True if removed or did not exist, False on error.
        """
        path = self.checkpoint_dir / f"step-{step:02d}.json"
        try:
            if path.exists():
                path.unlink()
                logger.info(f"[Checkpoint] Deleted step {step} checkpoint")
            return True
        except (IOError, PermissionError) as e:
            logger.error(f"[Checkpoint] Failed to delete step {step}: {e}")
            return False

    def clear_all(self) -> int:
        """
        Remove every checkpoint file in the session directory.

        Returns:
            Count of files removed.
        """
        removed = 0
        for f in self.checkpoint_dir.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except IOError:
                pass
        logger.info(f"[Checkpoint] Cleared {removed} checkpoint(s)")
        return removed


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_checkpoint_manager(session_id: str) -> CheckpointManager:
    """Create a CheckpointManager for the given session."""
    return CheckpointManager(session_id)


# ---------------------------------------------------------------------------
# CLI / smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sid = sys.argv[1] if len(sys.argv) > 1 else "test-session-cp"
    mgr = CheckpointManager(sid)

    dummy_state = {
        "session_id": sid,
        "user_message": "Implement feature X",
        "step1_plan_required": True,
        "step3_tasks_validated": [{"id": "t1", "description": "Write tests"}],
    }

    print("Saving checkpoint for step 3 (success)...")
    ok = mgr.save_checkpoint(3, dummy_state, success_status=True)
    print(f"  saved={ok}")

    print("Saving checkpoint for step 4 (failed)...")
    ok = mgr.save_checkpoint(4, dummy_state, success_status=False, error_message="LLM timeout after 30s")
    print(f"  saved={ok}")

    print("Loading checkpoint for step 3...")
    recovered = mgr.load_checkpoint(3)
    print(f"  user_message={recovered.get('user_message') if recovered else 'NONE'}")

    print("Loading metadata for step 4...")
    meta = mgr.load_checkpoint_metadata(4)
    print(f"  metadata={meta}")

    print("Loading by checkpoint_id...")
    cid = mgr._make_checkpoint_id(3)
    recovered_by_id = mgr.load_checkpoint_by_id(cid)
    print(f"  loaded_by_id ok={recovered_by_id is not None}")

    print("Getting last successful checkpoint...")
    last_step, _ = mgr.get_last_successful_checkpoint()
    print(f"  last_successful_step={last_step}")

    print("Getting last checkpoint (any)...")
    last_step, last_state = mgr.get_last_checkpoint()
    print(f"  last_step={last_step}")

    print("Listing all checkpoints...")
    for cp in mgr.list_checkpoints():
        print(f"  step={cp['step']} id={cp['checkpoint_id']} ok={cp['success_status']}")

    print("Done.")
