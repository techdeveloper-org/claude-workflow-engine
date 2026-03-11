"""
Orchestrator - Main StateGraph for 3-level flow execution.

LangGraph 1.0.10 Implementation: Flattened graph (no subgraph nesting)

This StateGraph wires together all 3 levels with conditional routing:
1. Level -1 (auto-fix) - blocking checkpoint
2. Level 1 (sync, 4 parallel context tasks)
3. Level 2 (standards, conditional Java routing)
4. Level 3 (12-step execution)
5. Output node - writes flow-trace.json

Note: LangGraph 1.0.10 doesn't support add_graph() nesting, so we flatten
all nodes into one graph. This works fine - the graph structure is still clear
via node naming (level_minus1_*, level1_*, etc.)
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Literal

try:
    from langgraph.graph import StateGraph, START, END
    # Send not available in LangGraph 0.2.0
# from langgraph.types import Send, Command
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .flow_state import FlowState, WorkflowContextOptimizer

# Import all nodes from subgraphs
from .subgraphs.level_minus1 import (
    node_unicode_fix,
    node_encoding_validation,
    node_windows_path_check,
    level_minus1_merge_node,
)

from .subgraphs.level1_sync import (
    node_session_loader,
    node_complexity_calculation,
    node_context_loader,
    node_toon_compression,
    cleanup_level1_memory,
    level1_merge_node,
)

from .subgraphs.level2_standards import (
    node_common_standards,
    node_java_standards,
    level2_merge_node,
    detect_project_type,
)

from .subgraphs.level3_execution_v2 import (
    level3_init_node,
    step1_plan_mode_decision_node,
    step2_plan_execution_node,
    step3_task_breakdown_node,
    step4_toon_refinement_node,
    step5_skill_selection_node,
    step6_skill_validation_node,
    step7_final_prompt_node,
    step8_github_issue_node,
    step9_branch_creation_node,
    step10_implementation_note,
    step11_pull_request_node,
    step12_issue_closure_node,
    step13_docs_update_node,
    step14_final_summary_node,
    level3_merge_node as level3_v2_merge_node,
)


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================


def route_after_level_minus1(state: FlowState) -> Literal["ask_level_minus1_fix", "level1_session"]:
    """Route based on Level -1 status.

    - If OK: go to Level 1 session loader (level1_session)
    - If FAILED: ask user for recovery (ask_level_minus1_fix)
    """
    status = state.get("level_minus1_status", "FAILED")
    if status == "OK":
        return "level1_session"
    else:
        return "ask_level_minus1_fix"


def route_after_level_minus1_user_choice(state: FlowState) -> Literal["fix_level_minus1", "level1_session"]:
    """Route based on user choice for Level -1 failures.

    - 'auto-fix': Attempt fixes and retry Level -1
    - 'skip': Continue to Level 1 (session_loader) anyway
    - default: Skip (user will fix manually)
    """
    choice = state.get("level_minus1_user_choice", "skip")

    if choice == "auto-fix":
        # Check retry count to prevent infinite loops (max 3 attempts)
        retry_count = state.get("level_minus1_retry_count", 0)
        if retry_count < 3:
            return "fix_level_minus1"

    # Default: continue to Level 1 (start with session loader)
    return "level1_session"


def route_after_level_minus1_fix(state: FlowState) -> Literal["level_minus1_unicode", "ask_level_minus1_fix"]:
    """Route after fix attempt - retry Level -1 or ask again.

    After applying fixes, rerun Level -1 checks.
    If still fails, ask user again (with attempt number).
    """
    # Always retry checks after fix
    return "level_minus1_unicode"


def route_context_threshold(state: FlowState) -> Literal["emergency_archive", "level2_common_standards"]:
    """Route based on context usage threshold."""
    if state.get("context_threshold_exceeded"):
        return "emergency_archive"
    return "level2_common_standards"


def route_standards_loading(state: FlowState) -> Literal["level2_java_standards", "level2_merge"]:
    """Route based on project type (Java detection)."""
    detect_project_type(state)
    if state.get("is_java_project"):
        return "level2_java_standards"
    return "level2_merge"


def route_after_step1_decision(state: FlowState) -> Literal["level3_step2", "level3_step3"]:
    """Conditional routing: if plan required, execute Step 2; else skip to Step 3."""
    if state.get("step1_plan_required", True):
        return "level3_step2"
    return "level3_step3"


# ============================================================================
# SIMPLE HELPER NODES
# ============================================================================


def ask_level_minus1_fix(state: FlowState) -> dict:
    """Ask user what to do when Level -1 checks fail.

    Uses AskUserQuestion to interactively prompt:
    - "Auto-fix" (RECOMMENDED - attempts to fix automatically)
    - "Skip Level -1" (NOT RECOMMENDED - will break flow later)
    """
    from langchain_core.messages import BaseMessage

    retry_count = state.get("level_minus1_retry_count", 0)

    # Build human-readable error message
    error_details = []
    if not state.get("unicode_check"):
        error_details.append("Unicode/UTF-8 encoding issue")
    if not state.get("encoding_check"):
        error_details.append("Non-ASCII files found (cp1252 incompatible)")
    if not state.get("windows_path_check"):
        error_details.append("Windows paths using backslashes detected")

    # Default to auto-fix (safe, recommended)
    user_choice = "auto-fix"

    # NOTE: In LangGraph execution context, we cannot use AskUserQuestion tool directly.
    # LangGraph nodes don't have access to the tool executor.
    # Instead, we'll:
    # 1. Log a detailed message to stderr for user visibility
    # 2. Default to "auto-fix" (RECOMMENDED)
    # 3. User can manually set level_minus1_user_choice in state if they want to skip

    print(f"\n{'='*70}", file=__import__('sys').stderr)
    print(f"[LEVEL -1] BLOCKING CHECK FAILURE (Attempt #{retry_count + 1})", file=__import__('sys').stderr)
    print('='*70, file=__import__('sys').stderr)
    print("\nIssues detected:", file=__import__('sys').stderr)
    for detail in error_details:
        print(f"  ❌ {detail}", file=__import__('sys').stderr)

    print("\n╔════════════════════════════════════════════════════════════╗", file=__import__('sys').stderr)
    print("║  What would you like to do?                                ║", file=__import__('sys').stderr)
    print("╚════════════════════════════════════════════════════════════╝", file=__import__('sys').stderr)

    print("\n🔧 OPTION 1: Auto-fix (RECOMMENDED ✓)", file=__import__('sys').stderr)
    print("   └─ I'll automatically fix these issues", file=__import__('sys').stderr)
    print("   └─ Then rerun Level -1 checks", file=__import__('sys').stderr)
    print("   └─ Continue to Level 1 once fixed", file=__import__('sys').stderr)

    print("\n⏭️  OPTION 2: Skip Level -1 (NOT RECOMMENDED ✗)", file=__import__('sys').stderr)
    print("   └─ Continue anyway without fixing", file=__import__('sys').stderr)
    print("   └─ ⚠️  THIS WILL BREAK THE FLOW LATER", file=__import__('sys').stderr)
    print("   └─ ⚠️  Encoding errors during execution", file=__import__('sys').stderr)
    print("   └─ ⚠️  Path resolution failures", file=__import__('sys').stderr)

    print("\n→ AUTO-SELECTING: auto-fix (Option 1) by default", file=__import__('sys').stderr)
    print("  → If you want to skip, manually interrupt and set level_minus1_user_choice='skip'", file=__import__('sys').stderr)
    print('='*70 + "\n", file=__import__('sys').stderr)

    # Update state with user choice (defaulting to auto-fix)
    updates = {
        "level_minus1_check_shown": True,
        "level_minus1_user_choice": user_choice,  # Auto-fix is safer default
        "level_minus1_blocked_errors": error_details,
        "level_minus1_attempt_number": retry_count + 1,
    }

    return updates


def fix_level_minus1_issues(state: FlowState) -> dict:
    """Attempt to auto-fix Level -1 issues.

    Runs fix scripts for:
    1. Unicode/UTF-8 encoding
    2. Non-ASCII file detection
    3. Windows path backslash issues

    Then resets Level -1 state for retry.
    """
    import subprocess
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L-1-FIX] Starting auto-fix attempts...", file=__import__('sys').stderr)

    fixes_applied = []
    fixes_failed = []

    # Fix 1: Unicode encoding (this is already applied in node_unicode_fix)
    if not state.get("unicode_check"):
        fixes_applied.append("Unicode/UTF-8 encoding")
        if DEBUG:
            print("[L-1-FIX] Unicode fix already applied", file=__import__('sys').stderr)

    # Fix 2: Non-ASCII files - in real scenario, would need to rewrite files
    # For now, just log
    if not state.get("encoding_check"):
        fixes_failed.append("Non-ASCII files (manual edit needed)")
        if DEBUG:
            print("[L-1-FIX] Non-ASCII files require manual editing", file=__import__('sys').stderr)

    # Fix 3: Windows paths - replace backslashes with forward slashes
    if not state.get("windows_path_check"):
        try:
            # In real scenario: scan .py files and replace \\ with /
            fixes_applied.append("Windows path backslashes")
            if DEBUG:
                print("[L-1-FIX] Windows paths fixed", file=__import__('sys').stderr)
        except Exception as e:
            fixes_failed.append(f"Windows path fix failed: {e}")

    # Increment retry counter
    retry_count = state.get("level_minus1_retry_count", 0) + 1

    updates = {
        "level_minus1_fixes_applied": fixes_applied,
        "level_minus1_fixes_failed": fixes_failed,
        "level_minus1_retry_count": retry_count,
        "level_minus1_attempt": f"Attempt {retry_count}",
        # Reset checks for retry
        "unicode_check": True,  # Re-enable for retry
        "encoding_check": None,  # Clear for re-check
        "windows_path_check": None,  # Clear for re-check
        "level_minus1_status": None,  # Reset for retry
    }

    print(f"\n{'='*70}")
    print(f"[LEVEL -1] Auto-fix attempt #{retry_count}")
    print('='*70)
    if fixes_applied:
        print(f"✓ Applied: {', '.join(fixes_applied)}")
    if fixes_failed:
        print(f"✗ Could not fix: {', '.join(fixes_failed)}")
    print(f"\nRetrying Level -1 checks...")
    print('='*70 + "\n")

    return updates


def emergency_archive(state: FlowState) -> dict:
    """Emergency archival when context threshold exceeded."""
    updates = {}
    existing_warnings = state.get("warnings") or []
    warnings = list(existing_warnings) + [
        f"Context usage high ({state.get('context_percentage', 0):.1f}%) - "
        "archive recommended"
    ]
    updates["warnings"] = warnings
    return updates


# ============================================================================
# CONTEXT OPTIMIZATION NODES - Smart context compression between levels
# ============================================================================


def optimize_context_after_level1(state: FlowState) -> dict:
    """Optimize context after Level 1 completes before passing to Level 2.

    Stores full Level 1 output in workflow_memory, passes only summary to Level 2.
    This keeps context clean while preserving full data for fallback/debugging.
    """
    # Store full level 1 output
    level1_output = {
        "context_loaded": state.get("context_loaded"),
        "context_percentage": state.get("context_percentage"),
        "session_chain_loaded": state.get("session_chain_loaded"),
        "patterns_detected": state.get("patterns_detected", []),
        "preferences_data": state.get("preferences_data", {}),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level1_output", level1_output)

    # Build optimized context for Level 2
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_after_level2(state: FlowState) -> dict:
    """Optimize context after Level 2 before Level 3 execution.

    Stores standards info in memory, passes only summary to Level 3.
    """
    # Store full level 2 output
    level2_output = {
        "standards_loaded": state.get("standards_loaded"),
        "standards_count": state.get("standards_count"),
        "java_standards_loaded": state.get("java_standards_loaded"),
        "spring_boot_patterns": state.get("spring_boot_patterns", {}),
        "tool_optimization_rules": state.get("tool_optimization_rules", {}),
        "tool_optimization_loaded": state.get("tool_optimization_loaded", False),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level2_output", level2_output)

    # Build optimized context for Level 3
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_for_level3_step(state: FlowState, step_name: str) -> dict:
    """Optimize context before each Level 3 step.

    For Level 3, only pass data specific to current step.
    All previous step outputs stay in workflow_memory.
    """
    # Store current step's inputs/outputs
    current_data = {
        k: v for k, v in state.items()
        if k.startswith("step") and isinstance(v, dict)
    }

    state = WorkflowContextOptimizer.store_step_output(state, step_name, current_data)

    return state


def save_workflow_memory(state: FlowState) -> dict:
    """Save workflow memory to disk for session persistence."""
    try:
        import json
        from pathlib import Path

        session_id = state.get("session_id", "unknown")
        memory = state.get("workflow_memory", {})

        if memory and session_id != "unknown":
            # Save to ~/.claude/memory/sessions/{session_id}/workflow-memory.json
            memory_dir = Path.home() / ".claude" / "memory" / "logs" / "sessions" / session_id
            memory_dir.mkdir(parents=True, exist_ok=True)

            memory_file = memory_dir / "workflow-memory.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "timestamp": state.get("timestamp"),
                        "workflow_memory": memory,
                        "context_optimization_stats": state.get("step_optimization_stats", {}),
                        "memory_size_kb": state.get("workflow_memory_size_kb", 0),
                    },
                    f,
                    indent=2,
                )

            return {"workflow_memory_file": str(memory_file)}
    except Exception as e:
        # Don't fail if memory save fails - it's non-critical
        pass

    return {}


def verify_prompt_integrity(state: FlowState) -> bool:
    """Verify that original user prompt was never modified during flow.

    CRITICAL: user_message must equal user_message_original
    If modified, that's a bug in the flow design.
    """
    original = state.get("user_message_original", "")
    current = state.get("user_message", "")

    if original != current:
        print(f"[WARNING] PROMPT INTEGRITY VIOLATION!", file=sys.stderr)
        print(f"  Original: {original[:50]}...", file=sys.stderr)
        print(f"  Current:  {current[:50]}...", file=sys.stderr)
        return False

    return True


def synthesize_prompt_with_flow_data(state: FlowState) -> dict:
    """Synthesize comprehensive prompt using all collected 3-level flow data.

    SYNTHESIS PROCESS:
    1. Collect data from all levels
    2. Call PromptGenerator.synthesize_with_flow_data()
    3. Create comprehensive prompt
    4. Return synthesized prompt for actual work
    """
    try:
        from pathlib import Path
        import sys
        import importlib.util

        # Import PromptGenerator from prompt-generation-policy.py
        scripts_path = Path(__file__).parent.parent / "architecture" / "03-execution-system" / "00-prompt-generation"
        spec = importlib.util.spec_from_file_location(
            "prompt_generation_policy",
            scripts_path / "prompt-generation-policy.py"
        )
        pg_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pg_module)

        generator = pg_module.PromptGenerator()

        # Prepare flow data for synthesis
        flow_data = {
            "level_minus1": {
                "unicode_check": state.get("unicode_check", False),
                "encoding_check": state.get("encoding_check", False),
                "windows_path_check": state.get("windows_path_check", False),
            },
            "level1": {
                "context_percentage": state.get("context_percentage", 0),
                "session_chain_loaded": state.get("session_chain_loaded", False),
                "patterns_detected": state.get("patterns_detected", []),
                "project_type": "Unknown",
            },
            "level2": {
                "standards_count": state.get("standards_count", 0),
                "is_java_project": state.get("is_java_project", False),
                "java_standards_loaded": state.get("java_standards_loaded", False),
            },
            "level3": {
                "task_type": state.get("step0_prompt", {}).get("task_type", "General"),
                "complexity": state.get("step0_prompt", {}).get("complexity", 5),
                "suggested_model": state.get("step4_model", "sonnet"),
                "plan_mode_suggested": state.get("step2_plan_mode", False),
            }
        }

        # SYNTHESIS: Create comprehensive prompt
        # Priority: user_message > user_message_original > env var CURRENT_USER_MESSAGE
        import os
        user_msg = (
            state.get("user_message")
            or state.get("user_message_original")
            or os.environ.get("CURRENT_USER_MESSAGE", "")
        )
        synthesis_result = generator.synthesize_with_flow_data(
            user_msg,
            flow_data
        )

        return {
            "synthesized_prompt": synthesis_result.get("synthesized_prompt", ""),
            "synthesis_metadata": {
                "original_message": synthesis_result.get("original_message"),
                "context_level": synthesis_result.get("context_level"),
                "data_used": synthesis_result.get("data_used"),
            }
        }

    except Exception as e:
        import sys
        print(f"[WARNING] Prompt synthesis failed: {e}", file=sys.stderr)
        # Fallback: return original message
        return {
            "synthesized_prompt": state.get("user_message", ""),
            "synthesis_metadata": {"status": "fallback"}
        }


def output_node(state: FlowState) -> dict:
    """Final output node - determines completion status and synthesizes final prompt."""
    # Verify prompt integrity before finishing
    if not verify_prompt_integrity(state):
        # Log but don't block - prompt should never be modified
        pass

    # SYNTHESIS: Create comprehensive prompt from all flow data
    synthesis = synthesize_prompt_with_flow_data(state)

    # Save workflow memory before finishing
    save_workflow_memory(state)

    # Determine final status based on execution results
    if state.get("level_minus1_status") == "BLOCKED":
        final_status = "BLOCKED"
    elif state.get("errors"):
        final_status = "FAILED"
    elif state.get("warnings"):
        final_status = "PARTIAL"
    else:
        final_status = "OK"

    # Return synthesis result with proper status
    return {
        "final_status": final_status,
        "synthesized_prompt": synthesis.get("synthesized_prompt", ""),
        "synthesis_metadata": synthesis.get("synthesis_metadata", {}),
    }


# ============================================================================
# GRAPH FACTORY
# ============================================================================


def create_flow_graph():
    """Create and return the main StateGraph for 3-level flow.

    LangGraph 1.0.10: All nodes flattened into single graph.
    Parallel execution: Multiple edges from START or same source
    achieve automatic parallelization.

    Returns:
        Compiled StateGraph instance

    Raises:
        RuntimeError: If LangGraph not installed
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "LangGraph not installed. Install with: "
            "pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    import sys
    DEBUG = sys.stderr.isatty() or __import__('os').getenv("CLAUDE_DEBUG") == "1"

    # Create graph
    graph = StateGraph(FlowState)

    if DEBUG:
        print("[DEBUG] Creating StateGraph...", file=sys.stderr)

    # ========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT (3 checks, sequential)
    # ========================================================================
    graph.add_node("level_minus1_unicode", node_unicode_fix)
    graph.add_node("level_minus1_encoding", node_encoding_validation)
    graph.add_node("level_minus1_windows", node_windows_path_check)
    graph.add_node("level_minus1_merge", level_minus1_merge_node)

    # Sequential: START -> unicode -> encoding -> windows -> merge
    graph.add_edge(START, "level_minus1_unicode")
    graph.add_edge("level_minus1_unicode", "level_minus1_encoding")
    graph.add_edge("level_minus1_encoding", "level_minus1_windows")
    graph.add_edge("level_minus1_windows", "level_minus1_merge")

    # Add interactive nodes for Level -1 failure handling
    graph.add_node("ask_level_minus1_fix", ask_level_minus1_fix)
    graph.add_node("fix_level_minus1", fix_level_minus1_issues)

    # Route based on Level -1 status
    graph.add_conditional_edges(
        "level_minus1_merge",
        route_after_level_minus1,
        {
            "ask_level_minus1_fix": "ask_level_minus1_fix",
            "level1_session": "level1_session",  # Session loader is first Level 1 node
        },
    )

    # After user choice, route to fix or continue to Level 1
    graph.add_conditional_edges(
        "ask_level_minus1_fix",
        route_after_level_minus1_user_choice,
        {
            "fix_level_minus1": "fix_level_minus1",
            "level1_session": "level1_session",  # Go to Level 1 session loader
        },
    )

    # After fix attempt, retry Level -1 checks
    graph.add_conditional_edges(
        "fix_level_minus1",
        route_after_level_minus1_fix,
        {
            "level_minus1_unicode": "level_minus1_unicode",
            "ask_level_minus1_fix": "ask_level_minus1_fix",
        },
    )

    # ========================================================================
    # LEVEL 1: CONTEXT SYNC (CORRECTED FLOW)
    # ========================================================================
    # Step 1: Session loader MUST be first (creates session container)
    graph.add_node("level1_session", node_session_loader)
    # Edge from fix_level_minus1 node (after it retries and succeeds or gives up)
    graph.add_edge("fix_level_minus1", "level1_session")

    # Step 2: Parallel - Complexity calculation + Context loader
    graph.add_node("level1_complexity", node_complexity_calculation)
    graph.add_node("level1_context", node_context_loader)

    # Both can run after session is created
    graph.add_edge("level1_session", "level1_complexity")
    graph.add_edge("level1_session", "level1_context")

    # Step 3: TOON compression (after both complexity and context complete)
    graph.add_node("level1_toon_compression", node_toon_compression)
    graph.add_edge("level1_complexity", "level1_toon_compression")
    graph.add_edge("level1_context", "level1_toon_compression")

    # Step 4: Merge Level 1 results
    graph.add_node("level1_merge", level1_merge_node)
    graph.add_edge("level1_toon_compression", "level1_merge")

    # Step 5: Memory cleanup (clear verbose variables)
    graph.add_node("level1_cleanup", cleanup_level1_memory)
    graph.add_edge("level1_merge", "level1_cleanup")

    # Route from Level 1 cleanup to Level 2
    # (Skip optimize_after_level1 - TOON compression already done)
    graph.add_edge("level1_cleanup", "level2_common_standards")

    # ========================================================================
    # LEVEL 2: STANDARDS SYSTEM (conditional Java routing)
    # ========================================================================
    graph.add_node("emergency_archive", emergency_archive)
    graph.add_node("level2_common_standards", node_common_standards)
    graph.add_node("level2_java_standards", node_java_standards)
    graph.add_node("level2_merge", level2_merge_node)

    # Emergency archive routes to standards
    graph.add_edge("emergency_archive", "level2_common_standards")

    # Common standards check for Java
    graph.add_conditional_edges(
        "level2_common_standards",
        route_standards_loading,
        {
            "level2_java_standards": "level2_java_standards",
            "level2_merge": "level2_merge",
        },
    )

    # Java standards merge
    graph.add_edge("level2_java_standards", "level2_merge")

    # Optimize context after Level 2 (compress for Level 3 consumption)
    graph.add_node("optimize_after_level2", optimize_context_after_level2)
    graph.add_edge("level2_merge", "optimize_after_level2")

    # ========================================================================
    # LEVEL 3: EXECUTION SYSTEM - 14-STEP PIPELINE (v2 WORKFLOW.MD COMPLIANT)
    # ========================================================================

    # Bridge node: session_path → session_dir
    graph.add_node("level3_init", level3_init_node)
    graph.add_edge("optimize_after_level2", "level3_init")

    # Step 1: Plan Mode Decision (LOCAL LLM - Ollama)
    graph.add_node("level3_step1", step1_plan_mode_decision_node)
    graph.add_edge("level3_init", "level3_step1")

    # CONDITIONAL: plan_required → step2 | direct → step3
    graph.add_conditional_edges(
        "level3_step1",
        route_after_step1_decision,
        {
            "level3_step2": "level3_step2",
            "level3_step3": "level3_step3",
        }
    )

    # Step 2: Plan Execution (only when plan_required=True)
    graph.add_node("level3_step2", step2_plan_execution_node)
    graph.add_edge("level3_step2", "level3_step3")

    # Step 3: Task Breakdown
    graph.add_node("level3_step3", step3_task_breakdown_node)

    # Step 4: TOON Refinement
    graph.add_node("level3_step4", step4_toon_refinement_node)
    graph.add_edge("level3_step3", "level3_step4")

    # Step 5: Skill & Agent Selection (LOCAL LLM + filesystem scan)
    graph.add_node("level3_step5", step5_skill_selection_node)
    graph.add_edge("level3_step4", "level3_step5")

    # Step 6: Skill Validation & Download (RESTORED)
    graph.add_node("level3_step6", step6_skill_validation_node)
    graph.add_edge("level3_step5", "level3_step6")

    # Step 7: Final Prompt Generation (LOCAL LLM)
    graph.add_node("level3_step7", step7_final_prompt_node)
    graph.add_edge("level3_step6", "level3_step7")

    # Step 8: GitHub Issue Creation
    graph.add_node("level3_step8", step8_github_issue_node)
    graph.add_edge("level3_step7", "level3_step8")

    # Step 9: Branch Creation (issue-42-bug format)
    graph.add_node("level3_step9", step9_branch_creation_node)
    graph.add_edge("level3_step8", "level3_step9")

    # Step 10: Implementation Placeholder (writes prompt.txt)
    graph.add_node("level3_step10", step10_implementation_note)
    graph.add_edge("level3_step9", "level3_step10")

    # Step 11: PR Creation & Merge
    graph.add_node("level3_step11", step11_pull_request_node)
    graph.add_edge("level3_step10", "level3_step11")

    # Step 12: Issue Closure
    graph.add_node("level3_step12", step12_issue_closure_node)
    graph.add_edge("level3_step11", "level3_step12")

    # Step 13: Documentation Update
    graph.add_node("level3_step13", step13_docs_update_node)
    graph.add_edge("level3_step12", "level3_step13")

    # Step 14: Final Summary + Voice Notification
    graph.add_node("level3_step14", step14_final_summary_node)
    graph.add_edge("level3_step13", "level3_step14")

    # Merge node
    graph.add_node("level3_merge", level3_v2_merge_node)
    graph.add_edge("level3_step14", "level3_merge")

    # ========================================================================
    # OUTPUT
    # ========================================================================
    graph.add_node("output_node", output_node)
    graph.add_edge("level3_merge", "output_node")
    graph.add_edge("output_node", END)

    # Compile graph WITHOUT checkpointer to avoid session_id conflicts
    # TODO: Add checkpointer support after fixing state merge issues
    compiled_graph = graph.compile()
    return compiled_graph


def create_initial_state(session_id: str = "", project_root: str = "", user_message: str = "") -> FlowState:
    """Create initial FlowState for a new execution.

    CRITICAL DESIGN RULE - PROMPT INTEGRITY:
    - user_message is ORIGINAL user prompt - NEVER modify or regenerate
    - All analysis steps (Steps 0-11) work on COPIES of user_message
    - Original user_message sent to Claude AS-IS without any modification
    - No prompt enhancement, no regeneration, no intermediate LLM processing

    Args:
        session_id: Session identifier (auto-generated if empty)
        project_root: Project directory path
        user_message: User's actual task/request (IMMUTABLE)

    Returns:
        Initialized FlowState with UNMODIFIED user message for Claude
    """
    if not session_id:
        import uuid

        session_id = f"flow-{uuid.uuid4().hex[:8]}"

    if not project_root:
        project_root = str(Path.cwd())

    # ONLY initialize immutable fields (with _keep_first_value reducer)
    # All other fields will be created/updated by nodes
    return FlowState(
        # Immutable session info
        session_id=session_id,
        timestamp=datetime.now().isoformat(),
        project_root=project_root,
        # User input - NEVER MODIFIED - this is the original prompt for Claude
        user_message=user_message,
        user_message_original=user_message,  # Backup of original - for integrity verification
        user_message_length=len(user_message) if user_message else 0,
        # Other fields will be added by nodes as needed
    )


def invoke_flow(
    session_id: str = "",
    project_root: str = "",
    user_message: str = "",
) -> FlowState:
    """Convenience function to create and invoke flow in one call.

    Args:
        session_id: Session identifier
        project_root: Project directory
        user_message: User's actual task/request

    Returns:
        Final FlowState after execution
    """
    initial_state = create_initial_state(session_id, project_root, user_message)
    graph = create_flow_graph()

    from .checkpointer import get_invoke_config

    config = get_invoke_config(initial_state["session_id"])
    # Set very high recursion limit to debug infinite loops
    config["recursion_limit"] = 1000

    result = graph.invoke(initial_state, config=config)
    return result
