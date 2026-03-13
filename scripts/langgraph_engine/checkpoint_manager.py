"""
Checkpoint Manager - State persistence between steps.

Saves full FlowState after each step so execution can resume from any
completed checkpoint instead of restarting from the beginning.

Directory layout:
    ~/.claude/logs/sessions/{session_id}/checkpoints/
        step-01.json
        step-02.json
        ...
        latest.json  (symlink / copy of most recent)

Usage:
    from .checkpoint_manager import CheckpointManager

    cp = CheckpointManager(session_id)
    cp.save_checkpoint(step=3, state=state)

    last_step, recovered_state = cp.get_last_checkpoint()
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

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
            json.dumps(value)   # probe
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
            self.checkpoint_dir = Path(
                self.CHECKPOINT_DIR_TEMPLATE.format(session_id=session_id)
            ).expanduser()

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"CheckpointManager ready: {self.checkpoint_dir}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_checkpoint(self, step: int, state: Dict[str, Any]) -> bool:
        """
        Persist state after a step completes.

        Args:
            step:  Step number (0-14).
            state: Current FlowState dict.

        Returns:
            True on success, False on failure.
        """
        try:
            safe_state = _serialize_state(state)
            checkpoint = {
                "step": step,
                "timestamp": _now_iso(),
                "session_id": self.session_id,
                "state": safe_state,
            }

            path = self.checkpoint_dir / f"step-{step:02d}.json"
            path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")

            # Also write latest.json so quick access doesn't need directory scan
            latest_path = self.checkpoint_dir / "latest.json"
            latest_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")

            logger.info(f"[Checkpoint] Saved after step {step} -> {path}")
            return True

        except IOError as e:
            logger.error(f"[Checkpoint] IOError saving step {step}: {e}")
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
            logger.info(f"[Checkpoint] Loaded step {step} checkpoint (ts={data.get('timestamp')})")
            return data.get("state")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[Checkpoint] Failed to load step {step}: {e}")
            return None

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
            step_str = last_file.stem.split("-")[1]   # "step-03" -> "03"
            step = int(step_str)
        except (IndexError, ValueError):
            logger.warning(f"[Checkpoint] Unexpected filename format: {last_file.name}")
            return None, None

        state = self.load_checkpoint(step)
        return step, state

    def list_checkpoints(self) -> list:
        """
        Return metadata list of all saved checkpoints (no state payloads).

        Returns:
            List of dicts: [{step, timestamp, path}, ...]
        """
        result = []
        for f in sorted(self.checkpoint_dir.glob("step-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "step": data.get("step"),
                    "timestamp": data.get("timestamp"),
                    "path": str(f),
                })
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
        except IOError as e:
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

    print("Saving checkpoint for step 3...")
    ok = mgr.save_checkpoint(3, dummy_state)
    print(f"  saved={ok}")

    print("Loading checkpoint for step 3...")
    recovered = mgr.load_checkpoint(3)
    print(f"  user_message={recovered.get('user_message') if recovered else 'NONE'}")

    print("Getting last checkpoint...")
    last_step, last_state = mgr.get_last_checkpoint()
    print(f"  last_step={last_step}")

    print("Listing all checkpoints...")
    for cp in mgr.list_checkpoints():
        print(f"  {cp}")

    print("Done.")
