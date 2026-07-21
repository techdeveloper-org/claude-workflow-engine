# GitHub Branch + PR Workflow Policy

**Version:** 3.0.0
**Last Updated:** 2026-03-05
**Status:** Active
**Depends On:** github-issues-integration-policy.md, context-management-policy.md, recommendations-policy.md
**Related To:** automatic-task-breakdown-policy.md, auto-skill-agent-selection-policy.md

---

## Overview

This policy defines the automated GitHub workflow that runs during a Claude Code session:
**Issue -> Branch -> Work -> Commit -> Push -> PR -> Auto-Review -> Smart Code Review -> Merge**

The workflow builds on the GitHub Issues integration by adding automatic branch creation,
pull request management, auto-review with session metrics, and **[NEW v3.0] Smart Code Review**
that validates files before auto-merge based on session context and skill patterns.

---

## Branch Naming

**Format:** `{label}/{issueId}`

- `{label}` = issue type detected from task subject/description
- `{issueId}` = GitHub issue number from the first TaskCreate

**Valid Label Prefixes (SEMANTIC - v3.0+):**

| Label | When Used | Example |
|-------|-----------|---------|
| `bugfix` | Bug fixes, error resolution, crash fixes | `bugfix/42` |
| `feature` | New functionality (default) | `feature/123` |
| `refactor` | Code restructuring, cleanup | `refactor/99` |
| `docs` | Documentation changes | `docs/55` |
| `enhancement` | Improving existing features | `enhancement/78` |
| `perf` | Performance optimization | `perf/34` |
| `test` | Adding or updating tests | `test/88` |
| `chore` | Maintenance, setup, dependencies | `chore/12` |

**Examples:**
- `bugfix/42` - Bug fix for issue #42 (NOT `fix/42`)
- `feature/123` - New feature for issue #123
- `refactor/99` - Code refactoring for issue #99
- `docs/55` - Documentation update for issue #55
- `perf/34` - Performance optimization for issue #34
- `enhancement/78` - Feature enhancement for issue #78

**Rules:**
- One branch per session (first TaskCreate triggers creation)
- All subsequent tasks stay on the same branch
- Branch is only created from `main` or `master`
- If already on a feature branch, branch creation is skipped
- Legacy `issue-{N}` format is still recognized for backwards compatibility

---

## Complete Workflow Steps (7-Step Process)

| Step | Event | Action | Script | Status |
|------|-------|--------|--------|--------|
| 0 | Session start | Build validation | auto_build_validator.validate_build() | ✅ |
| 1 | All tasks done + Stop | Commit changes | github_pr_workflow.py::_commit_session_changes() | ✅ |
| 2 | | Push branch | github_pr_workflow.py::_push_branch() | ✅ |
| 3 | | Create PR | github_pr_workflow.py::_create_pull_request() | ✅ |
| 4 | | Post auto-review comment | github_pr_workflow.py::_auto_review_pr() | ✅ |
| **4.5** | **[NEW v3.0]** | **Smart Code Review** | **github_pr_workflow.py::_smart_code_review()** | ✅ |
| 5 | | Merge PR (if review passes) | github_pr_workflow.py::_merge_pr() | ✅ |
| 6 | | Switch to main | github_pr_workflow.py::_switch_to_main() | ✅ |
| 7 | | Version bump on main | github_pr_workflow.py::_bump_and_push_on_main() | ✅ |

## Workflow Triggers (Task-Level)

| Event | Action | Script |
|-------|--------|--------|
| First TaskCreate | Create issue + create branch | post-tool-tracker.py -> github_issue_manager.py |
| Subsequent TaskCreate | Create issue (stay on branch) | post-tool-tracker.py -> github_issue_manager.py |
| TaskUpdate(completed) | Close issue | post-tool-tracker.py -> github_issue_manager.py |
| All tasks done + Stop | Execute 7-step workflow | stop-notifier.py -> github_pr_workflow.py |

---

## PR Template

**Title:** Derived from session task types (max 70 chars)

**Body structure:**
```markdown
## Summary
- [bullet points from session requests]

## Session Stats
- Requests: N
- Max Complexity: X/25
- Skills: skill1, skill2

## Issues
Closes #N
Closes #M

---
_Auto-created by Claude Memory System (GitHub PR Workflow)_
```

---

## Auto-Review (Step 4)

The system posts a review comment (not an approval) on the PR containing:

- **Session Metrics:** request count, task types, complexity stats, skills used
- **Work Done:** list of prompts/tasks with their types and models
- **Tool Usage:** total tool calls, tasks completed, top 5 tools used

Uses `gh pr comment` instead of `gh pr review --approve` to avoid branch protection conflicts.

---

## Smart Code Review (Step 4.5) [NEW in v3.0]

**Purpose:** Validate code quality before auto-merge based on session context and skill patterns.

**What It Does:**

1. **Load Session Context**
   - Reads `flow-trace.json` to get:
     - Primary skill used (e.g., java-spring-boot-microservices)
     - Primary agent (e.g., spring-boot-microservices)
     - Tech stack detected (e.g., [spring-boot, java, postgresql])
     - Supplementary skills (e.g., [rdbms-core, docker])
   - Reads `session-summary.json` to get:
     - Task description (what was being accomplished)
     - Task types (API, UI, Database, DevOps, Testing)
     - Request count and max complexity

2. **Get Changed Files**
   - Runs: `git diff --name-only main...HEAD`
   - Returns list of all modified files

3. **For Each File: Determine Skill**
   - Maps file extension to correct skill:
     ```
     .java → java-spring-boot-microservices
     .ts → angular-engineer
     .tsx → ui-ux-designer
     .html → ui-ux-designer
     .scss/.css → css-core
     .py → python-backend-engineer
     .sql → rdbms-core
     Dockerfile → docker
     pom.xml → java-spring-boot-microservices
     package.json → angular-engineer
     ... and more
     ```

4. **Review File Against Skill Patterns**
   - Validates against skill-specific patterns:
     - Java: @RestController, @Service, @Transactional, dependency injection
     - Angular: @Component, @NgModule, @Injectable, Observable handling
     - Python: async/await, request validation, error handling
     - CSS: responsive design, theming, performance
     - etc.

5. **Post Comprehensive Review Comment**
   - Includes:
     ```markdown
     ## 🔍 Smart Code Review (Session-Aware + Skill-Aware)

     ### 📋 Review Context
     - Task: [description]
     - Tech Stack: [technologies]
     - Skills Used: [skills]

     ### 📁 Files Reviewed: N
     [For each file]:
     **filename** → skill
       ✅ Check 1 passed
       ✅ Check 2 passed
       ⚠️ Suggestion: ...

     ### 📊 Summary
     - Critical Issues: 0
     - Warnings: 0
     - Status: ✅ Ready to auto-merge
     ```

6. **Make Merge Decision**
   - **if critical_count > 0:** Return False (DO NOT merge)
     - PR left open for manual review
     - User sees critical issues in review comment
     - Must fix issues before merge can happen
   - **if critical_count == 0:** Return True (SAFE to merge)
     - Continue to auto-merge
     - Warnings/suggestions included but non-blocking

**Review Status Codes:**

| Status | Meaning | Action |
|--------|---------|--------|
| ✅ **APPROVED** | All checks pass, no issues | Continue to auto-merge |
| ⚠️ **WARNINGS** | Checks pass, suggestions found | Continue to auto-merge, note suggestions |
| ❌ **CRITICAL** | Pattern violations found | Block merge, require fixes |

**Data Sources Used:**

| Data | Source | Provides |
|------|--------|----------|
| Context | flow-trace.json | Skill, agent, tech_stack, supplementary_skills |
| Task Info | session-summary.json | task_description, task_types, skills_used, complexity |
| Files | git diff | Changed files list |
| Patterns | Skill database | Skill-specific validation rules |

**Error Handling:**

- If review data unavailable: Safe to merge (assume passing)
- If file reading fails: Mark as warning, not critical
- If skill unknown: Use adaptive-skill-intelligence fallback
- If gh CLI fails: Log error, don't block merge

---

## Merge Strategy (Step 5)

**When Merge Happens:**
- Only after smart code review returns `safe_to_merge=True` (no critical issues)
- If critical issues found: PR left open, merge blocked

**Merge Method:**
- `gh pr merge --merge --delete-branch`
- Merge commit strategy (preserves PR history)
- Auto-deletes source branch after merge

**Fallback Handling:**
- If merge fails (branch protection, required reviews):
  - PR left open with message
  - No force-merge attempted
  - Returns False, stops workflow

**Post-Merge:**
- Automatically switches to `main`
- Pulls latest changes (--ff-only)
- Runs version bump (Step 7)

**Safety:**
- Never force-merges
- Respects all branch protection rules
- Only executes if smart review passes

---

## Safety

- All `gh` CLI calls have 30s timeout
- Every step is wrapped in try/except (never fails the stop hook)
- If any step fails, subsequent steps are skipped gracefully
- GitHub operations capped at 10 per session
- No force-push, no branch deletion (except via --delete-branch on merge)
- Logs all actions to `~/.claude/memory/logs/stop-notifier.log`

---

## Data Storage

**github-issues.json** (per-session) stores:
```json
{
  "task_to_issue": {
    "1": {
      "issue_number": 42,
      "issue_url": "https://github.com/user/repo/issues/42",
      "title": "[TASK-1] Fix authentication bug",
      "issue_type": "fix",
      "labels": ["task-auto-created", "level-3-execution", "bugfix", "priority-medium", "complexity-medium"],
      "created_at": "2026-02-28T10:30:00",
      "status": "open"
    }
  },
  "session_branch": "fix/42",
  "branch_created_at": "2026-02-28T10:30:00",
  "branch_from_issue": 42,
  "branch_type": "fix",
  "pr_number": 15,
  "pr_url": "https://github.com/user/repo/pull/15",
  "pr_merged": true,
  "pr_merged_at": "2026-02-28T11:00:00",
  "ops_count": 5
}
```

---

## Policy Chaining & Dependencies

**This policy depends on:**

1. **GitHub Issues Integration Policy**
   - Creates GitHub issues for each task
   - Links issues to branch names
   - Provides issue numbers for PR body

2. **Automatic Task Breakdown Policy (3.1)**
   - Detects task description
   - Identifies task types
   - Detects tech_stack (used by smart review)

3. **Auto Skill/Agent Selection Policy (3.5)**
   - Selects primary skill/agent
   - Identifies supplementary skills
   - Populates flow-trace.json (used by smart review)

4. **Context Management Policy (1.1)**
   - Monitors context usage
   - Provides session summary data
   - Ensures session data available for review

5. **Recommendations Policy (3.8)**
   - Provides pattern recommendations
   - Feeds into smart review patterns

**This policy feeds into:**

1. **Session Save & Archival Policy (3.11)**
   - Receives PR metadata (pr_number, pr_url, pr_merged)
   - Stores in session summary

2. **Progress Tracking & Metrics Policy (3.9)**
   - Logs PR workflow steps
   - Tracks merge success/failure

3. **Version Release Policy**
   - Bumps version after PR merges
   - Updates CHANGELOG

**Data Flow for Smart Review:**

```
User Session
    ↓
Task Breakdown (3.1) → Detects tech_stack, task_description
    ↓
Skill Selection (3.5) → Detects skills, populates flow-trace.json
    ↓
Session Summary → Stores task context
    ↓
Context Management (1.1) → Maintains session data
    ↓
[USER WORK HAPPENS]
    ↓
Stop Hook fires → github_pr_workflow.py starts
    ↓
Commit created (Step 1)
    ↓
PR created (Step 3)
    ↓
Auto-review posted (Step 4)
    ↓
🔍 SMART REVIEW (Step 4.5):
   ├─ Loads flow-trace.json (from Step 3.5)
   ├─ Loads session-summary.json (from Step 3.1)
   ├─ Gets changed files from git
   ├─ Determines skill for each file
   ├─ Validates against patterns
   └─ Posts findings on PR
    ↓
Merge decision (Step 5)
   ├─ if critical_issues: Block merge
   └─ if safe: Auto-merge
    ↓
Version bump (Step 7)
    ↓
Session saved (3.11)
```

---

## Prerequisites

1. `gh` CLI installed and authenticated (`gh auth login`)
2. Git repository with remote configured
3. GitHub Issues integration enabled (github_issue_manager.py present)
4. Session tracking active (session-progress.json exists)
5. **[NEW v3.0]** Flow-trace.json available (populated by Step 3.5)
6. **[NEW v3.0]** Session summary available (populated by Step 3.1)
