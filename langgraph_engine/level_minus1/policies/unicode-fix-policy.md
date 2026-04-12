# Unicode UTF-8 Fix Policy

**Version:** 1.0.0
**Priority:** CRITICAL
**Status:** ACTIVE
**Scope:** Windows only (sys.platform == 'win32')

---

## Purpose

Windows uses cp1252 encoding by default for console output. Python scripts that output
Unicode characters (emojis, non-Latin text, special symbols) will crash with
`UnicodeEncodeError` unless stdout/stderr are reconfigured to UTF-8.

---

## Detection

1. Check if `sys.platform == 'win32'`
2. If not Windows, mark as PASS (skip)
3. Attempt to reconfigure `sys.stdout` and `sys.stderr` to UTF-8 encoding
4. Use `sys.stdout.reconfigure(encoding='utf-8')` (Python 3.7+)
5. Fallback: wrap `sys.stdout.buffer` with `io.TextIOWrapper(encoding='utf-8')`

---

## Auto-Fix Strategy

| Method | Priority | Approach |
|--------|----------|----------|
| `reconfigure()` | 1st | Direct encoding change (Python 3.7+) |
| `TextIOWrapper` | 2nd | Buffer wrapping (older Python) |

---

## Success Criteria

- `sys.stdout.encoding` returns `'utf-8'` (case-insensitive)
- `sys.stderr.encoding` returns `'utf-8'` (case-insensitive)

---

## Failure Handling

- If both methods fail, mark check as FAIL
- Log error with method attempted and exception details
- Do NOT crash pipeline - allow user to decide (skip or retry)

---

## State Output

| Field | Value |
|-------|-------|
| `unicode_check` | "PASS" or "FAIL" |
