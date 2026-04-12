# Task & Phase Enforcement Policy (MANDATORY - BLOCKING)

## Status: 🔴 CRITICAL - ALWAYS ACTIVE

**Version:** 1.0.0
**Last Updated:** 2026-02-16
**Enforcement Level:** BLOCKING (Cannot proceed without compliance)

---

## 🚨 CRITICAL RULE

**I MUST NEVER start work without proper task/phase breakdown when required.**

This is a **BLOCKING REQUIREMENT** - violations prevent execution.

---

## Mandatory Breakdown Requirements

### Task Breakdown (TaskCreate + TaskUpdate)

**ALWAYS REQUIRED — EVERY REQUEST (v2.0.0 policy):**
- Complexity dekho mat — har coding/implementation request pe TaskCreate banana
- Minimum 1 task per request (policy visibility ke liye)
- 5+ tasks ho jayein = phases mein divide karo
- Exception: Pure conversational/informational responses (koi task nahi)

**OLD RULE (REMOVED):** "Non-trivial complexity", ">2 minutes", "3+ steps" — ye sab conditions hata di gayi hain

**Usage:**
```
1. TaskCreate("Description")
   → Creates task, returns task_id

2. TaskUpdate(task_id, status="in_progress")
   → Marks work started

3. [Do the work]

4. TaskUpdate(task_id, status="completed")
   → Triggers auto-commit
```

**Benefits:**
- Progress tracking visible to user
- Auto-commit triggered on completion
- Clear accountability
- Context management

---

### Phase Breakdown (Phased Execution)

**ALWAYS REQUIRED when task score >= 6:**

**Scoring Criteria (0-10):**

| Factor | Score | Description |
|--------|-------|-------------|
| **Requirements** | 0-3 | How many distinct requirements? |
| **Domains** | 0-2 | How many different tech domains? |
| **Effort** | 0-2 | Estimated implementation time |
| **Dependencies** | 0-2 | How many interdependent parts? |
| **Risk** | 0-1 | High risk of errors/loops? |

**Thresholds:**
- **0-2:** Direct execution (no phases)
- **3-5:** Ask user preference
- **6-10:** **MANDATORY phased execution**

**Phase Structure:**
```
Phase 1: [Clear milestone]
  - Step 1
  - Step 2
  - Success criteria
  - Git checkpoint

Phase 2: [Next milestone]
  - Step 1
  - Step 2
  - Success criteria
  - Git checkpoint
```

---

## Enforcement Mechanism

### Pre-Execution Check

**BEFORE starting ANY work, I MUST:**

1. **Analyze Request**
   ```
   → Complexity score (0-10)
   → Size score (0-10)
   → File modifications? (Yes/No)
   ```

2. **Check Requirements (v2.0.0)**
   ```
   ALWAYS:
      → TaskCreate REQUIRED (har request pe — no condition)

   IF size_score >= 6 OR task_count >= 5:
      → Phased execution REQUIRED
   ```

3. **Block if Non-Compliant**
   ```
   IF requirements not met:
      → STOP execution
      → Create tasks/phases first
      → THEN proceed
   ```

### Automated Checks

**Script:** `~/.claude/memory/task-phase-enforcer.py`

**Runs:**
- Before every file modification
- Before multi-step work begins
- When user says "start" or "begin"

**Action:**
- Checks if TaskCreate was called
- Checks if phases are defined (if needed)
- BLOCKS execution if missing
- Returns enforcement error

---

## Examples

### ✅ CORRECT: Task Breakdown

**User:** "Update all infrastructure READMEs"

**My Response:**
```
I'll break this into tasks:

[Creates tasks]
TaskCreate("Update Elasticsearch README")
TaskCreate("Update MongoDB README")
...

[Marks in progress]
TaskUpdate(1, status="in_progress")

[Does work]

[Marks complete]
TaskUpdate(1, status="completed")
→ Auto-commit triggered ✅
```

### ✅ CORRECT: Phase Breakdown

**User:** "Build authentication system"

**My Analysis:**
```
Complexity Score: 8/10
- Requirements: 3 (login, register, JWT)
- Domains: 2 (backend, frontend)
- Effort: 2 (60+ min)
- Dependencies: 1 (backend → frontend)

→ MANDATORY phased execution
```

**My Response:**
```
This requires phased execution:

Phase 1: Backend Auth API
- Create User entity
- Implement JWT service
- Build login/register endpoints
- Write tests
✓ Checkpoint: git commit

Phase 2: Frontend Auth UI
- Login form component
- Register form component
- Auth context/state
- Integration with API
✓ Checkpoint: git commit

Proceed with Phase 1?
```

### ❌ WRONG: No Task Breakdown

**User:** "Update all infrastructure READMEs"

**My Response:**
```
Sure! Let me update them...

[Directly edits files without TaskCreate]
❌ VIOLATION - No task tracking
❌ No auto-commit trigger
❌ No progress visibility
```

### ❌ WRONG: No Phase Breakdown

**User:** "Build authentication system"

**My Response:**
```
I'll implement the auth system...

[Starts coding everything at once]
❌ VIOLATION - Complexity score 8/10 requires phases
❌ High risk of errors/missed requirements
❌ No checkpoints
❌ Wasted tokens if something fails
```

---

## Violation Consequences

### What Happens on Violation

1. **Execution BLOCKED**
   - Work cannot proceed
   - Enforcer returns error
   - User notified

2. **Logged to Policy Violations**
   - Timestamp
   - Task description
   - Violation type
   - Resolution required

3. **Must Remediate**
   - Create tasks if missing
   - Break into phases if needed
   - THEN retry execution

### Violation Types

| Type | Description | Remedy |
|------|-------------|--------|
| **NO_TASK** | File modifications without TaskCreate | Create task first |
| **NO_PHASES** | Score >= 6 without phase breakdown | Define phases first |
| **INCOMPLETE_TASK** | Started work without TaskUpdate(in_progress) | Update status |
| **NO_COMPLETION** | Finished without TaskUpdate(completed) | Mark complete |

---

## Integration with Other Policies

### Git Auto-Commit Policy

- TaskUpdate(completed) → Triggers auto-commit ✅
- Phases → Git checkpoints after each phase ✅
- Task compliance ensures commit compliance ✅

### Context Management

- Tasks help scope context per work unit
- Phases prevent context overflow
- Clear boundaries for cleanup

### Session Memory

- Tasks saved in session state
- Phase progress tracked
- Resume capability between phases

---

## Checklist (Run BEFORE Every Request)

```
□ Is this modifying files?
   YES → TaskCreate REQUIRED

□ Is this multi-step work?
   YES → TaskCreate REQUIRED

□ Complexity score >= 3?
   YES → TaskCreate REQUIRED

□ Size score >= 6?
   YES → Phased execution REQUIRED

□ TaskCreate called?
   NO → BLOCK execution

□ Phases defined (if score >= 6)?
   NO → BLOCK execution

□ All requirements met?
   YES → Proceed with execution ✅
```

---

## Enforcer Script Usage

**Manual Check:**
```bash
python ~/.claude/memory/task-phase-enforcer.py \
  --analyze "Update all infrastructure READMEs"
```

**Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK/PHASE ENFORCEMENT CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Request: Update all infrastructure READMEs

Analysis:
✓ Complexity Score: 5/10
✓ Size Score: 7/10
✓ File Modifications: YES

Requirements:
✓ TaskCreate: REQUIRED
✓ Phased Execution: REQUIRED (score >= 6)

Status: ❌ NOT COMPLIANT
- Missing: TaskCreate
- Missing: Phase breakdown

Action: BLOCK execution
Remedy: Create tasks and define phases first
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Benefits

### For Me (Claude)

- ✅ Clear structure prevents loops
- ✅ Checkpoints enable recovery
- ✅ Better context management
- ✅ Automatic commit triggers
- ✅ Progress tracking

### For User

- ✅ Visibility into progress
- ✅ Clear deliverables per phase
- ✅ Can pause/resume work
- ✅ Reduced risk of incomplete work
- ✅ Automatic backups (commits)

### For System

- ✅ Token optimization (60-70% savings)
- ✅ Reduced error loops
- ✅ Better session management
- ✅ Audit trail of work
- ✅ Policy compliance enforcement

---

## References

- **Core Policy:** `~/.claude/memory/core-skills-mandate.md`
- **Enforcer Script:** `~/.claude/memory/task-phase-enforcer.py`
- **Git Integration:** `~/.claude/memory/git-auto-commit-policy.md`
- **CLAUDE.md:** Execution flow step 6

---

**STATUS:** 🟢 ACTIVE
**ENFORCEMENT:** BLOCKING
**REQUIRED:** ALWAYS

**This policy is NON-NEGOTIABLE and ALWAYS ENFORCED.**
