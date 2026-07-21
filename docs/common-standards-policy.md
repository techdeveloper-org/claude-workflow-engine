# Common Standards Enforcement Policy (Level 2.1)

**VERSION:** 1.0.0
**CREATED:** 2026-03-02
**PRIORITY:** CRITICAL - Always Active
**STATUS:** ACTIVE

---

## POLICY OVERVIEW

**PURPOSE:** Enforce universal coding standards that apply to ALL projects, regardless of tech stack.

**POSITION IN FLOW:**
```
Sync System (Context + Session)
        |
LEVEL 2.1: COMMON STANDARDS (THIS POLICY) <- Always active
        |
LEVEL 2.2: MICROSERVICES STANDARDS        <- Only if Spring Boot detected
        |
Execution System (Policies + Implementation)
```

**MANDATORY:** Level 2.1 ALWAYS runs. These are language-agnostic, universal best practices.

---

## 12 COMMON STANDARD CATEGORIES

### 1. Naming Conventions
- Variables and functions: camelCase
- Classes and types: PascalCase
- Constants: UPPER_SNAKE_CASE
- Database tables/columns: snake_case
- API endpoints: kebab-case plural nouns
- Booleans: prefix with is/has/can/should
- NEVER use abbreviations unless universally known (id, url, api)

### 2. Error Handling (Common)
- NEVER swallow exceptions silently (empty catch blocks)
- Catch specific exception types, not generic Exception/Error
- Include context in error messages (what operation failed)
- Log errors at the handling point with stack trace
- Use appropriate error codes/status for each error type
- NEVER expose internal details (stack traces, SQL) to end users

### 3. Logging Standards
- Use structured logging (key-value pairs, not free text)
- Include correlation/request ID in all log entries
- Use appropriate log levels (ERROR for failures, INFO for events)
- NEVER log sensitive data (passwords, tokens, PII)
- NEVER log at DEBUG level in production by default

### 4. Security Basics
- NEVER hardcode secrets, passwords, or API keys in source code
- Validate ALL external input (user input, API parameters, file uploads)
- Use parameterized queries for ALL database operations
- Apply principle of least privilege for all access control
- NEVER commit secrets to version control (.env, credentials)
- Sanitize output to prevent injection (XSS, SQL injection)

### 5. Code Organization
- Each class/module has a single, clear responsibility (SRP)
- Extract shared logic into reusable functions/utilities (DRY)
- Separate business logic from data access and presentation
- Keep functions small and focused (one task per function)
- Avoid circular dependencies between modules

### 6. API Design (Common)
- Use plural nouns for resource names (/users not /user)
- Use standard HTTP methods (GET, POST, PUT, DELETE)
- Return appropriate HTTP status codes
- Support pagination for list endpoints
- Version APIs in the URL path (/api/v1/)
- Use consistent response envelope/wrapper

### 7. Database (Common)
- Use snake_case for all table and column names
- Use database migrations for ALL schema changes (never manual)
- Add indexes on frequently queried columns
- Use parameterized queries (NEVER concatenate SQL strings)
- Include audit columns (created_at, updated_at) on all tables

### 8. Constants (Common)
- NO magic numbers in code (use named constants)
- NO magic strings in code (use named constants)
- Centralize related constants in dedicated files/classes
- Centralize all user-facing messages (for i18n readiness)
- NEVER duplicate constant definitions

### 9. Testing Approach
- Write unit tests for business logic
- Write integration tests for API endpoints and data access
- NEVER use production data in tests
- Use descriptive test names that explain the scenario
- Each test should be independent (no shared state between tests)

### 10. Documentation (Common)
- Comments explain WHY, not WHAT the code does
- Document all public APIs with request/response examples
- Every project has a README with setup and run instructions
- Keep documentation close to the code it describes
- Update documentation when changing functionality

### 11. Git Standards
- Write meaningful commit messages describing the change
- Use conventional commit format (feat/fix/refactor: description)
- Create feature branches for new work (never commit directly to main)
- Write PR descriptions explaining what and why
- NEVER commit generated files, build artifacts, or secrets

### 12. File Organization
- Group related files by feature/domain
- Separate configuration files from application code
- Keep a clear, documented project entry point
- Use consistent file naming conventions across the project
- Separate test files from source files

---

## ENFORCEMENT RULES SUMMARY

**Total Standards:** 12
**Total Rules:** ~65

These rules are enforced BEFORE any code generation, regardless of whether the project uses Spring Boot, Python, Angular, or any other technology.

---

**VERSION:** 1.0.0
**LOCATION:** policies/02-standards-system/common-standards-policy.md
