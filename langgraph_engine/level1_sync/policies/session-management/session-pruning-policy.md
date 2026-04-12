# Long-term Session Memory Pruning Policy (v1.0)

**Status:** ACTIVE | **Priority:** MEDIUM | **Auto-Active:** PERIODIC

---

## 🎯 Purpose

**Keep session memory clean, fast, and manageable.**

Over time, projects accumulate many session files. Old sessions from months ago are rarely needed but still load at session start, causing:
- Slower session initialization
- Cluttered memory
- Irrelevant old context

This policy automatically archives old sessions while keeping recent ones active.

---

## 📋 Archival Rules

### Rule 1: Always Keep Recent Sessions
**Keep last 10 sessions active (regardless of age)**

Why? Recent sessions are most relevant, even if they're from last month.

### Rule 2: Archive Old Sessions
**Archive sessions older than 30 days (except last 10)**

Why? Sessions from months ago are rarely needed for current work.

### Rule 3: Never Archive Project Summary
**project-summary.md is NEVER archived**

Why? This is the cumulative summary that's always needed.

---

## 🗂️ Archive Structure

### Before Archival:
```
sessions/example-project-ui/
├── project-summary.md           (always kept)
├── session-2026-01-26-14-30.md  (recent - kept)
├── session-2026-01-25-10-15.md  (recent - kept)
├── session-2026-01-20-09-00.md  (recent - kept)
├── session-2025-12-15-16-45.md  (old - 42 days)
├── session-2025-11-28-11-20.md  (old - 59 days)
└── session-2025-11-10-08-30.md  (old - 77 days)
```

### After Archival:
```
sessions/example-project-ui/
├── project-summary.md           (always kept)
├── session-2026-01-26-14-30.md  (active)
├── session-2026-01-25-10-15.md  (active)
├── session-2026-01-20-09-00.md  (active)
└── archive/
    ├── 2025-12/
    │   └── sessions.tar.gz      (compressed: session-2025-12-15-16-45.md)
    └── 2025-11/
        └── sessions.tar.gz      (compressed: 2 sessions from Nov 2025)
```

**Benefits:**
- ✅ Recent sessions: Fast access (uncompressed)
- ✅ Old sessions: Archived (compressed, still recoverable)
- ✅ Faster loading: Only recent context loaded
- ✅ Cleaner structure: Old files organized by month

---

## ⚙️ How It Works

### Detection Phase:
```python
1. Find all session-*.md files in project
2. Parse dates from filenames (session-YYYY-MM-DD-HH-MM.md)
3. Sort by date (newest first)
4. Keep last 10 sessions (Rule 1)
5. From remaining sessions, mark those >30 days old for archival (Rule 2)
```

### Archival Phase:
```python
1. Group sessions by month (YYYY-MM)
2. Create archive/<YYYY-MM>/ directory
3. Compress sessions into sessions.tar.gz
4. Delete original files (safely - after successful compression)
5. Log archival action
```

### Recovery (if needed):
```bash
# Extract archived sessions
cd ~/.claude/memory/sessions/project-name/archive/2025-12
tar -xzf sessions.tar.gz
# Sessions extracted back to current directory
```

---

## 🔧 Usage

### Auto-Archive All Projects:
```bash
python ~/.claude/memory/archive-old-sessions.py
```

Output:
```
🗂️  Archiving sessions for 8 projects...
   Rules: Keep last 10 sessions, archive older than 30 days

📦 example-project-ui:
   Total sessions: 25
   Keeping active: 10
   Archiving: 15
  ✓ Archived: session-2025-12-15-16-45.md → 2025-12/sessions.tar.gz (age: 42 days)
  ✓ Archived: session-2025-11-28-11-20.md → 2025-11/sessions.tar.gz (age: 59 days)
  ...

✅ Archived 47 sessions successfully!
```

### Archive Specific Project:
```bash
python ~/.claude/memory/archive-old-sessions.py example-project-ui
```

### Preview Without Archiving (Dry Run):
```bash
python ~/.claude/memory/archive-old-sessions.py --dry-run
```

Output:
```
[DRY RUN] Would archive 15 sessions to 2025-12/
    - session-2025-12-15-16-45.md (age: 42 days)
    - session-2025-12-10-09-30.md (age: 47 days)
    ...

📊 Would archive 47 sessions
```

### View Statistics:
```bash
python ~/.claude/memory/archive-old-sessions.py --stats
```

Output:
```
📊 Session Memory Statistics
======================================================================

📁 example-project-ui
   Active sessions: 10
   Archivable (>30d, beyond last 10): 15
   Already archived: 32 (2.45 MB)
   Oldest active session: 2025-12-20 (37 days old)

📁 claude-memory-system
   Active sessions: 5
   Archivable (>30d, beyond last 10): 0
   Oldest active session: 2026-01-15 (11 days old)

======================================================================
📊 Total:
   Active sessions: 38
   Archivable sessions: 15
   Archived sessions: 32 (2.45 MB)
```

---

## 📅 When to Run

### Option 1: Manual (Recommended for Now)
Run when you notice sessions accumulating:
```bash
# Check stats first
python ~/.claude/memory/archive-old-sessions.py --stats

# If needed, archive
python ~/.claude/memory/archive-old-sessions.py
```

**Suggested frequency:** Monthly

### Option 2: Auto-Run on Session Start (Future)
Add to session start auto-load (in CLAUDE.md):
```bash
# After loading project context
# Run archival if last run was >7 days ago
```

### Option 3: Scheduled (Advanced)
Set up a cron job or scheduled task:
```bash
# Run every Sunday at 2 AM
0 2 * * 0 python ~/.claude/memory/archive-old-sessions.py
```

---

## 🔍 Integration Points

### 1. Session Start (Future Enhancement)
```bash
# In session-start auto-load
LAST_ARCHIVE=$(stat -c %Y ~/.claude/memory/.last-archive 2>/dev/null || echo 0)
NOW=$(date +%s)
DAYS_SINCE=$(( (NOW - LAST_ARCHIVE) / 86400 ))

if [ $DAYS_SINCE -gt 7 ]; then
    # Run archival silently in background
    python ~/.claude/memory/archive-old-sessions.py > /dev/null 2>&1 &
    touch ~/.claude/memory/.last-archive
fi
```

### 2. Manual Trigger
```bash
# User runs manually
python ~/.claude/memory/archive-old-sessions.py
```

### 3. Dashboard Integration
```bash
# Show stats in dashboard
bash ~/.claude/memory/dashboard.sh
# Should include archival statistics
```

---

## 📊 Monitoring

### Check Archival Logs:
```bash
tail -f ~/.claude/memory/logs/policy-hits.log | grep session-pruning
```

Output:
```
[2026-01-26 20:30:15] session-pruning | archived | example-project-ui | 15 sessions
[2026-01-26 20:30:15] session-pruning | archived-all | 47 total sessions
```

### View Archive Contents:
```bash
# List archived sessions
tar -tzf ~/.claude/memory/sessions/project-name/archive/2025-12/sessions.tar.gz
```

### Check Archive Size:
```bash
du -sh ~/.claude/memory/sessions/*/archive/
```

---

## 🛠️ Recovery & Restore

### Extract Specific Month:
```bash
cd ~/.claude/memory/sessions/example-project-ui/archive/2025-12
tar -xzf sessions.tar.gz

# Sessions extracted to current directory
# Move back to parent if needed
mv session-*.md ../../
```

### Extract All Archives:
```bash
cd ~/.claude/memory/sessions/example-project-ui/archive

for dir in */; do
    cd "$dir"
    tar -xzf sessions.tar.gz
    mv session-*.md ../../
    cd ..
done
```

### Restore Specific Session:
```bash
# Extract one file from archive
cd ~/.claude/memory/sessions/example-project-ui/archive/2025-12
tar -xzf sessions.tar.gz session-2025-12-15-16-45.md
mv session-2025-12-15-16-45.md ../../
```

---

## ⚠️ Important Notes

### Safety:
- ✅ Archives are compressed with tar.gz (industry standard)
- ✅ Original files deleted only AFTER successful compression
- ✅ project-summary.md is NEVER archived
- ✅ Dry run mode available for testing
- ✅ All actions logged

### Performance:
- **Before:** Loading 50+ old sessions = slow
- **After:** Loading 10 recent sessions = fast
- **Archive:** Rarely accessed, recoverable when needed

### Disk Space:
- Text files compress ~10:1 ratio
- 100 sessions (~50KB each) = 5MB → ~500KB archived
- Significant space savings over time

---

## 🧪 Examples

### Example 1: First-Time Archival
```bash
$ python ~/.claude/memory/archive-old-sessions.py --stats

📊 Session Memory Statistics
======================================================================
📁 example-project-ui
   Active sessions: 35
   Archivable (>30d, beyond last 10): 25
   Oldest active session: 2025-10-15 (103 days old)

$ python ~/.claude/memory/archive-old-sessions.py

🗂️  Archiving sessions for 8 projects...

📦 example-project-ui:
   Total sessions: 35
   Keeping active: 10
   Archiving: 25
  ✓ Archived: session-2025-10-15-10-30.md → 2025-10/sessions.tar.gz (age: 103 days)
  ...

✅ Archived 25 sessions successfully!

$ python ~/.claude/memory/archive-old-sessions.py --stats

📊 Session Memory Statistics
======================================================================
📁 example-project-ui
   Active sessions: 10
   Archivable (>30d, beyond last 10): 0
   Already archived: 25 (1.2 MB)
   Oldest active session: 2025-12-20 (37 days old)
```

### Example 2: Dry Run First
```bash
$ python ~/.claude/memory/archive-old-sessions.py --dry-run

[DRY RUN] Archiving sessions for 8 projects...

📦 example-project-ui:
   Total sessions: 35
   Keeping active: 10
   Archiving: 25
  [DRY RUN] Would archive 25 sessions to 2025-10/
    - session-2025-10-15-10-30.md (age: 103 days)
    - session-2025-10-20-14-15.md (age: 98 days)
    ...

📊 Would archive 25 sessions

# Review output, then run for real
$ python ~/.claude/memory/archive-old-sessions.py
```

### Example 3: Restore Old Session
```bash
# Need to reference old session from December
cd ~/.claude/memory/sessions/example-project-ui/archive/2025-12
tar -xzf sessions.tar.gz session-2025-12-15-16-45.md
cat session-2025-12-15-16-45.md  # Review content
```

---

## 📁 Files

- **Script:** `~/.claude/memory/archive-old-sessions.py`
- **Policy Doc:** `~/.claude/memory/session-pruning-policy.md`
- **Logs:** `~/.claude/memory/logs/policy-hits.log`
- **Archives:** `~/.claude/memory/sessions/<project>/archive/<YYYY-MM>/sessions.tar.gz`

---

## 🎯 Configuration

### Default Settings:
```python
ARCHIVE_AGE_DAYS = 30      # Archive sessions older than 30 days
KEEP_RECENT_COUNT = 10     # Always keep last 10 sessions
```

### Customize:
Edit `archive-old-sessions.py` and change:
```python
ARCHIVE_AGE_DAYS = 60      # Keep 60 days instead
KEEP_RECENT_COUNT = 20     # Keep last 20 sessions
```

---

**Version:** 1.0 | **Status:** ACTIVE | **Frequency:** Manual (Monthly Recommended)
