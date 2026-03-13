# 🧪 WORKFLOW.MD TESTING & SYNC PLAN

**Version:** 1.0.0
**Date:** 2026-03-13
**Status:** PLANNING PHASE
**Owner:** Claude Insight Team

---

## 📋 EXECUTIVE SUMMARY

WORKFLOW.md specification is **95% implemented** but needs:
1. ✅ Global sync verification (files/scripts)
2. ✅ Hook integration testing (all 4 hooks)
3. ✅ Architecture system testing (Level -1 → Level 3)
4. ✅ End-to-end pipeline testing
5. ✅ Bug fixes from testing results

---

## PHASE 1: GLOBAL STATE VERIFICATION (1-2 hours)

### 1.1 Scripts Deployment Status
**Target:** `~/.claude/scripts/`

| Script | Status | Size | Last Modified |
|--------|--------|------|----------------|
| 3-level-flow.py | ✅ DEPLOYED | 9.2K | Mar 10 14:05 |
| pre-tool-enforcer.py | ✅ DEPLOYED | 83K | Mar 10 14:05 |
| post-tool-tracker.py | ✅ DEPLOYED | 80K | Mar 10 14:05 |
| stop-notifier.py | ✅ DEPLOYED | 39K | Mar 10 14:05 |
| Architecture system | ✅ DEPLOYED | N/A | Mar 10+ |

**Actions:**
- [ ] Verify all 4 main hook scripts executable
- [ ] Verify architecture/01-sync-system/ has all 38 files
- [ ] Verify architecture/02-standards-system/ has all 3 files
- [ ] Verify architecture/03-execution-system/ has all 66 files
- [ ] Check for missing imports or syntax errors

**Test Command:**
```bash
python ~/.claude/scripts/3-level-flow.py --help
python ~/.claude/scripts/pre-tool-enforcer.py --validate
python ~/.claude/scripts/post-tool-tracker.py --status
python ~/.claude/scripts/stop-notifier.py --test
```

### 1.2 Memory System Structure
**Target:** `~/.claude/memory/`

| Directory | Purpose | Status |
|-----------|---------|--------|
| logs/ | Session logs & traces | ? |
| sessions/ | Active sessions | ? |
| cache/ | Cached data | ✅ EXISTS |
| current/ | Active enforcement scripts | ? |

**Actions:**
- [ ] Check if `logs/sessions/` writable
- [ ] Check if `sessions/chain-index.json` exists
- [ ] Verify session folder creation permission
- [ ] Check log file structure

### 1.3 CLAUDE.md Sync Status
**Target:** `~/.claude/CLAUDE.md`

**Current:** Exists (2323 bytes, Mar 8 09:51)

**Actions:**
- [ ] Read current content
- [ ] Compare with `claude-insight/CLAUDE.md` (master copy)
- [ ] Sync if outdated
- [ ] Verify 3-level architecture section present

### 1.4 Settings.json Verification
**Target:** `~/.claude/settings.json` (2208 bytes, Mar 13 09:21)

**Current Configuration:**
```json
{
  "model": "haiku",
  "hooks": {
    "UserPromptSubmit": [ ... ]    // 3-level-flow.py
    "PreToolUse": [ ... ]           // pre-tool-enforcer.py
    "PostToolUse": [ ... ]          // post-tool-tracker.py
    "Stop": [ ... ]                 // stop-notifier.py
  }
}
```

**Actions:**
- [ ] Verify all 4 hooks have correct command paths
- [ ] Verify all paths use `C:/Users/techd/.claude/scripts/` (Windows format)
- [ ] Check timeout values (should be reasonable)
- [ ] Verify `async: false` on all hooks (MANDATORY)
- [ ] Check matchers for PreToolUse/PostToolUse

---

## PHASE 2: HOOK INTEGRATION TESTING (2-3 hours)

### 2.1 UserPromptSubmit Hook
**Trigger:** Every message submission

**Expected Flow:**
```
User submits message
  ↓
3-level-flow.py runs (Level -1 → Level 1 → Level 2 → Level 3)
  ├─ Level -1: Auto-fix checks
  ├─ Level 1: Context sync + TOON compression
  ├─ Level 2: Standards loading
  └─ Level 3: Pipeline decision
  ↓
Response proceeds
```

**Test Plan:**
```bash
# Manual test - send a simple message and check:
# 1. Does 3-level-flow.py execute?
# 2. Are there any errors in stderr?
# 3. Does session folder get created in ~/.claude/memory/logs/sessions/?
# 4. Is flow-trace.json written?
# 5. Is context.toon.json compressed?
```

**Expected Output:**
- Session folder: `~/.claude/memory/logs/sessions/session-20260313-XXXXXX/`
- Files: `session.json`, `flow-trace.json`, `context.toon.json`

**Possible Issues:**
- [ ] Path not found (Windows vs Unix paths)
- [ ] Python not executable
- [ ] Missing imports in 3-level-flow.py
- [ ] Permission denied on writing sessions
- [ ] TOON compression library missing

---

### 2.2 PreToolUse Hook
**Trigger:** Before Write, Edit, Read, Grep, Glob, Bash, NotebookEdit

**Expected Flow:**
```
Tool use detected (e.g., Read file)
  ↓
pre-tool-enforcer.py runs
  ├─ Check: File > 500 lines + no offset/limit?
  ├─ Check: Grep content mode + no head_limit?
  ├─ Check: All parameters match policy?
  └─ Decision: ALLOW or BLOCK
  ↓
If ALLOW: Tool executes
If BLOCK: Exit code 2, Claude retries with params
```

**Test Plan:**
```bash
# Test 1: Read large file WITHOUT offset/limit
# Should BLOCK and ask for offset/limit

# Test 2: Read large file WITH offset/limit
# Should ALLOW

# Test 3: Grep with no head_limit
# Should BLOCK if output_mode=content

# Test 4: Simple Read < 500 lines
# Should ALLOW immediately
```

**Possible Issues:**
- [ ] Matcher regex not matching tool names
- [ ] BLOCK logic not working (exit code 2)
- [ ] File size detection broken
- [ ] Line count calculation wrong
- [ ] Tool parameters not passed correctly

---

### 2.3 PostToolUse Hook
**Trigger:** After Write, Edit, Bash, TaskCreate, etc.

**Expected Flow:**
```
Tool completed
  ↓
post-tool-tracker.py runs
  ├─ Track: Which tool was used
  ├─ Track: What file was modified
  ├─ Update: GitHub workflow (if code changed)
  ├─ Update: Progress tracking
  └─ Check: Task completion status
  ↓
Continue with next step
```

**Test Plan:**
```bash
# Test 1: Write new file
# Check: Is file tracked in progress?

# Test 2: Edit existing file
# Check: Is GitHub issue updated?

# Test 3: Bash command execution
# Check: Is command logged?

# Test 4: TaskCreate
# Check: Is task visible in task list?
```

**Possible Issues:**
- [ ] GitHub API not authenticated
- [ ] Progress tracker not initialized
- [ ] File path tracking broken
- [ ] Matcher not matching second set of tools

---

### 2.4 Stop Hook
**Trigger:** After response sent to user

**Expected Flow:**
```
Response complete
  ↓
stop-notifier.py runs
  ├─ Save: session state
  ├─ Log: session summary
  └─ Notify: user with voice (Windows MessageBox)
  ↓
Session ready for next message
```

**Test Plan:**
```bash
# Test 1: Send message and complete response
# Check: Does Windows MessageBox show?

# Test 2: Check ~/.claude/memory/logs/sessions/
# Check: Is session-summary.json written?

# Test 3: Check session.json updated
# Check: Is timestamp updated?
```

**Possible Issues:**
- [ ] Voice notification not working (Windows issue)
- [ ] Session not saved before notification
- [ ] Summary generation broken
- [ ] No feedback to user

---

## PHASE 3: ARCHITECTURE SYSTEM TESTING (3-4 hours)

### 3.1 Level -1: Auto-Fix Enforcement
**Location:** `~/.claude/scripts/architecture/` (not yet in flow)

**Expected Behavior:**
```
Message arrives
  ↓
Check 1: Unicode encoding (UTF-8 on Windows)
Check 2: ASCII-only Python files
Check 3: Path format (forward slashes)
  ↓
All pass? → Continue to Level 1
Any fail? → Ask user: "Auto-fix or Skip?"
  ├─ Auto-fix: Attempt up to 3 times, then continue
  └─ Skip: Continue anyway (risky)
```

**Test Plan:**
```bash
# Create a test scenario with encoding issues:
# 1. File with UTF-8 BOM
# 2. File with backslashes in path
# 3. Non-ASCII Python file

# Then trigger 3-level-flow.py
# Should detect and offer to fix
```

**Possible Issues:**
- [ ] Level -1 checks not integrated into main flow
- [ ] Default choice not set to "auto-fix"
- [ ] Retry mechanism not working
- [ ] Cleanup between retries not working

---

### 3.2 Level 1: Context Sync
**Location:** `~/.claude/scripts/architecture/01-sync-system/`

**Expected Behavior:**
```
Level -1 passed
  ↓
Step 1: Create session folder
Step 2: Load context (parallel)
  ├─ Complexity calculation
  └─ File reading (SRS, README, CLAUDE.md)
Step 3: TOON compression
Step 4: Memory cleanup
  ↓
Only TOON object passed to Level 3
```

**Test Plan:**
```bash
# Test 1: Session creation
# Check: Is ~/.claude/memory/logs/sessions/session-XXXX created?

# Test 2: Context loading
# Check: Do all 3 context files load without error?

# Test 3: TOON compression
# Check: Is context.toon.json < original size by 10x?

# Test 4: Memory cleanup
# Check: Are large variables deleted from flow_state?
```

**Possible Issues:**
- [ ] Session folder not created
- [ ] File permissions prevent reading context
- [ ] TOON library import missing
- [ ] Compression not reducing size
- [ ] Memory not freed after cleanup

---

### 3.3 Level 2: Standards System
**Location:** `~/.claude/rules/`

**Expected Behavior:**
```
Level 1 passed
  ↓
Load standards into Claude's rules folder:
  ├─ project-standards.md
  ├─ tool-optimization rules (NEW)
  ├─ coding conventions
  └─ best practices
  ↓
Standards auto-enforced during execution
```

**Test Plan:**
```bash
# Test 1: Check if rules folder populated
# ls ~/.claude/rules/

# Test 2: Check if tool-optimization rules present
# grep -r "read_max_lines" ~/.claude/rules/

# Test 3: Verify Claude can access rules
# (Check in actual task execution)

# Test 4: Verify pre-tool-enforcer applies rules
# (Test Read with large file - should be blocked)
```

**Possible Issues:**
- [ ] Rules not loaded at startup
- [ ] Pre-tool enforcer not checking rules
- [ ] Tool optimization rules not in place
- [ ] Standards not being applied

---

### 3.4 Level 3: 14-Step Execution Pipeline
**Location:** `~/.claude/scripts/architecture/03-execution-system/`

**Expected Behavior:**
```
Level 2 passed
  ↓
Step 1: Plan decision (Ollama or Claude API)
  ↓
IF plan_required:
  Step 2: Generate plan (exploration + analysis)
  → Step 3: Task breakdown
ELSE:
  → Step 3: Task breakdown (from user_requirement)
  ↓
Step 4: TOON refinement
Step 5: Skill selection
Step 6: Skill validation + download
Step 7: Final prompt generation
Step 8: GitHub issue creation
Step 9: Branch creation
Step 10: Implementation
Step 11: PR & code review (with retry)
Step 12: Issue closure
Step 13: Documentation update
Step 14: Final summary
```

**Test Plan:**
```bash
# Test 1: Start simple task (no plan needed)
# Should skip Step 2, go directly to Step 3

# Test 2: Start complex task (plan needed)
# Should execute Step 2 (Ollama or Claude API)

# Test 3: Verify all 14 step functions exist
find ~/.claude/scripts/architecture/03-execution-system -name "step*.py"

# Test 4: Test skill selection works
# (Check if skills are downloaded)

# Test 5: Test GitHub workflow integration
# (Check if issues/PRs created)

# Test 6: Test retry loop in Step 11
# (Simulate code review failure, verify retry)
```

**Possible Issues:**
- [ ] Ollama server not running (need fallback to Claude API)
- [ ] Step functions not executable
- [ ] Conditional routing not working
- [ ] GitHub integration broken
- [ ] Skill download failing
- [ ] Retry loop not working
- [ ] Documentation generation broken

---

## PHASE 4: BUG FIXES & INTEGRATION (2-3 hours)

### 4.1 Common Issues to Check

**Issue #1: Windows Path Problems**
```
Expected: ~/.claude/scripts/3-level-flow.py
Actual:   C:\Users\techd\.claude\scripts\3-level-flow.py

Fix: Always convert to forward slashes in settings.json
Check: python path_resolver.py is working
```

**Issue #2: Python Executable Path**
```
settings.json has: python.exe C:/Users/techd/.claude/scripts/...
But should be: python C:/Users/techd/.claude/scripts/...

Fix: settings.json should use just 'python' not 'python.exe'
```

**Issue #3: Missing Dependencies**
```
Each hook script might be missing:
- import json
- import os
- import subprocess
- import sys

Fix: Run syntax check on all scripts
```

**Issue #4: Ollama Server Missing**
```
Step 1 tries to connect to Ollama (localhost:11434)
If missing: Should fallback to Claude API

Fix: Add Claude API fallback in step1_node
```

**Issue #5: GitHub Authentication**
```
PostToolUse hook needs GitHub token
If missing: PRs/Issues creation will fail

Fix: Check ~/.claude/.credentials.json has github_token
```

---

## PHASE 5: END-TO-END INTEGRATION TEST (4-5 hours)

### 5.1 Complete Workflow Test

**Scenario:** Fix a small bug in claude-insight

**Steps:**
```
1. Send message: "Add a debug endpoint to app.py"
   ↓
2. Monitor:
   - Does UserPromptSubmit hook run?
   - Is session created?
   - Is flow-trace.json written?
   ↓
3. Verify Level -1:
   - Are all 3 checks passed?
   ↓
4. Verify Level 1:
   - Is TOON compressed?
   - Is memory cleaned?
   ↓
5. Verify Level 3:
   - Does Step 1 decide plan needed?
   - Does Step 2 generate plan?
   - Do Steps 3-7 execute?
   - Is GitHub issue created?
   - Is branch created?
   ↓
6. Monitor implementation:
   - Does Step 10 execute without errors?
   - Are files modified correctly?
   ↓
7. Monitor PR:
   - Is PR created in GitHub?
   - Does code review run?
   - Is PR merged?
   ↓
8. Verify closure:
   - Is issue closed?
   - Is documentation updated?
   ↓
9. Verify stop hook:
   - Is session saved?
   - Is summary generated?
   - Is user notified?
```

**Success Criteria:**
- ✅ Session created and tracked
- ✅ All 14 steps execute without error
- ✅ GitHub issue created with correct label
- ✅ Branch created and pushed
- ✅ Code implemented without syntax errors
- ✅ PR created and merged
- ✅ Issue closed with summary
- ✅ Documentation updated
- ✅ User receives notification
- ✅ Session saved in ~/.claude/memory/logs/sessions/

---

## IMPLEMENTATION CHECKLIST

### Pre-Test Checklist
- [ ] All 4 main hook scripts deployed
- [ ] Architecture system complete (107 files)
- [ ] settings.json has correct syntax
- [ ] Memory system writable
- [ ] CLAUDE.md synced globally
- [ ] GitHub credentials in ~/.claude/.credentials.json
- [ ] Ollama server running (or Claude API available)

### Phase 1: Global Sync (1-2 hours)
- [ ] Verify script deployment
- [ ] Verify memory system
- [ ] Sync CLAUDE.md
- [ ] Fix settings.json issues
- [ ] Fix path issues (Windows)

### Phase 2: Hook Testing (2-3 hours)
- [ ] Test UserPromptSubmit hook
- [ ] Test PreToolUse hook
- [ ] Test PostToolUse hook
- [ ] Test Stop hook
- [ ] Fix any hook errors

### Phase 3: Architecture Testing (3-4 hours)
- [ ] Test Level -1 (auto-fix)
- [ ] Test Level 1 (context sync)
- [ ] Test Level 2 (standards)
- [ ] Test Level 3 (14-step pipeline)
- [ ] Fix any architecture errors

### Phase 4: Bug Fixes (2-3 hours)
- [ ] Fix Windows path issues
- [ ] Fix Python executable path
- [ ] Check missing imports
- [ ] Add Ollama → Claude API fallback
- [ ] Verify GitHub authentication

### Phase 5: End-to-End Test (4-5 hours)
- [ ] Run complete workflow
- [ ] Monitor all 5 levels
- [ ] Verify all 14 steps
- [ ] Check GitHub integration
- [ ] Verify session tracking
- [ ] Test notification system

---

## ESTIMATED TIMELINE

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 1: Global Sync | 1-2 hours | NOT STARTED |
| Phase 2: Hook Testing | 2-3 hours | NOT STARTED |
| Phase 3: Architecture Testing | 3-4 hours | NOT STARTED |
| Phase 4: Bug Fixes | 2-3 hours | NOT STARTED |
| Phase 5: End-to-End Test | 4-5 hours | NOT STARTED |
| **TOTAL** | **12-17 hours** | **NOT STARTED** |

---

## DELIVERABLES

After completion:

1. ✅ **TEST RESULTS REPORT** - All test results documented
2. ✅ **BUG FIX LOG** - All bugs found and fixed
3. ✅ **FIXES COMMITTED** - All changes committed to GitHub
4. ✅ **READINESS REPORT** - Workflow.md readiness: 0% → 100%
5. ✅ **DEPLOYMENT GUIDE** - Step-by-step deployment instructions

---

**Status:** READY TO START
**Next Step:** Execute Phase 1: Global Sync Verification

---
