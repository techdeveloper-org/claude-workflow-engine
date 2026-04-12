# Issue Closure Policy - Step 12

**Version:** 1.0.0
**Part of:** Level 3: Execution System (15 Steps: 0-14)
**Step:** 12 - Issue Closure
**Status:** Active
**Date:** 2026-03-17

---

## Overview

Step 12 closes the GitHub issue created in Step 8 after implementation (Step 10) and PR review (Step 11) are complete. It adds a closing comment with implementation summary, PR link, and verification status. Also performs post-merge cleanup when applicable.

**Input:** Issue ID (Step 8), PR URL (Step 11), review status, modified files
**Output:** Issue closure status, closing comment

---

## Policy Scope

**Applies to:** Level 3: Execution System, Step 12
**Predecessor:** Step 11 (Pull Request & Code Review)
**Successor:** Step 13 (Documentation Update)

---

## Closure Process

### 12.1 Skip Conditions

Issue closure is SKIPPED when:
- No issue was created in Step 8 (`step8_issue_created` is False)
- Issue ID is "0" or missing
- Returns `step12_status: "SKIPPED"` immediately

### 12.2 Closing Comment Content

The closing comment MUST include:

| Field | Source | Description |
|-------|--------|-------------|
| PR Link | `step11_pr_url` | Link to the pull request |
| Implementation Status | `step11_review_passed` | "Passed" or "Needs Work" |
| Approach | `step0_task_type` + `step5_skill` | How the task was executed |
| Modified Files | `step10_modified_files` | Files changed during implementation |
| Verification Steps | Computed | Review status + PR reference |

### 12.3 GitHub API Integration

Step 12 uses `Level3GitHubWorkflow.step12_close_issue()` with:
- `issue_number` - From Step 8
- `pr_number` - From Step 11
- `files_modified` - From Step 10
- `approach_taken` - Task type + skill used
- `verification_steps` - Review status and PR link

### 12.4 Post-Merge Cleanup

When the PR has been merged (`step11_merged` is True):
1. Checkout main branch
2. Pull latest changes
3. Delete the merged feature branch (`step9_branch_name`)
4. Uses `git.post_merge_cleanup(branch_name)`

Post-merge cleanup is best-effort:
- Success: Log cleanup message
- Failure: Log warning, do NOT block pipeline

---

## Fallback Behavior

If `Level3GitHubWorkflow` is unavailable (import error, API failure):
- Generate a markdown closing comment locally
- Return `step12_status: "FALLBACK"`
- `step12_issue_closed` set to False (issue remains open)
- The comment is stored but not posted to GitHub

---

## Output State Keys

| Key | Type | Description |
|-----|------|-------------|
| `step12_issue_closed` | bool | Whether issue was actually closed on GitHub |
| `step12_closing_comment` | str | The closing comment text |
| `step12_status` | str | `OK`, `SKIPPED`, `FALLBACK`, or `ERROR` |
| `step12_error` | str | Error message (if status is ERROR) |

---

## Quality Requirements

1. **Never close without PR reference** - Closing comment must link to PR
2. **Preserve issue history** - Add comment before closing (not just close)
3. **Post-merge cleanup is optional** - Never block on cleanup failure
4. **Skip gracefully** - If no issue exists, return SKIPPED (not ERROR)

---

## Error Handling

- GitHub API failure: Fall back to local comment generation
- Missing issue ID: Skip closure entirely
- Post-merge cleanup failure: Log warning, continue
- Exception: Return `ERROR` status with details

---

## Implementation Reference

- **Node function:** `step12_issue_closure_node()` in `level3_execution/subgraph.py`
- **Core logic:** `step12_issue_closure()` in `subgraphs/level3_execution.py`
- **GitHub workflow:** `langgraph_engine/level3_steps8to12_github.py`
- **Related policy:** `github-issues-integration-policy.md` (Step 8 issue creation)
