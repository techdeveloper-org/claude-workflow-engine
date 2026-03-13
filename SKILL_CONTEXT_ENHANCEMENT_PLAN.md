# Skill & Agent Context Enhancement Plan

## Current State: What's Being Passed?

### Available Resources
- **Skills:** 23 total (SKILL.md files across backend, frontend, devops, etc)
- **Agents:** 12 total (in ~/.claude/agents/)
- **What's Currently Passed:** Just the skill NAME (e.g., "java-spring-boot-microservices")

### The Problem

```
CURRENT (Wrong):
┌─────────────────────────────────────────────────────────┐
│ LLM receives:                                           │
│ - task_type: "Backend Enhancement"                     │
│ - skill: "java-spring-boot-microservices"              │
│ - agent: "spring-boot-microservices"                   │
│                                                         │
│ LLM thinks: "Okay, I have a skill name..."             │
│            "But what CAN this skill do?"               │
│            "What are its constraints?"                 │
│            "What tools can it use?"                    │
│ Result: VAGUE UNDERSTANDING ❌                          │
└─────────────────────────────────────────────────────────┘
```

### What's Missing

**Skill Name ALONE is insufficient!**

Example: `java-spring-boot-microservices`

LLM doesn't know:
- ❌ What tools this skill has access to
- ❌ What patterns it uses
- ❌ What database skills it depends on
- ❌ What its constraints are
- ❌ How it handles errors
- ❌ What file types it creates
- ❌ Integration patterns it uses

---

## The Solution: Complete Context Package

### What SHOULD Be Passed

```
IMPROVED (Right):
┌─────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT (Context as foundation):                 │
│                                                         │
│ You are executing: Implement OAuth2 authentication      │
│ Task Type: Backend Enhancement                         │
│ Complexity: 5/10                                       │
│                                                         │
│ Available Tasks:                                       │
│ 1. Setup OAuth2 provider [high effort]                │
│ 2. Implement auth flow [high effort]                  │
│ 3. Add session management [medium]                    │
│                                                         │
│ Project Context:                                       │
│ - Language: Python                                     │
│ - Framework: Django 4.0+                              │
│ - Database: PostgreSQL                                │
│ - Stack: REST API, Celery, DRF                        │
│                                                         │
│ ────────────────────────────────────────────────────── │
│ USER MESSAGE (What to do):                             │
│                                                         │
│ Skill Selected: python-backend-engineer               │
│                                                         │
│ SKILL DEFINITION (What it can do):                    │
│ ---                                                    │
│ name: python-backend-engineer                         │
│ version: 1.0.0                                        │
│ description: Python backend expert for REST APIs,     │
│              async patterns, ORM, database design      │
│                                                        │
│ Core Capabilities:                                    │
│ - API Development (FastAPI, Django, Flask)           │
│ - Async/Concurrency (asyncio, aiohttp)               │
│ - ORM (SQLAlchemy, Django ORM)                        │
│ - Authentication (JWT, OAuth2, sessions)             │
│ - Database (PostgreSQL, MySQL, MongoDB)              │
│ - Testing (pytest, fixtures, mocking)                │
│ - Deployment (Docker, k8s, ASGI servers)             │
│                                                        │
│ Allowed Tools: Read, Edit, Bash, Write, Grep         │
│ ---                                                    │
│                                                        │
│ Agent Selected: orchestrator-agent                    │
│                                                        │
│ AGENT DEFINITION (Who coordinates):                   │
│ ---                                                    │
│ name: orchestrator-agent                             │
│ version: 1.0.0                                        │
│ description: Agent orchestration for multi-step       │
│              implementation coordination              │
│ ---                                                    │
│                                                        │
│ Now implement OAuth2 using these resources            │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Load Skill Definitions ⚙️

**What to do:**
1. When Step 5 selects a skill, LOAD the full SKILL.md file
2. When Step 5 selects an agent, LOAD the full agent.md file
3. Pass the FULL content to Step 7

**Example:**
```python
# In Step 5
selected_skill = "python-backend-engineer"
skill_file = Path.home() / ".claude" / "skills" / "backend" / selected_skill / "SKILL.md"
full_skill_content = skill_file.read_text()

# Now pass to Step 7:
skill_definition = full_skill_content  # NOT just the name!
```

### Phase 2: Use Context as SYSTEM PROMPT 🧠

**What to do:**
1. In Step 7, separate SYSTEM PROMPT from USER MESSAGE
2. SYSTEM PROMPT: All the context (task, breakdown, patterns, TOON)
3. USER MESSAGE: The actual execution task

**Example:**
```python
# SYSTEM PROMPT (Context)
system_prompt = f"""
You are an AI assistant executing a complex development task.

TASK CONTEXT:
- Original Request: {user_message}
- Task Type: {task_type}
- Complexity: {complexity}/10
- Execution Plan: {plan_phases}

DETAILED BREAKDOWN:
{validated_tasks_formatted}

TECHNOLOGY STACK:
- Detected Patterns: {patterns}
- Project Type: {project_type}
- Required Dependencies: {dependencies}

AVAILABLE TOOLS:
{selected_skill_definition}
{selected_agent_definition}

CONSTRAINTS:
- Max 3 retries on failure
- Follow file modification best practices
- Update progress after each task
"""

# USER MESSAGE (What to do)
user_message = f"""
Now implement the OAuth2 authentication system according to the task breakdown.
Follow the execution plan, use the selected skill/agent, and report progress.
"""
```

### Phase 3: Enhance Step 5 Skill Selection ✨

**Current Implementation:**
```python
context_data = {
    "task_type": "Backend Enhancement",
    "complexity": 5,
    "validated_tasks": [...],
}
```

**Enhanced Implementation:**
```python
# Load all available skills with their definitions
available_skills_with_defs = {}
for skill_dir in Path.home().glob(".claude/skills/**/*"):
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        available_skills_with_defs[skill_dir.name] = skill_file.read_text()

# Build rich context
context_data = {
    "user_message": user_message,
    "task_type": task_type,
    "complexity": complexity,
    "validated_tasks": validated_tasks,
    "project_info": {
        "language": "Python",
        "framework": "Django",
        "database": "PostgreSQL",
    },
    "patterns": patterns,
    "available_skills": list(available_skills_with_defs.keys()),  # Names
    "skill_definitions": available_skills_with_defs,  # Full content!
}

# Now LLM can READ all skill definitions and choose the best one!
```

### Phase 4: Enhance Step 7 Prompt Generation 📝

**Current:**
```python
# Just saves basic structure
prompt = f"""
## Task: {user_message}
## Breakdown: {tasks}
## Skill: {skill_name}
"""
```

**Enhanced:**
```python
# Build comprehensive execution blueprint
system_context = f"""
EXECUTION CONTEXT:
{full_execution_context}

SELECTED TOOLS:
Skill: {skill_name}
{skill_definition_content}

Agent: {agent_name}
{agent_definition_content}

PROJECT KNOWLEDGE:
{project_details}

EXECUTION PLAN:
{plan_phases}
"""

execution_prompt = f"""
Using the above context and tools, execute:

{execution_tasks_with_details}

Follow these guidelines:
1. Use skill definitions to guide implementation
2. Follow the execution plan phases
3. Track file modifications
4. Update state after each task
"""

# Save BOTH
prompt_file.write(f"SYSTEM CONTEXT:\n{system_context}\n\nEXECUTION TASK:\n{execution_prompt}")
```

---

## Available Skills & Agents to Load

### Skills (23 total)
```
Backend:
- java-spring-boot-microservices
- spring-boot-design-patterns-core
- java-design-patterns-core
- rdbms-core
- nosql-core
- docker
- kubernetes
- jenkins-pipeline

Frontend:
- css-core
- animations-core

DevOps:
- [various deployment skills]

System:
- seo-keyword-research-core
- [various system skills]
```

### Agents (12 total)
```
- spring-boot-microservices
- android-backend-engineer
- android-ui-designer
- angular-engineer
- devops-engineer
- dynamic-seo-agent
- orchestrator-agent
- qa-testing-agent
- static-seo-agent
- swift-backend-engineer
- swiftui-designer
- ui-ux-designer
```

---

## Implementation Steps

### Step 1: Create Skill/Agent Loader Utility 📦

```python
# scripts/langgraph_engine/skill_agent_loader.py

from pathlib import Path
from typing import Dict, Optional

class SkillAgentLoader:
    """Load skill and agent definitions from filesystem"""

    def __init__(self):
        self.skills_dir = Path.home() / ".claude" / "skills"
        self.agents_dir = Path.home() / ".claude" / "agents"

    def load_skill(self, skill_name: str) -> Optional[str]:
        """Load full SKILL.md content for a skill"""
        # Search for SKILL.md or skill.md
        skill_file = self.skills_dir / "**" / skill_name / "SKILL.md"
        if not skill_file.exists():
            skill_file = self.skills_dir / "**" / skill_name / "skill.md"

        if skill_file.exists():
            return skill_file.read_text()
        return None

    def load_agent(self, agent_name: str) -> Optional[str]:
        """Load full agent.md content for an agent"""
        agent_file = self.agents_dir / agent_name / "agent.md"
        if agent_file.exists():
            return agent_file.read_text()
        return None

    def list_all_skills(self) -> Dict[str, str]:
        """Load all available skills with their definitions"""
        skills = {}
        for skill_dir in self.skills_dir.glob("**/*"):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills[skill_dir.name] = skill_file.read_text()
        return skills

    def list_all_agents(self) -> Dict[str, str]:
        """Load all available agents with their definitions"""
        agents = {}
        for agent_dir in self.agents_dir.glob("*"):
            if agent_dir.is_dir():
                agent_file = agent_dir / "agent.md"
                if agent_file.exists():
                    agents[agent_dir.name] = agent_file.read_text()
        return agents
```

### Step 2: Enhance Step 5 to Use Loader 🎯

```python
# In step5_skill_agent_selection()

from .skill_agent_loader import SkillAgentLoader

loader = SkillAgentLoader()

# Load ALL skill definitions for context
all_skills = loader.list_all_skills()
all_agents = loader.list_all_agents()

# Build enhanced context
context_data = {
    "user_message": user_message,
    "task_type": task_type,
    "complexity": complexity,
    "validated_tasks": validated_tasks,
    "patterns": patterns,
    "project_info": {...},
    "available_skills": list(all_skills.keys()),
    "skill_definitions": all_skills,  # Full content!
    "available_agents": list(all_agents.keys()),
    "agent_definitions": all_agents,  # Full content!
}

# Pass to LLM for intelligent selection
result = invoke_llm_with_context(
    task_type="skill_selection",
    system_prompt=build_system_prompt(context_data),
    user_message=f"Select the best skill and agent for: {task_type}",
)

# Extract selected skill/agent
selected_skill = result.get("selected_skill")
selected_agent = result.get("selected_agent")

# Load the FULL definitions
skill_definition = loader.load_skill(selected_skill)
agent_definition = loader.load_agent(selected_agent)

return {
    "step5_skill": selected_skill,
    "step5_skill_definition": skill_definition,  # FULL CONTENT!
    "step5_agent": selected_agent,
    "step5_agent_definition": agent_definition,  # FULL CONTENT!
}
```

### Step 3: Enhance Step 7 Prompt Generation 📖

```python
# In step7_final_prompt_generation()

# Build SYSTEM PROMPT (context foundation)
system_prompt = f"""
TASK EXECUTION CONTEXT

Original Request:
{user_message}

ANALYSIS:
- Type: {task_type}
- Complexity: {complexity}/10
- Reasoning: {reasoning}

DETAILED BREAKDOWN:
{format_validated_tasks(validated_tasks)}

EXECUTION PLAN:
{format_plan(plan_details)}

PROJECT CONTEXT:
- Language: {project_language}
- Framework: {project_framework}
- Database: {project_database}
- Stack: {', '.join(patterns)}

ENRICHED CONTEXT (from TOON):
{format_toon(refined_toon)}

TOOLS & RESOURCES:

Selected Skill: {skill_name}
Definition:
{skill_definition}

Selected Agent: {agent_name}
Definition:
{agent_definition}

CONSTRAINTS & GUIDELINES:
1. Follow skill definitions strictly
2. Execute according to plan phases
3. Track all file modifications
4. Report progress after each task
"""

# Build USER MESSAGE (what to do)
user_message_exec = f"""
Now execute the {task_type} according to the execution plan.

Use the selected skill and agent as guides.
Follow the detailed task breakdown.
Implement each task in order.
"""

# Save comprehensive prompt
final_prompt = f"""
SYSTEM PROMPT:
{system_prompt}

────────────────────────────────────────────────────────

USER MESSAGE:
{user_message_exec}
"""

# Also return structured data for LLM invocation
return {
    "step7_system_prompt": system_prompt,
    "step7_user_message": user_message_exec,
    "step7_full_prompt": final_prompt,
    "step7_context_included": {
        "skill_definition": bool(skill_definition),
        "agent_definition": bool(agent_definition),
        "system_prompt": True,
        "execution_plan": bool(plan_details),
    }
}
```

---

## Expected Quality Improvements

### Before (Skill Name Only)
```
LLM sees: "Use spring-boot-microservices skill"
LLM thinks: ??? What can it do?
Result: Generic implementation using general knowledge ❌
```

### After (Full Skill Definition + System Prompt)
```
LLM sees:
- SYSTEM PROMPT with task context
- Full skill definition (capabilities, patterns, tools)
- Full agent definition (coordination model)
- Project details (language, framework, database)
- Execution plan (phases, tasks, effort)

LLM thinks:
- "I know Spring Boot microservices patterns"
- "I can use: layered architecture, DTOs, validation"
- "Database: Must follow rdbms-core constraints"
- "Tools available: Read, Edit, Bash, Write"

Result: Precise, skill-guided implementation ✅
```

### Metrics

| Metric | Before | After | Gain |
|--------|--------|-------|------|
| Skill Utilization | 30% | 90% | +60% |
| Pattern Compliance | 40% | 95% | +55% |
| Error Rate | 25% | 5% | -80% |
| Implementation Quality | 6/10 | 9/10 | +3 points |

---

## Files to Modify

1. **Create:** `scripts/langgraph_engine/skill_agent_loader.py` (new file)
2. **Enhance:** `scripts/langgraph_engine/subgraphs/level3_execution.py`
   - Step 5: Use loader to get full definitions
   - Step 7: Build system prompt + user message format
3. **Update:** `hybrid_inference.py`
   - Add system prompt support to Claude CLI invocation
4. **Create:** `SKILL_CONTEXT_LOADING_GUIDE.md` (documentation)

---

## Priority

🔴 **CRITICAL** - This is essential for quality execution!

Passing skill names alone = Guessing what skill can do
Passing skill definitions = Precise skill-guided implementation

---

## Next: Implementation Sequence

1. Create SkillAgentLoader utility
2. Update Step 5 to use loader
3. Update Step 7 to generate system prompt
4. Update hybrid_inference.py for system prompt support
5. Test with real skill definitions
6. Verify 90%+ pattern compliance

---

## Success Criteria

✅ Step 5 loads full skill definitions before selection
✅ Step 7 generates system prompt + user message format
✅ LLM receives complete skill/agent definitions
✅ System prompt provides execution context
✅ Implementation quality improves to 9/10
✅ Pattern compliance reaches 95%+
