---
description: "Level 2.2 - AuditorAware, user context resolution, audit field lifecycle"
paths:
  - "src/**/config/AuditorAwareImpl.java"
  - "src/**/entity/**/*.java"
  - "src/**/*Application.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# JPA Auditing Pattern (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce consistent JPA auditing configuration so that every entity has
`createdBy` and `updatedBy` fields automatically populated from the authenticated user
context without any service-layer code. Prevents missing audit fields and prevents
service methods from manually setting the auditor.

**APPLIES WHEN:** Spring Boot project with spring-boot-starter-data-jpa and Spring Security.

---

## 1. @EnableJpaAuditing on Application Class

### What We Follow
The main application class carries `@EnableJpaAuditing(auditorAwareRef="auditorAwareImpl")`.
The `auditorAwareRef` value matches the bean name of the `AuditorAwareImpl` component.

### How To Implement

```java
// CORRECT -- auditing enabled with explicit bean reference
@SpringBootApplication
@EnableDiscoveryClient
@EnableJpaAuditing(auditorAwareRef = "auditorAwareImpl")
public class {Entity}ServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run({Entity}ServiceApplication.class, args);
    }
}

// WRONG -- @EnableJpaAuditing without auditorAwareRef
@SpringBootApplication
@EnableJpaAuditing  // Uses default AuditorAware -- may be null; auditor fields stay blank
public class {Entity}ServiceApplication { ... }

// WRONG -- @EnableJpaAuditing missing entirely
@SpringBootApplication
public class {Entity}ServiceApplication { ... }
// @CreatedBy and @LastModifiedBy annotations are silently ignored
```

### Why This Matters
Without `auditorAwareRef`, Spring JPA Auditing picks any available `AuditorAware` bean or
falls back to null. `createdBy` and `lastModifiedBy` fields are stored as null silently.

---

## 2. AuditorAwareImpl Resolution Priority

### What We Follow
`AuditorAwareImpl` resolves the current auditor from Spring Security's `SecurityContextHolder`
with a priority chain:
1. If authenticated: use the email/username from `UserDetails`
2. If authenticated but not `UserDetails`: use `principal.toString()`
3. If not authenticated (scheduled jobs, startup tasks): use `"SYSTEM"`

This class lives in common-lib so all services share the same resolution logic.

### How To Implement

```java
// CORRECT -- AuditorAwareImpl in common-lib with priority chain
@Component("auditorAwareImpl")
public class AuditorAwareImpl implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            return Optional.of("SYSTEM");
        }

        Object principal = authentication.getPrincipal();

        if (principal instanceof UserDetails userDetails) {
            return Optional.of(userDetails.getUsername());
        }

        return Optional.of(principal.toString());
    }
}

// WRONG -- AuditorAware that can return empty Optional
@Override
public Optional<String> getCurrentAuditor() {
    return Optional.ofNullable(
        SecurityContextHolder.getContext().getAuthentication()
    ).map(Authentication::getName);
    // Returns empty Optional for unauthenticated requests
    // JPA throws if @CreatedBy field is NOT NULL and auditor is empty
}
```

### Why This Matters
An `AuditorAware` that returns `Optional.empty()` for unauthenticated contexts causes
`TransactionSystemException` during scheduled job execution when the entity has a NOT NULL
`createdBy` column -- a runtime failure only discovered when the first scheduled job runs.

---

## 3. Entity Audit Fields

### What We Follow
Entities that need user-level auditing add `@CreatedBy` and `@LastModifiedBy` fields in
addition to the timestamp fields defined in rule 14-entity-design-patterns.md.
`createdBy` is marked `updatable=false`.

### How To Implement

```java
// CORRECT -- entity with full JPA auditing fields
@Entity
@Table(name = "{entity_table}", schema = "{schema}")
@DynamicInsert
@DynamicUpdate
@EntityListeners(AuditingEntityListener.class)  // REQUIRED for @CreatedBy/@LastModifiedBy
@Data
@NoArgsConstructor
public class {Entity} implements Serializable {

    private static final long serialVersionUID = 1L;

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "{entity_seq}_generator")
    @SequenceGenerator(name = "{entity_seq}_generator", sequenceName = "{entity_seq}",
                       schema = "{schema}", allocationSize = 1)
    private Long id;

    // Timestamp audit (from PrePersist/PreUpdate -- see 14-entity-design-patterns.md)
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    // User audit (from AuditorAwareImpl via @EntityListeners)
    @CreatedBy
    @Column(name = "created_by", nullable = false, updatable = false, length = 255)
    private String createdBy;

    @LastModifiedBy
    @Column(name = "updated_by", nullable = false, length = 255)
    private String updatedBy;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }
}

// WRONG -- @CreatedBy without @EntityListeners(AuditingEntityListener.class)
@Entity
public class {Entity} {
    @CreatedBy
    private String createdBy;
    // createdBy is NEVER set -- @EntityListeners missing
}
```

### Why This Matters
`@CreatedBy` and `@LastModifiedBy` are handled by `AuditingEntityListener`. Without
`@EntityListeners(AuditingEntityListener.class)` on the entity class, the annotations
are silently ignored and the fields are stored as null.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test: all entities with `@CreatedBy` fields
must also carry `@EntityListeners(AuditingEntityListener.class)`. Application class test
verifies `@EnableJpaAuditing` annotation is present (see 28-test-coverage-enforcement.md).

**SEE ALSO:**
- 14-entity-design-patterns.md -- timestamp audit fields (createdAt, updatedAt) via @PrePersist
- 22-common-library-design.md -- AuditorAwareImpl placement in common-lib config/
- 31-security-authentication.md -- SecurityContextHolder that AuditorAwareImpl reads from
