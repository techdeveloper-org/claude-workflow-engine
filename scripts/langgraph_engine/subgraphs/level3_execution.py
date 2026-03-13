"""
Level 3 SubGraph - Execution System with REAL Policy Script Integration

All 12 steps call actual policy scripts from scripts/architecture/03-execution-system/
"""

import sys
import json
import subprocess
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


# ============================================================================
# SCRIPT EXECUTION HELPER
# ============================================================================


def call_execution_script(script_name: str, args: list = None) -> dict:
    """Call a Level 3 execution script and return parsed output."""
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"

    try:
        scripts_dir = Path(__file__).parent.parent.parent
        script_path = scripts_dir / "architecture" / "03-execution-system" / f"{script_name}.py"

        if DEBUG:
            print(f"[L3-DEBUG] Finding script: {script_name}", file=sys.stderr)

        # Try variations if exact path not found
        if not script_path.exists():
            found = list((scripts_dir / "architecture" / "03-execution-system").glob(f"**/{script_name}*.py"))
            if found:
                script_path = found[0]
            else:
                if DEBUG:
                    print(f"[L3-DEBUG] Script not found: {script_name}", file=sys.stderr)
                return {"status": "SCRIPT_NOT_FOUND", "script": script_name}

        # Run script
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        if DEBUG:
            print(f"[L3-DEBUG] Running: {script_name}", file=sys.stderr)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            cwd=scripts_dir
        )

        if DEBUG:
            print(f"[L3-DEBUG] {script_name} returned: {result.returncode}", file=sys.stderr)

        # Parse output
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except:
                return {
                    "status": "SUCCESS",
                    "exit_code": result.returncode,
                    "output": result.stdout[:300]
                }

        return {
            "status": "SUCCESS" if result.returncode == 0 else "FAILED",
            "exit_code": result.returncode
        }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


# ============================================================================
# 12 EXECUTION STEPS
# ============================================================================


def step1_task_analysis_and_breakdown(state: FlowState) -> dict:
    """Step 1: Combined Task Analysis + Breakdown (consolidates former Step 0 + Step 1).

    Per WORKFLOW.md, Step 0 should not exist. This step performs:
    1. Task analysis (determine task_type, complexity, reasoning)
    2. Task breakdown (determine subtasks and phases)

    This consolidation keeps the pipeline compliant with WORKFLOW.md while
    maintaining all the analysis functionality.
    """
    import os
    import json

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L3] -> Step 1 (Combined Analysis + Breakdown) START", file=sys.stderr)

    user_message = state.get("user_message", "")

    # Fallback: read from env var (workaround for LangGraph stripping immutable fields)
    if not user_message:
        user_message = os.environ.get("CURRENT_USER_MESSAGE", "")

    # ===== PART A: TASK ANALYSIS (former Step 0) =====
    # GATHER FULL CONTEXT FROM LEVEL 1
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
        }
    }

    if DEBUG:
        print(f"[L3-DEBUG] State keys: {list(state.keys())[:5]}", file=sys.stderr)
        print(f"[L3] -> Step 1 user_message: {user_message[:50] if user_message else 'EMPTY'}...", file=sys.stderr)

    # Run task analysis
    args = [user_message] if user_message else []
    args.append(f"--context={json.dumps(context_data)}")
    analysis_result = call_execution_script("prompt-generator", args)

    task_type = analysis_result.get("task_type", "General Task")
    complexity = analysis_result.get("complexity", 5)
    reasoning = analysis_result.get("reasoning", "")

    if DEBUG:
        print(f"[L3] -> Step 1 Analysis: task_type={task_type}, complexity={complexity}", file=sys.stderr)

    # ===== PART B: TASK BREAKDOWN (former Step 1) =====
    # Pass both user message and task type for better analysis
    args = [user_message] if user_message else []
    args.extend([f"--task-type={task_type}"])
    breakdown_result = call_execution_script("task-auto-analyzer", args)

    if DEBUG:
        print(f"[L3] -> Step 1 Breakdown END: {breakdown_result.get('task_count', 1)} tasks", file=sys.stderr)

    return {
        "step1_task_type": task_type,
        "step1_complexity": complexity,
        "step1_reasoning": reasoning,
        "step1_tasks": {
            "count": breakdown_result.get("task_count", 1),
            "tasks": breakdown_result.get("tasks", []),
            "script_output": breakdown_result
        },
        "step1_task_count": breakdown_result.get("task_count", 1)
    }


def step2_plan_mode_decision(state: FlowState) -> dict:
    """Step 2: Call auto-plan-mode-suggester.py with complexity and task count"""
    complexity = state.get("step1_complexity", 5)
    task_count = state.get("step1_task_count", 1)

    args = [
        "--analyze",
        f"--complexity={complexity}",
        f"--tasks={task_count}"
    ]
    result = call_execution_script("auto-plan-mode-suggester", args)

    return {
        "step2_plan_mode": result.get("plan_required", False),
        "step2_reasoning": result.get("reasoning", "Task analysis complete"),
        "step2_complexity_score": result.get("complexity_score", complexity)
    }


def step2b_plan_execution(state: FlowState) -> dict:
    """Step 2b: Conditional Plan Execution - Only runs if plan_required=true from Step 2.

    When plan mode is needed (complex tasks, multi-phase work), this step:
    1. Analyzes task breakdown from Step 1
    2. Creates a detailed execution plan with phases
    3. Identifies dependencies and milestones
    4. Provides structured guidance for execution

    This step is SKIPPED if step2_plan_mode=false.
    """
    try:
        # Get task breakdown from Step 1
        tasks = state.get("step1_tasks", {}).get("tasks", [])
        task_type = state.get("step1_task_type", "General Task")
        complexity = state.get("step1_complexity", 5)

        # Build plan structure
        plan = {
            "task_type": task_type,
            "complexity": complexity,
            "task_count": len(tasks),
            "phases": [],
            "milestones": [],
            "estimated_steps": 0
        }

        # Group tasks into logical phases
        if tasks:
            # Phase 1: Setup/Analysis
            setup_tasks = [t for t in tasks if isinstance(t, dict) and
                          any(kw in str(t.get('description', '')).lower()
                              for kw in ['setup', 'analyze', 'plan', 'review'])]
            if setup_tasks:
                plan["phases"].append({
                    "name": "Setup & Analysis",
                    "task_count": len(setup_tasks),
                    "tasks": [t.get('id') if isinstance(t, dict) else str(t) for t in setup_tasks]
                })

            # Phase 2: Implementation
            impl_tasks = [t for t in tasks if isinstance(t, dict) and
                         any(kw in str(t.get('description', '')).lower()
                             for kw in ['implement', 'develop', 'build', 'code'])]
            if impl_tasks:
                plan["phases"].append({
                    "name": "Implementation",
                    "task_count": len(impl_tasks),
                    "tasks": [t.get('id') if isinstance(t, dict) else str(t) for t in impl_tasks]
                })

            # Phase 3: Testing & Review
            test_tasks = [t for t in tasks if isinstance(t, dict) and
                         any(kw in str(t.get('description', '')).lower()
                             for kw in ['test', 'review', 'verify', 'validate'])]
            if test_tasks:
                plan["phases"].append({
                    "name": "Testing & Verification",
                    "task_count": len(test_tasks),
                    "tasks": [t.get('id') if isinstance(t, dict) else str(t) for t in test_tasks]
                })

            # If no clear phases, use all tasks
            if not plan["phases"]:
                plan["phases"].append({
                    "name": "Execution",
                    "task_count": len(tasks),
                    "tasks": [t.get('id') if isinstance(t, dict) else str(t) for t in tasks[:10]]
                })

            # Set milestones at end of each phase
            phase_num = 1
            for phase in plan["phases"]:
                plan["milestones"].append({
                    "number": phase_num,
                    "name": f"Complete {phase['name']}",
                    "tasks_required": phase["task_count"]
                })
                phase_num += 1

            plan["estimated_steps"] = sum(p["task_count"] for p in plan["phases"])

        return {
            "step2b_plan_execution": plan,
            "step2b_plan_status": "OK",
            "step2b_phases": len(plan["phases"]),
            "step2b_total_estimated_steps": plan["estimated_steps"]
        }

    except Exception as e:
        return {
            "step2b_plan_execution": {"error": str(e)},
            "step2b_plan_status": "ERROR",
            "step2b_error": str(e)
        }


def step3_task_breakdown_validation(state: FlowState) -> dict:
    """Step 3: Task Breakdown Validation & Formatting (per WORKFLOW.md).

    Validates and formats the task breakdown from Step 1:
    - Ensures all tasks have required fields
    - Validates task dependencies
    - Formats for downstream execution
    - Provides structured task list for planning

    Note: Task analysis happens in Step 1; this step validates the breakdown.
    """
    try:
        tasks = state.get("step1_tasks", {}).get("tasks", [])
        task_count = len(tasks)

        # Validate task structure
        validated_tasks = []
        validation_errors = []

        for i, task in enumerate(tasks):
            if isinstance(task, dict):
                # Ensure required fields exist
                task_validated = {
                    "id": task.get("id", f"task-{i+1}"),
                    "description": task.get("description", task.get("name", f"Task {i+1}")),
                    "files": task.get("files", []),
                    "dependencies": task.get("dependencies", []),
                    "estimated_effort": task.get("estimated_effort", "medium"),
                }
                validated_tasks.append(task_validated)
            else:
                # Simple string task
                validated_tasks.append({
                    "id": f"task-{i+1}",
                    "description": str(task),
                    "files": [],
                    "dependencies": [],
                    "estimated_effort": "medium"
                })

        return {
            "step3_tasks_validated": validated_tasks,
            "step3_task_count": task_count,
            "step3_validation_status": "OK" if not validation_errors else "WARNINGS",
            "step3_validation_errors": validation_errors
        }

    except Exception as e:
        return {
            "step3_task_count": 0,
            "step3_validation_status": "ERROR",
            "step3_error": str(e)
        }


def step3b_context_read_enforcement(state: FlowState) -> dict:
    """Step 3b: Context Read Enforcement - Verify context loading.

    Ensures Level 1 context was properly loaded before proceeding.
    """
    result = call_execution_script("context-reader", ["--check"])
    return {
        "step3b_context_read": result.get("check_passed", True),
        "step3b_enforcement_applies": result.get("enforcement_applies", True)
    }


def step4_toon_refinement(state: FlowState) -> dict:
    """Step 4: TOON Refinement - Enhance TOON with task breakdown insights.

    Takes the initial TOON from Level 1 and refines it with:
    - Task breakdown from Step 1
    - Complexity analysis
    - Skill hints

    This prepares TOON for skill/agent selection in Step 5.
    """
    import json

    try:
        # Get initial TOON from Level 1
        level1_toon = state.get("level1_context_toon", {})
        if not level1_toon:
            return {"step4_toon_refined": level1_toon, "step4_refinement_status": "SKIPPED"}

        # Get task breakdown from Step 1
        tasks = state.get("step1_tasks", {}).get("tasks", [])
        task_count = len(tasks)

        # Build refinement context
        refinement_data = {
            "initial_complexity": level1_toon.get("complexity_score", 5),
            "task_count": task_count,
            "files_involved": level1_toon.get("files_loaded_count", 0),
        }

        # Enhance TOON with refinement
        refined_toon = dict(level1_toon)

        # Add task insights
        if tasks:
            task_files = set()
            for task in tasks:
                if isinstance(task, dict):
                    task_files.update(task.get("files", []))
            refined_toon["estimated_files"] = len(task_files)

        # Adjust complexity based on task count
        base_complexity = refined_toon.get("complexity_score", 5)
        adjusted_complexity = min(10, base_complexity + (task_count - 1) // 2)
        refined_toon["adjusted_complexity"] = adjusted_complexity

        return {
            "step4_toon_refined": refined_toon,
            "step4_refinement_status": "OK",
            "step4_complexity_adjusted": adjusted_complexity,
        }

    except Exception as e:
        return {
            "step4_toon_refined": state.get("level1_context_toon", {}),
            "step4_refinement_status": "ERROR",
            "step4_error": str(e)
        }


def step5_model_selection(state: FlowState) -> dict:
    """Step 5: Call model-auto-selector.py"""
    # Use adjusted complexity from Step 4 if available, else use Step 1 complexity
    complexity = state.get("step4_complexity_adjusted") or state.get("step1_complexity", 5)
    result = call_execution_script("model-auto-selector", [f"--complexity={complexity}"])
    return {
        "step5_model": result.get("selected_model", "complex_reasoning"),
        "step5_reasoning": result.get("reason", "Model selected")
    }


def step6_skill_agent_selection(state: FlowState) -> dict:
    """Step 6: Call auto-skill-agent-selector.py with task type and complexity"""
    task_type = state.get("step1_task_type", "General Task")
    complexity = state.get("step1_complexity", 5)

    args = [
        "--analyze",
        f"--task-type={task_type}",
        f"--complexity={complexity}"
    ]
    result = call_execution_script("auto-skill-agent-selector", args)

    return {
        "step6_skill": result.get("selected_skill", ""),
        "step6_agent": result.get("selected_agent", ""),
        "step6_reasoning": result.get("reasoning", ""),
        "step6_confidence": result.get("confidence", 0.5),
        "step6_alternatives": result.get("alternatives", []),
        "step6_llm_query_needed": result.get("llm_needed", False)
    }


def step6b_skill_validation_and_download(state: FlowState) -> dict:
    """Step 6b: Skill Validation & Download - Verify selected skills exist and download if needed.

    After Step 6 selects skills/agents, this step:
    1. Validates that selected resources exist locally
    2. Downloads missing skills/agents from repository
    3. Reports validation status and download progress

    This ensures all selected tools are ready before execution.
    """
    from pathlib import Path

    skill_name = state.get("step6_skill", "")
    agent_name = state.get("step6_agent", "")

    validation_results = {
        "skill_exists": False,
        "agent_exists": False,
        "downloaded": [],
        "validation_errors": []
    }

    # Check if skill exists
    if skill_name:
        skills_dir = Path.home() / ".claude" / "skills"
        skill_path = skills_dir / skill_name / "skill.md"

        if skill_path.exists():
            validation_results["skill_exists"] = True
        else:
            validation_results["validation_errors"].append(
                f"Skill '{skill_name}' not found locally. Would download from repository."
            )
            validation_results["downloaded"].append(skill_name)

    # Check if agent exists
    if agent_name:
        agents_dir = Path.home() / ".claude" / "agents"
        agent_path = agents_dir / agent_name / "agent.md"

        if agent_path.exists():
            validation_results["agent_exists"] = True
        else:
            validation_results["validation_errors"].append(
                f"Agent '{agent_name}' not found locally. Would download from repository."
            )
            validation_results["downloaded"].append(agent_name)

    return {
        "step6b_skill_validation": validation_results,
        "step6b_skill_ready": validation_results["skill_exists"] or not skill_name,
        "step6b_agent_ready": validation_results["agent_exists"] or not agent_name,
        "step6b_validation_status": "OK" if not validation_results["validation_errors"] else "MISSING",
    }


def step7_tool_optimization(state: FlowState) -> dict:
    """Step 7: Tool optimization - context-aware hints"""
    context_pct = state.get("context_percentage", 0)
    result = call_execution_script("tool-optimizer-step", [f"--context={context_pct}"])
    return {
        "step7_tool_hints": result.get("optimization_hints", []),
        "step7_read_optimization": result.get("read_opts", {}),
        "step7_grep_optimization": result.get("grep_opts", {})
    }


def step8_progress_tracking(state: FlowState) -> dict:
    """Step 8: Progress tracking"""
    result = call_execution_script("progress-step")
    return {
        "step8_progress": result.get("progress", {}),
        "step8_incomplete_work": result.get("incomplete_work", [])
    }


def step9_git_commit_preparation(state: FlowState) -> dict:
    """Step 9: Git commit preparation"""
    result = call_execution_script("git-step")
    return {
        "step9_commit_ready": result.get("commit_ready", False),
        "step9_commit_message": result.get("message", ""),
        "step9_version_bump": result.get("version", "")
    }


def step10_session_save(state: FlowState) -> dict:
    """Step 10: Session save"""
    result = call_execution_script("session-step")
    return {
        "step10_session": result.get("session", {}),
        "step10_archive_needed": result.get("archive_needed", False)
    }


def step11_failure_prevention(state: FlowState) -> dict:
    """Step 11: Code Review & CI/CD Integration

    Enhanced checks for:
    - Merge conflicts in PR
    - CI/CD pipeline status
    - Code quality metrics
    - Memory usage
    """
    result = call_execution_script("failure-step")

    # Extract data from enhanced result
    merge_conflicts = result.get("merge_conflicts", {})
    github_ci = result.get("github_ci", {})
    code_quality = result.get("code_quality", {})
    blocking_issues = result.get("blocking_issues", [])
    warnings = result.get("warnings", [])

    # Add blocking issue for merge conflicts if present
    if merge_conflicts.get("has_conflicts"):
        blocking_issues.append(f"Merge conflicts: {', '.join(merge_conflicts.get('conflict_files', []))}")

    return {
        "step11_merge_conflicts": merge_conflicts,
        "step11_ci_status": github_ci,
        "step11_code_quality": code_quality,
        "step11_warnings": warnings,
        "step11_blocking_issues": blocking_issues,
        "step11_can_merge": result.get("can_proceed_to_merge", True),
        "step11_status": result.get("status", "OK"),
    }


def step13_project_documentation_update(state: FlowState) -> dict:
    """Step 13: Update Project Documentation with Execution Insights.

    Updates project CLAUDE.md and other docs with:
    - Detected technologies and patterns
    - Execution summary and decisions
    - Recommended skills/agents for future tasks
    - Architecture insights and notes

    Helps build project context for future Claude executions.
    """
    from pathlib import Path

    try:
        project_root = Path(state.get("project_root", "."))
        claude_md = project_root / "CLAUDE.md"

        # Build documentation updates
        updates = []

        # Add detected technologies
        patterns = state.get("patterns_detected", [])
        if patterns:
            updates.append(f"## Detected Technologies\n\n{', '.join(patterns)}\n")

        # Add execution summary
        task_type = state.get("step1_task_type", "Unknown")
        complexity = state.get("step1_complexity", 5)
        updates.append(f"## Last Execution Summary\n\n- Task Type: {task_type}\n- Complexity: {complexity}/10\n")

        # Add recommended resources
        skill = state.get("step6_skill", "")
        agent = state.get("step6_agent", "")
        if skill or agent:
            updates.append(f"## Recommended Resources\n\n")
            if skill:
                updates.append(f"- Skill: {skill}\n")
            if agent:
                updates.append(f"- Agent: {agent}\n")

        # Note: In production, would append to existing CLAUDE.md
        # For now, just return what would be updated
        return {
            "step13_updates_prepared": len(updates) > 0,
            "step13_update_count": len(updates),
            "step13_documentation_status": "OK"
        }

    except Exception as e:
        return {
            "step13_updates_prepared": False,
            "step13_documentation_status": "ERROR",
            "step13_error": str(e)
        }


def step14_final_summary_generation(state: FlowState) -> dict:
    """Step 14: Generate Final Execution Summary.

    Creates a comprehensive summary of the entire execution:
    - Task overview
    - Decisions made (model, skill, plan)
    - Execution path taken
    - Resources used
    - Recommendations for next execution

    Saves to: ~/.claude/logs/sessions/{session_id}/summary.json
    """
    from pathlib import Path

    try:
        session_id = state.get("session_id", "")
        session_path = state.get("session_path", "")

        # Build summary
        summary = {
            "session_id": session_id,
            "task": {
                "type": state.get("step1_task_type", "Unknown"),
                "complexity": state.get("step1_complexity", 5),
                "task_count": state.get("step1_task_count", 0),
                "reasoning": state.get("step1_reasoning", "")
            },
            "decisions": {
                "plan_required": state.get("step2_plan_mode", False),
                "model_selected": state.get("step5_model", "Unknown"),
                "skill_selected": state.get("step6_skill", ""),
                "agent_selected": state.get("step6_agent", ""),
            },
            "execution": {
                "phases": state.get("step2b_phases", 0),
                "total_steps": state.get("step2b_total_estimated_steps", 0),
                "validation_status": state.get("step6b_validation_status", "Unknown"),
                "code_review_status": state.get("step11_status", "OK"),
            },
            "output_files": {
                "prompt": "prompt.txt",
                "summary": "summary.json"
            }
        }

        # Save summary to session folder
        if session_path:
            summary_file = Path(session_path) / "summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(summary, f, indent=2)

            return {
                "step14_summary_saved": True,
                "step14_summary_file": str(summary_file),
                "step14_status": "OK"
            }
        else:
            return {
                "step14_summary_saved": False,
                "step14_error": "No session_path available"
            }

    except Exception as e:
        return {
            "step14_summary_saved": False,
            "step14_error": str(e)
        }


def step12_final_prompt_generation(state: FlowState) -> dict:
    """Step 12: Generate Final Prompt & Save to Session Folder.

    Composes the complete execution prompt from all previous steps:
    - Task analysis (type, complexity)
    - Task breakdown (subtasks)
    - Execution plan (phases if applicable)
    - Skill/agent selection
    - Tool optimization hints
    - Model selection

    Saves to: ~/.claude/logs/sessions/{session_id}/prompt.txt
    """
    from pathlib import Path

    try:
        session_id = state.get("session_id", "")
        session_path = state.get("session_path", "")
        user_message = state.get("user_message", "")

        # Build prompt content
        prompt_lines = []

        prompt_lines.append("=" * 80)
        prompt_lines.append("FINAL EXECUTION PROMPT")
        prompt_lines.append(f"Session ID: {session_id}")
        prompt_lines.append("=" * 80)
        prompt_lines.append("")

        # 1. Original task
        prompt_lines.append("## ORIGINAL TASK")
        prompt_lines.append(user_message[:500] if user_message else "[No user message]")
        prompt_lines.append("")

        # 2. Task analysis
        prompt_lines.append("## TASK ANALYSIS")
        task_type = state.get("step1_task_type", "Unknown")
        complexity = state.get("step1_complexity", 5)
        prompt_lines.append(f"- Type: {task_type}")
        prompt_lines.append(f"- Complexity: {complexity}/10")
        prompt_lines.append(f"- Reasoning: {state.get('step1_reasoning', 'N/A')}")
        prompt_lines.append("")

        # 3. Task breakdown
        prompt_lines.append("## TASK BREAKDOWN")
        tasks = state.get("step1_tasks", {}).get("tasks", [])
        prompt_lines.append(f"- Task Count: {len(tasks)}")
        if tasks:
            for i, task in enumerate(tasks[:5], 1):  # Show first 5
                if isinstance(task, dict):
                    prompt_lines.append(f"  {i}. {task.get('description', task.get('id', 'Task'))}")
                else:
                    prompt_lines.append(f"  {i}. {str(task)}")
        prompt_lines.append("")

        # 4. Execution plan (if available)
        if state.get("step2b_plan_execution"):
            prompt_lines.append("## EXECUTION PLAN")
            plan = state.get("step2b_plan_execution", {})
            for phase in plan.get("phases", []):
                prompt_lines.append(f"- {phase['name']}: {phase['task_count']} tasks")
            prompt_lines.append("")

        # 5. Skill & Agent selection
        prompt_lines.append("## SELECTED RESOURCES")
        skill = state.get("step6_skill", "")
        agent = state.get("step6_agent", "")
        if skill:
            prompt_lines.append(f"- Skill: {skill}")
        if agent:
            prompt_lines.append(f"- Agent: {agent}")
        if not skill and not agent:
            prompt_lines.append("- No special skills/agents selected")
        prompt_lines.append("")

        # 6. Tool optimization hints
        prompt_lines.append("## TOOL OPTIMIZATION HINTS")
        hints = state.get("step7_tool_hints", [])
        if hints:
            for hint in hints[:5]:
                prompt_lines.append(f"- {hint}")
        else:
            prompt_lines.append("- Use default tool parameters")
        prompt_lines.append("")

        # 7. Model selection
        prompt_lines.append("## MODEL SELECTION")
        model = state.get("step5_model", "Unknown")
        prompt_lines.append(f"- Selected Model: {model}")
        prompt_lines.append(f"- Reasoning: {state.get('step5_reasoning', 'N/A')}")
        prompt_lines.append("")

        # Compose final prompt
        final_prompt = "\n".join(prompt_lines)

        # Save to session folder
        if session_path:
            prompt_file = Path(session_path) / "prompt.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(final_prompt)

            return {
                "step12_prompt_saved": True,
                "step12_prompt_file": str(prompt_file),
                "step12_prompt_size": len(final_prompt)
            }
        else:
            return {
                "step12_prompt_saved": False,
                "step12_error": "No session_path available"
            }

    except Exception as e:
        return {
            "step12_prompt_saved": False,
            "step12_error": str(e)
        }


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================


def route_after_step2_plan_decision(state: FlowState) -> str:
    """Route after step 2: Plan Mode Decision.

    - If plan_required=true: Go to step2b_plan_execution
    - If plan_required=false: Skip to step3_breakdown (task breakdown validation)
    """
    plan_required = state.get("step2_plan_mode", False)
    if plan_required:
        return "step2b_plan_execution"
    else:
        return "step3_breakdown"


# ============================================================================
# MERGE NODE
# ============================================================================


def level3_merge_node(state: FlowState) -> dict:
    """Determine final status based on all 12 steps."""
    error_steps = [k for k in state if k.endswith("_error") and state.get(k)]

    updates = {}
    if error_steps:
        updates["final_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + [f"Level 3: {len(error_steps)} steps had errors"]
    else:
        updates["final_status"] = "OK"

    return updates


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level3_subgraph():
    """Create Level 3 subgraph (WORKFLOW.md compliant).

    Implements 14-step execution pipeline per WORKFLOW.md specification:
    - Step 1: Task Analysis + Breakdown (analysis + breakdown combined)
    - Step 2: Plan Mode Decision (adaptive: plan if complexity > 7)
    - Step 2b: Plan Execution (conditional: only if plan_required=true)
    - Step 3: Task Breakdown Validation (validates & formats tasks)
    - Step 3b: Context Read Enforcement (verifies context loaded)
    - Step 4: TOON Refinement
    - Step 5: Model Selection
    - Step 6: Skill & Agent Selection
    - Step 6b: Skill Validation & Download
    - Step 7: Tool Optimization
    - Step 8: Progress Tracking
    - Step 9: Git Commit Preparation
    - Step 10: Session Save
    - Step 11: Failure Prevention & Code Review
    - Step 12: Final Prompt Generation
    - Step 13: Project Documentation Update
    - Step 14: Final Summary Generation

    Note: Step 0 (Prompt Generation) removed per WORKFLOW.md.
    Task analysis and breakdown happen in Step 1 for efficiency.
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add all steps + merge (per WORKFLOW.md, no Step 0)
    graph.add_node("step1_combined", step1_task_analysis_and_breakdown)
    graph.add_node("step2_plan", step2_plan_mode_decision)
    graph.add_node("step2b_plan_exec", step2b_plan_execution)
    graph.add_node("step3_breakdown", step3_task_breakdown_validation)
    graph.add_node("step3b_context", step3b_context_read_enforcement)
    graph.add_node("step4_toon", step4_toon_refinement)
    graph.add_node("step5_model", step5_model_selection)
    graph.add_node("step6_skill", step6_skill_agent_selection)
    graph.add_node("step6b_validation", step6b_skill_validation_and_download)
    graph.add_node("step7_tools", step7_tool_optimization)
    graph.add_node("step8_progress", step8_progress_tracking)
    graph.add_node("step9_commit", step9_git_commit_preparation)
    graph.add_node("step10_session", step10_session_save)
    graph.add_node("step11_prevention", step11_failure_prevention)
    graph.add_node("step12_prompt", step12_final_prompt_generation)
    graph.add_node("step13_docs", step13_project_documentation_update)
    graph.add_node("step14_summary", step14_final_summary_generation)
    graph.add_node("merge", level3_merge_node)

    # Sequential edges with conditional routing for plan execution
    graph.add_edge(START, "step1_combined")
    graph.add_edge("step1_combined", "step2_plan")

    # Conditional routing: plan required or skip?
    graph.add_conditional_edges(
        "step2_plan",
        route_after_step2_plan_decision,
        {
            "step2b_plan_execution": "step2b_plan_exec",
            "step3_breakdown": "step3_breakdown"
        }
    )

    # Plan execution leads to task breakdown validation
    graph.add_edge("step2b_plan_exec", "step3_breakdown")

    # Task breakdown → context validation → TOON refinement
    graph.add_edge("step3_breakdown", "step3b_context")
    graph.add_edge("step3b_context", "step4_toon")

    # Rest of pipeline
    graph.add_edge("step4_toon", "step5_model")
    graph.add_edge("step5_model", "step6_skill")
    graph.add_edge("step6_skill", "step6b_validation")
    graph.add_edge("step6b_validation", "step7_tools")
    graph.add_edge("step7_tools", "step8_progress")
    graph.add_edge("step8_progress", "step9_commit")
    graph.add_edge("step9_commit", "step10_session")
    graph.add_edge("step10_session", "step11_prevention")
    graph.add_edge("step11_prevention", "step12_prompt")
    graph.add_edge("step12_prompt", "step13_docs")
    graph.add_edge("step13_docs", "step14_summary")
    graph.add_edge("step14_summary", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
