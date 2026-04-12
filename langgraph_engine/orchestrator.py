"""
Orchestrator - Main StateGraph for 3-level flow execution.

LangGraph 1.0.10 Implementation: Flattened graph (no subgraph nesting)

This StateGraph wires together 3 levels (Level -1, Level 1, Level 3) with conditional routing:
1. Level -1 (auto-fix) - blocking checkpoint
2. Level 1 (sync, 4 parallel context tasks)
3. Level 3 (execution, 8 active steps: Pre-0, 0.0, 0.1, 0, 8-14)
4. Output node - writes flow-trace.json

Note: LangGraph 1.0.10 doesn't support add_graph() nesting, so we flatten
all nodes into one graph. This works fine - the graph structure is still clear
via node naming (level_minus1_*, level1_*, etc.)

CHANGE LOG (v1.13.0):
  Steps 1, 3, 4, 5, 6, 7 removed from Level 3 graph.
  Their outputs are now populated by step0_task_analysis_node after a single
  consolidated LLM call (orchestration template). Steps 8-14 are unchanged.
  route_after_step1_decision local function removed (step1 no longer exists).
  apply_integration_step1/2/3/4/5/6/7 removed (hooks only needed for live steps).
  route_pre_analysis updated: template fast-path routes to "level3_step8".

CHANGE LOG (v1.14.0):
  Step 0 caller scripts use claude CLI subprocess (not direct LLM API calls).
  Step 2 (plan execution) removed from pipeline -- orchestrator subprocess
  already produces a comprehensive plan. route_after_step0_to_step2_or_step8
  removed; Step 0 now routes directly to Step 8.
  Direct edge: level3_step0 -> level3_step8.
  Active step count: Pre-0, 0.0, 0.1, 0, 8, 9, [10-14] = 8 active steps.

CHANGE LOG (v1.15.0):
  TOON compression node removed from Level 1 graph.
  level1_complexity and level1_context now feed level1_merge directly (parallel).
  node_toon_compression import removed.

CHANGE LOG (v1.15.2):
  level3_merge_node removed from import and graph.
  The function body was never implemented in subgraph.py (comment stub only).
  Hook mode: level3_step9 -> level3_output (direct edge, no merge node).
  Full mode: level3_step14 -> level3_output (direct edge, no merge node).

CHANGE LOG (v1.16.0):
  Level 2 Standards Loader scripts fully removed.
  Pipeline now flows: level1_cleanup -> level3_init directly.
  Rules/policies are loaded directly from policies/ directory on disk.
  Removed imports: level2_standards, standard_selector.
  Removed local functions: route_context_threshold, route_standards_loading,
    level2_select_standards_node, emergency_archive, optimize_context_after_level2.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _ORCHESTRATOR_CLAUDE_HOME = get_claude_home()
except ImportError:
    _ORCHESTRATOR_CLAUDE_HOME = Path.home() / ".claude"

try:
    from langgraph.graph import END, START, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .checkpointer import CheckpointerManager
from .flow_state import FlowState, StepKeys, WorkflowContextOptimizer
from .level1_sync import (
    cleanup_level1_memory,
    level1_merge_node,
    node_complexity_calculation,
    node_context_loader,
    node_session_loader,
)
from .level3_execution.subgraph import (
    level3_init_node,
    orchestration_pre_analysis_node,
    route_pre_analysis,
    step0_0_project_context_node,
    step0_1_initial_callgraph_node,
    step0_task_analysis_node,
    step8_github_issue_node,
    step9_branch_creation_node,
    step10_implementation_note,
    step11_pull_request_node,
    step12_issue_closure_node,
    step13_docs_update_node,
    step14_final_summary_node,
)
from .level_minus1 import (
    ask_level_minus1_fix,
    fix_level_minus1_issues,
    level_minus1_merge_node,
    node_encoding_validation,
    node_unicode_fix,
    node_windows_path_check,
)

# Level -1 routing functions (canonical definitions live in routing/)
from .routing import route_after_level_minus1, route_after_level_minus1_user_choice
from .standards_integration import apply_standards_at_step

# REMOVED (v1.14.0): route_after_step0_to_step2_or_step8 -- Step 2 removed from pipeline.
#   Step 0 now routes directly to Step 8.


def route_after_step11_review(state: FlowState) -> Literal["level3_step12", "level3_step11_retry"]:
    """Conditional routing after PR review: if failed and retries < 3, retry; else continue to closure."""
    review_passed = state.get(StepKeys.REVIEW_PASSED, False)
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)

    if review_passed or retry_count >= 3:
        return "level3_step12"
    else:
        # Route to retry node (which will increment count via proper state return)
        return "level3_step11_retry"


def step11_retry_increment_node(state: FlowState) -> dict:
    """Increment retry count before re-routing to Step 10.

    State mutations must happen in nodes, not routing functions (LangGraph anti-pattern).
    """
    retry_count = state.get(StepKeys.RETRY_COUNT, 0)
    return {StepKeys.RETRY_COUNT: retry_count + 1}


# ============================================================================
# CONTEXT OPTIMIZATION NODES - Smart context compression between levels
# ============================================================================


def optimize_context_after_level1(state: FlowState) -> dict:
    """Optimize context after Level 1 completes before passing to Level 3.

    Stores full Level 1 output in workflow_memory, passes only summary to Level 3.
    This keeps context clean while preserving full data for fallback/debugging.
    """
    # Store full level 1 output
    level1_output = {
        StepKeys.CONTEXT_LOADED: state.get(StepKeys.CONTEXT_LOADED),
        StepKeys.CONTEXT_PERCENTAGE: state.get(StepKeys.CONTEXT_PERCENTAGE),
        StepKeys.SESSION_CHAIN_LOADED: state.get(StepKeys.SESSION_CHAIN_LOADED),
        StepKeys.PATTERNS_DETECTED: state.get(StepKeys.PATTERNS_DETECTED, []),
        StepKeys.PREFERENCES_DATA: state.get(StepKeys.PREFERENCES_DATA, {}),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level1_output", level1_output)

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
    current_data = {k: v for k, v in state.items() if k.startswith("step") and isinstance(v, dict)}

    state = WorkflowContextOptimizer.store_step_output(state, step_name, current_data)

    return state


def save_workflow_memory(state: FlowState) -> dict:
    """Save workflow memory to disk for session persistence."""
    try:
        import json

        session_id = state.get(StepKeys.SESSION_ID, "unknown")
        memory = state.get(StepKeys.WORKFLOW_MEMORY, {})

        if memory and session_id != "unknown":
            # Save to ~/.claude/memory/sessions/{session_id}/workflow-memory.json
            memory_dir = _ORCHESTRATOR_CLAUDE_HOME / "memory" / "logs" / "sessions" / session_id
            memory_dir.mkdir(parents=True, exist_ok=True)

            memory_file = memory_dir / "workflow-memory.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "timestamp": state.get(StepKeys.TIMESTAMP),
                        "workflow_memory": memory,
                        "context_optimization_stats": state.get(StepKeys.STEP_OPTIMIZATION_STATS, {}),
                        "memory_size_kb": state.get(StepKeys.WORKFLOW_MEMORY_SIZE_KB, 0),
                    },
                    f,
                    indent=2,
                )

            return {"workflow_memory_file": str(memory_file)}
    except Exception:
        # Don't fail if memory save fails - it's non-critical
        pass

    return {}


# REMOVED (v1.13.0): apply_integration_step1 -- Step 1 no longer in graph
# REMOVED (v1.14.0): apply_integration_step2 -- Step 2 removed from pipeline
# REMOVED (v1.13.0): apply_integration_step3 -- Step 3 no longer in graph
# REMOVED (v1.13.0): apply_integration_step4 -- Step 4 no longer in graph
# REMOVED (v1.13.0): apply_integration_step5 -- Step 5 no longer in graph
# REMOVED (v1.13.0): apply_integration_step6 -- Step 6 no longer in graph
# REMOVED (v1.13.0): apply_integration_step7 -- Step 7 no longer in graph
# REMOVED (v1.16.0): level2_select_standards_node -- Level 2 fully removed
# REMOVED (v1.16.0): emergency_archive -- Level 2 node removed
# REMOVED (v1.16.0): optimize_context_after_level2 -- Level 2 context node removed


def apply_integration_step10(state: FlowState) -> dict:
    """Apply standards integration point at Step 10 (code review)."""
    updated = apply_standards_at_step(10, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step13(state: FlowState) -> dict:
    """Apply standards integration point at Step 13 (documentation)."""
    updated = apply_standards_at_step(13, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def verify_prompt_integrity(state: FlowState) -> bool:
    """Verify that original user prompt was never modified during flow.

    CRITICAL: user_message must equal user_message_original
    If modified, that's a bug in the flow design.
    """
    original = state.get(StepKeys.USER_MESSAGE_ORIGINAL, "")
    current = state.get(StepKeys.USER_MESSAGE, "")

    if original != current:
        print("[WARNING] PROMPT INTEGRITY VIOLATION!", file=sys.stderr)
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
        import importlib.util
        import sys
        from pathlib import Path

        # Import PromptGenerator from prompt-generation-policy.py
        scripts_path = (
            Path(__file__).parent.parent / "scripts" / "architecture" / "03-execution-system" / "00-prompt-generation"
        )
        spec = importlib.util.spec_from_file_location(
            "prompt_generation_policy", scripts_path / "prompt-generation-policy.py"
        )
        pg_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pg_module)

        generator = pg_module.PromptGenerator()

        # Prepare flow data for synthesis - use ACTUAL pipeline results
        # Collect validated tasks for TodoList
        validated_tasks = state.get(StepKeys.TASKS_VALIDATED, [])
        raw_tasks = state.get(StepKeys.TASKS, {}).get("tasks", [])
        all_tasks = validated_tasks if validated_tasks else raw_tasks

        # Collect plan phases
        plan_exec = state.get(StepKeys.PLAN_EXECUTION, {})
        plan_phases = plan_exec.get("phases", []) if isinstance(plan_exec, dict) else []

        flow_data = {
            "level_minus1": {
                "unicode_check": state.get(StepKeys.UNICODE_CHECK, False),
                "encoding_check": state.get(StepKeys.ENCODING_CHECK, False),
                "windows_path_check": state.get(StepKeys.WINDOWS_PATH_CHECK, False),
            },
            "level1": {
                "context_percentage": state.get(StepKeys.CONTEXT_PERCENTAGE, 0),
                "session_chain_loaded": state.get(StepKeys.SESSION_CHAIN_LOADED, False),
                "patterns_detected": state.get(StepKeys.PATTERNS_DETECTED, []),
                "project_type": state.get(StepKeys.DETECTED_FRAMEWORK, "Unknown"),
            },
            "level2": {
                "standards_count": state.get(StepKeys.STANDARDS_COUNT, 0),
                "is_java_project": state.get(StepKeys.IS_JAVA_PROJECT, False),
                "java_standards_loaded": state.get(StepKeys.JAVA_STANDARDS_LOADED, False),
            },
            "level3": {
                "task_type": state.get(StepKeys.TASK_TYPE, "General"),
                "complexity": state.get(StepKeys.COMPLEXITY, 5),
                "suggested_model": state.get(StepKeys.SELECTED_MODEL, "complex_reasoning"),
                "plan_mode_suggested": state.get(StepKeys.PLAN_REQUIRED, False),
                "reasoning": state.get(StepKeys.REASONING, ""),
                "tasks": all_tasks,
                "task_count": len(all_tasks),
                "plan_phases": plan_phases,
                "selected_skill": state.get(StepKeys.SKILL, ""),
                "selected_agent": state.get(StepKeys.AGENT, ""),
                "selected_skills": state.get(StepKeys.SKILLS, []),
                "selected_agents": state.get(StepKeys.AGENTS, []),
                "skill_definition": state.get(StepKeys.SKILL_DEFINITION, ""),
                "agent_definition": state.get(StepKeys.AGENT_DEFINITION, ""),
            },
        }

        # SYNTHESIS: Create comprehensive prompt
        # Priority: user_message > user_message_original > env var CURRENT_USER_MESSAGE
        import os

        user_msg = (
            state.get(StepKeys.USER_MESSAGE)
            or state.get(StepKeys.USER_MESSAGE_ORIGINAL)
            or os.environ.get("CURRENT_USER_MESSAGE", "")
        )
        synthesis_result = generator.synthesize_with_flow_data(user_msg, flow_data)

        return {
            "synthesized_prompt": synthesis_result.get("synthesized_prompt", ""),
            "synthesis_metadata": {
                "original_message": synthesis_result.get("original_message"),
                "context_level": synthesis_result.get("context_level"),
                "data_used": synthesis_result.get("data_used"),
            },
        }

    except Exception as e:
        import sys

        print(f"[WARNING] Prompt synthesis failed: {e}", file=sys.stderr)
        # Fallback: return original message
        return {
            "synthesized_prompt": state.get(StepKeys.USER_MESSAGE, ""),
            "synthesis_metadata": {"status": "fallback"},
        }


def output_node(state: FlowState) -> dict:
    """Final output node - determines completion status and synthesizes final prompt."""
    # Verify prompt integrity before finishing
    if not verify_prompt_integrity(state):
        # Log but don't block - prompt should never be modified
        pass

    # Write session-start voice flag so Stop hook speaks a greeting
    # Use LEGACY flag (no PID) because pipeline runs in a separate process
    # from Claude Code. Stop-notifier's _resolve_flag checks PID first, then legacy.
    try:
        flag_dir = _ORCHESTRATOR_CLAUDE_HOME
        start_flag = flag_dir / ".session-start-voice"
        if not start_flag.exists():
            task_type = state.get(StepKeys.TASK_TYPE, "task")
            complexity = state.get(StepKeys.COMPLEXITY, 5)
            skill = state.get(StepKeys.SKILL, "")
            msg = f"Starting {task_type} task, complexity {complexity} out of 10."
            if skill:
                msg += f" Using {skill} skill."
            start_flag.write_text(msg, encoding="utf-8")
    except Exception:
        pass

    # SYNTHESIS: Create comprehensive prompt from all flow data
    synthesis = synthesize_prompt_with_flow_data(state)

    # Save workflow memory before finishing
    save_workflow_memory(state)

    # Determine final status based on actual step results (not just errors list)
    if state.get(StepKeys.LEVEL_MINUS1_STATUS) == "BLOCKED":
        final_status = "BLOCKED"
    else:
        step_failures = []
        for key, val in state.items():
            if key.endswith("_status") and isinstance(val, str) and val == "ERROR":
                step_failures.append(key)
        if step_failures:
            final_status = "FAILED"
        elif state.get(StepKeys.WARNINGS):
            final_status = "PARTIAL"
        else:
            final_status = "OK"

    # Save detailed pipeline execution log to session folder
    _save_pipeline_execution_log(state, final_status)

    # In hook_mode, Step 14 doesn't run. Save a quick summary anyway.
    if not state.get(StepKeys.SUMMARY_SAVED):
        session_dir = state.get(StepKeys.SESSION_DIR) or state.get(StepKeys.SESSION_PATH, "")
        if session_dir:
            try:
                from datetime import datetime

                quick_summary = (
                    f"Pipeline: {final_status} | "
                    f"Task: {state.get(StepKeys.TASK_TYPE, '?')} | "
                    f"Complexity: {state.get(StepKeys.COMPLEXITY, '?')}/10 | "
                    f"Skill: {state.get(StepKeys.SKILL, 'none')} | "
                    f"Agent: {state.get(StepKeys.AGENT, 'none')} | "
                    f"Framework: {state.get(StepKeys.DETECTED_FRAMEWORK, '?')} | "
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
                summary_file = Path(session_dir) / "execution-summary.txt"
                summary_file.write_text(quick_summary, encoding="utf-8")
            except Exception:
                pass

    # SESSION ACCUMULATE - Record this request's data via MCP session tools
    try:
        _src_mcp_dir = Path(__file__).resolve().parent.parent / "src" / "mcp"
        if str(_src_mcp_dir) not in sys.path:
            sys.path.insert(0, str(_src_mcp_dir))
        from session_hooks import accumulate_request

        accumulate_request(
            session_id=state.get(StepKeys.SESSION_ID, ""),
            prompt=state.get(StepKeys.USER_MESSAGE, "")[:300],
            task_type=state.get(StepKeys.TASK_TYPE, ""),
            skill=state.get(StepKeys.SKILL, ""),
            complexity=int(state.get(StepKeys.COMPLEXITY, 0)),
            model=state.get(StepKeys.SELECTED_MODEL, ""),
            cwd=state.get(StepKeys.PROJECT_ROOT, ""),
            plan_mode=bool(state.get(StepKeys.PLAN_REQUIRED)),
            context_pct=int(state.get("context_pct", 0)),
            supplementary_skills=",".join(state.get(StepKeys.SKILLS, []) or []),
        )
    except Exception:
        pass  # Accumulation is non-blocking, never fail the pipeline

    # Return synthesis result with proper status
    return {
        "final_status": final_status,
        "synthesized_prompt": synthesis.get("synthesized_prompt", ""),
        "synthesis_metadata": synthesis.get("synthesis_metadata", {}),
    }


def _save_pipeline_execution_log(state: FlowState, final_status: str) -> None:
    """Save a detailed pipeline execution log to session folder.

    Creates a human-readable execution-log.md in the session directory showing:
    - Each step's status, duration, decisions
    - What came in, what went out
    - Total pipeline timing
    - Skills/agents selected
    """
    from datetime import datetime

    session_dir = state.get(StepKeys.SESSION_DIR) or state.get(StepKeys.SESSION_PATH, "")
    if not session_dir:
        return

    try:
        log_lines = []
        log_lines.append("# Pipeline Execution Log")
        log_lines.append(f"\n**Session**: {state.get(StepKeys.SESSION_ID, 'unknown')}")
        log_lines.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"**Project**: {state.get(StepKeys.PROJECT_ROOT, '.')}")
        log_lines.append(f"**Final Status**: {final_status}")
        log_lines.append(f"**Framework**: {state.get(StepKeys.DETECTED_FRAMEWORK, 'unknown')}")
        log_lines.append("")

        # Level -1
        log_lines.append("## Level -1: Auto-Fix")
        log_lines.append(f"- Unicode: {'PASS' if state.get(StepKeys.UNICODE_CHECK) else 'FAIL'}")
        log_lines.append(f"- Encoding: {'PASS' if state.get(StepKeys.ENCODING_CHECK) else 'FAIL'}")
        log_lines.append(f"- Paths: {'PASS' if state.get(StepKeys.WINDOWS_PATH_CHECK) else 'FAIL'}")
        log_lines.append(f"- Status: {state.get(StepKeys.LEVEL_MINUS1_STATUS, 'unknown')}")
        log_lines.append("")

        # Level 1
        log_lines.append("## Level 1: Context Sync")
        log_lines.append(f"- Session: {state.get(StepKeys.SESSION_ID, 'none')}")
        log_lines.append(f"- Complexity: {state.get(StepKeys.COMPLEXITY_SCORE, '?')}/10")
        graph_score = state.get(StepKeys.GRAPH_COMPLEXITY_SCORE)
        if graph_score:
            log_lines.append(f"- Graph Complexity: {graph_score}/25")
            combined = state.get(StepKeys.COMBINED_COMPLEXITY_SCORE)
            if combined:
                log_lines.append(f"- Combined Score: {combined}/25")
        log_lines.append(f"- Context Files: {state.get(StepKeys.FILES_LOADED_COUNT, 0)}")
        log_lines.append(f"- Cache Hit: {state.get(StepKeys.CONTEXT_CACHE_HIT, False)}")
        log_lines.append("")

        # Level 2 (removed v1.16.0 -- log retained for historical visibility; fields will be empty)
        log_lines.append("## Level 2: Standards (removed v1.16.0)")
        log_lines.append(f"- Standards Loaded: {state.get(StepKeys.STANDARDS_COUNT, 0)}")
        log_lines.append(f"- Framework Detected: {state.get(StepKeys.DETECTED_FRAMEWORK, 'unknown')}")
        log_lines.append(f"- MCP Discovered: {state.get(StepKeys.MCP_DISCOVERED_COUNT, 0)}")
        log_lines.append(f"- Tool Rules: {'Loaded' if state.get(StepKeys.TOOL_OPTIMIZATION_LOADED) else 'Missing'}")
        log_lines.append(f"- Status: {state.get(StepKeys.LEVEL2_STATUS, 'n/a (removed)')}")
        log_lines.append("")

        # Level 3 Steps (v1.14.0: Steps 1-7 removed; Step 0 routes directly to Step 8)
        log_lines.append("## Level 3: Execution Steps")
        log_lines.append("")
        log_lines.append("| Step | Name | Status | Duration | Details |")
        log_lines.append("|------|------|--------|----------|---------|")

        step_info = [
            (0, "Task Analysis + Template", "step0_task_type", "step0_complexity"),
            (8, "GitHub Issue Creation", "step8_status", "step8_issue_url"),
            (9, "Branch Creation", "step9_status", "step9_branch_name"),
            (10, "Implementation", "step10_implementation_status", "step10_llm_invoked"),
            (11, "PR & Code Review", "step11_status", "step11_pr_url"),
            (12, "Issue Closure", "step12_status", "step12_issue_closed"),
            (13, "Documentation", "step13_documentation_status", "step13_update_count"),
            (14, "Final Summary", "step14_status", "step14_voice_sent"),
        ]

        for step_num, name, status_key, detail_key in step_info:
            time_key = f"step{step_num}_execution_time_ms"
            duration_ms = state.get(time_key, 0)
            duration_str = f"{duration_ms:.0f}ms" if duration_ms else "-"

            status_val = state.get(status_key, "")
            detail_val = state.get(detail_key, "")

            # Format detail value
            if isinstance(detail_val, (list, dict)):
                detail_str = f"{len(detail_val)} items" if isinstance(detail_val, list) else f"{len(detail_val)} keys"
            elif isinstance(detail_val, bool):
                detail_str = "Yes" if detail_val else "No"
            elif detail_val is not None:
                detail_str = str(detail_val)[:60]
            else:
                detail_str = "-"

            status_str = str(status_val)[:30] if status_val else "-"
            log_lines.append(f"| {step_num:2d} | {name} | {status_str} | {duration_str} | {detail_str} |")

        log_lines.append("")

        # Selected resources
        log_lines.append("## Selected Resources")
        skills = state.get(StepKeys.SKILLS) or []
        skill = state.get(StepKeys.SKILL, "")
        if skill and skill not in skills:
            skills = [skill] + skills
        agents = state.get(StepKeys.AGENTS) or []
        agent = state.get(StepKeys.AGENT, "")
        if agent and agent not in agents:
            agents = [agent] + agents

        if skills:
            log_lines.append(f"- **Skills**: {', '.join(skills)}")
        if agents:
            log_lines.append(f"- **Agents**: {', '.join(agents)}")
        log_lines.append("")

        # Errors
        errors = state.get(StepKeys.ERRORS) or []
        if errors:
            log_lines.append("## Errors")
            for err in errors[:10]:
                log_lines.append(f"- {err}")
            log_lines.append("")

        # Write to session folder
        log_path = Path(session_dir) / "execution-log.md"
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

    except Exception:
        pass  # Never crash on logging


# ============================================================================
# GRAPH FACTORY
# ============================================================================


def create_flow_graph(hook_mode: bool = False):
    """Create and return the main StateGraph for 3-level flow.

    LangGraph 1.0.10: All nodes flattened into single graph.
    Parallel execution: Multiple edges from START or same source
    achieve automatic parallelization.

    Args:
        hook_mode: If True, skip Steps 10-14 (GitHub workflow) for fast
                   UserPromptSubmit hook execution. Only runs Levels -1/1
                   and Steps 0/8/9 (analysis + prompt generation + issue + branch).
                   Steps 10-14 can be triggered separately after Claude has context.

    Returns:
        Compiled StateGraph instance

    Raises:
        RuntimeError: If LangGraph not installed

    CHANGE LOG (v1.13.0):
        Steps 1, 3, 4, 5, 6, 7 removed from graph.
        Step 0 now does consolidated LLM call (orchestration template) and
        populates all migration fields previously written by steps 1-7.
        Step 2 (plan execution) removed from pipeline (v1.14.0).
        route_pre_analysis targets updated to "level3_step8" for both fast paths.
        Standards hooks for removed steps are no longer registered.

    CHANGE LOG (v1.15.0):
        TOON compression node removed from Level 1 graph.
        level1_complexity and level1_context now feed level1_merge directly.

    CHANGE LOG (v1.15.2):
        level3_merge node removed (level3_merge_node was a comment stub, never
        implemented). Hook mode: level3_step9 -> level3_output directly.
        Full mode: level3_step14 -> level3_output directly.

    CHANGE LOG (v1.16.0):
        Level 2 Standards Loader nodes fully removed from graph.
        Direct bridge added: level1_cleanup -> level3_init.
        Removed nodes: level2_emergency_archive, level2_common_standards,
          level2_java_standards, level2_tool_optimization, level2_mcp_discovery,
          level2_merge, level2_select_standards, level2_optimize_context.
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "LangGraph not installed. Install with: " "pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    import sys

    DEBUG = sys.stderr.isatty() or __import__("os").getenv("CLAUDE_DEBUG") == "1"

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

    # After fix attempt, always retry Level -1 checks from start
    graph.add_edge("fix_level_minus1", "level_minus1_unicode")

    # ========================================================================
    # LEVEL 1: CONTEXT SYNC (CORRECTED FLOW)
    # ========================================================================
    # Step 1: Session loader MUST be first (creates session container)
    graph.add_node("level1_session", node_session_loader)

    # Step 2: Parallel - Complexity calculation + Context loader
    graph.add_node("level1_complexity", node_complexity_calculation)
    graph.add_node("level1_context", node_context_loader)

    # Both can run after session is created
    graph.add_edge("level1_session", "level1_complexity")
    graph.add_edge("level1_session", "level1_context")

    # Step 3: Merge Level 1 results (complexity + context both feed merge directly)
    graph.add_node("level1_merge", level1_merge_node)
    graph.add_edge("level1_complexity", "level1_merge")
    graph.add_edge("level1_context", "level1_merge")

    # Step 4: Memory cleanup (clear verbose variables)
    graph.add_node("level1_cleanup", cleanup_level1_memory)
    graph.add_edge("level1_merge", "level1_cleanup")

    # ========================================================================
    # LEVEL 3: EXECUTION SYSTEM - 9-STEP PIPELINE (v1.13.0 CONSOLIDATED)
    #
    # Active steps: Pre-0, 0.0, 0.1, 0, 8, 9, [10-14 full mode]
    # Steps 1, 3, 4, 5, 6, 7 removed -- outputs merged into Step 0 template call.
    # Level 2 removed (v1.16.0) -- direct bridge: level1_cleanup -> level3_init
    # ========================================================================

    # Bridge node: session_path -> session_dir
    # Direct connection: Level 1 cleanup -> Level 3 init (Level 2 removed in v1.16.0)
    graph.add_node("level3_init", level3_init_node)
    graph.add_edge("level1_cleanup", "level3_init")

    # Pre-analysis gate: call graph scan
    # Template fast-path (--orchestration-template): jumps directly to level3_step8
    # Normal path: falls through to level3_step0_0 (pre-flight flow)
    graph.add_node("level3_pre_analysis", orchestration_pre_analysis_node)
    graph.add_edge("level3_init", "level3_pre_analysis")
    graph.add_conditional_edges(
        "level3_pre_analysis",
        route_pre_analysis,
        {
            "level3_step0_0": "level3_step0_0",
            "level3_step8": "level3_step8",
        },
    )

    # Step 0.0: Pre-flight - Project Context (README, CHANGELOG, etc.)
    graph.add_node("level3_step0_0", step0_0_project_context_node)

    # Step 0.1: Pre-flight - Initial CallGraph Snapshot (baseline for Step 11 diff)
    graph.add_node("level3_step0_1", step0_1_initial_callgraph_node)
    graph.add_edge("level3_step0_0", "level3_step0_1")

    # Step 0: Task Analysis + Orchestration (2 claude CLI subprocess calls).
    # Populates all migration fields for steps 8-14 (previously written by 1/3/4/5/6/7).
    graph.add_node("level3_step0", step0_task_analysis_node)
    graph.add_edge("level3_step0_1", "level3_step0")

    # Direct edge: Step 0 -> Step 8 (Step 2 removed in v1.14.0)
    graph.add_edge("level3_step0", "level3_step8")

    # ========================================================================
    # STEPS 8-9: Issue + Branch Creation (runs in BOTH hook and full mode)
    # These create the GitHub issue and feature branch BEFORE Claude works
    # ========================================================================

    # Step 8: GitHub Issue Creation
    graph.add_node("level3_step8", step8_github_issue_node)

    # Step 9: Branch Creation (issue-42-bug format)
    graph.add_node("level3_step9", step9_branch_creation_node)
    graph.add_edge("level3_step8", "level3_step9")

    # ========================================================================
    # HOOK MODE: After Steps 8-9, go to output
    # Step 10 = Claude Code itself (the LLM reading this prompt and working)
    # Steps 11-14 = run in Stop hook after Claude finishes working
    # v1.15.2: level3_merge removed (was never implemented); direct edge used.
    # ========================================================================
    if hook_mode:
        graph.add_node("level3_output", output_node)
        graph.add_edge("level3_step9", "level3_output")
        graph.add_edge("level3_output", END)

        try:
            checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
            compiled_graph = graph.compile(checkpointer=checkpointer)
        except Exception:
            compiled_graph = graph.compile()
        return compiled_graph

    # ========================================================================
    # FULL MODE: Steps 10-14 (implementation + PR + merge + close)
    # Only used when running pipeline standalone (not as hook)
    # ========================================================================

    # Step 10: Implementation (in full mode)
    graph.add_node("level3_step10", step10_implementation_note)
    graph.add_edge("level3_step9", "level3_step10")

    # Standards integration hook: Step 10 (code review) - builds compliance checklist
    # Runs after step10, before step11, so PR review has the checklist available
    graph.add_node("level3_standards_hook_step10", apply_integration_step10)
    graph.add_edge("level3_step10", "level3_standards_hook_step10")

    # Step 11: PR Creation & Merge
    graph.add_node("level3_step11", step11_pull_request_node)
    graph.add_edge("level3_standards_hook_step10", "level3_step11")

    # Step 11 -> Conditional Routing (retry loop or continue to closure)
    # Retry goes through increment node first (state mutations only in nodes)
    graph.add_node("level3_step11_retry", step11_retry_increment_node)
    graph.add_edge("level3_step11_retry", "level3_step10")

    graph.add_conditional_edges(
        "level3_step11",
        route_after_step11_review,
        {
            "level3_step12": "level3_step12",  # Review passed or max retries reached
            "level3_step11_retry": "level3_step11_retry",  # Review failed, increment then retry
        },
    )

    # Step 12: Issue Closure
    graph.add_node("level3_step12", step12_issue_closure_node)

    # Step 13: Documentation Update
    graph.add_node("level3_step13", step13_docs_update_node)
    graph.add_edge("level3_step12", "level3_step13")

    # Standards integration hook: Step 13 - documentation requirements from standards
    graph.add_node("level3_standards_hook_step13", apply_integration_step13)
    graph.add_edge("level3_step13", "level3_standards_hook_step13")

    # Step 14: Final Summary + Voice Notification
    graph.add_node("level3_step14", step14_final_summary_node)
    graph.add_edge("level3_standards_hook_step13", "level3_step14")

    # ========================================================================
    # OUTPUT
    # v1.15.2: level3_merge removed (was never implemented); direct edge used.
    # ========================================================================
    graph.add_node("level3_output", output_node)
    graph.add_edge("level3_step14", "level3_output")
    graph.add_edge("level3_output", END)

    # Compile graph with SqliteSaver checkpointer for state persistence
    # Enables resume from any step if pipeline is interrupted
    try:
        checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
        compiled_graph = graph.compile(checkpointer=checkpointer)
    except Exception:
        # Fallback to no checkpointer if SQLite setup fails
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
    # **CRITICAL FIX**: Set project_root FIRST (before any immutable field is created)
    # project_root is Annotated[_keep_first_value] so once set, it can't change
    # We must set it to the correct value BEFORE creating the state
    import os
    import sys

    print(f"[CREATE_INITIAL_STATE] Input project_root: '{project_root}'", file=sys.stderr)
    if not project_root:
        # Use cwd from hook event or actual cwd - NOT hardcoded path
        project_root = os.environ.get("CLAUDE_CWD", str(Path.cwd()))
        print(f"[CREATE_INITIAL_STATE] Set project_root from cwd: {project_root}", file=sys.stderr)
    print(f"[CREATE_INITIAL_STATE] Final project_root before state creation: {project_root}", file=sys.stderr)

    # session_id is set by node_session_loader (Level 1) - NOT here
    # It's immutable (_keep_first_value), so if set here it blocks Level 1 from setting it
    # Only set here if explicitly passed (e.g., from CLI --session-id=)

    # ONLY initialize immutable fields (with _keep_first_value reducer)
    # All other fields will be created/updated by nodes
    initial_state = FlowState(
        # Immutable session info - session_id left for node_session_loader unless provided
        **({"session_id": session_id} if session_id else {}),
        timestamp=datetime.now().isoformat(),
        project_root=project_root,
        # User input - NEVER MODIFIED - this is the original prompt for Claude
        user_message=user_message,
        user_message_original=user_message,  # Backup of original - for integrity verification
        user_message_length=len(user_message) if user_message else 0,
        # Other fields will be added by nodes as needed
    )

    # Verify project_root was set correctly
    print(
        f"[CREATE_INITIAL_STATE] After FlowState creation: project_root='{initial_state.get('project_root', 'MISSING')}'",
        file=sys.stderr,
    )

    return initial_state


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


def resume_flow(
    session_id: str,
    checkpoint_id: Optional[str] = None,
) -> bool:
    """
    Resume an interrupted pipeline execution from a saved checkpoint.

    Loads the checkpoint state, installs signal handlers, and replays
    remaining steps (step_number+1 through 14) using the LangGraph graph.

    Usage:
        # Resume from last checkpoint
        resume_flow(session_id="flow-abc12345")

        # Resume from specific step checkpoint
        resume_flow(session_id="flow-abc12345", checkpoint_id="flow-abc12345:step-05")

    Args:
        session_id:    Session to resume.
        checkpoint_id: Optional specific checkpoint ID.  When None, the most
                       recent checkpoint for the session is used.

    Returns:
        True if resumed successfully.
    """
    from .recovery_handler import resume_from_checkpoint

    print(f"[Resume] Loading checkpoint for session: {session_id}", file=sys.stderr)
    if checkpoint_id:
        print(f"[Resume] Using checkpoint: {checkpoint_id}", file=sys.stderr)

    # RecoveryHandler.resume_session() handles loading + replaying steps.
    # We pass None as step_executor; the RecoveryHandler will use
    # its checkpoint_manager to iterate remaining steps.
    # For full LangGraph re-invocation, the caller should invoke the graph
    # manually with the loaded state.  This path uses the simple sequential
    # step executor (adequate for most recovery scenarios).
    success = resume_from_checkpoint(
        session_id=session_id,
        step_executor=None,  # No-op executor (returns loaded state only)
        checkpoint_id=checkpoint_id,
    )
    return success


# ---------------------------------------------------------------------------
# Optional type import (avoid polluting namespace at top level)
# ---------------------------------------------------------------------------
from typing import Optional  # noqa: E402 - placed after functions intentionally
