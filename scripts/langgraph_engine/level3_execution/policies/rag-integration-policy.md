# RAG Integration Policy

**Version:** 1.1.0
**Priority:** CRITICAL
**Status:** ACTIVE
**Updated:** 2026-04-04

---

## Purpose

Defines how the RAG (Retrieval-Augmented Generation) layer caches and retrieves pipeline
decisions using Qdrant Vector DB. Session summaries and flow traces are stored for
cross-session learning. The `RAGLayer` class provides `store()` and `lookup()` methods
for any pipeline node.

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

Only decision-making steps that call LLMs use RAG lookup. Implementation steps
(10+) do NOT cache because their output depends on specific code context.
Steps 1-7 were removed from the active graph in v1.13.0.

| Step | Eligible | Threshold | Rationale |
|------|----------|-----------|-----------|
| 0 (Task Analysis) | YES | 0.85 | Task classification is repeatable |
| 8 (GitHub Issue Creation) | YES | 0.78 | Issue label/template selection |
| 11 (PR Review) | YES | 0.85 | Review criteria are consistent |
| 13 (Documentation) | YES | 0.80 | Doc update patterns are repeatable |
| 14 (Summary) | YES | 0.75 | Summary patterns are simple |
| Pre-Analysis (orchestration) | NO | - | RAG lookup removed in v1.15.0 |
| 9-12 (execution) | NO | - | Execution steps, context-dependent |

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

### Session Summary Storage

- At pipeline end (output_node), `RAGLayer.store_session_summary()` records the full
  session outcome in the `sessions` collection
- Includes: task_type, skill, agent, final_status, user_prompt summary

### Flow Trace Storage

- `RAGLayer.store_flow_trace()` records per-level status in `flow_traces`
- Levels: level_minus1, level1, level2

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
| Cache hit rate (mature system) | 20-40% on eligible steps |
| Storage per session | ~5KB |

---

## Implementation

- **Module:** `scripts/langgraph_engine/rag_integration.py`
- **MCP Server:** `src/mcp/vector_db_mcp_server.py` (11 tools)
- **Vector DB:** Qdrant (localhost, default port 6333)
- **Embedding Model:** sentence-transformers (configurable)

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-03-18 | Initial policy with per-node RAG cache for steps 0,1,2,5,7,8 |
| 1.1.0 | 2026-04-04 | Removed orchestration-level RAG (pre-analysis gate); removed per-node RAG from _run_step; steps 1,2,5,7 removed from eligible list (removed from active graph v1.13.0) |
