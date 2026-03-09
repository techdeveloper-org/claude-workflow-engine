# Context-Read Enforcement (Step 3.0 - Pre-Flight)

## The Policy

**"Read README, SYSTEM_REQUIREMENTS_SPECIFICATION, and CLAUDE.md before writing code"**

This policy ensures all team members understand the project scope, requirements, and custom instructions before making changes.

---

## File Names (EXACT - Case Sensitive)

You MUST use these exact names. No variants, no substitutions:

| Required File | Exact Name | Purpose |
|---|---|---|
| 1️⃣ **README** | `README.md` | Project overview, setup, architecture |
| 2️⃣ **Requirements** | `SYSTEM_REQUIREMENTS_SPECIFICATION.md` | System requirements, constraints, scope |
| 3️⃣ **Instructions** | `CLAUDE.md` | Claude-specific instructions, policies, conventions |

---

## Enforcement Rules

### ✅ Enforcement APPLIES (All 3 Files Present)
- Project has `README.md` ✅
- Project has `SYSTEM_REQUIREMENTS_SPECIFICATION.md` ✅  
- Project has `CLAUDE.md` ✅

→ **Result:** `is_new_project = False` → Enforcement ACTIVE
→ **Behavior:** Must read context before Writing/Editing/Coding

### ❌ Enforcement SKIPPED (Any File Missing)
- Missing `README.md` ❌
- Missing `SYSTEM_REQUIREMENTS_SPECIFICATION.md` ❌
- Missing `CLAUDE.md` ❌

→ **Result:** `is_new_project = True` → Enforcement SKIPPED
→ **Behavior:** New project, free to code (no context to read)

---

## How It Works

### Flow
```
1. Every prompt → UserPromptSubmit hook fires
   ↓
2. 3-level-flow.py runs (Level 1-3 checks)
   ↓
3. context-reader.py runs (Level 3.0 Pre-Flight)
   ├─ Looks for: README.md, SYSTEM_REQUIREMENTS_SPECIFICATION.md, CLAUDE.md
   ├─ If ALL 3 exist: reads them, sets is_new_project=False
   ├─ If any missing: is_new_project=True
   └─ Creates flag: ~/.claude/memory/flags/.context-read-{SESSION}-{PID}.json
   
4. Before tool call → PreToolUse hook fires
   ↓
5. pre-tool-enforcer.py checks flag
   ├─ If is_new_project=True: ALLOW writes (new project)
   ├─ If is_new_project=False: (will BLOCK in v2)
   └─ Creates flag with is_new_project value
```

---

## For New Projects

If you're creating a NEW project without these 3 files:
1. Start coding freely (enforcement skipped)
2. When ready, create all 3 files:
   - `README.md` - Describe your project
   - `SYSTEM_REQUIREMENTS_SPECIFICATION.md` - Document requirements
   - `CLAUDE.md` - Add custom instructions (if needed)
3. Next prompt: enforcement activates
4. Future: must read all 3 before coding

---

## For Existing Projects

If your project has all 3 files:
1. **First Prompt:** context-reader scans and reads all 3
2. **Before Coding:** Flag is created showing all 3 are present
3. **Pre-Tool Check:** Enforcement verifies context was read
4. **Result:** Permission to code granted ✅

---

## Troubleshooting

### "Enforcement is blocking me but I'm in a new project"
Check: Does your project have all 3 files?
- If NO → Enforcement should be skipped (is_new_project=True)
- If YES → Check flag file: `~/.claude/memory/flags/.context-read-*`

### "I have the files but enforcement says they're missing"
Check file names EXACTLY:
- ✅ `README.md` (NOT `readme.md`, `README`, `readme.markdown`)
- ✅ `CLAUDE.md` (NOT `claude.md`, `Claude.md`, `CLAUDE`)
- ✅ `SYSTEM_REQUIREMENTS_SPECIFICATION.md` (NOT `SRS.md`, `SRS`, etc.)

**File names are case-sensitive on Linux/Mac!**

---

## Implementation Status

| Feature | Status | Details |
|---|---|---|
| Flag Creation | ✅ Done | context-reader.py creates `.context-read-{SESSION}-{PID}.json` |
| File Detection | ✅ Done | Exact name matching, all 3 required |
| Smart Logic | ✅ Done | is_new_project detection working |
| Enforcement Blocking | ⏳ V2 | Infrastructure ready, actual blocking pending |
| Error Messages | ⏳ V2 | Will show why enforcement is blocking |

---

## Questions?

See: `CLAUDE.md` (in project root) → Step 3.0 Pre-Flight
