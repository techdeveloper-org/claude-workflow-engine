"""
Level 3 Execution - Step 5: Skill & Agent Selection
"""

import json

from ....flow_state import FlowState
from ..helpers import _detect_project_type_from_files, call_execution_script


def step5_skill_agent_selection(state: FlowState) -> dict:
    """Step 5: Skill & Agent Selection - Select perfect skill/agent with FULL context + definitions.

    PHASE 2 ENHANCED: Includes DeepSeek reasoning for intelligent MCP selection.

    Uses COMPLETE context INCLUDING FULL SKILL DEFINITIONS to make informed skill/agent selection:
    - User message (what they're asking)
    - Task type & complexity (what kind of work)
    - Validated tasks (specific work items)
    - Project info (Java/Python/etc)
    - Patterns detected (tech stack)
    - TOON refinement (enriched overview)
    - **ALL SKILL DEFINITIONS** (what each skill can do - CRITICAL)
    - **ALL AGENT DEFINITIONS** (what each agent can orchestrate - CRITICAL)
    - **DeepSeek REASONING** (which MCPs are needed - Phase 2 NEW)

    Post-selection: ConflictResolver checks for incompatible skill/agent pairs.
    Any conflicts are resolved via priority-based rules before the result is stored.
    A conflict log is saved to the session directory if conflicts are found.

    Timeout: enforced at 60s by the v2 _run_step wrapper.
    """
    from ....deepseek_reasoning import get_deepseek_reasoning
    from ....skill_agent_loader import get_skill_agent_loader

    # Gather ALL context for best skill selection
    user_message = state.get("user_message", "")
    task_type = state.get("step0_task_type", "General Task")
    complexity = state.get("step0_complexity", 5)
    validated_tasks = state.get("step3_tasks_validated", [])
    patterns = state.get("patterns_detected", [])
    project_root = state.get("project_root", "")
    is_java = state.get("is_java_project", False)
    refined_toon = state.get("step4_toon_refined", {})

    # Build complete context for skill selection
    task_descriptions = [t.get("description", "") for t in validated_tasks]

    # ENHANCEMENT: Load ALL skill and agent definitions for LLM to see
    loader = get_skill_agent_loader()
    all_skills = loader.list_all_skills()  # Dict[skill_name: full_definition]
    all_agents = loader.list_all_agents()  # Dict[agent_name: full_definition]

    # NEW: Include available MCPs (MCP Integration Phase 1)
    available_mcps = state.get("mcp_servers_available", [])
    mcp_filesystem_enabled = state.get("mcp_filesystem_enabled", False)

    # PHASE 2 NEW: Get DeepSeek reasoning about MCP requirements
    deepseek_mcp_reasoning = None
    deepseek_skill_eval = None
    try:
        reasoner = get_deepseek_reasoning()
        deepseek_mcp_reasoning = reasoner.analyze_mcp_requirements(
            user_message=user_message,
            task_type=task_type,
            complexity=complexity,
            available_mcps=available_mcps,
            validated_tasks=validated_tasks,
            patterns=patterns,
        )

        # Also get skill/agent evaluation
        deepseek_skill_eval = reasoner.evaluate_skill_agent_fit(
            user_message=user_message,
            candidate_skills=list(all_skills.keys()),
            candidate_agents=list(all_agents.keys()),
        )
    except Exception:
        # Non-blocking: DeepSeek reasoning failure
        pass

    context_data = {
        "user_message": user_message,
        "task_type": task_type,
        "complexity": complexity,
        "validated_tasks_count": len(validated_tasks),
        "task_descriptions": task_descriptions,
        "patterns_detected": patterns,
        "project_info": {
            "project_root": project_root,
            "is_java_project": is_java,
        },
        "toon_refinement": refined_toon,
        # NEW: Include full skill/agent definitions for informed selection
        "available_skills": list(all_skills.keys()),
        "available_agents": list(all_agents.keys()),
        "skill_definitions": all_skills,  # Full markdown content for all skills
        "agent_definitions": all_agents,  # Full markdown content for all agents
        # NEW: Include available MCPs for context-aware skill selection
        "available_mcps": available_mcps,  # List of discovered MCPs
        "mcp_filesystem_enabled": mcp_filesystem_enabled,  # True if Filesystem MCP available
        # PHASE 2 NEW: Include DeepSeek reasoning if available
        "deepseek_mcp_reasoning": (deepseek_mcp_reasoning.to_dict() if deepseek_mcp_reasoning else None),
        "deepseek_skill_eval": deepseek_skill_eval,
    }

    # Pass task_type, complexity, and a SLIM context via temp file
    # (full context with skill definitions is ~800KB, exceeds Windows 32KB cmd line limit)
    import os
    import tempfile

    # Detect project type for skill matching
    detected_fw = state.get("detected_framework", "")
    if not detected_fw or detected_fw == "unknown":
        detected_fw = _detect_project_type_from_files(project_root)

    slim_context = {
        "user_message": user_message[:500],
        "task_type": task_type,
        "complexity": complexity,
        "project_type": detected_fw,
        "project_root": project_root,
        "available_skills": list(all_skills.keys()),
        "available_agents": list(all_agents.keys()),
        "patterns_detected": patterns,
        "is_java_project": is_java,
    }

    # Write context to temp file to avoid command line length limit
    context_file = None
    try:
        fd, context_file = tempfile.mkstemp(suffix=".json", prefix="step5_ctx_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(slim_context, f)
    except Exception:
        context_file = None

    args = [
        "--analyze",
        f"--task-type={task_type}",
        f"--complexity={complexity}",
    ]
    if context_file:
        args.append(f"--context-file={context_file}")

    result = call_execution_script("auto-skill-agent-selector", args, model_tier="balanced")

    # Cleanup temp file
    if context_file:
        try:
            os.unlink(context_file)
        except Exception:
            pass

    # Support multiple skills/agents from LLM
    selected_skills = result.get("selected_skills", [])
    selected_agents = result.get("selected_agents", [])

    # Backward compat: also check single-value keys
    selected_skill_name = result.get("selected_skill", "")
    selected_agent_name = result.get("selected_agent", "")

    if not selected_skills and selected_skill_name:
        selected_skills = [selected_skill_name]
    if not selected_agents and selected_agent_name:
        selected_agents = [selected_agent_name]

    # Primary skill/agent (first in list) for backward compat
    selected_skill_name = selected_skills[0] if selected_skills else ""
    selected_agent_name = selected_agents[0] if selected_agents else ""

    # --- Cross-session RAG boost: re-rank skills based on historical success ---
    try:
        from ....skill_selection_criteria import _get_rag_skill_boost

        task_info = {"task_type": task_type, "complexity": complexity}
        boosted = []
        for sk in selected_skills:
            boost = _get_rag_skill_boost(task_info, {"name": sk})
            boosted.append((sk, boost))
        # Re-sort if any skill gets meaningful boost
        if any(b > 0.05 for _, b in boosted):
            boosted.sort(key=lambda x: x[1], reverse=True)
            selected_skills = [sk for sk, _ in boosted]
            selected_skill_name = selected_skills[0] if selected_skills else selected_skill_name
    except Exception:
        pass  # RAG boost failure is non-blocking

    # --- Post-selection conflict resolution ---
    # Build minimal skill/agent dicts for ConflictResolver
    skill_conflicts_detected = 0
    skill_conflicts_removed: list = []

    try:
        from ....conflict_resolver import ConflictResolver

        session_dir = state.get("session_dir", ".")
        conflict_resolver = ConflictResolver(session_dir=session_dir)

        # Build list representation for conflict checks
        candidate_items = []
        if selected_skill_name:
            candidate_items.append(
                {
                    "name": selected_skill_name,
                    "capabilities": [],
                    "domain": "general",
                    "exclusive": False,
                    "conflicts_with": [],
                }
            )
        if selected_agent_name:
            candidate_items.append(
                {
                    "name": selected_agent_name,
                    "capabilities": [],
                    "domain": "general",
                    "exclusive": False,
                    "conflicts_with": [],
                }
            )

        # Resolve conflicts in the selected pair
        if candidate_items:
            task_context = {
                "required_capabilities": [],
                "domain": context_data.get("task_type", "general"),
            }
            resolution = conflict_resolver.resolve_skill_conflicts(candidate_items, task=task_context)
            skill_conflicts_detected = resolution.get("conflicts_detected", 0)
            skill_conflicts_removed = resolution.get("removed", [])

            if skill_conflicts_detected > 0:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    f"[Step5] Skill conflicts detected: {skill_conflicts_detected}. "
                    f"Removed: {skill_conflicts_removed}"
                )
                # Persist conflict log
                try:
                    conflict_resolver.save_conflict_log()
                except Exception:
                    pass

                # Clear removed items from selection
                if selected_skill_name in skill_conflicts_removed:
                    selected_skill_name = ""
                if selected_agent_name in skill_conflicts_removed:
                    selected_agent_name = ""

    except Exception as _conflict_err:
        import logging as _logging

        _logging.getLogger(__name__).debug(f"[Step5] ConflictResolver unavailable (non-fatal): {_conflict_err}")

    # Load full definitions for ALL selected skills/agents
    all_skill_defs = []
    for sk in selected_skills:
        sk_def = all_skills.get(sk, "")
        if sk_def:
            all_skill_defs.append(f"### Skill: {sk}\n{sk_def[:2000]}")

    all_agent_defs = []
    for ag in selected_agents:
        ag_def = all_agents.get(ag, "")
        if ag_def:
            all_agent_defs.append(f"### Agent: {ag}\n{ag_def[:2000]}")

    return {
        "step5_skill": selected_skill_name,
        "step5_agent": selected_agent_name,
        "step5_skills": selected_skills,
        "step5_agents": selected_agents,
        "step5_skill_definition": "\n\n".join(all_skill_defs) if all_skill_defs else "",
        "step5_agent_definition": "\n\n".join(all_agent_defs) if all_agent_defs else "",
        "step5_reasoning": result.get("reasoning", ""),
        "step5_confidence": result.get("confidence", 0.5),
        "step5_alternatives": result.get("alternatives", []),
        "step5_llm_query_needed": result.get("llm_needed", False),
        "step5_context_provided": True,
        "step5_task_count": len(validated_tasks),
        "step5_skills_available": len(all_skills),
        "step5_agents_available": len(all_agents),
        "step5_conflicts_detected": skill_conflicts_detected,
        "step5_conflicts_removed": skill_conflicts_removed,
    }
