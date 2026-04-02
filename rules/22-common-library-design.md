---
description: "Level 2.2 - Shared library structure, dependency scoping, what belongs in common-lib"
paths:
  - "**/common-lib/**/*.java"
  - "**/common-lib/pom.xml"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Common Library Design (Level 2.2 - Spring Boot)

**PURPOSE:** Define what belongs in the ecosystem-wide common library, how it is structured,
and how its dependencies are scoped. Prevents business logic creeping into common-lib (which
makes it a hidden monolith) and prevents common-lib from forcing transitive dependencies
onto consuming services.

**APPLIES WHEN:** Spring Boot microservices ecosystem with a shared `{project}-common-lib`.

---

## 1. What Belongs in common-lib

### What We Follow
Common-lib contains ONLY shared contracts and infrastructure. It never contains business logic.

```
BELONGS in common-lib:
  dto/          -- ApiResponseDto<T>, shared Dto classes used by multiple services
  form/         -- Shared Form classes (if a form is submitted to multiple services)
  enums/        -- Domain enums referenced by multiple services (see 23-enum-as-domain-model.md)
  client/       -- Feign client interfaces for all services (see 20-inter-service-communication.md)
  exception/    -- ApplicationException, DomainException, CommonExceptionHandler
  config/       -- BaseCacheConfig, AuditorAwareImpl, shared OpenAPI config
  validation/   -- ValidationMessageConstants, validation group interfaces, ValidationSequence
  constant/     -- Constants shared across all services

DOES NOT BELONG in common-lib:
  Business logic (order calculation, tax computation, discount rules)
  Service implementations (any class with @Service)
  Repository interfaces (any class with @Repository)
  Entity classes (any class with @Entity)
  Controllers (any class with @RestController)
```

### How To Implement

```java
// CORRECT -- common-lib contains only shared contract
// {project}-common-lib/src/main/java/{org}/{project}/common/
//   dto/ApiResponseDto.java
//   dto/{Entity}Dto.java               <- only if used by 2+ services
//   client/{Entity}ServiceClient.java
//   exception/ApplicationException.java
//   exception/CommonExceptionHandler.java
//   config/BaseCacheConfig.java
//   config/AuditorAwareImpl.java
//   validation/ValidationMessageConstants.java
//   validation/ValidationSequence.java
//   enums/{Entity}Status.java          <- only if used by 2+ services

// WRONG -- business logic in common-lib
// {project}-common-lib/src/main/java/{org}/{project}/common/
//   service/TaxCalculationService.java  <- business logic does not belong here
//   entity/{Entity}.java                <- entities are owned by individual services
```

### Why This Matters
Adding business logic to common-lib creates a hidden shared monolith. Every service that
depends on common-lib gets the business logic whether it needs it or not, creating tight
coupling that defeats the purpose of microservices.

---

## 2. All Dependencies Marked as Provided

### What We Follow
Every dependency in common-lib's `pom.xml` is marked `<scope>provided</scope>`. Consuming
services declare their own versions of the same dependencies. This prevents common-lib from
forcing transitive dependency versions onto consumers.

### How To Implement

```xml
<!-- CORRECT -- all common-lib deps are provided -->
<!-- {project}-common-lib/pom.xml -->
<dependencies>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.projectlombok</groupId>
        <artifactId>lombok</artifactId>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
        <scope>provided</scope>
    </dependency>

</dependencies>

<!-- WRONG -- compile-scope deps in common-lib -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
    <!-- No scope -- defaults to compile; forces JPA onto every consumer even if they don't use it -->
</dependency>
```

### Why This Matters
A common-lib with compile-scope Spring Security forces every service to include Security
even if it does not need authentication. This adds classpath conflicts and unused
auto-configuration to services that have no security requirements.

---

## 3. Shared Base Classes

### What We Follow
Common-lib provides these four abstract/concrete base classes that all services extend
rather than redefining:

| Class | Purpose | Services extend/use |
|---|---|---|
| `BaseCacheConfig` | L1+L2 hybrid cache setup | Override `getRedisCacheTtlOverrides()` |
| `CommonExceptionHandler` | Base @ExceptionHandler methods | Extend in `GlobalExceptionHandler` |
| `AuditorAwareImpl` | JPA auditing user resolution | Auto-configured via `@EnableJpaAuditing` |
| `ValidationMessageConstants` | Validation message strings | Extend in each Form class |

### How To Implement

```java
// CORRECT -- AuditorAwareImpl in common-lib
@Component("auditorAwareImpl")
public class AuditorAwareImpl implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.of("SYSTEM");
        }

        Object principal = authentication.getPrincipal();
        if (principal instanceof UserDetails userDetails) {
            return Optional.of(userDetails.getUsername());
        }

        return Optional.of(principal.toString());
    }
}

// WRONG -- AuditorAwareImpl redefined in each service
// service-a/config/AuditorAwareImpl.java  <- duplicated
// service-b/config/AuditorAwareImpl.java  <- same code, independent change history
```

### Why This Matters
Duplicated `AuditorAwareImpl` classes diverge: one service gets a bug fix (e.g., null
principal check), the other keeps the bug. The common-lib fix applies to all services
in a single release.

---

## 4. Versioning and Artifact Publication

### What We Follow
Common-lib uses semantic versioning (`1.0.0`, `1.1.0`, `2.0.0`). Patch versions are
backwards-compatible bug fixes. Minor versions add functionality without breaking changes.
Major versions contain breaking interface changes. Services pin to a minor version range.

### How To Implement

```xml
<!-- CORRECT -- services depend on a specific common-lib version -->
<!-- {service}/pom.xml -->
<dependency>
    <groupId>{org}.{project}</groupId>
    <artifactId>{project}-common-lib</artifactId>
    <version>1.2.0</version>
</dependency>

<!-- WRONG -- SNAPSHOT dependency in production builds -->
<dependency>
    <groupId>{org}.{project}</groupId>
    <artifactId>{project}-common-lib</artifactId>
    <version>1.2.0-SNAPSHOT</version>
    <!-- SNAPSHOT resolves to a different artifact on every build -- non-reproducible -->
</dependency>
```

### Why This Matters
A SNAPSHOT dependency resolves to whichever artifact was last published to the repository.
Two builds of the same commit can produce different JARs if common-lib was published between
them -- violating build reproducibility.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test in common-lib: no `@Service`, `@Repository`,
`@Entity`, or `@RestController` annotations in any class. Maven Enforcer plugin: no
compile-scope dependencies in common-lib POM (all must be provided or test).

**SEE ALSO:**
- 20-inter-service-communication.md -- Feign clients that live in common-lib client/
- 21-caching-strategy.md -- BaseCacheConfig in common-lib config/
- 19-exception-handling-hierarchy.md -- CommonExceptionHandler in common-lib
- 25-jpa-auditing-pattern.md -- AuditorAwareImpl in common-lib config/
