# 📦 Session Management

**Part of:** 🔵 Sync System

**Purpose:** Manage session history with unique IDs for context reuse

---

## 📋 What This Does

- Save sessions with unique IDs (e.g., `20260216-1430-a3f7`)
- Load previous sessions by ID
- Search sessions by tags, project, files
- Auto-save sessions based on triggers
- Prune old sessions (archive after 90 days)
- Track session metadata (work done, commits, duration)

---

## 📁 Files in This Folder

### **Policies:**
- `session-memory-policy.md` - Complete session management policy (v2.1)

### **Session Operations:**
- `session-loader.py` - Load session by ID
- `session-search.py` - Search sessions (tags, project, file, date)
- `auto-save-session.py` - Auto-save session logic
- `protect-session-memory.py` - Session protection

### **Daemons:**
- `session-auto-save-daemon.py` - Auto-save daemon (every 10-30 min)
- `session-pruning-daemon.py` - Prune old sessions

### **Triggers & State:**
- `session-save-triggers.py` - Session save triggers
- `session-state.py` - Session state management

### **Session Start:**
- `session-start.sh` - Session start script
- `session-start-check.py` - Health check on start

### **Maintenance:**
- `archive-old-sessions.py` - Archive old sessions
- `session-pruning-policy.md` - Pruning policy

---

## 🎯 Usage

### **Load Session by ID:**
```bash
python session-loader.py load 20260216-1430-a3f7
```

### **Search Sessions:**
```bash
# By tags
python session-search.py --tags authentication jwt

# By project
python session-search.py --project surgricalswale

# By file
python session-search.py --file AuthController.java

# By date
python session-search.py --date-from 2026-02-01 --date-to 2026-02-16
```

### **List Recent Sessions:**
```bash
python session-loader.py list 20
```

---

## 📊 Session Structure

**File:** `sessions/{project}/session-{id}.md`

**Example:** `sessions/surgricalswale/session-20260216-1430-a3f7.md`

**Contains:**
```yaml
---
session_id: "20260216-1430-a3f7"
timestamp: "2026-02-16 14:30:00"
project: "surgricalswale"
purpose: "Implement authentication"
tags: ["authentication", "jwt", "security"]
duration: "45 minutes"
files_modified: 5
status: "completed"
auto_committed: true
repos_committed: ["product-service"]
commit_hashes:
  - repo: "product-service"
    hash: "abc123"
    message: "✓ Session: Implement JWT auth"
---
```

---

## ✅ Benefits

- **Reuse Context:** Load old session → No re-explanation needed
- **Replicate Patterns:** "Do like session XYZ" → Consistent code
- **Track History:** Know what was done when
- **Save Tokens:** 70-90% savings vs re-explaining

---

**Location:** `~/.claude/memory/01-sync-system/session-management/`
