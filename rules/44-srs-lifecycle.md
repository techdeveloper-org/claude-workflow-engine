---
description: "Level 2.3 - SRS lifecycle: when to create, required sections, update triggers, update format"
priority: high
---

# SRS Lifecycle Rule (Level 2.3)

**PURPOSE:** Define when SRS.md must be created, what sections it must contain, and exactly how it must be updated after each SDLC cycle. This rule drives `documentation_manager.py` — the script executes, but this rule decides what.

---

## 1. Creation Trigger

Create `SRS.md` at project root when ALL of the following are true:

- No `SRS.md`, `System_Requirement_Analysis.md`, or `SYSTEM_REQUIREMENTS_SPECIFICATION.md` exists at root
- Step 13 is executing for the first time on this project
- The project has at least one source file (not purely config/scripts)

❌ **Do NOT create SRS if:**
- Any of the above alternate filenames already exist (use the existing file instead)
- The task type is `chore`, `refactor`, or `test` on a fresh project with no features yet

---

## 2. Required Sections (Creation)

Every new `SRS.md` must contain these sections in order:

```markdown
# Software Requirements Specification

## 1. Purpose
[One paragraph describing what this software does and for whom]

## 2. Scope
[What is in scope and explicitly what is out of scope]

## 3. Requirements
### 3.1 Functional Requirements
[Numbered FR-001, FR-002, ... entries]
### 3.2 Non-Functional Requirements
[NFR-001, NFR-002, ... entries covering: performance, security, scalability]

## 4. Acceptance Criteria
[Per-requirement acceptance criteria — one AC per FR]

## 5. Out of Scope
[Explicit list of excluded features to prevent scope creep]

## 6. Change Log
| Date | Version | Task | Change Summary | Status |
|------|---------|------|----------------|--------|
```

All sections are mandatory. Do not omit or merge sections.

---

## 3. Update Triggers

Update SRS.md at Step 13 when the completed task is:

| Task Type | Update SRS? | What to Update |
|-----------|------------|----------------|
| `feat` / `feature` | ✅ YES | Add FR entry + Change Log row |
| `fix` | ✅ YES | Update AC for affected FR + Change Log row |
| `enhance` | ✅ YES | Modify existing FR entry + Change Log row |
| `refactor` | ❌ NO | Skip SRS update |
| `chore` | ❌ NO | Skip SRS update |
| `test` | ❌ NO | Skip SRS update |
| `docs` | ✅ YES | Change Log row only |
| `security` | ✅ YES | Add NFR entry + Change Log row |

---

## 4. Update Format (Append-Only Rule)

**NEVER overwrite existing SRS content.** SRS is an append-only document.

### 4.1 Adding a Functional Requirement

Append to `### 3.1 Functional Requirements` section:

```markdown
**FR-{next_number}:** {Requirement description in imperative voice — "The system SHALL..."}
- Priority: {High | Medium | Low}
- Source: {GitHub Issue #N | User Story | Security Audit}
- Added: {YYYY-MM-DD}
```

### 4.2 Updating an Acceptance Criterion

Append below the existing AC (do NOT replace):

```markdown
**AC-{FR_number} (Updated {YYYY-MM-DD}):** {Revised criterion}
```

### 4.3 Change Log Entry

Always append one row to the Change Log table:

```markdown
| {YYYY-MM-DD} | {current_version} | {task_title} | {one-line summary of what changed} | ✅ Done |
```

---

## 5. Section Detection Logic

When updating, locate sections by these exact heading strings (case-insensitive):

- `## 3. Requirements` or `## Requirements`
- `### 3.1 Functional Requirements` or `### Functional Requirements`
- `### 3.2 Non-Functional Requirements` or `### Non-Functional Requirements`
- `## 6. Change Log` or `## Change Log` or `## Changelog`

If a section heading is not found, append the full section at the end of the file before updating.

---

## 6. Validation Before Writing

Before any SRS write operation, verify:

1. The file exists and is readable
2. The target section heading is present (create it if missing per §5)
3. The new FR number does not duplicate an existing `FR-{N}` in the file
4. The Change Log table header is present (add it if missing)

If validation fails, log the error with `level=ERROR` and skip the update — do NOT write partial content.

---

## 7. What This Rule Replaces

This rule replaces hardcoded logic in:
- `langgraph_engine/level3_execution/documentation_manager.py` → `_update_srs()` method
- `langgraph_engine/level3_execution/documentation_generator.py` → SRS template section
- `scripts/tools/post-merge-version-updater.py` → SRS update logic

Scripts read this rule to decide WHAT to write. Scripts decide HOW to write it.

---

**ENFORCEMENT:** Level 2.3 — ACTIVE at Step 13. Violations logged with `rule=44-srs-lifecycle`.
