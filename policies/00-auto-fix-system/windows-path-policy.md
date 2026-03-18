# Windows Path Validation Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Scope:** Windows only (sys.platform == 'win32')

---

## Purpose

Hardcoded Windows-style paths (`C:\Users\...`, `D:\projects\...`) in Python source files
cause cross-platform failures and are a code smell. All paths should use forward slashes
or `pathlib.Path` / `os.path.join` for cross-platform compatibility.

---

## Detection

1. Scan all `.py` files in the project directory
2. Cap scan at **500 files** to prevent timeout
3. For each file, check for both `"\\"` AND `":\\"` patterns in content
4. This catches `C:\`, `D:\`, etc. while avoiding false positives on single backslashes
5. Report problem files in error state

---

## Detection Pattern

```python
# Matches: "C:\\Users\\", "D:\\projects\\"
# Avoids: "\\n" (newline), "\\t" (tab) when not preceded by drive letter
if "\\" in content and ":\\" in content:
    # File contains Windows-style paths
```

---

## Auto-Fix Strategy

1. **Backup** the file before modification (via BackupManager)
2. Apply regex substitutions to convert backslash paths to forward slashes
3. **Preserve** escape sequences (`\n`, `\t`, `\r`, `\\\\` for literal backslash)
4. **Validate** file integrity after modification (syntax check)
5. If validation fails, **restore** from backup
6. Generate diff for audit trail

---

## Fix Safety Rules

| Rule | Rationale |
|------|-----------|
| Always backup before fix | Restore on failure |
| Validate after fix | Catch broken syntax |
| Preserve escape sequences | `\n`, `\t` are NOT paths |
| Generate diff | Audit trail for review |
| Restore on failure | No data loss |

---

## Known Limitations

- Regex may over-match strings with embedded backslashes used for non-path purposes
- Complex escape sequences may require manual review
- Files with mixed path styles need careful handling

---

## Success Criteria

- No `.py` files contain `":\\"` pattern (drive-letter backslash paths)
- OR: All detected paths successfully converted to forward slashes

---

## State Output

| Field | Value |
|-------|-------|
| `windows_path_check` | "PASS" or "FAIL" |
