# 🚀 Implementation Phases: 95 Gaps → Actionable Tasks

**Status:** Ready for Parallel Execution
**Total Effort:** 85-110 hours
**Parallel Execution:** YES (Multiple agents)

---

## PHASE 1: CRITICAL PATH (40-50 hours)
**Priority:** IMMEDIATE | **Impact:** 🔴→🟡

### SUBTASK GROUP 1.1: LEVEL -1 ERROR INFRASTRUCTURE (8 hours)

#### Task 1.1.1: Error Logging System
- **What:** Add comprehensive error logging
- **Files:** `level_minus1.py`, new file `error_logger.py`
- **Subtasks:**
  - Create `ErrorLogger` class with timestamp + severity
  - Add error log file: `~/.claude/logs/sessions/{sid}/errors.log`
  - Log each check result (PASS/FAIL with reason)
  - Log each retry attempt (attempt #, timestamp, result)

#### Task 1.1.2: Exit Strategy After Max Retries
- **What:** Define explicit failure behavior
- **Files:** `level_minus1.py`
- **Subtasks:**
  - Add `FATAL_FAILURE` state
  - After 3 retries, ask user: "Auto-fix failed. Options: [Debug manually] [Skip and continue] [Exit]"
  - Save error report before exit
  - Preserve original user prompt for recovery

#### Task 1.1.3: Fix Validation (Before/After)
- **What:** Verify fixes actually worked
- **Files:** `level_minus1.py`
- **Subtasks:**
  - Before applying fix: `backup_file()`
  - Apply fix
  - After applying fix: `verify_fix()` - check file is still valid
  - On failure: `restore_from_backup()` + log error
  - Compare before/after: save diff to `{sid}/unicode-fix.diff`

#### Task 1.1.4: Fix Dependency Ordering
- **What:** Ensure Unicode fix runs before encoding
- **Files:** `level_minus1.py`
- **Subtasks:**
  - Define dependency: `unicode → encoding → paths`
  - Add `depends_on` field to checks
  - Validate dependency graph (no cycles)
  - Execute in dependency order

#### Task 1.1.5: Backup & Rollback
- **What:** Safe recovery mechanism
- **Files:** `level_minus1.py`, new file `backup_manager.py`
- **Subtasks:**
  - Before Level -1: `backup_session_files()`
  - Store in: `~/.claude/logs/sessions/{sid}/backup/`
  - On FATAL_FAILURE: `restore_from_backup()`
  - Add `git stash` as additional safety

---

### SUBTASK GROUP 1.2: LEVEL 1 FOUNDATIONS (10 hours)

#### Task 1.2.1: TOON Schema Definition
- **What:** Define strict TypedDict for TOON
- **Files:** `flow_state.py`
- **Subtasks:**
  - Define `TOONSchema(TypedDict)` with all fields
  - Add version field: `"1.0.0"`
  - Add validation: `validate_toon_schema()`
  - Document each field: purpose, type, constraints

#### Task 1.2.2: Complexity Score Calculation Rules
- **What:** Define how complexity is calculated
- **Files:** new file `complexity_calculator.py`
- **Subtasks:**
  - Define scoring matrix:
    ```
    1-3: Single file, <500 LOC, <2 files, <3 deps
    4-7: Multi-file, 500-5000 LOC, 2-10 files, 3-10 deps
    8-10: Major refactor, >5000 LOC, >10 files, >10 deps
    ```
  - Implement: `calculate_complexity_score(project_path)`
  - Add metrics: files, lines, dependencies, architecture_depth
  - Document thresholds clearly

#### Task 1.2.3: Context Loading Timeout
- **What:** Prevent hanging on large projects
- **Files:** `node_context_loader.py`
- **Subtasks:**
  - Add parameters:
    - `timeout_per_file = 30` seconds
    - `timeout_total = 120` seconds
  - Implement timeout checks
  - On timeout: use partial context (whatever loaded)
  - Log warning: "Context loading timed out after 120s"

#### Task 1.2.4: TOON Compression Validation
- **What:** Verify compression didn't lose data
- **Files:** `node_toon_compression.py`
- **Subtasks:**
  - After compress: `toon = compress(context)`
  - Decompress: `decompressed = decompress(toon)`
  - Verify: `assert data_integrity_check(decompressed, original)`
  - If fails: log error + use raw context (fallback)

#### Task 1.2.5: Memory Limits
- **What:** Prevent OOM on huge projects
- **Files:** `node_context_loader.py`
- **Subtasks:**
  - Constants:
    ```
    MAX_FILE_SIZE = 1_000_000  # 1MB
    MAX_TOTAL_SIZE = 10_000_000  # 10MB
    ```
  - Per-file check: skip if > MAX_FILE_SIZE
  - Total check: stop if > MAX_TOTAL_SIZE
  - Log skipped files: which ones + why

#### Task 1.2.6: Context Deduplication
- **What:** Remove redundant information
- **Files:** new file `context_deduplicator.py`
- **Subtasks:**
  - Algorithm: Find duplicates across SRS/README/CLAUDE.md
  - Merge duplicates: keep unique info only
  - Size comparison: use dedup if saves > 20%
  - Log: which parts deduplicated

#### Task 1.2.7: Partial Context Fallback
- **What:** Graceful degradation if file fails
- **Files:** `node_context_loader.py`
- **Subtasks:**
  - Try loading each file separately
  - On error: skip file + log warning
  - Continue with what loaded
  - Track loaded files in TOON: `"files_loaded": ["SRS", "CLAUDE.md"]`

#### Task 1.2.8: Caching Strategy
- **What:** Reuse context for same project
- **Files:** new file `context_cache.py`
- **Subtasks:**
  - Cache location: `~/.claude/logs/cache/`
  - Cache key: hash of project path
  - Validity rules: expires after 24h OR if files modified
  - Use cache if: path same + files unchanged + <24h old
  - Log cache hits/misses

---

### SUBTASK GROUP 1.3: LEVEL 2 INTEGRATION (8 hours)

#### Task 1.3.1: Standards Integration Points
- **What:** Define where standards apply
- **Files:** `orchestrator.py`, new file `standards_integration.py`
- **Subtasks:**
  - Map standards to steps:
    - Step 1: Load standards for complexity assessment
    - Step 2: Ensure plan follows project standards
    - Step 5: Validate skill selection
    - Step 10: Code review checks compliance
    - Step 13: Documentation matches standards
  - Create integration hooks
  - Document each hook purpose

#### Task 1.3.2: Standard Selection Criteria
- **What:** Choose correct standards per project
- **Files:** new file `standard_selector.py`
- **Subtasks:**
  - Detect: project_type (Python/Java/JS/etc)
  - Detect: framework (Django/Spring/React/etc)
  - Load: custom standards from project
  - Load: team standards from ~/.claude/
  - Merge: apply priority order
  - Return: selected standards list

#### Task 1.3.3: Standards Schema
- **What:** Define valid standard file format
- **Files:** new file `standards_schema.py`
- **Subtasks:**
  - Define YAML schema:
    ```
    version: "1.0.0"
    project_type: "python"
    framework: "flask"
    enforced: true
    rules: [...]
    ```
  - Validation: `validate_standard_file()`
  - Version compatibility: handle deprecations
  - Document schema

#### Task 1.3.4: Conflict Resolution
- **What:** Handle conflicting standards
- **Files:** `standard_selector.py`
- **Subtasks:**
  - Detect conflicts: Python vs Framework
  - Priority order:
    1. Custom standards (highest)
    2. Project standards
    3. Framework standards
    4. Language standards (lowest)
  - Apply higher priority
  - Log conflicts + resolution

---

### SUBTASK GROUP 1.4: LEVEL 3 DECISION CRITERIA (12 hours)

#### Task 1.4.1: Plan Mode Decision Rules
- **What:** Define when planning is required
- **Files:** `level3_step1.py`
- **Subtasks:**
  - Threshold: complexity ≥ 6
  - Always plan: refactoring, architecture changes
  - Bug fixes: always plan if complexity ≥ 4
  - Document rules clearly
  - Add LLM fallback: if local LLM fails → Claude API

#### Task 1.4.2: Plan Convergence Criteria
- **What:** When is plan "done"?
- **Files:** `level3_step2.py`
- **Subtasks:**
  - Define quality threshold: 0.85 (85% complete)
  - Max iterations: 3
  - Stopping condition: quality ≥ threshold OR iterations ≥ max
  - If still not done: use best plan so far + log warning

#### Task 1.4.3: Task Breakdown Validation
- **What:** Verify tasks are valid
- **Files:** new file `task_validator.py`
- **Subtasks:**
  - Cycle detection: check for circular dependencies
  - Completeness: all requirements covered?
  - Reachability: can all tasks be executed?
  - Feasibility: are tasks actually possible?
  - Return: validation errors or OK

#### Task 1.4.4: Skill Selection Criteria
- **What:** How to choose correct skills
- **Files:** `level3_step5.py`
- **Subtasks:**
  - Capability matrix: skill → capabilities
  - Conflict detection: incompatible skills?
  - Coverage assessment: does skill cover task?
  - Confidence scoring: how sure?
  - Alternatives: why not other skills?

#### Task 1.4.5: Step Input/Output Validation
- **What:** Validate at each step
- **Files:** new file `step_validator.py`
- **Subtasks:**
  - Step 1 output: valid plan decision?
  - Step 2 output: valid plan?
  - Step 3 output: valid task breakdown?
  - Step 5 output: valid skill selection?
  - Step 7 output: valid prompt?
  - Create validators for each

#### Task 1.4.6: Token Budget Enforcement
- **What:** Never exceed token limits
- **Files:** new file `token_manager.py`
- **Subtasks:**
  - Total budget: 10,000 tokens
  - Allocate: Step 2 (planning) 30% = 3,000
  - Allocate: Step 7 (prompt) 40% = 4,000
  - Allocate: Reserve 30% = 3,000
  - Track: actual usage per step
  - Enforce: block if exceeds limit

---

### SUBTASK GROUP 1.5: GLOBAL ERROR HANDLING (8 hours)

#### Task 1.5.1: Try/Catch Pattern
- **What:** Add error handling everywhere
- **Files:** All level3 step files
- **Subtasks:**
  - Pattern: Try → Do → Except → Fallback
  - LLM errors: fallback to Claude API
  - Network errors: retry + cache
  - File errors: skip + continue
  - API errors: save locally + ask user
  - Document each error type + recovery

#### Task 1.5.2: Checkpointing System
- **What:** Save state after each step
- **Files:** new file `checkpoint_manager.py`
- **Subtasks:**
  - After Step N: `save_checkpoint(step_n_state)`
  - Location: `~/.claude/logs/sessions/{sid}/checkpoints/step-{n}.json`
  - Fields: step number, completed steps, TOON, git state, timestamp
  - On interrupt: can resume from last checkpoint
  - Resume: `resume_from_checkpoint(checkpoint_file)`

#### Task 1.5.3: Recovery Mechanism
- **What:** Resume on interruption
- **Files:** `orchestrator.py`, `checkpoint_manager.py`
- **Subtasks:**
  - Signal handler: `SIGINT → save checkpoint`
  - Recovery command: `resume_insight {session_id}`
  - Load checkpoint: restore TOON, git state, completed steps
  - Skip completed steps: jump to next incomplete
  - Resume execution from there

#### Task 1.5.4: Metrics Collection
- **What:** Track execution metrics
- **Files:** new file `metrics_collector.py`
- **Subtasks:**
  - Per-step: execution_time, tokens_used, files_modified
  - Global: total_time, success/failure, errors
  - Save to: `~/.claude/logs/sessions/{sid}/metrics.json`
  - Log: step transitions, decisions, errors
  - Aggregation: metrics for analysis

---

## PHASE 2: HIGH PRIORITY (25-30 hours)
**Priority:** HIGH | **Impact:** 🟠→🟢

### SUBTASK GROUP 2.1: LEVEL 1 OPTIMIZATION (6 hours)

#### Task 2.1.1: Context Caching Implementation
- **What:** Cache context for repeated projects
- **Time:** 3 hours
- **Location:** `context_cache.py`

#### Task 2.1.2: Timeout Handling
- **What:** Graceful timeout recovery
- **Time:** 2 hours
- **Location:** `node_context_loader.py`

#### Task 2.1.3: Memory Pressure Management
- **What:** Handle memory constraints
- **Time:** 1 hour
- **Location:** `node_context_loader.py`

---

### SUBTASK GROUP 2.2: LEVEL 3 ROBUSTNESS (12 hours)

#### Task 2.2.1: Timeouts for All Steps
- **What:** Prevent hanging
- **Time:** 4 hours
- **Subtasks:**
  - Step 1 timeout: 30s
  - Step 2 timeout: 120s (planning can take time)
  - Step 5 timeout: 60s
  - Step 7 timeout: 30s
  - Log timeout + fallback

#### Task 2.2.2: Conflict Resolution
- **What:** Handle edge cases
- **Time:** 5 hours
- **Subtasks:**
  - Skill conflicts: choose by priority
  - Standard conflicts: apply hierarchy
  - Branch conflicts: merge or manual
  - API conflicts: retry + fallback

#### Task 2.2.3: Review Criteria Definition
- **What:** Define PR review rules
- **Time:** 3 hours
- **Location:** `level3_step11.py`
- **Subtasks:**
  - Code quality: required, blockers
  - Test coverage: ≥80%, required
  - Documentation: required, blockers
  - Standards compliance: required

---

### SUBTASK GROUP 2.3: SKILL MANAGEMENT (7 hours)

#### Task 2.3.1: Download Failure Handling
- **What:** Resilient skill downloads
- **Time:** 3 hours
- **Subtasks:**
  - Retry logic: exponential backoff
  - Max retries: 3
  - Fallback: use cached version
  - Log: download success/failure

#### Task 2.3.2: Skill Dependencies
- **What:** Handle skill dependencies
- **Time:** 2 hours
- **Subtasks:**
  - Parse skill metadata: dependencies field
  - Recursive download: get all deps
  - Conflict detection: incompatible deps?
  - Validation: all deps available

#### Task 2.3.3: Skill Versioning
- **What:** Version management
- **Time:** 2 hours
- **Subtasks:**
  - Version field: in skill metadata
  - Compatibility check: Python version?
  - Version pinning: use specific version
  - Deprecation: handle old versions

---

## PHASE 3: POLISH (20-25 hours)
**Priority:** MEDIUM | **Impact:** 🟡→⭐

### SUBTASK GROUP 3.1: TESTING (8 hours)

#### Task 3.1.1: Integration Tests
- **Time:** 4 hours
- **Coverage:** All 14 steps
- **Location:** `tests/integration/`

#### Task 3.1.2: Failure Scenarios
- **Time:** 4 hours
- **Scenarios:**
  - Network failure recovery
  - LLM failure fallback
  - Timeout handling
  - File system errors
  - API errors

---

### SUBTASK GROUP 3.2: PERFORMANCE (8 hours)

#### Task 3.2.1: Parallelization
- **Time:** 4 hours
- **Opportunities:**
  - Step 2: parallel exploration
  - Step 10: parallel task execution
  - Skill downloads: parallel

#### Task 3.2.2: Caching Strategies
- **Time:** 4 hours
- **Add caching for:**
  - LLM responses
  - File analysis results
  - Skill definitions

---

### SUBTASK GROUP 3.3: UX (9 hours)

#### Task 3.3.1: Progress Visibility
- **Time:** 3 hours
- **Add:**
  - Progress bars
  - Step status
  - ETA calculation

#### Task 3.3.2: Decision Explanation
- **Time:** 3 hours
- **Explain:**
  - Why plan required?
  - Why this skill?
  - Why this approach?

#### Task 3.3.3: Error Messages
- **Time:** 3 hours
- **Add:**
  - User-friendly messages
  - Actionable recommendations
  - Troubleshooting links

---

## EXECUTION MATRIX

```
PHASE 1 GROUPS:
├─ 1.1 ERROR INFRASTRUCTURE (8h) → python-backend-engineer
├─ 1.2 LEVEL 1 FOUNDATIONS (10h) → python-backend-engineer
├─ 1.3 LEVEL 2 INTEGRATION (8h) → python-backend-engineer
├─ 1.4 LEVEL 3 DECISION CRITERIA (12h) → python-backend-engineer
└─ 1.5 GLOBAL ERROR HANDLING (8h) → python-backend-engineer

PHASE 2 GROUPS:
├─ 2.1 LEVEL 1 OPTIMIZATION (6h) → python-backend-engineer
├─ 2.2 LEVEL 3 ROBUSTNESS (12h) → python-backend-engineer
└─ 2.3 SKILL MANAGEMENT (7h) → python-backend-engineer

PHASE 3 GROUPS:
├─ 3.1 TESTING (8h) → qa-testing-agent
├─ 3.2 PERFORMANCE (8h) → python-backend-engineer
└─ 3.3 UX (9h) → python-backend-engineer

TOTAL: 95 hours (46 subtasks)
PARALLEL: 2-3 agents simultaneously
```

---

## READY FOR IMPLEMENTATION?

Each subtask is:
- ✅ Clearly defined
- ✅ Has specific files to modify
- ✅ Has clear acceptance criteria
- ✅ Estimated effort/time
- ✅ Can be parallelized

**Next Step:** Create task entries + launch agents

