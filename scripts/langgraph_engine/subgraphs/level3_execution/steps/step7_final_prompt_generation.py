"""
Level 3 Execution - Step 7: Final Prompt Generation
"""

from ....flow_state import FlowState
from ..helpers import _detect_project_type_from_files, _read_project_context_snippets


def step7_final_prompt_generation(state: FlowState) -> dict:
    """Step 7: Final Prompt Generation - Compose COMPLETE execution prompt with SYSTEM PROMPT.

    Generates comprehensive execution blueprint with SEPARATE system prompt and user message:

    SYSTEM PROMPT (context foundation - sent as system message):
    - Original user message (what they're asking)
    - Task type & complexity (scope analysis)
    - Validated task breakdown (specific work items)
    - Execution plan with phases (if planning enabled)
    - TOON enrichment (context from previous sessions)
    - Selected skill/agent FULL DEFINITIONS (tools to use)
    - Patterns detected (tech stack hints)
    - Project information (Java/Python/etc)

    USER MESSAGE (execution task - sent as user message):
    - "Execute the tasks above using the selected skill/agent..."

    This SYSTEM PROMPT + USER MESSAGE format provides:
    1. LLM has complete context before seeing the task
    2. LLM understands skill capabilities
    3. Reduces confusion about what to do
    4. Enables better execution decisions

    This is the MOST IMPORTANT prompt - it determines execution quality!
    Saves both system_prompt.txt and user_message.txt to session folder.
    """
    try:
        import os
        from pathlib import Path

        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH")

        # =====================================================================
        # BUILD SYSTEM PROMPT (comprehensive context foundation)
        # =====================================================================
        system_prompt_lines = []

        system_prompt_lines.append("# TASK EXECUTION CONTEXT")
        system_prompt_lines.append("")

        # 1. User message (original request)
        user_msg = state.get("user_message", "").strip()
        if user_msg:
            system_prompt_lines.append("## ORIGINAL REQUEST")
            system_prompt_lines.append(user_msg)
            system_prompt_lines.append("")

        # 2. Task analysis
        system_prompt_lines.append("## ANALYSIS")
        task_type = state.get("step0_task_type", "General")
        complexity = state.get("step0_complexity", 5)
        reasoning = state.get("step0_reasoning", "N/A")[:200]
        system_prompt_lines.append(f"- Type: {task_type}")
        system_prompt_lines.append(f"- Complexity: {complexity}/10")
        system_prompt_lines.append(f"- Reasoning: {reasoning}")
        system_prompt_lines.append("")

        # 3. VALIDATED Task breakdown (from Step 3, not Step 0)
        system_prompt_lines.append("## DETAILED BREAKDOWN")
        validated_tasks = state.get("step3_tasks_validated", [])
        raw_tasks = state.get("step0_tasks", {}).get("tasks", [])
        tasks_to_show = validated_tasks if validated_tasks else raw_tasks

        system_prompt_lines.append(f"Total Tasks: {len(tasks_to_show)}")
        if tasks_to_show:
            for i, task in enumerate(tasks_to_show[:10], 1):  # Show all 10 tasks
                if isinstance(task, dict):
                    desc = task.get("description", task.get("id", "Task"))
                    effort = task.get("estimated_effort", "medium")
                    files = task.get("files", [])
                    system_prompt_lines.append(f"\n  {i}. {desc}")
                    system_prompt_lines.append(f"     Effort: {effort}")
                    if files:
                        system_prompt_lines.append(f"     Files: {', '.join(files[:3])}")
                else:
                    system_prompt_lines.append(f"  {i}. {str(task)}")
        system_prompt_lines.append("")

        # 4. Execution plan (if available)
        plan_exec = state.get("step2_plan_execution", {})
        if plan_exec and plan_exec.get("phases"):
            system_prompt_lines.append("## EXECUTION PLAN")
            phases = plan_exec.get("phases", [])
            for phase in phases:
                system_prompt_lines.append(f"### {phase.get('name', 'Phase')}")
                system_prompt_lines.append(f"Tasks: {phase.get('task_count', 0)}")
                system_prompt_lines.append(f"IDs: {', '.join([str(t) for t in phase.get('tasks', [])])}")
            system_prompt_lines.append("")

        # 5. TOON Enrichment
        toon = state.get("step4_toon_refined", {})
        if toon:
            system_prompt_lines.append("## CONTEXT & INSIGHTS")
            if toon.get("task_descriptions"):
                system_prompt_lines.append("- Task Descriptions: Available")
            if toon.get("detected_patterns"):
                system_prompt_lines.append(f"- Patterns: {', '.join(toon.get('detected_patterns', []))}")
            if toon.get("planned_phases"):
                system_prompt_lines.append(f"- Planned Phases: {toon.get('planned_phases')}")
            system_prompt_lines.append("")

        # 6. ALL Selected Skills & Agents (multiple supported)
        system_prompt_lines.append("## TOOLS & RESOURCES")

        # Get all selected skills/agents (lists)
        selected_skills = state.get("step5_skills", [])
        selected_agents = state.get("step5_agents", [])
        skill_def = state.get("step5_skill_definition", "")
        agent_def = state.get("step5_agent_definition", "")
        skill_reasoning = state.get("step5_reasoning", "")

        # Backward compat: if lists empty, check single values
        if not selected_skills:
            single_skill = state.get("step5_skill", "")
            if single_skill:
                selected_skills = [single_skill]
        if not selected_agents:
            single_agent = state.get("step5_agent", "")
            if single_agent:
                selected_agents = [single_agent]

        if selected_skills:
            system_prompt_lines.append(f"\n### Selected Skills ({len(selected_skills)}):")
            for sk in selected_skills:
                system_prompt_lines.append(f"  - /{sk}")
            if skill_def:
                system_prompt_lines.append("\nSkill Definitions:")
                system_prompt_lines.append(skill_def)
            system_prompt_lines.append("")

        if selected_agents:
            system_prompt_lines.append(f"\n### Selected Agents ({len(selected_agents)}):")
            for ag in selected_agents:
                system_prompt_lines.append(f"  - {ag}")
            if agent_def:
                system_prompt_lines.append("\nAgent Definitions:")
                system_prompt_lines.append(agent_def)
            system_prompt_lines.append("")

        if skill_reasoning:
            system_prompt_lines.append(f"Selection reasoning: {skill_reasoning}")
            system_prompt_lines.append("")

        if not selected_skills and not selected_agents:
            system_prompt_lines.append("- No special skills/agents selected")
            system_prompt_lines.append("")

        # 7. Project context - RICH context from README/SRS + detected framework
        system_prompt_lines.append("## PROJECT CONTEXT")
        project_root = state.get("project_root", "")
        is_java = state.get("is_java_project", False)
        detected_fw = state.get("detected_framework", "")
        patterns = state.get("patterns_detected", [])

        if project_root:
            system_prompt_lines.append(f"- Root: {project_root}")

        # Use detected_framework from Level 2 (not hardcoded binary)
        if detected_fw:
            system_prompt_lines.append(f"- Type: {detected_fw}")
        elif is_java:
            system_prompt_lines.append("- Type: Java/Spring")
        else:
            # Auto-detect from project files
            proj_type = _detect_project_type_from_files(project_root)
            system_prompt_lines.append(f"- Type: {proj_type}")

        if patterns:
            system_prompt_lines.append(f"- Stack: {', '.join(patterns[:5])}")

        # Read README/SRS snippets for project understanding
        readme_snippet, srs_snippet = _read_project_context_snippets(project_root)
        if readme_snippet:
            system_prompt_lines.append("\n### README Summary")
            system_prompt_lines.append(readme_snippet)
        if srs_snippet:
            system_prompt_lines.append("\n### SRS Summary")
            system_prompt_lines.append(srs_snippet)

        system_prompt_lines.append("")

        system_prompt = "\n".join(system_prompt_lines)

        # =====================================================================
        # BUILD USER MESSAGE (original user prompt - NEVER generic)
        # =====================================================================
        # CRITICAL: user_message.txt must contain the ORIGINAL user request,
        # NOT a generic "Execute the General..." instruction.
        # The system prompt already has full context; user message is the actual task.
        if user_msg:
            user_message = user_msg
        else:
            # Fallback to env var if state didn't have it
            user_message = os.environ.get("CURRENT_USER_MESSAGE", "")
        if not user_message:
            # Last resort: generic instruction (should rarely happen)
            user_message = f"Execute the {task_type} using the breakdown and tools above."

        # =====================================================================
        # BUILD COMBINED PROMPT (for tools that don't support system prompt)
        # =====================================================================
        combined_prompt_lines = [
            "SYSTEM PROMPT:",
            "=" * 60,
            system_prompt,
            "",
            "=" * 60,
            "USER MESSAGE:",
            "=" * 60,
            user_message,
            "=" * 60,
        ]
        combined_prompt = "\n".join(combined_prompt_lines)

        # Save to session folder
        if session_path:
            # Save all three versions
            system_prompt_file = Path(session_path) / "system_prompt.txt"
            user_message_file = Path(session_path) / "user_message.txt"
            combined_prompt_file = Path(session_path) / "prompt.txt"

            with open(system_prompt_file, "w", encoding="utf-8") as f:
                f.write(system_prompt)

            with open(user_message_file, "w", encoding="utf-8") as f:
                f.write(user_message)

            with open(combined_prompt_file, "w", encoding="utf-8") as f:
                f.write(combined_prompt)

            return {
                "step7_prompt_saved": True,
                "step7_system_prompt_file": str(system_prompt_file),
                "step7_user_message_file": str(user_message_file),
                "step7_combined_prompt_file": str(combined_prompt_file),
                "step7_system_prompt_size": len(system_prompt),
                "step7_user_message_size": len(user_message),
                "step7_combined_prompt_size": len(combined_prompt),
                "step7_context_included": {
                    "user_message": bool(user_msg),
                    "task_analysis": True,
                    "validated_tasks": len(validated_tasks) > 0,
                    "execution_plan": plan_exec.get("phases") is not None,
                    "toon_enrichment": bool(toon),
                    "skill_definition": bool(skill_def),
                    "agent_definition": bool(agent_def),
                    "project_context": bool(project_root or patterns),
                    "system_prompt_format": True,  # NEW: using system prompt format
                },
            }
        else:
            return {"step7_prompt_saved": False, "step7_error": "No session_dir available"}

    except Exception as e:
        return {"step7_prompt_saved": False, "step7_error": str(e)}
