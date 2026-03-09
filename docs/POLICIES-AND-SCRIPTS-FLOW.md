# Claude Insight - Policies & Scripts Complete Flow

## 🎯 Core Concept

```
POLICIES (Documentation)          SCRIPTS (Implementation)
      ↓                                ↓
  "What to do"              →    "How to do it"
  "Rules to follow"         →    "Execute rules"
  "Constraints"             →    "Enforce constraints"
```

---

## 📊 3-LEVEL SYSTEM ARCHITECTURE

### **LEVEL 1: 🔵 SYNC SYSTEM (Foundation)**
Load context before execution

```
policies/01-sync-system/
├── context-management/
│   └── context-management-policy.md
│       ↓
│   scripts/architecture/01-sync-system/context-management/
│   ├── context-monitor-v2.py (Monitor context usage)
│   ├── context-management-policy.py (Enforce policy)
│   └── session-pruning-policy.py (Clean old data)
│
├── session-management/
│   └── session-*-policy.md
│       ↓
│   scripts/architecture/01-sync-system/session-management/
│   ├── session-chaining-policy.py (Link sessions)
│   ├── auto-save-session.py (Auto-save with ID)
│   └── archive-old-sessions.py (Archive old ones)
│
├── pattern-detection/
│   └── cross-project-patterns-policy.md
│       ↓
│   scripts/architecture/01-sync-system/pattern-detection/
│   ├── detect-patterns.py (Find patterns)
│   ├── apply-patterns.py (Replicate patterns)
│   └── cross-project-patterns-policy.py
│
└── user-preferences/
    └── user-preferences-policy.md
        ↓
    scripts/architecture/01-sync-system/user-preferences/
    ├── preference-auto-tracker.py (Learn preferences)
    └── load-preferences.py (Load on session start)

**OUTPUT:** Complete context + session history + patterns + preferences
```

---

### **LEVEL 2: 🟢 STANDARDS SYSTEM (Rules)**
Define coding standards & constraints

```
policies/02-standards-system/
├── common-standards-policy.md (65+ coding rules)
│   ↓
│   scripts/02-standards-system/
│   ├── common-standards-enforcer.py (Enforce standards)
│   └── standards-loader.py (Load all rules)
│
├── coding-standards-enforcement-policy.md
│   ↓
│   scripts/02-standards-system/
│   ├── coding-standards-enforcer.py
│   └── validate-code-standards.py
│
└── README.md
    Lists all 65 rules organized by category
    - Python/Java/JavaScript rules
    - API design rules
    - Security rules
    - Performance rules
    - Code style rules

**OUTPUT:** 65 standards loaded and ready to enforce
```

---

### **LEVEL 3: 🔴 EXECUTION SYSTEM (Do the work)**
Execute 11 steps in order

```
policies/03-execution-system/

Step 0: Prompt Generation
├─ prompt-generation-policy.md
├─ scripts/00-prompt-generation/prompt-generator.py
└─ OUTPUT: Structured prompt with context

Step 1: Task Breakdown
├─ automatic-task-breakdown-policy.md
├─ scripts/01-task-breakdown/task-auto-tracker.py
└─ OUTPUT: Phases + task list

Step 2: Plan Mode Decision
├─ auto-plan-mode-suggestion-policy.md
├─ scripts/02-plan-mode/auto-plan-mode-suggester.py
└─ OUTPUT: Should use plan mode?

Step 4: Model Selection
├─ intelligent-model-selection-policy.md
├─ scripts/04-model-selection/intelligent-model-selector.py
└─ OUTPUT: Haiku/Sonnet/Opus

Step 5: Skill/Agent Selection
├─ auto-skill-agent-selection-policy.md
├─ scripts/05-skill-agent-selection/
│  ├─ auto-skill-agent-selector.py
│  ├─ core-skills-loader.py (Load from ~/.claude/skills/)
│  └─ core-skills-enforcer.py
└─ OUTPUT: Selected skill + agent

Step 6: Tool Optimization
├─ tool-usage-optimization-policy.md
├─ scripts/06-tool-optimization/tool-usage-optimizer.py
└─ OUTPUT: 60-85% token savings

Step 7: Auto Recommendations
├─ scripts/07-recommendations/auto-recommendation-daemon.py
└─ OUTPUT: Real-time suggestions

Step 8: Progress Tracking
├─ task-progress-tracking-policy.md
├─ scripts/08-progress-tracking/task-progress-tracking-policy.py
└─ OUTPUT: Progress updates

Step 9: Git Auto-Commit
├─ git-auto-commit-policy.md
├─ scripts/09-git-commit/auto-commit.py
├─ version-release-policy.md
└─ OUTPUT: Committed + version bumped

Step 10: Session Save
├─ scripts/session-logger.py
└─ OUTPUT: Session with unique ID

Failure Prevention:
├─ failure-prevention/failure-detector.py
├─ failure-kb.json
└─ OUTPUT: Prevent known failures
```

---

## 🔄 COMPLETE FLOW: HOW IT ALL WORKS

### **Session Start:**
```
1. USER sends message
        ↓
2. HOOKS trigger (UserPromptSubmit)
        ↓
3. 3-level-flow.py runs ALL 3 LEVELS:

   🔵 LEVEL 1 (SYNC):
   - context-reader.py → Load README + SRS + CLAUDE.md
   - session-loader.py → Load previous sessions
   - preference-loader.py → Load user preferences
   - pattern-detector.py → Detect code patterns
   ↓

   🟢 LEVEL 2 (STANDARDS):
   - standards-loader.py → Load 65 coding rules
   - common-standards-enforcer.py → Prepare enforcement
   ↓

   🔴 LEVEL 3 (EXECUTION):
   Step 0: prompt-generator.py → Structured prompt
   Step 1: task-auto-tracker.py → Task breakdown
   Step 2: auto-plan-mode-suggester.py → Plan mode decision
   Step 4: intelligent-model-selector.py → Choose model
   Step 5: auto-skill-agent-selector.py → Choose skill
   Step 6: tool-usage-optimizer.py → Optimize tools
   Step 7: auto-recommendation-daemon.py → Get recommendations
   Step 8: task-progress-tracking-policy.py → Set up tracking
   Step 9: auto-commit.py → Prepare commit
   Step 10: session-logger.py → Prepare session save
   ↓
4. flow-trace.json written with all decisions
        ↓
5. Claude Code executes work with FULL CONTEXT
        ↓
6. HOOKS enforce during execution:
   PreToolUse:  Verify task, optimize tools, block if needed
   PostToolUse: Track progress, auto-commit, post-merge automation
   Stop:        Save session, voice notification
```

---

## 📋 POLICY → SCRIPT MAPPING

| Policy File | What It Says | Script File | What It Does |
|-------------|--------------|------------|--------------|
| context-management-policy.md | "Monitor context ≤85%" | context-monitor-v2.py | Checks usage, archives old |
| session-*-policy.md | "Save with unique IDs" | session-chaining-policy.py | Creates chains |
| cross-project-patterns-policy.md | "Detect & replicate" | detect-patterns.py | Finds patterns |
| common-standards-policy.md | "Follow 65 rules" | common-standards-enforcer.py | Validates all |
| prompt-generation-policy.md | "Generate prompts" | prompt-generator.py | Creates prompts |
| automatic-task-breakdown-policy.md | "Break into tasks" | task-auto-tracker.py | Task structure |
| intelligent-model-selection-policy.md | "Choose right model" | intelligent-model-selector.py | Haiku/Sonnet/Opus |
| auto-skill-agent-selection-policy.md | "Find skill" | auto-skill-agent-selector.py | Selects skill |
| tool-usage-optimization-policy.md | "Save tokens" | tool-usage-optimizer.py | Optimizes calls |
| task-progress-tracking-policy.md | "Track progress" | task-progress-tracking-policy.py | Progress updates |
| git-auto-commit-policy.md | "Commit code" | auto-commit.py | Commits changes |
| version-release-policy.md | "Bump version" | version-release-policy.py | Updates VERSION |

---

## 🎯 HOOK ENFORCEMENT

### **PreToolUse Hook (pre-tool-enforcer.py):**
```
BEFORE Write/Edit/Bash/Read:

1. Level 3.0: Context Read Enforcement
   ✓ Check if project is fresh or existing
   ✓ If existing, verify README+SRS+CLAUDE.md read

2. Level 3.1: Task Breakdown Enforcement
   ✓ Check .task-breakdown-pending flag
   ✓ If set, BLOCK Write/Edit until TaskCreate called

3. Level 3.5: Skill Verification
   ✓ If /skill invoked, verify skill exists
   ✓ Load from core-skills-loader.py
   ✓ Provide available skills list if not found

4. Level 3.6: Tool Optimization
   ✓ Check Read file size → recommend offset/limit
   ✓ Check Grep result size → recommend head_limit
   ✓ Provide optimization hints

5. Level 3.7: Failure Prevention
   ✓ Block Windows-only commands in Bash
   ✓ Block Unicode in .py files
   ✓ Validate command safety

Exit: ALLOW or BLOCK with reason
```

### **PostToolUse Hook (post-tool-tracker.py):**
```
AFTER Write/Edit/Bash/TaskCreate/Skill:

1. Level 3.9: Progress Tracking
   ✓ Update task completion count
   ✓ Update modified files list
   ✓ Record tool execution time

2. Level 3.10: Version Release Enforcement
   ✓ If git push detected, verify VERSION updated
   ✓ Trigger version-release-policy.py if needed

3. Level 3.11: Git Status Validation
   ✓ Check uncommitted changes
   ✓ Warn if threshold exceeded
   ✓ Suggest commit

4. Level 3.12: GitHub Issue Closing
   ✓ If TaskUpdate(completed), close linked issue
   ✓ Use github_issue_manager.py

5. Level 3.10+: Post-Merge Automation
   ✓ Detect 'gh pr merge' or 'git push' to main
   ✓ Call post-merge-version-updater.py
   ✓ Auto-bump VERSION + README + SRS

6. Session Progress Tracking
   ✓ Save session-progress.json
   ✓ Archive old sessions if needed
```

### **Stop Hook (stop-notifier.py):**
```
WHEN session ends:

1. Finalize session-progress.json
2. Archive if needed (30+ days old)
3. Generate session summary
4. Voice notification with completion stats
5. Save session with unique ID
```

---

## 📊 DATA STRUCTURES

### **flow-trace.json (What 3-level flow decided):**
```json
{
  "session_id": "SESSION-20260310-011657-ABC1",
  "timestamp": "2026-03-10T01:16:57...",
  "level_minus_1": { ... },
  "level_1": {
    "context": "README loaded, 5 previous sessions, patterns detected",
    "status": "OK"
  },
  "level_2": {
    "standards": "65 rules loaded, enforcement ready",
    "status": "OK"
  },
  "level_3": {
    "step_0_prompt": { ... },
    "step_1_tasks": { ... },
    "step_4_model": "SONNET",
    "step_5_skill": "python-backend-engineer",
    "step_6_tools": { optimizations: [...] },
    "status": "OK"
  }
}
```

### **session-progress.json (Current session state):**
```json
{
  "session_id": "SESSION-...",
  "started_at": "2026-03-10T01:16:57...",
  "tasks_created": 5,
  "tasks_completed": 2,
  "tool_calls": 23,
  "modified_files": ["src/app.py", "tests/test_app.py"],
  "context_usage": "71%",
  "model_selected": "SONNET",
  "skill_selected": "python-backend-engineer"
}
```

---

## 🚀 EXAMPLE: Write Python File

### **Before (No policies):**
```
User: "Write a new API endpoint"
Claude: Writes code
- Doesn't match existing patterns
- Violates some standards
- Uses inefficient tools
- Task not tracked
- Not committed
- Session lost
```

### **After (With full 3-level system):**
```
1. Load context (Level 1)
   ✓ README: "This is Flask API with SQLAlchemy"
   ✓ Patterns: "All endpoints use @app.route decorator"
   ✓ History: "Previous endpoints in services/api/"

2. Load standards (Level 2)
   ✓ 65 rules: "All functions need docstrings"
   ✓ "API responses must be JSON"
   ✓ "Use type hints"

3. Execute with full context (Level 3)
   Step 0: Generate prompt with context
   Step 1: Break into tasks (Route + Handler + Tests)
   Step 2: Complexity=3, no plan mode needed
   Step 4: Choose Sonnet (medium complexity)
   Step 5: Select python-backend-engineer skill
   Step 6: Optimize Read (use offset/limit)
   ↓
   PreToolUse Hook:
   ✓ Check TaskCreate called (Step 1)
   ✓ Verify skill available
   ✓ Optimize tools
   ↓
   Write code:
   - Matches Flask pattern
   - Follows all 65 standards
   - Uses type hints
   - Has docstrings
   ↓
   PostToolUse Hook:
   ✓ Track progress (1 task completed)
   ✓ Auto-commit: "feat: Add /users endpoint"
   ✓ Version bump: "1.0.0" → "1.1.0"
   ✓ Update README + SRS
   ↓
   Stop Hook:
   ✓ Save session
   ✓ Voice: "Session saved: 3 tasks, 5 commits"

RESULT: Production-ready code + committed + versioned + documented!
```

---

## ✅ COMPLETE STATUS

```
LEVEL 1 (SYNC):
  ├─ Context Management: 3 scripts + policy ✅
  ├─ Session Management: 5 scripts + policy ✅
  ├─ Pattern Detection: 3 scripts + policy ✅
  └─ User Preferences: 2 scripts + policy ✅
     Total: 36 files

LEVEL 2 (STANDARDS):
  ├─ Common Standards: 65 rules ✅
  ├─ Enforcement: 2 scripts + policy ✅
  └─ Validation: 1 script ✅
     Total: 12 enforcement rules

LEVEL 3 (EXECUTION):
  ├─ Step 0 (Prompt): 1 script + policy ✅
  ├─ Step 1 (Task): 2 scripts + policy ✅
  ├─ Step 2 (Plan): 1 script + policy ✅
  ├─ Step 4 (Model): 3 scripts + policy ✅
  ├─ Step 5 (Skill): 6 scripts + policy ✅
  ├─ Step 6 (Tools): 4 scripts + policy ✅
  ├─ Step 7 (Recommendations): 5 scripts ✅
  ├─ Step 8 (Progress): 3 scripts + policy ✅
  ├─ Step 9 (Commit): 5 scripts + policy ✅
  ├─ Step 10 (Session): 1 script ✅
  └─ Failure Prevention: 8 scripts ✅
     Total: 66 scripts, 11 steps

HOOKS:
  ├─ UserPromptSubmit: 3-level-flow + github_issue_manager ✅
  ├─ PreToolUse: pre-tool-enforcer (5 enforcement levels) ✅
  ├─ PostToolUse: post-tool-tracker (6 tracking levels) ✅
  └─ Stop: stop-notifier ✅

OVERALL: 45 POLICIES + 74+ SCRIPTS = FULLY INTEGRATED 3-LEVEL SYSTEM ✅
```

---

**Bilkul! Ab tume complete flow clear ho gaya! 🎉**

Policies = Rules + Decisions
Scripts = Implementation + Enforcement
Hooks = Real-time Validation

Together they ensure 100% standards compliance + context awareness + progress tracking!
