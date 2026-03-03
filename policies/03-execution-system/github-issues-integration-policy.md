# GitHub Issues Integration Policy - Level 3 Execution System

**Version:** 3.0.0 (UPDATED - Problem-centric, one issue per problem)
**Part of:** Level 3: Execution System (12 Steps)
**Status:** Active - Breaking Changes from v2.0
**Date:** 2026-03-03

---

## Overview

**CHANGED in v3.0:** This policy now creates ONE issue per problem statement (not per task).

Old approach (v2.0): 1 problem → 3 tasks → 3 issues ❌
New approach (v3.0): 1 problem → 3 tasks → 1 issue ✅

The Level 3 Execution System creates semantic GitHub Issues that aggregates all related tasks. Each issue includes:
- Clear problem statement (not task-centric)
- Semantic branch naming (`bugfix/model-selection` not `fix/1`)
- Semantic labels (`bugfix`, `p1-high` not task-based)
- When closed: Rich narrative with commit IDs, RCA, and verification

---

## Policy Scope

**Applies to:** Level 3: Execution System, Step 3.2 (Task Breakdown) and Step 3.11 (Git Auto-Commit)

**Automatic Triggers:**
- Task creation via TaskCreate tool (Step 3.2)
- Task completion and commit (Step 3.11)
- Major policy enforcement events (Step 3.0+)

---

## GitHub Issues Management

### [3.2] Task Breakdown → Create GitHub Issues

**What Happens:**
When Level 3 auto-creates a task during execution, it ALSO creates a corresponding GitHub Issue with:

#### Issue Details

**Title Format (CHANGED in v3.0):**
```
{type}: {problem_statement}
```

Where `type` is: `bugfix`, `feature`, `refactor`, `perf`, `docs`, `enhancement`

Examples:
```
bugfix: Model selection defaulting to HAIKU for complex tasks
feature: Implement JWT authentication system
refactor: Simplify context management
perf: Improve complexity scoring performance
docs: Add architecture diagrams to README
```

**NOT this (old format):**
```
❌ [TASK-001] Implement GitHub Issues integration
❌ [TASK-002] Add tests for issues
```

**Description/Body (CHANGED in v3.0 - Problem-Centric Format):**
```markdown
## Problem Statement

{What is the actual problem from user perspective?
 Why does it matter? What's broken or needed?}

## Context & Background

{Why is this happening? What's the root cause theory?
 Any relevant history or related issues?
 What areas will be affected?}

## Solution Approach

{High-level strategy. What needs investigation/change?
 Which files/modules are involved?}

## Success Criteria

- [ ] {Measurable outcome 1}
- [ ] {Measurable outcome 2}
- [ ] All related tasks completed
- [ ] Changes committed and merged

## Related Tasks

{If multiple internal tasks, reference them}

---
_Auto-created by Claude Memory System (Level 3 Execution) | v3.0.0_
```

**Real Example:**
```markdown
## Problem Statement

Model selection policy isn't working. Tasks that should get SONNET (complex API work)
are getting HAIKU (simple tasks model) instead. This causes wrong model selection.

## Context & Background

Complexity scoring uses 1-10 scale, but policy thresholds expect 1-25 scale.
This mismatch causes all scores to map to HAIKU range.

## Solution Approach

1. Expand complexity scale from 1-10 → 1-25
2. Add task-type weights (Auth=8, API=7, Security=8)
3. Add integration/cross-cutting detection
4. Test with real task examples

## Success Criteria

- [ ] SIMPLE tasks (typos) → HAIKU
- [ ] MODERATE tasks (bug fix) → SONNET
- [ ] COMPLEX tasks (API/auth) → SONNET/OPUS
- [ ] All edge cases tested
```

#### Labels (CHANGED in v3.0.0 - Semantic Labels)

**Type Labels (Mutually Exclusive - Auto-Detected):**

| Label | When to Use |
|-------|-------------|
| `bugfix` | Fixing broken behavior |
| `feature` | New capability/functionality |
| `refactor` | Improving code without user-visible change |
| `docs` | Documentation only |
| `enhancement` | Improving existing feature |
| `perf` | Performance optimization |
| `test` | Test coverage/infrastructure |
| `chore` | Maintenance, setup, etc. |

**Priority Labels (Based on Complexity - Mutually Exclusive):**

| Label | Complexity | When to Use |
|-------|-----------|-------------|
| `p0-critical` | >= 18 | Blocking, must fix now |
| `p1-high` | 12-17 | Important, fix soon |
| `p2-medium` | 6-11 | Regular priority |
| `p3-low` | 0-5 | Nice to have |

**Status Labels (Auto-Applied):**

| Label | Meaning |
|-------|---------|
| `in-progress` | Work started |
| `blocked` | Waiting on something |
| `review` | PR in review |
| `approved` | Ready to merge |

**Example Label Combinations:**
```
bugfix + p1-high + in-progress
feature + p2-medium + review
refactor + p3-low + approved
```

**NO MORE (old format):**
```
❌ task-auto-created
❌ level-3-execution
❌ priority-critical (use p0-critical)
❌ complexity-high (use complexity in issue, not as label)
```

### [3.2] Branch Naming (COORDINATED with github-branch-pr-policy.md)

**Format (UNCHANGED - Required for auto-close):**
```
{label}/{issueId}
```

Where:
- `label` = `fix`, `feature`, `refactor`, `docs`, `enhancement`, `test`, `chore`
- `issueId` = GitHub issue number (REQUIRED for auto-close policy!)

**Examples:**
```
fix/42              (Auto-closes issue #42 when merged)
feature/123         (Auto-closes issue #123 when merged)
refactor/99         (Auto-closes issue #99 when merged)
docs/55             (Auto-closes issue #55 when merged)
enhancement/78      (Auto-closes issue #78 when merged)
```

**IMPORTANT - WHY issue ID in branch name:**
- Required by `github-branch-pr-policy.md` for auto-close mechanism
- github-issues.json stores `branch_from_issue` to track which issue is being fixed
- PR workflow uses issue ID to add "Closes #N" in PR body
- Without issue ID, auto-close chain breaks!

**Single Branch Per Problem (Session):**
- First TaskCreate → creates issue + branch (e.g., fix/42)
- All subsequent tasks in same session → stay on same branch
- Multiple commits in one branch is OK
- One PR from that branch when all tasks complete
- Issue auto-closes when PR merges

#### Assignees

```
Automatic: None (open for any team member)
Optional: Can be assigned manually in GitHub
```

#### Milestones

```
Auto-Set: Current Phase (Phase X)
Example: "Phase 6 - Settings & Preferences"
```

### [3.11] Git Auto-Commit → Close GitHub Issues

**What Happens:**
When a task is completed, the corresponding GitHub Issue is AUTOMATICALLY CLOSED with a
**comprehensive resolution story** that narrates what was done, how it was investigated,
what files were changed, and how it was verified.

#### Close Mechanism

**Trigger:**
1. Task marked as completed (status = "completed")
2. `close_github_issue()` called with comprehensive closing comment

**Closing Comment Format (CHANGED in v3.0 - Rich Narrative with Commits):**

```markdown
## Resolution Story

{Narrative paragraph explaining:
 - What was the problem (restated for clarity)
 - How we investigated it (which files, what we learned)
 - What solution was found (the fix)
 - How it was verified (tests, commands)
 - Why this solution was chosen}

## Problem Summary

| Field | Value |
|-------|-------|
| **Problem** | {Original problem statement} |
| **Root Cause** | {Why it was happening} |
| **Solution** | {How it was fixed} |
| **Impact** | {User-visible improvement} |

## Commits

| Commit ID | Message |
|-----------|---------|
| `abc1234` | fix: Expand complexity scoring 1-10 → 1-25 |
| `def5678` | test: Add complexity scoring tests |
| `ghi9012` | docs: Update model selection guide |

## Files Changed

| File | Change Type | Impact |
|------|-------------|--------|
| `prompt-generator.py` | Modified | +45 lines |
| `test_complexity.py` | Created | +80 lines |

## Verification

- [x] HAIKU: Simple tasks (<=4) correctly selected
- [x] SONNET: Moderate tasks (5-19) correctly selected
- [x] OPUS: Complex tasks (>=20) correctly selected
- [x] All edge cases tested
- [x] No regressions in other parts
- [x] PR reviewed and approved

---
_Closed by Claude Memory System (Level 3 Execution) | v3.0.0_
```

**Real Closing Example:**
```markdown
## Resolution Story

Model selection was broken because complexity scoring used a 1-10 scale
while thresholds expected 1-25. This caused all tasks to score in HAIKU range.
We expanded the scale and added task-type weights. Now API tasks get SONNET
and typos get HAIKU - working correctly!

## Problem Summary

| Field | Value |
|-------|-------|
| **Problem** | Complex tasks getting HAIKU model (wrong) |
| **Root Cause** | 1-10 scale vs 1-25 threshold mismatch |
| **Solution** | Expand scale + add task-type weights |
| **Impact** | Proper model selection (faster inference) |

## Commits

| Commit ID | Message |
|-----------|---------|
| `d08ec84` | fix: Expand complexity scoring 1-10 → 1-25 scale |
| `e172381` | test: Add complexity tests |

## Files Changed

| File | Change Type |
|------|-------------|
| `prompt-generator.py` | +45 lines |
| `test_complexity.py` | +80 lines |

## Verification

- [x] HAIKU: Typo fix (complexity 2) → gets HAIKU ✅
- [x] SONNET: API work (complexity 12) → gets SONNET ✅
- [x] OPUS: Refactor (complexity 22) → gets OPUS ✅
```

**Commit Message Format:**
```
{Category}: {brief_description}

{detailed_explanation}

- Completed task {task_id}
- Closes #{issue_number}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

---

## GitHub API Integration

### Authentication

**Method:** GitHub Personal Access Token (PAT)

**Token Scope Required:**
```
- repo:full (read/write repositories)
- issues:read/write (manage issues)
- workflow:read (optional - for workflow automation)
```

**Token Location:**
```
Environment Variable: GITHUB_TOKEN
File Location: ~/.github/token (fallback, not recommended)
```

**Setup:**
```bash
# Set environment variable
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Or in ~/.bashrc / ~/.zshrc
echo 'export GITHUB_TOKEN="ghp_..."' >> ~/.bashrc
source ~/.bashrc
```

### API Calls

#### Create Issue (Step 3.2)

**Endpoint:**
```
POST /repos/{owner}/{repo}/issues
```

**Request:**
```json
{
  "title": "[TASK-001] Implement GitHub Issues integration",
  "body": "## Task Details\n...",
  "labels": [
    "task-auto-created",
    "level-3-execution",
    "complexity-medium",
    "priority-high"
  ],
  "milestone": null
}
```

**Error Handling:**
- ✅ Network error → Log warning, continue without issue
- ✅ Auth error → Log error, skip issue creation
- ✅ Rate limited → Retry after delay
- ✅ No token → Log notice, continue

#### Close Issue (Step 3.11)

**Endpoint:**
```
PATCH /repos/{owner}/{repo}/issues/{issue_number}
```

**Request:**
```json
{
  "state": "closed",
  "state_reason": "completed"
}
```

**Auto-Link via Commit:**
```
Commit message contains: "Closes #123"
↓
GitHub auto-detects
↓
Issues #123 automatically closed on push
```

---

## Task Tracking Workflow

### Complete Lifecycle

```
┌─────────────────────────────────────────┐
│ [3.0] User sends prompt/message         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ [3.2] Task Breakdown                    │
├─ Auto-creates LOCAL task                │
│  └─ ~/.claude/memory/tasks/{id}.json    │
│                                          │
├─ Auto-creates GITHUB ISSUE              │
│  └─ POST /repos/{owner}/{repo}/issues   │
│  └─ With comprehensive labels + details │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ [3.3-3.10] Execute Task                 │
├─ Work on task                           │
├─ Monitor progress                       │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ [3.11] Git Auto-Commit                  │
├─ Create commit                          │
├─ Include "Closes #{issue_number}"       │
├─ Push to GitHub                         │
│  └─ GitHub auto-closes issue            │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ Task Complete                           │
├─ GitHub Issue CLOSED ✓                  │
├─ Git commit PUSHED ✓                    │
├─ Session saved ✓                        │
└─────────────────────────────────────────┘
```

---

## Safety & Constraints

### Rate Limiting

**GitHub API Limits:**
- 60 requests/hour (unauthenticated)
- 5,000 requests/hour (authenticated)

**Our Strategy:**
- Batch operations where possible
- Delay between requests: 500ms
- Max 10 issue operations per session
- Log rate limit hits to ~/.claude/memory/logs/

### Error Recovery

**Network Issues:**
```
Try 1 → Fail → Wait 5s
Try 2 → Fail → Wait 10s
Try 3 → Fail → Log to errors, continue
(never block execution)
```

**Permission Issues:**
```
No GITHUB_TOKEN env var → Log notice, skip GitHub
Invalid token → Log error, skip GitHub
No repo access → Log warning, skip GitHub
(local tasks still created successfully)
```

### Data Privacy

**What's Uploaded to GitHub:**
- Task title, description, labels
- Task type and complexity
- Timestamps
- Session ID (anonymous)

**What's NOT Uploaded:**
- Full prompt/user message content
- API keys or credentials
- User personal information
- Sensitive code (can be edited in GitHub later)

---

## Monitoring & Debugging

### Logging

**Location:** `~/.claude/memory/logs/sessions/{SESSION_ID}/github-issues.log`

**Log Format:**
```
[2026-02-26T10:30:45] [CREATE] Issue #42 created
[2026-02-26T10:30:46] [LABEL] Added 4 labels
[2026-02-26T10:35:12] [CLOSE] Issue #42 closed via commit abc123
[2026-02-26T10:35:13] [SUCCESS] Task lifecycle complete
```

### Debugging Commands

```bash
# View all auto-created issues
gh issue list --label "task-auto-created" --state all

# View current session issues
gh issue list --label "session-{SESSION_ID}"

# Manually close issue (if needed)
gh issue close {ISSUE_NUMBER}

# Check GitHub API status
curl https://api.github.com/repos/{owner}/{repo}/issues

# View last GitHub operation log
tail -f ~/.claude/memory/logs/sessions/{SESSION_ID}/github-issues.log
```

---

## Configuration

### In hook-downloader.py

**Enable/Disable GitHub Issues:**
```python
# In hook-downloader.py
GITHUB_ISSUES_ENABLED = True  # Set False to disable
GITHUB_ISSUES_AUTO_CLOSE = True  # Set False to disable auto-close
```

**Repository Configuration:**
```python
# Detect from git config
GITHUB_OWNER = "piyushmakhija28"  # From git origin
GITHUB_REPO = "claude-code-ide"    # From git origin
```

### In ~/.claude/settings.json

**Add optional GitHub Issues configuration:**
```json
{
  "github": {
    "enabled": true,
    "token_env_var": "GITHUB_TOKEN",
    "auto_create_issues": true,
    "auto_close_issues": true,
    "labels_enabled": true,
    "milestone_tracking": true
  }
}
```

---

## Examples

### Example 1: Bug Fix Task (complexity 5)

**Local Task Created:**
```json
{
  "id": "1",
  "subject": "Fix authentication bug in login flow",
  "type": "fix",
  "complexity": 5
}
```

**GitHub Issue Created:**
```
Title: [TASK-1] Fix authentication bug in login flow
Labels: task-auto-created, level-3-execution, bugfix, priority-medium, complexity-medium
Branch: fix/45
```

**Issue Body (Story Format):**
```markdown
## Story
A bug has been identified that needs to be resolved. The issue affects
the system behavior described below and requires investigation, root
cause analysis, and a targeted fix.

**What needs to be done:**
Fix authentication bug in login flow - login fails with special characters in password.

## Task Overview
| Field | Value |
|-------|-------|
| **Task ID** | 1 |
| **Type** | fix |
| **Complexity** | 5/25 |
| **Priority** | Medium |

## Acceptance Criteria
- [ ] Fix authentication bug in login flow
- [ ] Root cause identified and documented
- [ ] Fix verified - bug no longer reproducible
- [ ] Changes committed and pushed
```

**Issue Closed (Resolution Story):**
```markdown
## Resolution Story
This bug has been investigated, root-caused, and fixed.
The investigation involved reading 4 file(s) to understand the problem context.
The fix was applied across 2 file(s) to resolve the issue.
Verification was performed using 3 command(s) to confirm the fix works correctly.

## Root Cause Analysis (RCA)
**Investigation:** 4 files investigated
**Root Cause Location:** `src/auth/login.py`, `src/utils/validator.py`
**Fix Applied:** 2 edit(s) made
**Verification:** 3 command(s) run to verify fix
```

### Example 2: New Feature Task (complexity 12)

**GitHub Issue Created:**
```
Title: [TASK-2] Implement user dashboard analytics
Labels: task-auto-created, level-3-execution, feature, priority-high, complexity-high
Branch: feature/67
```

### Example 3: Refactoring Task (complexity 3)

**GitHub Issue Created:**
```
Title: [TASK-3] Refactor database connection pooling
Labels: task-auto-created, level-3-execution, refactor, priority-low, complexity-low
Branch: refactor/89
```

---

## Future Enhancements

1. **Linking:** Cross-link issues with related tasks
2. **Milestones:** Auto-assign to current development milestone
3. **Project Boards:** Auto-add to GitHub Project
4. **Code Review:** Link to related pull requests
5. **Notifications:** Email/Slack on issue creation/close
6. **Analytics:** Dashboard of auto-created vs manual issues

---

## References

- [GitHub Issues REST API](https://docs.github.com/en/rest/issues)
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [GitHub API Rate Limiting](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting)
- Level 3 Execution System (12 Steps)

---

**Status:** ACTIVE
**Last Updated:** 2026-02-28
**Maintainer:** Claude Memory System
**Feedback:** Create issues in claude-insight repo
