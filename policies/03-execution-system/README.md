# EXECUTION SYSTEM (Implementation Layer)

**PURPOSE:** Execute tasks following loaded standards from Rules/Standards System
**VERSION:** 2.0.0 (Updated for 15-step pipeline: Steps 0-14)
**DATE:** 2026-03-17

---

## What This System Does

**Executes 15 Steps in Order (Step 0 through Step 14):**

| Step | Name | Folder | Description |
|------|------|--------|-------------|
| 0 | Task Analysis + Prompt Generation | `00-prompt-generation/` | Convert natural language to structured prompt |
| 1 | Plan Mode Decision | `02-plan-mode/` | Auto-suggest plan mode based on complexity |
| 2 | Plan Execution | `02-plan-mode/` | Execute plan if complexity warrants it |
| 3 | Task/Phase Breakdown | `01-task-breakdown/` | Divide into phases and validated tasks |
| 4 | TOON Refinement | `04-toon-refinement/` | Enrich TOON with full task context |
| 5 | Skill & Agent Selection | `05-skill-agent-selection/` | Auto-select skills and agents |
| 6 | Skill Validation & Download | `06-tool-optimization/` | Validate and optimize tool usage |
| 7 | Final Prompt Generation | `00-prompt-generation/` | Generate system_prompt.txt + user_message.txt |
| 8 | GitHub Issue Creation | `github-issues-integration-policy.md` | Create semantic GitHub issue |
| 9 | Branch Creation + Git Setup | `09-git-commit/` | Create feature branch and git setup |
| 10 | Implementation Execution | `10-implementation-execution/` | Execute tasks with system prompt context |
| 11 | Pull Request & Code Review | `github-branch-pr-policy.md` | Create PR and review loop (max 3 retries) |
| 12 | Issue Closure | `12-issue-closure/` | Close GitHub issue with summary |
| 13 | Documentation Update | `13-documentation-update/` | Update CLAUDE.md and session docs |
| 14 | Final Summary | `14-final-summary/` | Generate execution summary + voice notification |

**OUTPUT:** Code generated with standards compliance, documented, and merged

---

## Sub-Folders (Organized by Step)

```
03-execution-system/
|-- 00-prompt-generation/           Step 0+7: Structured prompts
|   |-- prompt-generation-policy.md
|   +-- anti-hallucination-enforcement.md
|
|-- 00-code-graph-analysis/         Step 0: Code complexity analysis
|   +-- code-graph-analysis-policy.md
|
|-- 00-context-reading/             Step 0: Context/tech stack reading
|   +-- context-reading-policy.md
|
|-- 01-task-breakdown/              Step 3: Phases & tasks
|   +-- automatic-task-breakdown-policy.md
|
|-- 02-plan-mode/                   Steps 1-2: Plan mode decision & execution
|   +-- auto-plan-mode-suggestion-policy.md
|
|-- 04-model-selection/             Model Selection (cross-cutting)
|   |-- intelligent-model-selection-policy.md
|   +-- intelligent-decision-engine-policy.md
|
|-- 04-toon-refinement/             Step 4: TOON enrichment [NEW]
|   +-- toon-refinement-policy.md
|
|-- 05-skill-agent-selection/       Step 5: Skills & agents
|   |-- auto-skill-agent-selection-policy.md
|   |-- adaptive-skill-registry.md
|   +-- core-skills-mandate.md
|
|-- 06-tool-optimization/           Step 6: Token savings
|   +-- tool-usage-optimization-policy.md
|
|-- 08-progress-tracking/           Progress tracking (cross-cutting)
|   |-- task-phase-enforcement-policy.md
|   +-- task-progress-tracking-policy.md
|
|-- 09-git-commit/                  Step 9: Auto-commit & branching
|   |-- git-auto-commit-policy.md
|   +-- version-release-policy.md
|
|-- 10-implementation-execution/    Step 10: Implementation [NEW]
|   +-- implementation-execution-policy.md
|
|-- 12-issue-closure/               Step 12: Issue closure [NEW]
|   +-- issue-closure-policy.md
|
|-- 13-documentation-update/        Step 13: Documentation [NEW]
|   +-- documentation-update-policy.md
|
|-- 14-final-summary/              Step 14: Final summary [NEW]
|   +-- final-summary-policy.md
|
|-- failure-prevention/             Failure prevention (cross-cutting)
|   |-- common-failures-prevention.md
|   +-- failure-kb.json
|
|-- github-issues-integration-policy.md     Step 8: Issue creation
|-- github-branch-pr-policy.md              Step 11: PR & code review
|-- parallel-execution-policy.md            Parallel task execution
|-- proactive-consultation-policy.md        User consultation rules
|-- file-management-policy.md               Protected directories
+-- architecture-script-mapping-policy.md   Script-to-step mapping
```

**Total: 15 sub-folders + 6 root policies, 49 policy files**

---

## Execution Modes

### Hook Mode (CLAUDE_HOOK_MODE=1) - Default
```
Steps 0-7  -> Pipeline (analysis + prompt generation)
Steps 8-9  -> Pipeline (GitHub issue + branch creation)
Step 10    -> Claude Code (user implements with generated prompt)
Steps 11-14 -> Stop hook auto-executes (PR, issue close, docs, summary)
```

### Full Mode (CLAUDE_HOOK_MODE=0)
```
Steps 0-14 -> Sequential pipeline execution (no user interaction)
```

---

## Pipeline Flow

```
User Request
    |
Step 0:  Task Analysis + Prompt Generation
    |
Step 1:  Plan Mode Decision (complexity-based)
    |
Step 2:  Plan Execution (conditional - if plan required)
    |
Step 3:  Task/Phase Breakdown (validated tasks)
    |
Step 4:  TOON Refinement (enrich with full context)
    |
Step 5:  Skill & Agent Selection (auto-choose)
    |
Step 6:  Skill Validation & Download
    |
Step 7:  Final Prompt Generation (3 files)
    |
Step 8:  GitHub Issue Creation (semantic)
    |
Step 9:  Branch Creation + Git Setup
    |
Step 10: Implementation Execution (with system prompt)
    |
Step 11: PR & Code Review (retry loop, max 3)
    |           |
    |     [review failed? retry -> Step 10]
    |
Step 12: Issue Closure (with summary)
    |
Step 13: Documentation Update (CLAUDE.md + session docs)
    |
Step 14: Final Summary + Voice Notification
    |
    DONE
```

---

## Dependencies

**Depends on:**
1. Level -1: Auto-Fix (Unicode, encoding, paths)
2. Level 1: Sync System (Context + Session loaded)
3. Level 2: Rules/Standards System (Standards loaded)

**Provides:**
- Generated code following standards
- GitHub issue + branch + PR lifecycle
- Auto-tracked progress
- Documentation updates
- Execution summary with metrics

---

## Standards Integration Hooks

5 hooks inject standards at critical steps:

| Hook | Step | Purpose |
|------|------|---------|
| `apply_integration_step1` | 1 | Plan mode constraints |
| `apply_integration_step2` | 2 | Naming/layer constraints |
| `apply_integration_step5` | 5 | Skill/standards compatibility |
| `apply_integration_step10` | 10 | Code review compliance checklist |
| `apply_integration_step13` | 13 | Documentation requirements |

---

**STATUS:** ACTIVE
**PRIORITY:** NORMAL (Runs after Level -1 + Level 1 + Level 2)
