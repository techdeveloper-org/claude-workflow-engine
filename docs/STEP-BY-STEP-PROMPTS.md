# Complete Step-by-Step Prompt & Data Flow

**This document shows EXACTLY what prompts and data are being generated at each level and step**

---

## Example: User sends message in Claude Code

```
User: "Create a REST API endpoint for user authentication with JWT tokens"
```

---

## LEVEL -1: AUTO-FIX ENFORCEMENT

### What Happens
- **node_unicode_fix**: Checks if Windows, applies UTF-8 encoding
- **node_encoding_validation**: Validates Python files are ASCII-only
- **node_windows_path_check**: Checks for hardcoded backslash paths

### Data Output
```json
{
  "level_minus1_status": "OK",
  "unicode_check": true,
  "encoding_check": true,
  "windows_path_check": true,
  "auto_fix_applied": ["Unicode UTF-8 encoding"]
}
```

### Routing Decision
```
If level_minus1_status == "BLOCKED" → EXIT early
Else → Continue to Level 1
```

---

## LEVEL 1: SYNC SYSTEM (4 Context Tasks)

### Node 1: Context Loader
**Script:** `context-monitor-v2.py`

**Input:** None (reads system state)

**Prompt:** (internal to script)
```
Calculate context usage from:
- ~/.claude/memory/logs/ directory size
- ~/.claude/memory/sessions/ directory size
- CONTEXT_BUDGET = 200KB
- THRESHOLD = 85%
```

**Output:**
```json
{
  "context_loaded": true,
  "context_percentage": 32.5,
  "context_threshold_exceeded": false,
  "context_metadata": {
    "logs_size_kb": 45.2,
    "sessions_size_kb": 20.1,
    "total_used_kb": 65.3,
    "status": "OK"
  }
}
```

---

### Node 2: Session Loader
**Script:** `session-loader.py`

**Input:** None (reads session state)

**Prompt:** (internal to script)
```
Load session data from:
- ~/.claude/memory/sessions/
- Current session ID
- Previous session history
```

**Output:**
```json
{
  "session_chain_loaded": true,
  "session_history": [
    {
      "session_id": "SESSION-20260310-0245-ABCD",
      "timestamp": "2026-03-10T02:45:00",
      "messages": 3,
      "duration": 245000
    }
  ],
  "session_state_data": {
    "session_id": "SESSION-20260310-0305-EFGH",
    "chain_depth": 1
  }
}
```

---

### Node 3: Preferences Loader
**Script:** `load-preferences.py`

**Input:** None (reads user preferences)

**Prompt:** (internal to script)
```
Load from ~/.claude/preferences.json:
- default_model
- use_plan_mode
- parallel_execution
- etc.
```

**Output:**
```json
{
  "preferences_loaded": true,
  "preferences_data": {
    "default_model": "sonnet",
    "use_plan_mode": false,
    "parallel_execution": true,
    "verbose_output": true
  }
}
```

---

### Node 4: Pattern Detector
**Script:** `detect-patterns.py`

**Input:** `--project=/path/to/project`

**Prompt:** (internal to script)
```
Scan project directory for patterns:
- Technology stack (Java, Python, Node.js, etc.)
- Project structure (.git, Dockerfile, etc.)
- Common patterns (microservices, monolith, etc.)
```

**Output:**
```json
{
  "patterns_detected": [
    "Java Spring Boot project",
    "Maven-based",
    "REST API structure",
    "Maven multi-module"
  ],
  "pattern_metadata": {
    "total_patterns": 4,
    "primary_tech": "Java"
  }
}
```

---

### Level 1 Merge
```json
{
  "level1_status": "OK",
  "context_loaded": true,
  "context_percentage": 32.5,
  "context_threshold_exceeded": false,
  "session_chain_loaded": true,
  "preferences_loaded": true,
  "patterns_detected": ["Java Spring Boot project", "Maven-based", ...]
}
```

---

## LEVEL 2: STANDARDS SYSTEM

### Node: Common Standards Loader
**Script:** `standards-loader.py`

**Input:** `--load-all`

**Prompt:** (internal - scans policy directory)
```
Load policies from ~/.claude/policies/:
- 01-sync-system/ policies
- 02-standards-system/ policies
- 03-execution-system/ policies
```

**Output:**
```json
{
  "standards_loaded": true,
  "standards_count": 37,
  "standards_list": [
    "api-design-standards",
    "error-handling-patterns",
    "code-organization-rules",
    ...
  ]
}
```

---

### Conditional: Java Detection
**Input:** Check if project is Java

**Detection Logic:**
```
if pom.xml exists → is_java_project = true
if build.gradle exists → is_java_project = true
if *.java files exist → is_java_project = true
else → is_java_project = false
```

**Result for our example:** `is_java_project = true` (found pom.xml)

---

### Node: Java Standards Loader (if Java detected)
**Script:** (inline logic)

**Input:** `--project=/path/to/project`

**Prompt:** (internal)
```
Load Java-specific standards from:
- ~/.claude/policies/02-standards-system/*java*.md
- Spring Boot patterns
- Java design patterns
```

**Output:**
```json
{
  "java_standards_loaded": true,
  "spring_boot_patterns": {
    "standards_found": 8,
    "standards_list": [
      "spring-boot-microservices",
      "spring-dependency-injection",
      "spring-mvc-patterns"
    ],
    "annotations": [
      "@SpringBootApplication",
      "@Service",
      "@Repository",
      "@RestController",
      "@Bean",
      "@Configuration"
    ],
    "patterns": [
      "dependency-injection",
      "service-layer",
      "repository-pattern",
      "exception-handling"
    ]
  }
}
```

---

### Level 2 Merge
```json
{
  "level2_status": "OK",
  "standards_loaded": true,
  "standards_count": 37,
  "is_java_project": true,
  "java_standards_loaded": true,
  "spring_boot_patterns": { ... }
}
```

---

## LEVEL 3: EXECUTION SYSTEM (12 SEQUENTIAL STEPS)

---

### STEP 0: Prompt Generation

**Script:** `prompt-generator.py` with **Ollama LLM**

**Input to Script:**
```
User Message: "Create a REST API endpoint for user authentication with JWT tokens"
Project Type: Java (detected)
```

**Prompt Sent to Ollama LLM:**
```
Analyze this task and respond with ONLY a JSON object (no markdown, no extra text):

Task: Create a REST API endpoint for user authentication with JWT tokens
Project Type: Java

Respond ONLY with JSON:
{
  "task_type": "one of: API Creation, Bug Fix, Refactoring, New Feature, Testing, Documentation, Database, Security, Configuration, or Design",
  "complexity": integer from 1 to 10,
  "reasoning": "brief explanation"
}

JSON only, no markdown:
```

**Ollama Response (qwen2.5:7b):**
```
{
  "task_type": "API Creation",
  "complexity": 8,
  "reasoning": "Creating JWT authentication requires designing endpoints, implementing security patterns, database integration, and testing. Spring Boot framework helps but complexity is high due to security requirements."
}
```

**Step 0 Output:**
```json
{
  "step0_prompt": {
    "task_type": "API Creation",
    "complexity": 8,
    "reasoning": "Creating JWT authentication requires designing endpoints, implementing security patterns, database integration, and testing. Spring Boot framework helps but complexity is high due to security requirements.",
    "script_output": {
      "task_type": "API Creation",
      "complexity": 8,
      "suggested_model": "sonnet",
      "project_type": "Java",
      "reasoning": "..."
    }
  }
}
```

**Data Now Available to Downstream Steps:**
- `step0_prompt.task_type` = "API Creation"
- `step0_prompt.complexity` = 8
- `user_message` = "Create a REST API endpoint for user authentication with JWT tokens"

---

### STEP 1: Task Breakdown

**Script:** `task-auto-analyzer.py`

**Input to Script:**
```
Argument 0: "Create a REST API endpoint for user authentication with JWT tokens"
Argument 1: --task-type=API Creation
```

**Prompt Sent to Ollama (via script logic):**
```
Break down this API Creation task into specific subtasks:

Task: Create a REST API endpoint for user authentication with JWT tokens
Task Type: API Creation

Provide JSON with task_count and list of specific subtasks
```

**Ollama Response:**
```json
{
  "task_count": 5,
  "tasks": [
    "Design authentication endpoint schema (user registration/login)",
    "Implement JWT token generation and validation",
    "Create user database entity and repository",
    "Add password hashing with BCrypt",
    "Write unit and integration tests for auth endpoints"
  ],
  "reasoning": "API Creation for auth requires careful design of schema, secure token handling, data persistence, and comprehensive testing"
}
```

**Step 1 Output:**
```json
{
  "step1_tasks": {
    "count": 5,
    "tasks": [
      "Design authentication endpoint schema (user registration/login)",
      "Implement JWT token generation and validation",
      "Create user database entity and repository",
      "Add password hashing with BCrypt",
      "Write unit and integration tests for auth endpoints"
    ],
    "script_output": { ... }
  },
  "step1_task_count": 5
}
```

---

### STEP 2: Plan Mode Decision

**Script:** `auto-plan-mode-suggester.py`

**Input to Script:**
```
--analyze
--complexity=8
--tasks=5
```

**Prompt Sent to Ollama:**
```
For a task with complexity=8 and 5 subtasks, should the user enter EnterPlanMode for planning?

Complexity: 8/10
Task Count: 5 subtasks
Task Type: API Creation

Respond with:
{
  "plan_required": true/false,
  "reasoning": "explanation",
  "complexity_score": 8
}
```

**Ollama Response:**
```json
{
  "plan_required": true,
  "reasoning": "With 5 subtasks and complexity 8, planning mode helps organize API design, security implementation, and testing strategy. JWT authentication has multiple security considerations that benefit from planning.",
  "complexity_score": 8,
  "factors": [
    "Multiple subtasks (5) suggest need for planning",
    "High complexity (8/10) requires careful approach",
    "Security-critical (JWT/auth) needs planning",
    "Multi-step implementation (schema → tokens → DB → hashing → tests)"
  ]
}
```

**Step 2 Output:**
```json
{
  "step2_plan_mode": true,
  "step2_reasoning": "With 5 subtasks and complexity 8, planning mode helps organize API design, security implementation, and testing strategy. JWT authentication has multiple security considerations that benefit from planning.",
  "step2_complexity_score": 8
}
```

---

### STEP 3: Context Read Enforcement

**Script:** `context-reader.py`

**Input:** None (checks project state)

**Logic:**
```
if README.md exists AND SRS.md exists AND CLAUDE.md exists:
    is_new_project = false
    enforcement_applies = true
else:
    is_new_project = true
    enforcement_applies = false
```

**Step 3 Output:**
```json
{
  "step3_context_read": true,
  "step3_enforcement_applies": true,
  "step3_context_status": "Files found",
  "step3_message": "Project context documentation found - enforcement applies"
}
```

---

### STEP 4: Model Selection

**Script:** `model-auto-selector.py`

**Input:**
```
--complexity=8
```

**Logic:**
```
if complexity <= 3:
    selected_model = "haiku"  (fast, cheap)
elif complexity <= 7:
    selected_model = "sonnet" (balanced)
else:
    selected_model = "opus"   (most capable)

if context_percentage > 75%:
    upgrade_model()
```

**Model Selection:**
- complexity = 8
- context_percentage = 32.5% (below threshold)
- **selected_model = "opus"** (needed for complexity 8)

**Step 4 Output:**
```json
{
  "step4_model": "opus",
  "step4_reasoning": "Complexity 8 (JWT API Creation) needs Opus. API design, security patterns, and token handling require most capable model.",
  "step4_cost_estimate": "Input: $5/M, Output: $25/M"
}
```

---

### STEP 5: Skill & Agent Selection

**Script:** `auto-skill-agent-selector.py`

**Input:**
```
--analyze
--task-type=API Creation
--complexity=8
```

**Prompt Sent to Ollama:**
```
Given a task and skills/agents, which are best?

Task Type: API Creation
Complexity: 8
Technologies Detected: Java, Spring Boot, Maven

Available Skills:
- java-spring-boot-microservices
- spring-boot-design-patterns-core
- docker
- kubernetes
- etc.

Available Agents:
- spring-boot-microservices
- java-backend-engineer
- devops-engineer
- etc.

Which skill and agent best match this task?
Respond with JSON: {
  "selected_skill": "...",
  "selected_agent": "...",
  "confidence": 0.95,
  "alternatives": [...]
}
```

**Ollama Response:**
```json
{
  "selected_skill": "java-spring-boot-microservices",
  "selected_agent": "spring-boot-microservices",
  "confidence": 0.95,
  "alternatives": [
    "java-design-patterns-core (for advanced patterns)",
    "java-backend-engineer (for implementation)"
  ],
  "reasoning": "API Creation with JWT auth is core Spring Boot microservices work. This skill directly covers REST API design, Spring Boot patterns, and authentication patterns."
}
```

**Step 5 Output:**
```json
{
  "step5_skill": "java-spring-boot-microservices",
  "step5_agent": "spring-boot-microservices",
  "step5_reasoning": "API Creation with JWT auth is core Spring Boot microservices work.",
  "step5_confidence": 0.95,
  "step5_alternatives": [
    "java-design-patterns-core (for advanced patterns)",
    "java-backend-engineer (for implementation)"
  ],
  "step5_llm_query_needed": false
}
```

---

### STEP 6: Tool Optimization

**Script:** `tool-optimizer-step.py`

**Input:**
```
--context=32.5
```

**Logic:**
```
if context_percentage > 75%:
    hints = "Context high - use offset/limit on large files"
    read_opts = {"limit": 500, "offset": 0}
    grep_opts = {"head_limit": 50}
else:
    hints = "Context normal - read files fully, grep liberally"
    read_opts = {"limit": None}
    grep_opts = {"head_limit": None}
```

**Step 6 Output:**
```json
{
  "step6_tool_hints": [
    "Context usage is 32.5% - normal",
    "Read large files with offset/limit (>500 lines)",
    "Grep can use full results (no head_limit needed)",
    "Safe to do comprehensive code exploration"
  ],
  "step6_read_optimization": {
    "max_lines": 2000,
    "offset_for_large": 0,
    "limit_for_large": 500
  },
  "step6_grep_optimization": {
    "head_limit": null,
    "context_flags": "-C3"
  }
}
```

---

### STEP 7: Auto-Recommendations

**Script:** `recommendations-step.py`

**Input:**
```
--task-type=API Creation
--complexity=8
--context=Create a REST API endpoint for user authentication with JWT tokens...
```

**Prompt Sent to Ollama:**
```
Given the task context, suggest 3-5 best practices for API Creation with JWT auth:

Task Type: API Creation
Complexity: 8
Task: Create a REST API endpoint for user authentication with JWT tokens

Suggest best practices in JSON:
{
  "recommendations": ["practice 1", "practice 2", ...],
  "warnings": ["warning 1", ...],
  "best_practices": ["pattern 1", ...]
}
```

**Ollama Response:**
```json
{
  "recommendations": [
    "Use HTTPS/TLS for all authentication endpoints (never HTTP)",
    "Implement rate limiting on login/register endpoints to prevent brute force",
    "Store JWT secret as environment variable, never hardcode",
    "Add token expiration and refresh token mechanism",
    "Validate JWT signature on every protected endpoint"
  ],
  "best_practices": [
    "Use Spring Security @EnableWebSecurity for centralized auth",
    "Implement custom JwtAuthenticationFilter extending OncePerRequestFilter",
    "Use BCryptPasswordEncoder for password hashing",
    "Return secure error messages (never expose token details)"
  ],
  "warnings": [
    "Don't store sensitive data in JWT claims (passwords, secrets)",
    "Don't hardcode JWT expiration time",
    "Don't skip CORS validation for auth endpoints"
  ]
}
```

**Step 7 Output:**
```json
{
  "step7_recommendations": [
    "Use HTTPS/TLS for all authentication endpoints",
    "Implement rate limiting on login/register endpoints",
    "Store JWT secret as environment variable",
    "Add token expiration and refresh token mechanism",
    "Validate JWT signature on every protected endpoint"
  ],
  "step7_best_practices": [
    "Use Spring Security @EnableWebSecurity for centralized auth",
    "Implement custom JwtAuthenticationFilter",
    "Use BCryptPasswordEncoder for password hashing",
    "Return secure error messages"
  ],
  "step7_warnings": [
    "Don't store sensitive data in JWT claims",
    "Don't hardcode JWT expiration time",
    "Don't skip CORS validation for auth endpoints"
  ]
}
```

---

### STEP 8: Progress Tracking

**Script:** `progress-step.py`

**Input:** None (checks execution state)

**Logic:**
```
Check task progress:
- Completed steps: 8/12
- Percentage: 66%
- Current: Step 8 (Progress Tracking)
- Remaining: 4 steps (tool-opt, git, session-save, failure-prevention)
```

**Step 8 Output:**
```json
{
  "step8_progress": {
    "percentage": 66,
    "completed_steps": 8,
    "total_steps": 12,
    "current_step": 8
  },
  "step8_incomplete_work": [
    "step9_git_commit_preparation",
    "step10_session_save",
    "step11_failure_prevention"
  ]
}
```

---

### STEP 9: Git Commit Preparation

**Script:** `git-step.py`

**Input:** None (checks git status)

**Logic:**
```
run: git status --short
if changes detected:
    commit_ready = true
else:
    commit_ready = false
```

**Step 9 Output:**
```json
{
  "step9_commit_ready": false,
  "step9_commit_message": "No changes to commit",
  "step9_version_bump": "5.2.1 -> 5.2.2"
}
```

---

### STEP 10: Session Save

**Script:** `session-step.py`

**Input:** None (saves current session state)

**Logic:**
```
Save to: ~/.claude/memory/sessions/SESSION-20260310-0305-EFGH/
Include: All FlowState, execution trace, recommendations
```

**Step 10 Output:**
```json
{
  "step10_session": {
    "session_id": "SESSION-20260310-0305-EFGH",
    "timestamp": "2026-03-10T03:05:47",
    "saved": true
  },
  "step10_archive_needed": false
}
```

---

### STEP 11: Failure Prevention

**Script:** `failure-step.py`

**Input:** None (checks system health)

**Logic:**
```
Check for:
- Infinite loops: No
- Memory safety: OK
- Error handling: Present
- Timeouts: Configured
- Logging: Enabled
- Memory directory size: Check if > 1000MB
```

**Step 11 Output:**
```json
{
  "failure_prevention": {
    "no_infinite_loops": true,
    "memory_safe": true,
    "error_handling_present": true,
    "timeout_configured": true,
    "logging_enabled": true
  },
  "failure_prevention_warnings": []
}
```

---

### LEVEL 3 MERGE

All step outputs combined into final state:

```json
{
  "step0_prompt": { "task_type": "API Creation", "complexity": 8, ... },
  "step1_tasks": { "count": 5, "tasks": [...], ... },
  "step2_plan_mode": true,
  "step3_context_read": true,
  "step4_model": "opus",
  "step5_skill": "java-spring-boot-microservices",
  "step5_agent": "spring-boot-microservices",
  "step6_tool_hints": [...],
  "step7_recommendations": [...],
  "step8_progress": { "percentage": 66, ... },
  "step9_commit_ready": false,
  "step10_session": { "saved": true, ... },
  "failure_prevention": { ... },
  "final_status": "OK"
}
```

---

## OUTPUT

### flow-trace.json

Written to `~/.claude/memory/logs/sessions/SESSION-20260310-0305-EFGH/flow-trace.json`

```json
{
  "session_id": "SESSION-20260310-0305-EFGH",
  "timestamp": "2026-03-10T03:05:47",
  "project_root": "/path/to/project",
  "final_status": "OK",
  "user_message": "Create a REST API endpoint for user authentication with JWT tokens",
  "pipeline": [
    {
      "step": "LEVEL_MINUS_1",
      "name": "Auto-Fix Enforcement",
      "status": "OK",
      "policy_output": { ... }
    },
    {
      "step": "LEVEL_1_CONTEXT",
      "name": "Context Management",
      "status": "OK",
      "context_percentage": 32.5,
      "patterns_detected": ["Java Spring Boot", ...]
    },
    {
      "step": "LEVEL_2_STANDARDS",
      "name": "Rules/Standards System",
      "status": "OK",
      "standards_count": 37
    },
    {
      "step": "LEVEL_3_STEP_0",
      "name": "Prompt Generation",
      "status": "OK",
      "task_type": "API Creation",
      "complexity": 8
    },
    {
      "step": "LEVEL_3_STEP_1",
      "name": "Task Breakdown",
      "status": "OK",
      "task_count": 5
    },
    ... (steps 2-11)
  ]
}
```

---

## Summary

**With this fix, the system now:**

1. ✅ **Captures** the actual user message
2. ✅ **Passes it through** the entire pipeline
3. ✅ **Step 0** analyzes task with Ollama LLM
4. ✅ **Steps 1-5** receive real analyzed data
5. ✅ **Steps 6-11** work with real complexity, task count, model, skill, agent
6. ✅ **Output** contains real recommendations based on actual task
7. ✅ **pre-tool-enforcer.py** gets real data for decisions

**Before fix:** Dummy data everywhere → Wrong decisions
**After fix:** Real data throughout → Right decisions
