# Task Progress Tracking Policy (MANDATORY)

## Status: 🟢 ALWAYS ACTIVE

**Version:** 1.0.0
**Last Updated:** 2026-02-16
**Purpose:** Ensure granular progress tracking for session resumability

---

## 🚨 CRITICAL RULE

**I MUST update task progress FREQUENTLY throughout work, not just at start/end.**

This ensures:
- ✅ I know exactly where I was if session exits
- ✅ User sees real-time progress
- ✅ Can resume from exact point
- ✅ Clear accountability

---

## Mandatory Status Updates

### When to Update Task Status

**ALWAYS update task status at these points:**

1. **Task Start**
   - `TaskUpdate(id, status="in_progress")`

2. **After Each Sub-Step Completes**
   - `TaskUpdate(id, metadata={"progress": "Step 1/5 complete"})`

3. **Before Context-Heavy Operations**
   - `TaskUpdate(id, metadata={"current": "Reading files..."})`

4. **After Major Milestones**
   - `TaskUpdate(id, metadata={"milestone": "API implemented, starting tests"})`

5. **Task Completion**
   - `TaskUpdate(id, status="completed")`

---

## Progress Metadata Structure

### Using Metadata Field

Store progress information in task metadata:

```json
{
  "progress": "3/5 steps complete",
  "current_step": "Implementing authentication",
  "completed": ["Setup", "Database", "API endpoints"],
  "remaining": ["Frontend", "Tests"],
  "notes": "JWT token generation working",
  "last_file": "src/auth/AuthService.java:145"
}
```

### Update Frequency

- **Minimum:** Every significant action
- **Recommended:** Every 2-3 tool calls
- **Maximum:** Don't let > 5 tool calls pass without update

---

## Implementation Pattern

### Single Task Example

```
User: "Fix authentication bug"

TaskCreate("Fix authentication bug") → Task ID: 1

TaskUpdate(1, status="in_progress")

[Analyze code]
TaskUpdate(1, metadata={"progress": "Analyzing auth flow"})

[Found issue]
TaskUpdate(1, metadata={
  "progress": "Found issue in JWT validation",
  "location": "AuthService.java:234"
})

[Implement fix]
TaskUpdate(1, metadata={
  "progress": "Implementing fix",
  "completed": ["Analysis", "Issue identification"]
})

[Test fix]
TaskUpdate(1, metadata={
  "progress": "Testing fix"
})

[Complete]
TaskUpdate(1, status="completed", metadata={
  "summary": "Fixed JWT token expiry validation"
})
```

---

## Resume Capability

### How Progress Tracking Enables Resume

If session exits unexpectedly:

1. **Check Task List** - `TaskList()`

2. **Find Last Active Task**
   ```
   Task #5: status="in_progress"
   Metadata: {
     "progress": "3/5 steps complete",
     "completed": ["Setup", "Database", "API"],
     "current": "Implementing frontend",
     "last_file": "LoginPage.tsx:67"
   }
   ```

3. **Resume From Exact Point**
   - Know what's done
   - Know current location
   - Continue seamlessly

---

## Benefits

### For Me (Claude)
- ✅ Know exactly where I was
- ✅ Can resume seamlessly
- ✅ Better context management

### For User
- ✅ Real-time progress visibility
- ✅ Can see what's done/remaining
- ✅ Can resume without re-explaining

---

## Examples

### ✅ GOOD: Frequent Updates

```
TaskCreate("Implement user registration")
TaskUpdate(1, status="in_progress")

TaskUpdate(1, metadata={"step": "Creating User entity"})
→ 30 seconds later

TaskUpdate(1, metadata={"step": "Implementing validation"})
→ 45 seconds later

TaskUpdate(1, metadata={"step": "Adding password hashing"})
→ 1 minute later

TaskUpdate(1, status="completed")
```

**Result:** Clear progress trail, easy to resume ✓

---

### ❌ BAD: No Intermediate Updates

```
TaskCreate("Implement user registration")
TaskUpdate(1, status="in_progress")

[5 minutes of work with no updates]

TaskUpdate(1, status="completed")
```

**Problem:**
- ❌ No visibility into progress
- ❌ Can't resume if session breaks

---

## Best Practices

### DO:
- ✅ Update progress every 2-3 tool calls
- ✅ Use descriptive metadata
- ✅ Track completed/remaining items
- ✅ Note current file/location

### DON'T:
- ❌ Only update at start/end
- ❌ Skip intermediate updates
- ❌ Use vague metadata ("working...")

---

## Quick Reference

### Update Checklist

```
□ TaskUpdate at start (in_progress)
□ TaskUpdate after each sub-step (metadata)
□ TaskUpdate at milestones (metadata)
□ TaskUpdate at completion (completed)
```

### Metadata Template

```json
{
  "progress": "X/Y steps complete",
  "current_step": "What I'm doing now",
  "completed": ["Done1", "Done2"],
  "remaining": ["Todo1", "Todo2"],
  "last_file": "path/to/file:line"
}
```

---

## Summary

**Key Principles:**

1. **Update Frequently** - Every 2-3 tool calls minimum
2. **Be Specific** - Clear metadata about progress
3. **Track Location** - File and line number
4. **Enable Resume** - Anyone can pick up where I left
5. **Trust Through Visibility** - User always knows status

**Remember:**
> Frequent updates = Better resumability = Less rework = Happier user

---

**STATUS:** 🟢 ACTIVE
**ENFORCEMENT:** Self-enforced with reminders
**INTEGRATION:** Works with TaskCreate/TaskUpdate tools
