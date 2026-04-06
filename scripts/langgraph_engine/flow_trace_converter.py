"""
FlowState to flow-trace.json converter - Ensures backward compatibility.

The new LangGraph engine produces FlowState, but downstream tools
(pre-tool-enforcer.py, monitoring dashboard) expect flow-trace.json format.

This converter transforms FlowState -> flow-trace.json with identical format
so pre-tool-enforcer.py doesn't need any changes.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .flow_state import FlowState

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _FLOW_TRACE_MEMORY_DIR = get_claude_home() / "memory"
except ImportError:
    _FLOW_TRACE_MEMORY_DIR = Path.home() / ".claude" / "memory"


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
        pipeline.append(
            {
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
            }
        )

    # Level 1 - Session + Context (pre-tool-enforcer checks for BOTH)
    if state.get("level1_status"):
        pipeline.append(
            {
                "step": "LEVEL_1_SESSION",
                "name": "Session Init (Level 1)",
                "level": 1,
                "order": 1,
                "is_blocking": False,
                "timestamp": timestamp,
                "duration_ms": state.get("level_durations", {}).get("level1_session", 0),
                "input": {
                    "purpose": "Create session and initialize session directory",
                },
                "policy_output": {
                    "session_id": session_id,
                    "session_created": True,
                },
                "decision": f"Session created - {session_id}",
                "passed_to_next": {
                    "session_id": session_id,
                },
            }
        )
        pipeline.append(
            {
                "step": "LEVEL_1_CONTEXT",
                "name": "Context Sync (Level 1 Parallel)",
                "level": 1,
                "order": 2,
                "is_blocking": False,
                "timestamp": timestamp,
                "duration_ms": state.get("level_durations", {}).get("level1", 0),
                "input": {
                    "purpose": "Load context and calculate complexity",
                },
                "policy_output": {
                    "context_loaded": state.get("context_loaded", False),
                    "context_percentage": state.get("context_percentage", 0),
                    "complexity_score": state.get("complexity_score", 0),
                },
                "decision": f"Level 1 completed - {state.get('level1_status')}",
                "passed_to_next": {
                    "context_pct": state.get("context_percentage", 0),
                    "context_threshold_exceeded": state.get("context_threshold_exceeded", False),
                },
            }
        )

    # Level 2
    if state.get("level2_status"):
        pipeline.append(
            {
                "step": "LEVEL_2_STANDARDS",
                "name": "Standards System",
                "level": 2,
                "order": 3,
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
            }
        )

    # Level 3 - 8 active steps (Pre-0, Step 0, Steps 8-14)
    level3_steps = [
        (
            "LEVEL_3_STEP_0",
            "Task Analysis",
            "step0_task_type",
            {
                "task_type": state.get("step0_task_type"),
                "complexity": state.get("step0_complexity"),
                "reasoning": state.get("step0_reasoning"),
                "task_count": state.get("step0_task_count"),
            },
        ),
        (
            "LEVEL_3_STEP_8",
            "GitHub Issue Creation",
            "step8_status",
            {
                "issue_id": state.get("step8_issue_id"),
                "issue_created": state.get("step8_issue_created"),
                "status": state.get("step8_status"),
            },
        ),
        (
            "LEVEL_3_STEP_9",
            "Branch Creation",
            "step9_status",
            {
                "branch_name": state.get("step9_branch_name"),
                "branch_created": state.get("step9_branch_created"),
                "status": state.get("step9_status"),
            },
        ),
        (
            "LEVEL_3_STEP_10",
            "Implementation",
            "step10_status",
            {
                "implementation_status": state.get("step10_implementation_status"),
                "tasks_executed": state.get("step10_tasks_executed"),
                "modified_files": state.get("step10_modified_files"),
            },
        ),
        (
            "LEVEL_3_STEP_11",
            "Pull Request Review",
            "step11_status",
            {
                "review_passed": state.get("step11_review_passed"),
                "retry_count": state.get("step11_retry_count"),
                "status": state.get("step11_status"),
            },
        ),
        (
            "LEVEL_3_STEP_12",
            "Issue Closure",
            "step12_status",
            {
                "issue_closed": state.get("step12_issue_closed"),
                "status": state.get("step12_status"),
            },
        ),
        (
            "LEVEL_3_STEP_13",
            "Documentation Update",
            "step13_documentation_status",
            {
                "updates_prepared": state.get("step13_updates_prepared"),
                "status": state.get("step13_documentation_status"),
            },
        ),
        (
            "LEVEL_3_STEP_14",
            "Final Summary",
            "step14_status",
            {
                "status": state.get("step14_status"),
                "summary": state.get("step14_summary"),
            },
        ),
    ]

    for step_num, (step_id, step_name, state_key, step_output) in enumerate(level3_steps):
        pipeline.append(
            {
                "step": step_id,
                "name": step_name,
                "level": 3,
                "order": 4 + step_num,
                "is_blocking": False,
                "timestamp": timestamp,
                "duration_ms": state.get("level_durations", {}).get(state_key, 0),
                "input": {},
                "policy_output": step_output,
                "decision": f"Step {step_num} - {step_name}",
                "passed_to_next": {},
            }
        )

    # Build final trace
    trace = {
        "meta": {
            "flow_version": "7.5.0-langgraph",
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
            "task_type": state.get("step0_task_type", "General Task"),
            "complexity": state.get("step0_complexity", 5),
            "context_pct": state.get("context_percentage", 0),
            "standards_active": state.get("standards_count", 0),
            "model_selected": state.get("step4_model", "haiku"),
            "plan_required": False,
            "issue_id": state.get("step8_issue_id", ""),
            "branch_name": state.get("step9_branch_name", ""),
            "proceed": state.get("final_status") != "BLOCKED",
            "summary": f"Status={state.get('final_status')} Context={(state.get('context_percentage') or 0):.1f}%",
        },
        "work_started": state.get("final_status") != "BLOCKED",
        "status": state.get("final_status", "UNKNOWN"),
        "synthesis": {
            "synthesized_prompt": state.get("synthesized_prompt", ""),
            "synthesis_metadata": state.get("synthesis_metadata", {}),
            "context_optimization": {
                "workflow_memory_size_kb": state.get("workflow_memory_size_kb", 0),
                "step_optimization_stats": state.get("step_optimization_stats", {}),
            },
        },
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
        session_dir = _FLOW_TRACE_MEMORY_DIR / "logs" / "sessions" / session_id

    session_dir.mkdir(parents=True, exist_ok=True)

    trace = convert_flow_state_to_trace(state)
    trace_file = session_dir / "flow-trace.json"

    trace_file.write_text(
        json.dumps(trace, indent=2),
        encoding="utf-8",
    )

    return trace_file


def print_flow_checkpoint(state: FlowState, verbose: bool = False) -> None:
    """Print flow checkpoint summary with synthesized prompt integration.

    Args:
        state: Completed FlowState
        verbose: If True, print full details
    """
    status = state.get("final_status", "UNKNOWN")
    session_id = state.get("session_id", "SESSION-UNKNOWN")
    context_pct = state.get("context_percentage", 0)
    model = state.get("step4_model", "complex_reasoning")
    synthesized_prompt = state.get("synthesized_prompt", "")

    print("\n[FLOW CHECKPOINT]")
    print(f"  Status: {status}")
    print(f"  Session: {session_id}")
    print(f"  Context: {context_pct:.1f}%")
    print(f"  Model: {model}")

    # Save synthesized prompt to file AND print to stdout so Claude Code receives it
    if synthesized_prompt:
        try:
            synthesis_file = _FLOW_TRACE_MEMORY_DIR / "current-synthesis.txt"
            synthesis_file.parent.mkdir(parents=True, exist_ok=True)
            synthesis_file.write_text(synthesized_prompt, encoding="utf-8")
            print(f"  Synthesis: Generated ({len(synthesized_prompt)} chars)")
            print(f"  Location: {synthesis_file}")
        except Exception:
            pass

        # CRITICAL: Print the ACTUAL synthesized prompt content to stdout
        # This is what Claude Code reads as hook output and uses as context
        print("\n--- SYNTHESIZED CONTEXT (from 3-level pipeline) ---")
        print(synthesized_prompt)
        print("--- END SYNTHESIZED CONTEXT ---\n")

    # Selected skills/agents are part of orchestrator_result now
    orchestrator_result = state.get("orchestrator_result", "")
    if orchestrator_result:
        print(f"  Orchestrator: result available ({len(str(orchestrator_result))} chars)")

    if verbose:
        if state.get("errors"):
            print(f"  Errors ({len(state['errors'])}): {state['errors'][:2]}")
        if state.get("warnings"):
            print(f"  Warnings ({len(state['warnings'])}): {state['warnings'][:2]}")
