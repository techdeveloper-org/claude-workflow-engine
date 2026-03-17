# Final Summary Policy - Step 14

**Version:** 1.0.0
**Part of:** Level 3: Execution System (15 Steps: 0-14)
**Step:** 14 - Final Summary Generation
**Status:** Active
**Date:** 2026-03-17

---

## Overview

Step 14 is the terminal step of the pipeline. It generates a comprehensive execution summary from all prior steps, saves it to the session folder, and optionally sends a voice notification. This step ALWAYS runs (never skipped) as it provides the final execution record.

**Input:** All step outputs aggregated from Steps 0-13
**Output:** Summary dict, saved summary file, optional voice notification
**RAG Threshold:** 0.75 (low stakes, summary generation)

---

## Policy Scope

**Applies to:** Level 3: Execution System, Step 14 (Terminal)
**Predecessor:** Step 13 (Documentation Update)
**Successor:** None - Pipeline ends after Step 14
**Post-Step:** `level3_merge` -> `output_node` -> `END`

---

## Summary Generation

### 14.1 Summary Data Collected

The summary dict aggregates from ALL steps:

| Field | Source | Description |
|-------|--------|-------------|
| `task_type` | Step 0 | Classified task type |
| `complexity` | Step 0 | Complexity score (1-10) |
| `plan_used` | Step 1 | Whether planning was enabled |
| `skill_selected` | Step 5 | Selected skill name |
| `agent_selected` | Step 5 | Selected agent name |
| `issue_created` | Step 8 | Whether GitHub issue was created |
| `issue_url` | Step 8 | GitHub issue URL |
| `pr_url` | Step 11 | Pull request URL |
| `pr_merged` | Step 11 | Whether PR was merged |
| `files_modified` | Step 10 | Count of modified files |
| `modified_files_list` | Step 10 | File paths (capped at 20) |
| `status` | Computed | Always "COMPLETED" |
| `timestamp` | Generated | ISO format timestamp |

### 14.2 Summary File

ALWAYS saved to session folder as `execution-summary.txt`:
- Uses `_build_summary_text()` helper for formatted output
- Includes all summary fields in human-readable format
- Saved with UTF-8 encoding
- If session folder is unavailable: Log warning, do NOT error

### 14.3 Metrics Display

Step 14 prints pipeline execution metrics to terminal:
- Per-step execution times
- Total pipeline duration
- RAG hit/miss statistics
- LLM calls saved by RAG

---

## Voice Notification

Best-effort voice notification using `voice-notifier.py`:

### Voice Message Format
```
Pipeline complete. {task_type} task, complexity {complexity}.
Using {skill}. Issue created. PR merged. {N} files modified.
```

### Voice Rules

1. **Best-effort only** - Voice failure NEVER blocks pipeline
2. **60-second timeout** - Generous for Coqui TTS model loading
3. **Script must exist** - Skip silently if `voice-notifier.py` not found
4. **Debug-level logging** - Voice failures logged at debug (not warning)
5. **Non-blocking** - Uses subprocess with timeout, not async

---

## Output State Keys

| Key | Type | Description |
|-----|------|-------------|
| `step14_summary` | dict | Complete summary object |
| `step14_summary_saved` | bool | Whether summary file was written |
| `step14_voice_sent` | bool | Whether voice notification succeeded |
| `step14_status` | str | `OK` or `ERROR` |
| `step14_error` | str | Error message (if status is ERROR) |

---

## Post-Step 14: Output Node

After Step 14, the pipeline flows to `output_node` which:
1. Synthesizes the comprehensive prompt from all step outputs
2. Saves the execution log to session folder
3. Calls RAG storage for cross-session learning
4. Sends session accumulate via MCP
5. Prints final pipeline status

---

## Quality Requirements

1. **Always execute** - Step 14 must never be skipped
2. **Summary file is mandatory** - ALWAYS attempt to save to session folder
3. **Voice is optional** - Never block on voice notification
4. **Cap file lists** - Maximum 20 files in modified_files_list
5. **ISO timestamps** - Use ISO 8601 format for all timestamps

---

## Error Handling

- Summary generation error: Return `ERROR` status with details
- File save error: Log warning, set `summary_saved: False`
- Voice timeout: Log at debug level, set `voice_sent: False`
- Voice script missing: Skip silently, set `voice_sent: False`
- Exception: Return `ERROR` status, pipeline still reaches END node

---

## Implementation Reference

- **Node function:** `step14_final_summary_node()` in `subgraphs/level3_execution_v2.py`
- **Core logic:** `step14_final_summary_generation()` in `subgraphs/level3_execution.py`
- **Summary text builder:** `_build_summary_text()` in `subgraphs/level3_execution.py`
- **Metrics display:** `langgraph_engine/metrics_collector.py`
- **Voice notifier:** `scripts/voice-notifier.py`
