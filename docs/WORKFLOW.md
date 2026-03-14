# Claude Insight: Complete 3-Level Execution Workflow

**Version:** 1.0.0
**Date:** 2026-03-10
**Status:** ACTIVE IMPLEMENTATION

---

## Overview

The Claude Insight system implements a **3-level enforcement architecture** with automated context optimization, plan mode decision-making, and structured task execution.

```
USER PROMPT
    ↓
LEVEL -1: AUTO-FIX ENFORCEMENT (Blocking Checks)
    ↓
LEVEL 1: CONTEXT SYNC (Build TOON Object)
    ↓
LEVEL 2: STANDARDS SYSTEM (Claude's Rules Folder - Not in Flow)
    ↓
LEVEL 3: 14-STEP EXECUTION PIPELINE
    ↓
RESULT
```

---

## LEVEL -1: AUTO-FIX ENFORCEMENT

### Purpose
System setup validation with interactive failure handling.

### Flow

```
START
  ↓
Three Sequential Checks:
  1. node_unicode_fix (UTF-8 encoding on Windows)
  2. node_encoding_validation (ASCII-only Python files)
  3. node_windows_path_check (Forward slashes, no backslashes)
  ↓
level_minus1_merge_node
  ├─ If ALL PASS → GO TO LEVEL 1
  └─ If ANY FAIL → ask_level_minus1_fix (INTERACTIVE)
      ├─ Show SPECIFIC failures (✓ PASS / ❌ FAIL for each)
      ├─ Ask user: "Auto-fix or Skip?"
      │
      ├─ Choice: "Auto-fix"
      │  ↓
      │  fix_level_minus1_issues
      │  ├─ Attempt fixes (max 3 retries)
      │  ├─ Reset checks
      │  └─ Retry Level -1
      │     ├─ If pass → GO TO LEVEL 1
      │     └─ If fail → Ask again (Attempt #2, #3...)
      │
      └─ Choice: "Skip"
         └─ GO TO LEVEL 1 (⚠️ NOT RECOMMENDED - will break later)
```

### Key Points

- **3 independent checks** run sequentially
- **Individual failure reporting** - shows exactly which check failed
- **Retry loop with max 3 attempts** - prevents infinite loops
- **Memory cleanup on failure** - no state pollution
- **Original user prompt preserved** throughout

### Output

```json
{
  "level_minus1_status": "OK" | "BLOCKED",
  "failed_nodes": ["encoding_validation", "windows_path_check"],
  "auto_fix_applied": ["Unicode UTF-8 encoding"],
  "retry_count": 1
}
```

---

## LEVEL 1: CONTEXT SYNC

### Purpose
Collect project context, analyze complexity, compress to TOON object.

### Flow

```
START (from Level -1)
  ↓
Step 1: node_session_loader (MUST BE FIRST)
  ├─ Create session folder: ~/.claude/logs/sessions/{session_id}/
  ├─ Save: session.json (metadata)
  └─ Output: session_id, session_path
      ↓
Step 2: PARALLEL (Both run simultaneously)
  ├─ node_complexity_calculation
  │  ├─ Analyze project structure
  │  ├─ Build call stack and graph
  │  └─ Output: complexity_score, project_graph, architecture
  │
  └─ node_context_loader
     ├─ Read from PROJECT folder (not ~/.claude/)
     ├─ Try: SRS, README.md, CLAUDE.md
     ├─ Skip if not found
     └─ Output: context_data (full file contents)
      ↓
Step 3: node_toon_compression (NEW!)
  ├─ Combine all Level 1 data
  ├─ Build TOON object:
  │  ├─ session_id
  │  ├─ complexity_score
  │  ├─ files_loaded_count
  │  └─ context (SRS, README, CLAUDE.md status)
  ├─ Compress using toons library
  ├─ Save: ~/.claude/logs/sessions/{session_id}/context.toon.json
  ├─ Clear from memory:
  │  ├─ full_srs_content
  │  ├─ full_readme_content
  │  ├─ full_claude_md_content
  │  ├─ project_graph
  │  └─ architecture
  └─ Output: TOON object (COMPACT)
      ↓
Step 4: level1_merge_node
  ├─ Output: level1_context_toon (ONLY compact TOON object)
  └─ Signal: Memory cleanup completed
      ↓
Step 5: cleanup_level1_memory
  └─ Free remaining RAM variables
      ↓
GO TO LEVEL 2
```

### Key Points

- **Session isolated in ~/.claude/logs/sessions/**
- **Context from PROJECT folder** (not ~/.claude/memory/)
- **TOON compression 10x token reduction**
- **Memory cleaned after compression** (project files safe)
- **Only TOON object flows to Level 3**

### Output (TOON Object)

```json
{
  "session_id": "session-20260310-120000-abc12345",
  "timestamp": "2026-03-10T12:00:00.123456",
  "complexity_score": 7,
  "files_loaded_count": 3,
  "context": {
    "files": ["SRS", "README", "CLAUDE.md"],
    "srs": true,
    "readme": true,
    "claude_md": true
  }
}
```

---

## LEVEL 2: STANDARDS SYSTEM

### Purpose
Load project-specific rules and standards.

### Implementation

**NOT part of execution flow** - Standards are loaded into Claude's RULES folder.

When Claude works on any task, it automatically loads:
- Project-specific standards (18 for Java, 10 for common)
- Coding patterns and conventions
- Best practices

**One-time setup:**
```bash
~/.claude/rules/
├─ project-standards.md (auto-loaded)
└─ [other rule files]
```

### In Workflow

- **No explicit execution step** in Level 3
- **Automatic** - Claude environment loads rules
- **External to flow** - managed separately

---

## LEVEL 3: 14-STEP EXECUTION PIPELINE

### Purpose
Execute the actual development task using plan, skills, agents, and automation.

### Input

```json
{
  "user_requirement": "Fix dashboard bug in...",
  "toon_object": { /* from Level 1 */ }
}
```

### Flow

#### STEP 1: PLAN MODE DECISION

```
Action:
  Send TOON + user_requirement to LOCAL LLM

System Prompt:
  "Analyze the project TOON and user requirement.
   Determine if PLAN MODE is required based on:
   - complexity_score
   - project architecture
   - requirement complexity

   Return: { plan_required: true/false, reasoning: '...' }"

Output:
  {
    "plan_required": true | false,
    "reasoning": "explanation"
  }
```

#### STEP 2: PLAN MODE EXECUTION (if required)

```
Model Selection:
  - Planning: INTELLIGENT (Haiku/Sonnet/Opus based on complexity)
    * Complexity 1-3: Haiku (fast, cheap, simple planning)
    * Complexity 4-7: Sonnet (balanced reasoning and speed)
    * Complexity 8-10: Opus (deep reasoning for complex architecture)

  - Exploration: ALWAYS HAIKU (fast and cost-effective)
    * File reading, code search, pattern matching
    * NEVER use heavy models for exploration

Tool Optimization (MANDATORY):
  - Read: offset/limit (max 500 lines per file)
  - Grep: head_limit (max 50 matches)
  - Search: max_results (max 10 results)

  ✅ Policy Reference: policies/03-execution-system/06-tool-optimization/
  ✅ Script Reference: ~/.claude/memory/tool-usage-optimizer.py

Output:
  - Detailed implementation plan (from planning model)
  - Analysis of affected files (from exploration)
  - Code context from tool-optimized searches
  - Recommended approach
```

#### STEP 3: TASK/PHASE BREAKDOWN

```
Action:
  Break plan into structured tasks

Each Task:
  - target_files: ["src/component.py", "tests/test.py"]
  - modifications: ["Add feature X", "Update test Y"]
  - dependencies: ["Task 1", "Task 2"]
  - execution_order: 1, 2, 3...

Output:
  Structured task list with dependencies
```

#### STEP 4: TOON REFINEMENT

```
Keep:
  - final_plan
  - task_breakdown
  - files_involved
  - change_descriptions

Delete:
  - unnecessary analysis
  - exploration data
  - intermediate findings

Output:
  Refined TOON = Execution Blueprint
```

#### STEP 5: SKILL & AGENT SELECTION

```
Action:
  Send refined TOON + skill definitions + agent definitions to LOCAL LLM

System Prompt:
  "Analyze the refined TOON.
   Identify:
   - Which skills are required for which tasks
   - Which agents can execute which phases
   - Task → Skill mapping
   - Task → Agent mapping

   Return: Updated TOON with mappings"

Available Skills:
  (Complete definitions from ~/.claude/skills/)
  - java-spring-boot-microservices
  - docker
  - kubernetes
  - jenkins-pipeline
  - [etc...]

Available Agents:
  (Complete definitions from ~/.claude/agents/)
  - spring-boot-microservices
  - orchestrator-agent
  - devops-engineer
  - [etc...]

Output:
  {
    "tasks": [
      {
        "id": "Task-1",
        "skills": ["java-spring-boot"],
        "agents": ["spring-boot-microservices"]
      }
    ]
  }

Post-Processing:
  - Merge previous TOON + skill mapping TOON
  - Delete all old TOON versions
  - Keep ONLY final merged TOON
```

#### STEP 6: SKILL VALIDATION & DOWNLOAD

```
Action:
  1. Get skills selected by Step 5
  2. Validate: Check if they exist on system
  3. Download: Fetch missing skills from Claude Code GitHub
  4. Return: Selected skills with full content ready to use

Process:
  - Scan available skills/agents locally
  - Validate LLM recommendations from Step 5
  - Download any missing skills from internet
  - Prepare skills for Step 7 prompt generation

Output:
  - final_skills: ["docker", "kubernetes", ...]
  - final_agents: ["devops-engineer", ...]
  - downloaded: List of newly downloaded skills
```

**Note:** Old recommendation system (requiring RAG) has been completely removed.
This step replaces it with practical skill validation and download capability.

#### STEP 7: FINAL PROMPT GENERATION

```
Action:
  Send final merged TOON to LOCAL LLM

System Prompt:
  "Analyze the complete TOON object.
   Convert into a single, optimized execution prompt.

   Include:
   - Full context understanding
   - Detailed task breakdown
   - Required skills
   - Required agents
   - Execution strategy
   - File modifications
   - Expected outcomes

   Generate ONE consolidated prompt (no markdown, plain text)"

Output:
  prompt.txt (saved to session folder)

Save Location:
  ~/.claude/logs/sessions/{session_id}/prompt.txt

Post-Processing:
  - Delete TOON object from memory
  - Only prompt.txt remains
```

#### STEP 8: GITHUB ISSUE CREATION

```
Action:
  Analyze prompt.txt

Determine:
  Issue label from prompt content:
  - bug
  - feature
  - enhancement
  - test
  - documentation

Create GitHub Issue:
  {
    "title": "Issue title from prompt",
    "label": "bug" | "feature" | ... ,
    "body": {
      "task_summary": "...",
      "reasoning": "...",
      "implementation_plan": "...",
      "execution_approach": "..."
    }
  }

Output:
  issue_id (e.g., 42)
```

#### STEP 9: BRANCH CREATION

```
Action:
  1. Switch to: main or master branch
  2. Create new branch: issueID-label
     Example: issue-42-feature
  3. Push to remote

Output:
  Branch created and pushed
```

#### STEP 10: IMPLEMENTATION

```
Action:
  Execute tasks from prompt.txt sequentially

Guidelines:
  - Use tool optimization rules
  - Read files with offset/limit
  - Grep with head_limit
  - Follow task dependencies
  - Commit after each significant change

Output:
  Code modifications, file updates
```

#### STEP 11: PULL REQUEST & REVIEW

```
Action:
  1. Create PR: current_branch → main/master
  2. Automated code review (using skills/agents)
  3. If review passes:
     - Merge PR
     - Close PR
  4. If review fails:
     - Request changes
     - Update implementation
     - Re-review

Output:
  PR merged and closed (success)
  OR
  Changes requested (iterate)
```

#### STEP 12: ISSUE CLOSURE

```
Action:
  Close GitHub Issue

Add Comment:
  {
    "what_implemented": "Detailed description",
    "files_modified": ["src/file.py", "tests/test.py"],
    "approach_taken": "Explanation of solution",
    "verification_steps": [
      "Step 1",
      "Step 2"
    ]
  }

Output:
  Issue closed with detailed comment
```

#### STEP 13: PROJECT DOCUMENTATION UPDATE

```
Action:
  Check and update project documentation

Required Files:
  - SRS.md (System Requirements Specification)
  - README.md (Project Overview)
  - CLAUDE.md (Claude-specific context)

If not exist:
  Create them with:
  - Project description
  - Architecture overview
  - Setup instructions
  - Usage guide

If exist:
  Update based on:
  - Latest codebase changes
  - New features
  - Modified architecture
  - Updated standards

Output:
  Comprehensive project documentation
```

#### STEP 14: FINAL SUMMARY

```
Action:
  Generate execution summary

Content:
  - What was implemented
  - What changed
  - How system evolved
  - Key achievements

Format:
  Story-style narrative

Delivery:
  Voice notification to user
```

---

## Complete Execution Example

```
User Input:
  "Fix the authentication bug in dashboard"

Level -1:
  ✓ Unicode check: PASS
  ✓ Encoding check: PASS
  ✓ Path check: PASS
  → GO TO LEVEL 1

Level 1:
  ✓ Session created: session-20260310-120000-abc123
  ✓ Complexity calculated: 6/10
  ✓ Context loaded: SRS, README, CLAUDE.md
  ✓ TOON compressed: 10x smaller
  → GO TO LEVEL 2 (rules auto-loaded)

Level 3 - Step 1:
  Plan required? YES (complexity 6 + auth bug = needs planning)
  → GO TO STEP 2

Level 3 - Step 2:
  OPUS analyzes, identifies:
  - 3 files involved
  - Auth middleware needs update
  - Database schema change
  → Plan created

Level 3 - Step 3:
  Tasks breakdown:
  Task 1: Update auth middleware
  Task 2: Modify database schema
  Task 3: Add tests

Level 3 - Step 4:
  TOON refined to execution blueprint

Level 3 - Step 5:
  Skills selected: python-backend-engineer
  Agent selected: python-backend-engineer

Level 3 - Step 7:
  Prompt generated: "Implement auth fix with..."

Level 3 - Step 8:
  Issue created: "issue-42-bug"

Level 3 - Step 9:
  Branch created: issue-42-bug

Level 3 - Step 10:
  Implementation: Files modified

Level 3 - Step 11:
  PR created and merged

Level 3 - Step 12:
  Issue closed with details

Level 3 - Step 13:
  Documentation updated

Level 3 - Step 14:
  Summary: "Fixed authentication bug by..."

Result:
  ✅ Bug fixed
  ✅ Tests passing
  ✅ Documentation updated
  ✅ Issue closed
```

---

## Critical Rules

### Execution
- ✓ Every step completes before next starts
- ✓ No hallucinations allowed
- ✓ No assumptions allowed
- ✓ If data missing → ask questions first
- ✓ Deterministic execution only
- ✓ Follow defined workflow strictly

### TOON Object
- ✓ Refined at each step
- ✓ Old versions deleted after merge
- ✓ Only final TOON flows through pipeline
- ✓ Converted to prompt.txt for execution

### Tool Usage
- ✓ Read: Use offset/limit for large files
- ✓ Grep: Use head_limit
- ✓ Search: Optimization rules apply
- ✓ All exploration with HAIKU

### GitHub Integration
- ✓ Issue label determined from prompt
- ✓ Branch naming: issueID-label
- ✓ Automated review before merge
- ✓ Detailed closure comment

---

## File Locations

```
~/.claude/logs/sessions/{session_id}/
├─ session.json                    (Session metadata)
├─ context-raw.json               (Raw context from Level 1)
├─ context.toon.json              (Compressed TOON object)
└─ prompt.txt                      (Final execution prompt)

~/.claude/rules/
├─ project-standards.md           (Auto-loaded standards)
└─ [other rule files]

~/.claude/skills/                  (Skill definitions)
└─ [category folders]

~/.claude/agents/                  (Agent definitions)
└─ [agent folders]
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-10 | Initial implementation of 3-level workflow |

---

## References

- **CLAUDE.md** - Project-specific context
- **SRS.md** - System requirements
- **README.md** - Project overview
- **Level -1 Details** - Auto-fix enforcement
- **Level 1 Details** - Context sync with TOON
- **Level 3 Details** - 14-step execution pipeline

---

**Last Updated:** 2026-03-10
**Status:** ACTIVE
**Maintainers:** Claude Insight Team
