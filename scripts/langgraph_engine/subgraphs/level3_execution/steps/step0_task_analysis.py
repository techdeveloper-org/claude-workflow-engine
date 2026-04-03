"""
Level 3 Execution - Step 0: Task Analysis
"""

import json
import sys

from ....flow_state import FlowState
from ..helpers import call_execution_script


def step0_task_analysis(state: FlowState) -> dict:
    """Task Analysis - Determines task type, complexity, and breakdown for Step 1.

    This is a pre-step that runs before Step 1 to gather context for the plan decision.
    Per WORKFLOW.md, this is consolidated into the execution flow (not a separate step).
    """
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L3] -> Step 0 (Task Analysis) START", file=sys.stderr)

    user_message = state.get("user_message", "")

    # Fallback: read from env var (workaround for LangGraph stripping immutable fields)
    if not user_message:
        user_message = os.environ.get("CURRENT_USER_MESSAGE", "")

    # PART A: TASK ANALYSIS
    context_data = {
        "user_message": user_message,
        "loaded_context": {
            "files_loaded": state.get("context_metadata", {}).get("files_loaded_count", 0),
            "context_percentage": state.get("context_percentage", 0),
            "context_threshold_exceeded": state.get("context_threshold_exceeded", False),
        },
        "session_info": {
            "session_chain_loaded": state.get("session_chain_loaded", False),
            "previous_sessions": len(state.get("session_history", [])),
        },
        "patterns": {
            "patterns_detected": state.get("patterns_detected", []),
        },
        "project": {
            "project_root": state.get("project_root", ""),
            "is_java_project": state.get("is_java_project", False),
        },
    }

    # SDLC Read Phase: Detect project documentation state
    doc_info = {"is_fresh_project": False, "srs_exists": False, "readme_exists": False, "claude_md_exists": False}
    try:
        from ....level3_execution.documentation_manager import Level3DocumentationManager

        doc_manager = Level3DocumentationManager(
            project_root=state.get("project_root", "."), session_dir=state.get("session_dir", "")
        )
        doc_info = doc_manager.detect_project_docs()

        # Inject doc summaries into context for better task analysis
        if not doc_info.get("is_fresh_project", False):
            doc_summaries = doc_manager.summarize_existing_docs(state.get("context_data", {}))
            if doc_summaries:
                context_data["documentation"] = doc_summaries
    except Exception:
        pass  # Doc detection failure is never fatal

    if DEBUG:
        print(f"[L3-DEBUG] State keys: {list(state.keys())[:5]}", file=sys.stderr)
        print(f"[L3] -> Step 0 user_message: {user_message[:50] if user_message else 'EMPTY'}...", file=sys.stderr)
        print(f"[L3-DEBUG] Docs found: {doc_info.get('docs_found', [])}", file=sys.stderr)

    # Run anti-hallucination enforcement before prompt generation (non-blocking)
    try:
        ah_result = call_execution_script("anti-hallucination-enforcement", ["--enforce"])
        if DEBUG and ah_result.get("status") != "SCRIPT_NOT_FOUND":
            print(f"[L3-DEBUG] Anti-hallucination: {ah_result.get('status', 'unknown')}", file=sys.stderr)
    except Exception:
        pass  # Anti-hallucination failure is never fatal

    # Run task analysis
    args = [user_message] if user_message else []
    args.append(f"--context={json.dumps(context_data)}")
    analysis_result = call_execution_script("prompt-generator", args, model_tier="fast")

    task_type = analysis_result.get("task_type", "General Task")
    complexity = analysis_result.get("complexity", 5)
    reasoning = analysis_result.get("reasoning", "")

    if DEBUG:
        print(f"[L3] -> Step 0 Analysis: task_type={task_type}, complexity={complexity}", file=sys.stderr)

    # PART B: TASK BREAKDOWN
    args = [user_message] if user_message else []
    args.extend([f"--task-type={task_type}"])
    breakdown_result = call_execution_script("task-auto-analyzer", args, model_tier="fast")

    if DEBUG:
        print(f"[L3] -> Step 0 Breakdown END: {breakdown_result.get('task_count', 1)} tasks", file=sys.stderr)

    return {
        "step0_task_type": task_type,
        "step0_complexity": complexity,
        "step0_reasoning": reasoning,
        "step0_tasks": {
            "count": breakdown_result.get("task_count", 1),
            "tasks": breakdown_result.get("tasks", []),
            "script_output": breakdown_result,
        },
        "step0_task_count": breakdown_result.get("task_count", 1),
        "is_fresh_project": doc_info.get("is_fresh_project", False),
        "step0_docs_found": doc_info,
    }
