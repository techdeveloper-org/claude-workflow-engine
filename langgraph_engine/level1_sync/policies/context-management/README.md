# 📖 Context Management

**Part of:** 🔵 Sync System

**Purpose:** Monitor and optimize context usage for efficient token management

---

## 📋 What This Does

- Monitor context window usage (70%, 85%, 90% thresholds)
- Auto-cleanup when context fills up
- Cache frequently accessed files
- Extract context summaries
- Estimate context usage before operations
- Trigger cleanup when needed

---

## 📁 Files in This Folder

### **Monitoring:**
- `context-daemon.py` - Context monitoring daemon
- `context-monitor.py` - Context usage monitor (v2)
- `monitor-context.py` - Monitor context
- `monitor-and-cleanup-context.py` - Monitor + cleanup combined

### **Optimization:**
- `context-cache.py` - Context caching
- `context-monitor.py` - Estimate context usage
- `context-extractor.py` - Extract context info
- `auto-context-pruner.py` - Auto-prune context

### **Maintenance:**
- `update-context-usage.py` - Update usage stats
- `trigger-context-cleanup.sh` - Trigger cleanup

---

## 🎯 Usage

### **Monitor Context:**
```bash
python context-monitor.py --current-status
```

**Output:**
```
Context Usage: 45% (90K/200K tokens)
Status: 🟢 GREEN (Normal)
Action: None needed
```

### **Trigger Cleanup:**
```bash
bash trigger-context-cleanup.sh
```

### **Estimate Context:**
```bash
python context-monitor.py --file ProductService.java
```

---

## 📊 Context Thresholds

| Usage | Status | Action |
|-------|--------|--------|
| < 70% | 🟢 GREEN | Continue normally |
| 70-84% | 🟡 YELLOW | Use cache, offset/limit |
| 85-89% | 🟠 ORANGE | Session state, summaries |
| 90%+ | 🔴 RED | Force compact/clear |

---

## 🔧 Optimization Strategies

### **When Context > 70%:**
- Use cache for repeated files
- Read with offset/limit (not full file)
- Grep with head_limit
- Session state for large contexts

### **When Context > 85%:**
- Extract summaries instead of full content
- Session state (external file storage)
- Aggressive pruning

### **When Context > 90%:**
- Force session save
- Compact context
- Clear unrelated context

---

## 💾 Context Cache

**Location:** `~/.claude/memory/.cache/`

**What's Cached:**
- Files accessed 3+ times
- Project structure (tree output)
- Frequently used patterns

**Benefits:**
- 90% token savings on cached reads
- Faster responses
- Less API calls

---

## ✅ Benefits

- **Prevent Context Overflow:** Never hit 100% limit
- **Token Savings:** 40-60% through caching
- **Auto-Optimization:** No manual intervention
- **Smart Cleanup:** Keeps relevant, removes irrelevant

---

**Location:** `~/.claude/memory/01-sync-system/context-management/`
