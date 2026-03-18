# Level -1: Auto-Fix System

**Version:** 1.0.0
**Priority:** CRITICAL (Blocking Checkpoint)
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Overview

Level -1 is a **blocking pre-flight checkpoint** that runs BEFORE any pipeline execution.
It detects and fixes 3 categories of platform-specific issues that would cause silent failures
in downstream levels.

**Execution:** Sequential (3 checks -> merge -> conditional fix -> retry)
**Max Retries:** 3 attempts before force-continue
**Platform:** Windows-specific (skipped on macOS/Linux)

---

## Architecture

```
START
  |
  v
[Check 1: Unicode UTF-8]  --> validates stdout/stderr encoding
  |
  v
[Check 2: ASCII Encoding]  --> scans .py files for non-ASCII content
  |
  v
[Check 3: Windows Paths]  --> detects backslash paths in .py files
  |
  v
[Merge Node]  --> aggregates results (ALL must pass)
  |
  +-- OK --> Level 1 (continue pipeline)
  +-- FAILED --> [Ask User]
                   |
                   +-- "auto-fix" --> [Fix Node] --> retry from Check 1
                   +-- "skip" --> Level 1 (continue with warnings)
                   +-- max attempts (3) --> force Level 1 (with warning)
```

---

## Checks

### Check 1: Unicode UTF-8 Fix
- **Policy:** [unicode-fix-policy.md](unicode-fix-policy.md)
- **Node:** `node_unicode_fix`
- **Purpose:** Ensure stdout/stderr use UTF-8 encoding (not cp1252)

### Check 2: ASCII-Only Encoding Validation
- **Policy:** [encoding-validation-policy.md](encoding-validation-policy.md)
- **Node:** `node_encoding_validation`
- **Purpose:** Detect non-ASCII characters in Python source files

### Check 3: Windows Path Validation
- **Policy:** [windows-path-policy.md](windows-path-policy.md)
- **Node:** `node_windows_path_check`
- **Purpose:** Detect hardcoded backslash paths in Python source files

---

## Recovery Flow

- **Policy:** [recovery-policy.md](recovery-policy.md)
- **Nodes:** `ask_level_minus1_fix` + `fix_level_minus1_issues`
- **Purpose:** Interactive or automatic recovery with backup/restore safety

---

## State Fields

| Field | Type | Purpose |
|-------|------|---------|
| `unicode_check` | str | "PASS" or "FAIL" |
| `encoding_check` | str | "PASS" or "FAIL" |
| `windows_path_check` | str | "PASS" or "FAIL" |
| `level_minus1_status` | str | "OK" or "FAILED" |
| `level_minus1_user_choice` | str | "auto-fix" or "skip" |
| `level_minus1_retry_count` | int | Current retry attempt (0-3) |

---

## Dependencies

- **ErrorLogger** (`error_logger.py`) - Structured error tracking
- **BackupManager** (`backup_manager.py`) - File backup/restore for path fixes
- **StepLogger** (`step_logger.py`) - Per-check execution logging

---

## Implementation

- **File:** `scripts/langgraph_engine/subgraphs/level_minus1.py`
- **Lines:** ~754
- **Orchestrator integration:** `orchestrator.py` lines 977-1028
