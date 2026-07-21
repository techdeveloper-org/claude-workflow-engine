---
description: "Level 2.2 - State machines via enums, business logic methods, display names, persistence"
paths:
  - "src/**/enums/**/*.java"
  - "src/**/entity/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Enum as Domain Model (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce that domain state machines (order lifecycle, payment status, account state)
are implemented as enums with behavior rather than as plain string constants. Prevents scattered
status-check logic (if/switch on string values) by centralizing state transitions and validity
rules inside the enum itself.

**APPLIES WHEN:** Spring Boot project where entities have a status or state field.

---

## 1. Required Enum Fields and Methods

### What We Follow
Every domain enum has a `displayName` field for UI presentation, an `isTerminal()` method
indicating that no further transitions are allowed, and domain-specific helper methods
that encode business rules about the state.

### How To Implement

```java
// CORRECT -- enum with behavior
public enum {Entity}Status {

    /**
     * Initial state. {Entity} has been received and is awaiting processing.
     */
    PENDING("Pending"),

    /**
     * {Entity} is actively being processed.
     */
    ACTIVE("Active"),

    /**
     * Processing is complete. No further transitions possible.
     */
    COMPLETED("Completed"),

    /**
     * {Entity} was cancelled before completion. No further transitions possible.
     */
    CANCELLED("Cancelled");

    private final String displayName;

    {Entity}Status(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() { return displayName; }

    public boolean isTerminal() {
        return this == COMPLETED || this == CANCELLED;
    }

    public boolean isActive() {
        return this == ACTIVE;
    }

    public boolean canTransitionTo({Entity}Status target) {
        return switch (this) {
            case PENDING  -> target == ACTIVE || target == CANCELLED;
            case ACTIVE   -> target == COMPLETED || target == CANCELLED;
            case COMPLETED, CANCELLED -> false;
        };
    }
}

// WRONG -- plain enum with no behavior
public enum {Entity}Status {
    PENDING, ACTIVE, COMPLETED, CANCELLED;
    // isTerminal check scattered across service classes:
    // if (status == COMPLETED || status == CANCELLED) { ... } in 5 different places
}
```

### Why This Matters
When terminal states or valid transitions change, scattered if/switch statements require
a codebase-wide search. Centralizing in the enum means one change location.

---

## 2. Enums Centralized in common-lib

### What We Follow
Domain enums shared across services live in the `enums/` package of the common-lib.
Service-specific enums that are not shared may reside in the service's own package.

### How To Implement

```
CORRECT -- shared enum location
{project}-common-lib/
  src/main/java/{org}/{project}/common/
    enums/
      {Entity}Status.java       <- shared across services that reference {Entity}
      PaymentMethod.java        <- shared across order and payment services

WRONG -- enum duplicated per service
{service-a}/src/.../enums/{Entity}Status.java  <- PENDING, ACTIVE, COMPLETED
{service-b}/src/.../enums/{Entity}Status.java  <- PENDING, IN_PROGRESS, DONE
// Two copies with different values; Feign deserialization fails silently
```

### Why This Matters
An enum duplicated in two services can have different constant names. A Feign response
containing `"status": "IN_PROGRESS"` fails to deserialize to the enum that defines `ACTIVE`.

---

## 3. Persistence Uses EnumType.STRING

### What We Follow
Entity fields that store enums use `@Enumerated(EnumType.STRING)`. Ordinal storage is
forbidden because it corrupts data when enum constants are reordered.

### How To Implement

```java
// CORRECT -- STRING-based persistence
@Entity
public class {Entity} {

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 50)
    private {Entity}Status status;
}

// WRONG -- ORDINAL (default when @Enumerated is omitted)
@Entity
public class {Entity} {
    private {Entity}Status status;
    // Stored as 0, 1, 2, 3 -- reordering constants corrupts all existing rows
}
```

### Why This Matters
If `ACTIVE` moves from ordinal 1 to ordinal 2 (because `IN_REVIEW` was inserted before it),
every row in the database with value `1` now reads as `IN_REVIEW` instead of `ACTIVE`.

---

## 4. Transition Validation in Service Layer

### What We Follow
Before persisting a status change, the service calls `canTransitionTo()` on the current
status to validate the transition is permitted. Invalid transitions throw a domain exception.

### How To Implement

```java
// CORRECT -- transition validated via enum method
public ApiResponseDto<{Entity}Dto> complete{Entity}(Long id) {
    {Entity} entity = findById(id);
    if (!entity.getStatus().canTransitionTo({Entity}Status.COMPLETED)) {
        throw new InvalidOperation{Entity}Exception(
            "Cannot transition from " + entity.getStatus() + " to COMPLETED"
        );
    }
    entity.setStatus({Entity}Status.COMPLETED);
    {entity}Repository.save(entity);
    return buildSuccessResponse(entity, ServiceMessageConstants.{ENTITY}_COMPLETED);
}

// WRONG -- business logic for transition duplicated in service
public ApiResponseDto<{Entity}Dto> complete{Entity}(Long id) {
    {Entity} entity = findById(id);
    if (entity.getStatus() == {Entity}Status.COMPLETED
            || entity.getStatus() == {Entity}Status.CANCELLED) {
        // Duplicated terminal check -- also in delete, cancel, and reactivate methods
        throw new InvalidOperation{Entity}Exception("Already in terminal state");
    }
    entity.setStatus({Entity}Status.COMPLETED);
    // ...
}
```

### Why This Matters
Scattered transition logic means adding a new state requires updating every service method
that checks status. The enum is the only place to update.

---

**ENFORCEMENT:** Level 2 loading -- code review: no `@Enumerated(EnumType.ORDINAL)` or
missing `@Enumerated` on entity fields typed as enums. SonarQube custom rule can detect
bare enum fields without `@Enumerated(STRING)`.

**SEE ALSO:**
- 14-entity-design-patterns.md -- @Enumerated annotation on entity fields
- 22-common-library-design.md -- enum placement in common-lib enums/ package
- 19-exception-handling-hierarchy.md -- InvalidOperationException for rejected transitions
