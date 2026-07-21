# Global User Preferences Policy (v1.0)

**Status:** ACTIVE | **Priority:** HIGH | **Auto-Active:** YES

---

## 🎯 Purpose

**Learn from user's repeated choices and stop asking the same questions.**

After a user makes the same choice 3+ times across sessions, automatically save it as a global preference and apply it without asking again.

---

## 📋 What Gets Tracked

### Technology Preferences
- `api_style` - REST, GraphQL, gRPC, etc.
- `testing` - skip, full_coverage, unit_only, integration_only
- `ui_theme` - dark, light, auto
- `auth_method` - JWT, OAuth, session, basic
- `database` - postgres, mysql, mongodb, etc.

### Language Preferences
- `backend` - python, java, node, go, etc.
- `frontend` - react, angular, vue, vanilla
- `scripting` - python, bash, powershell

### Workflow Preferences
- `commit_style` - conventional, descriptive, simple
- `plan_mode` - always_ask, auto_enter, skip
- `phased_execution` - preferred, ask, avoid
- `documentation` - minimal, comprehensive, inline

---

## ⚙️ How It Works

### Learning Phase (First 3 Times)

**Scenario:** User chooses "skip tests" for the 1st time

**Claude's Action:**
1. Ask user: "Skip tests?"
2. User chooses: "Yes"
3. **Track it:**
   ```bash
   python ~/.claude/memory/track-preference.py testing skip
   ```
4. Output: `📊 Choice recorded: testing = skip (1/3 times observed)`

**Scenario:** User chooses "skip tests" for the 2nd time

**Claude's Action:**
1. Ask user: "Skip tests?"
2. User chooses: "Yes"
3. **Track it:**
   ```bash
   python ~/.claude/memory/track-preference.py testing skip
   ```
4. Output: `📊 Choice recorded: testing = skip (2/3 times observed)`

**Scenario:** User chooses "skip tests" for the 3rd time

**Claude's Action:**
1. Ask user: "Skip tests?"
2. User chooses: "Yes"
3. **Track it:**
   ```bash
   python ~/.claude/memory/track-preference.py testing skip
   ```
4. Output: `✅ Preference learned: testing = skip (Observed 3x, threshold: 3)`

**Preference is now saved globally!**

---

### Application Phase (4th Time Onwards)

**Scenario:** User works on a new task that involves testing

**Claude's Action:**
1. **Check preference:**
   ```bash
   python ~/.claude/memory/load-preferences.py testing
   ```
2. Result: `skip`
3. **Auto-apply** without asking:
   - Claude: "Skipping tests (based on your preference)"
   - Proceeds without prompting user
4. **Log it:**
   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] user-preferences | applied | testing=skip" >> ~/.claude/memory/logs/policy-hits.log
   ```

**User can always override:** "Actually, write tests this time"

---

## 🔄 Integration Points

### When to Track Preferences (AUTO)

**1. After User Consultation (Proactive Consultation Policy)**
```bash
# User chose REST over GraphQL
python ~/.claude/memory/track-preference.py api_style REST
```

**2. After Test Policy Decision (Test Case Policy)**
```bash
# User chose to skip tests
python ~/.claude/memory/track-preference.py testing skip
```

**3. After Plan Mode Decision (Planning Intelligence)**
```bash
# User chose to enter plan mode
python ~/.claude/memory/track-preference.py plan_mode enter
```

**4. After Technology Choice**
```bash
# User chose Python for backend
python ~/.claude/memory/track-preference.py backend python
```

**5. After Workflow Choice**
```bash
# User chose conventional commits
python ~/.claude/memory/track-preference.py commit_style conventional
```

---

### When to Apply Preferences (AUTO)

**1. Before Asking User Questions**
```bash
# Check if testing preference exists
PREF=$(python ~/.claude/memory/load-preferences.py testing 2>/dev/null)

if [ -n "$PREF" ]; then
    # Preference exists - auto-apply
    echo "Skipping tests (based on your preference: $PREF)"
    # Log it
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] user-preferences | applied | testing=$PREF" >> ~/.claude/memory/logs/policy-hits.log
else
    # No preference - ask user
    # (Use AskUserQuestion tool)
fi
```

**2. During Technology Decisions**
```bash
# Check if API style preference exists
PREF=$(python ~/.claude/memory/load-preferences.py api_style 2>/dev/null)

if [ -n "$PREF" ]; then
    # Auto-select based on preference
    echo "Using $PREF API (based on your preference)"
else
    # Ask user
fi
```

**3. During Workflow Decisions**
```bash
# Check if plan mode preference exists
PREF=$(python ~/.claude/memory/load-preferences.py plan_mode 2>/dev/null)

if [ -n "$PREF" ] && [ "$PREF" = "always_enter" ]; then
    # Auto-enter plan mode
    echo "Entering plan mode (based on your preference)"
else
    # Use standard planning intelligence rules
fi
```

---

## 📊 Monitoring

### View All Preferences
```bash
python ~/.claude/memory/load-preferences.py
```

Output:
```
🎯 Global User Preferences
============================================================

📱 Technology Preferences:
  ✓ api_style: REST
  ✓ testing: skip
  - ui_theme: (not set)
  - auth_method: (not set)
  - database: (not set)

💻 Language Preferences:
  ✓ backend: python
  ✓ frontend: typescript
  - scripting: (not set)

⚙️  Workflow Preferences:
  ✓ commit_style: conventional
  ✓ plan_mode: always_ask
  - phased_execution: (not set)
  - documentation: (not set)

📊 Statistics:
  Total preferences learned: 5
  Learning threshold: 3
  Last updated: 2026-01-26 14:32:15
```

### Check Specific Preference
```bash
python ~/.claude/memory/load-preferences.py testing
# Output: skip
```

### Check If Preference Exists
```bash
python ~/.claude/memory/load-preferences.py --has testing
# Output: yes
```

### View Learning History
```bash
tail -f ~/.claude/memory/logs/policy-hits.log | grep user-preferences
```

---

## 🛠️ Manual Override

### Reset a Preference
Edit `~/.claude/memory/user-preferences.json`:
```json
{
  "technology_preferences": {
    "testing": null  // Reset to null
  }
}
```

### Change Learning Threshold
```json
{
  "metadata": {
    "learning_threshold": 5  // Require 5 observations instead of 3
  }
}
```

### Add New Preference Category
1. Add to JSON structure:
```json
{
  "technology_preferences": {
    "my_new_category": null
  },
  "learning_data": {
    "my_new_category": []
  }
}
```
2. Track it: `python track-preference.py my_new_category my_value`

---

## ⚠️ Important Rules

### Always Track Choices
**MANDATORY:** After user makes a decision on a tracked category, ALWAYS track it:
```bash
python ~/.claude/memory/track-preference.py <category> <value>
```

### Always Check Before Asking
**MANDATORY:** Before asking user a question about a tracked category, ALWAYS check if preference exists:
```bash
PREF=$(python ~/.claude/memory/load-preferences.py <category> 2>/dev/null)
```

### Always Log Application
**MANDATORY:** When applying a preference, ALWAYS log it:
```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] user-preferences | applied | category=value" >> ~/.claude/memory/logs/policy-hits.log
```

### User Can Always Override
- Preferences are defaults, not restrictions
- If user explicitly requests different choice, honor it and track the new choice
- Example: User has `testing=skip` but says "write tests this time" → Write tests AND track new choice

---

## 🎯 Execution Flow

```
Decision Point (e.g., "Should I skip tests?")
  ↓
Check for preference:
  python load-preferences.py testing
  ↓
┌─────────────────────┬─────────────────────┐
│ Preference EXISTS   │ No Preference       │
│                     │                     │
│ 1. Auto-apply       │ 1. Ask user         │
│ 2. Log application  │ 2. Track choice     │
│ 3. Proceed          │ 3. Proceed          │
└─────────────────────┴─────────────────────┘
```

---

## 🧪 Examples

### Example 1: Testing Preference

**Session 1:**
```
Claude: "Skip tests? (Recommended)"
User: "Yes"
Claude: [Tracks] python track-preference.py testing skip
        Output: 📊 Choice recorded: testing = skip (1/3 times observed)
```

**Session 2:**
```
Claude: "Skip tests? (Recommended)"
User: "Yes"
Claude: [Tracks] python track-preference.py testing skip
        Output: 📊 Choice recorded: testing = skip (2/3 times observed)
```

**Session 3:**
```
Claude: "Skip tests? (Recommended)"
User: "Yes"
Claude: [Tracks] python track-preference.py testing skip
        Output: ✅ Preference learned: testing = skip
```

**Session 4+:**
```
Claude: [Checks] python load-preferences.py testing
        Result: skip
Claude: "Skipping tests (based on your preference)"
        [Logs application]
        [Proceeds without asking]
```

---

### Example 2: API Style Preference

**First 3 times:** User always chooses REST over GraphQL
**4th time onwards:**
```
Claude: [Checks] python load-preferences.py api_style
        Result: REST
Claude: "Using REST API (based on your preference)"
```

---

### Example 3: Override Preference

**User has testing=skip preference**

```
User: "Implement user authentication, and write tests this time"
Claude: "Got it! I'll write tests for authentication."
        [Tracks] python track-preference.py testing full_coverage
        [This will eventually learn the new preference if repeated]
```

---

## 📁 Files

- **Storage:** `~/.claude/memory/user-preferences.json`
- **Track Script:** `~/.claude/memory/track-preference.py`
- **Load Script:** `~/.claude/memory/load-preferences.py`
- **Helper:** `~/.claude/memory/apply-preference.sh`
- **Policy Doc:** `~/.claude/memory/user-preferences-policy.md`

---

**Version:** 1.0 | **Status:** ACTIVE | **Auto-Active:** YES
