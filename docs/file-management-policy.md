# File Management Policy (ALWAYS ACTIVE)

## System-Level Requirement

This is a **permanent rule** that applies to ALL file creation and documentation tasks.

---

## 🛡️ Protected Directories (NEVER CLEANUP/DELETE)

**These directories are PROTECTED from all cleanup operations:**

1. **Session Memory**: `~/.claude/memory/sessions/**`
   - Contains persistent project context
   - Auto-loaded at session start
   - NEVER auto-deleted by context cleanup
   - User manually manages (if needed)

2. **Policy Files**: `~/.claude/memory/*.md`
   - Core system policies
   - NEVER modified by auto-cleanup
   - Only updated via explicit user request

3. **User Configurations**: `~/.claude/settings*.json`
   - User settings and preferences
   - NEVER modified by cleanup

4. **Logs**: `~/.claude/memory/logs/**`
   - Policy execution logs
   - Manually archived if needed

**Why Protected:**
- Session memory provides persistent context across sessions
- Auto-cleanup would destroy user's project history
- User expects these to persist (like git history)

---

## Mandatory Rules

### 1. Temporary File Management
**Priority**: SYSTEM-LEVEL
**Status**: ALWAYS ACTIVE

#### Rules:
- **NEVER** create temporary or script files in the working directory
- **ALWAYS** use system temp directories:
  - **Windows**: `%TEMP%` or `$env:TEMP` (typically `C:\Users\<username>\AppData\Local\Temp`)
  - **Linux/Mac**: `/tmp` or `$TMPDIR`

#### What Qualifies as Temporary:
- Quick test scripts
- One-time utility scripts
- Temporary data processing files
- Build artifacts (unless project-specific)
- Debugging/testing files
- Any file not meant to be committed to version control

#### Implementation:
```bash
# Windows (PowerShell)
$tempFile = Join-Path $env:TEMP "script.py"

# Windows (CMD)
set TEMP_FILE=%TEMP%\script.bat

# Linux/Mac
TEMP_FILE=$(mktemp /tmp/script.XXXXXX)
```

#### Why This Matters:
- Keeps working directory clean
- Prevents accidental commits of temporary files
- Follows OS-level conventions for temp file management
- Automatic cleanup by OS temp directory policies

---

### 2. Documentation File Management
**Priority**: SYSTEM-LEVEL
**Status**: ALWAYS ACTIVE

#### Rules:
- **NEVER** create multiple separate markdown documentation files
- **ALWAYS** maintain a single `README.md` in the project root
- **UPDATE** the existing README instead of creating new MD files

#### Exceptions (ONLY create separate files for):
- `CHANGELOG.md` - Version history
- `CONTRIBUTING.md` - Contribution guidelines
- `LICENSE.md` - License information
- Project-specific docs explicitly requested by user

#### What Should Go in README:
- Project overview
- Setup instructions
- Usage examples
- API documentation
- Configuration details
- Troubleshooting
- Updates and changes

#### Why This Matters:
- Prevents documentation sprawl
- Single source of truth
- Easier to maintain
- Better user experience
- Reduces clutter

---

### 3. Large Documentation File Handling (INTELLIGENT STRATEGY)
**Priority**: SYSTEM-LEVEL
**Status**: ALWAYS ACTIVE
**Problem**: Large README files (500+ lines) waste tokens on full reads/writes

#### Size Thresholds:
- **< 500 lines**: Normal operation (read full, edit normally)
- **500-1000 lines**: ⚠️ WARNING - Use smart strategies below
- **1000+ lines**: 🚨 CRITICAL - MUST use intelligent handling

#### Intelligent Read Strategy (MANDATORY for 500+ line files):

**Step 1: Structure Read First**
```bash
# Read only first 100 lines to understand structure
Read file with limit=100
```
- Understand table of contents / section headers
- Identify where your target section is
- Cache this structure for the session

**Step 2: Targeted Section Read**
```bash
# Calculate target section line range
Read file with offset=200, limit=50
```
- Only read the specific section you need to update
- Don't read entire file unless absolutely necessary
- Use Grep to find section boundaries if needed

**Step 3: Use Edit Tool (NOT Write Tool)**
```python
# ❌ WRONG: Read full file + Write full file = 2X tokens
Read(file, full=True)  # 1000 lines = 3000 tokens
Write(file, content)   # 1000 lines = 3000 tokens
Total: 6000 tokens

# ✅ CORRECT: Targeted Edit
Read(file, offset=200, limit=50)  # 50 lines = 150 tokens
Edit(file, old_string, new_string) # Targeted = 200 tokens
Total: 350 tokens (94% savings!)
```

#### Smart Update Patterns:

**Pattern 1: Adding New Section (at end)**
```
1. Read last 50 lines only (to see structure)
2. Use Edit to append new section
3. No need to read full file
```

**Pattern 2: Updating Existing Section**
```
1. Read first 100 lines (structure)
2. Grep for section header
3. Read that section only (offset + limit)
4. Edit that specific section
```

**Pattern 3: Major Restructure**
```
1. Check if README > 1000 lines
2. If yes, consider docs/ folder exception
3. Ask user: "README is large (1200 lines). Split into:
   - README.md (overview + quick start)
   - docs/API.md
   - docs/SETUP.md
   Proceed with split?"
```

#### Section-Based Caching:
```
[CACHE:README.md:structure]
- Line 1-50: Project overview
- Line 51-200: Installation
- Line 201-400: API docs
- Line 401-600: Configuration
- Line 601-800: Troubleshooting
```
- Cache structure on first read
- Reuse cached structure for targeting sections
- Invalidate cache if file modified

#### Content Compaction Rules:

**For Old/Stable Features** (> 6 months old):
```markdown
❌ VERBOSE (100 lines):
## User Authentication
### Setup
1. Install passport...
2. Configure strategies...
[50 more lines of detail]

✅ COMPACT (10 lines):
## User Authentication
Uses Passport.js with JWT strategy.
- Setup: `npm install passport passport-jwt`
- Config: See `config/auth.js`
- Usage: Import `authMiddleware` in routes
```

**For New/Active Features** (< 1 month):
- Keep detailed documentation
- Full examples and explanations
- Comprehensive troubleshooting

#### Exception Clause (1000+ Lines):

When README exceeds 1000 lines:
1. **Propose split** to user (don't auto-create)
2. **Recommended structure**:
   ```
   README.md (200-300 lines max)
   ├── Project overview
   ├── Quick start
   ├── Links to detailed docs

   docs/
   ├── API.md
   ├── SETUP.md
   ├── ARCHITECTURE.md
   └── TROUBLESHOOTING.md
   ```
3. **Get user approval** before creating `docs/` folder
4. **Update README** with links to docs

#### Token Savings Example:

**Scenario**: Update API section in 800-line README

**Without Intelligent Strategy**:
```
Read full README: 800 lines × 3 tokens = 2400 tokens
Write full README: 800 lines × 3 tokens = 2400 tokens
Total: 4800 tokens
```

**With Intelligent Strategy**:
```
Read structure (first 100): 100 lines × 3 = 300 tokens
Grep for "## API": 10 tokens
Read API section (offset=200, limit=100): 100 × 3 = 300 tokens
Edit API section: ~200 tokens
Total: 810 tokens

Savings: 83%! (3990 tokens saved)
```

#### Enforcement Rules:

**MUST USE intelligent strategy when**:
- README > 500 lines
- Microservices projects (likely large docs)
- Multi-file updates where README also needs update
- Long session with repeated README access

**HOW TO CHECK FILE SIZE**:
```bash
# Before reading large file
wc -l README.md  # Check line count
# If > 500, use intelligent strategy
```

**DECISION TREE**:
```
README update needed
    ↓
Check line count
    ↓
< 500 lines → Normal read/edit
    ↓
500-1000 lines → Smart strategy (structure + targeted)
    ↓
1000+ lines → Propose docs/ split to user
```

#### Integration with Context Management:

This strategy works with `context-management-core`:
- **Structure caching** leverages intelligent caching feature
- **Targeted reads** reduce context bloat
- **Smart edits** prevent token waste
- **Compaction rules** align with context cleanup

**Combined Benefits**:
- Context stays lean (no 1000-line file in memory)
- Token savings compound (50-70% from caching + 80-90% from targeted edits)
- Long sessions stay efficient (README structure cached, not full content)

---

## Execution Flow

### Before Creating ANY File:

1. **Ask Yourself**:
   - Is this temporary? → Use system temp directory
   - Is this documentation? → Update README.md
   - Is this permanent project code? → Use proper project structure

2. **Check Existing Files**:
   - Does README.md already exist? → Update it
   - Are there temp files in working directory? → Clean them up
   - Can I consolidate multiple MD files? → Do it

3. **Get Location**:
   ```bash
   # Windows
   echo %TEMP%

   # Linux/Mac
   echo $TMPDIR
   ```

---

## Enforcement

### When User Asks to Create Script/Temp File:
- ✅ Create it in system temp directory
- ✅ Inform user of the location
- ❌ Do NOT create it in working directory

### When User Asks for Documentation:
- ✅ Check if README.md exists
- ✅ Update existing README
- ✅ Ask user before creating separate MD files
- ❌ Do NOT auto-create multiple MD files

### Proactive Cleanup:
- If you see temp files in working directory → Suggest moving to temp
- If you see multiple MD files → Suggest consolidation
- Keep working directory minimal and organized

---

## Integration with Other Skills

This policy applies ALONGSIDE core skills:
1. context-management-core (FIRST)
2. model-selection-core (SECOND)
3. **file-management-policy** (THROUGHOUT EXECUTION)
4. All other skills (AFTER)

---

## Example Scenarios

### Scenario 1: User Asks for Test Script
```
User: "Create a quick Python script to test this API"

❌ WRONG:
Write file to: ./test_api.py

✅ CORRECT:
Write file to: /tmp/test_api.py (Linux)
Write file to: %TEMP%\test_api.py (Windows)
Inform user: "Script created at [location]"
```

### Scenario 2: User Asks for Documentation
```
User: "Document this new feature"

❌ WRONG:
Create new file: FEATURE_DOCS.md

✅ CORRECT:
Update existing: README.md
Add section: ## New Feature Documentation
```

### Scenario 3: Previous Session Created Multiple MD Files
```
Situation: Last session created API_DOCS.md, SETUP.md, USAGE.md

✅ PROACTIVE ACTION:
1. Read all MD files
2. Consolidate into README.md
3. Delete redundant files
4. Inform user of cleanup
```

### Scenario 4: Updating Large README (850 lines)
```
User: "Add new API endpoint docs to README"

❌ WRONG (Token Waste):
Read README.md (full 850 lines) → 2550 tokens
Write README.md (full) → 2550 tokens
Total: 5100 tokens

✅ CORRECT (Intelligent):
wc -l README.md → 850 lines (trigger smart strategy)
Read first 100 lines (structure) → 300 tokens
Grep "## API Documentation" → 10 tokens
Read offset=300, limit=100 → 300 tokens
Edit (targeted section) → 200 tokens
Total: 810 tokens (84% savings!)
```

### Scenario 5: README Exceeds 1000 Lines
```
User: "Update installation docs"
Check: README.md is 1200 lines

✅ PROACTIVE ACTION:
1. Alert user: "README is 1200 lines, consider splitting"
2. Propose structure:
   - README.md (overview + quick start)
   - docs/INSTALLATION.md
   - docs/API.md
   - docs/CONFIGURATION.md
3. Ask permission before creating docs/ folder
4. If approved: Split and update
5. If declined: Use targeted edit strategy
```

---

## Status

**ACTIVE**: This policy is permanent and applies to all sessions.
**Version**: 2.0.0
**Created**: 2026-01-22
**Last Updated**: 2026-01-22 (Added intelligent large file handling strategy)

---

## Quick Reference Card

| Situation | Action |
|-----------|--------|
| Creating temp/test script | Use `$TMPDIR` or `%TEMP%` |
| Creating documentation | Update README.md |
| Multiple MD files exist | Consolidate into README |
| User wants separate MD | Ask permission first |
| Temp files in working dir | Suggest cleanup |
| Documentation scattered | Suggest consolidation |
| **README < 500 lines** | Normal read/edit |
| **README 500-1000 lines** | Smart strategy: structure + targeted edit |
| **README 1000+ lines** | Propose docs/ split, get approval |
| Updating large README | Check size first, use targeted edit |
| Repeated README access | Cache structure (not full content) |

---

**Remember**: A clean working directory = better project hygiene!
