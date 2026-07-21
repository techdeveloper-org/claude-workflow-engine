---
description: "Level 2.2 - Interface+Impl pattern, transaction boundaries, Helper pattern, return types"
paths:
  - "src/**/service/**/*.java"
  - "src/**/service/impl/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Service Layer Conventions (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce consistent service layer structure using Interface + Impl + Helper
triple pattern, correct transaction annotations on the interface (not implementation),
and the rule that ALL service methods return `ApiResponseDto<T>` so the controller
never makes presentation decisions.

**APPLIES WHEN:** Spring Boot project with `@Service` annotated classes.

---

## 1. Interface + Implementation + Helper Triple Pattern

### What We Follow
Every domain service is split into three artifacts:
1. A public interface (`{Entity}Services`) defining the contract
2. A package-private implementation (`{Entity}ServicesImpl`) carrying the `@Service` annotation
3. An abstract package-private helper (`{Entity}ServiceHelper`) with shared lookups and builders

The implementation extends the helper and implements the interface.

### How To Implement

```java
// 1. Public interface (contract)
public interface {Entity}Services {

    @Transactional(rollbackFor = DataAccessException.class,
                   propagation = Propagation.REQUIRES_NEW)
    ApiResponseDto<{Entity}Dto> create({Entity}CreateForm form);

    @Transactional(propagation = Propagation.NEVER, readOnly = true)
    ApiResponseDto<{Entity}Dto> get{Entity}ById(Long id);

    @Transactional(rollbackFor = DataAccessException.class,
                   propagation = Propagation.REQUIRES_NEW)
    ApiResponseDto<Void> delete{Entity}(Long id);
}

// 2. Abstract helper (reusable lookups and entity builders)
@RequiredArgsConstructor
abstract class {Entity}ServiceHelper {

    protected final {Entity}Repository {entity}Repository;
    protected final {Entity}ServiceMessageConstants messages;

    protected {Entity} findById(Long id) {
        return {entity}Repository.findById(id)
            .orElseThrow(() -> new {Entity}NotFoundException(String.valueOf(id)));
    }

    protected {Entity}Dto mapToDto({Entity} entity) {
        return {Entity}Dto.builder()
            .id(entity.getId())
            .{field}(entity.get{Field}())
            .status(entity.getStatus())
            .statusDisplayName(entity.getStatus().getDisplayName())
            .createdAt(entity.getCreatedAt())
            .updatedAt(entity.getUpdatedAt())
            .build();
    }

    protected {Entity} buildEntity({Entity}CreateForm form) {
        {Entity} entity = new {Entity}();
        entity.set{Field}(form.get{Field}());
        entity.setStatus({Entity}Status.ACTIVE);
        return entity;
    }
}

// 3. Package-private implementation
@Service
@RequiredArgsConstructor
class {Entity}ServicesImpl extends {Entity}ServiceHelper implements {Entity}Services {

    @Override
    public ApiResponseDto<{Entity}Dto> create({Entity}CreateForm form) {
        {Entity} entity = buildEntity(form);
        {entity}Repository.save(entity);
        return ApiResponseDto.<{Entity}Dto>builder()
            .data(mapToDto(entity))
            .message(ServiceMessageConstants.{ENTITY}_CREATED_SUCCESS)
            .success(true)
            .status(201)
            .timestamp(LocalDateTime.now())
            .build();
    }

    @Override
    public ApiResponseDto<{Entity}Dto> get{Entity}ById(Long id) {
        return ApiResponseDto.<{Entity}Dto>builder()
            .data(mapToDto(findById(id)))
            .message(ServiceMessageConstants.{ENTITY}_FETCHED_SUCCESS)
            .success(true)
            .status(200)
            .timestamp(LocalDateTime.now())
            .build();
    }
}

// WRONG -- single class, no interface, no helper
@Service
public class {Entity}Service {
    // All logic in one class -- not testable at the interface contract level
    // findById duplicated across every service class
}
```

### Why This Matters
The helper pattern centralizes entity-lookup and mapping code that would otherwise be
duplicated in every `ServiceImpl`. The interface enables mocking in tests and ensures
the transaction contract is declared in one place.

---

## 2. Transaction Annotations on the Interface

### What We Follow
`@Transactional` is placed on the **interface** methods, not on the implementation.
Spring's transaction proxy wraps the interface; annotations on implementation methods
are ignored when calling through the proxy.

### How To Implement

```java
// CORRECT -- @Transactional on interface method
public interface {Entity}Services {
    @Transactional(rollbackFor = DataAccessException.class,
                   propagation = Propagation.REQUIRES_NEW)
    ApiResponseDto<{Entity}Dto> create({Entity}CreateForm form);

    @Transactional(propagation = Propagation.NEVER, readOnly = true)
    ApiResponseDto<List<{Entity}Dto>> list{Entity}();
}

// WRONG -- @Transactional on implementation method
@Service
public class {Entity}ServicesImpl implements {Entity}Services {
    @Transactional  // Ignored for calls coming through the interface proxy
    public ApiResponseDto<{Entity}Dto> create({Entity}CreateForm form) { ... }
}
```

Transaction rules:
- Write operations: `Propagation.REQUIRES_NEW`, `rollbackFor = DataAccessException.class`
- Read operations: `Propagation.NEVER`, `readOnly = true`
- NEVER use bare `@Transactional` without propagation -- defaults vary by provider

### Why This Matters
A `@Transactional` on the implementation class is silently ignored when the method is
invoked via the Spring-generated interface proxy, giving false confidence that writes
are transactionally protected.

---

## 3. Constructor Injection via @RequiredArgsConstructor

### What We Follow
All service dependencies are declared as `final` fields. Lombok `@RequiredArgsConstructor`
generates the constructor. Never use field injection (`@Autowired` on a field).

### How To Implement

```java
// CORRECT -- constructor injection
@Service
@RequiredArgsConstructor
class {Entity}ServicesImpl extends {Entity}ServiceHelper implements {Entity}Services {

    private final AnotherService anotherService;  // injected via constructor
}

// WRONG -- field injection
@Service
public class {Entity}ServicesImpl implements {Entity}Services {
    @Autowired
    private AnotherService anotherService;  // cannot be final; not testable without Spring
}
```

### Why This Matters
Field injection prevents creating the service in a unit test without starting the Spring
context. Constructor injection allows `new {Entity}ServicesImpl(mockRepo, ...)` in tests.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test: all classes in `service/impl/` must
be package-private. All fields in `@Service` classes must be `final` (enforces constructor
injection). Code review: no `@Transactional` directly on implementation classes.

**SEE ALSO:**
- 17-api-response-wrapper.md -- ApiResponseDto structure returned by all service methods
- 19-exception-handling-hierarchy.md -- exceptions thrown from helper findById methods
- 28-test-coverage-enforcement.md -- JUnit 5 testing of service interfaces
