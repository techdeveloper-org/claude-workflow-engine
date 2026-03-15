# Computer Use Testing - Pre-Flight Checklist

## ⚠️ CRITICAL DEPENDENCIES

Computer Use E2E testing will **ONLY WORK** if these prerequisites are met:

---

## 1. POLICY EXECUTION ✅

### Required: All 25 policies must execute successfully

```
Level -1 (Auto-Fix):           7 checks → All PASSED
Level 1 (Sync):                6 steps → All PASSED
Level 2 (Standards):           2 checks → All PASSED
Level 3 (Execution 12 steps):  12 steps → All PASSED
─────────────────────────────────────────────────
TOTAL:                         25 policies PASSED
```

**Verification:**
```bash
cd "$(git rev-parse --show-toplevel)"  # auto-detect project root
python scripts/3-level-flow.py --summary

# Expected output:
# [OK] ALL 3 LEVELS VERIFIED - AUTO-PROCEED TO WORK
# No FAILED policies
```

---

## 2. OUTPUT FILES SAVED CORRECTLY ✅

### Required: All policy outputs must be persisted to correct locations

#### A. Session Flow Trace
```
Location: ~/.claude/memory/logs/sessions/{SESSION_ID}/flow-trace.json
Required: Must contain complete pipeline with all 25 steps
Check:    jq '.pipeline | length' flow-trace.json → Should be 25
```

#### B. Policy Hit Log
```
Location: ~/.claude/memory/logs/policy-hits.log
Required: Record of all policy executions
Check:    tail -50 policy-hits.log → Should show recent policy hits
```

#### C. Session Progress
```
Location: ~/.claude/memory/logs/session-progress.json
Required: Task counts, tool usage, completion tracking
Check:    jq '.tasks_completed' session-progress.json → Should match actual tasks
```

#### D. Task Breakdown Flag
```
Location: ~/.claude/memory/logs/sessions/{SESSION_ID}/flags/task-breakdown-pending.json
Required: Flag indicates task enforcement active
Check:    test -f flags/task-breakdown-pending.json → Should exist when needed
```

#### E. Work Summary
```
Location: ~/.claude/memory/logs/sessions/{SESSION_ID}/work-summary.json
Required: Summary of completed work
Check:    jq '.completion_percentage' work-summary.json → Should show >=95%
```

---

## 3. DASHBOARD DATA LOADING ✅

### Required: Flask dashboard must correctly read and display all data

#### A. Dashboard Startup
```bash
cd "$(git rev-parse --show-toplevel)"  # auto-detect project root
python run.py

# Expected:
# * Running on http://localhost:5000
# * No errors in Flask logs
# * Database initialization successful
```

#### B. Session Data Display
```
URL: http://localhost:5000/sessions
Expected:
  - List of all sessions
  - Each session shows: SESSION_ID, timestamp, context%, task count
  - Flow trace available for click-through
```

#### C. Flow History Display
```
URL: http://localhost:5000/3level-flow-history
Expected:
  - Timeline of all 3-level flow executions
  - All 25 policies listed with status
  - No missing steps or data gaps
```

#### D. Task Progress Display
```
URL: http://localhost:5000/tasks
Expected:
  - All created tasks listed
  - Status: pending → in_progress → completed
  - Completion timestamps accurate
```

#### E. Policy Enforcement Display
```
URL: http://localhost:5000/policies
Expected:
  - All 32 policies listed
  - Execution counts accurate
  - Hit frequency matches logs
```

---

## 4. DATA FLOW INTEGRITY ✅

### Verify end-to-end data flow:

```
User Input (prompt)
    ↓
3-level-flow.py executes
    ↓
Each policy produces output (JSON, logs)
    ↓
Output saved to ~/.claude/memory/logs/
    ↓
Dashboard queries logs directory
    ↓
Dashboard renders in Flask templates
    ↓
UI displays all data correctly
```

**Verification Command:**
```bash
# Check if all required directories exist and have data
test -d ~/.claude/memory/logs/sessions && echo "✓ Sessions dir"
test -f ~/.claude/memory/logs/policy-hits.log && echo "✓ Policy log"
ls -la ~/.claude/memory/logs/sessions/*/flow-trace.json | wc -l → Should be >0

# Check if dashboard can read this data
curl -s http://localhost:5000/api/sessions | jq '.total_sessions' → Should be >0
```

---

## 5. PRE-FLIGHT CHECKLIST

Before running Computer Use tests, verify ALL:

```
[  ] 1. All 25 policies execute and show PASSED status
[  ] 2. flow-trace.json created in session directory
[  ] 3. policy-hits.log has recent entries
[  ] 4. session-progress.json exists and has task counts
[  ] 5. task-breakdown flags created/cleared correctly
[  ] 6. work-summary.json generated after task completion
[  ] 7. Flask dashboard starts without errors
[  ] 8. Dashboard /sessions endpoint returns session list
[  ] 9. Dashboard /3level-flow-history shows all 25 steps
[  ] 10. Dashboard /tasks shows all created tasks
[  ] 11. Dashboard /policies shows policy execution counts
[  ] 12. All data is fresh (timestamps match current time)
```

---

## 6. IF ANY CHECK FAILS

**DO NOT RUN COMPUTER USE TESTS**

Instead, investigate:

### Policy Failed?
```bash
python scripts/3-level-flow.py --summary --verbose
# Look for which step/policy failed
# Check logs for error messages
```

### Output Files Missing?
```bash
find ~/.claude/memory/logs -type f -mmin -5 | head -20
# Verify files were created in last 5 minutes
```

### Dashboard Not Loading?
```bash
python run.py
# Check Flask error output
# Verify database: test -f instance/claude_insight.db
```

### Data Not Displaying?
```bash
curl -s http://localhost:5000/api/sessions | jq . | less
# Check if API returns valid JSON
# Verify database query results
```

---

## 7. ONCE ALL CHECKS PASS ✅

Only then run Computer Use tests:

```bash
python scripts/agents/computer-use-agent.py --run-tests \
  --dashboard-url http://localhost:5000 \
  --username admin \
  --password admin
```

---

## SUMMARY

**Computer Use testing depends on this chain:**

| Step | Component | Status |
|------|-----------|--------|
| 1 | Policies execute | Must be ✅ PASSED |
| 2 | Output saved | Must be ✅ FILES EXIST |
| 3 | Dashboard reads | Must be ✅ DATA LOADED |
| 4 | UI displays | Must be ✅ VISIBLE |
| 5 | Computer Use verifies | Can now ✅ RUN |

**If ANY step fails → Testing will fail**

So verify the ENTIRE pipeline first! 🔗
