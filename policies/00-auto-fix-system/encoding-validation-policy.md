# ASCII-Only Encoding Validation Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Scope:** Windows only (sys.platform == 'win32')

---

## Purpose

Python source files (.py) must contain only ASCII characters to ensure cp1252 compatibility
on Windows. Non-ASCII characters (Unicode literals, accented chars, emojis in comments)
cause `SyntaxError` or `UnicodeDecodeError` when processed by tools that assume ASCII/cp1252.

---

## Detection

1. Scan all `.py` files in the project directory
2. Cap scan at **500 files** to prevent timeout on large projects
3. For each file, attempt `content.decode("ascii")`
4. If decode fails, file contains non-ASCII content - record it
5. Report first 3 non-ASCII files in error state

---

## Scan Limits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max files scanned | 500 | Prevent timeout on large monorepos |
| Error reporting | First 3 files | Keep error messages concise |

---

## Auto-Fix Limitations

**Cannot auto-fix.** Non-ASCII content requires human judgment:
- Could be intentional (i18n strings, Unicode test data)
- Could be accidental (copy-paste from web, smart quotes)
- Removing characters could break functionality

**Action:** Report non-ASCII files and flag for manual review.

---

## Success Criteria

- All scanned `.py` files pass ASCII decode check
- OR: No `.py` files found (empty project)

---

## Failure Handling

- Mark check as FAIL
- Include list of non-ASCII files (first 3) in error state
- Log: "Non-ASCII files detected - manual edit needed"
- Allow user to skip (non-blocking with user consent)

---

## State Output

| Field | Value |
|-------|-------|
| `encoding_check` | "PASS" or "FAIL" |
