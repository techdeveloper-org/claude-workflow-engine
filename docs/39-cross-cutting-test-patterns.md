---
description: "Level 2.3 - Cross-layer test contracts: response wrapper, idempotent delete, case-insensitive duplication, sort, cache events"
paths:
  - "src/test/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Cross-Cutting Test Patterns (Level 2.3 - Spring Boot)

**PURPOSE:** Define the test contracts that span multiple application layers and must be
enforced consistently across the entire codebase. These are the patterns that, when broken
in one layer, silently corrupt behaviour in all consuming layers. Each pattern includes:
which layers it spans, what to verify in tests, and why inconsistency is catastrophic.

**APPLIES WHEN:** Any Spring Boot REST microservice with Controller → Service → Repository
layers and an `ApiResponse<T>` response wrapper.

---

## Pattern 1: ApiResponse<T> Wrapper Consistency

**Spans:** Controller Layer (Layer 3) + Exception Handler Layer (Layer 6)

### What We Follow
Every endpoint — success and error — returns the same `ApiResponse<T>` wrapper structure:

```
ApiResponse<T> {
    boolean success;
    int     status;
    String  message;
    T       data;
}
```

No endpoint returns a raw `T` on success and a wrapped error on failure. No endpoint
returns `null` for `message` on success. No endpoint returns a non-null `data` on error.

### How To Implement

```java
// CORRECT -- Wrapper consistency tests across Controller and Exception Handler
@ExtendWith(MockitoExtension.class)
class ApiResponseConsistencyTest {

    @Mock private ResourceService resourceService;
    @InjectMocks private ResourceRestController controller;
    @InjectMocks private GlobalExceptionHandler handler;

    // Test 1: Success response has success=true, non-null data, non-null message
    @Test
    @DisplayName("should return ApiResponse with success=true and non-null data on POST success")
    void shouldReturnApiResponseWithSuccessTrueAndNonNullDataOnPostSuccess() {
        ResourceDto dto = new ResourceDto(1L, "Name", "/path");
        when(resourceService.add(any())).thenReturn(ApiResponse.created(dto));

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.create(new ResourceForm());

        assertThat(response.getBody().isSuccess()).isTrue();
        assertThat(response.getBody().getData()).isNotNull();
        assertThat(response.getBody().getStatus()).isEqualTo(201);
        assertThat(response.getBody().getMessage()).isNotBlank();
    }

    // Test 2: Error response has success=false, null data, non-null message
    @Test
    @DisplayName("should return ApiResponse with success=false and null data on exception")
    void shouldReturnApiResponseWithSuccessFalseAndNullDataOnException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicate(new DuplicateResourceException("exists"));

        assertThat(response.getBody().isSuccess()).isFalse();
        assertThat(response.getBody().getData()).isNull();
        assertThat(response.getBody().getMessage()).isNotBlank();
    }

    // Test 3: HTTP status in ResponseEntity matches body status field (both layers)
    @Test
    @DisplayName("should have matching HTTP status and body status in controller success response")
    void shouldHaveMatchingHttpStatusAndBodyStatusInSuccessResponse() {
        when(resourceService.add(any())).thenReturn(ApiResponse.created(new ResourceDto()));

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.create(new ResourceForm());

        assertThat(response.getStatusCodeValue())
            .isEqualTo(response.getBody().getStatus());
    }

    @Test
    @DisplayName("should have matching HTTP status and body status in exception handler response")
    void shouldHaveMatchingHttpStatusAndBodyStatusInErrorResponse() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleNotFound(new ResourceNotFoundException("not found"));

        assertThat(response.getStatusCodeValue())
            .isEqualTo(response.getBody().getStatus());
    }
}

// WRONG -- raw object returned on success, wrapper only on error
@GetMapping("/{id}")
public ResourceDto getById(@PathVariable Long id) { // returns raw DTO
    return service.getById(id);
}
@ExceptionHandler
public ResponseEntity<ApiResponse<Void>> handleError(Exception e) { // returns wrapper
    return ResponseEntity.status(500).body(ApiResponse.error(...)); // inconsistent!
}
```

### Why This Matters
API clients (mobile apps, frontend SPAs, API gateways) that parse `response.success` to
determine routing cannot function when the response structure changes between success and
error cases. Inconsistency forces clients to implement both parsing paths,
doubling client-side error handling complexity.

---

## Pattern 2: success=false on All Error Responses

**Spans:** Exception Handler Layer (Layer 6)

### What We Follow
Every `@ExceptionHandler` method, regardless of the HTTP status code returned, must
set `success = false` in the `ApiResponse` body. This must be tested on each handler.

### How To Implement

```java
// CORRECT -- Consistent success=false across all handlers
@Test
@DisplayName("should return success=false across all registered exception handlers")
void shouldReturnSuccessFalseAcrossAllRegisteredExceptionHandlers() {
    GlobalExceptionHandler handler = new GlobalExceptionHandler();

    // All handlers must return success=false
    Map<String, ResponseEntity<?>> responses = Map.of(
        "duplicate-name",      handler.handleDuplicate(new DuplicateResourceException("x")),
        "duplicate-path",      handler.handleConflict(new ResourceConflictException("y")),
        "not-found",           handler.handleNotFound(new ResourceNotFoundException("z")),
        "data-integrity",      handler.handleDataIntegrity(new DataIntegrityViolationException("c"))
    );

    responses.forEach((name, response) -> {
        ApiResponse<?> body = (ApiResponse<?>) response.getBody();
        assertThat(body.isSuccess())
            .as("Handler '%s' should return success=false", name)
            .isFalse();
    });
}

// WRONG -- one handler accidentally returns success=true on error
@ExceptionHandler(ResourceNotFoundException.class)
public ResponseEntity<ApiResponse<Void>> handleNotFound(ResourceNotFoundException ex) {
    return ResponseEntity.status(404)
        .body(new ApiResponse<>(true, 404, ex.getMessage(), null)); // BUG: true!
}
```

### Why This Matters
Clients that check `if (response.success)` to branch between success and error processing
will process a 404 NOT FOUND response as a success if `success=true` is returned by
mistake. This triggers destructive downstream operations on null data.

---

## Pattern 3: HTTP Status in ResponseEntity Matches Body Status Field

**Spans:** Controller Layer (Layer 3) + Exception Handler Layer (Layer 6)

### What We Follow
The integer `status` field in the `ApiResponse` body must always equal
`ResponseEntity.getStatusCodeValue()`. Logging middleware, request tracing, and API
gateways that log both the HTTP status and the body status must see identical values.

### How To Implement

```java
// CORRECT -- Status consistency test
@Test
@DisplayName("should have identical HTTP status code and body status field in all responses")
void shouldHaveIdenticalHttpStatusAndBodyStatusFieldInAllResponses() {
    // Test at least: 201, 200, 409, 404, 500
    assertStatusConsistency(controller.create(validForm()), 201);
    assertStatusConsistency(controller.getById(1L), 200);
    assertStatusConsistency(handler.handleDuplicate(dupEx()), 409);
    assertStatusConsistency(handler.handleNotFound(notFoundEx()), 404);
}

private void assertStatusConsistency(ResponseEntity<ApiResponse<?>> response, int expectedStatus) {
    assertThat(response.getStatusCodeValue())
        .as("HTTP status code mismatch for status %d", expectedStatus)
        .isEqualTo(expectedStatus);
    assertThat(response.getBody().getStatus())
        .as("Body status field mismatch for status %d", expectedStatus)
        .isEqualTo(expectedStatus);
    assertThat(response.getStatusCodeValue())
        .as("HTTP status and body status must be identical")
        .isEqualTo(response.getBody().getStatus());
}

// WRONG -- HTTP status is 409 but body status is 400
return ResponseEntity.status(HttpStatus.CONFLICT)
    .body(new ApiResponse<>(false, 400, "duplicate", null)); // body says 400, HTTP says 409
```

### Why This Matters
API gateways that route error responses by HTTP status code will misroute if the body
contains a different status. Distributed tracing systems that record both the HTTP status
and the body status will log contradictory values, making incident diagnosis extremely
difficult.

---

## Pattern 4: Case-Insensitive Duplicate Detection

**Spans:** Service Layer (Layer 4)

### What We Follow
Repository methods used for uniqueness checks must use `IgnoreCase` variants:
- `existsByNameIgnoreCase(String name)` — for add operations
- `existsByNameIgnoreCaseAndIdNot(String name, Long id)` — for update operations
(excludes the current entity from the check)

Both the base and the update variants must be tested with case-variant inputs.

### How To Implement

```java
// CORRECT -- Case-insensitive duplicate detection tests
@ExtendWith(MockitoExtension.class)
class ResourceServiceDuplicateDetectionTest {

    @Mock private ResourceRepository resourceRepository;
    @InjectMocks private ResourceServiceImpl resourceService;

    // Test 1: Adding with same-name but different case throws
    @Test
    @DisplayName("should throw when name matches existing resource with different case on add")
    void shouldThrowWhenNameMatchesExistingResourceWithDifferentCaseOnAdd() {
        // "resource" already exists, "RESOURCE" is a case-variant duplicate
        when(resourceRepository.existsByNameIgnoreCase("RESOURCE")).thenReturn(true);

        assertThatThrownBy(() -> resourceService.add(new ResourceForm("RESOURCE", "/new")))
            .isInstanceOf(DuplicateResourceException.class);
    }

    // Test 2: Updating with taken name (different case, different entity) throws
    @Test
    @DisplayName("should throw when updating name to a value taken by another resource (different case)")
    void shouldThrowWhenUpdatingNameToValueTakenByAnotherResourceDifferentCase() {
        ResourceEntity existing = new ResourceEntity(1L, "OldName", "/old");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("TAKEN", 1L)).thenReturn(true);

        assertThatThrownBy(() -> resourceService.update(1L, new ResourceForm("TAKEN", "/new")))
            .isInstanceOf(DuplicateResourceException.class);
    }

    // Test 3: Updating with own current name (excluded by IdNot) does NOT throw
    @Test
    @DisplayName("should not throw when updating resource with its own current name")
    void shouldNotThrowWhenUpdatingResourceWithOwnCurrentName() {
        ResourceEntity existing = new ResourceEntity(1L, "MyName", "/path");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("MyName", 1L)).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCaseAndIdNot("/path", 1L)).thenReturn(false);
        when(resourceRepository.save(any())).thenReturn(existing);

        assertThatNoException().isThrownBy(() ->
            resourceService.update(1L, new ResourceForm("MyName", "/path")));
    }
}

// WRONG -- case-sensitive check misses "DASHBOARD" when "dashboard" exists
boolean exists = resourceRepository.existsByName(name); // case-sensitive!
// On PostgreSQL with COLLATE "en_US.utf8": "DASHBOARD" != "dashboard" → duplicate passes
// On MySQL with utf8mb4_unicode_ci: "DASHBOARD" == "dashboard" → duplicate caught
// Result: test passes on dev (MySQL) but fails in production (PostgreSQL)
```

### Why This Matters
Case-sensitivity behaviour differs between databases. `existsByName()` may pass on a
case-insensitive database but allow "Dashboard" and "DASHBOARD" as two separate resources
on a case-sensitive PostgreSQL collation. The `IgnoreCase` variant enforces consistent
application-level uniqueness regardless of database collation.

---

## Pattern 5: Idempotent Delete

**Spans:** Service Layer (Layer 4)

### What We Follow
`service.delete(nonExistentId)` must NOT throw `ResourceNotFoundException`.
JPA's `deleteById()` is silent on missing IDs — the service must not introduce an
artificial existence check that makes delete non-idempotent.

### How To Implement

```java
// CORRECT -- Idempotent delete test
@ExtendWith(MockitoExtension.class)
class ResourceServiceIdempotentDeleteTest {

    @Mock private ResourceRepository resourceRepository;
    @Mock private EventPublisher eventPublisher;
    @InjectMocks private ResourceServiceImpl resourceService;

    // Test 1: Deleting non-existent ID returns success (idempotent)
    @Test
    @DisplayName("should not throw when delete is called with an ID that does not exist")
    void shouldNotThrowWhenDeleteCalledWithNonExistentId() {
        doNothing().when(resourceRepository).deleteById(999L);

        assertThatNoException().isThrownBy(() -> resourceService.delete(999L));
    }

    // Test 2: Second delete on same ID also succeeds
    @Test
    @DisplayName("should succeed on repeated delete calls for the same ID")
    void shouldSucceedOnRepeatedDeleteCallsForSameId() {
        doNothing().when(resourceRepository).deleteById(1L);

        assertThatNoException().isThrownBy(() -> {
            resourceService.delete(1L);
            resourceService.delete(1L); // second call — must not throw
        });
    }
}

// WRONG -- findById check before delete makes it non-idempotent
public void delete(Long id) {
    if (!resourceRepository.existsById(id)) {
        throw new ResourceNotFoundException("Resource not found: " + id); // NON-IDEMPOTENT!
    }
    resourceRepository.deleteById(id);
}
// REST spec: DELETE /resources/1 should return 200/204 even if 1 no longer exists
// A client that retries a DELETE after a timeout will get a 404 on the retry — wrong
```

### Why This Matters
REST clients that retry idempotent operations on timeout expect DELETE to be idempotent.
A non-idempotent delete converts a successful retry into a 404 error that the client
must then distinguish from a genuinely missing resource.

---

## Pattern 6: Sort by ID ASC — Validated with argThat

**Spans:** Service Layer (Layer 4)

### What We Follow
When the service retrieves all resources, it must pass `Sort.by(Sort.Direction.ASC, "id")`
to the repository. This contract must be verified with `argThat()` — not `any(Sort.class)`.
Using `any(Sort.class)` would allow the sort field to silently change from "id" to "name"
or the direction to flip from ASC to DESC.

### How To Implement

```java
// CORRECT -- Exact Sort validation with argThat
@Test
@DisplayName("should pass Sort.by(ASC, id) to repository when getting all resources")
void shouldPassSortByIdAscToRepositoryWhenGettingAllResources() {
    when(resourceRepository.findAll(any(Sort.class))).thenReturn(Collections.emptyList());

    resourceService.getAll();

    verify(resourceRepository).findAll(
        argThat(sort -> sort.equals(Sort.by(Sort.Direction.ASC, "id"))));
}

// Test the actual ordering of results (integration-level — use H2 @DataJpaTest)
@Test
@DisplayName("should return resources in ID-ascending order")
void shouldReturnResourcesInIdAscendingOrder() {
    List<ResourceEntity> unordered = List.of(
        new ResourceEntity(3L, "C", "/c"),
        new ResourceEntity(1L, "A", "/a"),
        new ResourceEntity(2L, "B", "/b"));
    when(resourceRepository.findAll(any(Sort.class))).thenReturn(unordered);

    ApiResponse<Set<ResourceDto>> result = resourceService.getAll();

    List<Long> ids = result.getData().stream()
        .map(ResourceDto::getId).collect(Collectors.toList());
    assertThat(ids).containsExactly(3L, 1L, 2L); // order from repo is preserved in LinkedHashSet
}

// WRONG -- any(Sort.class) accepts Sort.by(DESC, "name") silently
verify(resourceRepository).findAll(any(Sort.class)); // too permissive
```

### Why This Matters
A UI that renders a resource list relies on stable ordering. If the sort direction
accidentally flips to DESC on a code change, the UI shows the list in reverse. `argThat()`
validates the exact contract, making the test fail immediately on any sort regression.

---

## Pattern 7: Cache Invalidation Event — CREATE / UPDATE / DELETE Coverage

**Spans:** Service Layer (Layer 4) + Event Publisher Layer (Layer 8)

### What We Follow
Every mutating service operation must publish the correct event type. The service test
verifies delegation; the publisher test verifies the payload. Both levels are required.

### How To Implement

```java
// CORRECT -- Service verifies delegation; Publisher verifies payload
// ---------- SERVICE LAYER TEST ----------
@Test
@DisplayName("service.add() should trigger CREATE event publication")
void serviceShouldTriggerCreateEventPublication() {
    when(resourceRepository.existsByNameIgnoreCase(any())).thenReturn(false);
    when(resourceRepository.existsByPathIgnoreCase(any())).thenReturn(false);
    when(resourceRepository.save(any())).thenReturn(new ResourceEntity(1L, "Name", "/path"));

    resourceService.add(new ResourceForm("Name", "/path"));

    verify(eventPublisher, times(1)).publishCreate(null);
}

@Test
@DisplayName("service.update() should trigger UPDATE event with entity ID")
void serviceShouldTriggerUpdateEventWithEntityId() {
    ResourceEntity entity = new ResourceEntity(1L, "Old", "/old");
    when(resourceRepository.findById(1L)).thenReturn(Optional.of(entity));
    when(resourceRepository.existsByNameIgnoreCaseAndIdNot(any(), eq(1L))).thenReturn(false);
    when(resourceRepository.existsByPathIgnoreCaseAndIdNot(any(), eq(1L))).thenReturn(false);
    when(resourceRepository.save(any())).thenReturn(entity);

    resourceService.update(1L, new ResourceForm("New", "/new"));

    verify(eventPublisher, times(1)).publishUpdate(1L);
}

@Test
@DisplayName("service.delete() should trigger DELETE event with entity ID")
void serviceShouldTriggerDeleteEventWithEntityId() {
    doNothing().when(resourceRepository).deleteById(1L);

    resourceService.delete(1L);

    verify(eventPublisher, times(1)).publishDelete(1L);
}

// ---------- PUBLISHER LAYER TEST ----------
@Test
@DisplayName("publisher should emit structurally distinct event types for all operations")
void publisherShouldEmitStructurallyDistinctEventTypes() {
    List<CacheInvalidationEvent> captured = new ArrayList<>();
    doAnswer(inv -> { captured.add(inv.getArgument(1)); return null; })
        .when(redisTemplate).convertAndSend(anyString(), any());

    publisher.publishCreate(null);
    publisher.publishUpdate(1L);
    publisher.publishDelete(1L);

    Set<EventType> types = captured.stream()
        .map(CacheInvalidationEvent::getEventType).collect(Collectors.toSet());
    assertThat(types).containsExactlyInAnyOrder(
        EventType.CREATE, EventType.UPDATE, EventType.DELETE);
}

// WRONG -- service.delete() not verified to publish event
// Cache invalidation never happens → stale data served until TTL expires
public void delete(Long id) {
    resourceRepository.deleteById(id);
    // forgot to call eventPublisher.publishDelete(id)
}
```

### Why This Matters
Missing cache invalidation events cause stale data to be served from cache after a
resource is deleted or updated. The resource appears to exist in the API even after it
has been deleted from the database. This is impossible to detect without this test
because the database write succeeds and the HTTP response is 200 OK.

---

## Cross-Cutting Checklist

Use this checklist when writing or reviewing tests for any new resource/entity:

```
Response Wrapper Consistency:
  [ ] POST success:    success=true, status=201, data=non-null, message=non-blank
  [ ] PUT success:     success=true, status=200, data=non-null, message=non-blank
  [ ] GET success:     success=true, status=200, data=non-null
  [ ] DELETE success:  success=true, status=200
  [ ] Any error:       success=false, data=null, message=non-blank
  [ ] HTTP status code == body.status in ALL responses

Case-Insensitive Duplicate Detection:
  [ ] existsByNameIgnoreCase() used for add
  [ ] existsByNameIgnoreCaseAndIdNot() used for update
  [ ] Test: upper-case variant of existing name throws on add
  [ ] Test: own current name does NOT throw on update

Idempotent Delete:
  [ ] service.delete(nonExistentId) does NOT throw
  [ ] Repeated delete calls succeed (no state-based failure)

Sort Contract:
  [ ] verify(repo).findAll(argThat(s -> s.equals(Sort.by(ASC, "id"))))
  [ ] NOT: verify(repo).findAll(any(Sort.class))

Cache Invalidation Events:
  [ ] service.add()    → verify(publisher).publishCreate(null)
  [ ] service.update() → verify(publisher).publishUpdate(entityId)
  [ ] service.delete() → verify(publisher).publishDelete(entityId)
  [ ] publisher: all three event types are structurally distinct
```

---

**ENFORCEMENT:** The cross-cutting checklist above is a mandatory code review checkpoint
for every PR that introduces a new entity/resource type. Any PR that adds a new service
without all seven pattern tests will be returned to the author before review.

**SEE ALSO:**
- 17-api-response-wrapper.md -- ApiResponse<T> wrapper implementation conventions
- 18-service-layer-conventions.md -- service method return types and exception contracts
- 19-exception-handling-hierarchy.md -- exception class hierarchy and HTTP status mapping
- 21-caching-strategy.md -- cache name constants and eviction strategy
- 35-positive-testing-standards.md -- layer-by-layer positive test scenarios
- 36-negative-testing-standards.md -- layer-by-layer negative test scenarios
- 37-edge-case-testing-standards.md -- boundary and edge case tests
- 38-test-mocking-strategy.md -- isolation strategies per layer
