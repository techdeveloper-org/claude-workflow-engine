# Architecture Script Mapping Policy

**Version:** 2.0.0
**Last Updated:** 2026-03-17
**Total Architecture Scripts:** 6 (scripts/architecture/)

---

## Overview

This document maps all scripts that physically exist in `scripts/architecture/` to their pipeline step, purpose, and current execution status.

**Important Migration Note:** The original architecture (v1.0.0) documented 65 scripts, the vast majority of which have been migrated into the LangGraph orchestration engine at `scripts/langgraph_engine/`. Only 6 scripts remain in `scripts/architecture/` as standalone modules. These 6 scripts are imported or invoked by the LangGraph subgraph nodes rather than by the old hook chain.

---

## Existing Architecture Scripts (6 Scripts)

### Level 02: Standards System

| Script | Path | Pipeline Step | Purpose |
|--------|------|--------------|---------|
| `standards-loader.py` | `scripts/architecture/02-standards-system/` | Level 2 - Standards loading | Loads all coding standards and project-specific rules; called by `subgraphs/level2_standards.py` |

---

### Level 03: Execution System

#### Step 0 - Prompt Generation (2 scripts)

| Script | Path | Pipeline Step | Purpose |
|--------|------|--------------|---------|
| `anti-hallucination-enforcement.py` | `scripts/architecture/03-execution-system/00-prompt-generation/` | Step 0 - Task analysis | Enforces anti-hallucination constraints during prompt construction |
| `prompt-generator.py` | `scripts/architecture/03-execution-system/00-prompt-generation/` | Step 0 and Step 7 - Prompt generation | Generates structured prompts; called at task analysis and again at final prompt generation with full skill context |

#### Step 1 - Task Breakdown (1 script)

| Script | Path | Pipeline Step | Purpose |
|--------|------|--------------|---------|
| `task-auto-analyzer.py` | `scripts/architecture/03-execution-system/01-task-breakdown/` | Step 3 - Task/Phase breakdown | Automatic task breakdown and complexity analysis; feeds phase decomposition in Level 3 |

#### Step 2 - Plan Mode (1 script)

| Script | Path | Pipeline Step | Purpose |
|--------|------|--------------|---------|
| `auto-plan-mode-suggester.py` | `scripts/architecture/03-execution-system/02-plan-mode/` | Step 1 - Plan mode decision | Decides whether plan mode is required based on task complexity; input to `level3_step1_planner.py` |

#### Step 5 - Skill and Agent Selection (1 script)

| Script | Path | Pipeline Step | Purpose |
|--------|------|--------------|---------|
| `auto-skill-agent-selector.py` | `scripts/architecture/03-execution-system/05-skill-agent-selection/` | Step 5 - Skill and agent selection | Selects appropriate skills and agents for the task; enhanced with RAG cross-session boost in Level 3 v2 |

---

### Data Files (not scripts)

| File | Path | Purpose |
|------|------|---------|
| `failure-kb.json` | `scripts/architecture/03-execution-system/failure-prevention/` | Knowledge base of known failure patterns and solutions; read by `rag_integration.py` and failure prevention nodes |

---

## Migration: What Happened to the Other 59 Scripts

All scripts that existed in the original v1.0.0 policy (65 total) but are no longer present in `scripts/architecture/` have been migrated into the LangGraph engine modules at `scripts/langgraph_engine/`. Below is the mapping of major functional areas to their LangGraph equivalents.

| Original Functional Area | Migrated To (scripts/langgraph_engine/) |
|--------------------------|----------------------------------------|
| Session management (session-loader, session-state, auto-save, archive) | `session_manager.py`, `checkpoint_manager.py`, `backup_manager.py` |
| Context management (context-monitor, context-pruner) | `context_cache.py`, `context_deduplicator.py`, `token_manager.py` |
| User preferences (load-preferences, preference-detector) | `skill_selection_criteria.py`, `patterns.py` |
| Pattern detection (detect-patterns, apply-patterns) | `rag_integration.py` (RAG-based pattern matching) |
| Model selection (model-auto-selector, intelligent-model-selector) | `version_selector.py`, `inference_router.py`, `hybrid_inference.py` |
| Tool optimization (tool-usage-optimizer, smart-read, ast-navigator) | `subgraphs/level2_standards.py` tool optimization section |
| Failure prevention (pre-execution-checker, failure-detector, failure-learner) | `recovery_handler.py`, `error_logger.py`, `rag_integration.py` |
| Git commit (auto-commit-enforcer, auto-commit-detector, auto-commit) | `git_operations.py`, `github_facade.py` |
| GitHub integration (github-issue, pr-workflow) | `github_integration.py`, `subgraphs/level3_steps8to12_github.py` |
| Progress tracking (check-incomplete-work) | `progress_display.py`, `step_logger.py` |
| Skill management (skill-detector, skill-manager, core-skills-enforcer) | `skill_manager.py`, `skill_agent_loader.py` |

---

## Pipeline Step Reference

The 6 remaining architecture scripts map to these LangGraph Level 3 steps:

```
Level 2: Standards
  standards-loader.py          -> Level2Standards node

Level 3 Execution:
  Step 0:  prompt-generator.py              (Task Analysis + Prompt)
           anti-hallucination-enforcement.py (Anti-hallucination constraints)
  Step 1:  auto-plan-mode-suggester.py      (Plan Mode Decision)
  Step 3:  task-auto-analyzer.py            (Task/Phase Breakdown)
  Step 5:  auto-skill-agent-selector.py     (Skill and Agent Selection)
  Step 7:  prompt-generator.py              (Final Prompt - called again with skill context)
```

For the complete 15-step pipeline (Steps 0-14), see:
- `scripts/langgraph_engine/subgraphs/level3_execution_v2.py` (ACTIVE)
- `scripts/langgraph_engine/orchestrator.py` (main StateGraph)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Scripts remaining in scripts/architecture/ | 6 |
| Data files in scripts/architecture/ | 1 (failure-kb.json) |
| Scripts migrated to scripts/langgraph_engine/ | ~59 |
| LangGraph engine modules (scripts/langgraph_engine/) | 70+ |

---

## Version History

- **v2.0.0** (2026-03-17): Rewrite to reflect actual filesystem state after mass migration
  - Removed all 59 references to non-existent scripts
  - Documented the 6 scripts that actually exist in scripts/architecture/
  - Added migration table mapping original scripts to LangGraph equivalents
  - Updated pipeline step references to match Level 3 v2 (15-step pipeline)
- **v1.0.0** (2026-02-28): Initial mapping of 65 architecture scripts (now stale; most migrated to langgraph_engine/)
