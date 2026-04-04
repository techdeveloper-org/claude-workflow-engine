# Impact Map: Level 3 Simplification
# Collapse Steps 1-7 into Step 0 + Template
# Produced by: solution-architect
# Date: 2026-04-03

---

## 1. SAFE DELETION ORDER

Delete in this exact sequence to avoid dangling edges in the StateGraph.

### Step 1: Remove orchestrator.py Standards Hook Nodes for Steps 1-7

Remove these `add_node` / `add_edge` calls from `orchestrator.py`:
- `level3_standards_hook_step1` (apply_integration_step1)
- `level3_step1` (step1_plan_mode_decision_node)
- `level3_step2` (step2_plan_execution_node)
- `level3_standards_hook_step2` (apply_integration_step2)
- `level3_step3` (step3_task_breakdown_node)
- `level3_standards_hook_step3` (apply_integration_step3)
- `level3_step4` (step4_toon_refinement_node)
- `level3_standards_hook_step4` (apply_integration_step4)
- `level3_step5` (step5_skill_selection_node)
- `level3_standards_hook_step5` (apply_integration_step5)
- `level3_step6` (step6_skill_validation_node)
- `level3_standards_hook_step6` (apply_integration_step6)
- `level3_step7` (step7_final_prompt_node)
- `level3_standards_hook_step7` (apply_integration_step7)
- Remove `route_after_step1_decision` conditional edges (from step1)
- Remove `apply_integration_step1/2/3/4/5/6/7` function definitions

New wiring after `level3_step0`:
```
level3_step0 -> level3_step8
```
(Remove the old: level3_step0 -> level3_standards_hook_step1 chain)

### Step 2: Update route_pre_analysis targets in orchestrator.py

Current:
- template_fast_path -> "level3_step6"
- RAG hit -> "level3_step5"
- miss -> "level3_step0_0"

New:
- template_fast_path -> "level3_step8"
- RAG hit -> "level3_step8"
- miss -> "level3_step0_0"

Also update `orchestration.py:route_pre_analysis()` to return "level3_step8" for both fast-path cases.

Update the `add_conditional_edges` call in `orchestrator.py` for `level3_pre_analysis`:
```python
graph.add_conditional_edges(
    "level3_pre_analysis",
    route_pre_analysis,
    {
        "level3_step0_0": "level3_step0_0",
        "level3_step8": "level3_step8",   # Was step5 and step6
    },
)
```

### Step 3: Remove imports from orchestrator.py

Remove these imports from `orchestrator.py`:
```python
step1_plan_mode_decision_node,
step3_task_breakdown_node,
step4_toon_refinement_node,
step5_skill_selection_node,
step6_skill_validation_node,
step7_final_prompt_node,
```

Also remove the local function definitions (or mark as REMOVED):
- `apply_integration_step1`
- `apply_integration_step2`
- `apply_integration_step3`
- `apply_integration_step4`
- `apply_integration_step5`
- `apply_integration_step6`
- `apply_integration_step7`
- `route_after_step1_decision`

### Step 4: Update nodes/__init__.py

Remove exports for deleted step nodes:
- `step1_plan_mode_decision_node`
- `step3_task_breakdown_node`
- `step4_toon_refinement_node`
- `step5_skill_selection_node`
- `step6_skill_validation_node`
- `step7_final_prompt_node`
- `route_to_plan_or_breakdown` (only used by Step 1 routing)

Keep:
- `_build_retry_history_context` (used by step10_implementation_note)
- `step8_github_issue_node`
- `step9_branch_creation_node`

### Step 5: Remove routing function from routing/level3_routes.py

Remove:
- `route_after_step1_decision()` — only used by the removed Step 1 conditional edge

Keep:
- `route_after_step11_review()` — still used by Step 11 conditional edge

### Step 6: Update subgraph.py imports

Remove from the `from .nodes import (...)` block:
- `step1_plan_mode_decision_node`
- `step3_task_breakdown_node`
- `step4_toon_refinement_node`
- `step5_skill_selection_node`
- `step6_skill_validation_node`
- `step7_final_prompt_node`
- `route_to_plan_or_breakdown`

Keep:
- `_build_retry_history_context`
- All step 8-14 nodes

### Step 7: Modify Step 0 node (step_wrappers_0to4.py)

See Section 3 (Step 0 Modification Spec) for detailed injection instructions.

### Step 8: Remove node implementation files (do NOT delete files)

The files `step_wrappers_0to4.py` and `step_wrappers_5to9.py` contain shared utilities.
DO NOT delete them. Instead:

In `step_wrappers_0to4.py`:
- Keep `step0_task_analysis_node` (modified per Section 3)
- Remove function bodies for `step1_plan_mode_decision_node`, `step3_task_breakdown_node`,
  `step4_toon_refinement_node` — replace with `# REMOVED: collapsed into Step 0 template`
- Keep `step2_plan_execution_node` AS-IS (Step 2 is NOT removed — it is kept)

In `step_wrappers_5to9.py`:
- Remove function bodies for `step5_skill_selection_node`, `step6_skill_validation_node`,
  `step7_final_prompt_node`
- Keep `step8_github_issue_node`, `step9_branch_creation_node`
- Keep `_build_retry_history_context` (consumed by Step 10)

---

## 2. FLOWSTATE FIELD AUDIT

### Fields Written by Removed Steps and Their Downstream Consumers

#### Fields from Step 1 (step1_plan_mode_decision_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step1_plan_required | Step 1 | YES — orchestrator.py output_node reads it for execution-summary.txt, flow_trace_converter.py, decision_explainer.py, step_validator.py | KEEP, populate from Step 0 template output |
| step1_reasoning | Step 1 | No (observability only) | REMOVE from StepKeys if desired, but harmless to leave |
| step1_error | Step 1 | No | Harmless, leave |
| step1_complexity_score | Step 1 | No | Harmless, leave |

#### Fields from Step 3 (step3_task_breakdown_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step3_tasks_validated | Step 3 | YES — output_node synthesize_prompt_with_flow_data() reads it; step_validator.py | KEEP, populate from Step 0 template output |
| step3_task_count | Step 3 | No (logging only) | Harmless |
| step3_validation_status | Step 3 | No (logging only) | Harmless |
| step3_phase_file_map | Step 3 | No (was consumed by Step 4) | Can leave null |
| step3_graph_snapshot | Step 3 | No | Can leave null |

#### Fields from Step 4 (step4_toon_refinement_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step4_model | Step 4 | YES — flow_trace_converter.py L317, output_node (StepKeys.SELECTED_MODEL), session accumulation | KEEP, populate from Step 0 template output |
| step4_refinement_status | Step 4 | No (logging only) | Harmless |
| step4_complexity_adjusted | Step 4 | No (logging only) | Harmless |
| step4_phase_contexts | Step 4 | No (was consumed internally) | Can leave null |

#### Fields from Step 5 (step5_skill_selection_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step5_skill | Step 5 | YES — output_node, session accumulation, RAG storage, voice flag | KEEP, populate from Step 0 template output |
| step5_agent | Step 5 | YES — output_node, session accumulation, RAG storage | KEEP, populate from Step 0 template output |
| step5_skills | Step 5 | YES — output_node, session accumulation | KEEP, populate from Step 0 template output |
| step5_agents | Step 5 | YES — output_node, session accumulation | KEEP, populate from Step 0 template output |
| step5_skill_definition | Step 5 | YES — synthesize_prompt_with_flow_data() | KEEP, populate from Step 0 template output |
| step5_agent_definition | Step 5 | YES — synthesize_prompt_with_flow_data() | KEEP, populate from Step 0 template output |
| step5_reasoning | Step 5 | No (logging only) | Harmless |

#### Fields from Step 6 (step6_skill_validation_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step6_skill_ready | Step 6 | YES — flow_trace_converter.py, step_validator.py | KEEP, populate from Step 0 with default True |
| step6_agent_ready | Step 6 | No (logging only) | Harmless |
| step6_validation_status | Step 6 | No (logging only) | Harmless |

#### Fields from Step 7 (step7_final_prompt_node)
| Field | Written by | Read by Steps 8-14? | Action |
|-------|-----------|---------------------|--------|
| step7_execution_prompt | Step 7 | YES — step10_implementation_note reads it as `base_prompt` | KEEP, populate from Step 0 template LLM output |
| step7_prompt_saved | Step 7 | YES — output_node checks it | KEEP, set to True in Step 0 |
| step7_system_prompt_file | Step 7 | YES — step10 reads from filesystem | KEEP, Step 0 writes file to disk |
| step7_system_prompt_loaded | Step 7 | No (logging only) | Harmless |
| step7_prompt_file | Step 7 | No (logging only) | Harmless |
| step7_prompt_size | Step 7 | No (logging only) | Harmless |

### Summary: Fields Step 0 MUST Populate for Steps 8-14

Step 0 must populate all of the following after its template LLM call:
```
step1_plan_required       (bool, default False - template decides)
step3_tasks_validated     (list of task dicts, may be empty list)
step4_model               (str, model name e.g. "complex_reasoning")
step5_skill               (str, primary skill name)
step5_agent               (str, primary agent name)
step5_skills              (list of str, all skills)
step5_agents              (list of str, all agents)
step5_skill_definition    (str, skill file content or empty)
step5_agent_definition    (str, agent file content or empty)
step6_skill_ready         (bool, True by default)
step7_execution_prompt    (str, the final LLM prompt for Step 10)
step7_prompt_saved        (bool, True after Step 0 writes it)
step7_system_prompt_file  (str, path to written prompt file)
```

---

## 3. STEP 0 MODIFICATION SPEC

### Target File
`scripts/langgraph_engine/level3_execution/nodes/step_wrappers_0to4.py`
Function: `step0_task_analysis_node(state)`

### Injection Points (add BEFORE the _run_step call)

#### Injection A: Complexity Score from Level 1

```python
# Inject combined_complexity_score from Level 1 (1-25 scale, NOT re-computed)
complexity_score = state.get("combined_complexity_score", 5)
# Note: combined_complexity_score is 1-25, not 1-10. Do not clamp to 10.
```

#### Injection B: CallGraph Analysis

```python
# Inject CallGraph impact analysis
call_graph_risk_level = "LOW"
call_graph_danger_zones = []
call_graph_affected_methods = []
try:
    from ..call_graph_analyzer import analyze_impact_before_change
    project_root = state.get("project_root", ".")
    target_files = state.get("step0_target_files", [])
    task_desc = state.get("user_message", "")
    cg_result = analyze_impact_before_change(project_root, target_files, task_desc)
    if cg_result.get("call_graph_available"):
        call_graph_risk_level = cg_result.get("risk_level", "LOW")
        call_graph_danger_zones = cg_result.get("danger_zones", [])
        call_graph_affected_methods = cg_result.get("affected_methods", [])
except Exception as _cg_exc:
    pass  # Fail-open: CallGraph injection is never fatal
```

#### Injection C: Template Context Dict

The step0 implementation (step0_task_analysis in level3_execution/) builds a template_context
dict before calling the LLM. Add these keys to that dict:

```python
template_context["complexity_score"] = complexity_score
template_context["call_graph_risk_level"] = call_graph_risk_level
template_context["call_graph_danger_zones"] = call_graph_danger_zones
template_context["call_graph_affected_methods"] = call_graph_affected_methods
```

#### Injection D: After LLM Call - Populate Fields for Steps 8-14

After the LLM call returns `result`, add:

```python
# Populate fields that removed steps (1,3,4,5,6,7) used to provide
# so Steps 8-14 receive correct data from the consolidated Step 0.
result.setdefault("step1_plan_required", False)
result.setdefault("step3_tasks_validated", result.get("step0_tasks", {}).get("tasks", []))
result.setdefault("step4_model", result.get("step0_model_recommendation", "complex_reasoning"))
result.setdefault("step5_skill", result.get("step0_selected_skill", ""))
result.setdefault("step5_agent", result.get("step0_selected_agent", ""))
result.setdefault("step5_skills", result.get("step0_skills", []))
result.setdefault("step5_agents", result.get("step0_agents", []))
result.setdefault("step5_skill_definition", "")
result.setdefault("step5_agent_definition", "")
result.setdefault("step6_skill_ready", True)
# step7_execution_prompt: the template output IS the execution prompt
result.setdefault("step7_execution_prompt", result.get("step0_prompt", ""))
result.setdefault("step7_prompt_saved", bool(result.get("step7_execution_prompt")))
```

Also write the execution prompt to disk (what Step 7 used to do):
```python
try:
    session_dir = state.get("session_dir", "")
    if session_dir and result.get("step7_execution_prompt"):
        from pathlib import Path as _Path
        sp_file = _Path(session_dir) / "system_prompt.txt"
        sp_file.parent.mkdir(parents=True, exist_ok=True)
        sp_file.write_text(result["step7_execution_prompt"], encoding="utf-8")
        result["step7_system_prompt_file"] = str(sp_file)
except Exception:
    pass  # Non-blocking
```

---

## 4. ROUTING FUNCTION CHANGES

### orchestration.py - route_pre_analysis()

Current:
```python
if state.get("template_fast_path"):
    return "level3_step6"
if state.get("rag_orchestration_hit") and state.get("skip_architecture"):
    return "level3_step5"
return "level3_step0_0"
```

New:
```python
if state.get("template_fast_path"):
    return "level3_step8"
if state.get("rag_orchestration_hit") and state.get("skip_architecture"):
    return "level3_step8"
return "level3_step0_0"
```

Also update the print statement in orchestration.py that says "-> jumping to Step 6" to say "-> jumping to Step 8".

### orchestrator.py - add_conditional_edges for level3_pre_analysis

Current:
```python
graph.add_conditional_edges(
    "level3_pre_analysis",
    route_pre_analysis,
    {
        "level3_step0_0": "level3_step0_0",
        "level3_step5": "level3_step5",
        "level3_step6": "level3_step6",
    },
)
```

New:
```python
graph.add_conditional_edges(
    "level3_pre_analysis",
    route_pre_analysis,
    {
        "level3_step0_0": "level3_step0_0",
        "level3_step8": "level3_step8",
    },
)
```

### orchestrator.py - Wiring after Step 0

Remove:
```python
graph.add_node("level3_standards_hook_step1", apply_integration_step1)
graph.add_edge("level3_step0", "level3_standards_hook_step1")
graph.add_node("level3_step1", step1_plan_mode_decision_node)
graph.add_edge("level3_standards_hook_step1", "level3_step1")
graph.add_conditional_edges("level3_step1", route_after_step1_decision, {...})
# ... all step2 through step7 nodes and edges
```

Add:
```python
graph.add_edge("level3_step0", "level3_step8")
```

### orchestrator.py - Hook mode path

In hook_mode, the terminal edge was `level3_step9 -> level3_merge`. This stays unchanged.
However, note that steps 8 and 9 are NOW the direct successors of step 0, so hook mode
still works correctly (runs step 0 -> step 8 -> step 9 -> merge -> output).

### routing/level3_routes.py

Remove the entire `route_after_step1_decision()` function.
Keep `route_after_step11_review()`.

### routing/__init__.py

Remove the export of `route_after_step1_plan_decision` or `route_after_step1_decision`.

---

## 5. ADDITIONAL FILES THAT REFERENCE REMOVED STEPS

These files contain references to removed step fields or names. They do NOT need to be
broken; they degrade gracefully since all state.get() calls have defaults. However,
for observability correctness, note:

- `helper_nodes/output_helpers.py`: References step1, step3, step4, step5, step6 in
  logging table. These will show empty/default values. Acceptable — do not modify.
- `flow_trace_converter.py`: References step1, step4, step5, step6 fields. These are
  populated by Step 0 migration (see Section 2), so they will have correct values.
- `orchestrator.py:_save_pipeline_execution_log()`: References step1-step7 in step_info
  table. Fields populated by Step 0 migration will show correctly; others will show "-".
  Update the step_info list to remove steps 1, 3, 4, 5, 6, 7 entries.
- `decision_explainer.py`: Reads step1_plan_required and step5_skill — both migrated.
- `user_interaction.py`: Reads step5_skill — migrated.
- `step_validator.py`: Validates step1_plan_required, step3_tasks, step5_skills,
  step6_skill_ready, step7_execution_prompt — all migrated to Step 0 output.
- `checkpoint_manager.py`: Has hardcoded references in test fixture data. Tests using
  these will still pass since the fields exist (populated by Step 0).
- `pipeline_builder.py`: Imports and registers step5_skill_selection_node. Remove the
  import and the graph.add_node("level3_step5", ...) call.

---

## 6. BACKWARD-COMPAT SHIMS (DO NOT TOUCH)

The following shim files must NOT be modified or deleted:
- `scripts/langgraph_engine/flow_state.py` — shim -> state/
- `scripts/langgraph_engine/uml_generators.py` — shim -> diagrams/
- `scripts/langgraph_engine/call_graph_builder.py` — shim -> parsers/

None of these shims reference the removed step nodes. Confirmed safe.

---

## 7. PIPELINE_BUILDER.PY CHANGES

`pipeline_builder.py` has its own Level 3 graph construction logic independent of orchestrator.py.
It imports and registers `step5_skill_selection_node` on line 82 and 366.

Changes required:
1. Remove the import of `step5_skill_selection_node` from the import block (line 82)
2. Remove the `g.add_node("level3_step5", step5_skill_selection_node)` call (line 366)
3. Rewire the edge from step0 to step8 in the PipelineBuilder.add_level3() method

---

## 8. ARCHITECTURAL DECISION RECORD (ADR-001)

### ADR-001: Collapse Level 3 Steps 1-7 into Step 0 + Orchestration Prompt Template

**Date:** 2026-04-03
**Status:** ACCEPTED

**Context:**
The Level 3 execution pipeline originally had 15 steps (Step 0 through Step 14).
Steps 1-7 performed sequential LLM-based planning: plan mode decision, plan execution,
task breakdown, TOON refinement, skill selection, skill validation, and prompt generation.
Each step was an independent LLM call (~1 per step = 6 LLM calls total for Steps 1-7).

A prompt-generation-expert produced an orchestration prompt template that consolidates
all planning outputs (skill selection, agent selection, task breakdown, prompt generation,
complexity assessment, plan mode decision) into a single structured LLM call executed
in Step 0.

**Decision:**
Remove Steps 1, 3, 4, 5, 6, 7 from the StateGraph.
Modify Step 0 to inject combined_complexity_score (from Level 1, 1-25 scale) and
CallGraph analysis before the template LLM call.
Step 0 single LLM call produces all outputs that Steps 1-7 previously produced.
Step 2 (Plan Execution / impact analysis) is retained because it provides structural
plan data consumed directly by Step 10 (Implementation) and Step 11 (PR/Review).
The new pipeline path is: Pre-0 -> Step 0 -> Step 8 -> Step 9 -> Step 10 -> Step 11
-> Step 12 -> Step 13 -> Step 14 -> END.

**Rationale:**
- Reduces planning LLM calls from ~6 to ~1 (83% reduction in planning LLM calls)
- Estimated time saving: 60-90 seconds per run
- The orchestration template encodes the planning logic that required sequential LLM calls
- CallGraph and complexity data are now injected into the template context rather than
  being intermediate step outputs

**Risks:**
- Step 0 template must produce all required fields for Steps 8-14 compatibility
- Migration fields (step5_skill, step7_execution_prompt, etc.) must be correctly populated
- fast-path routing (template and RAG hit) now jumps to Step 8 instead of Step 5/6

**Accepted Risks Mitigated By:**
- All fields use state.setdefault() with safe defaults
- step7_execution_prompt falls back to empty string (Step 10 handles empty prompt gracefully)
- step6_skill_ready defaults to True (non-blocking default in original Step 6 fallback)

---

## 9. TEST IMPACT

Tests that will need updates (do NOT modify test files now - flag for qa-testing-agent):

- `tests/test_level3_execution.py`: Imports `step1_plan_mode_decision_node`,
  `step3_task_breakdown_node`, etc. These will fail import if functions are deleted.
  Resolution: Keep stub/removed function stubs in files, or update test imports.

- `tests/test_level3_remaining_steps.py`: May reference step5-7 nodes.

- Any test that asserts `route_pre_analysis` returns "level3_step5" or "level3_step6"
  must be updated to expect "level3_step8".

---

## 10. REVISED PIPELINE FLOW (for CLAUDE.md update)

```
Level 3: Execution (9 meaningful steps: Pre-0, Step 0, Steps 8-14)
    |-- Pre-0: Orchestration Pre-Analysis (Template check + CallGraph scan + RAG lookup)
    |           Template provided -> skip Step 0, jump to Step 8 (~1 LLM call saved)
    |           RAG hit (>=0.85) -> skip Step 0, jump to Step 8 (~1 LLM call saved)
    |           RAG miss -> normal flow
    |-- Step 0:  Task Analysis + Orchestration Template
    |            (complexity from Level 1 1-25 scale + CallGraph injection)
    |            (Single LLM call produces: skill, agent, tasks, prompt, model, plan_required)
    |-- Step 8:  GitHub Issue + Jira Issue creation (ENABLE_JIRA, dual-linked)
    |-- Step 9:  Branch Creation (Jira key: feature/PROJ-123)
    |-- Step 10: Implementation + Jira "In Progress" + Figma "started" comment
    |-- Step 11: PR + Code Review + Jira PR link + Figma design review
    |-- Step 12: Issue Closure (GitHub + Jira "Done" + Figma "complete" comment)
    |-- Step 13: Documentation Update + UML Diagram Generation
    |-- Step 14: Final Summary
```

Step count change: 15 steps -> 9 steps (removed: Step 1, 3, 4, 5, 6, 7 + 6 standards hooks)
LLM calls during planning: ~6 -> ~1 (Step 0 template call only)
