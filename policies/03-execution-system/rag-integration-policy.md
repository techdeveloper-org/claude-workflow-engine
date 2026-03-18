# RAG Integration Policy

**Version:** 1.0.0
**Priority:** CRITICAL
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines how the RAG (Retrieval-Augmented Generation) layer caches and retrieves pipeline
decisions using Qdrant Vector DB. Every LangGraph node stores its decision; before LLM
calls, the pipeline checks RAG for similar past decisions to save inference time and
improve consistency.

---

## Architecture

```
[LangGraph Node]
       |
       v
[RAG Lookup] ---> [Vector DB: node_decisions]
       |
       +-- HIT (confidence >= threshold) --> Use cached decision (skip LLM)
       +-- MISS --> Call LLM --> Store decision in Vector DB
```

---

## Vector DB Collections (4)

| Collection | Purpose | Schema |
|------------|---------|--------|
| `node_decisions` | Pipeline node decision history | {node_name, decision, context_hash, confidence, timestamp} |
| `sessions` | Session metadata and summaries | {session_id, summary, tags, created_at} |
| `flow_traces` | Full flow execution traces | {session_id, trace_data, step_count, status} |
| `tool_calls` | Tool usage patterns and outcomes | {tool_name, params_hash, result_summary, success} |

---

## RAG-Eligible Steps

Only decision-making steps use RAG lookup. Implementation steps (10+) do NOT cache
because their output depends on specific code context.

| Step | Eligible | Threshold | Rationale |
|------|----------|-----------|-----------|
| 0 (Task Analysis) | YES | 0.82 | Task classification is repeatable |
| 1 (Task Breakdown) | YES | 0.80 | Similar tasks break down similarly |
| 2 (Plan Decision) | YES | 0.85 | Complexity scoring is deterministic |
| 3 (Phase Breakdown) | NO | - | Depends on specific task details |
| 4 (TOON Refinement) | NO | - | Depends on current context |
| 5 (Skill Selection) | YES | 0.78 | Skills match file types reliably |
| 6 (Skill Validation) | NO | - | Validation is cheap, no LLM |
| 7 (Prompt Generation) | YES | 0.85 | Similar tasks produce similar prompts |
| 8 (Progress Tracking) | YES | 0.75 | Progress patterns are repeatable |
| 9-14 | NO | - | Execution steps, context-dependent |

**Default threshold:** 0.82

---

## Store Strategy

### When to Store

- After EVERY successful LLM call in eligible steps
- Include: node name, decision output, input context hash, confidence score
- Timestamp for freshness ordering

### What to Store

```json
{
  "node_name": "step0_task_analysis",
  "decision": "Task type: feature, complexity: 7",
  "context_hash": "sha256_of_input_context",
  "confidence": 0.92,
  "session_id": "session-20260318-...",
  "timestamp": "2026-03-18T10:30:00Z",
  "model_used": "ollama/qwen2.5-coder:7b",
  "tokens_saved": 0
}
```

---

## Query Strategy

### When to Query

- Before every LLM call in eligible steps
- Use input context as query vector
- Retrieve top-3 similar decisions

### Decision Logic

```
IF top_result.confidence >= step_threshold:
    USE cached decision (skip LLM)
    LOG: "RAG hit - saved {estimated_tokens} tokens"
ELSE:
    CALL LLM normally
    STORE result in Vector DB
```

---

## Cross-Session Learning

### Pattern Detection

- When Step 5 (Skill Selection) runs, RAG checks if the same skill was selected
  for similar file types across 3+ sessions
- If pattern confidence > 0.90, boost that skill's ranking
- Enables: "learning" from past sessions without explicit memory

### Session Boost

```
skill_score = base_score + (rag_boost * pattern_confidence)
rag_boost = 0.15  # 15% boost for cross-session patterns
```

---

## Cache Invalidation

| Trigger | Action |
|---------|--------|
| Policy file updated | Invalidate decisions referencing that policy |
| Skill definition changed | Invalidate skill selection decisions |
| Project type changes | Invalidate all project-specific decisions |
| Manual: `--clear-rag-cache` | Clear all collections |
| Age > 30 days | Lower confidence by 10% per week past 30 days |

---

## Privacy & Safety

- Decisions are stored locally (Qdrant on localhost)
- No sensitive code content is stored - only decision metadata
- Context is hashed, not stored in plain text
- Cache can be fully cleared without affecting pipeline functionality

---

## Performance Targets

| Metric | Target |
|--------|--------|
| RAG lookup latency | < 50ms |
| Token savings per hit | 500-2000 tokens |
| Cache hit rate (mature system) | 40-60% on eligible steps |
| Storage per session | ~5KB |

---

## Implementation

- **Module:** `scripts/langgraph_engine/rag_integration.py`
- **MCP Server:** `src/mcp/vector_db_mcp_server.py` (11 tools)
- **Vector DB:** Qdrant (localhost, default port 6333)
- **Embedding Model:** sentence-transformers (configurable)
