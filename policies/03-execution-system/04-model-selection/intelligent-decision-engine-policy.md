# Intelligent Decision Engine Policy (v1.0.0)

**Script:** `scripts/architecture/03-execution-system/04-model-selection/intelligent-decision-engine.py`
**Pipeline Step:** 3.3A (after Context Check, before Model Selection)
**Type:** MANDATORY - no fallback to keyword-based system
**LLM Provider:** OpenRouter (free models)

---

## Purpose

Replaces ALL keyword-based guessing in Level 3 with a single OpenRouter LLM call
that makes intelligent decisions based on full context understanding.

Previously, 4 separate keyword-based systems made decisions independently:
1. Prompt Generator - task type via keyword matching
2. Complexity Scorer - keyword + graph weighted scoring
3. Model Selector - threshold-based rules
4. Skill/Agent Selector - 4-layer keyword waterfall

Now ONE LLM call replaces all of them with semantic understanding.

---

## Pipeline Position

```
Step 3.0    Prompt Generation     -> basic analysis (still runs, feeds data)
Step 3.0.0  Context Reader        -> README, SRS, tech stack
Step 3.1    Task Breakdown        -> task phases
Step 3.2    Context Check         -> context window %

Step 3.3A   DECISION ENGINE (NEW) -> LLM makes ALL decisions
                                     Overrides Step 3.4 and 3.5

Step 3.4    Model Selection       -> USES LLM decision (or fallback)
Step 3.5    Skill/Agent Selection  -> USES LLM decision (or fallback)
```

---

## Input (Master Context)

The engine receives ALL collected data (~500 tokens):

| Field | Source | Example |
|-------|--------|---------|
| user_message | Raw user prompt | "Create JWT auth API for Spring Boot" |
| keyword_task_type | prompt-generator.py | "API Creation" |
| keyword_complexity | keyword + graph combined | 15 |
| tech_stack | context-reader.py | ["spring-boot", "java", "jwt"] |
| keywords | prompt-generator.py | ["authentication", "api"] |
| context_pct | context-monitor.py | 65 |
| task_count | task-breakdown.py | 3 |
| plan_required | plan-mode check | false |
| project_name | Path.cwd().name | "claude-insight" |

---

## Output (LLM Decision)

```json
{
  "task_type": "Authentication",
  "complexity": 15,
  "model": "SONNET",
  "model_reasoning": "JWT auth implementation needs balanced reasoning",
  "agent_name": "spring-boot-microservices",
  "agent_type": "agent",
  "agent_reasoning": "Spring Boot JWT requires full microservices agent",
  "supplementary_skills": ["java-spring-boot-microservices"],
  "confidence": 0.95,
  "llm_model_used": "meta-llama/llama-3.3-70b-instruct:free",
  "engine_version": "1.0.0",
  "duration_ms": 1200
}
```

---

## Rules

### R1: Mandatory Pipeline Step
- If the LLM call fails, the pipeline output records FAILED status
- All 3 free models are tried before failure
- Timeout: 20 seconds per model attempt

### R2: Valid Registry Only
- agent_name MUST exist in AVAILABLE_AGENTS or AVAILABLE_SKILLS
- supplementary_skills filtered against AVAILABLE_SKILLS
- Invalid names from LLM are rejected (next model tried)

### R3: Plan Mode Override
- If plan_required=True, model is ALWAYS forced to OPUS
- LLM model recommendation is overridden post-decision

### R4: Model Selection Guide
- HAIKU: complexity < 5, simple tasks
- SONNET: complexity 5-19, most coding tasks
- OPUS: complexity >= 20, architecture, security-critical

### R5: Language Understanding
- LLM understands English, Hinglish, informal language
- No keyword matching needed - semantic intent understanding

---

## OpenRouter Models (Free Tier)

Priority order (tried sequentially on failure):

1. `meta-llama/llama-3.3-70b-instruct:free` - Best accuracy
2. `qwen/qwen3-coder:free` - Code-specialized
3. `mistralai/mistral-small-3.1-24b-instruct:free` - Fast fallback

API Key Location: `~/.claude/config/openrouter-api-key`

---

## Available Registries

### Agents (12)
| Agent | Domain |
|-------|--------|
| spring-boot-microservices | Java/Spring Boot backend |
| ui-ux-designer | UI/UX, dashboards, CSS |
| angular-engineer | Angular/TypeScript |
| devops-engineer | Docker, K8s, Jenkins |
| qa-testing-agent | Testing, QA |
| android-backend-engineer | Android/Kotlin |
| swiftui-designer | iOS/SwiftUI |
| swift-backend-engineer | Swift server-side |
| orchestrator-agent | Multi-service coordination |
| dynamic-seo-agent | SEO for dynamic apps |
| static-seo-agent | SEO for static sites |
| python-backend-engineer | Python Flask/Django/FastAPI |

### Skills (13)
| Skill | Domain |
|-------|--------|
| java-spring-boot-microservices | Spring Boot patterns |
| spring-boot-design-patterns-core | Java design patterns |
| java-design-patterns-core | GoF/SOLID patterns |
| docker | Dockerfile, compose |
| kubernetes | K8s manifests, helm |
| jenkins-pipeline | Jenkinsfile, CI/CD |
| rdbms-core | SQL, PostgreSQL, MySQL |
| nosql-core | MongoDB, Elasticsearch |
| css-core | CSS layouts, responsive |
| animations-core | CSS/JS animations |
| seo-keyword-research-core | SEO keywords |
| python-system-scripting | Python scripting |
| adaptive-skill-intelligence | System/meta tasks |

---

## Logging

Log file: `~/.claude/memory/logs/llm-decision-engine.log`

All LLM calls, attempts, successes, and failures are logged with timestamps.

---

## Testing

```bash
# Quick test with a message
python intelligent-decision-engine.py --test "Create a REST API for user management"

# Test with full context JSON
python intelligent-decision-engine.py context.json
```

---

**Version:** 1.0.0
**Created:** 2026-03-08
