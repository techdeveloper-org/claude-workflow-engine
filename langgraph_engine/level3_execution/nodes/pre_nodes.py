"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.
"""

import os
from pathlib import Path
from typing import Any, Dict

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_session_logs_dir

    _LEVEL3V2_SESSION_LOGS_DIR = get_session_logs_dir()
except ImportError:
    _LEVEL3V2_SESSION_LOGS_DIR = Path.home() / ".claude" / "logs" / "sessions"

# _run_step is defined in the parent subgraph module.  Imported via try/except
# because subgraph.py imports this module (circular chain); the fallback keeps
# the module importable in isolation (unit tests, static analysis).
try:
    from ..subgraph import _run_step
except ImportError:  # pragma: no cover

    def _run_step(step_number, label, fn, state, fallback_result=None):  # type: ignore[misc]
        try:
            return fn(state)
        except Exception as exc:
            logger.error("_run_step fallback caught exception in Step %s: %s", step_number, exc)
            return fallback_result or {}


def step0_0_project_context_node(state: FlowState) -> Dict[str, Any]:
    """Step 0.0: Pre-flight - Read project context files (README, CHANGELOG, etc.).

    Reads key project files (capped 5KB each) to provide context for downstream steps.
    Fail-open: never blocks the pipeline.
    """
    import time as _t

    _start = _t.time()
    try:
        project_root = Path(state.get("project_root", "."))
        context = {}
        files_read = []
        max_bytes = 5120  # 5KB cap per file

        candidate_files = [
            "README.md",
            "CHANGELOG.md",
            "VERSION",
            "pyproject.toml",
            "package.json",
        ]

        for fname in candidate_files:
            fpath = project_root / fname
            if fpath.is_file():
                try:
                    raw = fpath.read_text(encoding="utf-8", errors="replace")
                    context[fname] = raw[:max_bytes]
                    files_read.append(fname)
                except Exception:
                    pass

        elapsed = (_t.time() - _start) * 1000
        return {
            "step0_0_project_context": context,
            "step0_0_files_read": files_read,
            "step0_0_execution_time_ms": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = (_t.time() - _start) * 1000
        return {
            "step0_0_project_context": {},
            "step0_0_files_read": [],
            "step0_0_error": str(e),
            "step0_0_execution_time_ms": round(elapsed, 1),
        }


def step0_1_initial_callgraph_node(state: FlowState) -> Dict[str, Any]:
    """Step 0.1: Pre-flight - Capture initial call graph baseline.

    Calls snapshot_call_graph() to create a pre-change baseline that Step 11
    can diff against to detect breaking changes.
    Fail-open: never blocks the pipeline.
    """
    import time as _t

    _start = _t.time()
    try:
        from ..call_graph_analyzer import snapshot_call_graph

        project_root = state.get("project_root", ".")
        snapshot = snapshot_call_graph(project_root)

        elapsed = (_t.time() - _start) * 1000
        return {
            "step0_1_initial_callgraph": snapshot,
            "step0_1_callgraph_available": bool(snapshot),
            "step0_1_execution_time_ms": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = (_t.time() - _start) * 1000
        logger.debug("[v2] Initial callgraph snapshot skipped: %s" % str(e))
        return {
            "step0_1_initial_callgraph": None,
            "step0_1_callgraph_available": False,
            "step0_1_error": str(e),
            "step0_1_execution_time_ms": round(elapsed, 1),
        }


def level3_init_node(state: FlowState) -> Dict[str, Any]:
    """
    Bridge: Map session_path (from Level 1) to session_dir (used by steps).

    session_path is set by node_session_loader in Level 1.
    session_dir is what Level 3 steps use.

    CRITICAL: Must resolve to REAL session directory, never "unknown".
    Fallback chain: state.session_path -> state.session_id -> env CURRENT_SESSION_ID
    """

    session_path = state.get("session_path", "")
    session_id = state.get("session_id", "")

    # Fallback chain for session_id
    if not session_id:
        session_id = os.environ.get("CURRENT_SESSION_ID", "")

    if not session_path:
        # Construct from session_id
        if not session_id:
            session_id = "unknown"
        session_path = str(_LEVEL3V2_SESSION_LOGS_DIR / session_id)
        Path(session_path).mkdir(parents=True, exist_ok=True)

    # Install signal handlers once per session (best-effort, main thread only)
    try:
        from ..recovery_handler import RecoveryHandler

        handler = RecoveryHandler(session_id=session_id)
        handler.install_signal_handlers()
        handler.update_state(0, dict(state))
    except Exception as e:
        logger.debug(f"[v2] Recovery handler install skipped: {e}")

    # Load workflow memory from previous run (if resuming)
    workflow_memory = {}
    try:
        import json

        memory_file = Path(session_path) / "workflow-memory.json"
        if memory_file.is_file():
            workflow_memory = json.loads(memory_file.read_text(encoding="utf-8", errors="replace"))
            logger.info(
                "[v2] Loaded workflow memory from previous run " "(last_step=%s)", workflow_memory.get("last_step", "?")
            )
    except Exception as e:
        logger.debug("[v2] Workflow memory load skipped: %s" % str(e))

    result = {
        "session_dir": session_path,
        "user_requirement": state.get("user_message", ""),
    }
    if workflow_memory:
        result["workflow_memory_file"] = str(Path(session_path) / "workflow-memory.json")

    # Extract user preferences into pre-computed context for Steps 1, 5, 7
    try:
        prefs = state.get("preferences_data") or {}
        if prefs:
            result["user_preferences_context"] = {
                "model_hint": prefs.get("preferred_model", ""),
                "skill_hints": prefs.get("preferred_skills", []),
                "complexity_threshold": prefs.get("complexity_threshold", 7),
                "raw_keys": list(prefs.keys()),
            }
    except Exception:
        pass  # Best-effort: preferences context is non-blocking

    return result


# ============================================================================
# STEP NODE FACTORY - Factory pattern for thin step wrapper nodes
# ============================================================================


class StepNodeFactory:
    """Factory for creating LangGraph-compatible step node callables.

    Wraps _run_step() so that callers can register new pipeline steps
    without duplicating the try/except/metrics/checkpoint boilerplate.
    Steps that contain substantial extra logic beyond the core step
    function (e.g. CallGraph injection, Figma, Jira) should still be
    implemented as explicit node functions; this factory is intended
    for thin wrappers where the only responsibility is delegating to
    a step function and providing a fallback result.

    Usage::

        node = StepNodeFactory.make(
            step_number=1,
            step_label="Plan Mode Decision",
            step_fn=step1_plan_mode_decision,
            fallback={"step1_plan_required": True},
        )
        graph.add_node("level3_step1", node)

    Design pattern: Factory Method (GoF) - creates callables without
    requiring the caller to know about _run_step internals.
    """

    @staticmethod
    def make(step_number, step_label, step_fn, fallback=None):
        """Create and return a LangGraph node callable for a pipeline step.

        Args:
            step_number: Numeric step index (0-14).
            step_label:  Human-readable step label for logging.
            step_fn:     Callable(state) -> dict implementing the step.
            fallback:    Optional dict returned on unrecoverable error.

        Returns:
            A callable (state: FlowState) -> Dict[str, Any] with
            __name__ set to 'step{N}_node' for LangGraph introspection.
        """

        def _node(state):
            return _run_step(step_number, step_label, step_fn, state, fallback_result=fallback)

        _node.__name__ = "step%d_node" % step_number
        _node.__qualname__ = "step%d_node" % step_number
        return _node


# ============================================================================
# STEP WRAPPER NODES - Full error handling + checkpointing + metrics
# ============================================================================
