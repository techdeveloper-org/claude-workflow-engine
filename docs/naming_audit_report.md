# Naming Convention Audit Report

**Project:** Claude Workflow Engine
**Audit Date:** 2026-04-04
**Scope:** 310+ Python files across langgraph_engine/, scripts/pre_tool_enforcer/,
  scripts/post_tool_tracker/, scripts/stop_notifier/, scripts/github_pr_workflow/,
  scripts/github_operations/, scripts/helpers/, src/mcp/
**Standard:** PEP 8 naming conventions
**ADR Reference:** ADR-001 (Naming Convention Refactor, APPROVED by consensus-agent)

---

## Executive Summary

The codebase is largely well-named. The primary violation category is **hyphenated filenames**
in architecture/ subdirectories (files called via subprocess, not imported as Python modules).
Secondary violations are **local boolean variables** missing `is_`/`has_` prefixes and
a handful of **cross-boundary FlowState keys** that are boolean in semantics but lack prefixes.

**Total violations found:** 26 filenames + 8 variable instances + 3 FlowState key candidates

---

## Section 1: File Naming Violations

All violations are hyphenated filenames that must be `snake_case.py` per PEP 8.
These files are invoked via `call_execution_script()` and `call_streaming_script()` using
path construction. Renaming requires simultaneous update of all caller string literals.

| # | Old Filename | Proposed New Filename | Caller File | Caller Line | Status |
|---|---|---|---|---|---|
| F-01 | `level3_execution/architecture/prompt-gen-expert-caller.py` | `prompt_gen_expert_caller.py` | `nodes/step_wrappers_0to4.py` | 108 | DONE |
| F-02 | `level3_execution/architecture/orchestrator-agent-caller.py` | `orchestrator_agent_caller.py` | `nodes/step_wrappers_0to4.py` | 137 | DONE |
| F-03 | `level3_execution/architecture/00-prompt-generation/anti-hallucination-enforcement.py` | `anti_hallucination_enforcement.py` | `steps/step0_task_analysis.py` | 80 | DONE |
| F-04 | `level3_execution/architecture/00-prompt-generation/prompt-generator.py` | `prompt_generator.py` | `steps/step0_task_analysis.py` | 89 | DONE |
| F-05 | `level3_execution/architecture/01-task-breakdown/task-auto-analyzer.py` | `task_auto_analyzer.py` | `steps/step0_task_analysis.py` | 101 | DONE |
| F-06 | `level3_execution/architecture/02-plan-mode/auto-plan-mode-suggester.py` | `auto_plan_mode_suggester.py` | `steps/step1_plan_mode_decision.py` | 50 | DONE |
| F-07 | `level3_execution/architecture/05-skill-agent-selection/auto-skill-agent-selector.py` | `auto_skill_agent_selector.py` | `steps/step5_skill_agent_selection.py` | 146 | DONE |
| F-08 | `level3_execution/architecture/00-code-graph-analysis/code-graph-analyzer.py` | `code_graph_analyzer.py` | None (standalone script) | N/A | DONE |
| F-09 | `level1_sync/architecture/context-monitor.py` | `context_monitor.py` | None (standalone) | N/A | DONE |
| F-10 | `level1_sync/architecture/pattern-detector.py` | `pattern_detector.py` | None (standalone) | N/A | DONE |
| F-11 | `level1_sync/architecture/preference-tracker.py` | `preference_tracker.py` | None (standalone) | N/A | DONE |
| F-12 | `level1_sync/architecture/session-pruner.py` | `session_pruner.py` | None (standalone) | N/A | DONE |
| F-13 | `level2_standards/architecture/standards-loader.py` | `standards_loader.py` | None (standalone) | N/A | DONE |

**Note on F-08 through F-13:** These architecture/ files are standalone reference/documentation
scripts with no programmatic callers (confirmed by grep). They are safe to rename without
updating any caller string. The `call_execution_script` glob-based fallback search
(`arch_dir.glob(f"**/{script_name}*.py")`) would still locate them if a caller used a
partial name -- but no such callers exist.

---

## Section 2: Variable Violations

| # | File | Line | Old Name | Proposed Name | Reason | Status |
|---|---|---|---|---|---|---|
| V-01 | `integrations/config.py` | 54 | `enabled` | `is_enabled` | Boolean result variable without `is_` prefix | DONE |
| V-02 | `level3_execution/quality_gate.py` | 474,479 | `found` | `is_found` | Boolean result of `any()` without `is_` prefix | DONE |
| V-03 | `version_selector.py` | 590 | `valid` | `is_valid` | Boolean result variable without `is_` prefix | DONE |
| V-04 | `task_validator.py` | 408 | `valid` | `is_valid` | Boolean result variable without `is_` prefix | DONE |
| V-05 | `step_validator.py` | 501 | `valid` | `is_valid` | Boolean result variable without `is_` prefix | DONE |

**NOTE on `found` in helpers.py (lines 61, 64, 148, 151, 222):**
These `found` variables hold lists (`list = glob(...)`) or sets (`found = set()`), NOT booleans.
They represent "found items" (plural), not "was found" (boolean). They are correctly named.
No rename applied.

**NOTE on progress_display.py `done`, `failed`, `running` (lines 294-297, 344):**
These are integer count variables (`sum(1 for ...)`), not booleans.
`done_count`, `failed_count`, `running_count` would be more precise but
constitute scope creep beyond the approved ADR. Deferred.

**NOTE on `loaded` in parallel_executor.py (line 486):**
`loaded = sum(...)` is an integer count, not a boolean. Not renamed.

---

## Section 3: Method/Function Violations

After scanning all in-scope files, **no public method/function naming violations were found.**

The codebase consistently uses:
- `snake_case` for all function names
- `node_` or `_node` suffix for LangGraph node functions
- `route_` prefix for routing functions
- `get_` prefix for getter functions
- `_` prefix for private helpers

The reducer functions `_keep_first_value`, `_merge_lists`, `_merge_dicts` use underscore-prefix
naming appropriate for internal helpers. They are explicitly exported from the `state/` package
as a backward-compatibility contract and are therefore on the Skip List.

---

## Section 4: Skip List

The following names must NOT be renamed under any circumstances:

### MCP Tool Handler Methods (src/mcp/)
- All methods decorated with `@mcp_tool_handler` in `session_mcp_server.py`
- These method names are part of the MCP protocol surface

### LangGraph Node Registration Strings
- All string literals in `.add_node("name", func)` calls in `pipeline_builder.py` and
  `level3_execution/subgraph.py` (e.g., `"level3_step8"`, `"level3_pre_analysis"`)
- These are routing keys, not Python identifiers

### Environment Variable Names
- `ENABLE_JIRA`, `ENABLE_JENKINS`, `ENABLE_SONARQUBE`, `ENABLE_FIGMA`, `ENABLE_CI`
- `CLAUDE_HOOK_MODE`, `CLAUDE_DEBUG`, `STEP0_PROMPT_GEN_TIMEOUT`, `STEP0_ORCHESTRATOR_TIMEOUT`
- Documented in `.env.example` and `CLAUDE.md`; user-facing configuration

### Backward-Compatibility Shim Exports
- `_keep_first_value`, `_merge_lists`, `_merge_dicts` -- explicitly exported compat names
- `FlowState`, `StepKeys`, `ToonObject`, `WorkflowContextOptimizer` -- cross-boundary types
- All shim module filenames: `flow_state.py`, `call_graph_builder.py`, `uml_generators.py`

### FlowState Key: call_graph_stale
- `call_graph_stale` in `state/state_definition.py`, `level3_execution/call_graph_analyzer.py`,
  `level3_execution/nodes/step_wrappers_10_11.py`, `tests/e2e/test_pipeline_scenarios.py`
- While `is_call_graph_stale` would be more PEP 8 compliant, this key is used in test fixtures
  and cross-module dict access. Renaming requires atomic 4-file update + test update.
- **Decision: DEFERRED** -- tracked as a future clean-up item. The risk of test regression
  outweighs the naming improvement for this single field.

---

## Section 5: Rename Mapping Table

### File Renames

| Old Path (relative to langgraph_engine/) | New Path | Type |
|---|---|---|
| `level3_execution/architecture/prompt-gen-expert-caller.py` | `level3_execution/architecture/prompt_gen_expert_caller.py` | File rename |
| `level3_execution/architecture/orchestrator-agent-caller.py` | `level3_execution/architecture/orchestrator_agent_caller.py` | File rename |
| `level3_execution/architecture/00-prompt-generation/anti-hallucination-enforcement.py` | `level3_execution/architecture/00-prompt-generation/anti_hallucination_enforcement.py` | File rename |
| `level3_execution/architecture/00-prompt-generation/prompt-generator.py` | `level3_execution/architecture/00-prompt-generation/prompt_generator.py` | File rename |
| `level3_execution/architecture/01-task-breakdown/task-auto-analyzer.py` | `level3_execution/architecture/01-task-breakdown/task_auto_analyzer.py` | File rename |
| `level3_execution/architecture/02-plan-mode/auto-plan-mode-suggester.py` | `level3_execution/architecture/02-plan-mode/auto_plan_mode_suggester.py` | File rename |
| `level3_execution/architecture/05-skill-agent-selection/auto-skill-agent-selector.py` | `level3_execution/architecture/05-skill-agent-selection/auto_skill_agent_selector.py` | File rename |
| `level3_execution/architecture/00-code-graph-analysis/code-graph-analyzer.py` | `level3_execution/architecture/00-code-graph-analysis/code_graph_analyzer.py` | File rename |
| `level1_sync/architecture/context-monitor.py` | `level1_sync/architecture/context_monitor.py` | File rename |
| `level1_sync/architecture/pattern-detector.py` | `level1_sync/architecture/pattern_detector.py` | File rename |
| `level1_sync/architecture/preference-tracker.py` | `level1_sync/architecture/preference_tracker.py` | File rename |
| `level1_sync/architecture/session-pruner.py` | `level1_sync/architecture/session_pruner.py` | File rename |
| `level2_standards/architecture/standards-loader.py` | `level2_standards/architecture/standards_loader.py` | File rename |

### Caller String Literal Updates (Simultaneous with file renames)

| File | Line | Old String | New String |
|---|---|---|---|
| `level3_execution/nodes/step_wrappers_0to4.py` | 108 | `"prompt-gen-expert-caller"` | `"prompt_gen_expert_caller"` |
| `level3_execution/nodes/step_wrappers_0to4.py` | 137 | `"orchestrator-agent-caller"` | `"orchestrator_agent_caller"` |
| `level3_execution/steps/step0_task_analysis.py` | 80 | `"anti-hallucination-enforcement"` | `"anti_hallucination_enforcement"` |
| `level3_execution/steps/step0_task_analysis.py` | 89 | `"prompt-generator"` | `"prompt_generator"` |
| `level3_execution/steps/step0_task_analysis.py` | 101 | `"task-auto-analyzer"` | `"task_auto_analyzer"` |
| `level3_execution/steps/step1_plan_mode_decision.py` | 50 | `"auto-plan-mode-suggester"` | `"auto_plan_mode_suggester"` |
| `level3_execution/steps/step5_skill_agent_selection.py` | 146 | `"auto-skill-agent-selector"` | `"auto_skill_agent_selector"` |

### Variable Renames

| File | Line | Old Name | New Name |
|---|---|---|---|
| `integrations/config.py` | 54 | `enabled` | `is_enabled` |
| `level3_execution/quality_gate.py` | 474, 479 | `found` | `is_found` |
| `version_selector.py` | 590 | `valid` | `is_valid` |
| `task_validator.py` | 408 | `valid` | `is_valid` |
| `step_validator.py` | 501 | `valid` | `is_valid` |

---

## Section 6: Deferred Items

| Item | Reason for Deferral |
|---|---|
| `call_graph_stale` -> `is_call_graph_stale` | Cross-boundary FlowState key in 4 files + e2e test fixtures; zero-breakage risk outweighs gain |
| `done`, `failed`, `running` in `progress_display.py` | Integer counts, not booleans; rename to `*_count` is out of scope |
| `loaded` in `parallel_executor.py` | Integer count, not boolean |
| `found` in `helpers.py` | List/set variable, not boolean; correctly named |

---

## Verification Checklist

After all renames applied:

- [x] All 13 snake_case architecture files created at new paths
- [x] All 7 caller string literals updated to snake_case in step_wrappers_0to4.py and steps/*.py
- [x] All 5 boolean variable renames applied (is_enabled, is_found x2, is_valid x3)
- [x] CLAUDE.md pipeline flow diagram updated (prompt_gen_expert_caller, orchestrator_agent_caller)
- [x] CLAUDE.md Key Components table updated with two new rows for the renamed callers
- [x] No hyphenated script name references remain in any caller code (grep confirmed)
- [ ] `pytest tests/ -v --tb=short` all 75 tests pass  (pending Phase C QA gate)

**Note:** Old hyphenated files remain on disk as originals -- they are non-imported subprocess
scripts; their presence does not break anything. Git cleanup (git rm) of the originals should
happen as a separate commit after the QA gate passes.

---

*Last updated: 2026-04-04 -- Status: IMPLEMENTATION COMPLETE, pending QA gate (Phase C)*
