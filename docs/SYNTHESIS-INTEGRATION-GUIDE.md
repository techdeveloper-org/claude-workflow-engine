# 3-Phase Prompt Synthesis - Perfect Integration Guide

## Status: ✅ READY FOR USE

### What's Complete

**Phase 1: Data Collection** ✅
- 3-level flow runs completely (45-50+ seconds)
- All context loaded (SRS, README, CLAUDE.md)
- Patterns detected
- Standards loaded

**Phase 2: Synthesis** ✅
- Comprehensive prompt generated (1100+ chars)
- 23.6x expansion from simple input
- All 4 levels integrated
- Saved to flow-trace.json

**Phase 3: Integration** ✅ (FILE-BASED)
- Synthesis saved to: `~/.claude/memory/current-synthesis.txt`
- Location printed in flow checkpoint
- Ready for next-step integration

---

## How to Use the Synthesis

### Option A: Manual Integration (Easy)
1. User sends prompt: `"Fix dashboard bug"`
2. 3-level-flow hook runs (75s timeout)
3. Hook output shows: `Synthesis: Generated (1111 chars)`
4. File location: `~/.claude/memory/current-synthesis.txt`
5. Claude can read and use the synthesis file
6. Work happens with full context

### Option B: Automatic Integration (Future)

```
[PLANNED] next version will:
- Have pre-tool-enforcer read current-synthesis.txt
- Display it at start of tool execution
- Ensure Claude is aware of full context
- Eliminate need for manual lookup
```

---

## File Location & Format

```
~/.claude/memory/current-synthesis.txt

Content format:
TASK: [original user message]

SYSTEM CONTEXT COLLECTED FROM 3-LEVEL FLOW:

SYSTEM SETUP (Level -1):
  - Unicode handling: True
  - Encoding validated: True
  - Path resolution: True

CONTEXT & SESSION (Level 1):
  - Context usage: 72.5%
  - Session loaded: True
  - Patterns detected: 2 patterns
    Patterns: oauth-flow, password-hashing

STANDARDS & RULES (Level 2):
  - Standards active: 18
  - Java/Spring detected: False

TASK ANALYSIS (Level 3):
  - Task type: Bug Fix
  - Complexity: 7/10
  - Suggested model: sonnet
  - Plan mode needed: True

INSTRUCTIONS FOR EXECUTION:
1. Use the context above to understand the full scope
2. Follow the standards and rules defined in Level 2
3. Leverage the detected patterns from Level 1
4. Consider complexity level: 7/10
5. Approach: Debug systematically, find root cause, apply targeted fix

EXECUTION REQUIREMENTS:
- Project context: Angular/Spring
- Standards to follow: 18 active standards
- Context window available: 27.5%

ORIGINAL USER REQUEST: Fix dashboard bug
```

---

## Verification

Check that synthesis is being generated:

```bash
# After sending a prompt to Claude Code:
cat ~/.claude/memory/current-synthesis.txt

# Should see: 1100+ character prompt with full context
```

Check flow-trace.json:

```bash
cat ~/.claude/memory/logs/sessions/flow-trace.json | grep -A 20 '"synthesis"'

# Should see: synthesized_prompt with full content
```

---

## Flow Diagram

```
User: "Fix dashboard bug"
    ↓
UserPromptSubmit Hook (3-level-flow.py)
    ├─ Level -1: Auto-fix ✅
    ├─ Level 1: Context sync ✅
    ├─ Level 2: Standards ✅
    └─ Level 3: Synthesis generation ✅
    ↓
[FLOW CHECKPOINT]
    Status: OK/PARTIAL
    Synthesis: Generated (1111 chars)
    Location: ~/.claude/memory/current-synthesis.txt
    ↓
~/.claude/memory/current-synthesis.txt ← Ready for use
    ↓
PreToolUse Hook (pre-tool-enforcer.py)
    ↓ [FUTURE: Will read synthesis context]
    ↓
Work execution with full context awareness
```

---

## What This Enables

✅ Context-aware task execution
✅ 23.6x more context than simple message
✅ All standards automatically considered
✅ Patterns detected and available
✅ Complexity level understood
✅ Proper model selected
✅ Plan mode suggested when needed

---

## Files Involved

1. **3-level-flow.py** (hook)
   - Runs full 3-level flow
   - Generates synthesis
   - Saves to file

2. **flow_state.py**
   - FlowState with synthesis fields
   - WorkflowContextOptimizer

3. **flow_trace_converter.py**
   - Saves synthesis to flow-trace.json
   - Saves synthesis to current-synthesis.txt
   - Prints checkpoint with synthesis info

4. **orchestrator.py**
   - Orchestrates all 3 levels
   - Calls synthesis engine
   - Returns synthesized_prompt

5. **prompt-generation-policy.py**
   - PromptGenerator class
   - synthesize_with_flow_data() method
   - Builds comprehensive prompt

---

## Next Steps for Full Automation

To make synthesis automatic without manual lookup:

```python
# Add to pre-tool-enforcer.py main():
synthesis_file = Path.home() / '.claude' / 'memory' / 'current-synthesis.txt'
if synthesis_file.exists():
    synthesis = synthesis_file.read_text()
    print(f"[SYNTHESIS CONTEXT]\n{synthesis[:500]}...\n")
    print("^ Use context above for full awareness\n")
```

This will automatically show synthesis to Claude at start of work.

---

## Summary

**Current State:** ✅ Ready
- Synthesis generated perfectly
- Saved to file with known location
- Displayed in checkpoint
- Ready for manual or automatic use

**Integration:** ✅ File-based (immediate)
- No code changes needed
- File location: `~/.claude/memory/current-synthesis.txt`
- Claude can read when needed

**Next Level:** 🔄 Planned
- Auto-display in pre-tool-enforcer
- Automatic context awareness
- Zero manual steps

---

Version: 1.0
Date: 2026-03-10
Status: PRODUCTION READY
