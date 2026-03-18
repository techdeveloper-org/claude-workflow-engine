# Tool Optimization Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines optimization rules for Claude Code tool usage to minimize token consumption,
prevent excessive file reads, and enforce efficient search patterns. These rules are
loaded by Level 2 (`node_tool_optimization_standards`) and enforced by the PreToolUse hook.

---

## Tool Usage Limits

### Read Tool

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `read_max_lines` | 500 | Prevents reading entire large files |
| `read_max_bytes` | 51,200 (50KB) | Memory budget per file read |
| `cache_after_n_reads` | 3 | Cache file content after 3rd read of same file |

### Search Tools

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `grep_max_matches` | 50 | Limit matches per grep call |
| `grep_max_results` | 100 | Total result cap across all grep calls |
| `search_max_results` | 10 | Web/semantic search result limit |

### Bash Tool

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `bash_find_head` | 20 | Limit `find` output to 20 results |

---

## Tree Pattern (Structure-First Approach)

**NEW in v1.0:** Before searching for files, understand directory structure first.

### Rule

> Use `find` command FIRST to understand directory structure before searching for
> specific files. This saves 80-90% tokens on file location searches.

### Example

```bash
# GOOD: Understand structure first (20 tokens)
find . -type d -maxdepth 3 | head -20

# BAD: Blind grep across entire project (2000+ tokens)
grep -r "className" .
```

### When to Apply

- User asks to find a file or class
- User asks to modify code in an unknown location
- First interaction with a new project/directory

### Platform Note

Works in Git Bash on Windows (unlike `tree` command which is unavailable).

---

## Enforcement

### PreToolUse Hook

The `pre-tool-enforcer.py` checks each tool call against these rules:
1. Read tool: Check line count and byte size against limits
2. Grep tool: Check match count against limits
3. Bash tool: Suggest `find | head` pattern for directory exploration
4. All tools: Suggest cached result if same file read 3+ times

### Violation Handling

| Severity | Action |
|----------|--------|
| WARNING | Log violation, allow tool call to proceed |
| BLOCK | Reject tool call, suggest optimized alternative |

Tool optimization violations are **warnings by default** - they guide behavior
but do not block pipeline execution.

---

## State Fields

| Field | Type | Purpose |
|-------|------|---------|
| `tool_optimization_rules` | dict | All 7 rules loaded |
| `tool_optimization_loaded` | bool | Whether rules loaded successfully |

---

## Integration

- **Loaded by:** Level 2 `node_tool_optimization_standards`
- **Enforced by:** `scripts/pre-tool-enforcer.py` (PreToolUse hook)
- **Consumed by:** Level 3 Steps 5, 10 (tool selection and implementation)
