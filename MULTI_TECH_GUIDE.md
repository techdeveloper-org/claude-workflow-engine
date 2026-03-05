# Multi-Tech Skill/Agent Selection Guide

**Version:** 3.3.0
**Last Updated:** 2026-03-05

---

## Quick Overview

The Claude Insight system now automatically:

1. **Detects ALL technologies** in your task (not just file extensions)
2. **Selects appropriate agents/skills** based on complete tech stack
3. **Escalates to orchestrator-agent** for multi-domain projects
4. **Shows task context** in every file-level hint

---

## How It Works: Step by Step

### 1. Task Breakdown (Your Message)
```
User: "Implement JWT auth in Spring Boot API + Angular frontend + Docker deployment"
       ↓
Detected: ['spring-boot', 'angular', 'docker']
Tech Stack: Multi-domain (backend + frontend + devops)
```

### 2. Phase Detection (Tech-Aware)
```
Spring Boot (backend) detected → Use Backend-Specific Phases:
  ✓ Foundation
  ✓ Business Logic
  ✓ API Layer
  ✓ Configuration

Angular (frontend) detected → Could use Frontend-Specific Phases:
  ✓ Structure
  ✓ Styling
  ✓ Components
  ✓ Integration

DevOps (Docker) detected → Could use DevOps-Specific Phases:
  ✓ Containerization
  ✓ Orchestration
  ✓ Pipeline
  ✓ Monitoring
```

### 3. Skill/Agent Selection (Multi-Domain Logic)
```
Detected agents:
  - spring-boot-microservices (backend)
  - angular-engineer (frontend)
  - devops-engineer (devops)

Multi-domain rule triggered (3 domains detected)
  ↓
Primary agent: orchestrator-agent ⭐
Supplementary: spring-boot-microservices, angular-engineer, devops-engineer
```

### 4. Session-Level Context
```
Session context stored in flow-trace.json:
  - task_type: "API Development"
  - complexity: 18
  - model: "sonnet"
  - skill: "orchestrator-agent" ← Primary
  - tech_stack: ['spring-boot', 'angular', 'docker']
  - supplementary_skills: [spring-boot-microservices, angular-engineer, devops-engineer]
```

### 5. File-Level Hints (When You Edit)
```
User reads: UserController.java
  ↓
[SKILL-CONTEXT] UserController.java -> java-spring-boot-microservices (skill)
  CONTEXT: Java/Spring Boot patterns, annotations, DI, REST controllers
  TASK TECH STACK: spring-boot, angular, docker
  SESSION PRIMARY: orchestrator-agent
  OTHER FILES IN THIS TASK: .ts -> angular-engineer | Dockerfile -> docker
  ACTION: Apply java-spring-boot-microservices patterns for this file.

User reads: auth.component.ts
  ↓
[SKILL-CONTEXT] auth.component.ts -> angular-engineer (agent)
  CONTEXT: TypeScript/Angular components, services, modules, RxJS
  TASK TECH STACK: spring-boot, angular, docker
  SESSION PRIMARY: orchestrator-agent
  OTHER FILES IN THIS TASK: .java -> java-spring-boot-microservices | Dockerfile -> docker
  ACTION: Apply angular-engineer patterns for this file.

User reads: Dockerfile
  ↓
[SKILL-CONTEXT] Dockerfile -> docker (skill)
  CONTEXT: Docker image definitions, multi-stage builds, optimization
  TASK TECH STACK: spring-boot, angular, docker
  SESSION PRIMARY: orchestrator-agent
  OTHER FILES IN THIS TASK: .java -> java-spring-boot-microservices | .ts -> angular-engineer
  ACTION: Apply docker patterns for this file.
```

---

## Technology Recognition

The system recognizes 23+ technologies:

### Backend
- `spring-boot`, `java` → java-spring-boot-microservices
- `python`, `flask`, `django`, `fastapi` → python-backend-engineer
- `nodejs` → adaptive-skill-intelligence

### Frontend
- `angular`, `typescript` → angular-engineer
- `react`, `vue` → ui-ux-designer
- `css`, `scss`, `html` → css-core, ui-ux-designer

### Mobile
- `kotlin`, `android` → android-backend-engineer
- `swift`, `ios`, `swiftui` → swift-backend-engineer

### DevOps
- `docker` → devops-engineer, docker skill
- `kubernetes`, `k8s` → devops-engineer, kubernetes skill
- `jenkins`, `ci/cd` → devops-engineer, jenkins-pipeline skill

### Database
- `postgresql`, `mysql` → rdbms-core
- `mongodb` → nosql-core
- `redis` → redis (caching)

### Other
- `seo` → dynamic-seo-agent
- `testing`, `test` → qa-testing-agent

---

## Multi-Domain Escalation Rules

### When orchestrator-agent Activates

The system automatically selects `orchestrator-agent` as primary when you mention 2+ of these domains:

1. **FRONTEND**: angular, typescript, react, vue, css, scss, html
2. **BACKEND**: python, flask, django, fastapi, java, spring-boot, kotlin, swift
3. **DEVOPS**: docker, kubernetes, jenkins, ci/cd

### Examples

```
"Add JWT auth to Spring Boot + Angular app"
  Domains: BACKEND (spring-boot) + FRONTEND (angular)
  Result: orchestrator-agent ⭐

"Deploy Python API to Kubernetes with Docker"
  Domains: BACKEND (python) + DEVOPS (docker, kubernetes)
  Result: orchestrator-agent ⭐

"Implement SEO for React app"
  Domains: FRONTEND (react) only
  Result: ui-ux-designer (single domain, no escalation)

"Create User entity in Spring Boot"
  Domains: BACKEND (spring-boot) only
  Result: spring-boot-microservices (single domain, no escalation)
```

---

## What You'll See

### Single-Tech Task (No Escalation)
```
Session Information:
  Model: haiku
  Complexity: 10
  Primary Skill: java-spring-boot-microservices
  Supplementary: [rdbms-core]

File hints show single skill + basic context
```

### Multi-Tech Task (With Escalation)
```
Session Information:
  Model: sonnet (note: complexity warrants better reasoning)
  Complexity: 18
  Primary Skill: orchestrator-agent ⭐
  Supplementary: [java-spring-boot-microservices, angular-engineer, devops-engineer]

File hints show:
  1. Which skill to use FOR THIS FILE
  2. ALL technologies in the task
  3. Which agent/skill is coordinating (SESSION PRIMARY)
  4. What OTHER files will be touched and by whom (OTHER FILES IN THIS TASK)
```

---

## Best Practices

### ✅ DO

1. **Be specific about technologies:**
   - "Add JWT auth using Flask" (not just "add auth")
   - "Style with Tailwind CSS" (not just "add styling")
   - "Deploy with Docker + Kubernetes" (not just "deploy")

2. **Let the system detect orchestration:**
   - No need to ask for orchestrator-agent
   - Just mention multiple technologies
   - System automatically escalates

3. **Use tech-aware file hints:**
   - Read the "OTHER FILES IN THIS TASK" line
   - Understand which technologies will be touched by which experts
   - Coordinate changes across technologies

### ❌ DON'T

1. **Don't be vague:**
   - ❌ "Make it work with APIs" (which API? which framework?)
   - ✅ "Add REST API using Spring Boot with PostgreSQL"

2. **Don't assume single-domain:**
   - ❌ Only mention frontend, but need backend too
   - ✅ Mention all tech: "React frontend + Node.js backend + PostgreSQL"

3. **Don't ignore orchestrator hints:**
   - Pay attention when SESSION PRIMARY shows orchestrator-agent
   - This means expert coordination across multiple technologies
   - Claude will coordinate between expert agents automatically

---

## Phase Names by Technology

### Python Backend (Flask/Django/FastAPI)
1. Setup - Project structure and dependencies
2. Data Layer - Database models and ORM
3. Logic - Business logic and services
4. Endpoints - API endpoints and routing

### Frontend (Angular/React/Vue)
1. Structure - HTML layout and components
2. Styling - CSS and responsive design
3. Components - Interactive components
4. Integration - API integration and routing

### DevOps (Docker/Kubernetes/Jenkins)
1. Containerization - Docker/container setup
2. Orchestration - Kubernetes deployment
3. Pipeline - CI/CD pipeline configuration
4. Monitoring - Observability and monitoring

### Java/Spring Boot (Default)
1. Foundation - Entities and repositories
2. Business Logic - Service layer implementation
3. API Layer - Controllers and DTOs
4. Configuration - Config files and properties

---

## Real-World Examples

### Example 1: Full Stack CRUD API

```
User: "Implement a product management CRUD API with Angular UI, Spring Boot backend, PostgreSQL database, and Docker deployment"

System Detection:
  Technologies: [spring-boot, angular, postgresql, docker]
  Domains: BACKEND + FRONTEND + DEVOPS (3 domains)
  Primary: orchestrator-agent ⭐

Phases Generated:
  1. Foundation (entities, repositories)
  2. Business Logic (service layer)
  3. API Layer (controllers, DTOs)
  4. Configuration (app config, Docker setup)

Session Info:
  Model: sonnet (complexity 20/25 requires deeper reasoning)
  Primary: orchestrator-agent
  Supplementary: [
    java-spring-boot-microservices,
    angular-engineer,
    rdbms-core,
    docker
  ]

File Hints:
  ProductEntity.java → java-spring-boot-microservices
  ProductService.java → java-spring-boot-microservices
  ProductController.java → java-spring-boot-microservices + OTHER: .ts → angular-engineer | .sql → rdbms-core | Dockerfile → docker
  product.component.ts → angular-engineer + OTHER: .java → java-spring-boot-microservices | schema.sql → rdbms-core | Dockerfile → docker
  schema.sql → rdbms-core + OTHER: .java → java-spring-boot-microservices | .ts → angular-engineer | Dockerfile → docker
  Dockerfile → docker + OTHER: .java → java-spring-boot-microservices | .ts → angular-engineer | .sql → rdbms-core
```

### Example 2: Python API with DevOps

```
User: "Create a FastAPI REST service for user authentication with JWT, deploy to Kubernetes with Prometheus monitoring"

System Detection:
  Technologies: [fastapi, python, kubernetes, docker]
  Domains: BACKEND + DEVOPS (2 domains)
  Primary: orchestrator-agent ⭐

Phases Generated:
  1. Setup - Project and dependencies
  2. Data Layer - Database models
  3. Logic - Auth logic and JWT handling
  4. Endpoints - Auth endpoints

Session Info:
  Model: sonnet
  Primary: orchestrator-agent
  Supplementary: [
    python-backend-engineer,
    devops-engineer,
    kubernetes,
    docker
  ]

File Hints Show:
  auth.py → python-backend-engineer + OTHER: Dockerfile → docker | k8s-deployment.yaml → kubernetes
  Dockerfile → docker + OTHER: auth.py → python-backend-engineer | k8s-deployment.yaml → kubernetes
  k8s-deployment.yaml → kubernetes + OTHER: auth.py → python-backend-engineer | Dockerfile → docker
```

### Example 3: UI Enhancement (No Escalation)

```
User: "Add dark mode toggle to React components with Tailwind CSS"

System Detection:
  Technologies: [react, css]
  Domains: FRONTEND only (1 domain)
  Primary: ui-ux-designer (NO escalation)

Phases Generated:
  1. Structure - Components
  2. Styling - CSS and themes
  3. Components - Dark mode toggle
  4. Integration - State management

Session Info:
  Model: haiku (low complexity 8/25, quick reasoning sufficient)
  Primary: ui-ux-designer
  Supplementary: [css-core]

File Hints:
  theme.context.tsx → ui-ux-designer + OTHER: .css → css-core
  styles.css → css-core + OTHER: .tsx → ui-ux-designer
```

---

## Troubleshooting

### Q: Why am I seeing orchestrator-agent when I don't expect it?
**A:** You mentioned 2+ domains. Check:
- Spring Boot (backend) + styling (frontend) = 2 domains ✓
- Docker (devops) + Flask (backend) = 2 domains ✓
- Angular (frontend) + CSS (still frontend) = 1 domain ✗

### Q: Why aren't OTHER FILES shown in hints?
**A:** Possible reasons:
1. Only 1 technology in task (nothing "other" to show)
2. Technology not in `_TECH_TO_FILE_SKILL` mapping
3. Other technology mapped to same skill as current file (skipped to avoid duplication)

### Q: Why is complexity high for a simple task?
**A:** Complexity calculation includes:
- Entity count
- File count estimate
- Technology stack size
- Detected domains

Multi-tech projects are inherently more complex.

### Q: How do I avoid orchestrator-agent escalation?
**A:** Simply don't mention multiple domains:
- ✅ "Create Spring Boot REST API" (backend only)
- ❌ "Create Spring Boot REST API with Angular UI" (backend + frontend)

---

## Related Documentation

- **Policy:** `policies/03-execution-system/05-skill-agent-selection/`
- **Architecture:** `scripts/architecture/03-execution-system/05-skill-agent-selection/`
- **Implementation:** `SKILL_AGENT_ENHANCEMENT_SUMMARY.md`

---

**Questions?** Refer to the policy and architecture files for detailed technical specifications.
