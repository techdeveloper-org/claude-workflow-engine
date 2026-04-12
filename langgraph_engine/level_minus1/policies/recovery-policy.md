# Level -1 Recovery Policy

**Version:** 1.0.0
**Priority:** CRITICAL
**Status:** ACTIVE

---

## Purpose

Defines the interactive recovery flow when one or more Level -1 checks fail.
Ensures the pipeline can proceed safely with user consent or automatic fixes.

---

## Recovery Flow

### Step 1: Display Status

Show pass/fail status for each check:
```
Level -1 Auto-Fix Results:
  [PASS] Unicode UTF-8
  [FAIL] ASCII Encoding (3 files with non-ASCII)
  [PASS] Windows Paths
```

### Step 2: User Choice

Offer two options:
1. **"auto-fix"** - Attempt automatic fixes for all failed checks
2. **"skip"** - Continue pipeline with warnings (user accepts risk)

### Step 3: Non-TTY Fallback

In hook mode (non-interactive / no TTY):
- Default to **"auto-fix"** automatically
- Log that auto-fix was chosen due to non-TTY context

---

## Retry Logic

| Parameter | Value |
|-----------|-------|
| Max attempts | 3 |
| Retry scope | All 3 checks re-run after fix |
| Force-continue | After 3 failed attempts, force proceed with warning |

### Retry Flow

```
Attempt 1: Check -> Fail -> Fix -> Re-check
Attempt 2: Check -> Fail -> Fix -> Re-check
Attempt 3: Check -> Fail -> Force-continue (WARNING logged)
```

---

## Auto-Fix Actions Per Check

| Check | Auto-Fix Action | Can Auto-Fix? |
|-------|-----------------|---------------|
| Unicode UTF-8 | Reconfigure stdout/stderr encoding | YES |
| ASCII Encoding | Report files for manual review | NO (report only) |
| Windows Paths | Regex replace with backup/restore | YES |

---

## Backup Safety

All auto-fix operations that modify files MUST:
1. Create backup via BackupManager before any modification
2. Validate file integrity after modification
3. Restore from backup if validation fails
4. Generate diff for audit trail
5. Log all backup/restore operations

---

## Force-Continue Behavior

After maximum 3 attempts:
- Pipeline proceeds to Level 1
- Warning logged: "Level -1 checks not fully resolved after 3 attempts"
- `level_minus1_status` set to "OK" with force flag
- Downstream levels should check for force flag and add extra caution

---

## State Output

| Field | Value |
|-------|-------|
| `level_minus1_user_choice` | "auto-fix" or "skip" |
| `level_minus1_retry_count` | 0-3 |
| `level_minus1_status` | "OK" or "FAILED" |
