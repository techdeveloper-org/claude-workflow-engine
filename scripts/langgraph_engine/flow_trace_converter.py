"""
FlowState to flow-trace.json converter - Ensures backward compatibility.

The new LangGraph engine produces FlowState, but downstream tools
(pre-tool-enforcer.py, monitoring dashboard) expect flow-trace.json format.

This converter transforms FlowState -> flow-trace.json with identical format
so pre-tool-enforcer.py doesn't need any changes.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .flow_state import FlowState


def convert_flow_state_to_trace(state: FlowState) -> Dict[str, Any]:
    """Convert FlowState to flow-trace.json format.

    Maps all FlowState fields to pipeline entries compatible with
    pre-tool-enforcer.py and other downstream consumers.

    Args:
        state: Completed FlowState from LangGraph execution

    Returns:
        Dict in flow-trace.json format
    """
    # Extract timing info
    timestamp = state.get("timestamp", datetime.now().isoformat())
    session_id = state.get("session_id", "SESSION-UNKNOWN")

    # Build pipeline entries from state
    pipeline = []

    # Level -1
    if state.get("level_minus1_status"):
        pipeline.append({
            "step": "LEVEL_MINUS_1",
            "name": "Auto-Fix Enforcement",
            "level": -1,
            "order": 0,
            "is_blocking": True,
            "timestamp": timestamp,
            "duration_ms": state.get("level_durations", {}).get("level_minus1", 0),
            "input": {
                "trigger": "user_prompt_received",
                "purpose": "Verify ALL systems operational before any work",
                "is_blocking": True,
            },
            "policy_output": {
                "status": state.get("level_minus1_status"),
                "unicode_check": state.get("unicode_check", False),
                "encoding_check": state.get("encoding_check", False),
                "windows_path_check": state.get("windows_path_check", False),
            },
            "decision": f"Auto-fix checks completed - {state.get('level_minus1_status')}",
            "passed_to_next": {
                "status": state.get("level_minus1_status"),
            },
        })

    # Level 1
    if state.get("level1_status"):
        pipeline.append({
            "step": "LEVEL_1_CONTEXT",
            "name": "Context Management (Level 1 Parallel)",
            "level": 1,
            "order": 1,
            "is_blocking": False,
            "timestamp": timestamp,
            "duration_ms": state.get("level_durations", {}).get("level1", 0),
            "input": {
                "purpose": "Load context, sessions, preferences, patterns in parallel",
            },
            "policy_output": {
                "context_loaded": state.get("context_loaded", False),
                "context_percentage": state.get("context_percentage", 0),
                "session_chain_loaded": state.get("session_chain_loaded", False),
                "preferences_loaded": state.get("preferences_loaded", False),
                "patterns_detected": state.get("patterns_detected", []),
            },
            "decision": f"Level 1 completed - {state.get('level1_status')}",
            "passed_to_next": {
                "context_pct": state.get("context_percentage", 0),
                "context_threshold_exceeded": state.get("context_threshold_exceeded", False),
            },
        })

    # Level 2
    if state.get("level2_status"):
        pipeline.append({
            "step": "LEVEL_2_STANDARDS",
            "name": "Rules/Standards System",
            "level": 2,
            "order": 2,
            "is_blocking": False,
            "timestamp": timestamp,
            "duration_ms": state.get("level_durations", {}).get("level2", 0),
            "input": {
                "purpose": "Load coding standards and language-specific rules",
                "is_java_project": state.get("is_java_project", False),
            },
            "policy_output": {
                "standards_loaded": state.get("standards_loaded", False),
                "standards_count": state.get("standards_count", 0),
                "java_standards_loaded": state.get("java_standards_loaded", False),
            },
            "decision": f"Standards loaded - {state.get('level2_status')}",
            "passed_to_next": {
                "standards_active": state.get("standards_count", 0),
            },
        })

    # Level 3 - All 12 steps
    level3_steps = [
        ("LEVEL_3_STEP_3_0", "Prompt Generation", "step0_prompt", state.get("step0_prompt")),
        ("LEVEL_3_STEP_3_1", "Task Breakdown", "step1_tasks", state.get("step1_tasks")),
        ("LEVEL_3_STEP_3_2", "Plan Mode Decision", "step2_plan_mode", state.get("step2_plan_mode")),
        ("LEVEL_3_STEP_3_3", "Context Read Check", "step3_context_read", state.get("step3_context_read")),
        ("LEVEL_3_STEP_3_4", "Model Selection", "step4_model", state.get("step4_model")),
        ("LEVEL_3_STEP_3_5", "Skill/Agent Selection", "step5_skill", state.get("step5_skill")),
        ("LEVEL_3_STEP_3_6", "Tool Optimization", "step6_tool_hints", state.get("step6_tool_hints")),
        ("LEVEL_3_STEP_3_7", "Auto-Recommendations", "step7_recommendations", state.get("step7_recommendations")),
        ("LEVEL_3_STEP_3_8", "Progress Tracking", "step8_progress", state.get("step8_progress")),
        ("LEVEL_3_STEP_3_9", "Git Commit Prep", "step9_commit_ready", state.get("step9_commit_ready")),
        ("LEVEL_3_STEP_3_10", "Session Save", "step10_session", state.get("step10_session")),
        ("LEVEL_3_STEP_3_11", "Failure Prevention", "failure_prevention", state.get("failure_prevention")),
    ]

    for step_num, (step_id, step_name, state_key, step_value) in enumerate(level3_steps):
        pipeline.append({
            "step": step_id,
            "name": step_name,
            "level": 3,
            "order": 3 + step_num,
            "is_blocking": False,
            "timestamp": timestamp,
            "duration_ms": state.get("level_durations", {}).get(state_key, 0),
            "input": {},
            "policy_output": {
                "result": step_value,
            },
            "decision": f"Step {step_num} executed",
            "passed_to_next": {},
        })

    # Build final trace
    trace = {
        "meta": {
            "flow_version": "5.0.0-langgraph",  # New version using LangGraph
            "script": "3-level-flow.py (LangGraph Engine)",
            "mode": "langgraph-orchestration",
            "flow_start": state.get("timestamp"),
            "flow_end": datetime.now().isoformat(),
            "duration_seconds": state.get("execution_time_ms", 0) / 1000,
            "session_id": session_id,
            "engine": "LangGraph",
        },
        "user_input": {
            "prompt": "[Generated by LangGraph flow]",
            "received_at": timestamp,
            "source": "LangGraph Engine",
        },
        "pipeline": pipeline,
        "final_decision": {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "context_pct": state.get("context_percentage", 0),
            "standards_active": state.get("standards_count", 0),
            "model_selected": state.get("step4_model", "haiku"),
            "skill_or_agent": state.get("step5_skill") or state.get("step5_agent", ""),
            "proceed": state.get("final_status") != "BLOCKED",
            "summary": f"Status={state.get('final_status')} Context={(state.get('context_percentage') or 0):.1f}%",
        },
        "work_started": state.get("final_status") != "BLOCKED",
        "status": state.get("final_status", "UNKNOWN"),
    }

    return trace


def write_flow_trace_json(state: FlowState, session_dir: Optional[Path] = None) -> Path:
    """Write flow-trace.json file from FlowState.

    Args:
        state: Completed FlowState
        session_dir: Directory to write flow-trace.json to.
                    Defaults to ~/.claude/memory/logs/sessions/{session_id}/

    Returns:
        Path to written file
    """
    if session_dir is None:
        session_id = state.get("session_id", "SESSION-UNKNOWN")
        session_dir = (
            Path.home()
            / ".claude"
            / "memory"
            / "logs"
            / "sessions"
            / session_id
        )

    session_dir.mkdir(parents=True, exist_ok=True)

    trace = convert_flow_state_to_trace(state)
    trace_file = session_dir / "flow-trace.json"

    trace_file.write_text(
        json.dumps(trace, indent=2),
        encoding="utf-8",
    )

    return trace_file


def print_flow_checkpoint(state: FlowState, verbose: bool = False) -> None:
    """Print flow checkpoint summary (same format as before).

    Args:
        state: Completed FlowState
        verbose: If True, print full details
    """
    status = state.get("final_status", "UNKNOWN")
    session_id = state.get("session_id", "SESSION-UNKNOWN")
    context_pct = state.get("context_percentage", 0)
    model = state.get("step4_model", "haiku")

    print(f"\n[FLOW CHECKPOINT]")
    print(f"  Status: {status}")
    print(f"  Session: {session_id}")
    print(f"  Context: {context_pct:.1f}%")
    print(f"  Model: {model}")

    if verbose:
        if state.get("errors"):
            print(f"  Errors ({len(state['errors'])}): {state['errors'][:2]}")
        if state.get("warnings"):
            print(f"  Warnings ({len(state['warnings'])}): {state['warnings'][:2]}")
