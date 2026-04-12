# Session Memory Policy (Simple Persistent Memory)

## Version: 1.0.0
## Status: ALWAYS ACTIVE
## Priority: SYSTEM-LEVEL

---

## Purpose

Provides **100% local, 100% private persistent memory** across Claude Code sessions without external API calls or complex dependencies.

**Key Principle:** Simple markdown files > Complex databases

---

## How It Works

### **Session Start:**
```
1. Detect current project folder
2. Load ~/.claude/memory/sessions/{project-name}/project-summary.md
3. Inject context into session
4. User gets continuity from previous sessions ✅
```

### **Session End / Phase Complete:**
```
1. Claude generates session summary (from conversation analysis)
2. Save to ~/.claude/memory/sessions/{project-name}/session-{timestamp}.md
3. Update project-summary.md (cumulative context)
4. Next session auto-loads this context ✅
```

---

## Storage Structure

```
~/.claude/memory/sessions/
├── example-project-ui/
│   ├── session-2026-01-25-15-00.md     (individual session)
│   ├── session-2026-01-24-10-30.md     (individual session)
│   └── project-summary.md               (← MAIN FILE - auto-loaded)
│
├── medspy-node/
│   ├── session-2026-01-23-14-00.md
│   └── project-summary.md
│
├── m2-surgicals-ui/
│   └── project-summary.md
│
└── triglav-node/
    └── project-summary.md
```

**Organization:**
- One folder per project (based on project folder name)
- `project-summary.md` = Cumulative context (loaded at session start)
- `session-{timestamp}.md` = Individual session records (for reference)

---

## Session Summary Template

### **Individual Session File Format:**

```markdown
# Session Summary
**Date:** 2026-01-25 15:00-16:00
**Project:** {project-name}
**Location:** {full-path}
**Duration:** {time}

---

## 📋 What Was Done

- Task 1: Description
- Task 2: Description
- Task 3: Description

---

## 🎯 Key Decisions Made

### Technical Decisions:
- ✅ Decision 1 with reasoning
- ✅ Decision 2 with reasoning

### User Preferences (for THIS project):
- Prefers X over Y for Z reason
- Skip tests for rapid iteration
- Plan mode threshold: 7+ complexity

### Architecture Choices:
- JWT authentication (not session-based)
- REST API (not GraphQL) - simpler for this project
- SQLite (not Postgres) - sufficient for scale

---

## 📝 Files Modified

```
src/app/services/auth.service.ts       (added JWT refresh logic)
src/app/components/login/login.component.ts  (updated error handling)
src/app/interceptors/auth.interceptor.ts     (new file - token refresh)
```

---

## 💡 Important Context for Next Session

**Don't suggest again:**
- Session-based auth (user chose JWT)
- GraphQL (user prefers REST for this project)
- Writing tests (user skips for rapid iteration)

**Remember:**
- Auth flow is JWT-based, token in localStorage
- Error handling pattern established in auth.service.ts
- Interceptor handles refresh globally - don't duplicate

**Architecture patterns used:**
- Service-based architecture (Angular best practices)
- Interceptors for cross-cutting concerns
- RxJS for async handling

---

## 📦 Dependencies Added

```json
None this session
```

---

## 🔄 Pending Work / Next Steps

- [ ] Add password reset flow
- [ ] Implement remember-me functionality
- [ ] Add 2FA support (low priority)

---

## 🐛 Known Issues

- None currently

---

## 📊 Policy Stats (This Session)

- Model selection: ✅ Haiku for searches, Sonnet for implementation
- Planning intelligence: ✅ Complexity score 5 → Direct implementation (user choice)
- Proactive consultation: ✅ Asked user about approach
- Failures prevented: 0
- Auto-commits: 1 (after auth implementation)
```

---

### **Project Summary File Format (Cumulative):**

```markdown
# Project Summary: {project-name}

**Last Updated:** 2026-01-25 16:00
**Project Path:** {full-path}
**Total Sessions:** 5

---

## 🎯 Project Quick Context (Read This First!)

**In 3 lines:**
This is an Angular 19 app for example-project.org with JWT authentication,
service-based architecture, and REST API integration. User prefers rapid
iteration (skip tests), direct implementation for <7 complexity tasks.

---

## 🏗️ Architecture Overview

**Frontend:** Angular 19 + Angular Material + Bootstrap
**Auth:** JWT (localStorage + httpOnly refresh cookie)
**API Integration:** REST (services pattern)
**State:** Services + RxJS (no NgRx - overkill for this scale)

**Key Patterns:**
- Service-based architecture
- Interceptors for cross-cutting concerns
- Component-service separation
- RxJS for async operations

---

## 👤 User Preferences (This Project)

**Model Selection:**
- ✅ Haiku for searches/exploration
- ✅ Sonnet for implementation
- ✅ Plan mode only for 7+ complexity

**Development Workflow:**
- ✅ Skip tests (rapid iteration)
- ✅ Direct implementation over planning (unless complex)
- ✅ Phased approach for 6+ size tasks

**Technical Preferences:**
- ✅ JWT auth (not session)
- ✅ REST API (not GraphQL)
- ✅ Services pattern (not NgRx)
- ✅ Plain CSS (not SCSS) - simplicity

---

## 📂 Project Structure

```
src/
├── app/
│   ├── components/        (UI components)
│   ├── services/          (Business logic, API calls)
│   ├── interceptors/      (HTTP interceptors)
│   ├── guards/            (Route guards)
│   ├── models/            (TypeScript interfaces)
│   └── utils/             (Helper functions)
```

---

## 🔑 Key Files to Remember

| File | Purpose | Last Modified |
|------|---------|---------------|
| `auth.service.ts` | JWT auth logic, token refresh | 2026-01-25 |
| `auth.interceptor.ts` | Auto token attachment, refresh on 401 | 2026-01-25 |
| `login.component.ts` | Login UI, error handling | 2026-01-25 |

---

## ✅ Implemented Features

- [x] JWT Authentication
- [x] Token refresh mechanism
- [x] Login/Logout
- [x] Protected routes (guards)
- [x] Error handling in auth flow
- [ ] Password reset (pending)
- [ ] Remember me (pending)
- [ ] 2FA (future)

---

## 🚫 Don't Suggest These (Already Decided Against)

- ❌ Session-based auth → User chose JWT
- ❌ GraphQL → User prefers REST
- ❌ NgRx/state management → Services sufficient
- ❌ SCSS/preprocessors → Plain CSS preferred
- ❌ Writing tests → Skip for rapid iteration

---

## 🐛 Known Issues / Technical Debt

None currently

---

## 📦 Dependencies

**Production:**
- @angular/core: ^19.0.0
- @angular/material: ^19.0.0
- bootstrap: ^5.3.0

**Dev:**
- typescript: ^5.6.0

---

## 🔄 Next Session TODO

- [ ] Implement password reset flow
- [ ] Add remember-me checkbox
- [ ] Consider 2FA (low priority)

---

## 📊 Session History

1. **2026-01-25 15:00** - Implemented JWT auth, token refresh, login flow
2. **2026-01-24 10:30** - Initial setup, routing, basic components
3. **2026-01-23 14:00** - Project creation, structure planning

---

## 💭 Notes for Claude

- This user prefers practical over perfect
- Fast iteration > thorough testing
- Simple solutions > over-engineered ones
- Ask before planning complex tasks
- Remember JWT is the auth choice - don't suggest alternatives
```

---

## When to Save Session Summary

### **Automatic Triggers:**

1. **Session End** (user exits)
   - Generate summary of what was done
   - Update project-summary.md

2. **Phase Completion** (multi-phase tasks)
   - Save phase summary
   - Update cumulative context

3. **Major Milestone** (user request)
   - User says "summarize this session"
   - Save checkpoint

### **Manual Triggers:**

User can request:
```
"Save session summary"
"Update project context"
"Create checkpoint"
```

---

## When to Load Project Summary

### **Automatic:**

1. **Session Start**
   - If project-summary.md exists → Auto-load
   - Inject context silently (don't mention unless relevant)

2. **User Asks Context Question**
   - "What did we do last time?"
   - "What's the auth setup?"
   - Reference summary to answer

### **On-Demand:**

User can request:
```
"Load project context"
"What do you remember about this project?"
"Show me previous decisions"
```

---

## What to Capture in Summary

### **MUST Include:**

1. **Technical Decisions**
   - Technology choices (JWT vs Session, REST vs GraphQL)
   - Architecture patterns used
   - Why these choices were made

2. **User Preferences** (project-specific)
   - Model selection preferences
   - Planning threshold
   - Test policy preference
   - Code style preferences

3. **Files Modified**
   - What changed
   - Why it changed
   - Key functions/components added

4. **Important Context**
   - What NOT to suggest (rejected alternatives)
   - Established patterns (don't violate)
   - Known issues or constraints

5. **Pending Work**
   - Clear TODO list
   - Next logical steps

### **SKIP (Don't Capture):**

1. **Sensitive Data**
   - API keys, passwords, tokens
   - Personal information
   - Client confidential data

2. **Temporary Context**
   - Debugging output
   - Trial-and-error attempts
   - One-off experiments

3. **Obvious Info**
   - Standard framework conventions
   - Common knowledge
   - Generic best practices

---

## Privacy & Security

### **100% Local:**

- ✅ All summaries stored locally in `~/.claude/memory/sessions/`
- ✅ No external API calls for storage
- ✅ No cloud sync
- ✅ Plain markdown (human-readable)

### **User Control:**

**View all sessions:**
```bash
ls -la ~/.claude/memory/sessions/{project-name}/
```

**Read summary:**
```bash
cat ~/.claude/memory/sessions/{project-name}/project-summary.md
```

**Edit summary:**
```bash
nano ~/.claude/memory/sessions/{project-name}/project-summary.md
```

**Delete old sessions:**
```bash
rm ~/.claude/memory/sessions/{project-name}/session-2026-01-20*.md
```

**Delete entire project context:**
```bash
rm -rf ~/.claude/memory/sessions/{project-name}/
```

**Delete sensitive content:**
Just edit the MD file and remove lines!

---

## Integration with Existing Policies

### **Works WITH:**

1. **core-skills-mandate.md**
   - Session summaries INCLUDE policy stats
   - Track model selection, planning decisions
   - Log compliance

2. **proactive-consultation-policy.md**
   - Save user's decision preferences per project
   - Don't ask same question twice for same project

3. **git-auto-commit-policy.md**
   - Session end triggers summary + commit
   - Checkpoint summaries on git commits

4. **file-management-policy.md**
   - Session summaries stored in memory/ folder
   - Old sessions can be archived/deleted

### **🛡️ PROTECTED from Context Auto-Cleanup:**

**CRITICAL:** Session memory files are **NEVER affected** by context management auto-cleanup!

**What Context Cleanup Does:**
- ✅ Clears old conversation messages
- ✅ Compacts MCP responses
- ✅ Removes completed task details
- ✅ Summarizes long prompts

**What Context Cleanup NEVER Does:**
- ❌ Delete session memory files (`~/.claude/memory/sessions/**`)
- ❌ Remove project-summary.md
- ❌ Clean up session-*.md records
- ❌ Touch policy files or configurations

**Why This Matters:**
- Session memory = persistent storage (like git history)
- Context cleanup = temporary memory management (like RAM)
- Mixing them would destroy user's project context!

**Separation:**
```
Context Cleanup (Temporary):
  - Conversation context
  - In-session task details
  - MCP responses
  - Debugging output
  ↓
  Clears every session (intentional)

Session Memory (Persistent):
  - ~/.claude/memory/sessions/
  - project-summary.md
  - session-*.md files
  ↓
  Persists forever (intentional)
```

### **Enhances:**

- **Context management** - Perfect historical context
- **Model selection** - Remember per-project preferences
- **Planning intelligence** - Remember complexity thresholds
- **User preferences** - No re-asking same questions

---

## Summary Generation Process

### **How Claude Generates Summary:**

**Analysis Sources:**
1. Conversation history (what user requested)
2. Tool usage (files read, edited, created)
3. Git diff (what actually changed)
4. User decisions made (from AskUserQuestion responses)
5. Policies applied (from logs)

**Format:**
1. Extract key points
2. Identify decisions
3. List files modified
4. Note user preferences
5. Suggest next steps

**Quality:**
- Concise (not verbose)
- Actionable (useful for next session)
- Accurate (based on actual work done)
- Organized (easy to scan)

---

## Folder Naming Convention

**Project Name Detection:**

```bash
# Option 1: Use current folder name
PROJECT_NAME=$(basename "$PWD")

# Option 2: Use git repo name
PROJECT_NAME=$(basename $(git rev-parse --show-toplevel 2>/dev/null) || basename "$PWD")

# Option 3: User override (in project .clauderc)
# .clauderc file:
#   CLAUDE_PROJECT_NAME="example-project-ui"
```

**Examples:**
```
/c/Users/techd/Documents/workspace/example-project/frontend/example-project-ui
→ sessions/example-project-ui/

/c/Users/techd/Documents/workspace/medspy/backend/medspy-node
→ sessions/medspy-node/

Custom override in .clauderc:
→ sessions/custom-project-name/
```

---

## Workflow Examples

### **Example 1: New Project (First Session)**

```
Session starts in: example-project-ui/
Claude checks: ~/.claude/memory/sessions/example-project-ui/project-summary.md
Result: File doesn't exist
Claude: Starts fresh (no previous context)

[Work happens: User implements auth]

Session ends:
Claude: Generates summary
Saves to:
  - sessions/example-project-ui/session-2026-01-25-15-00.md
  - sessions/example-project-ui/project-summary.md (created)
```

### **Example 2: Continuing Project (Second Session)**

```
Session starts in: example-project-ui/
Claude checks: ~/.claude/memory/sessions/example-project-ui/project-summary.md
Result: File exists! ✅
Claude loads:
  - JWT auth is implemented
  - User prefers Haiku for searches
  - User chose REST over GraphQL
  - Password reset is pending

User: "Add password reset"
Claude: "I see JWT auth is already implemented in auth.service.ts.
         I'll add password reset following the same pattern.
         Should I use the existing error handling approach?"

[User feels continuity! Claude remembers context!]
```

### **Example 3: Switching Projects**

```
Morning session in: example-project-ui/
Claude loads: example-project-ui context ✅

Afternoon session in: medspy-node/
Claude detects project change
Claude loads: medspy-node context ✅
(Doesn't confuse with example-project context!)
```

---

## Maintenance

### **Storage Management:**

**Growth rate:**
- ~1-2 KB per session summary
- ~5-10 KB project summary
- 100 sessions = ~200 KB (negligible)

**Cleanup strategy:**
```bash
# Archive old sessions (older than 30 days)
find ~/.claude/memory/sessions/ -name "session-*.md" -mtime +30 -exec mv {} ~/.claude/memory/archive/ \;

# Delete archived sessions (older than 90 days)
find ~/.claude/memory/archive/ -name "session-*.md" -mtime +90 -delete

# Or manual cleanup anytime
rm ~/.claude/memory/sessions/old-project/session-2025-*.md
```

**project-summary.md:**
- Keep updated (don't let it get stale)
- Review and edit manually if needed
- Regenerate if confused (delete and let Claude rebuild)

---

## Logging

**Session memory actions should be logged:**

```bash
# When summary is saved
echo "[$(date '+%Y-%m-%d %H:%M:%S')] session-memory | summary-saved | project-name" >> ~/.claude/memory/logs/policy-hits.log

# When context is loaded
echo "[$(date '+%Y-%m-%d %H:%M:%S')] session-memory | context-loaded | project-name" >> ~/.claude/memory/logs/policy-hits.log

# Update counter
policy="session-memory" && counter_file=~/.claude/memory/logs/policy-counters.txt && \
current=$(grep "^$policy=" "$counter_file" 2>/dev/null | cut -d'=' -f2 || echo "0") && \
new=$((current + 1)) && \
sed -i "s/^$policy=.*/$policy=$new/" "$counter_file" 2>/dev/null || echo "$policy=$new" >> "$counter_file"
```

---

## Session ID System (v2.0 - Enhanced)

### **Purpose:**
Enable session retrieval by unique ID for context reuse without token waste.

**Use Case:**
```
User: "Bhai session ID abc123 me dekh, authentication ka kaam kiya tha, ab improve karna hai"
Claude: Loads session abc123 context → knows exactly what was done → improves it
```

**Token Savings:** 70-90% (no re-explanation needed!)

---

### **1. Session ID Generation**

**On Claude Start:**
```python
import uuid
from datetime import datetime

# Generate unique session ID
session_id = str(uuid.uuid4())[:8]  # Short ID: "a3f7b2c1"

# Alternative: Readable ID
timestamp = datetime.now().strftime("%Y%m%d-%H%M")
session_id = f"{timestamp}-{uuid.uuid4().hex[:4]}"  # "20260216-1430-a3f7"

print(f"🎯 Session Started: {session_id}")
```

**Session ID Format Options:**

**Option 1: Short UUID (8 chars)**
- Example: `a3f7b2c1`
- Pros: Compact, unique
- Cons: Not human-readable

**Option 2: Timestamp + Short UUID**
- Example: `20260216-1430-a3f7`
- Pros: Sortable, unique, includes date/time
- Cons: Slightly longer

**Option 3: Descriptive ID**
- Example: `auth-feature-a3f7`
- Pros: Human-readable purpose
- Cons: Not auto-generated

**Recommended:** Option 2 (timestamp + short UUID)

---

### **2. Session Metadata Structure**

**File:** `~/.claude/memory/sessions/{project-name}/session-{session-id}.md`

**Example:** `~/.claude/memory/sessions/surgricalswale/session-20260216-1430-a3f7.md`

```markdown
---
session_id: "20260216-1430-a3f7"
timestamp: "2026-02-16 14:30:00"
project: "surgricalswale"
purpose: "Implement authentication feature"
tags: ["authentication", "jwt", "security", "user-service"]
duration: "45 minutes"
files_modified: 5
status: "completed"
---

# Session: 20260216-1430-a3f7

## Quick Summary (3 lines)
Implemented JWT authentication for user-service with token refresh mechanism.
Added login/logout endpoints with proper error handling.
Integrated with Secret Manager for JWT secret storage.

---

## 📋 What Was Done

1. **Created AuthController**
   - POST /api/v1/auth/login
   - POST /api/v1/auth/logout
   - POST /api/v1/auth/refresh

2. **Implemented AuthService**
   - JWT token generation
   - Token validation
   - Refresh token logic

3. **Added Security Config**
   - Spring Security configuration
   - JWT filter
   - CORS settings

---

## 🎯 Key Decisions Made

### Technical Decisions:
- ✅ JWT (not session-based) - stateless, scalable
- ✅ Access token (15 min) + Refresh token (7 days)
- ✅ Tokens stored in Secret Manager
- ✅ Password hashing using BCrypt

### User Preferences (for THIS project):
- Prefers stateless auth over sessions
- Skip writing tests (rapid iteration)
- Use standard Spring Security patterns

---

## 📝 Files Modified

```
backend/user-service/src/main/java/
├── controller/AuthController.java           (created)
├── services/AuthService.java                (created)
├── services/impl/AuthServiceImpl.java       (created)
├── config/SecurityConfig.java               (created)
├── filter/JwtAuthenticationFilter.java      (created)
└── constants/SecurityConstants.java         (created)
```

---

## 💡 Important Context for Future

**Architecture:**
- JWT flow: Login → Access token + Refresh token
- Access token in header: Authorization: Bearer {token}
- Refresh endpoint: /auth/refresh with refresh token

**Don't suggest again:**
- Session-based auth (user chose JWT)
- Storing tokens in database (Secret Manager used)
- Complex refresh logic (simple 7-day refresh is fine)

---

## 🔗 Related Sessions

- Previous: `20260215-1020-b8c3` (User service setup)
- Next: `20260217-1000-c9d4` (Role-based access control)

---

## 📊 Session Stats

- Model used: Sonnet (implementation)
- Complexity score: 12 (COMPLEX)
- Plan mode: YES (used)
- Files created: 6
- Files modified: 0
- Lines added: ~500
- Failures prevented: 2
- Auto-commits: 1
```

---

### **3. Session Index (Master Registry)**

**File:** `~/.claude/memory/sessions/session-index.json`

**Purpose:** Fast lookup of all sessions by ID, tags, project, or files

```json
{
  "sessions": [
    {
      "session_id": "20260216-1430-a3f7",
      "timestamp": "2026-02-16T14:30:00",
      "project": "surgricalswale",
      "purpose": "Implement authentication feature",
      "tags": ["authentication", "jwt", "security", "user-service"],
      "duration_minutes": 45,
      "files_modified": 5,
      "status": "completed",
      "file_path": "sessions/surgricalswale/session-20260216-1430-a3f7.md"
    },
    {
      "session_id": "20260215-1020-b8c3",
      "timestamp": "2026-02-15T10:20:00",
      "project": "surgricalswale",
      "purpose": "Setup user service structure",
      "tags": ["setup", "user-service", "microservice"],
      "duration_minutes": 30,
      "files_modified": 8,
      "status": "completed",
      "file_path": "sessions/surgricalswale/session-20260215-1020-b8c3.md"
    }
  ],
  "total_sessions": 2,
  "projects": ["surgricalswale", "example-project-ui"],
  "last_updated": "2026-02-16T15:15:00"
}
```

**Auto-Update:** Daemon adds entry when session ends

---

### **4. Session Retrieval by ID**

**Command:**
```bash
# CLI command
python ~/.claude/memory/session-loader.py --session-id 20260216-1430-a3f7

# Or via Claude
User: "Load session 20260216-1430-a3f7"
Claude: Reads session file → Injects context → Ready to continue work
```

**Implementation:**
```python
#!/usr/bin/env python3
"""
Session Loader - Load session by ID
"""
import json
from pathlib import Path

def load_session(session_id: str):
    """Load session by ID"""

    # Read index
    index_file = Path.home() / ".claude" / "memory" / "sessions" / "session-index.json"
    with open(index_file, 'r') as f:
        index = json.load(f)

    # Find session
    session = next((s for s in index['sessions'] if s['session_id'] == session_id), None)

    if not session:
        print(f"❌ Session {session_id} not found")
        return None

    # Load session file
    session_file = Path.home() / ".claude" / "memory" / session['file_path']
    with open(session_file, 'r') as f:
        content = f.read()

    print(f"✅ Loaded session: {session_id}")
    print(f"   Project: {session['project']}")
    print(f"   Purpose: {session['purpose']}")
    print(f"   Tags: {', '.join(session['tags'])}")
    print(f"\n{content}")

    return content

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python session-loader.py SESSION_ID")
        sys.exit(1)

    load_session(sys.argv[1])
```

---

### **5. Session Search**

**Search by tags:**
```bash
python ~/.claude/memory/session-search.py --tags authentication jwt
# Returns: All sessions with these tags
```

**Search by project:**
```bash
python ~/.claude/memory/session-search.py --project surgricalswale
# Returns: All sessions for this project
```

**Search by file:**
```bash
python ~/.claude/memory/session-search.py --file AuthController.java
# Returns: All sessions that modified this file
```

**Search by date range:**
```bash
python ~/.claude/memory/session-search.py --date-from 2026-02-01 --date-to 2026-02-16
# Returns: Sessions in this date range
```

**Implementation:**
```python
def search_sessions(tags=None, project=None, file=None, date_from=None, date_to=None):
    """Search sessions by various criteria"""

    index_file = Path.home() / ".claude" / "memory" / "sessions" / "session-index.json"
    with open(index_file, 'r') as f:
        index = json.load(f)

    results = index['sessions']

    # Filter by tags
    if tags:
        results = [s for s in results if any(tag in s['tags'] for tag in tags)]

    # Filter by project
    if project:
        results = [s for s in results if s['project'] == project]

    # Filter by file (requires reading session content)
    if file:
        filtered = []
        for session in results:
            session_file = Path.home() / ".claude" / "memory" / session['file_path']
            content = session_file.read_text()
            if file in content:
                filtered.append(session)
        results = filtered

    # Filter by date range
    if date_from or date_to:
        from datetime import datetime
        results = [
            s for s in results
            if (not date_from or datetime.fromisoformat(s['timestamp']) >= datetime.fromisoformat(date_from))
            and (not date_to or datetime.fromisoformat(s['timestamp']) <= datetime.fromisoformat(date_to))
        ]

    return results
```

---

### **6. Auto-Start/End Integration**

**On Session Start (session-start.sh):**
```bash
#!/bin/bash
# Generate session ID
SESSION_ID=$(date +%Y%m%d-%H%M)-$(openssl rand -hex 2)

# Save to temp file for later reference
echo $SESSION_ID > ~/.claude/memory/.current-session-id

echo "🎯 Session Started: $SESSION_ID"
echo "   Project: $(basename $(pwd))"
```

**On Session End (session-auto-save-daemon.py):**
```python
# Read current session ID
session_id_file = Path.home() / ".claude" / "memory" / ".current-session-id"
session_id = session_id_file.read_text().strip()

# Generate session summary
summary = generate_session_summary(conversation)

# Save session file with ID
session_file = sessions_dir / project / f"session-{session_id}.md"
session_file.write_text(summary)

# Update session index
update_session_index(session_id, metadata)

# Log
print(f"✅ Session saved: {session_id}")
```

---

### **7. Session Linking (Related Sessions)**

**Track session relationships:**
```markdown
## 🔗 Related Sessions

**Parent:** `20260215-1020-b8c3` (User service setup)
**Children:**
- `20260217-1000-c9d4` (Role-based access control)
- `20260218-1400-e5f8` (Password reset feature)

**Related:**
- `20260216-1600-f7a9` (Product service auth integration)
```

**Benefits:**
- Navigate session history like Git commits
- Understand feature evolution
- Find related work quickly

---

### **8. Usage Examples**

**Example 1: Continue Previous Work**
```
User: "Load session 20260216-1430-a3f7"
Claude: [Loads session context]
        ✅ Session loaded: Implement authentication feature
        Files modified: AuthController.java, AuthService.java, ...
        Key decisions: JWT auth, 15-min access token, BCrypt hashing

        Ready to continue! What improvements do you need?

User: "Add password reset functionality"
Claude: [Already knows auth architecture from session]
        [Implements reset based on existing patterns]
```

**Token Savings:** ~5K tokens (no re-explaining auth flow!)

---

**Example 2: Search for Previous Work**
```
User: "Bhai authentication pe kaam kiye the kabhi?"
Claude: Searching sessions with tag 'authentication'...

        Found 3 sessions:
        1. 20260216-1430-a3f7 - Implement authentication feature
        2. 20260220-1100-h8k2 - Add OAuth2 support
        3. 20260225-1500-j9m3 - Fix token refresh bug

        Which one should I load?

User: "Pehla wala"
Claude: [Loads 20260216-1430-a3f7]
        Ready! This session implemented JWT auth. What next?
```

---

**Example 3: Reference Old Session for New Work**
```
User: "Session 20260216-1430-a3f7 jaise auth implement kiya tha,
       waise hi product-service me bhi karo"

Claude: [Loads session 20260216-1430-a3f7]
        ✅ Loaded authentication implementation pattern
        [Replicates same architecture in product-service]

        Same decisions applied:
        - JWT tokens (15 min access, 7 day refresh)
        - Secret Manager for keys
        - Spring Security config
        - BCrypt password hashing
```

**Consistency:** 100% (same patterns across services!)

---

### **9. Session ID CLI Commands**

**Available commands:**
```bash
# List all sessions
session list

# List sessions for project
session list --project surgricalswale

# Load session
session load 20260216-1430-a3f7

# Search sessions
session search --tags authentication jwt
session search --file AuthController.java
session search --date 2026-02-16

# Show session info
session info 20260216-1430-a3f7

# Link sessions
session link 20260216-1430-a3f7 --parent 20260215-1020-b8c3

# Export session
session export 20260216-1430-a3f7 --format json
```

---

### **10. Session Metadata Best Practices**

**Good tags:**
- Feature area: `authentication`, `user-management`, `products`
- Technology: `jwt`, `redis`, `postgresql`
- Service: `user-service`, `product-service`, `gateway`
- Type: `bugfix`, `feature`, `refactor`, `migration`

**Good purpose:**
- ✅ "Implement JWT authentication for user service"
- ✅ "Fix Redis connection pooling issue"
- ✅ "Migrate PostgreSQL to MongoDB"
- ❌ "Various changes" (too vague)
- ❌ "Updates" (not descriptive)

**Auto-tagging:**
Daemon extracts tags from:
- Files modified (controller → `api`, entity → `database`)
- Keywords in summary (`jwt` → tag: `jwt`)
- Service folder (`user-service/` → tag: `user-service`)

---

### **11. Session Statistics Dashboard**

**File:** `~/.claude/memory/sessions/session-stats.md`

```markdown
# Session Statistics

**Total Sessions:** 47
**Total Projects:** 5
**This Month:** 12 sessions
**Average Duration:** 38 minutes

---

## Top Tags (All Time)

1. authentication (8 sessions)
2. user-service (7 sessions)
3. jwt (6 sessions)
4. database (5 sessions)
5. bugfix (4 sessions)

---

## Recent Sessions

| ID | Date | Project | Purpose | Duration |
|----|------|---------|---------|----------|
| 20260216-1430-a3f7 | 2026-02-16 | surgricalswale | Implement auth | 45 min |
| 20260215-1020-b8c3 | 2026-02-15 | surgricalswale | User service setup | 30 min |
| 20260214-1600-c9d4 | 2026-02-14 | example-project-ui | Fix login UI | 20 min |

---

## Productivity Insights

**Most Productive Day:** Tuesday (12 sessions)
**Most Productive Hour:** 14:00-15:00 (8 sessions)
**Average Files/Session:** 4.2
**Longest Session:** 120 min (database migration)
**Shortest Session:** 10 min (quick bugfix)
```

**Update:** Auto-generated by daemon

---

---

## Git Auto-Commit Integration

### **Automatic Commit on Session End**

When session is auto-saved by daemon, **automatically commit and push all repos with changes**.

**Flow:**
```
Session Auto-Save Triggered
        ↓
Save session with ID
        ↓
🚨 Trigger Auto-Commit Enforcer
        ↓
Scan workspace for git repos
        ↓
For each repo with changes:
    - git add -A
    - git commit -m "..."
    - git push
        ↓
✅ Session saved + All repos committed
```

**Benefits:**
- ✅ Never lose work (auto-committed)
- ✅ Session + code always in sync
- ✅ Easy to rollback (session ID = commit)
- ✅ No manual commit needed

**Session Metadata Includes:**
```yaml
---
session_id: "20260216-1430-a3f7"
...
auto_committed: true
repos_committed: ["product-service", "user-service", "frontend"]
commit_hashes:
  - repo: "product-service"
    hash: "abc123def"
    message: "✓ Session: Implement JWT auth"
  - repo: "user-service"
    hash: "def456ghi"
    message: "✓ Session: Add user endpoints"
---
```

**Daemon Integration:**
- Located in: `session-auto-save-daemon.py`
- Function: `trigger_auto_commit()`
- Runs automatically after session save
- Timeout: 120 seconds
- Logs: `~/.claude/memory/logs/session-save-daemon.log`

---

## Status

**ACTIVE**: This policy provides persistent memory across sessions with unique ID tracking and auto-commit integration.
**Version**: 2.1.0 (Added Git Auto-Commit Integration)
**Created**: 2026-01-25
**Enhanced**: 2026-02-16 (Added Session IDs, Search, Retrieval, Auto-Commit)
**Privacy**: 100% local, 0% cloud
**Dependencies**: None (just markdown files + JSON index)
**Complexity**: Minimal (simple file read/write + JSON)
**User Control**: 100% (manual file management)

---

## Success Metrics

**Track:**
- Number of projects with summaries
- Number of sessions recorded
- Context load success rate
- User satisfaction (fewer re-explanations)

**Expected improvement:**
- Session startup context: 0% → 80%+ (huge win!)
- User re-explanation time: 50% reduction
- Claude accuracy on project context: 90%+
- Privacy preserved: 100% ✅
