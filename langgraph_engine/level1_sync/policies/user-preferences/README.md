# 🎯 User Preferences

**Part of:** 🔵 Sync System

**Purpose:** Automatically learn and apply user preferences across sessions

---

## 📋 What This Does

- Track user preferences automatically (coding style, naming patterns, architectural choices)
- Learn from user feedback and corrections
- Apply learned preferences in new tasks
- Build user preference profile over time
- Reduce re-explanations by remembering choices

---

## 📁 Files in This Folder

### **Policies:**
- `user-preferences-policy.md` - Complete user preferences policy

### **Trackers:**
- `preference-auto-tracker.py` - Auto-track preferences (daemon)
- `preference-detector.py` - Detect preferences from conversations
- `track-preference.py` - Manual preference tracking

### **Loaders:**
- `load-preferences.py` - Load user preferences before execution

---

## 🎯 Usage

### **Load Preferences:**
```bash
python load-preferences.py --user techd
```

### **Track Preference:**
```bash
python track-preference.py --category "naming" --preference "snake_case for variables"
```

### **Start Auto-Tracker (Daemon):**
```bash
nohup python preference-auto-tracker.py > /dev/null 2>&1 &
```

---

## 📊 Preference Categories

| Category | Examples |
|----------|----------|
| **Naming** | camelCase vs snake_case, class naming patterns |
| **Architecture** | Layered architecture, package structure |
| **Error Handling** | Global handler vs local try-catch |
| **Testing** | Unit test patterns, mock preferences |
| **Documentation** | Comment style, JavaDoc preferences |
| **Code Style** | Brace placement, line length, formatting |

---

## ✅ Benefits

- **Token Savings:** 60-80% (no need to re-explain preferences)
- **Consistency:** Same style across all work
- **Speed:** Faster execution (no back-and-forth)
- **Personalization:** Code matches user expectations

---

**Location:** `~/.claude/memory/01-sync-system/user-preferences/`
