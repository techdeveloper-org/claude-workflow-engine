# Auto-Sync Policies - Documentation

**Version:** 1.0.0
**Date:** 2026-02-17
**Purpose:** Automatically sync 3-Level Architecture policies from global memory system to Claude Workflow Engine

---

## 🎯 Problem Solved

**Before:** When you update 3-level architecture policies in global `~/.claude/memory/`, you had to manually:
1. Find which policies changed
2. Update file paths in Claude Workflow Engine
3. Fix path issues
4. Update PolicyChecker code
5. Test everything

**Now:** Just run one command and everything syncs automatically! ✅

---

## 🚀 Quick Start

```bash
# Navigate to Claude Workflow Engine
cd claude-workflow-engine

# Run auto-sync
python scripts/auto-sync-policies.py

# Restart Flask
python src/app.py
```

**That's it!** All policies synced with correct paths.

---

## 📋 What It Does

### **Step 1: Scan Global Memory System**
- Scans `~/.claude/memory/` for all policy files
- Checks 14 policy categories:
  - Level -1: Auto-Fix Enforcement
  - Level 1: Context Management, Session Management
  - Level 2: Standards Loader
  - Level 3: 12-Step Execution System (9 policies)
  - Infrastructure: Daemon Management

### **Step 2: Generate Definitions**
- Creates Python code for PolicyChecker
- Uses correct file paths automatically:
  - `utilities/` for daemon files
  - `01-sync-system/` for sync files
  - `02-standards-system/` for standards
  - `03-execution-system/` for execution files
  - `scripts/` for scripts
- Includes metadata (name, description, phase, level)

### **Step 3: Update PolicyChecker**
- Backs up original file (`.backup`)
- Replaces policy definitions
- Preserves other code

### **Step 4: Verify**
- Loads PolicyChecker
- Counts active/warning/error policies
- Shows results

---

## 🔧 How to Use

### **Scenario 1: After Global Policy Updates**

You updated global memory system with new policies:

```bash
# Just run auto-sync
python scripts/auto-sync-policies.py

# Restart Flask
python src/app.py
```

Dashboard will show updated policy count automatically!

### **Scenario 2: Regular Sync**

Run periodically to stay in sync:

```bash
# Weekly or when needed
python scripts/auto-sync-policies.py
```

### **Scenario 3: Troubleshooting**

If policies show errors in dashboard:

```bash
# Re-sync to fix paths
python scripts/auto-sync-policies.py

# Check detailed output
python test-policies-detailed.py
```

---

## 📊 Output Example

```
================================================================================
Auto-Sync Policies from Global Memory System
================================================================================

  Memory System: C:\Users\techd\.claude\memory

[1/4] Scanning global memory system...

  Found: 14 policies
  Missing: 0 policies

[2/4] Generating policy definitions...
  [OK] Auto-Fix Enforcement
  [OK] Context Management
  [OK] Session Management
  ... (all policies)

[3/4] Updating PolicyChecker...
  [OK] PolicyChecker updated
  [BACKUP] Original saved: policy_checker.py.backup

[4/4] Verifying sync...

  Total Policies: 14
  Active: 13
  Warning: 1

================================================================================
[SUCCESS] Policies synced successfully!
================================================================================
```

---

## 🛡️ Safety Features

1. **Automatic Backup**
   - Creates `.backup` file before changes
   - Can rollback if needed

2. **Verification**
   - Tests PolicyChecker after update
   - Shows status of all policies

3. **Error Handling**
   - Clear error messages
   - Won't break existing code

4. **Path Intelligence**
   - Automatically detects correct subdirectories
   - Handles Windows/Linux path differences

---

## 📁 Files Modified

**Updated by Script:**
- `src/services/monitoring/policy_checker.py` - Policy definitions

**Created by Script:**
- `src/services/monitoring/policy_checker.py.backup` - Backup

**Not Modified:**
- All other files remain unchanged

---

## 🔄 Integration with Global CLAUDE.md

**In Global CLAUDE.md (`~/.claude/CLAUDE.md`)**, add this reminder:

```markdown
## 🔄 Sync to Claude Workflow Engine

When you update 3-Level Architecture policies, sync to Claude Workflow Engine:

```bash
cd /path/to/claude-workflow-engine
python scripts/auto-sync-policies.py
```

This auto-updates PolicyChecker with correct file paths.
```

---

## 🧪 Testing

**After sync, verify:**

```bash
# Test monitoring services
python test-monitoring.py

# Test detailed policy status
python test-policies-detailed.py
```

**Expected Results:**
- Total Policies: 14
- Active: 13 or 14
- Errors: 0

---

## 🐛 Troubleshooting

### **Issue: "Global memory system not found"**

**Solution:** You're using local mode (./data/). Script will notify you.

### **Issue: "No policies found to sync"**

**Solution:** Check if `~/.claude/memory/` has policy files.

### **Issue: Policies show as "error" in dashboard**

**Solution:**
1. Re-run auto-sync
2. Check file paths in global system
3. Run test scripts for details

### **Issue: Need to rollback**

**Solution:**
```bash
cd src/services/monitoring
cp policy_checker.py.backup policy_checker.py
```

---

## 🎯 Best Practices

1. **Run after global updates**
   - After adding new policies to `~/.claude/memory/`
   - After reorganizing policy files
   - After major version updates

2. **Keep backups**
   - Script creates automatic backups
   - Save `.backup` files for safety

3. **Test after sync**
   - Always run test scripts
   - Check dashboard for policy count
   - Verify all policies active

4. **Document changes**
   - Keep changelog of policy updates
   - Note which policies added/removed

---

## 📖 Advanced Usage

### **Add New Policy Category**

Edit `scripts/auto-sync-policies.py`, add to `policy_files`:

```python
'your-new-policy': [
    'path/to/policy-file.py'
]
```

And `policy_metadata`:

```python
'your-new-policy': {
    'name': 'Your New Policy',
    'description': 'What it does',
    'phase': 5,
    'level': 'LEVEL 3'
}
```

Then run sync!

### **Custom Path Mapping**

If policy files move, update paths in `policy_files` dict.

---

## ✅ Summary

**One Command to Sync Everything:**

```bash
python scripts/auto-sync-policies.py
```

**What You Get:**
- ✅ All 14 policies auto-detected
- ✅ Correct file paths automatically
- ✅ PolicyChecker updated
- ✅ Backup created
- ✅ Verification done

**No more manual path fixes!** 🎉

---

**Created:** 2026-02-17
**Status:** ✅ WORKING
**Location:** `claude-workflow-engine/scripts/auto-sync-policies.py`
