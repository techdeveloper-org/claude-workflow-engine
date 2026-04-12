# Context Management Policy (Level 1)

**Version:** 3.0.0
**Status:** Active
**Last Updated:** 2026-03-05

---

## Overview

Context Management Policy monitors, tracks, and optimizes Claude's context window usage in real-time. It prevents token overflow, manages memory efficiently, and ensures continuous operation within token budgets.

**Location:** `policies/01-sync-system/context-management/`
**Implementation:** `scripts/architecture/01-sync-system/context-management/context-monitor.py`

---

## Responsibilities

### 1. **Context Usage Monitoring**
- Track real-time token consumption
- Calculate percentage of context window used
- Monitor per-session and aggregate usage
- Alert when approaching limits (80%, 90%, 95%)

### 2. **Context Estimation & Projection**
- Estimate tokens consumed by current session
- Project token consumption for next N operations
- Predict when context overflow will occur
- Recommend cleanup timing

### 3. **Intelligent Context Optimization**
- Select which files to cache vs load full
- Summarize long files to reduce tokens
- Prune old session history
- Consolidate similar context entries

### 4. **Cleanup & Pruning**
- Auto-delete old sessions when threshold exceeded
- Archive completed sessions to disk
- Remove redundant context entries
- Maintain only essential context in memory

### 5. **Token Budget Management**
- Respect configured token limits (e.g., 200k tokens)
- Reserve space for response generation
- Allocate tokens across components fairly
- Prevent catastrophic overflow

---

## Key Metrics Tracked

| Metric | Purpose | Trigger Action |
|--------|---------|-----------------|
| Current Usage % | Know how full context is | Log every minute |
| Projected Usage | Predict overflow | At 80% usage |
| Session Age | Cleanup old sessions | > 24 hours old |
| File Size (tokens) | Decide compression | > 500 tokens |
| Redundancy Score | Find duplicate context | > 0.8 similarity |

---

## Execution Flow

```
Session Start
    ↓
Load Context Monitor
    ├─ Calculate current usage
    ├─ Estimate session size
    └─ Project future usage
    ↓
Monitor Loop (every tool call):
    ├─ Update usage %
    ├─ Check thresholds
    ├─ Log metrics
    └─ Trigger cleanup if needed
    ↓
Tool Execution
    ├─ Monitor token consumption
    ├─ Track file sizes loaded
    └─ Update running totals
    ↓
Session End
    ├─ Final usage calculation
    ├─ Archive if > 90% used
    └─ Cleanup old sessions
```

---

## Thresholds & Actions

### **GREEN ZONE: 0-70% Usage**
```
Status: OPTIMAL
Action: Monitor normally
Log:    Standard metrics only
```

### **YELLOW ZONE: 70-85% Usage**
```
Status: CAUTION
Action: Start optimization
Log:    Hourly compression recommendations
```

### **ORANGE ZONE: 85-95% Usage**
```
Status: ALERT
Action: Aggressive cleanup
Log:    Every action logged
Clean:  Archive sessions, prune history
```

### **RED ZONE: 95%+ Usage**
```
Status: CRITICAL
Action: Emergency cleanup
Log:    Every token tracked
Clean:  Delete old sessions immediately
Force:  Remove non-essential context
```

---

## Cleanup Strategy

### **Stage 1: Soft Cleanup (70-85% Usage)**
1. Compress large files (> 500 tokens)
2. Summarize old conversation history
3. Archive old sessions to disk
4. Remove duplicate context entries

### **Stage 2: Aggressive Cleanup (85-95% Usage)**
1. Delete sessions older than 24 hours
2. Reduce file cache to essentials only
3. Compress all files aggressively
4. Keep only last 5 sessions in memory

### **Stage 3: Emergency Cleanup (95%+ Usage)**
1. Delete all sessions except current
2. Clear all caches
3. Load files on-demand only
4. Disable non-essential features

---

## Helper Scripts

| Script | Purpose |
|--------|---------|
| `context-monitor.py` | Main monitoring engine |
| `context-monitor.py` | Token estimation & projection |
| `context-extractor.py` | Extract context from files |
| `context-cache.py` | In-memory context caching |
| `auto-context-pruner.py` | Automatic pruning logic |
| `smart-file-summarizer.py` | File compression & summarization |
| `tiered-cache.py` | Multi-tier caching strategy |
| `smart-cleanup.py` | Cleanup orchestration |
| `monitor-and-cleanup-context.py` | Combined monitoring + cleanup |
| `monitor-context.py` | Baseline monitoring |
| `session-pruning-policy.py` | Session-specific pruning |
| `file-type-optimizer.py` | File-type-specific optimization |
| `update-context-usage.py` | Update usage metrics |

---

## Integration Points

### **Triggered By:**
- Session start (initialize monitoring)
- Tool execution (track usage)
- Session end (final calculation)
- Every 5 minutes (periodic check)
- Context threshold breach (alert & cleanup)

### **Provides Data To:**
- `3-level-flow.py` (decision-making context)
- `pre-tool-enforcer.py` (tool optimization hints)
- `post-tool-tracker.py` (progress metrics)
- `stop-notifier.py` (session summary)

### **Reads From:**
- Current session state
- File sizes and types
- Session history
- User preferences

---

## Configuration

```python
# Token Budget
MAX_CONTEXT_TOKENS = 200000
RESERVE_FOR_RESPONSE = 20000  # Always keep 20k for Claude's response
USABLE_TOKENS = 180000

# Thresholds
GREEN_THRESHOLD = 0.70    # 70%
YELLOW_THRESHOLD = 0.85   # 85%
ORANGE_THRESHOLD = 0.95   # 95%

# Cleanup Timings
SOFT_CLEANUP_INTERVAL = 300      # 5 minutes
AGGRESSIVE_CLEANUP_INTERVAL = 60  # 1 minute
SESSION_ARCHIVE_AGE = 86400       # 24 hours
SESSION_DELETE_AGE = 259200       # 72 hours

# Compression
FILE_COMPRESSION_THRESHOLD = 500  # Compress files > 500 tokens
COMPRESSION_RATIO = 0.3           # Compress to 30% of original
```

---

## Metrics Output

### **Per-Tool Execution:**
```json
{
  "timestamp": "2026-03-05T21:04:30Z",
  "context_usage": {
    "current_tokens": 165000,
    "max_tokens": 200000,
    "usage_percent": 82.5,
    "threshold_zone": "ORANGE",
    "trend": "increasing"
  },
  "projections": {
    "tokens_after_next_10_tools": 175000,
    "estimated_overflow_time": "15 minutes",
    "recommendation": "Start cleanup"
  },
  "cleanup_actions": {
    "sessions_archived": 2,
    "files_compressed": 5,
    "tokens_freed": 8000
  }
}
```

### **Per-Session Summary:**
```json
{
  "session_id": "SESSION-20260305-210424-75B6",
  "context_statistics": {
    "peak_usage": 92,
    "average_usage": 75,
    "final_usage": 45,
    "total_tokens_processed": 2500000
  },
  "cleanup_events": 3,
  "archival_status": "archived"
}
```

---

## Error Handling

### **Scenario 1: Context Overflow Imminent**
```
Detection: Usage > 95%
Action:    EMERGENCY_CLEANUP
  1. Delete all non-current sessions
  2. Clear all caches
  3. Load files on-demand
Fallback:  Restrict to essential operations only
```

### **Scenario 2: File Too Large to Load**
```
Detection: File size > available tokens
Action:    Compress or summarize file
Fallback:  Load first N tokens only, warn user
```

### **Scenario 3: Projection Indicates Overflow**
```
Detection: Projected usage > 95% within 10 tools
Action:    Start aggressive cleanup
Fallback:  Reduce operation scope
```

---

## Best Practices

✅ **DO:**
- Monitor context usage continuously
- Clean up before overflow (at 85% threshold)
- Archive old sessions regularly
- Compress large files proactively
- Reserve tokens for response generation

❌ **DON'T:**
- Let context exceed 95% before cleanup
- Delete current session data
- Disable monitoring for "speed"
- Ignore usage trends
- Assume unlimited context

---

## Success Criteria

- ✅ Context never exceeds 98% usage
- ✅ Average usage stays below 80%
- ✅ Cleanup completes in < 500ms
- ✅ Old sessions archived automatically
- ✅ File compression achieves 30-50% reduction
- ✅ No data loss during cleanup
- ✅ Metrics logged every 5 minutes
- ✅ Alerts triggered at correct thresholds

---

## Related Policies

- **Session Management Policy:** Handles session persistence
- **Context Optimization:** Handles token-efficient coding
- **Tool Usage Optimization:** Prevents unnecessary large reads
- **Pattern Detection:** Finds repeating context to compress

---

**Policy Status:** ✅ ACTIVE
**Last Verified:** 2026-03-05
**Next Review:** 2026-04-05
