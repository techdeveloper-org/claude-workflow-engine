# Common Failures Prevention (Self-Learning Knowledge Base)

## Metadata
- **Version**: 1.0.0
- **Status**: ALWAYS ACTIVE
- **Priority**: SYSTEM-LEVEL (Applied DURING execution planning)
- **Type**: Self-Learning Knowledge Base
- **Last Updated**: 2026-01-22

---

## Purpose

This is a **self-learning failure prevention system** that:
- 🧠 Learns from past failures (yours and common patterns)
- 🛡️ Prevents repeating same mistakes
- ⚡ Saves tokens by avoiding error → retry cycles
- 🎯 Improves over time as new patterns are discovered
- 🔄 Self-updating (new failures automatically logged)

**Core Principle**: "Fool me once, shame on you. Fool me twice, shame on me."

After a failure happens once, it should NEVER happen again due to the same reason.

---

## How It Works

### Execution Flow

```
Before executing any command/tool:
    ↓
1. Check if pattern matches known failure
    ↓
2. If match found:
   ├─ Use solution from KB
   ├─ Execute corrected version
   └─ Log: "Prevented [failure type] using KB"
    ↓
3. If no match:
   ├─ Execute as planned
   ├─ If succeeds → Continue
   └─ If fails → Log failure + Add pattern to KB
         ↓
    Next time → Will be prevented
```

### Pattern Matching Algorithm

```python
def check_failure_kb(action):
    for pattern in failure_kb:
        if matches(action, pattern.signature):
            if pattern.confidence > 0.7:
                return pattern.solution
    return None  # Execute as-is
```

---

## Known Failure Patterns (Seed Knowledge Base)

### Category 0: Python Encoding Errors (CRITICAL - Windows)

#### Pattern 0.1: Unicode Characters in Python on Windows
```yaml
Signature: "UnicodeEncodeError: 'charmap' codec can't encode character"
Platform: Windows (sys.platform == 'win32')
Root Cause: Unicode characters (emojis, special symbols) in Python print() statements
Frequency: EXTREMELY HIGH (1000+ occurrences reported)
Confidence: 100%
Severity: CRITICAL (breaks execution completely)

Why This Happens:
  - Windows console uses cp1252 encoding (NOT UTF-8)
  - Python print() uses console encoding by default
  - Unicode chars (📝, ✅, 🚨, etc.) cannot be encoded in cp1252
  - Results in: UnicodeEncodeError and script crash

Prevention Strategy:
  Before writing ANY Python code on Windows:
    1. Check platform: if sys.platform == 'win32'
    2. Scan code for Unicode characters (regex: [\u0080-\uffff])
    3. If found: REPLACE with ASCII equivalents
    4. Forbidden chars: All emojis, →, ✓, ✗, •, ★, etc.
    5. Allowed: ASCII only (0-127): [OK], [ERROR], [INFO], ->

  Auto-Fix Strategy:
    📝 → [LOG]
    ✅ → [OK]
    ❌ → [ERROR]
    🚨 → [ALERT]
    🔍 → [SEARCH]
    📊 → [CHART]
    🎯 → [TARGET]
    → (arrow) → ->
    ✓ (checkmark) → [CHECK]
    • (bullet) → -

Example:
  ❌ WRONG (Windows will crash):
    print(f"✅ Task completed successfully")
    print(f"📝 Logging session data")
    print(f"🚨 Critical error occurred")

  ✅ RIGHT (Windows-safe):
    print(f"[OK] Task completed successfully")
    print(f"[LOG] Logging session data")
    print(f"[ALERT] Critical error occurred")

Detection Keywords:
  - Error: "UnicodeEncodeError"
  - Error: "charmap codec"
  - Error: "can't encode character"
  - Context: Windows system (.py files)

Pre-Execution Check:
  def check_unicode_in_python_windows():
      if sys.platform != 'win32':
          return True  # Unix/Linux can handle Unicode

      # Read Python file
      with open(file_path, 'r', encoding='utf-8') as f:
          content = f.read()

      # Check for Unicode characters
      import re
      unicode_chars = re.findall(r'[\u0080-\uffff]', content)

      if unicode_chars:
          return {
              'status': 'FAIL',
              'reason': 'Unicode characters found in Python file on Windows',
              'chars': set(unicode_chars),
              'fix': 'Replace Unicode with ASCII equivalents'
          }

      return {'status': 'PASS'}

Permanent Solution:
  1. Add to global CLAUDE.md: "NEVER use Unicode in Python on Windows"
  2. Add to pre-execution checker
  3. Add to failure prevention daemon
  4. Make it BLOCKING (cannot write Unicode in .py files)

Note: This is NOT a workaround (export PYTHONIOENCODING=utf-8)
      This is FIXING the root cause (don't use Unicode at all)
```

---

### Category 1: Bash Command Errors

#### Pattern 1.1: Windows Commands in Git Bash/Linux
```yaml
Signature: "bash: del: command not found"
Platform: Linux, Git Bash, WSL
Root Cause: Windows command used in Unix-like shell
Frequency: Very High (9/10 Windows users make this)
Confidence: 100%

Prevention Strategy:
  Before execution: Check if command in ['del', 'copy', 'move', 'cls', 'dir']
  If platform is Unix-like:
    - del → rm
    - copy → cp
    - move → mv
    - cls → clear
    - dir → ls
  Auto-translate and inform user

Example:
  ❌ Wrong: bash -c "del file.txt"
  ✅ Right: bash -c "rm file.txt"
  Message: "Converted 'del' to 'rm' for Unix compatibility"
```

#### Pattern 1.2: Missing Quotes in Paths with Spaces
```yaml
Signature: "No such file or directory" + path contains spaces
Platform: All
Root Cause: Unquoted file paths with spaces
Frequency: High (7/10)
Confidence: 95%

Prevention Strategy:
  Before execution: Check if path contains spaces
  If yes and not quoted:
    - Wrap in double quotes
    - Inform user

Example:
  ❌ Wrong: cd C:\Program Files\App
  ✅ Right: cd "C:\Program Files\App"
  Message: "Added quotes for path with spaces"
```

#### Pattern 1.3: Using '-i' Flag in Non-Interactive Context
```yaml
Signature: "git rebase -i" or "git add -i" in bash tool
Platform: All
Root Cause: Interactive commands don't work in non-interactive shells
Frequency: Medium (4/10)
Confidence: 100%

Prevention Strategy:
  Before execution: Check if command has '-i' flag
  If yes:
    - Block execution
    - Suggest alternative approach
    - Example: "git rebase -i" → use git rebase with specific commits instead

Example:
  ❌ Wrong: git rebase -i HEAD~3
  ✅ Right: git rebase --onto <base> <commit1> <commit2>
  Message: "Interactive flag '-i' not supported in non-interactive shell"
```

---

### Category 2: Edit Tool Errors

#### Pattern 2.1: String Not Found (Whitespace Mismatch)
```yaml
Signature: "String to replace not found" + file recently read
Platform: All
Root Cause: Line number prefix or whitespace differences
Frequency: Very High (8/10 when editing from Read output)
Confidence: 90%

Prevention Strategy:
  Before Edit execution:
    1. Strip line number prefixes from old_string (format: "  123→")
    2. Check for exact match in file
    3. If not found, try fuzzy match (ignore leading/trailing whitespace)
    4. If still not found, suggest using Grep to find exact string

Warning Signs:
  - old_string starts with spaces + number + arrow (line prefix)
  - old_string has mixed tabs/spaces

Example:
  ❌ Wrong: old_string = "     1→function foo() {"
  ✅ Right: old_string = "function foo() {"
  Message: "Stripped line number prefix for accurate matching"
```

#### Pattern 2.2: String Not Unique
```yaml
Signature: "old_string not unique in file"
Platform: All
Root Cause: Attempting to replace text that appears multiple times
Frequency: Medium (5/10)
Confidence: 100%

Prevention Strategy:
  Before Edit execution:
    1. Check if old_string appears multiple times
    2. If yes, include more surrounding context to make unique
    3. OR suggest using replace_all=true if all occurrences should change

Example:
  ❌ Wrong: old_string = "return true"
  ✅ Right: old_string = "function validate() {\n    return true\n}"
  Message: "Expanded context to make string unique"
```

---

### Category 3: File Operation Errors

#### Pattern 3.1: Write Without Prior Read
```yaml
Signature: "Write tool error: must read file first"
Platform: All
Root Cause: Attempting to overwrite existing file without reading it first
Frequency: Medium (6/10 for existing files)
Confidence: 100%

Prevention Strategy:
  Before Write execution:
    1. Check if file exists
    2. If exists and not in recent reads → Read it first
    3. Then proceed with Write

Example:
  ❌ Wrong: Write(existing_file.txt, content)
  ✅ Right: Read(existing_file.txt) → Write(existing_file.txt, content)
  Message: "Read file first before overwriting (safety check)"
```

#### Pattern 3.2: Large File Read Without Limit
```yaml
Signature: "File too large" or context overflow after full read
Platform: All
Root Cause: Reading 1000+ line file completely
Frequency: Medium (from file-management-policy)
Confidence: 90%

Prevention Strategy:
  Before Read execution:
    1. Check file size (wc -l or equivalent)
    2. If > 500 lines:
       - Read first 100 lines (structure)
       - Use targeted reads with offset+limit
    3. Apply file-management-policy intelligent strategy

Example:
  ❌ Wrong: Read(large_readme.md)
  ✅ Right: wc -l → Read(first 100) → Grep(section) → Read(offset, limit)
  Message: "Large file detected. Using intelligent read strategy."
```

---

### Category 4: Tool-Specific Patterns

#### Pattern 4.1: Glob Pattern Syntax Error
```yaml
Signature: Glob returns empty when files should exist
Platform: All
Root Cause: Incorrect glob pattern syntax
Frequency: Low (3/10)
Confidence: 80%

Prevention Strategy:
  Common mistakes:
    - Using regex syntax in glob (use shell glob syntax)
    - Forgetting ** for recursive search
    - Wrong directory separator (/ vs \)

Example:
  ❌ Wrong: Glob("src/*.tsx$")  # regex anchor
  ✅ Right: Glob("src/**/*.tsx")  # recursive glob
```

#### Pattern 4.2: Grep Multiline Without Flag
```yaml
Signature: Grep returns no results for multi-line pattern
Platform: All
Root Cause: Pattern spans lines but multiline not enabled
Frequency: Low (3/10)
Confidence: 85%

Prevention Strategy:
  Before Grep execution:
    1. Check if pattern contains \n or [\s\S]
    2. If yes and multiline=false:
       - Set multiline=true
       - Inform user

Example:
  ❌ Wrong: Grep(pattern="function.*\n.*return", multiline=false)
  ✅ Right: Grep(pattern="function.*\n.*return", multiline=true)
  Message: "Enabled multiline mode for cross-line pattern"
```

---

### Category 5: Git Operations

#### Pattern 5.1: Commit Without Staged Files
```yaml
Signature: "nothing to commit"
Platform: All
Root Cause: Files not staged before commit
Frequency: Medium (5/10)
Confidence: 95%

Prevention Strategy:
  Before git commit:
    1. Check git status
    2. If no staged files:
       - Either stage relevant files
       - Or inform user nothing to commit

Example:
  ❌ Wrong: git commit -m "message" (when nothing staged)
  ✅ Right: git add files → git commit -m "message"
  Message: "No files staged. Staging [files] first."
```

#### Pattern 5.2: Force Push to Main/Master
```yaml
Signature: "git push --force" + branch is main/master
Platform: All
Root Cause: Dangerous force push to protected branch
Frequency: Low (2/10, but critical)
Confidence: 100%

Prevention Strategy:
  Before git push --force:
    1. Check current branch
    2. If main/master:
       - BLOCK execution
       - Warn user of danger
       - Require explicit override

Example:
  ❌ Dangerous: git push --force origin main
  ✅ Safe: Switch to feature branch first OR get explicit user confirmation
  Message: "⚠️ BLOCKED: Force push to main/master is dangerous. Confirm if intentional."
```

---

### Category 6: Platform-Specific Issues

#### Pattern 6.1: Path Format Mismatch
```yaml
Signature: "No such file" + path uses wrong separator
Platform: Cross-platform
Root Cause: Using \ on Linux or / inconsistently on Windows
Frequency: Medium (5/10 in cross-platform work)
Confidence: 85%

Prevention Strategy:
  Before file operations:
    1. Detect platform
    2. Normalize path separators
    3. Windows: Accept both / and \
    4. Linux: Only /

Example:
  ❌ Wrong (on Linux): "C:\Users\file.txt"
  ✅ Right: "C:/Users/file.txt" or use path.join()
  Message: "Normalized path separators for platform"
```

#### Pattern 6.2: Permission Denied (Common Cases)
```yaml
Signature: "Permission denied" errors
Platform: All
Root Cause: Various - file locked, no write perms, admin needed
Frequency: Medium (4/10)
Confidence: 70%

Prevention Strategy:
  When permission denied:
    1. Check if file is locked by another process
    2. Check file permissions
    3. On Windows: Check if admin rights needed
    4. Suggest solutions based on context

Common Fixes:
  - File locked: Close other applications
  - No write perms: chmod on Linux, properties on Windows
  - Admin needed: Run as admin or use sudo
```

---

## Self-Learning Mechanism

### When New Failure Occurs

```markdown
1. **Capture Failure Context**:
   - Error message
   - Tool/command used
   - Platform
   - File/context involved
   - Attempted action

2. **Log Pattern**:
   - Add to "New Patterns Discovered" section below
   - Include frequency counter (starts at 1)
   - Mark confidence as "Learning" (< 50%)

3. **Pattern Promotion**:
   - After same failure occurs 2+ times → Confidence 60%
   - After 3+ times → Confidence 80% → Move to main KB
   - After 5+ times → Confidence 95% → Permanent pattern

4. **Solution Discovery**:
   - When failure fixed, log the solution
   - Associate solution with failure pattern
   - Next time → Auto-prevent using solution
```

### New Patterns Discovered (Auto-Updated Section)

```yaml
# This section grows over time as new failures are encountered
# Format:
# - Date: YYYY-MM-DD
# - Failure: [description]
# - Frequency: [count]
# - Status: Learning | Confirmed | Promoted
# - Solution: [if found]

# Example entry:
# - Date: 2026-01-22
# - Failure: Bash "del" command not found
# - Frequency: 1
# - Status: Learning
# - Solution: Use "rm" instead

# [New patterns will be added here automatically]
```

---

## Integration with Other Skills

### Priority in Execution Flow

```
1. context-management-core     (validate context)
2. model-selection-core        (select model)
3. task-planning-intelligence  (decide strategy)
4. ↓
5. BEFORE EXECUTION: Check common-failures-prevention ← NEW!
   ├─ Pattern match against KB
   ├─ If match: Use solution, prevent failure
   └─ If no match: Execute as planned
6. ↓
7. Execute (Tool call)
8. ↓
9. IF FAILED: Log to failures KB
   └─ Update pattern frequency
   └─ Mark for future prevention
```

---

## Usage Examples

### Example 1: Preventing del Command Error

**User Request**: "Delete the temp file"

**Without KB**:
```
bash -c "del temp.txt"
Error: bash: del: command not found
↓
Retry with: rm temp.txt
Total: 2 attempts, wasted tokens
```

**With KB**:
```
Planned: bash -c "del temp.txt"
↓
Check KB: Pattern match "del in Unix shell"
↓
Auto-correct to: bash -c "rm temp.txt"
↓
Success on first try
Message: "Converted 'del' to 'rm' for Unix compatibility"
```

### Example 2: Edit String Not Found

**User Request**: "Update the function"

**Without KB**:
```
Edit(file, old_string="     1→function foo() {", new_string="...")
Error: String not found
↓
Retry with fixed string
Total: 2 attempts
```

**With KB**:
```
Planned: Edit with line-number prefix
↓
Check KB: Pattern match "line prefix in old_string"
↓
Auto-strip prefix before execution
↓
Success on first try
Message: "Stripped line number prefix for accurate matching"
```

### Example 3: Large File Read

**User Request**: "Update API docs in README"

**Without KB**:
```
Read(README.md)  # 800 lines
Total tokens: 2400
↓
Write(README.md)
Total tokens: 2400
Total: 4800 tokens
```

**With KB**:
```
Check file size: 800 lines (>500, trigger intelligent strategy)
↓
Read structure only: 300 tokens
Grep section: 10 tokens
Read target section: 300 tokens
Edit section: 200 tokens
Total: 810 tokens (83% savings!)
Message: "Large file detected. Using intelligent read strategy."
```

---

## Token Savings Analysis

### Per-Failure Savings

```
Average failure-retry cycle: 1000-3000 tokens
Average prevention check: 50-100 tokens

Savings per prevented failure: 900-2900 tokens
ROI: 10x-30x return on prevention check
```

### Cumulative Savings

```
Session with 10 commands:
- Without KB: 2-3 failures × 2000 tokens = 4000-6000 tokens wasted
- With KB: Prevented all → 0 tokens wasted
- Net savings: 4000-6000 tokens per session

Long-term (50 sessions):
- Prevents 100-150 failures
- Saves 100K-300K tokens
- Equivalent to saving $1-3 on API costs
```

---

## Confidence Scoring System

```python
confidence_levels = {
    0-25:   "Unknown - First occurrence",
    26-50:  "Learning - Observed 2 times",
    51-75:  "Probable - Observed 3 times, solution works",
    76-90:  "Confirmed - Observed 5+ times, solution reliable",
    91-100: "Certain - Observed 10+ times, never fails"
}

# Execution decision
if confidence >= 75:
    auto_prevent()  # High confidence, just do it
elif confidence >= 50:
    warn_and_prevent()  # Medium confidence, inform user
else:
    execute_and_learn()  # Low confidence, try and log
```

---

## Maintenance & Evolution

### Pruning Old Patterns

```
If pattern not matched in 100+ sessions:
  - Mark as "Deprecated"
  - Move to archive
  - Keep solution for reference
  - Remove from active prevention checks

Reason: Keeps KB lean, focuses on relevant failures
```

### Pattern Merging

```
If two patterns are >80% similar:
  - Merge into single generalized pattern
  - Keep both specific examples
  - Increase confidence

Example:
  Pattern A: "del command on Git Bash"
  Pattern B: "del command on WSL"
  ↓
  Merged: "del command on Unix-like shells"
```

### User Feedback Loop

```
When prevention applied:
  - Show message: "Prevented [X] using KB"
  - If user says "wrong prevention":
    - Lower confidence by 20%
    - Ask for correct approach
    - Update pattern
```

---

## Quick Reference

### Before Using Tool, Check:

| Tool | Check For | Prevention |
|------|-----------|------------|
| Bash | Windows commands (del, copy, etc.) | Auto-translate to Unix |
| Bash | Paths with spaces unquoted | Add quotes |
| Bash | Interactive flags (-i) | Block & suggest alternative |
| Edit | Line number prefixes | Strip before matching |
| Edit | Non-unique strings | Expand context |
| Read | Large files (>500 lines) | Use intelligent strategy |
| Write | Existing file not read | Read first |
| Grep | Multi-line pattern | Enable multiline flag |
| Git | Force push to main | Block & warn |

---

## Status

**Version**: 1.0.0
**Status**: ACTIVE (Always checking before execution)
**Created**: 2026-01-22
**Patterns**: 13 initial patterns (will grow over time)
**Integration**: Works with all core skills

---

## Summary (TL;DR)

**What**: Self-learning knowledge base of failures and solutions
**How**: Pattern matching before execution + logging after failures
**Why**: Prevent repeating mistakes, save tokens, improve over time
**Savings**: 10x-30x ROI, prevents 2-3 failures per session
**Evolution**: Learns from new failures, promotes patterns based on frequency

**Key Principle**: "Never make the same mistake twice"

---

**Remember**: This KB grows smarter with every session! 🧠
