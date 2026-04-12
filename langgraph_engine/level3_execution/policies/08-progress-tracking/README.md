# 📊 Progress Tracking (Step 8)

**Part of:** 🔴 Execution System

**Purpose:** Automatically track task progress with granular updates

---

## 📋 What This Does

- Auto-track task progress (0-100%)
- Update progress metadata frequently (every 2-3 tool calls)
- Track current step, completed items, blocked status
- Enforce task/phase creation based on complexity
- Integrate with git auto-commit on completion

---

## 📁 Files in This Folder

### **Policies:**
- `task-phase-enforcement-policy.md` - BLOCKING policy (complexity-based task creation)
- `task-progress-tracking-policy.md` - Granular progress updates policy

### **Enforcers:**
- `check-incomplete-work.py` - Check for incomplete tasks/phases

---

## 🎯 Usage

### **Check Task/Phase Requirements:**
```bash
python task-phase-enforcer.py --analyze "Create Product API"
```

**Output:**
```json
{
  "complexity_score": 21,
  "task_creation_required": true,
  "phase_division_required": true,
  "recommended_phases": 3,
  "recommended_tasks_per_phase": 3,
  "blocking": true,
  "message": "⛔ BLOCKING: Complexity 21 requires TaskCreate + Phases BEFORE proceeding"
}
```

### **Check Incomplete Work:**
```bash
python check-incomplete-work.py
```

---

## 📊 Task Creation Rules (BLOCKING)

| Complexity | Task Creation | Phase Division | Action |
|------------|---------------|----------------|--------|
| 0-2 | ❌ Optional | ❌ No | Continue directly |
| 3-5 | ✅ REQUIRED | ❌ No | Create tasks, no phases |
| 6-9 | ✅ REQUIRED | ✅ REQUIRED | Create 2 phases |
| 10-19 | ✅ REQUIRED | ✅ REQUIRED | Create 2-3 phases |
| 20+ | ✅ REQUIRED | ✅ REQUIRED | Create 3-4 phases |

**Complexity Formula:**
```
complexity = files × 2 + operations × 3 + entities × 5 + dependencies × 1
```

---

## 📈 Progress Tracking Workflow

**Step 1: Task Creation (if required)**
```python
TaskCreate(
    subject="Implement Product API",
    description="...",
    activeForm="Implementing Product API"
)
```

**Step 2: Mark In Progress**
```python
TaskUpdate(
    taskId="1",
    status="in_progress"
)
```

**Step 3: Frequent Progress Updates (Every 2-3 Tool Calls)**
```python
TaskUpdate(
    taskId="1",
    metadata={
        "progress": 35,
        "current_step": "Creating entity classes",
        "completed": ["Controller", "Service interface"],
        "pending": ["Repository", "Tests"],
        "files_modified": 3
    }
)
```

**Step 4: Mark Completed**
```python
TaskUpdate(
    taskId="1",
    status="completed",
    metadata={
        "progress": 100,
        "files_modified": 8,
        "tests_passed": 15
    }
)
```

**Step 5: Auto-Commit Triggers (Automatic)**
- Git auto-commit enforcer runs
- All repos with changes get committed
- Session saved with commit hashes

---

## ⚠️ BLOCKING Enforcement

**This is a BLOCKING policy:**
- If complexity >= 3, you MUST create tasks before proceeding
- If complexity >= 6, you MUST create phases before proceeding
- task-phase-enforcer.py will return `blocking: true`
- You CANNOT proceed until tasks/phases are created

**Example:**
```
User: "Create authentication system"
→ Run task-phase-enforcer.py
→ Complexity: 18
→ Result: BLOCKING - Create 3 phases with 3 tasks each
→ Create TaskCreate calls
→ THEN proceed with implementation
```

---

## ✅ Benefits

- **Visibility:** User knows exactly where you are
- **Recovery:** Can resume from any point
- **Quality:** Forces proper planning for complex tasks
- **Integration:** Triggers auto-commit automatically

---

**Location:** `~/.claude/memory/03-execution-system/08-progress-tracking/`
