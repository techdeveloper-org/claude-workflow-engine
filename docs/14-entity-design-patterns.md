---
description: "Level 2.2 - JPA entity structure, ID generation, audit fields, optimistic locking, Hibernate annotations"
paths:
  - "src/**/entity/**/*.java"
  - "src/**/model/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Entity Design Patterns (Level 2.2 - Spring Boot)

**PURPOSE:** Standardize JPA entity structure so every entity has consistent audit fields,
safe ID generation, explicit schema mapping, and proper serialization. Prevents silent
INSERT of null audit timestamps, ordinal enum corruption on schema changes, and
N+1 query issues from missing column definitions.

**APPLIES WHEN:** Spring Boot project with spring-boot-starter-data-jpa in pom.xml.

---

## 1. Dynamic Insert and Update

### What We Follow
Every entity carries `@DynamicInsert` and `@DynamicUpdate`. Hibernate generates SQL only
for columns that are non-null on insert and only for fields that actually changed on update.

### How To Implement

```java
// CORRECT -- dynamic SQL generation
@Entity
@Table(name = "{entity_table}", schema = "{schema}")
@DynamicInsert
@DynamicUpdate
@Data
@NoArgsConstructor
public class {Entity} implements Serializable {

    private static final long serialVersionUID = 1L;

    // ... fields
}

// WRONG -- omitting @DynamicInsert/@DynamicUpdate
@Entity
@Table(name = "{entity_table}")
public class {Entity} {
    // Hibernate sends ALL columns on every INSERT and UPDATE
    // Sends null for audit fields not yet set; can overwrite DB defaults
}
```

### Why This Matters
Without `@DynamicUpdate`, updating one field sends the entire row to the database,
causing unnecessary data transfer and defeating column-level DB triggers.

---

## 2. ID Generation via Sequence

### What We Follow
Use database sequences with `allocationSize=1`. Never use `IDENTITY` (auto-increment)
strategy — it forces an extra DB round-trip per insert and breaks batch insert optimization.

### How To Implement

```java
// CORRECT -- sequence-based ID with allocationSize=1
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "{entity_seq}_generator")
@SequenceGenerator(
    name = "{entity_seq}_generator",
    sequenceName = "{entity_seq}",
    schema = "{schema}",
    allocationSize = 1
)
private Long id;

// WRONG -- IDENTITY strategy
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
// Breaks batch inserts; requires round-trip per row; cannot predict ID before persist
```

### Why This Matters
`allocationSize=1` matches the database sequence increment, preventing gaps caused by
Hibernate pre-allocating a range. Sequences work correctly with batch processing.

---

## 3. Explicit Table and Schema Mapping

### What We Follow
Always specify `@Table(name=..., schema=...)` explicitly. Never rely on Hibernate's
default naming strategy to derive the table name from the class name.

### How To Implement

```java
// CORRECT -- explicit mapping
@Entity
@Table(name = "{entity_table}", schema = "{schema}")
public class {Entity} {

    @Column(name = "{field}", nullable = false, length = 255)
    private String {field};

    @Column(name = "status", nullable = false, length = 50)
    @Enumerated(EnumType.STRING)
    private {Entity}Status status;
}

// WRONG -- implicit naming, no schema
@Entity
public class {Entity} {
    private String {field};  // Column name derived from field name -- fragile
    private {Entity}Status status;  // No @Enumerated -- defaults to ORDINAL
}
```

Column naming rules:
- Always snake_case for column names
- Specify `nullable`, `length` for VARCHAR, `precision`/`scale` for DECIMAL
- Never use `@Column` without explicit `name` attribute

### Why This Matters
Implicit naming breaks when entity classes are renamed or when Hibernate naming strategy
configuration changes. Ordinal enum storage corrupts data when enum constants are reordered.

---

## 4. Mandatory Audit Fields

### What We Follow
Every entity has `createdAt` and `updatedAt` timestamp fields managed via JPA lifecycle
callbacks. `createdAt` is immutable after insert (`updatable=false`).

### How To Implement

```java
// CORRECT -- audit fields with lifecycle callbacks
@Column(name = "created_at", nullable = false, updatable = false)
private LocalDateTime createdAt;

@Column(name = "updated_at", nullable = false)
private LocalDateTime updatedAt;

@PrePersist
protected void onCreate() {
    this.createdAt = LocalDateTime.now();
    this.updatedAt = LocalDateTime.now();
}

@PreUpdate
protected void onUpdate() {
    this.updatedAt = LocalDateTime.now();
}

// WRONG -- audit fields without updatable=false or lifecycle callbacks
@Column(name = "created_at")
private LocalDateTime createdAt;  // Can be overwritten on update; can be null
```

### Why This Matters
Without `updatable=false`, a full-entity merge accidentally resets `createdAt` to the
current time, destroying the original creation timestamp permanently.

---

## 5. Optimistic Locking for Concurrent Entities

### What We Follow
Entities subject to concurrent modification (orders, payments, inventory counts) carry
`@Version`. Hibernate automatically detects stale reads and throws `OptimisticLockException`.

### How To Implement

```java
// CORRECT -- version field for concurrency control
@Version
@Column(name = "version", nullable = false)
private Long version;

// Usage in service: catch and retry on OptimisticLockException
try {
    {entity}Repository.save({entity});
} catch (OptimisticLockException e) {
    throw new ConcurrentModificationException(
        "Concurrent update detected for {Entity} id: " + {entity}.getId()
    );
}

// WRONG -- no @Version on entities that multiple threads/services can update
// Last writer wins silently; lost updates go undetected
```

### Why This Matters
Without optimistic locking, two concurrent requests can both read the same entity,
both modify it, and both save -- the second save silently discards the first change.

---

## 6. Serializable and SerialVersionUID

### What We Follow
All entities implement `Serializable` with an explicit `serialVersionUID`. This is required
for Redis caching, Feign response deserialization, and distributed session support.

### How To Implement

```java
// CORRECT
@Entity
@Table(name = "{entity_table}", schema = "{schema}")
public class {Entity} implements Serializable {

    private static final long serialVersionUID = 1L;

    // fields...
}

// WRONG -- missing Serializable or auto-generated UID
@Entity
public class {Entity} {
    // Cannot be cached in Redis; Feign deserialization fails at runtime
}
```

### Why This Matters
Missing `Serializable` causes `NotSerializableException` at runtime when the entity
is first placed in a distributed cache -- a failure that only appears in production load.

---

**ENFORCEMENT:** Level 2 loading -- code review checklist. JaCoCo enforces test coverage
on entity lifecycle methods. SonarQube rule: entities without @Table annotation flagged.

**SEE ALSO:**
- 25-jpa-auditing-pattern.md -- AuditorAware for createdBy/updatedBy fields
- 32-repository-conventions.md -- repository interface design for these entities
- 23-enum-as-domain-model.md -- enum structure persisted via @Enumerated(STRING)
- 21-caching-strategy.md -- Serializable requirement for Redis caching
