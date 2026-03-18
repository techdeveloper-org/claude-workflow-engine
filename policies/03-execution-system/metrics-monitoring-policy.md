# Metrics & Monitoring Policy

**Version:** 1.0.0
**Priority:** MEDIUM
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines metrics collection, aggregation, and monitoring for pipeline execution.
Provides visibility into session performance, step durations, LLM costs, and
tool usage patterns.

---

## Metrics Collection Points

### Per-Step Metrics

Collected after each of the 15 steps (0-14):

| Metric | Type | Source |
|--------|------|--------|
| `step_duration_ms` | float | Timer around step execution |
| `step_status` | str | "success", "failed", "skipped" |
| `step_tokens_in` | int | LLM input tokens (if LLM called) |
| `step_tokens_out` | int | LLM output tokens (if LLM called) |
| `step_model_used` | str | Model ID (e.g., "ollama/qwen2.5-coder:7b") |
| `step_rag_hit` | bool | Whether RAG cache was used |
| `step_error` | str | Error message (if failed) |

### Per-Session Metrics

Aggregated at session completion (Step 14 or Stop hook):

| Metric | Type | Source |
|--------|------|--------|
| `total_duration_ms` | float | Sum of all step durations |
| `total_tokens` | int | Sum of all LLM tokens |
| `total_steps_executed` | int | Count of non-skipped steps |
| `total_steps_failed` | int | Count of failed steps |
| `rag_hit_rate` | float | % of eligible steps that used RAG cache |
| `final_status` | str | "OK", "PARTIAL", "FAILED" |

### LLM Provider Metrics

Per-provider aggregation:

| Metric | Type | Source |
|--------|------|--------|
| `provider_name` | str | "ollama", "anthropic", "openai", "groq" |
| `total_calls` | int | Number of LLM calls |
| `total_tokens` | int | Total tokens consumed |
| `avg_latency_ms` | float | Average response time |
| `error_rate` | float | % of failed calls |
| `cost_estimate` | float | Estimated cost (API providers only) |

### Tool Usage Metrics

Per-tool aggregation:

| Metric | Type | Source |
|--------|------|--------|
| `tool_name` | str | Tool identifier |
| `call_count` | int | Number of invocations |
| `total_duration_ms` | float | Total execution time |
| `avg_duration_ms` | float | Average execution time |
| `token_savings` | int | Tokens saved by tool optimization |

---

## Storage

### Telemetry JSONL

Each step appends a line to `~/.claude/logs/telemetry/{session_id}.jsonl`:

```json
{
  "timestamp": "2026-03-18T10:30:00Z",
  "session_id": "session-20260318-103000-abc12345",
  "step": 5,
  "step_name": "skill_selection",
  "duration_ms": 1234,
  "status": "success",
  "model": "ollama/qwen2.5-coder:7b",
  "tokens_in": 500,
  "tokens_out": 150,
  "rag_hit": true
}
```

### Step Logs

Per-step JSON in `session_dir/step-logs/step-{NN}.json`:
- Full step input/output
- Decision rationale
- Error details (if failed)

---

## Aggregation

### CLI Metrics Tool

`scripts/langgraph_engine/metrics_aggregator.py` provides:

| Command | Output |
|---------|--------|
| `--session {id}` | Single session metrics |
| `--last N` | Last N sessions summary |
| `--provider-stats` | LLM provider comparison |
| `--tool-stats` | Tool usage patterns |
| `--step-breakdown` | Average duration per step |

### Dashboard Display

`scripts/langgraph_engine/metrics_dashboard.py` provides:
- ASCII table display for terminal
- Formatted data for web dashboard integration
- Historical trend comparison

---

## Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Step duration | > 30s | > 120s |
| Total session duration | > 5 min | > 15 min |
| LLM error rate | > 10% | > 30% |
| RAG hit rate (mature) | < 30% | < 10% |
| Token usage per session | > 10K | > 50K |

---

## Implementation

- **Aggregator:** `scripts/langgraph_engine/metrics_aggregator.py`
- **Dashboard:** `scripts/langgraph_engine/metrics_dashboard.py`
- **Step Logger:** `scripts/langgraph_engine/step_logger.py`
- **Telemetry:** JSONL files in `~/.claude/logs/telemetry/`
