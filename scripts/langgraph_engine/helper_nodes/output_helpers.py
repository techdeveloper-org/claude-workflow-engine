"""Output helper nodes - Final output synthesis and pipeline execution logging.

Extracted from orchestrator.py. Handles the final output_node which synthesizes
the prompt, saves the execution log, and accumulates session info.

CHANGE LOG (v1.15.0):
  Removed TOON log line from _save_pipeline_execution_log() Level 1 section
  (TOON compression node removed from pipeline).

CHANGE LOG (v1.15.2):
  Removed step_info rows for steps 4-7 from _save_pipeline_execution_log()
  (TOON Refinement, Skill & Agent Selection, Skill Validation, Final Prompt
  Generation were removed from the pipeline in v1.13.0).
"""

import sys
from pathlib import Path

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _OUTPUT_HELPERS_CLAUDE_HOME = get_claude_home()
except ImportError:
    _OUTPUT_HELPERS_CLAUDE_HOME = Path.home() / ".claude"

from ..flow_state import FlowState, StepKeys
from .context_helpers import save_workflow_memory


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

        # Import PromptGenerator from prompt-generation-policy.py
        scripts_path = (
            Path(__file__).parent.parent.parent / "architecture" / "03-execution-system" / "00-prompt-generation"
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
        flag_dir = _OUTPUT_HELPERS_CLAUDE_HOME
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
        _src_mcp_dir = Path(__file__).resolve().parent.parent.parent.parent / "src" / "mcp"
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

        # Level 2
        log_lines.append("## Level 2: Standards")
        log_lines.append(f"- Standards Loaded: {state.get(StepKeys.STANDARDS_COUNT, 0)}")
        log_lines.append(f"- Framework Detected: {state.get(StepKeys.DETECTED_FRAMEWORK, 'unknown')}")
        log_lines.append(f"- MCP Discovered: {state.get(StepKeys.MCP_DISCOVERED_COUNT, 0)}")
        log_lines.append(f"- Tool Rules: {'Loaded' if state.get(StepKeys.TOOL_OPTIMIZATION_LOADED) else 'Missing'}")
        log_lines.append(f"- Status: {state.get(StepKeys.LEVEL2_STATUS, 'unknown')}")
        log_lines.append("")

        # Level 3 Steps (active steps only: Pre-0, Step 0, Steps 8-14)
        # v1.15.2: removed rows for steps 4-7 (TOON Refinement, Skill & Agent Selection,
        #          Skill Validation, Final Prompt Generation -- removed from pipeline in v1.13.0)
        log_lines.append("## Level 3: Execution Steps")
        log_lines.append("")
        log_lines.append("| Step | Name | Status | Duration | Details |")
        log_lines.append("|------|------|--------|----------|---------|")

        step_info = [
            (0, "Task Analysis", "step0_task_type", "step0_complexity"),
            (1, "Plan Mode Decision", "step1_plan_required", "step1_reasoning"),
            (2, "Plan Execution", "step2_plan_status", "step2_phases"),
            (3, "Task Breakdown", "step3_validation_status", "step3_task_count"),
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
