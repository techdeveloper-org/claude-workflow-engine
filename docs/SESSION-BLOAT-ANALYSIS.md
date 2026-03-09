# SESSION BLOAT & SUBPROCESS LEAK ANALYSIS
**Date:** 2026-03-09 11:30
**Severity:** CRITICAL (causes auto-logout due to context bloat)

---

## PROBLEMS IDENTIFIED

### 1. ❌ flow-trace.json UNBOUNDED GROWTH
```
Location: ~/.claude/memory/logs/sessions/{SESSION_ID}/flow-trace.json
Current Size: 69-259 KB per session
Average: 100 KB per session
Total (20 sessions): 20 MB

Per-Entry Data:
- Each pipeline entry: ~3 KB
- Per session: 25-65 entries
- No truncation/rotation implemented
```

**Impact:**
- Context window fills up quickly (each trace loads in memory)
- Session auto-logout when context > 90%
- User can only do ~5-10 tool calls per session before logout

### 2. ❌ Session Folder Bloat
```
Location: ~/.claude/memory/sessions/
Current Size: 2.1 MB
Files: 411

Large Files:
- claude-insight/project-summary.md: 170 KB
- techdeveloper-ui/project-summary.md: 31 KB
- chain-index.json: 85 KB
```

**Impact:**
- Project summaries grow unbounded
- Session metadata accumulates over time
- Context usage for session loading

### 3. ❌ Hook Output Verbosity
```
3-level-flow.py: 244 print statements (4% of file)
post-tool-tracker.py: 10+ file operations
Each hook call outputs multiple lines to stdout
```

**Impact:**
- Claude Code reads all stdout and includes in context window
- Verbose output = context waste
- 244 print statements = lots of output

### 4. ⚠️  Potential Subprocess/Connection Issues
```
subprocess.run() calls found in:
- 3-level-flow.py: Multiple subprocess calls
- post-tool-tracker.py: May not close file handles properly (10 open() statements)
- No explicit cleanup/close in some paths
```

**Impact:**
- Stalled processes might consume resources
- File handles staying open
- Connection leaks if not properly closed

---

## ROOT CAUSE ANALYSIS

### Primary Cause: trace Pipeline Array Growth
**File:** `3-level-flow.py` and `post-tool-tracker.py`

Each tool call (PostToolUse hook):
```python
trace["pipeline"].append({
    "step": "TOOL_NAME",
    "status": "...",
    "input": {...},        # ← Can be large
    "output": {...},       # ← Can be large
    ...other fields...     # ← Many metadata fields
})
```

**Example entry size:**
```json
{
  "step": "Edit",
  "name": "Edit file",
  "input": {
    "file_path": "/long/path/to/file.py",
    "old_string": "...100+ chars...",
    "new_string": "...100+ chars..."
  },
  "output": {
    "result": "changed",
    "lines_affected": 5
  },
  ...15+ other fields...
}
```

**Per Session:**
- 25 tool calls = 25 entries
- 25 * 3 KB = 75 KB trace file
- Long sessions: 50+ tool calls = 150 KB+

**Problem:** No cleanup, no rotation. File grows for the entire session.

### Secondary Cause: Session Metadata Accumulation
**File:** `~/.claude/memory/sessions/{project}/project-summary.md`

These files keep growing as sessions accumulate data:
- Each project has ONE project-summary.md
- Gets appended to with each session
- No rotation or compression
- 170 KB for claude-insight alone!

---

## SOLUTIONS REQUIRED

### IMMEDIATE FIXES (High Priority)

#### 1. Trace Rotation: Keep only last N entries
```python
# In 3-level-flow.py and post-tool-tracker.py:
# BEFORE appending to pipeline:
MAX_TRACE_ENTRIES = 30  # Keep last 30 tool calls only
if len(trace["pipeline"]) >= MAX_TRACE_ENTRIES:
    trace["pipeline"] = trace["pipeline"][-MAX_TRACE_ENTRIES:]
```

**Impact:** Reduces trace from 100+ KB to ~90 KB (30 * 3 KB)

#### 2. Reduce Trace Verbosity: Remove large fields
```python
# Don't store raw input/output - just summary:
entry = {
    "step": "Edit",
    "status": "PASSED",
    "duration_ms": 125,
    "file_changed": True,      # ← Instead of full old_string/new_string
    "lines_affected": 5        # ← Instead of raw diff
}
# Save: ~2 KB per entry (down from 3 KB)
```

**Impact:** Saves 25-30% per entry

#### 3. Silent Hook Mode: Make print statements debug-only
```python
# In hooks:
DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
if DEBUG:
    print(f"[INFO] Step {step_name} completed")  # Only if debug enabled
# Remove all other prints or make them log-file only
```

**Impact:** Reduces stdout noise by 70-80%

#### 4. Session Metadata Cleanup
```python
# In session folder:
# Compress/archive old project-summary.md files
# Or: Keep only last 5 entries per project
# Or: Move to separate archive folder
```

**Impact:** Reduces session folder from 2.1 MB to <500 KB

### MEDIUM PRIORITY FIXES

#### 5. File Handle Management
```python
# In post-tool-tracker.py:
with open(trace_file, 'r') as f:
    data = json.load(f)  # ← Auto-closes
# Not: f = open(...); f.read()  # ← Requires explicit close
```

#### 6. Subprocess Cleanup
```python
# Ensure subprocess calls have timeouts:
try:
    result = subprocess.run(..., timeout=10)
except subprocess.TimeoutExpired:
    # Kill the process
    pass  # ← Process terminated on exception
```

---

## RECOMMENDED IMPLEMENTATION PLAN

### Phase 1: Immediate (Today)
1. Add trace rotation to 3-level-flow.py (keep last 30 entries)
2. Remove non-essential fields from trace entries
3. Make prints debug-only or log-file only
4. **Impact:** Session size from 100 KB → ~60 KB per session

### Phase 2: Short-term (This Week)
1. Implement session metadata cleanup
2. Compress old project-summary.md files
3. Review file handle management
4. **Impact:** Session folder from 2.1 MB → ~500 KB total

### Phase 3: Long-term (This Month)
1. Implement proper trace rotation (keep last 10, move older to archive)
2. Add session archival system
3. Implement automatic cleanup of sessions >7 days old
4. **Impact:** Infinite growth becomes finite/bounded

---

## VERIFICATION METRICS

**Before:**
- flow-trace.json: 100 KB/session (20 sessions = 2 GB potential)
- Context bloat causes logout after ~10 tool calls
- Session folder: 2.1 MB (411 files)

**After Phase 1:**
- flow-trace.json: ~60 KB/session
- Can handle ~50+ tool calls per session without logout
- Session folder: <2 MB (reduced metadata)

**After Phase 2:**
- flow-trace.json: ~40 KB/session (trimmed entries)
- Session folder: <500 KB total
- No auto-logout during normal work

**After Phase 3:**
- Auto-archival prevents growth
- Old sessions don't impact current work
- Bounded memory usage

---

## STATUS: Ready for Implementation

All issues identified, all solutions mapped.
User approval needed for Phase 1 fixes.
