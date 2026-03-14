# LEVEL 3: DEEP ARCHITECTURAL DESIGN ANALYSIS

**Status:** DESIGN PHASE (NO IMPLEMENTATION YET)
**Date:** 2026-03-10
**Approach:** OPUS-level reasoning, maximum precision

---

## CRITICAL DESIGN QUESTIONS

Before implementation, we must answer these precisely:

### 1. TOON Object Lifecycle

**Question:** How does TOON flow through all 14 steps?

**Current Understanding:**
- Input: TOON from Level 1 (complexity_score, files_loaded, context)
- Modified at: Step 4 (refinement), Step 5 (skill mapping)
- Deleted from memory: After Step 7 (prompt.txt generation)
- Only prompt.txt continues to Step 10+

**ISSUES TO RESOLVE:**
1. Where is TOON object stored while processing?
   - In FlowState? In session folder? Both?
2. How do we track TOON versions?
   - Step 4 creates refined TOON
   - Step 5 merges skill TOON
   - Do we save intermediate versions?
3. When exactly is TOON deleted?
   - Immediately after Step 7?
   - What if Step 8+ needs reference data?
4. Is TOON serialization consistent?
   - Using toons.dumps()?
   - What about deserialization in later steps?

**DECISION NEEDED:** Define precise TOON lifecycle with save points.

---

### 2. LOCAL LLM Integration

**Question:** How do we call LOCAL LLM vs Claude?

**Current Understanding:**
- Steps 1, 5, 7 use LOCAL LLM (ollama)
- Not Claude API
- Returns structured JSON responses

**ISSUES TO RESOLVE:**
1. Ollama endpoint configuration?
   - Default: http://127.0.0.1:11434
   - Fallback if not available?
2. Model selection?
   - Which ollama model for each step?
   - qwen2.5:7b? llama2? granite?
3. System prompts?
   - Exactly what to send for plan decision?
   - What JSON structure expected back?
4. Error handling?
   - What if ollama unavailable?
   - What if model times out?
   - Fallback behavior?
5. Token limits?
   - How many tokens for each LLM call?
   - Context window per step?

**DECISION NEEDED:** Specify LOCAL LLM interface with fallbacks.

---

### 3. Script Integration vs New Code

**Question:** Which existing scripts to reuse? Which need new wrappers?

**Current Understanding:**
- Reuse existing scripts where possible
- Create NEW nodes that CALL existing scripts
- Don't modify existing scripts

**ISSUES TO RESOLVE:**
1. Existing script compatibility?
   - Do they accept JSON input?
   - Do they output JSON or text?
   - Do they handle large inputs?
2. Which scripts DON'T exist yet?
   - GitHub issue creation
   - PR creation and review
   - Issue closure
   - Documentation update
   - Final summary
3. For new functionality:
   - Use subprocess to existing scripts?
   - Or implement directly in Python?
4. Error handling in wrappers?
   - What if subprocess script fails?
   - How to recover?

**DECISION NEEDED:** Audit each step, identify gaps, define interfaces.

---

### 4. Prompt.txt Generation and Usage

**Question:** What exactly goes in prompt.txt and how is it executed?

**Current Understanding:**
- Step 7: Generate prompt.txt
- Step 10: Read prompt.txt and execute
- Execution means: Apply changes to codebase

**ISSUES TO RESOLVE:**
1. Prompt.txt format?
   - Plain text instructions?
   - Markdown with code blocks?
   - Structured YAML?
2. How is Step 10 "executed"?
   - Do we parse prompt.txt and call tools?
   - Do we send to Claude with prompt.txt?
   - Do we run as bash script?
3. File modifications in Step 10?
   - Who performs them? (Claude? Automation?)
   - How to verify modifications are correct?
   - Rollback if something fails?
4. Tool usage in Step 10?
   - Read, Grep, Bash, Edit, Write?
   - Tool optimization rules still apply?
   - Who decides which tool to use?

**DECISION NEEDED:** Define prompt.txt format, execution mechanism, verification.

---

### 5. GitHub Integration Points

**Question:** How does GitHub integration work across steps?

**Current Understanding:**
- Step 8: Create issue, get issue_id
- Step 9: Create branch with issue_id
- Step 11: Create PR, review, merge
- Step 12: Close issue with comment

**ISSUES TO RESOLVE:**
1. GitHub authentication?
   - How to authenticate? (Token, SSH, etc.)
   - Where to store credentials?
   - Fallback if auth fails?
2. Issue label determination (Step 8)?
   - Parse prompt.txt for keywords?
   - Pattern matching?
   - LLM classification?
3. Branch naming consistency?
   - issueID-label format
   - What if issue_id not numeric?
   - Conflict with existing branches?
4. PR automation (Step 11)?
   - Who reviews? (bot? LLM?)
   - What are pass/fail criteria?
   - Auto-merge if passes?
5. Issue closure (Step 12)?
   - What format for closure comment?
   - JSON structure? Markdown? Plain text?
   - Who can close (tool user? auto-bot)?

**DECISION NEEDED:** Define GitHub workflow with auth, issue labels, PR criteria.

---

### 6. Documentation Update Strategy

**Question:** How to auto-update SRS, README, CLAUDE.md?

**Current Understanding:**
- Step 13: Update/create project documentation
- Based on latest codebase
- Ensure comprehensive understanding

**ISSUES TO RESOLVE:**
1. SRS.md generation?
   - Parse code to extract requirements?
   - LLM-based from code analysis?
   - Manual template + auto-fill?
2. README.md update?
   - What sections required?
   - How to detect changed features?
   - Preserve user edits?
3. CLAUDE.md update?
   - Project-specific context
   - When to update vs create?
   - Preserve global rules section?
4. Detection of changes?
   - Compare before/after git diff?
   - LLM analysis of modifications?
5. Conflict resolution?
   - What if docs have manual edits?
   - How to preserve custom sections?

**DECISION NEEDED:** Define documentation update mechanism with conflict handling.

---

### 7. Execution Control and Rollback

**Question:** What happens if a step fails?

**Current Understanding:**
- Every step must complete before next
- But: What if Step 10 (implementation) fails?

**ISSUES TO RESOLVE:**
1. Step failure scenarios?
   - Step 7 (prompt generation) fails → Stop?
   - Step 10 (implementation) fails → Rollback?
   - Step 11 (PR review) fails → What to do?
2. Rollback mechanism?
   - Delete the git branch?
   - Undo file modifications?
   - Keep issue for retry?
3. Partial failures?
   - Some tasks succeed, others fail
   - How to handle mixed state?
4. Logging and auditing?
   - Track each step outcome
   - Save logs to session folder?
   - Replay capability?
5. Retry strategy?
   - Can user retry after fix?
   - How to preserve state?

**DECISION NEEDED:** Define failure handling, rollback strategy, retry mechanisms.

---

### 8. Hook Integration (Pre-tool, Post-tool)

**Question:** How do hooks interact with Level 3?

**Current Understanding:**
- Level 3 is the execution after Level 1 collects data
- But: Where do hooks fit?

**ISSUES TO RESOLVE:**
1. Pre-tool hook behavior during Level 3?
   - Runs before each tool call?
   - Should it enforce optimization rules?
   - Should it access TOON data?
2. Post-tool hook behavior during Level 3?
   - Runs after each tool call?
   - Tracks progress?
   - Updates session data?
3. Hook context availability?
   - Can hooks access prompt.txt?
   - Can hooks access TOON data (deleted after Step 7)?
   - What state available to hooks?
4. Tool execution control?
   - Pre-tool decides which tools allowed?
   - Post-tool tracks usage?
   - Rate limiting?

**DECISION NEEDED:** Define hook behavior during Level 3 execution.

---

### 9. Data Persistence Strategy

**Question:** What data persists where throughout workflow?

**Current Understanding:**
```
Session folder: ~/.claude/logs/sessions/{session_id}/
├─ session.json (Level 1)
├─ context.toon.json (Level 1)
├─ context-raw.json (Level 1)
├─ prompt.txt (Level 3 Step 7)
└─ ??? (execution logs?)
```

**ISSUES TO RESOLVE:**
1. What to save during execution?
   - Plan decision result? (Step 1)
   - Task breakdown? (Step 3)
   - Refined TOON? (Step 4)
   - Skill mappings? (Step 5)
   - GitHub issue ID? (Step 8)
   - Branch name? (Step 9)
   - PR number? (Step 11)
2. How to structure saved data?
   - JSON files? YAML? Plain text?
   - Organized by step or flat?
3. Cleanup strategy?
   - Delete intermediate files after success?
   - Keep everything for audit?
4. Recovery from crashes?
   - Can we resume from saved state?
   - How to detect incomplete execution?

**DECISION NEEDED:** Define data persistence model with recovery capability.

---

### 10. Claude vs Local LLM Boundary

**Question:** What should Claude do vs LOCAL LLM in Level 3?

**Current Understanding:**
- TOON object + prompt.txt created by LOCAL LLM
- Step 10 (implementation) executed by... Claude? Script?

**ISSUES TO RESOLVE:**
1. Step 10 execution responsibility?
   - Claude reads prompt.txt and implements?
   - Local script parses prompt and runs tools?
   - Hybrid approach?
2. If Claude executes:
   - How does Claude get prompt.txt?
   - Is prompt.txt sent as context?
   - Or Claude reads from session folder?
3. If script executes:
   - How to parse execution instructions from prompt?
   - Which tools does script use?
   - Error handling in script?
4. Tool usage during execution?
   - Pre-tool/post-tool hooks still active?
   - Tool optimization rules apply?
   - Who decides tool selection?

**DECISION NEEDED:** Define Claude vs automation boundary for Step 10+.

---

### 11. Session Folder Structure

**Question:** Exact structure for Level 3 session data?

**Current Design (needs refinement):**
```
~/.claude/logs/sessions/{session_id}/
├─ session.json
├─ context-raw.json
├─ context.toon.json
├─ prompt.txt
└─ ???
```

**ISSUES TO RESOLVE:**
1. Should there be subfolders?
   - level1-data/
   - level3-execution/
   - github-artifacts/
2. What files for each step?
   - Step 1 (plan decision): save response?
   - Step 3 (task breakdown): save tasks list?
   - Step 8 (GitHub): save issue details?
   - Step 11 (PR): save PR metadata?
3. Log files?
   - Execution log? (all tool calls, results)
   - Error log? (all failures)
   - Audit log? (who did what, when)
4. Size constraints?
   - Keep all files or cleanup?
   - Archive old sessions?
   - Compress if too large?

**DECISION NEEDED:** Define comprehensive session folder schema.

---

### 12. Error Messages and User Communication

**Question:** How does system communicate with user during Level 3?

**Current Understanding:**
- Step 14: Voice notification at the end
- But: What about errors during execution?

**ISSUES TO RESOLVE:**
1. Error notification?
   - Real-time? Or after completion?
   - To user or to log?
2. Progress updates?
   - User knows which step executing?
   - Estimates for completion?
3. Decision points?
   - Does user approve before PR merge?
   - Does user decide on conflicts?
4. Format of final summary?
   - Story-style narrative
   - How long? (brief? detailed?)
   - What level of technical detail?

**DECISION NEEDED:** Define user communication protocol throughout Level 3.

---

### 13. Production Readiness Checklist

**Question:** What makes Level 3 "production-ready"?

**CRITERIA TO DEFINE:**
- [ ] All 14 steps implemented
- [ ] Error handling for all failure cases
- [ ] Rollback mechanism for partial failures
- [ ] Data persistence to session folder
- [ ] GitHub integration tested
- [ ] Documentation auto-update working
- [ ] Logging comprehensive
- [ ] User communication clear
- [ ] Recovery from crashes
- [ ] Security (credentials, token storage)
- [ ] Performance (no timeouts)
- [ ] Audit trail complete

**DECISION NEEDED:** Define production readiness criteria and testing plan.

---

### 14. Integration with Existing Hook System

**Question:** How does Level 3 work with existing hooks?

**Current Hook System:**
```
UserPromptSubmit: script-chain-executor.py (Level -1, 1, 2)
PreToolUse: pre-tool-enforcer.py
PostToolUse: script-chain-executor.py
Stop: stop-notifier.py
```

**ISSUES TO RESOLVE:**
1. Does Level 3 run inside hook system?
   - Or separate from hooks?
2. If inside hooks:
   - Which hook triggers Level 3?
   - How to pass TOON through hook?
3. If separate:
   - How is Level 3 triggered?
   - After all hooks complete?
4. Hook modifications needed?
   - Pre-tool: needs Level 3 context?
   - Post-tool: tracks Level 3 progress?
5. Tool optimization during Level 3?
   - Pre-tool still enforces rules?
   - Or relaxed for Level 3 execution?

**DECISION NEEDED:** Define Level 3 relationship with hook system.

---

## CRITICAL DECISIONS NEEDED

Before implementation, we must decide:

1. ✓ TOON object lifecycle and storage
2. ✓ LOCAL LLM integration (ollama, models, fallback)
3. ✓ Script reuse vs new implementation
4. ✓ Prompt.txt generation and execution
5. ✓ GitHub workflow (auth, labels, PR criteria)
6. ✓ Documentation update mechanism
7. ✓ Failure handling and rollback
8. ✓ Hook integration strategy
9. ✓ Data persistence model
10. ✓ Claude vs automation boundary
11. ✓ Session folder structure
12. ✓ User communication protocol
13. ✓ Production readiness criteria
14. ✓ Hook system integration

---

## DESIGN APPROACH

**Recommended:**

1. **Answer each critical question above** (user input needed)
2. **Create detailed specification** based on decisions
3. **Plan exact code changes** (which files, what modifications)
4. **Create implementation checklist** (14 steps, dependencies)
5. **Only THEN implement** (with full context)

**No code should be written until these decisions are made.**

---

## NEXT STEPS

User should review these 14 critical questions and provide:

1. Decisions on each architecture question
2. Any constraints or preferences
3. Examples of expected behavior
4. Production requirements

Once decisions are made, I will:
1. Create detailed Level 3 specification
2. Plan exact implementation steps
3. Identify code changes needed
4. Create implementation with full context

---

**Status:** AWAITING DECISIONS
**Target:** Production-ready Level 3 implementation
**Approach:** Deep architectural design first, code second

