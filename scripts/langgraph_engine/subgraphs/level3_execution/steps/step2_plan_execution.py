"""
Level 3 Execution - Step 2: Plan Execution (Conditional)
"""

import json

from loguru import logger

from ....flow_state import FlowState


def _keyword_plan_fallback(tasks, task_type, complexity):
    """Fallback: group tasks into phases using keyword matching.

    Used when LLM is unavailable or returns unparseable output.
    Preserves original behavior as a reliable safety net.
    """
    plan = {
        "task_type": task_type,
        "complexity": complexity,
        "task_count": len(tasks),
        "phases": [],
        "milestones": [],
        "estimated_steps": 0,
        "plan_source": "keyword_fallback",
    }

    if not tasks:
        return plan

    # Phase 1: Setup/Analysis
    setup_tasks = [
        t
        for t in tasks
        if isinstance(t, dict)
        and any(kw in str(t.get("description", "")).lower() for kw in ["setup", "analyze", "plan", "review"])
    ]
    if setup_tasks:
        plan["phases"].append(
            {
                "name": "Setup & Analysis",
                "task_count": len(setup_tasks),
                "tasks": [t.get("id") if isinstance(t, dict) else str(t) for t in setup_tasks],
            }
        )

    # Phase 2: Implementation
    impl_tasks = [
        t
        for t in tasks
        if isinstance(t, dict)
        and any(kw in str(t.get("description", "")).lower() for kw in ["implement", "develop", "build", "code"])
    ]
    if impl_tasks:
        plan["phases"].append(
            {
                "name": "Implementation",
                "task_count": len(impl_tasks),
                "tasks": [t.get("id") if isinstance(t, dict) else str(t) for t in impl_tasks],
            }
        )

    # Phase 3: Testing & Review
    test_tasks = [
        t
        for t in tasks
        if isinstance(t, dict)
        and any(kw in str(t.get("description", "")).lower() for kw in ["test", "review", "verify", "validate"])
    ]
    if test_tasks:
        plan["phases"].append(
            {
                "name": "Testing & Verification",
                "task_count": len(test_tasks),
                "tasks": [t.get("id") if isinstance(t, dict) else str(t) for t in test_tasks],
            }
        )

    # If no clear phases, use all tasks in one execution phase
    if not plan["phases"]:
        plan["phases"].append(
            {
                "name": "Execution",
                "task_count": len(tasks),
                "tasks": [t.get("id") if isinstance(t, dict) else str(t) for t in tasks[:10]],
            }
        )

    # Set milestones at end of each phase
    for phase_num, phase in enumerate(plan["phases"], start=1):
        plan["milestones"].append(
            {"number": phase_num, "name": "Complete " + phase["name"], "tasks_required": phase["task_count"]}
        )

    plan["estimated_steps"] = sum(p["task_count"] for p in plan["phases"])
    return plan


def step2_plan_execution(state: FlowState) -> dict:
    """Step 2: Plan Execution - Create detailed execution plan (only if step1_plan_required=true).

    When plan mode is needed (complex tasks, multi-phase work), this step:
    1. Determines model tier from complexity: 1-3=fast, 4-7=balanced, 8-10=deep
    2. Sends task list + user message + complexity to LLM with a planning prompt
    3. Parses LLM response for phases, milestones, estimated steps
    4. Falls back to keyword-based grouping if LLM fails

    This step is SKIPPED if step1_plan_required=false.
    """
    try:
        from ....llm_call import llm_call

        # Get task breakdown from Step 0
        tasks = state.get("step0_tasks", {}).get("tasks", [])
        task_type = state.get("step0_task_type", "General Task")
        complexity = state.get("step0_complexity", 5)
        user_msg = state.get("user_message", "").strip()

        # Determine model tier from complexity score
        if complexity <= 3:
            model_tier = "fast"
        elif complexity <= 7:
            model_tier = "balanced"
        else:
            model_tier = "deep"

        # Build task summary for LLM prompt (ASCII-safe, truncated)
        task_lines = []
        for i, t in enumerate(tasks[:15], start=1):
            if isinstance(t, dict):
                desc = str(t.get("description", t.get("id", "Task")))
                effort = str(t.get("estimated_effort", "medium"))
                task_lines.append("%d. %s [effort: %s]" % (i, desc[:120], effort))
            else:
                task_lines.append("%d. %s" % (i, str(t)[:120]))
        task_summary = "\n".join(task_lines) if task_lines else "No tasks defined yet."

        # Truncate user message so the prompt stays within bounds
        user_msg_snippet = user_msg[:300] if user_msg else "(not provided)"

        planning_prompt = (
            "You are a software project planner. Given the task list below, "
            "produce a structured JSON execution plan.\n\n"
            "User request: %s\n\n"
            "Task type: %s\n"
            "Complexity: %d/10\n\n"
            "Tasks:/n%s\n\n"
            "Return ONLY valid JSON with this exact structure (no markdown, no explanation):\n"
            "{\n"
            '  "phases": [\n'
            '    {"name": "Phase Name", "tasks": ["task id or description", ...], '
            '"task_count": 3}\n'
            "  ],\n"
            '  "milestones": [\n'
            '    {"number": 1, "name": "Milestone name", "tasks_required": 3}\n'
            "  ],\n"
            '  "estimated_steps": 10,\n'
            '  "summary": "One sentence describing the plan"\n'
            "}"
        ) % (user_msg_snippet, task_type, complexity, task_summary)

        llm_response = llm_call(
            prompt=planning_prompt,
            model=model_tier,
            temperature=0.4,
            timeout=60,
            json_mode=True,
        )

        plan = None

        # Attempt to parse LLM JSON response
        if llm_response:
            try:
                # Strip markdown code fences if present
                cleaned = llm_response.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[-2] if cleaned.count("```") >= 2 else cleaned
                    cleaned = cleaned.lstrip("json").strip()

                parsed = json.loads(cleaned)

                # Validate that required keys are present
                if (
                    isinstance(parsed, dict)
                    and "phases" in parsed
                    and isinstance(parsed["phases"], list)
                    and len(parsed["phases"]) > 0
                ):
                    plan = {
                        "task_type": task_type,
                        "complexity": complexity,
                        "task_count": len(tasks),
                        "phases": parsed["phases"],
                        "milestones": parsed.get("milestones", []),
                        "estimated_steps": parsed.get("estimated_steps", len(tasks)),
                        "summary": parsed.get("summary", ""),
                        "plan_source": "llm_%s" % model_tier,
                    }

                    # Ensure each phase has task_count field
                    for phase in plan["phases"]:
                        if "task_count" not in phase:
                            phase["task_count"] = len(phase.get("tasks", []))

            except (ValueError, KeyError, TypeError) as parse_err:
                logger.debug("Step2 LLM JSON parse failed: %s", parse_err)
                plan = None

        # Fall back to keyword-based grouping if LLM failed
        if plan is None:
            logger.debug("Step2: LLM unavailable or parse failed, using keyword fallback")
            plan = _keyword_plan_fallback(tasks, task_type, complexity)

        # CallGraph impact analysis (best-effort, enriches plan with risk data)
        impact_analysis = None
        try:
            from ....level3_execution.call_graph_analyzer import analyze_impact_before_change

            target_files = []
            for phase in plan.get("phases", []):
                for t in phase.get("tasks", []):
                    if isinstance(t, dict) and t.get("files"):
                        target_files.extend(t["files"])
            if target_files:
                impact_analysis = analyze_impact_before_change(state.get("project_root", "."), target_files)
        except ImportError:
            pass  # CallGraph not available
        except Exception:
            pass  # Impact analysis is best-effort

        result = {
            "step2_plan_execution": plan,
            "step2_plan_status": "OK",
            "step2_phases": len(plan["phases"]),
            "step2_total_estimated_steps": plan["estimated_steps"],
            "step2_model_tier": model_tier,
            "step2_plan_source": plan.get("plan_source", "unknown"),
        }
        if impact_analysis:
            result["step2_impact_analysis"] = impact_analysis
        return result

    except Exception as e:
        return {"step2_plan_execution": {"error": str(e)}, "step2_plan_status": "ERROR", "step2_error": str(e)}
