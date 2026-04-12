# RULES/STANDARDS SYSTEM (Middle Layer)

**PURPOSE:** Load coding standards BEFORE code generation to ensure 100% consistency

---

## Structure: 2 Sub-Levels

### Level 2.1: Common Standards (Always Active)
Universal coding standards that apply to ALL projects regardless of tech stack.

**Loads 12 Standard Categories:**
1. Naming Conventions (camelCase, PascalCase, snake_case, etc.)
2. Error Handling (Common) (no swallowed exceptions, specific types)
3. Logging Standards (structured logging, levels, no sensitive data)
4. Security Basics (no hardcoded secrets, input validation)
5. Code Organization (SRP, DRY, separation of concerns)
6. API Design (Common) (REST conventions, HTTP status codes)
7. Database (Common) (snake_case naming, migrations, parameterized queries)
8. Constants (Common) (no magic numbers/strings)
9. Testing Approach (unit/integration tests, no prod data)
10. Documentation (Common) (comments explain WHY, API docs)
11. Git Standards (meaningful commits, branch naming)
12. File Organization (group by feature, separate config)

**OUTPUT:** ~65 universal rules loaded

### Level 2.2: Microservices Standards (Conditional - Spring Boot)
Spring Boot / Java / microservices specific standards. Only active when Spring Boot is detected.

**Loads 15 Standard Categories:**
1. Java Project Structure (packages, visibility)
2. Config Server Rules (what goes where)
3. Secret Management (never hardcode)
4. Response Format (ApiResponseDto<T>)
5. API Design Standards (REST patterns)
6. Database Standards (naming, audit fields, JPA)
7. Error Handling (global handler, exceptions)
8. Service Layer Pattern (Helper, package-private)
9. Entity Pattern (audit fields, lifecycle)
10. Controller Pattern (validation, responses)
11. Constants Organization (no magic strings)
12. Common Utilities (reusable code)
13. Documentation Standards (README structure)
14. Kubernetes Network Policies (3-layer architecture)
15. K8s/Docker/Jenkins Infrastructure (deployment archetypes)

**OUTPUT:** ~139 Spring Boot microservices rules loaded

---

## Files in This Folder

### Policies:
- `common-standards-policy.md` - Level 2.1: Universal standards (always active)
- `coding-standards-enforcement-policy.md` - Level 2.2: Microservices standards (conditional)

### Scripts:
- `standards-loader.py` - Load standards via CLI

---

## Usage

```bash
# Load common standards only (Level 2.1)
python standards-loader.py --load-common

# Load microservices standards only (Level 2.2)
python standards-loader.py --load-microservices

# Load all standards (backward compatible)
python standards-loader.py --load-all
```

**Output (Level 2.1):**
```
[2.1] COMMON STANDARDS LOADER (Universal)
======================================================================
  [1/12] Naming Conventions... [CHECK] Loaded
  ...
  [12/12] File Organization... [CHECK] Loaded

Common Standards: 12
Common Rules Loaded: 65
```

**Output (Level 2.2 - only if Spring Boot):**
```
[2.2] MICROSERVICES STANDARDS LOADER (Spring Boot)
======================================================================
  [1/15] Java Project Structure... [CHECK] Loaded
  ...
  [15/15] K8s/Docker/Jenkins Infrastructure... [CHECK] Loaded

Microservices Standards: 15
Microservices Rules Loaded: 139
```

---

## Dependencies

**Depends on:**
- Sync System (must run after)
- Tech Stack Detection (determines if Level 2.2 runs)

**Used by:**
- Execution System (provides standards)

---

## Integration

**Position in Flow:**
```
SYNC SYSTEM (Context + Session)
        |
LEVEL 2.1: COMMON STANDARDS (always)  <- 12 standards, ~65 rules
        |
LEVEL 2.2: MICROSERVICES (conditional) <- 15 standards, ~139 rules
        |
EXECUTION SYSTEM (Follow standards)
```

---

**STATUS:** ACTIVE
**PRIORITY:** CRITICAL (Must run before execution)
