---
description: "Level 2.2 - Documentation file governance: permitted root doc files and Git enforcement"
priority: high
---

# Documentation File Governance (Level 2.2)

**PURPOSE:** Enforce that only the five canonical documentation files exist at the repository root in Git. All other documentation lives in subdirectories (`docs/`) or is gitignored.

---

## 1. Permitted Root Documentation Files

Only the following files are allowed at the repository root and tracked in Git:

| File | Purpose |
|------|---------|
| `SRS.md` | Software Requirements Specification |
| `README.md` | Project overview, setup, and usage guide |
| `CLAUDE.md` | Claude Code instructions and project context |
| `VERSION` or `version.txt` | Single source-of-truth version string |
| `CHANGELOG.md` | Chronological release history |

✅ **CORRECT - Only permitted files at root:**
```
/
+-- SRS.md
+-- README.md
+-- CLAUDE.md
+-- VERSION
+-- CHANGELOG.md
+-- docs/          ← generated artifacts, exempt (all .md files allowed here)
+-- uml/           ← auto-generated UML, exempt
+-- drawio/        ← auto-generated draw.io diagrams, exempt
```

❌ **PROHIBITED - Extra documentation at root:**
```
/
+-- ARCHITECTURE.md    ✗ NOT PERMITTED at root
+-- DESIGN.md          ✗ NOT PERMITTED at root
+-- NOTES.md           ✗ NOT PERMITTED at root
+-- TODO.md            ✗ NOT PERMITTED at root
+-- CONTRIBUTING.md    ✗ NOT PERMITTED at root (move to docs/)
+-- API.md             ✗ NOT PERMITTED at root (move to docs/)
```

---

## 2. Required Sections Per File

### SRS.md

Every `SRS.md` must contain all of the following headings:

```markdown
## 1. Purpose
## 2. Scope
## 3. Requirements
### 3.1 Functional Requirements
### 3.2 Non-Functional Requirements
## 4. Acceptance Criteria
## 5. Out of Scope
```

✅ **Minimum required headings check:**
```bash
grep -E "^## (1\. Purpose|2\. Scope|3\. Requirements|4\. Acceptance Criteria)" SRS.md
# All 4 must match
```

### README.md

Every `README.md` must contain all of the following headings:

```markdown
## Overview
## Prerequisites / Requirements
## Installation / Setup
## Usage
## Architecture (or link to docs/architecture)
## Contributing
```

### CLAUDE.md

Every `CLAUDE.md` must contain all of the following headings:

```markdown
## Project Overview
## Architecture & Structure
## Development Guidelines
```

### VERSION / version.txt

- Must contain a single line with a valid semver string: `MAJOR.MINOR.PATCH`
- No trailing whitespace, no extra lines

✅ **CORRECT:**
```
1.7.0
```

❌ **WRONG:**
```
version: 1.7.0
v1.7.0
1.7.0 (stable)
```

### CHANGELOG.md

Every `CHANGELOG.md` must follow [Keep a Changelog](https://keepachangelog.com) format:

```markdown
# Changelog

## [UNRELEASED]

## [X.Y.Z] - YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
```

✅ **Each version entry must include the date in ISO 8601 format (YYYY-MM-DD).**

---

## 3. Prohibited Files (Git Enforcement)

The following categories of files must NOT be committed to the repository root:

❌ **Extra documentation files at root:**
```bash
# These must NOT appear in git ls-files at repo root:
ARCHITECTURE.md
DESIGN.md
NOTES.md
TODO.md
CONTRIBUTING.md    # move to docs/contributing.md
API.md             # move to docs/api.md
ROADMAP.md         # move to docs/roadmap.md
DECISIONS.md       # move to docs/decisions.md
INSTALL.md         # merge into README.md
USAGE.md           # merge into README.md
```

✅ **CORRECT placement for non-root documentation:**
```
docs/architecture.md     ← architecture decisions
docs/contributing.md     ← contribution guide
docs/api/                ← API reference
uml/                     ← UML diagrams (auto-generated)
drawio/                  ← draw.io diagrams (auto-generated)
```

---

## 4. .gitignore Additions

Add the following entries to `.gitignore` to prevent accidental root-level doc commits:

```gitignore
# Documentation governance - only 5 files allowed at root
# (SRS.md, README.md, CLAUDE.md, VERSION, CHANGELOG.md are exempt)
/ARCHITECTURE.md
/DESIGN.md
/NOTES.md
/TODO.md
/CONTRIBUTING.md
/ROADMAP.md
/DECISIONS.md
/INSTALL.md
/USAGE.md
/API.md
```

---

## 5. Update Triggers (Pipeline Step Mapping)

| Pipeline Step | Action | File Updated |
|--------------|--------|-------------|
| Step 8 (GitHub Issue created) | New feature starts | `CHANGELOG.md` — add `[UNRELEASED]` entry |
| Step 9 (Branch created) | Work begins | `SRS.md` — link issue number to requirement |
| Step 13 (Documentation update) | Work closes | `CHANGELOG.md` — move `[UNRELEASED]` to versioned entry |
| Step 13 (Documentation update) | Work closes | `VERSION` — bump patch/minor/major |
| Step 13 (Documentation update) | Work closes | `README.md` — update if setup or usage changed |
| Step 14 (Final summary) | Sprint ends | `CLAUDE.md` — update `Latest Execution Insight` block |

✅ **Step 13 is the canonical trigger for version bump + CHANGELOG finalization.**

---

## 6. Exemptions

The following directories are **fully exempt** from this rule:

```
docs/        ← any .md files allowed, subdirectories allowed
uml/         ← auto-generated by pipeline, not reviewed
drawio/      ← auto-generated by pipeline, not reviewed
policies/    ← pipeline policy definitions, governed separately
rules/       ← Claude Code rules, governed separately
```

Scripts-directory `CLAUDE.md` files (e.g., `scripts/CLAUDE.md`) are also exempt — they are context files for Claude Code sub-directory awareness, not root documentation.

---

## 7. Enforcement in Level 2

This rule is evaluated by Level 2 Standards Loading before any code change is written.

```
Level 2 Check:
  1. git ls-files --others --cached | grep -E "^[^/]+\.md$"
     → Fail if any .md at root other than SRS.md, README.md, CLAUDE.md, CHANGELOG.md
  2. cat VERSION | grep -E "^[0-9]+\.[0-9]+\.[0-9]+$"
     → Fail if VERSION does not match semver
  3. grep -c "^## [0-9]\+\. Purpose" SRS.md
     → Warn if required SRS sections are missing
```

---

**ENFORCEMENT:** This is Level 2.2 - ACTIVE when any documentation file is created or modified. Violations block commit at pre-tool gate.
