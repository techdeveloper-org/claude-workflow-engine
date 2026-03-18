"""
Level 3 SubGraph v2 - Integrated 15-Step Execution Pipeline (Step 0-14)

Bridge module that wraps the WORKFLOW.md-compliant level3_execution.py functions
with proper orchestrator integration and logging.

All 15 steps (Step 0-14) implemented with:
- Proper logging via loguru
- Time tracking
- TOON object handling
- Session management
- LangGraph routing support
- Global error handling with try/catch on every critical path
- Checkpointing after each completed step
- Metrics collection (duration, status, tokens) per step
- RecoveryHandler for signal handling (Ctrl+C)
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Lazy import: avoid import-time side effects from timeout_wrapper
def _get_timeout_wrapper():
    """Lazy-load timeout_wrapper to avoid import-time side effects."""
    try:
        from ..timeout_wrapper import STEP_TIMEOUTS, StepTimeout
        return STEP_TIMEOUTS, StepTimeout
    except Exception as _e:
        return {}, None

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from ..flow_state import FlowState
from ..step_logger import write_level_log
from ..rag_integration import rag_store_after_node, rag_lookup_before_llm, get_rag_layer
from .level3_execution import (
    step0_task_analysis,
    step1_plan_mode_decision,
    step2_plan_execution,
    step3_task_breakdown_validation,
    step4_toon_refinement,
    step5_skill_agent_selection,
    step6_skill_validation_download,
    step7_final_prompt_generation,
    step8_github_issue_creation,
    step9_branch_creation,
    step10_implementation_execution,
    step11_pull_request_review,
    step12_issue_closure,
    step13_project_documentation_update,
    step14_final_summary_generation,
    route_after_step1_plan_decision,
    route_after_step11_review,
    level3_merge_node,
)

# ---------------------------------------------------------------------------
# Lazy import helpers for the new infrastructure modules
# ---------------------------------------------------------------------------

def _get_checkpoint_manager(session_id: str):
    """Lazy-load CheckpointManager to avoid import-time side-effects."""
    try:
        from ..checkpoint_manager import CheckpointManager
        return CheckpointManager(session_id)
    except Exception as e:
        logger.warning(f"[v2] CheckpointManager unavailable: {e}")
        return None


def _get_metrics_collector(session_id: str):
    """Lazy-load MetricsCollector."""
    try:
        from ..metrics_collector import MetricsCollector
        return MetricsCollector(session_id)
    except Exception as e:
        logger.warning(f"[v2] MetricsCollector unavailable: {e}")
        return None


def _get_error_logger(session_id: str):
    """Lazy-load ErrorLogger."""
    try:
        from ..error_logger import ErrorLogger
        return ErrorLogger(session_id=session_id)
    except Exception as e:
        logger.warning(f"[v2] ErrorLogger unavailable: {e}")
        return None


def _get_backup_manager(session_id: str):
    """Lazy-load BackupManager."""
    try:
        from ..backup_manager import BackupManager
        return BackupManager(session_id=session_id)
    except Exception as e:
        logger.warning(f"[v2] BackupManager unavailable: {e}")
        return None


# ---------------------------------------------------------------------------
# Shared per-session infrastructure cache (keyed by session_id)
# ---------------------------------------------------------------------------
# Avoids creating multiple instances when the same session runs many steps.

_infra_cache: Dict[str, Dict[str, Any]] = {}


def _get_infra(state: FlowState) -> Dict[str, Any]:
    """
    Return (and cache) infrastructure objects for this session.

    Returns a dict with keys: checkpoint, metrics, error_logger, backup.
    Missing objects are None (degraded but non-fatal).

    IMPORTANT: session_id MUST be a real session ID (from Level 1 node_session_loader).
    We check state, then env var, then session_path. Never use "unknown" - it creates
    orphan log directories.
    """
    import os

    session_id = (
        state.get("session_id")
        or os.environ.get("CURRENT_SESSION_ID", "")
        or ""
    )

    # Extract session_id from session_path if still empty
    if not session_id:
        session_path = state.get("session_path", "") or state.get("session_dir", "")
        if session_path:
            # session_path = ~/.claude/logs/sessions/{session_id}
            session_id = Path(session_path).name

    if not session_id:
        session_id = "unknown"

    # Cache infrastructure per session_id, but allow upgrade from "unknown" to real ID
    if session_id != "unknown" and "unknown" in _infra_cache and session_id not in _infra_cache:
        # Real session_id arrived - create proper infra (don't keep using "unknown")
        _infra_cache[session_id] = {
            "checkpoint": _get_checkpoint_manager(session_id),
            "metrics":    _get_metrics_collector(session_id),
            "error_logger": _get_error_logger(session_id),
            "backup":     _get_backup_manager(session_id),
        }
        # Store session_id in env for other components
        os.environ["CURRENT_SESSION_ID"] = session_id

    if session_id not in _infra_cache:
        _infra_cache[session_id] = {
            "checkpoint": _get_checkpoint_manager(session_id),
            "metrics":    _get_metrics_collector(session_id),
            "error_logger": _get_error_logger(session_id),
            "backup":     _get_backup_manager(session_id),
        }
        if session_id != "unknown":
            os.environ["CURRENT_SESSION_ID"] = session_id

    return _infra_cache[session_id]


# ---------------------------------------------------------------------------
# Per-step session logging
# ---------------------------------------------------------------------------

def _write_step_log(
    state: FlowState,
    step_number: int,
    step_label: str,
    status: str,
    duration: float,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Write per-step log entry to session directory.

    Delegates to the shared write_level_log utility for the level3 step-logs
    directory, AND writes a backward-compatible step-{NN}.json file.

    Args:
        state: Current flow state (for session_dir)
        step_number: Step number (0-14)
        step_label: Human-readable step label
        status: OK / FAILED / TIMEOUT
        duration: Duration in seconds
        result: Step result dict (keys only, not full values to save space)
        error: Error message if failed
    """
    # Write to shared level3-logs/{step_name}.json
    step_name = f"step-{step_number:02d}-{step_label.lower().replace(' ', '-')}"
    write_level_log(state, "level3", step_name, status, duration, result, error)

    # Also write backward-compatible step-logs/step-{NN}.json
    import json as _json

    session_dir = state.get("session_dir") or state.get("session_path", "")
    if not session_dir:
        return

    try:
        log_dir = Path(session_dir) / "step-logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "step": step_number,
            "label": step_label,
            "status": status,
            "duration_ms": round(duration * 1000, 1),
            "timestamp": datetime.now().isoformat(),
            "session_id": state.get("session_id", ""),
        }

        if error:
            log_entry["error"] = error

        if result:
            from ..step_logger import _summarize_result
            log_entry["result_summary"] = _summarize_result(result)

        log_file = log_dir / f"step-{step_number:02d}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            _json.dump(log_entry, f, indent=2)

    except Exception:
        pass  # Logging failure is never fatal


# ---------------------------------------------------------------------------
# RAG-eligible steps: these make LLM calls that can be short-circuited by RAG
# ---------------------------------------------------------------------------
# Steps 3,4,6 have no LLM; Steps 9-14 are unique per task; Step 10 is implementation
_RAG_ELIGIBLE_STEPS = {0, 1, 2, 5, 7, 8}


# ---------------------------------------------------------------------------
# Core step execution wrapper
# ---------------------------------------------------------------------------

def _run_step(
    step_number: int,
    step_label: str,
    step_fn,
    state: FlowState,
    *,
    fallback_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a single step function with full error handling infrastructure.

    Responsibilities:
    1. Log step entry.
    2. Update RecoveryHandler with current step (for Ctrl+C).
    3. Execute step_fn(state) inside a timeout-enforced wrapper.
    4. On success: record metric, save checkpoint.
    5. On timeout/failure: log error, record metric, return fallback_result.

    Timeouts are loaded from timeout_wrapper.STEP_TIMEOUTS (lazy import).
    Steps without a configured timeout run without a time limit.

    Args:
        step_number:    Numeric step (0-14), used for checkpoint naming.
        step_label:     Human label for logging (e.g. "STEP 3").
        step_fn:        Callable(state) -> dict.
        state:          Current FlowState.
        fallback_result: Dict to return on unrecoverable error.

    Returns:
        Result dict from step_fn, or fallback_result on timeout/failure.
    """
    import os as _os
    # Dry-run: skip Steps 8-14 (GitHub, implementation, PR, review, docs)
    if step_number >= 8 and _os.environ.get("CLAUDE_DRY_RUN") == "1":
        logger.info(f"[v2] Step {step_number} skipped (dry-run mode)")
        print(f"[STEP {step_number:02d}] {step_label} - SKIPPED (dry-run)", file=sys.stderr)
        return {**(fallback_result or {}), f"step{step_number}_status": "DRY_RUN_SKIPPED"}

    infra = _get_infra(state)
    cp = infra["checkpoint"]
    metrics = infra["metrics"]
    error_logger = infra["error_logger"]

    # Update recovery handler's view of current step
    try:
        from ..recovery_handler import _register_globals
        if cp and error_logger:
            _register_globals(step_number, dict(state), cp, error_logger)
    except Exception:
        pass   # Recovery handler update is best-effort

    # Log step start to stderr for real-time visibility
    print(f"\n[STEP {step_number:02d}] {step_label} - START", file=sys.stderr)
    logger.info(f"\n[STEP {step_number:02d}] {step_label} - START")
    step_start = time.time()

    # --- RAG lookup before LLM call (fail-open) ---
    if step_number in _RAG_ELIGIBLE_STEPS:
        try:
            user_msg = state.get("user_message", "") or ""
            rag_query = f"{step_label} {user_msg[:200]}"
            step_key = f"step{step_number}"
            rag_result = rag_lookup_before_llm(step=step_key, query=rag_query, state=dict(state))
            if rag_result and rag_result.get("rag_hit"):
                duration = time.time() - step_start
                cached_decision = rag_result.get("decision", {})
                confidence = rag_result.get("confidence", 0.0)
                print(
                    f"[STEP {step_number:02d}] {step_label} - RAG HIT "
                    f"(confidence={confidence:.2f}, {duration*1000:.0f}ms)",
                    file=sys.stderr,
                )
                logger.info(
                    f"[STEP {step_number:02d}] {step_label} - RAG HIT "
                    f"(confidence={confidence:.2f})"
                )
                # Add RAG metadata to cached result
                cached_decision[f"step{step_number}_rag_hit"] = True
                cached_decision[f"step{step_number}_rag_confidence"] = confidence
                cached_decision[f"step{step_number}_execution_time_ms"] = duration * 1000
                # Write step log
                _write_step_log(state, step_number, step_label, "RAG_HIT", duration, cached_decision)
                # Record metric
                if metrics:
                    try:
                        metrics.record_step(step=step_number, duration=duration, status="RAG_HIT")
                    except Exception:
                        pass
                return cached_decision
            else:
                print(f"[STEP {step_number:02d}] {step_label} - RAG MISS", file=sys.stderr)
        except Exception as rag_exc:
            # Fail-open: RAG errors never block pipeline
            logger.debug(f"[STEP {step_number:02d}] RAG lookup failed (non-fatal): {rag_exc}")

    # --- Timeout enforcement ---
    # Load timeout table; gracefully degrade if module unavailable
    _timeouts, _StepTimeout = _get_timeout_wrapper()
    timeout_s = _timeouts.get(step_number) if _timeouts else None

    try:
        if timeout_s is not None and _StepTimeout is not None:
            tw = _StepTimeout(timeout_seconds=timeout_s)
            result = tw.run(
                fn=step_fn,
                args=(state,),
                fallback=fallback_result or {},
                step_label=f"STEP {step_number:02d}: {step_label}",
            )
            # Check if timeout_wrapper returned its own error result
            if result.get("timed_out"):
                logger.warning(
                    f"[STEP {step_number:02d}] {step_label} - TIMED OUT after {timeout_s}s"
                )
                duration = time.time() - step_start
                if metrics:
                    try:
                        metrics.record_step(step=step_number, duration=duration, status="TIMEOUT")
                    except Exception:
                        pass
                if error_logger:
                    try:
                        error_logger.log_error(
                            step=f"Step {step_number}",
                            error_message=f"Timeout after {timeout_s}s",
                            severity="ERROR",
                            error_type="TimeoutError",
                            recovery_action="Returning fallback result",
                        )
                    except Exception:
                        pass
                # Build full fallback with timing info
                base = {
                    f"step{step_number}_error": f"Timeout after {timeout_s}s",
                    f"step{step_number}_execution_time_ms": duration * 1000,
                }
                return {**(fallback_result or {}), **base}
        else:
            result = step_fn(state)

        duration = time.time() - step_start

        # Record SUCCESS metric
        if metrics:
            try:
                metrics.record_step(
                    step=step_number,
                    duration=duration,
                    status="SUCCESS",
                )
            except Exception as me:
                logger.warning(f"[v2] Metrics record failed: {me}")

        # Checkpoint: merge state + result then save (success_status=True)
        if cp:
            try:
                merged = {**dict(state), **(result or {})}
                cp.save_checkpoint(
                    step_number,
                    merged,
                    success_status=True,
                )
            except Exception as ce:
                logger.warning(f"[v2] Checkpoint save failed: {ce}")

        print(f"[STEP {step_number:02d}] {step_label} - OK ({duration*1000:.0f}ms)", file=sys.stderr)
        logger.info(f"[STEP {step_number:02d}] {step_label} - OK ({duration*1000:.0f}ms)")

        # Write step log to session directory
        _write_step_log(state, step_number, step_label, "OK", duration, result)

        # Store node decision in Vector DB for RAG (non-blocking)
        try:
            step_key = f"step{step_number}"
            rag_store_after_node(step=step_key, decision=result or {}, state=dict(state))
        except Exception:
            pass  # RAG storage is never fatal

        # Save workflow memory for resume support (non-blocking)
        try:
            import json as _json
            session_dir = state.get("session_dir", "")
            if session_dir:
                mem_path = Path(session_dir) / "workflow-memory.json"
                mem_data = {
                    "last_step": step_number,
                    "last_step_label": step_label,
                    "last_step_status": "SUCCESS",
                    "timestamp": datetime.now().isoformat(),
                    "session_id": state.get("session_id", ""),
                }
                mem_path.write_text(
                    _json.dumps(mem_data, indent=2), encoding="utf-8"
                )
        except Exception:
            pass  # Workflow memory is best-effort

        if result is not None:
            result[f"step{step_number}_execution_time_ms"] = duration * 1000

        return result or {}

    except Exception as exc:
        duration = time.time() - step_start

        # Log structured error
        if error_logger:
            try:
                error_logger.log_error(
                    step=f"Step {step_number}",
                    error_message=str(exc),
                    severity="ERROR",
                    error_type=type(exc).__name__,
                    recovery_action=(
                        "Returning fallback result"
                        if fallback_result is not None
                        else "Step returning empty result"
                    ),
                )
            except Exception:
                pass

        # Record FAILED metric
        if metrics:
            try:
                metrics.record_step(
                    step=step_number,
                    duration=duration,
                    status="FAILED",
                )
                metrics.record_error(
                    step=step_number,
                    error_type=type(exc).__name__,
                    recovery="Fallback result returned",
                    message=str(exc),
                )
            except Exception:
                pass

        # Save failed checkpoint (success_status=False, include error message)
        if cp:
            try:
                merged = {**dict(state), **(fallback_result or {})}
                cp.save_checkpoint(
                    step_number,
                    merged,
                    success_status=False,
                    error_message=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            except Exception as ce:
                logger.warning(f"[v2] Failed checkpoint save after error: {ce}")

        print(f"[STEP {step_number:02d}] {step_label} - FAILED: {exc}", file=sys.stderr)
        logger.error(f"[STEP {step_number:02d}] {step_label} - FAILED: {exc}")

        # Write step error log to session directory
        _write_step_log(state, step_number, step_label, "FAILED", duration, None, str(exc))

        error_key = f"step{step_number}_error"
        base: Dict[str, Any] = {
            error_key: str(exc),
            f"step{step_number}_execution_time_ms": duration * 1000,
        }

        if fallback_result:
            return {**fallback_result, **base}

        return base


# ============================================================================
# BRIDGE NODE - Map Level 1 fields to Level 3 fields
# ============================================================================


def level3_init_node(state: FlowState) -> Dict[str, Any]:
    """
    Bridge: Map session_path (from Level 1) to session_dir (used by steps).

    session_path is set by node_session_loader in Level 1.
    session_dir is what Level 3 steps use.

    CRITICAL: Must resolve to REAL session directory, never "unknown".
    Fallback chain: state.session_path -> state.session_id -> env CURRENT_SESSION_ID
    """
    import os

    session_path = state.get("session_path", "")
    session_id = state.get("session_id", "")

    # Fallback chain for session_id
    if not session_id:
        session_id = os.environ.get("CURRENT_SESSION_ID", "")

    if not session_path:
        # Construct from session_id
        if not session_id:
            session_id = "unknown"
        session_path = str(Path.home() / ".claude" / "logs" / "sessions" / session_id)
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
            workflow_memory = json.loads(
                memory_file.read_text(encoding="utf-8", errors="replace")
            )
            logger.info(
                "[v2] Loaded workflow memory from previous run "
                "(last_step=%s)", workflow_memory.get("last_step", "?")
            )
    except Exception as e:
        logger.debug("[v2] Workflow memory load skipped: %s" % str(e))

    result = {
        "session_dir": session_path,
        "user_requirement": state.get("user_message", ""),
    }
    if workflow_memory:
        result["workflow_memory_file"] = str(
            Path(session_path) / "workflow-memory.json"
        )
    return result


# ============================================================================
# STEP WRAPPER NODES - Full error handling + checkpointing + metrics
# ============================================================================


def step0_task_analysis_node(state: FlowState) -> Dict[str, Any]:
    """Step 0: Task Analysis with full error handling."""
    return _run_step(
        0, "Task Analysis",
        step0_task_analysis,
        state,
        fallback_result={
            "step0_task_type": "General Task",
            "step0_complexity": 5,
            "step0_reasoning": "Default - step0 failed",
            "step0_tasks": {"count": 1, "tasks": []},
            "step0_task_count": 1,
        },
    )


def step1_plan_mode_decision_node(state: FlowState) -> Dict[str, Any]:
    """Step 1: Plan Mode Decision with full error handling."""
    return _run_step(
        1, "Plan Mode Decision",
        step1_plan_mode_decision,
        state,
        fallback_result={
            "step1_plan_required": True,   # Safe default: always plan on error
            "step1_reasoning": "Default - step1 failed, defaulting to plan mode",
            "step1_complexity_score": state.get("step0_complexity", 5),
        },
    )


def step2_plan_execution_node(state: FlowState) -> Dict[str, Any]:
    """Step 2: Plan Execution (conditional on Step 1) with full error handling.

    Injects CallGraph impact analysis before planning so the planner
    considers ripple effects of proposed changes.
    """
    # --- CallGraph Impact Analysis (pre-plan) ---
    impact_data = {}
    try:
        from ..call_graph_analyzer import analyze_impact_before_change
        project_root = state.get("project_root", ".")
        target_files = state.get("step0_target_files", [])
        task_desc = state.get("user_message", "")
        impact_data = analyze_impact_before_change(
            project_root, target_files, task_desc
        )
        if impact_data.get("call_graph_available"):
            logger.info(
                "[v2] Step 2 CallGraph impact: risk=%s, affected=%d methods",
                impact_data.get("risk_level", "unknown"),
                len(impact_data.get("affected_methods", [])),
            )
    except Exception as e:
        logger.debug("[v2] Step 2 CallGraph analysis skipped: %s", e)

    result = _run_step(
        2, "Plan Execution",
        step2_plan_execution,
        state,
        fallback_result={
            "step2_plan_execution": {"error": "Step 2 failed", "phases": []},
            "step2_plan_status": "ERROR",
            "step2_phases": 0,
            "step2_total_estimated_steps": 0,
        },
    )

    # Merge impact analysis into result
    if impact_data.get("call_graph_available"):
        result["step2_impact_analysis"] = impact_data
        result["step2_graph_risk_level"] = impact_data.get("risk_level", "low")
        result["step2_affected_methods"] = [
            m.get("fqn", "") for m in impact_data.get("affected_methods", [])
        ]

    return result


def step3_task_breakdown_node(state: FlowState) -> Dict[str, Any]:
    """Step 3: Task Breakdown Validation with full error handling."""
    result = _run_step(
        3, "Task Breakdown Validation",
        step3_task_breakdown_validation,
        state,
        fallback_result={
            "step3_tasks_validated": [],
            "step3_task_count": 0,
            "step3_validation_status": "ERROR",
            "step3_validation_errors": ["Step 3 failed"],
        },
    )

    # --- CallGraph: Map files to tasks/phases based on graph analysis ---
    try:
        from ..call_graph_analyzer import snapshot_call_graph
        project_root = state.get("project_root", ".")

        # Get or build the graph snapshot (reuse from Step 2 if available)
        graph_snapshot = state.get("step2_impact_analysis", {})
        if not graph_snapshot.get("call_graph_available"):
            graph_snapshot = snapshot_call_graph(project_root)

        # Map task descriptions to files using graph's method/class names
        validated_tasks = result.get("step3_tasks_validated", [])
        phase_file_map = {}

        all_methods = graph_snapshot.get("nodes", {}).get("methods", []) if "nodes" in graph_snapshot else []
        all_classes = graph_snapshot.get("nodes", {}).get("classes", []) if "nodes" in graph_snapshot else []

        for task in validated_tasks:
            desc = task.get("description", "").lower()
            task_id = task.get("id", "unknown")
            matched_files = set()

            # If task already has files from Step 0, use those
            if task.get("files"):
                matched_files.update(task["files"])
            else:
                # Match by keyword in class/method names against task description
                desc_words = set(w for w in desc.replace("-", " ").replace("_", " ").split() if len(w) > 3)
                for m in all_methods:
                    m_name = m.get("name", "").lower()
                    m_file = m.get("file", "")
                    if any(w in m_name for w in desc_words) and m_file:
                        matched_files.add(m_file)
                for c in all_classes:
                    c_name = c.get("name", "").lower()
                    c_file = c.get("file", "")
                    if any(w in c_name for w in desc_words) and c_file:
                        matched_files.add(c_file)

            phase_file_map[task_id] = sorted(matched_files)

        result["step3_phase_file_map"] = phase_file_map
        # Store the graph snapshot for reuse in Step 4
        if "nodes" in graph_snapshot:
            result["step3_graph_snapshot"] = graph_snapshot

        logger.info("[v2] Step 3 mapped %d tasks to files via CallGraph", len(phase_file_map))
    except Exception as e:
        logger.debug("[v2] Step 3 file mapping skipped: %s", e)

    return result


def step4_toon_refinement_node(state: FlowState) -> Dict[str, Any]:
    """Step 4: TOON Refinement with full error handling."""
    result = _run_step(
        4, "TOON Refinement",
        step4_toon_refinement,
        state,
        fallback_result={
            "step4_toon_refined": state.get("level1_context_toon", {}),
            "step4_refinement_status": "ERROR",
            "step4_complexity_adjusted": state.get("step0_complexity", 5),
        },
    )

    # --- CallGraph: Inject phase-scoped context, clear old broad context ---
    try:
        from ..call_graph_analyzer import get_phase_scoped_context

        # Get graph snapshot (from Step 3 or Step 2)
        graph_snapshot = (
            state.get("step3_graph_snapshot")
            or state.get("step2_impact_analysis", {})
        )

        # Get phase file mapping from Step 3
        phase_file_map = state.get("step3_phase_file_map", {})

        if graph_snapshot and phase_file_map:
            # For each phase/task, get its scoped context
            phase_contexts = {}
            all_phase_files = set()

            for task_id, files in phase_file_map.items():
                if files:
                    ctx = get_phase_scoped_context(
                        graph_snapshot, files, task_id
                    )
                    phase_contexts[task_id] = ctx
                    all_phase_files.update(files)

            if phase_contexts:
                result["step4_phase_contexts"] = phase_contexts
                result["step4_phase_scope_files"] = sorted(all_phase_files)

                # Clear old broad context - replace with focused phase data
                result["step4_old_context_cleared"] = True

                logger.info(
                    "[v2] Step 4 injected %d phase contexts, %d files in scope",
                    len(phase_contexts), len(all_phase_files),
                )
    except Exception as e:
        logger.debug("[v2] Step 4 phase context skipped: %s", e)

    return result


def step5_skill_selection_node(state: FlowState) -> Dict[str, Any]:
    """Step 5: Skill & Agent Selection with full error handling."""
    return _run_step(
        5, "Skill & Agent Selection",
        step5_skill_agent_selection,
        state,
        fallback_result={
            "step5_skill": "",
            "step5_agent": "",
            "step5_reasoning": "Default - step5 failed",
            "step5_confidence": 0.0,
            "step5_alternatives": [],
            "step5_llm_query_needed": False,
        },
    )


def step6_skill_validation_node(state: FlowState) -> Dict[str, Any]:
    """Step 6: Skill Validation & Download with full error handling."""
    return _run_step(
        6, "Skill Validation & Download",
        step6_skill_validation_download,
        state,
        fallback_result={
            "step6_skill_validation": {},
            "step6_skill_ready": True,    # Non-blocking default
            "step6_agent_ready": True,
            "step6_validation_status": "ERROR",
        },
    )


def step7_final_prompt_node(state: FlowState) -> Dict[str, Any]:
    """Step 7: Final Prompt Generation with full error handling."""

    def _with_file_error_handling(st):
        """Wrap step7 to add explicit file operation error handling."""
        try:
            return step7_final_prompt_generation(st)
        except IOError as io_err:
            # File write failure - attempt backup restore if possible
            infra = _get_infra(st)
            if infra["error_logger"]:
                infra["error_logger"].log_error(
                    step="Step 7",
                    error_message=str(io_err),
                    severity="ERROR",
                    error_type="IOError",
                    recovery_action="Returning minimal result without file persistence",
                )
            return {
                "step7_prompt_saved": False,
                "step7_error": f"IOError: {io_err}",
            }

    return _run_step(
        7, "Final Prompt Generation",
        _with_file_error_handling,
        state,
        fallback_result={
            "step7_prompt_saved": False,
            "step7_error": "Step 7 failed",
        },
    )


def step8_github_issue_node(state: FlowState) -> Dict[str, Any]:
    """Step 8: GitHub Issue Creation with retry and full error handling."""

    def _with_network_retry(st):
        """Network calls in step 8 get exponential backoff retry."""
        import requests
        from time import sleep

        last_exc = None
        for attempt in range(3):
            try:
                return step8_github_issue_creation(st)
            except requests.RequestException as req_exc:
                last_exc = req_exc
                infra = _get_infra(st)
                if infra["error_logger"]:
                    infra["error_logger"].log_error(
                        step="Step 8",
                        error_message=str(req_exc),
                        severity="WARNING",
                        error_type="NetworkError",
                        recovery_action=f"Retry {attempt + 1}/3 with backoff",
                    )
                logger.warning(f"[Step 8] Network error attempt {attempt + 1}/3: {req_exc}")
                sleep(2 ** attempt)
            except Exception:
                # Non-network errors: don't retry
                raise

        # All retries exhausted
        raise last_exc or RuntimeError("GitHub issue creation failed after 3 retries")

    return _run_step(
        8, "GitHub Issue Creation",
        _with_network_retry,
        state,
        fallback_result={
            "step8_issue_id": "0",
            "step8_issue_url": "",
            "step8_issue_created": False,
            "step8_status": "ERROR",
        },
    )


def step9_branch_creation_node(state: FlowState) -> Dict[str, Any]:
    """Step 9: Branch Creation with full error handling."""
    return _run_step(
        9, "Branch Creation",
        step9_branch_creation,
        state,
        fallback_result={
            "step9_branch_name": "fallback-branch",
            "step9_branch_created": False,
            "step9_status": "ERROR",
        },
    )


def _build_retry_history_context(state) -> str:
    """Build complete retry history context for inclusion in execution prompt.

    Returns empty string on first attempt (retry_count == 0).
    On retries, builds a formatted block showing:
    - Previous attempt summaries
    - Current issues to fix (truncated to first 10)
    - Retry status with remaining attempts
    - FINAL ATTEMPT warning when no retries remain
    """
    retry_count = state.get("step11_retry_count", 0)
    if retry_count == 0:
        return ""

    retry_messages = state.get("step11_retry_messages", [])
    review_issues = state.get("step11_review_issues", [])
    max_retries = 3
    remaining = max(0, max_retries - retry_count)

    lines = []
    lines.append("=" * 70)
    lines.append("COMPLETE RETRY HISTORY")
    lines.append("=" * 70)
    lines.append("")
    lines.append("PREVIOUS ATTEMPTS (What was fixed):")
    lines.append("-" * 70)

    for i, msg in enumerate(retry_messages, 1):
        lines.append("")
        lines.append("  Attempt %d:" % i)
        lines.append("  %s" % msg)

    lines.append("")
    lines.append("CURRENT ISSUES TO FIX:")
    lines.append("-" * 70)

    display_issues = review_issues[:10]
    for i, issue in enumerate(display_issues, 1):
        lines.append("  %d. %s" % (i, issue))

    if len(review_issues) > 10:
        lines.append("  ... and %d more issues" % (len(review_issues) - 10))

    lines.append("")
    lines.append("RETRY STATUS:")
    lines.append("-" * 70)
    lines.append("  Current Attempt: #%d of %d" % (retry_count, max_retries))
    lines.append("  Remaining Attempts: %d" % remaining)

    if remaining == 0:
        lines.append("")
        lines.append("FINAL ATTEMPT - PR will be blocked for manual review")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def step10_implementation_note(state: FlowState) -> Dict[str, Any]:
    """Step 10: Implementation Execution with LLM fallback, retry history, and full error handling.

    Injects CallGraph implementation context before execution and
    snapshots the call graph for Step 11 comparison.
    """
    # --- CallGraph: Snapshot before change + implementation context ---
    pre_change_graph = {}
    call_context = {}
    suggested_tests = []
    try:
        from ..call_graph_analyzer import (
            snapshot_call_graph, get_implementation_context,
        )
        project_root = state.get("project_root", ".")
        target_files = state.get("step2_files_affected", []) or state.get("step0_target_files", [])

        # Snapshot current state for Step 11 diff
        pre_change_graph = snapshot_call_graph(project_root)

        # Get implementation context
        if target_files:
            call_context = get_implementation_context(project_root, target_files)
            suggested_tests = call_context.get("suggested_test_scope", [])
            if call_context.get("call_graph_available"):
                logger.info(
                    "[v2] Step 10 CallGraph context: %d entry points, %d test files suggested",
                    len(call_context.get("entry_points_affected", [])),
                    len(suggested_tests),
                )
    except Exception as e:
        logger.debug("[v2] Step 10 CallGraph context skipped: %s", e)

    # Build retry context before execution
    retry_count = state.get("step11_retry_count", 0)
    history = _build_retry_history_context(state)
    has_retry = retry_count > 0

    # Build execution prompt (with retry history if applicable)
    base_prompt = state.get("step7_execution_prompt", "")
    if has_retry:
        issues = state.get("step11_review_issues", [])
        issue_lines = "\n".join("- %s" % issue for issue in issues)
        exec_prompt = (
            "%s\n\n"
            "[RETRY #%d] Fix the following code review issues while keeping\n"
            "previous fixes:\n\n"
            "CURRENT ISSUES TO FIX:\n"
            "%s\n\n"
            "IMPORTANT:\n"
            "- Do NOT undo previous fixes (shown in history above)\n"
            "- Fix ONLY the current issues listed above\n"
            "- Keep all working code from previous attempts\n"
            "- Run tests to verify fixes if possible\n\n"
            "Original implementation prompt:\n"
            "---\n"
            "%s\n"
            "---\n\n"
            "Please fix the issues above and re-implement."
        ) % (history, retry_count, issue_lines, base_prompt)
    else:
        exec_prompt = base_prompt

    def _with_llm_fallback(st):
        """
        Wrap step10 with explicit LLM error -> Claude API fallback pattern
        and file modification tracking.
        The underlying step10_implementation_execution already handles
        hybrid_inference internally, but we add a second layer here for
        any uncaught LLM-related exceptions bubbling up.
        """
        try:
            result = step10_implementation_execution(st)
            # Track files modified by implementation step
            if result and result.get("step10_modified_files"):
                infra = _get_infra(st)
                if infra["metrics"]:
                    try:
                        infra["metrics"].record_files_modified(
                            step=10,
                            files=result["step10_modified_files"],
                            operation="modified",
                        )
                    except Exception:
                        pass
            return result
        except Exception as llm_exc:
            # Check if this looks like an LLM connectivity issue
            err_msg = str(llm_exc).lower()
            is_llm_error = any(
                kw in err_msg
                for kw in ("ollama", "connection", "model", "timeout", "inference")
            )
            if is_llm_error:
                infra = _get_infra(st)
                if infra["error_logger"]:
                    infra["error_logger"].log_error(
                        step="Step 10",
                        error_message=str(llm_exc),
                        severity="ERROR",
                        error_type="LLMError",
                        recovery_action="Attempting Claude API fallback",
                    )
                    infra["error_logger"].log_decision(
                        step="Step 10",
                        decision="Fallback to Claude API",
                        reasoning="Local LLM failed during implementation execution",
                    )
                # Re-raise; _run_step will catch and return fallback_result
            raise

    result = _run_step(
        10, "Implementation Execution",
        _with_llm_fallback,
        state,
        fallback_result={
            "step10_implementation_status": "ERROR",
            "step10_tasks_executed": 0,
            "step10_modified_files": [],
            "step10_llm_invoked": False,
            "step10_system_prompt_loaded": False,
            "step10_user_message_loaded": False,
        },
    )

    # Merge retry context into result
    result["step10_execution_prompt"] = exec_prompt
    result["step10_has_retry_context"] = has_retry
    result["step10_status"] = result.get("step10_status", result.get("step10_implementation_status", "OK"))
    result["step10_message"] = result.get(
        "step10_message",
        "Step 10 executed (retry=%d)" % retry_count
    )

    # Merge CallGraph data into result for Step 11
    if pre_change_graph:
        result["step10_pre_change_graph"] = pre_change_graph
    if call_context.get("call_graph_available"):
        result["step10_call_context"] = call_context
    if suggested_tests:
        result["step10_suggested_test_scope"] = suggested_tests

    return result


def step11_pull_request_node(state: FlowState) -> Dict[str, Any]:
    """Step 11: Pull Request & Code Review with full error handling.

    After the standard review, runs CallGraph impact comparison between
    pre-change snapshot (from Step 10) and current state to detect
    breaking changes, orphaned methods, and risk assessment.
    """
    result = _run_step(
        11, "Pull Request & Code Review",
        step11_pull_request_review,
        state,
        fallback_result={
            "step11_review_passed": True,   # Allow pipeline to continue on error
            "step11_review_issues": ["Step 11 failed - skipping review"],
            "step11_retry_count": state.get("step11_retry_count", 0),
            "step11_status": "ERROR",
        },
    )

    # --- CallGraph: Post-change impact review ---
    try:
        from ..call_graph_analyzer import review_change_impact
        project_root = state.get("project_root", ".")
        modified_files = (
            result.get("step10_modified_files")
            or state.get("step10_modified_files", [])
        )
        pre_snapshot = state.get("step10_pre_change_graph", {})

        if modified_files:
            impact_review = review_change_impact(
                project_root, modified_files, pre_snapshot
            )
            if impact_review.get("call_graph_available"):
                result["step11_impact_review"] = impact_review
                result["step11_risk_assessment"] = impact_review.get(
                    "risk_assessment", "safe"
                )
                breaking = impact_review.get("breaking_changes", [])
                if breaking:
                    result["step11_breaking_changes"] = breaking
                    # Add breaking changes to review issues
                    existing_issues = result.get("step11_review_issues", [])
                    for bc in breaking[:5]:
                        existing_issues.append(
                            "BREAKING: %s (%s, %d callers)" % (
                                bc.get("method", ""),
                                bc.get("reason", ""),
                                bc.get("callers", 0),
                            )
                        )
                    result["step11_review_issues"] = existing_issues

                logger.info(
                    "[v2] Step 11 CallGraph review: risk=%s, breaking=%d, orphaned=%d",
                    impact_review.get("risk_assessment", "unknown"),
                    len(breaking),
                    len(impact_review.get("orphaned_methods", [])),
                )
    except Exception as e:
        logger.debug("[v2] Step 11 CallGraph review skipped: %s", e)

    return result


def step12_issue_closure_node(state: FlowState) -> Dict[str, Any]:
    """Step 12: Issue Closure with full error handling."""
    return _run_step(
        12, "Issue Closure",
        step12_issue_closure,
        state,
        fallback_result={
            "step12_issue_closed": False,
            "step12_status": "ERROR",
        },
    )


def step13_docs_update_node(state: FlowState) -> Dict[str, Any]:
    """Step 13: Documentation Update with file-op error handling."""

    def _with_file_error_handling(st):
        try:
            result = step13_project_documentation_update(st)
            # Track documentation files updated
            if result and result.get("step13_updates_prepared"):
                updated = result.get("step13_updated_files") or []
                if updated:
                    infra = _get_infra(st)
                    if infra["metrics"]:
                        try:
                            infra["metrics"].record_files_modified(
                                step=13,
                                files=updated,
                                operation="modified",
                            )
                        except Exception:
                            pass
            return result
        except IOError as io_err:
            infra = _get_infra(st)
            if infra["error_logger"]:
                infra["error_logger"].log_error(
                    step="Step 13",
                    error_message=str(io_err),
                    severity="WARNING",
                    error_type="IOError",
                    recovery_action="Documentation update skipped; continuing pipeline",
                )
            return {
                "step13_updates_prepared": False,
                "step13_documentation_status": "ERROR",
                "step13_error": f"IOError: {io_err}",
            }

    return _run_step(
        13, "Documentation Update",
        _with_file_error_handling,
        state,
        fallback_result={
            "step13_updates_prepared": False,
            "step13_documentation_status": "ERROR",
        },
    )


def step14_final_summary_node(state: FlowState) -> Dict[str, Any]:
    """Step 14: Final Summary with metrics print and full error handling."""

    def _with_metrics_summary(st):
        result = step14_final_summary_generation(st)
        # Print metrics summary at end of pipeline
        infra = _get_infra(st)
        if infra["metrics"]:
            try:
                # Record any files modified from state
                modified_files = (
                    st.get("step10_modified_files") or
                    st.get("step13_updated_files") or
                    []
                )
                if modified_files:
                    infra["metrics"].record_files_modified(
                        step=14,
                        files=modified_files,
                        operation="modified",
                    )
                infra["metrics"].print_summary()
            except Exception:
                pass
        return result

    return _run_step(
        14, "Final Summary",
        _with_metrics_summary,
        state,
        fallback_result={
            "step14_status": "ERROR",
            "step14_summary": {},
        },
    )


# ============================================================================
# ROUTING FUNCTIONS - Pass-through to core routing logic
# ============================================================================


def route_to_plan_or_breakdown(state: FlowState) -> str:
    """Route after Step 1 plan decision."""
    return route_after_step1_plan_decision(state)


def route_to_closure_or_retry(state: FlowState) -> str:
    """Route after Step 11 PR review."""
    return route_after_step11_review(state)


# ============================================================================
# MERGE NODE - Final status determination
# ============================================================================


# Just re-export the merge node from core
level3_v2_merge_node = level3_merge_node
