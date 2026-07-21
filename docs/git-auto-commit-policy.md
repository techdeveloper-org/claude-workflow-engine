# Git Auto Commit Policy (ALWAYS ACTIVE)

## System-Level Requirement

This is a **permanent rule** that applies automatically when todos/phases/tasks complete.

---

## Mandatory Git Workflow

### Auto-Commit Triggers (MANDATORY)

Claude MUST automatically commit and push changes when ANY of these events occur:

1. **Phase Completion**
   - When any phased execution phase completes
   - Checkpoint commit with phase summary
   - Auto-push to remote

2. **Todo Completion**
   - When a TaskUpdate marks status as "completed"
   - Commit with descriptive message
   - Auto-push to remote

3. **Periodic Checkpoints**
   - Every 3-5 file changes during active work
   - Prevents loss of progress
   - Auto-push for backup

---

## Commit Message Format

### Phase Completion
```
✅ Phase [N] Complete: [Phase Name]

[Summary of what was accomplished]
- Key change 1
- Key change 2

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Todo Completion
```
✓ Task Complete: [Task Subject]

[Brief description of changes]

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Periodic Checkpoint
```
🔄 Checkpoint: [Current Work Summary]

Progress on: [Task/Phase]
Files changed: [List]

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

---

## Execution Flow

When auto-commit is triggered:

1. **Stage Changes**
   ```bash
   git add -A
   ```

2. **Create Commit**
   ```bash
   git commit -m "$(cat <<'EOF'
   [Formatted commit message]
   EOF
   )"
   ```

3. **Push to Remote**
   ```bash
   git push
   ```

4. **Handle Errors**
   - If push fails (no remote): Skip push, commit locally
   - If push fails (rejected): Pull first, then push
   - If commit fails (hook): Fix issue, retry commit
   - Always inform user of status

---

## Integration with Workflows

### With Phased Execution
```
Phase 1 complete → Auto-commit → Auto-push → Checkpoint saved
User runs: claude --resume
Phase 2 complete → Auto-commit → Auto-push → Checkpoint saved
```

### With Task Management
```
TaskUpdate(taskId: "1", status: "completed")
  ↓
Auto-commit triggered
  ↓
Changes committed & pushed
  ↓
User informed: "✅ Task committed and pushed"
```

### Periodic During Work
```
File 1 changed
File 2 changed
File 3 changed → Auto-checkpoint commit & push
File 4 changed
File 5 changed
File 6 changed → Auto-checkpoint commit & push
```

---

## Safety Rules

1. **Never Force Push**
   - Always pull before pushing if rejected
   - Preserve remote changes

2. **Respect Hooks**
   - If pre-commit hook fails, fix and retry
   - Never use --no-verify

3. **Clean Commits**
   - Stage specific files when possible
   - Avoid committing secrets (.env, credentials)
   - Check git status before staging

4. **Inform User**
   - Always announce when auto-commit happens
   - Show commit message created
   - Report push status (success/failure)

---

## User Notifications

When auto-commit happens, inform user:

```
✅ Auto-committed: Phase 1 Complete
📤 Pushed to remote successfully

Commit message:
✅ Phase 1 Complete: Core Authentication
- JWT setup complete
- Login/logout routes working
```

If push fails:
```
✅ Auto-committed: Phase 1 Complete
⚠️ Push failed: No remote configured

Changes are saved locally. Set up remote with:
git remote add origin <url>
```

---

## Priority

**SYSTEM-LEVEL**: This policy activates automatically after:
1. context-management-core (context validation)
2. model-selection-core (model selection)
3. task-planning-intelligence (planning decision)
4. phased-execution-intelligence (phase execution)
5. common-failures-prevention (tool checks)
6. Task/Phase completion event

---

## Exception Cases

**Do NOT auto-commit when:**
- User explicitly says "don't commit"
- Working directory is not a git repo
- User is in detached HEAD state
- Merge conflict is in progress

In these cases, inform user and skip auto-commit.

---

## Status

**ACTIVE**: This policy is permanent and applies to all sessions.
**Version**: 1.0.0
**Last Updated**: 2026-01-23 (Initial creation - Auto git commit/push on phase/todo completion)
