# Hook System Execution Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines how the PreToolUse and PostToolUse hooks enforce policies, track progress,
and optimize tool usage during Claude Code execution. Hooks are the runtime enforcement
layer that bridges pipeline policies with actual tool calls.

---

## Hook Architecture

```
[User Prompt] --> [UserPromptSubmit Hook] --> script-chain-executor.py (pre-tool mode)
                                                |
                                                v
                                          [Pipeline Levels -1, 1, 2, 3 Steps 0-9]
                                                |
                                                v
[Tool Call] --> [PreToolUse Hook] --> pre-tool-enforcer.py
                   |                     |
                   |                     +-- ALLOW (with hints)
                   |                     +-- BLOCK (with reason)
                   |
                   v
              [Tool Executes]
                   |
                   v
              [PostToolUse Hook] --> script-chain-executor.py (post-tool mode)
                                       |
                                       +-- post-tool-tracker.py
                                       +-- Progress tracking
                                       +-- Commit readiness check
                                       |
                                       v
[Session End] --> [Stop Hook] --> stop-notifier.py
                                    |
                                    +-- Session save
                                    +-- Steps 11-14 (auto PR, closure, docs, summary)
```

---

## PreToolUse Hook: `pre-tool-enforcer.py`

### Validation Checks (8 policies)

| Check | Policy | Action |
|-------|--------|--------|
| 1. Read file size | tool-optimization-policy.md | Block if > 50KB without offset/limit |
| 2. Grep result limit | tool-optimization-policy.md | Warn if > 50 matches expected |
| 3. Bash command safety | common-failures-prevention.md | Block dangerous commands |
| 4. Edit string match | common-failures-prevention.md | Verify old_string exists in file |
| 5. Write file backup | file-management-policy.md | Ensure backup before overwrite |
| 6. Skill context hint | auto-skill-agent-selection-policy.md | Inject per-file skill context |
| 7. Tool optimization | tool-optimization-policy.md | Suggest efficient alternatives |
| 8. MCP routing | mcp-plugin-discovery-policy.md | Route to MCP if available |

### Skill Context Injection (Dynamic Per-File)

For every tool call that targets a file:
1. Detect file extension (.py, .java, .ts, .kt, etc.)
2. Look up matching skill from session's skill selection
3. Inject skill context as hint in PreToolUse response
4. De-duplicate: don't re-inject same skill for same file type

### Response Format

```json
{
  "decision": "allow" | "block",
  "reason": "Human-readable explanation",
  "hints": [
    "Skill context: python-core (for .py files)",
    "Consider using Read with offset for large files"
  ]
}
```

---

## PostToolUse Hook: `post-tool-tracker.py`

### Tracking Actions (6 functions)

| Function | Purpose |
|----------|---------|
| 1. Progress update | Update task completion % based on tool calls |
| 2. File change tracking | Record which files were modified |
| 3. Commit readiness check | Determine if changes are ready for commit |
| 4. Token usage tracking | Count tokens consumed by tool call |
| 5. Error pattern detection | Check if tool result matches known error patterns |
| 6. Session accumulation | Append tool result summary to session |

### Commit Readiness Criteria

A commit is ready when:
- At least 1 file has been modified (Edit/Write tool used)
- No pending tool calls in the current phase
- No blocking errors in recent tool results
- Tests pass (if test tool was used)

---

## Stop Hook: `stop-notifier.py`

### Session Save Actions

1. Save session summary to `~/.claude/logs/sessions/{session_id}/`
2. Finalize flow-trace.json
3. Archive session metadata

### Auto-Execution (Hook Mode)

In Hook Mode (CLAUDE_HOOK_MODE=1), Stop hook triggers:
- Step 11: Auto-create PR with accumulated changes
- Step 12: Close associated GitHub issue
- Step 13: Update documentation
- Step 14: Generate final summary

---

## Hook Configuration

### Settings: `~/.claude/settings.json`

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "type": "command",
      "command": "python ~/.claude/scripts/script-chain-executor.py pre-tool",
      "async": false
    }],
    "PreToolUse": [{
      "type": "command",
      "command": "python ~/.claude/scripts/pre-tool-enforcer.py",
      "async": false
    }],
    "PostToolUse": [{
      "type": "command",
      "command": "python ~/.claude/scripts/script-chain-executor.py post-tool",
      "async": false
    }],
    "Stop": [{
      "type": "command",
      "command": "python ~/.claude/scripts/stop-notifier.py",
      "async": false
    }]
  }
}
```

### Critical Rule

All hooks MUST be **synchronous** (`async: false`). Async hooks cause race conditions
with pipeline state and tool execution ordering.

---

## Hook Failure Handling

| Scenario | Action |
|----------|--------|
| Hook script not found | Log warning, allow tool call |
| Hook script crashes | Log error, allow tool call |
| Hook returns BLOCK | Reject tool call, show reason |
| Hook timeout (>10s) | Kill hook, allow tool call |
| Hook returns invalid JSON | Log error, allow tool call |

**Principle:** Hook failures should NEVER block the user from working.
Only explicit BLOCK decisions from healthy hooks should prevent tool calls.

---

## Source of Truth

Hook scripts live in `claude-insight/scripts/` (the repo).
They are downloaded to `~/.claude/scripts/` by `hook-downloader.py`.

**NEVER edit `~/.claude/scripts/` directly.** Always edit in the repo,
commit, push, and re-download.

---

## Implementation

- **PreToolUse:** `scripts/pre-tool-enforcer.py`
- **PostToolUse:** `scripts/post-tool-tracker.py`
- **Chain Executor:** `scripts/script-chain-executor.py`
- **Stop Hook:** `scripts/stop-notifier.py`
- **Downloader:** `claude-code-ide/scripts/hook-downloader.py`
