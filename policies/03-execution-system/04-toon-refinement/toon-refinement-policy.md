# TOON Refinement Policy - Step 4

**Version:** 1.0.0
**Part of:** Level 3: Execution System (15 Steps: 0-14)
**Step:** 4 - TOON Refinement
**Status:** Active
**Date:** 2026-03-17

---

## Overview

Step 4 enriches the initial TOON (Token-Optimized Object Notation) created during Level 1 with full task context from Steps 0-3. This produces a comprehensive TOON that drives accurate skill/agent selection in Step 5.

**Input:** Level 1 TOON (basic project context)
**Output:** Refined TOON with task-specific insights

---

## Policy Scope

**Applies to:** Level 3: Execution System, Step 4
**Predecessor:** Step 3 (Task/Phase Breakdown)
**Successor:** Step 5 (Skill & Agent Selection)
**RAG Threshold:** 0.82 (default)

---

## Refinement Process

### 4.1 Gather Context from Prior Steps

TOON refinement MUST incorporate data from ALL preceding steps:

| Source | State Key | Data Extracted |
|--------|-----------|----------------|
| Level 1 | `level1_context_toon` | Base TOON (project structure, tech stack) |
| Step 0 | `step0_task_type`, `step0_complexity` | Task classification and complexity score |
| Step 2 | `step2_plan_execution` | Plan phases and estimated steps (if planning enabled) |
| Step 3 | `step3_tasks_validated` | Validated task breakdown with files and dependencies |
| Level 1 | `patterns_detected` | Detected technology patterns |

### 4.2 Enrichment Rules

The refined TOON MUST include:

1. **Task File Estimates**
   - Extract unique files from all validated tasks
   - Set `estimated_files` count
   - Flag `has_dependencies` if any task has dependencies

2. **Task Descriptions**
   - Collect description from each validated task
   - Store as `task_descriptions` array for skill matching

3. **Plan Insights** (if Step 2 produced a plan)
   - `planned_phases` - Number of execution phases
   - `planned_steps` - Estimated step count from plan

4. **Pattern Integration**
   - Copy `detected_patterns` from Level 1 patterns
   - These drive skill selection accuracy in Step 5

5. **Complexity Adjustment**
   - Formula: `adjusted_complexity = min(10, base_complexity + (task_count - 1) // 2)`
   - More tasks = higher adjusted complexity
   - Capped at 10

### 4.3 Skip Conditions

TOON refinement is SKIPPED when:
- `level1_context_toon` is empty or missing (Level 1 failed)
- Status returns `SKIPPED` (not `OK`)

When skipped, the pipeline continues with the unrefined Level 1 TOON.

---

## Output State Keys

| Key | Type | Description |
|-----|------|-------------|
| `step4_toon_refined` | dict | Complete refined TOON object |
| `step4_refinement_status` | str | `OK`, `SKIPPED`, or `ERROR` |
| `step4_complexity_adjusted` | int | Adjusted complexity (1-10) |
| `step4_context_provided` | bool | Whether full context was used |
| `step4_tasks_included` | int | Number of tasks incorporated |

---

## Quality Requirements

1. **Refinement MUST be deterministic** - Same inputs produce same TOON
2. **No LLM calls** - Step 4 is pure data transformation (fast, no inference cost)
3. **Preserve base TOON** - Never remove Level 1 fields, only add/enhance
4. **Store full context** - `refinement_context` key preserves all input data for debugging

---

## Error Handling

- On exception: Return `step4_refinement_status: "ERROR"` with error details
- Pipeline continues with unrefined TOON (graceful degradation)
- Error is logged but does NOT block Steps 5-14

---

## Implementation Reference

- **Node function:** `step4_toon_refinement_node()` in `subgraphs/level3_execution_v2.py`
- **Core logic:** `step4_toon_refinement()` in `subgraphs/level3_execution.py`
- **TOON schema:** `langgraph_engine/toon_schema.py`
- **TOON models:** `langgraph_engine/toon_models.py`
