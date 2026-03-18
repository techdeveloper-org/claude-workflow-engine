# Error Recovery Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines error classification, recovery strategies, and failure prevention for all
pipeline levels. Ensures the pipeline degrades gracefully rather than crashing,
and learns from past failures via the Failure Prevention KB.

---

## Error Classification

### By Severity

| Severity | Definition | Action |
|----------|-----------|--------|
| FATAL | Pipeline cannot continue | Stop pipeline, log error, notify user |
| RECOVERABLE | Step failed but can retry | Retry with backoff, then fallback |
| WARNING | Issue detected, non-blocking | Log warning, continue pipeline |
| INFO | Informational anomaly | Log only |

### By Source

| Source | Examples | Default Severity |
|--------|----------|-----------------|
| LLM Provider | Timeout, rate limit, model unavailable | RECOVERABLE |
| MCP Server | Connection refused, tool error | WARNING |
| File System | Permission denied, file not found | RECOVERABLE |
| Git/GitHub | Auth failure, merge conflict | RECOVERABLE |
| User Input | Invalid task, missing context | FATAL (ask user) |
| Internal Logic | State validation failure | FATAL |

---

## Recovery Strategies

### Strategy 1: Retry with Backoff

For transient failures (network, rate limits):

| Attempt | Delay | Action |
|---------|-------|--------|
| 1 | 0s | Immediate retry |
| 2 | 2s | Short backoff |
| 3 | 5s | Medium backoff |
| FAIL | - | Move to fallback strategy |

### Strategy 2: Fallback Chain

For LLM failures:

```
Primary LLM (Ollama local)
    |-- FAIL --> Secondary LLM (Anthropic API)
    |              |-- FAIL --> RAG cached result
    |                            |-- FAIL --> Manual prompt (ask user)
```

### Strategy 3: Graceful Degradation

For non-critical features:

| Feature | Degradation |
|---------|-------------|
| CallGraph analysis | Skip impact analysis, warn in review |
| RAG lookup | Skip cache, always call LLM |
| MCP discovery | Use known servers from config |
| Standards enforcement | Skip linting, log warning |
| UML generation | Skip diagrams, note in summary |

### Strategy 4: Checkpoint Recovery

For pipeline interruptions (Ctrl+C, crash):

1. Pipeline saves checkpoint after each successful step
2. On restart, load last checkpoint
3. Resume from last successful step + 1
4. User can choose: resume OR restart from beginning

---

## Retry Limits Per Level

| Level | Component | Max Retries | After Max |
|-------|-----------|-------------|-----------|
| -1 | Auto-fix | 3 | Force-continue with warning |
| 1 | Session loader | 2 | Use minimal session |
| 1 | Context loader | 2 | Return partial context |
| 2 | Standards loader | 2 | Use hardcoded defaults |
| 3 | Step 11 review | 3 | Mark as RISKY, require manual |
| 3 | GitHub operations | 3 | Skip GitHub integration |

---

## Failure Prevention KB

### Source: `common-failures-prevention.md`

Self-learning knowledge base with 13 pattern categories:

| Category | Pattern | Prevention |
|----------|---------|------------|
| Unicode | Non-ASCII in Python files | Level -1 auto-fix |
| Bash | Invalid commands on Windows | Use Git Bash syntax |
| Edit | String mismatch in Edit tool | Read file first, exact match |
| File | Permission denied | Check permissions before write |
| Tool | Tool timeout | Set appropriate timeouts |
| Git | Merge conflicts | Pull before push |
| Import | Module not found | Check requirements.txt |
| Encoding | cp1252 decode errors | UTF-8 everywhere |
| Path | Backslash in paths | Forward slashes only |
| API | Rate limiting | Exponential backoff |
| Memory | Context window overflow | TOON compression |
| Network | Connection timeout | Retry with backoff |
| State | Missing state field | Default values |

### KB Learning

When a new failure pattern is detected:
1. Log failure with full context (error type, step, input, stack trace)
2. Check if pattern matches existing KB entry
3. If new pattern: add to KB with prevention strategy
4. If existing: increment occurrence count, update last_seen

---

## Error Logging

### Structured Error Format

```json
{
  "timestamp": "2026-03-18T10:30:00Z",
  "session_id": "session-...",
  "level": "ERROR",
  "step": 5,
  "error_type": "LLMProviderError",
  "message": "Ollama connection refused",
  "recovery_action": "fallback_to_anthropic",
  "recovery_success": true,
  "stack_trace": "...",
  "context": {
    "model": "qwen2.5-coder:7b",
    "endpoint": "http://localhost:11434"
  }
}
```

### Error Logger: `error_logger.py`

- Tracks severity, error type, recovery action
- Saves audit trail per session
- Aggregates error patterns for Failure Prevention KB

---

## User Escalation

Escalate to user when:
1. All retry attempts exhausted
2. Error requires user decision (e.g., merge conflict resolution)
3. Task is invalid or ambiguous
4. Security-sensitive operation failed (credential issues)

---

## State Fields

| Field | Type | Purpose |
|-------|------|---------|
| `errors` | list | All errors across all levels (merged) |
| `warnings` | list | All warnings across all levels (merged) |
| `final_status` | str | "OK", "PARTIAL", "FAILED", "BLOCKED" |
| `failure_prevention` | dict | Loaded KB entries |
| `failure_prevention_warnings` | list | Pre-emptive warnings from KB |

---

## Implementation

- **Error Logger:** `scripts/langgraph_engine/error_logger.py`
- **Recovery Handler:** `scripts/langgraph_engine/recovery_handler.py`
- **Backup Manager:** `scripts/langgraph_engine/backup_manager.py`
- **Failure KB:** `policies/03-execution-system/common-failures-prevention.md`
- **Checkpoint:** Per-step JSON in session directory
