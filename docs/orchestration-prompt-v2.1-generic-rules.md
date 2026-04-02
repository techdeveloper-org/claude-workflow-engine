# MASTER ORCHESTRATION PROMPT v2.1 — Generic Spring Boot Rules Generation

**Created:** 2026-04-01
**Purpose:** Generate 20 new coding standard rule files (13-32) in `rules/` folder
**Status:** Ready to execute

---

## YOUR TASK

Create a comprehensive set of coding standards rule files in the `rules/` folder
of the claude-workflow-engine project. These rules codify the PATTERNS and
CONVENTIONS that we consistently follow across ALL our Spring Boot microservice
ecosystems. The rules must be:

- **Generic:** Applicable to ANY new Spring Boot microservice project
- **Pattern-focused:** Describe WHAT to do and HOW to do it
- **Placeholder-based:** Use {project}, {entity}, {service} instead of real names
- **Framework-version-agnostic:** Say "Spring Boot 3.x+" not "Spring Boot 4.0.5"

These rules serve as Level 2 standards loading -- when the pipeline detects a
Spring Boot project, these rules are injected into the coding context so every
new service follows the same architecture from day one.

### Rule Files to Create (13 through 32):

| # | File | Scope |
|---|------|-------|
| 13 | `13-spring-cloud-infrastructure.md` | Centralized config, service discovery, API gateway, retry/failover |
| 14 | `14-entity-design-patterns.md` | JPA entity structure, ID generation, audit fields, optimistic locking, Hibernate annotations |
| 15 | `15-dto-form-separation.md` | Request objects (Form) vs response objects (Dto), serialization rules, immutability |
| 16 | `16-validation-sequence-pattern.md` | Ordered validation groups, ValidationSequence, constant-driven messages |
| 17 | `17-api-response-wrapper.md` | Unified response envelope, status propagation, error responses |
| 18 | `18-service-layer-conventions.md` | Interface+Impl, transaction boundaries, Helper pattern, return types |
| 19 | `19-exception-handling-hierarchy.md` | Custom exceptions, GlobalExceptionHandler, HTTP status mapping |
| 20 | `20-inter-service-communication.md` | OpenFeign via gateway, client configuration, circuit breaking |
| 21 | `21-caching-strategy.md` | L1+L2 hybrid cache, TTL tiers, financial data exceptions, serialization |
| 22 | `22-common-library-design.md` | Shared library structure, dependency scoping, what belongs in common-lib |
| 23 | `23-enum-as-domain-model.md` | State machines via enums, business logic methods, display names, persistence |
| 24 | `24-constants-organization.md` | Message constants, validation constants, API constants, usage pattern |
| 25 | `25-jpa-auditing-pattern.md` | AuditorAware, user context resolution, audit field lifecycle |
| 26 | `26-openapi-documentation.md` | Controller-level tags, operation annotations, response schemas, gateway aggregation |
| 27 | `27-centralized-logging.md` | Logback HTTP appender, async batching, MDC tracing, log level governance |
| 28 | `28-test-coverage-enforcement.md` | JaCoCo per-package 100%, JUnit 5 patterns, application class testing |
| 29 | `29-container-deployment.md` | Dockerfile template, non-root user, JVM container flags, health checks |
| 30 | `30-maven-build-conventions.md` | Parent POM, plugin stack, library packaging, dependency management |
| 31 | `31-security-authentication.md` | Spring Security stateless config, JWT filter chain, CORS, public endpoints |
| 32 | `32-repository-conventions.md` | JpaRepository typing, query method naming, JPQL over native, Sort/Pageable |

---

### Rule File Format (MANDATORY for every file):

```markdown
---
description: "Level 2.2 - {one-line description}"
paths:
  - "src/**/*.java"
  - "{additional glob patterns}"
priority: critical | high | medium
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# {Rule Title} (Level 2.2 - Spring Boot)

**PURPOSE:** {Why this rule exists -- what problem it prevents}

**APPLIES WHEN:** {Detection condition -- e.g., Spring Boot project with JPA}

---

## 1. {First Pattern}

### What We Follow
{Plain English description of the pattern}

### How To Implement
\```java
// CORRECT -- {why this is correct}
{generic code with {placeholders}}

// WRONG -- {why this is wrong}
{anti-pattern code}
\```

### Why This Matters
{1-2 sentences on the consequence of not following this}

---

## N. {Last Pattern}

...

---

**ENFORCEMENT:** {How this rule is checked: Level 2 loading / code review / build plugin}
**SEE ALSO:** {Cross-references to other rule files}
```

---

### Placeholder Convention (USE EVERYWHERE):

| Placeholder | Meaning | Example |
|-------------|---------|---------|
| `{org}` | Organization/company name | `com.acme` |
| `{project}` | Project/ecosystem name | `ecommerce`, `social` |
| `{service}` | Microservice name | `product-service` |
| `{entity}` | Domain entity name | `Product`, `Order` |
| `{Entity}` | PascalCase entity | `Product` |
| `{entity_table}` | snake_case table | `products` |
| `{entity_seq}` | Sequence name | `product_seq` |
| `{schema}` | Database schema | `ecommerce` |
| `{gateway-url}` | Gateway base URL | `https://gateway:8085` |
| `{config-server-url}` | Config server URL | `http://config-server:8888` |
| `{field}` | Any entity field | `name`, `email` |
| `{cache-name}` | Cache identifier | `productById` |

---

### Content Guidelines for Each Rule:

**Rule 13 -- Spring Cloud Infrastructure:**
- Config Server: service application.yml contains ONLY `spring.config.import` + retry config
- ALL business properties (DB, Redis, ports, feature flags) live in Config Server
- Secret references use `${SECRET:key-name}` placeholder pattern
- Eureka: `@EnableDiscoveryClient` on application class
- Gateway: single entry point for all external + inter-service traffic
- Retry: fail-fast=true with exponential backoff
- Generic -- NO hardcoded URLs, use `{config-server-url}`, `{gateway-url}`

**Rule 14 -- Entity Design Patterns:**
- `@DynamicInsert` + `@DynamicUpdate` on every entity (performance)
- ID: `@SequenceGenerator(allocationSize=1)` + `@GeneratedValue(SEQUENCE)`
- Schema: `@Table(name="{entity_table}", schema="{schema}")` -- ALWAYS explicit
- Audit: `createdAt` (immutable via `updatable=false`), `updatedAt` -- MANDATORY
- Lifecycle: `@PrePersist` sets both, `@PreUpdate` sets updatedAt only
- Locking: `@Version` for entities with concurrent writes (orders, payments)
- Serialization: `implements Serializable` with explicit `serialVersionUID`
- Columns: snake_case, explicit `@Column(name="...")`, nullable/length specified
- Enums: `@Enumerated(EnumType.STRING)` -- NEVER ORDINAL
- Lombok: `@Data` + `@NoArgsConstructor`
- Generic -- examples use `{Entity}`, `{entity_table}`, `{schema}`

**Rule 15 -- DTO/Form Separation:**
- Request objects go in `form/` package, suffixed `Form` (e.g., `{Entity}Form`)
- Response objects go in `dto/` package, suffixed `Dto` (e.g., `{Entity}Dto`)
- NEVER use same class for both request and response
- Form: `@Data`, extends `ValidationMessageConstants`, `@JsonIgnoreProperties(ignoreUnknown=true)`
- Dto: `@Builder`, `@Getter` (NO setter), `@AllArgsConstructor`, `@NoArgsConstructor`
- Dto: `@JsonInclude(Include.NON_NULL)` -- exclude nulls from response
- Dto: `implements Serializable` with explicit UID
- ApiResponseDto<T> lives in common-lib, shared across all services

**Rule 16 -- Validation Sequence:**
- Define validation groups: `NotNullGroup` -> `NotEmptyGroup` -> `NotBlankGroup` -> `LengthGroup` -> `PatternGroup`
- `ValidationSequence` interface orders them via `@GroupSequence`
- Controller uses `@Validated(ValidationSequence.class)` -- NOT `@Valid`
- Form fields use group-specific annotations: `@NotNull(message=CONSTANT, groups=NotNullGroup.class)`
- All validation messages are constants from `ValidationMessageConstants`
- NEVER hardcode message strings in annotations

**Rule 17 -- API Response Wrapper:**
- ALL endpoints return `ResponseEntity<ApiResponseDto<T>>`
- ApiResponseDto fields: `data`, `message`, `success`, `status`, `timestamp`
- Success: `ApiResponseDto.builder().data(dto).message(MSG).success(true).status(200).build()`
- Error: `ApiResponseDto<Void>` with `success=false` and appropriate HTTP status
- Controller extracts status: `HttpStatus.valueOf(apiResponseDto.getStatus())`
- NEVER return raw DTOs or entities from controllers
- Void operations (delete, update-no-return) use `ApiResponseDto<Void>`

**Rule 18 -- Service Layer Conventions:**
- Service interface: `public interface {Entity}Services` -- defines contract
- Implementation: package-private `class {Entity}ServicesImpl extends {Entity}ServiceHelper implements {Entity}Services`
- Helper: `abstract class {Entity}ServiceHelper` -- reusable lookups, validations, entity builders
- Transaction on INTERFACE methods (not implementation):
  - Write ops: `@Transactional(rollbackFor=DataAccessException.class, propagation=Propagation.REQUIRES_NEW)`
  - Read ops: `@Transactional(propagation=Propagation.NEVER, readOnly=true)`
- ALL service methods return `ApiResponseDto<T>` -- controller never builds response
- Constructor injection via `@RequiredArgsConstructor` (Lombok)

**Rule 19 -- Exception Handling:**
- Base: `ApplicationException extends RuntimeException` with `code` + `httpStatus` fields
- One exception class per business scenario: `{Entity}NotFoundException`, `Duplicate{Entity}Exception`
- `@RestControllerAdvice GlobalExceptionHandler extends CommonExceptionHandler`
- CommonExceptionHandler lives in common-lib (handles MethodArgumentNotValidException, generic Exception)
- Service-specific handler adds domain exceptions
- Status mapping: NOT_FOUND=404, CONFLICT=409, BAD_REQUEST=400, INTERNAL_SERVER_ERROR=500
- ALL error responses: `ApiResponseDto<Void>` with `success=false`

**Rule 20 -- Inter-Service Communication:**
- ALL inter-service calls via OpenFeign through API Gateway (single entry point)
- `@FeignClient(name="gateway", contextId="{entity}Client", url="{gateway-url}", configuration=FeignConfig.class)`
- FeignConfig: `Logger.Level.FULL` for debugging
- Feign clients defined in common-lib `client/` package (shared across services)
- Circuit breaker (Resilience4j) on gateway for fault tolerance
- Fallback methods for graceful degradation
- contextId differentiates multiple clients pointing to same gateway

**Rule 21 -- Caching Strategy:**
- Hybrid L1 + L2 architecture:
  - L1: Caffeine (in-process, ~2min TTL, bounded size per pod)
  - L2: Redis (distributed, longer TTL, shared across pods)
- TTL tiers by data volatility:
  - By-ID lookups: 30 minutes
  - List/collection queries: 15 minutes
  - Count/aggregate results: 10 minutes
  - External service existence checks: 5 minutes
- Financial/payment data: Redis-ONLY (no L1), short TTL (60s), immediate evict on write
- Serialization: JSON via `GenericJacksonJsonRedisSerializer` (human-readable, debuggable)
- Always `enableStatistics()` for monitoring cache hit ratios
- `BaseCacheConfig` abstract class in common-lib, services override `getRedisCacheTtlOverrides()`
- Cache names as `public static final String` constants in CacheConfig

**Rule 22 -- Common Library Design:**
- Every ecosystem has ONE common library (e.g., `{project}-common-lib`)
- Contains: shared DTOs, enums, Feign clients, base configs, common exceptions, validation groups
- Dependency scope: ALL dependencies marked `provided` -- never force transitive deps
- Published as Maven artifact, consumed by all services in the ecosystem
- NEVER put business logic in common-lib -- only shared contracts and infrastructure
- Base classes: `BaseCacheConfig`, `CommonExceptionHandler`, `AuditorAwareImpl`

**Rule 23 -- Enum as Domain Model:**
- Enums represent domain state machines (e.g., order lifecycle, payment status)
- Required fields: `displayName` (String) for UI presentation
- Required methods: `isTerminal()`, `isActive()`, domain-specific helpers
- Centralized in common-lib `enums/` package (shared across services)
- Entity persistence: `@Enumerated(EnumType.STRING)` -- NEVER ordinal
- Javadoc per value explaining when/why this state is reached

**Rule 24 -- Constants Organization:**
- Three constant classes per service:
  - `ServiceMessageConstants` -- success/error messages for service responses
  - `ValidationMessageConstants` -- constraint violation messages (extended by Forms)
  - `ApiConstants` -- endpoint paths, header names
- All constants: `public static final String`
- Forms extend `ValidationMessageConstants` to use in annotation messages
- NEVER hardcode strings in `@NotNull(message="...")` -- always use constant reference

**Rule 25 -- JPA Auditing:**
- Application class: `@EnableJpaAuditing(auditorAwareRef="auditorAwareImpl")`
- `AuditorAwareImpl implements AuditorAware<String>` -- resolves current user
- Resolution priority: request context email -> userId -> "SYSTEM" fallback
- Entity audit fields: `@CreatedBy`, `@LastModifiedBy` (optional, via Spring Data)
- Timestamp fields: `@PrePersist`/`@PreUpdate` lifecycle callbacks (mandatory)
- AuditorAwareImpl lives in common-lib config package

**Rule 26 -- OpenAPI Documentation:**
- Controller class: `@Tag(name="{Entity} Management", description="...")`
- Each method: `@Operation(summary="...", description="...")`
- Each method: `@ApiResponses` with `@ApiResponse` for 200/201/400/404/409/500
- Path/query params: `@Parameter(description="...", required=true/false)`
- Gateway aggregates all service Swagger docs (springdoc group config)
- JWT auth: OpenAPI security scheme configured in common-lib

**Rule 27 -- Centralized Logging:**
- logback-spring.xml with dual appenders: Console (local dev) + HTTP (centralized)
- HTTP appender sends structured JSON logs to a central endpoint in async batches
- Batch config: configurable batch size, queue size, flush interval
- Async wrapper: `neverBlock=true` -- logging never blocks request processing
- MDC pattern: `[%X{traceId:-},%X{spanId:-}]` for distributed tracing correlation
- Log levels: managed via Config Server (NOT in logback.xml)
- NEVER log passwords, tokens, PII, credit card numbers

**Rule 28 -- Test Coverage Enforcement:**
- JaCoCo plugin with per-PACKAGE enforcement
- Minimum 1.00 (100%) for: LINE, BRANCH, CLASS, METHOD, INSTRUCTION, COMPLEXITY
- No exclusions -- every class, every branch, every method
- JUnit 5 + Mockito for unit tests
- H2 in-memory database for `@DataJpaTest` repository tests
- Application class tests: verify annotations via reflection + mock `SpringApplication.run()`
- Test naming: `{ClassName}UnitTest`, `{ClassName}IntegrationTest`

**Rule 29 -- Container Deployment:**
- Base image: JRE-only Alpine variant (minimal attack surface)
- Non-root user: create group + user with UID/GID 1000 for K8s security
- JVM container-aware flags:
  - `MaxRAMPercentage=75%` (respect container memory limits)
  - `UseG1GC` (low-latency garbage collection)
  - `UseStringDeduplication` (memory optimization)
  - `DisableExplicitGC` (prevent accidental full GC)
- HEALTHCHECK: `curl` to `/actuator/health` with interval/timeout/retries
- Single COPY of pre-built JAR (no multi-stage build needed if CI builds JAR)
- EXPOSE only the service port

**Rule 30 -- Maven Build Conventions:**
- Parent: `spring-boot-starter-parent` (inherit dependency management)
- Java version: property `<java.version>` in POM
- Spring Cloud: BOM import via `<dependencyManagement>`
- Required plugins:
  - `spring-boot-maven-plugin` -- executable JAR
  - `jacoco-maven-plugin` -- coverage enforcement
  - `maven-compiler-plugin` -- annotation processing (Lombok)
  - `maven-source-plugin` -- attach sources (common-lib only)
- Common library: packaging=jar, published to artifact repo
- Service: packaging=jar (Spring Boot executable)
- Dev vs prod dependencies: test-scoped for H2, JUnit, Mockito

**Rule 31 -- Security Authentication:**
- Spring Security with stateless session management (`STATELESS`)
- CSRF: disabled (REST APIs with JWT don't need CSRF)
- JWT filter: custom `JwtAuthenticationFilter` added before `UsernamePasswordAuthenticationFilter`
- Public endpoints: registration, login, password reset -- explicitly `permitAll()`
- All other endpoints: `authenticated()`
- CORS: origins loaded from Config Server property, not hardcoded
- `@EnableMethodSecurity` for role-based method-level authorization
- JWT library: JJWT with separate api/impl/jackson modules

**Rule 32 -- Repository Conventions:**
- Extend `JpaRepository<{Entity}, Serializable>` (not `Long` -- allows flexibility)
- Access modifier: package-private (no `public` on repository interface)
- Spring Data query methods: `findBy{Field}`, `existsBy{Field}`, `countBy{Field}`
- Case-insensitive: `{Field}EqualsIgnoreCase` suffix
- Sorted results: accept `Sort` parameter
- Complex queries: `@Query` with JPQL (not native SQL)
- NEVER use `nativeQuery=true` unless absolutely unavoidable
- Aggregations: return `List<Object[]>` or projection interface
- Pagination: accept `Pageable` parameter, return `Page<{Entity}>`

---

## CONSTRAINTS

1. **ASCII-only** -- all files must be cp1252 safe (Windows). Use `CORRECT:` and
   `WRONG:` labels instead of Unicode symbols (no checkmarks, no crosses, no emojis)
2. **Frontmatter required** -- YAML frontmatter with: description, paths, priority,
   conditional
3. **Generic examples only** -- use `{placeholders}` for project/entity/schema names.
   NO hardcoded org names, URLs, IPs, registry addresses, or domain-specific examples
4. **Pattern over implementation** -- describe the RULE, then show the STRUCTURE.
   A reader should be able to apply this to a brand new project without knowing
   our existing projects
5. **Version ranges** -- say "Spring Boot 3.x+" or "Java 17+" not pinned versions.
   The pattern matters, not the exact version number
6. **Enforcement section** -- each rule ends with ENFORCEMENT block
7. **No overlap** -- rules 13-32 must NOT duplicate content from existing rules 01-12.
   Cross-reference instead: "See also: 01-common-standards.md Section 6 (API Design)"
8. **Format consistency** -- follow existing rule file format (01-03) for structure
9. **No hardcoded values** -- no IPs, no DNS names, no registry URLs, no org-specific
   package prefixes. Everything parameterized
10. **WHY before WHAT** -- each pattern section explains WHY we follow this convention
    before showing HOW

---

## TECHNICAL DOMAINS DETECTED

| Domain | Agent | Justification |
|--------|-------|---------------|
| Spring Boot Microservices | `spring-boot-microservices` | Core domain -- all rules are Spring Boot Java patterns |
| Java Design Patterns | (skill: `java-design-patterns-core`) | Interface+Impl, Builder, Helper, Abstract Factory |
| Database Engineering | `database-engineer` | JPA entity design, sequences, JPQL, schema patterns |
| Cloud Engineering | `cloud-engineer` | Docker, K8s deployment, Config Server, service discovery |
| Security Architecture | `security-defense-architect` | JWT, Spring Security, CORS, container security |
| QA/Testing | `qa-testing-agent` | JaCoCo 100%, JUnit 5, Mockito, test patterns |

---

## MATH REQUIREMENTS

**None.** Pure code pattern documentation task.

---

## PROMPT ENGINEERING REQUIREMENTS

**None.** No AI systems or LLM pipelines involved.

---

## EXECUTION PATTERN

### Recommended: Parallel-then-Sequential Hybrid

```
Phase 1 (PARALLEL -- 4 agents, independent rule files):
  |-- spring-boot-microservices  -> Rules 13,14,15,16,17,18,19,20,23,24,26,32
  |-- cloud-engineer             -> Rules 29, 30
  |-- security-defense-architect -> Rule 31
  |-- qa-testing-agent           -> Rule 28

Phase 2 (PARALLEL -- 2 agents, rules that reference Phase 1 output):
  |-- spring-boot-microservices  -> Rules 21,22,25,27 (cache/common-lib/audit/logging)
  |-- database-engineer          -> Review+amend Rules 14, 32 for DB accuracy

Phase 3 (SEQUENTIAL -- cross-reference update):
  |-- spring-boot-microservices  -> Update Rule 03 frontmatter with see-also list

Phase 4 (SEQUENTIAL -- validation gate):
  |-- qa-testing-agent           -> Validate ALL 20 files:
      - ASCII-only (no byte > 127)
      - YAML frontmatter parses correctly
      - No hardcoded project names, URLs, IPs
      - No {placeholder} left unfilled in non-example sections
      - No content overlap with rules 01-12
      - Code blocks have language tags
      - Every "See also" points to existing file
```

### Dependency Reasoning:
- Phase 1: all agents write independent files, zero cross-dependency
- Phase 2: cache rule references entity patterns (Rule 14), common-lib rule
  references DTOs/enums (Rules 15,23) -- needs Phase 1 complete
- Phase 3: Rule 03 update needs all 20 rule file names finalized
- Phase 4: validation requires all files written

---

## INTERFACE CONTRACTS

### Contract 1: spring-boot-microservices -> rules/

| Field | Value |
|-------|-------|
| **FROM** | `spring-boot-microservices` |
| **TO** | `rules/13-*.md` through `rules/27-*.md` (16 files) |
| **INPUT** | Pattern knowledge from codebase analysis of all microservice repos |
| **OUTPUT** | Generic markdown rule files with {placeholder} examples, YAML frontmatter |
| **ASSUMES** | Existing rules 01-12 are in `rules/`. New files numbered 13-32. All examples use `{placeholder}` syntax for project-specific values |
| **MUST NOT** | Hardcode any project name, URL, IP, org name, or domain entity. Duplicate content from rules 01-12. Use Unicode characters. Pin exact framework versions |

### Contract 2: cloud-engineer -> rules/

| Field | Value |
|-------|-------|
| **FROM** | `cloud-engineer` |
| **TO** | `rules/29-container-deployment.md`, `rules/30-maven-build-conventions.md` |
| **INPUT** | Generic Docker + Maven patterns extracted from microservice repos |
| **OUTPUT** | Two rule files with container and build patterns using `{placeholders}` |
| **ASSUMES** | On-premise Kubernetes (not cloud-managed). JRE Alpine base image. Maven (not Gradle) |
| **MUST NOT** | Reference specific Docker registry IPs/URLs. Reference AWS/GCP/Azure. Include CI/CD pipeline rules (out of scope) |

### Contract 3: security-defense-architect -> rules/

| Field | Value |
|-------|-------|
| **FROM** | `security-defense-architect` |
| **TO** | `rules/31-security-authentication.md` |
| **INPUT** | Spring Security + JWT patterns |
| **OUTPUT** | One generic rule file for stateless JWT authentication |
| **ASSUMES** | JWT is auth mechanism. Stateless REST APIs. CORS configured externally |
| **MUST NOT** | Duplicate generic security rules from `05-security-standards.md`. Include OAuth2/SAML/LDAP (not in our pattern). Hardcode allowed origins or endpoint paths |

### Contract 4: qa-testing-agent -> rules/

| Field | Value |
|-------|-------|
| **FROM** | `qa-testing-agent` |
| **TO** | `rules/28-test-coverage-enforcement.md` |
| **INPUT** | JaCoCo + JUnit 5 + Mockito testing patterns |
| **OUTPUT** | One rule file covering test standards and coverage enforcement |
| **ASSUMES** | 100% coverage is non-negotiable policy. H2 for in-memory testing |
| **MUST NOT** | Suggest lowering coverage thresholds. Add frameworks we do not use (Testcontainers, WireMock, Spock). Hardcode package names in JaCoCo config |

### Contract 5: database-engineer -> Review

| Field | Value |
|-------|-------|
| **FROM** | `database-engineer` |
| **TO** | Amendments to `rules/14-entity-design-patterns.md`, `rules/32-repository-conventions.md` |
| **INPUT** | Phase 1 output of rules 14 and 32 |
| **OUTPUT** | Technical corrections for sequence semantics, JPQL best practices, index patterns |
| **ASSUMES** | PostgreSQL primary. Some services may use MongoDB (rule should note this) |
| **MUST NOT** | Create new files. Only amend rules 14 and 32. Add DB-vendor-specific syntax |

### Contract 6: spring-boot-microservices -> Rule 03 Update

| Field | Value |
|-------|-------|
| **FROM** | `spring-boot-microservices` |
| **TO** | `rules/03-microservices-standards.md` (UPDATE only) |
| **INPUT** | File names of all new rules 13-32 |
| **OUTPUT** | Updated frontmatter with `see-also` references. Updated intro noting detailed sub-rules exist |
| **ASSUMES** | Rule 03 exists with 13 sections |
| **MUST NOT** | Delete or modify any existing content in rule 03. Only ADD cross-references |

---

## QUALITY GATES

### Gate 1: Generic Check (BLOCKING)
Every rule file is scanned for:
- No occurrence of specific project/org names
- No IP addresses (regex: `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`)
- No hardcoded ports (except illustrative `:8080` in generic examples)
- No `.svc.cluster.local` DNS references
- No GitHub URLs pointing to specific repos
- No pinned versions (e.g., `4.0.5`, `2025.1.0`) -- use ranges like `3.x+`

### Gate 2: Format Check
- YAML frontmatter parses without error
- Section numbers are sequential (1, 2, 3...)
- Every code block has a language tag (```java, ```yaml, ```xml)
- ENFORCEMENT section present at end of file
- SEE ALSO section present (can be empty if no cross-refs needed)

### Gate 3: Dedup Check
- No paragraph in rules 13-32 has >60% token similarity with rules 01-12
- No two rules in 13-32 have >40% content overlap with each other

### Gate 4: Completeness Check
- All 20 files exist (13 through 32)
- Rule 03 updated with see-also references
- Total rules directory: 32 files (12 existing + 20 new)
