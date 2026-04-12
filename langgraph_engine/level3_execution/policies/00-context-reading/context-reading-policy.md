# Project Context Reading Policy (Pre-Flight)

**VERSION:** 1.0.0
**CREATED:** 2026-03-06
**PRIORITY:** 🔴 CRITICAL - Step 3.0.0 (BEFORE Prompt Generation)
**STATUS:** 🟢 ACTIVE

---

## Overview

**Mandatory Pre-Flight Step:**
Before ANY prompt generation or execution, automatically detect and read project context files to provide Claude with project knowledge before making decisions.

The system reads:
1. `README.md` - Project overview, architecture, tech stack
2. `CHANGELOG.md` - Version history and recent changes
3. `VERSION` - Current project version
4. `SRS.md` or `SYSTEM_REQUIREMENTS_SPECIFICATION.md` - Core requirements
5. `CLAUDE.md` - Project-specific instructions

**Key Behavior:**
- ✅ If context files found → Read and cache for session
- ✅ If NO files found (new project) → Skip gracefully, proceed with generic context
- ✅ Cache result in session for reuse across multiple requests
- ✅ Pass metadata to prompt generation for enrichment
- ✅ Complete traceability in flow-trace.json

---

## Execution Order

```
User Input ("please implement X")
         ↓
    3-Level Flow starts
         ↓
Level -1: Auto-Fix Enforcement
Level 1: Sync System
Level 2: Standards System
         ↓
🔴 STEP 3.0.0: CONTEXT READING (THIS POLICY - PRE-FLIGHT)
         ↓
      Scan Project Root
         ↓
    Files Found?
      /        \
    YES        NO
     ↓          ↓
  Read All   Skip
  Files    (New Project)
     ↓          ↓
  Cache      Continue
     ↓          ↓
    Pass to Prompt Gen ←────┘
     ↓
Step 3.0: Structured Prompt Generation (enriched with context)
     ↓
Step 3.1: Task Breakdown
Step 3.2-3.12: Rest of pipeline
     ↓
Done!
```

---

## Detection Logic

**File Search Order (Priority):**

1. **README.md** (High Priority)
   - Extract: First 500 lines
   - Contains: Project overview, tech stack, features, architecture
   - Purpose: Provide comprehensive project context

2. **CHANGELOG.md** (Medium Priority)
   - Extract: Last 1000 lines (most recent changes)
   - Contains: Version history, recent updates, bug fixes
   - Purpose: Show current development focus

3. **VERSION** (High Priority)
   - Extract: Entire file (usually 1 line)
   - Contains: Current version number
   - Purpose: Identify project maturity/release status

4. **SRS.md / SYSTEM_REQUIREMENTS_SPECIFICATION.md** (Medium Priority)
   - Extract: First 1000 lines
   - Contains: Core requirements, goals, constraints
   - Purpose: Understand project scope and requirements

5. **CLAUDE.md** (Optional)
   - Extract: Relevant sections only
   - Contains: Project-specific instructions for Claude
   - Purpose: Custom behavioral guidelines

---

## Output Format

**Session Cache File:**
`~/.claude/memory/logs/sessions/{SESSION_ID}/context-cache.json`

```json
{
  "version": "1.0.0",
  "context_read_at": "2026-03-06T10:00:00.123456",
  "project_detected": true,
  "project_name": "claude-insight",
  "version": "4.4.4",
  "files_found": {
    "readme": {
      "exists": true,
      "size_bytes": 15234,
      "excerpt_lines": 500,
      "excerpt": "# Claude Insight v4.4.4\n..."
    },
    "changelog": {
      "exists": true,
      "size_bytes": 34567,
      "excerpt_lines": 1000,
      "excerpt": "## [4.4.4] - 2026-02-25\n..."
    },
    "version": {
      "exists": true,
      "content": "4.4.4"
    },
    "srs": {
      "exists": true,
      "excerpt_lines": 1000,
      "excerpt": "# System Requirements Specification\n..."
    },
    "claude_md": {
      "exists": false
    }
  },
  "metadata": {
    "tech_stack": ["Python", "Flask", "SQLite"],
    "project_type": "Flask Monitoring Dashboard",
    "is_new_project": false
  },
  "passed_to_prompt_generation": {
    "project_name": "claude-insight",
    "project_overview": "Real-time monitoring dashboard...",
    "current_version": "4.4.4",
    "recent_context": "Latest changes include..."
  }
}
```

---

## Error Handling

### Scenario 1: New Project (No Files Found)
```
Input:  Project root with NO README/CHANGELOG/VERSION
Action: SKIP gracefully
Output: "SKIPPED - New project detected, no context files found"
Result: Continue with generic context (no enrichment)
```

### Scenario 2: File Read Error
```
Input:  README.md exists but cannot be read (permission denied)
Action: Log warning, continue with available files
Output: "PARTIAL - Skipped README (permission denied), continued with others"
Result: Proceed with available context
```

### Scenario 3: Large Files
```
Input:  CHANGELOG.md is 50MB (too large to read entirely)
Action: Read LAST N lines only (default: 1000 lines)
Output: "TRUNCATED - Read last 1000 lines of CHANGELOG.md"
Result: Recent context preserved, older context skipped
```

### Scenario 4: Encoding Issues (Windows)
```
Input:  File with mixed UTF-8/cp1252 encoding
Action: Try UTF-8 decode, fallback to cp1252 with errors='replace'
Output: "DECODED - Used fallback encoding for file"
Result: File readable (may have replacement chars, but readable)
```

### Scenario 5: Path Issues
```
Input:  hook_cwd points to subdirectory (not project root)
Action: Check both cwd AND walk up one level to find README
Output: "FOUND - Located context files in parent directory"
Result: Context successfully read from project root
```

---

## Integration Points

### 1. Called by: 3-level-flow.py (Main Hook)
- Executes BEFORE prompt-generator.py
- Receives hook_cwd (current working directory)
- Returns cached context dict
- Logs complete pipeline entry in flow-trace.json

### 2. Used by: prompt-generator.py (Step 3.0)
- Receives cached context as parameter
- Enriches structured prompt with:
  - Project name (from README first line)
  - Project overview (from README excerpt)
  - Current version (from VERSION file)
  - Recent changes (from CHANGELOG excerpt)
  - Tech stack (extracted from README)
- Allows Claude to make better informed decisions

### 3. Logged in: flow-trace.json
- Pipeline entry with complete traceability
- Input: hook_cwd
- Output: cached context, files found
- Decision: what was passed to next step
- Duration: timing metrics

### 4. Cached in: Session Summary
- Location: `~/.claude/memory/logs/sessions/{SESSION_ID}/context-cache.json`
- Reused across multiple requests in same session
- Persisted for session chaining (continuation)
- Expires with session (fresh read on new session)

---

## Success Criteria

- [x] Detects all 5 context file types correctly
- [x] Reads files without blocking/hanging
- [x] Handles missing files gracefully (skip, don't error)
- [x] Handles corrupted/unreadable files (log warning, continue)
- [x] Extracts key metadata (version, project name, tech stack)
- [x] Caches context in session JSON file
- [x] Passes structured dict to prompt generation
- [x] Complete traceability in flow-trace.json with all decisions
- [x] Works on new projects (skips cleanly without errors)
- [x] Windows-safe encoding handling (UTF-8 + cp1252 fallback)
- [x] Performance: reads complete in <1 second
- [x] Backward compatible (no breaking changes to existing steps)

---

## Benefits

1. **Context-Aware Decisions:** Claude understands project scope before starting
2. **Better Task Analysis:** Project requirements visible from SRS/README
3. **Version-Aware:** Current version influences approach (new project vs mature)
4. **Tech Stack Explicit:** Claude knows tech choices before suggesting solutions
5. **Graceful Degradation:** Works on both new and existing projects
6. **Reusable:** Cached for multiple requests (efficiency)
7. **Traceable:** Complete audit trail of what context was read
8. **Safe:** Encoding issues, missing files, permission errors all handled

---

## Execution Timing

- **File Detection:** ~10ms (file exists checks)
- **File Reading:** ~100-200ms (I/O bound)
- **Metadata Extraction:** ~10ms (regex parsing)
- **Session Caching:** ~10ms (JSON write)
- **Total:** <300ms for complete context reading

**Non-blocking:** Timeout set to 5 seconds (more than sufficient)

---

## Version History

| Version | Date       | Changes |
|---------|-----------|---------|
| 1.0.0   | 2026-03-06 | Initial release. Context reading pre-flight policy. |
