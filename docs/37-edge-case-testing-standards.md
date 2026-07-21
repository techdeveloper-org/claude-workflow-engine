---
description: "Level 2.3 - Edge case test scenarios for boundary values, nulls, combined failures, security/path-params/error-structure"
paths:
  - "src/test/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Edge Case Testing Standards (Level 2.3 - Spring Boot)

**PURPOSE:** Define the mandatory edge case and boundary test scenarios for every Spring Boot
REST microservice layer. Edge case tests verify behaviour at the extremes of input space:
null values, empty collections, maximum/minimum boundary lengths, special characters, type
limits (Long.MAX_VALUE), combined multi-field failures, and case-insensitive string matching.
These are the tests that always catch the regressions no one expects.

**APPLIES WHEN:** Any Spring Boot REST microservice with Controller → Service → Repository layers.

---

## 1. Bootstrap Layer — Edge Case Tests

### What We Follow
The main method must gracefully handle any argument array at runtime — including multiple
JVM flags. The forwarding contract must be verified with the exact args passed.

### How To Implement

```java
// CORRECT -- Bootstrap edge case tests
@ExtendWith(MockitoExtension.class)
class ApplicationBootstrapEdgeCaseTest {

    // E11: main() with multiple args forwards all
    @Test
    @DisplayName("should forward all multiple args to SpringApplication.run()")
    void shouldForwardAllMultipleArgsToSpringApplicationRun() {
        String[] args = {"--server.port=9090", "--spring.profiles.active=prod", "--debug"};
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            ArgumentCaptor<String[]> captor = ArgumentCaptor.forClass(String[].class);
            mocked.when(() -> SpringApplication.run(any(Class.class), captor.capture()))
                  .thenReturn(null);

            MyServiceApplication.main(args);

            assertThat(captor.getValue()).containsExactly(
                "--server.port=9090", "--spring.profiles.active=prod", "--debug");
        }
    }
}
```

### Why This Matters
Production Kubernetes deployments inject multiple JVM arguments via the container CMD.
Verifying multi-arg forwarding prevents silent argument loss caused by incorrect varargs
spreading or array copying.

---

## 2. Configuration Layer — Edge Case Tests

### What We Follow
Cache name constants must all be distinct. Duplicate constant values cause the cache
manager to merge two logically separate caches, leading to cross-contamination.

### How To Implement

```java
// CORRECT -- Config edge case tests
class CacheConfigEdgeCaseTest {

    // E17: All constants are distinct (no accidental duplicates)
    @Test
    @DisplayName("should have distinct values for all cache name constants")
    void shouldHaveDistinctValuesForAllCacheNameConstants() {
        Set<String> constants = Set.of(
            CacheConfig.CACHE_BY_ID,
            CacheConfig.CACHE_ALL,
            CacheConfig.CACHE_COUNT);
        // If any two constants are equal the set size will be less than 3
        assertThat(constants).hasSize(3);
    }
}
```

### Why This Matters
Two constants with the same value map to the same physical cache region. An update
to one evicts entries from the other, causing spurious cache misses that are
indistinguishable from normal eviction in monitoring dashboards.

---

## 3. Controller Layer — Edge Case Tests

### What We Follow
Empty collection responses must not be null. The ordered collection type
(LinkedHashSet) must be preserved in the response body.

### How To Implement

```java
// CORRECT -- Controller layer edge case tests
@ExtendWith(MockitoExtension.class)
class ResourceRestControllerEdgeCaseTest {

    @Mock private ResourceService resourceService;
    @InjectMocks private ResourceRestController controller;

    // E28: GET all with empty data returns empty collection, not null
    @Test
    @DisplayName("should return empty collection (not null) when no resources exist")
    void shouldReturnEmptyCollectionNotNullWhenNoResourcesExist() {
        when(resourceService.getAll())
            .thenReturn(ApiResponse.ok(new LinkedHashSet<>()));

        ResponseEntity<ApiResponse<Set<ResourceDto>>> response = controller.getAll();

        assertThat(response.getBody().getData()).isNotNull();
        assertThat(response.getBody().getData()).isEmpty();
    }

    // E29: GET all preserves LinkedHashSet type (ordering contract)
    @Test
    @DisplayName("should preserve LinkedHashSet type in response body for ordered results")
    void shouldPreserveLinkedHashSetTypeInResponseBody() {
        LinkedHashSet<ResourceDto> ordered = new LinkedHashSet<>(List.of(
            new ResourceDto(1L, "Alpha", "/alpha"),
            new ResourceDto(2L, "Beta", "/beta")));
        when(resourceService.getAll()).thenReturn(ApiResponse.ok(ordered));

        ResponseEntity<ApiResponse<Set<ResourceDto>>> response = controller.getAll();

        assertThat(response.getBody().getData()).isInstanceOf(LinkedHashSet.class);
    }

    // E30: Service invoked exactly once per controller call (no accidental double-call)
    @Test
    @DisplayName("should invoke service method exactly once per controller call")
    void shouldInvokeServiceMethodExactlyOncePerControllerCall() {
        when(resourceService.getById(1L)).thenReturn(ApiResponse.ok(new ResourceDto()));

        controller.getById(1L);

        verify(resourceService, times(1)).getById(1L);
    }
}
```

### Why This Matters
A null collection in the response body causes a `NullPointerException` in any client
iterating over the response. A `HashSet` instead of `LinkedHashSet` breaks clients
that expect stable ordering (e.g., paginated UI rendering).

---

## 4. Service Layer — Edge Case Tests

### What We Follow
Case-insensitive duplicate detection, empty collection returns, idempotent delete,
null publisher safety, and exact Sort validation.

### How To Implement

```java
// CORRECT -- Service layer edge case tests
@ExtendWith(MockitoExtension.class)
class ResourceServiceImplEdgeCaseTest {

    @Mock private ResourceRepository resourceRepository;
    @Mock private EventPublisher eventPublisher;
    @InjectMocks private ResourceServiceImpl resourceService;

    // E46: Case-insensitive duplicate name detection
    @Test
    @DisplayName("should throw DuplicateResourceException when name differs only in case")
    void shouldThrowDuplicateResourceExceptionWhenNameDiffersOnlyInCase() {
        // "resource" already exists, adding "RESOURCE" — same logical name
        when(resourceRepository.existsByNameIgnoreCase("RESOURCE")).thenReturn(true);

        assertThatThrownBy(() -> resourceService.add(new ResourceForm("RESOURCE", "/new")))
            .isInstanceOf(DuplicateResourceException.class);

        verify(resourceRepository, never()).save(any());
    }

    // E47: Get all — empty list returns empty Set, not null
    @Test
    @DisplayName("should return empty set (not null) when no resources exist in repository")
    void shouldReturnEmptySetNotNullWhenNoResourcesExist() {
        when(resourceRepository.findAll(any(Sort.class))).thenReturn(Collections.emptyList());

        ApiResponse<Set<ResourceDto>> result = resourceService.getAll();

        assertThat(result.getData()).isNotNull();
        assertThat(result.getData()).isEmpty();
    }

    // E48: Delete non-existent ID — JPA idempotent, no exception thrown
    @Test
    @DisplayName("should not throw when delete is called with a non-existent ID (idempotent)")
    void shouldNotThrowWhenDeleteCalledWithNonExistentId() {
        doNothing().when(resourceRepository).deleteById(999L);

        assertThatNoException().isThrownBy(() -> resourceService.delete(999L));
    }

    // E49: Delete with null EventPublisher — no NullPointerException
    @Test
    @DisplayName("should not throw NullPointerException when EventPublisher is null")
    void shouldNotThrowNullPointerExceptionWhenEventPublisherIsNull() {
        // Inject service with null publisher via direct constructor or reflection
        ResourceServiceImpl serviceWithNullPublisher =
            new ResourceServiceImpl(resourceRepository, null);
        doNothing().when(resourceRepository).deleteById(1L);

        assertThatNoException().isThrownBy(() -> serviceWithNullPublisher.delete(1L));
    }

    // E50: Sort argument is exactly Sort.by(ASC, "id") — validated with argThat
    @Test
    @DisplayName("should pass Sort.by(ASC, id) exactly to repository when getting all resources")
    void shouldPassExactSortByIdAscToRepository() {
        when(resourceRepository.findAll(any(Sort.class))).thenReturn(Collections.emptyList());

        resourceService.getAll();

        verify(resourceRepository).findAll(
            argThat(sort -> sort.equals(Sort.by(Sort.Direction.ASC, "id"))));
    }
}
```

### Why This Matters
- **Case-insensitive detection:** PostgreSQL with `COLLATE "C"` is case-sensitive, but
  MySQL often isn't. Using `existsByNameIgnoreCase` at the service layer ensures consistent
  behaviour regardless of database collation.
- **Idempotent delete:** REST clients that retry on timeout will call DELETE twice.
  If the second call throws 404, the client incorrectly treats a successful delete as an error.
- **Null publisher safety:** Integration tests that stub out Redis will inject null.
  A NPE here crashes the test suite and masks coverage for the rest of the delete path.

---

## 5. Entity Layer — Edge Case Tests

### What We Follow
Entities must handle boundary values (maximum length strings, Long.MAX_VALUE IDs),
special characters, null fields, whitespace strings, and null-ID equality without
throwing any exceptions.

### How To Implement

```java
// CORRECT -- Entity edge case tests
class ResourceEntityEdgeCaseTest {

    // E67: Boundary — name at exactly 50 characters
    @Test
    @DisplayName("should store and return name of exactly 50 characters without truncation")
    void shouldStoreAndReturnNameOfExactly50Characters() {
        String maxName = "A".repeat(50);
        ResourceEntity entity = new ResourceEntity();
        entity.setName(maxName);
        assertThat(entity.getName()).hasSize(50);
    }

    // E68: Boundary — path at exactly 50 characters
    @Test
    @DisplayName("should store and return path of exactly 50 characters without truncation")
    void shouldStoreAndReturnPathOfExactly50Characters() {
        String maxPath = "/p".repeat(25); // 50 chars
        ResourceEntity entity = new ResourceEntity();
        entity.setPath(maxPath);
        assertThat(entity.getPath()).hasSize(50);
    }

    // E69: Boundary — Long.MAX_VALUE as ID
    @Test
    @DisplayName("should store and return Long.MAX_VALUE as entity ID without overflow")
    void shouldStoreLongMaxValueAsEntityId() {
        ResourceEntity entity = new ResourceEntity(Long.MAX_VALUE, "Name", "/path");
        assertThat(entity.getId()).isEqualTo(Long.MAX_VALUE);
    }

    // E70: Boundary — minimum ID value of 1
    @Test
    @DisplayName("should store and return minimum valid ID of 1")
    void shouldStoreMinimumValidIdOfOne() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        assertThat(entity.getId()).isEqualTo(1L);
    }

    // E71: Special characters in name — stored exactly
    @Test
    @DisplayName("should store and return name with special characters without modification")
    void shouldStoreNameWithSpecialCharactersExactly() {
        String specialName = "Res & Co. (2024) @#$%";
        ResourceEntity entity = new ResourceEntity();
        entity.setName(specialName);
        assertThat(entity.getName()).isEqualTo(specialName);
    }

    // E72: Whitespace-only string in name — stored without transformation
    @Test
    @DisplayName("should store whitespace-only name without trimming or transformation")
    void shouldStoreWhitespaceOnlyNameWithoutTransformation() {
        ResourceEntity entity = new ResourceEntity();
        entity.setName("   ");
        // Entity is a data container — transformation is the validator's job, not the entity's
        assertThat(entity.getName()).isEqualTo("   ");
    }

    // E73: Two instances with null IDs and same data are equal
    @Test
    @DisplayName("should be equal when both instances have null IDs and same field values")
    void shouldBeEqualWhenBothInstancesHaveNullIdsAndSameFieldValues() {
        ResourceEntity e1 = new ResourceEntity(null, "Name", "/path");
        ResourceEntity e2 = new ResourceEntity(null, "Name", "/path");
        assertThat(e1).isEqualTo(e2);
        assertThat(e1.hashCode()).isEqualTo(e2.hashCode());
    }

    // Additional: Null ID stored without NPE
    @Test
    @DisplayName("should allow null ID to be set without throwing")
    void shouldAllowNullIdWithoutThrowing() {
        ResourceEntity entity = new ResourceEntity();
        assertThatNoException().isThrownBy(() -> entity.setId(null));
        assertThat(entity.getId()).isNull();
    }
}
```

### Why This Matters
- **Long.MAX_VALUE:** Auto-generated sequence IDs in PostgreSQL eventually reach large
  values. Overflow during arithmetic comparison breaks equality.
- **Null-ID equality:** JPA entities before persistence have null IDs. A broken
  `equals()` that NPEs on null ID crashes `Set.contains()` during deduplication.
- **Whitespace name:** Trimming in the entity layer hides a bug — two entities with
  "Name" and " Name " compare as equal in the database but not in Java code.

---

## 6. Exception Handler Layer — Edge Case Tests

### What We Follow
Exception handlers must maintain cross-handler consistency. Both the HTTP status and
the body status field must match across all handlers of the same severity class (e.g.,
all 409 CONFLICT handlers must behave identically).

### How To Implement

```java
// CORRECT -- Exception handler edge case tests
@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerEdgeCaseTest {

    @InjectMocks private GlobalExceptionHandler handler;

    // E80: Both conflict handlers return identical HTTP status
    @Test
    @DisplayName("should return identical HTTP status code from both 409 CONFLICT handlers")
    void shouldReturnIdenticalHttpStatusFromBothConflictHandlers() {
        ResponseEntity<ApiResponse<Void>> r1 =
            handler.handleDuplicateName(new DuplicateResourceException("e1"));
        ResponseEntity<ApiResponse<Void>> r2 =
            handler.handleDuplicatePath(new ResourceConflictException("e2"));

        assertThat(r1.getStatusCode()).isEqualTo(r2.getStatusCode());
    }

    // E81: Both conflict handlers return success=false consistently
    @Test
    @DisplayName("should return success=false from all conflict handlers consistently")
    void shouldReturnSuccessFalseFromAllConflictHandlersConsistently() {
        boolean s1 = handler.handleDuplicateName(
            new DuplicateResourceException("e1")).getBody().isSuccess();
        boolean s2 = handler.handleDuplicatePath(
            new ResourceConflictException("e2")).getBody().isSuccess();

        assertThat(s1).isFalse();
        assertThat(s2).isFalse();
    }

    // E-extra: Body status matches ResponseEntity status for all handlers
    @Test
    @DisplayName("should have matching HTTP status value and body status field in all handlers")
    void shouldHaveMatchingStatusInAllHandlers() {
        ResponseEntity<ApiResponse<Void>> r1 =
            handler.handleDuplicateName(new DuplicateResourceException("x"));
        ResponseEntity<ApiResponse<Void>> r2 =
            handler.handleDuplicatePath(new ResourceConflictException("y"));

        assertThat(r1.getStatusCodeValue()).isEqualTo(r1.getBody().getStatus());
        assertThat(r2.getStatusCodeValue()).isEqualTo(r2.getBody().getStatus());
    }
}
```

### Why This Matters
Inconsistent status codes across handlers of the same type break API client error
classification logic. If DuplicateName returns 409 and DuplicatePath returns 400,
clients that route on status code apply the wrong recovery strategy.

---

## 7. Form Validation Layer — Edge Case Tests

### What We Follow
Combined multi-field failures must produce the exact expected number of violations.
Validation sequence order must be verified (NotNull fires before Length — not both).

### How To Implement

```java
// CORRECT -- Form validation edge case tests
class ResourceFormValidationEdgeCaseTest {

    private Validator validator;

    @BeforeEach
    void setUp() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    private Set<ConstraintViolation<ResourceForm>> validate(ResourceForm form) {
        return validator.validate(form, ValidationSequence.class);
    }

    // E97: Both fields null → exactly 2 violations (one per field)
    @Test
    @DisplayName("should produce exactly 2 violations when both name and path are null")
    void shouldProduceTwoViolationsWhenBothFieldsAreNull() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm(null, null));
        assertThat(violations).hasSize(2);
    }

    // E98: Both fields empty → at least 2 violations
    @Test
    @DisplayName("should produce at least 2 violations when both name and path are empty")
    void shouldProduceAtLeastTwoViolationsWhenBothFieldsAreEmpty() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("", ""));
        assertThat(violations.size()).isGreaterThanOrEqualTo(2);
    }

    // E99: Both fields blank → at least 2 violations
    @Test
    @DisplayName("should produce at least 2 violations when both fields are blank")
    void shouldProduceAtLeastTwoViolationsWhenBothFieldsAreBlank() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("   ", "   "));
        assertThat(violations.size()).isGreaterThanOrEqualTo(2);
    }

    // E100: Both fields too long → exactly 2 @Length violations
    @Test
    @DisplayName("should produce exactly 2 Length violations when both fields exceed max length")
    void shouldProduceTwoLengthViolationsWhenBothFieldsExceedMaxLength() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("A".repeat(51), "P".repeat(51)));
        assertThat(violations).hasSize(2);
        assertThat(violations).allSatisfy(v ->
            assertThat(v.getConstraintDescriptor().getAnnotation()).isInstanceOf(Length.class));
    }

    // E101: Validation sequence — @NotNull fires BEFORE @Length (not both at once)
    @Test
    @DisplayName("should produce only NotNull violation (not Length) when name is null")
    void shouldProduceOnlyNotNullViolationNotLengthWhenNameIsNull() {
        // null name should NOT produce a @Length violation (sequence stops at @NotNull)
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm(null, "/path"));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(NotNull.class);
    }

    // E-extra: Tab characters in name trigger @NotBlank
    @Test
    @DisplayName("should have NotBlank violation when name consists of tab characters only")
    void shouldHaveNotBlankViolationWhenNameIsOnlyTabs() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("\t\t\t", "/path"));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(NotBlank.class);
    }
}
```

### Why This Matters
- **Violation count on null-both:** If a `@GroupSequence` is misconfigured, both
  fields may only produce one violation even when both are null. Asserting size=2 catches
  a broken group sequence before it reaches production.
- **Sequence order test (E101):** If sequence is broken, the user sees both
  "name is required" AND "name is too long" at the same time for a null input, which
  is nonsensical. This single test verifies the sequence works correctly.

---

## 8. Event Publisher Layer — Edge Case Tests

### What We Follow
All three event types must have structurally distinct payloads. A test that verifies
distinctness catches copy-paste errors where the DELETE publisher accidentally sends an
UPDATE event type.

### How To Implement

```java
// CORRECT -- Event publisher edge case tests
@ExtendWith(MockitoExtension.class)
class CacheEventPublisherEdgeCaseTest {

    @Mock private RedisTemplate<String, CacheInvalidationEvent> redisTemplate;
    @InjectMocks private CacheEventPublisher publisher;

    private final List<CacheInvalidationEvent> capturedEvents = new ArrayList<>();

    @BeforeEach
    void setUp() {
        doAnswer(inv -> {
            capturedEvents.add((CacheInvalidationEvent) inv.getArgument(1));
            return null;
        }).when(redisTemplate).convertAndSend(anyString(), any());
    }

    // E107: CREATE, UPDATE, DELETE events have distinct event types
    @Test
    @DisplayName("should publish distinct event types for CREATE, UPDATE, and DELETE operations")
    void shouldPublishDistinctEventTypesForAllOperations() {
        publisher.publishCreate(null);
        publisher.publishUpdate(1L);
        publisher.publishDelete(1L);

        assertThat(capturedEvents).hasSize(3);
        Set<EventType> eventTypes = capturedEvents.stream()
            .map(CacheInvalidationEvent::getEventType)
            .collect(Collectors.toSet());
        assertThat(eventTypes).containsExactlyInAnyOrder(
            EventType.CREATE, EventType.UPDATE, EventType.DELETE);
    }
}
```

### Why This Matters
Copy-paste errors when implementing three event methods in the same class are extremely
common. This test catches the case where `publishDelete` calls `buildEvent(UPDATE, id)`
instead of `buildEvent(DELETE, id)`.

---

## 9. Security Layer — Edge Case Tests (SEC7–SEC8)

### What We Follow
Edge cases in security: oversized request bodies and missing Content-Type headers.

### How To Implement

```java
// SEC7: Oversized request body returns 413 or 400, not 500
@Test
@DisplayName("should return 413 or 400 when request body exceeds size limit")
void shouldReturn413Or400WhenBodyExceedsSizeLimit() {
    String hugeBody = "{\"name\": \"" + "A".repeat(10_000_000) + "\", \"path\": \"/test\"}";
    MvcResult result = mockMvc.perform(post("/api/v1/resources")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content(hugeBody))
        .andReturn();

    int status = result.getResponse().getStatus();
    assertThat(status).isIn(400, 413, 422);
    assertThat(status).isNotEqualTo(500);
}

// SEC8: Missing Content-Type header returns 415 or 400
@Test
@DisplayName("should return 415 or 400 when Content-Type header is missing on POST")
void shouldReturn415Or400WhenContentTypeMissing() {
    mockMvc.perform(post("/api/v1/resources")
            .header("Authorization", "Bearer " + validJwtToken)
            .content("{\"name\": \"Test\", \"path\": \"/test\"}"))
        .andExpect(status().isIn(400, 415));
}
```

### Why This Matters
An oversized body without a size limit causes OutOfMemoryError on the JVM, crashing the
entire application. Missing Content-Type without handling causes a 500 instead of 415.

---

## 10. Path Parameters — Edge Case Tests (PP2–PP4)

### What We Follow
Boundary path parameter values: negative IDs, zero, and integer overflow.

### How To Implement

```java
// PP2: Negative ID returns 400 or 404
@Test
@DisplayName("should return 400 or 404 when path parameter is negative integer")
void shouldReturn400Or404WhenPathParamIsNegative() {
    MvcResult result = mockMvc.perform(get("/api/v1/resources/-1")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andReturn();
    assertThat(result.getResponse().getStatus()).isIn(400, 404);
}

// PP3: Zero ID returns 400 or 404
@Test
@DisplayName("should return 400 or 404 when path parameter is zero")
void shouldReturn400Or404WhenPathParamIsZero() {
    MvcResult result = mockMvc.perform(get("/api/v1/resources/0")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andReturn();
    assertThat(result.getResponse().getStatus()).isIn(400, 404);
}

// PP4: Overflow integer ID returns 400
@Test
@DisplayName("should return 400 when path parameter exceeds Long.MAX_VALUE")
void shouldReturn400WhenPathParamExceedsLongMaxValue() {
    mockMvc.perform(get("/api/v1/resources/99999999999999999999")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isBadRequest());
}
```

### Why This Matters
Spring MVC parses path params as Long. Values beyond Long.MAX_VALUE cause
`NumberFormatException` which must be caught by the global handler and returned as 400.

---

## 11. Error Structure — Edge Case Tests (ERR3)

### What We Follow
Even 500 errors must return JSON, not HTML. Clients parsing JSON will crash on an HTML response.

### How To Implement

```java
// ERR3: Error response Content-Type is application/json even for 500
@Test
@DisplayName("should return application/json Content-Type even on 500 error")
void shouldReturnJsonContentTypeOn500Error() {
    when(resourceService.getById(anyLong())).thenThrow(new RuntimeException("crash"));

    mockMvc.perform(get("/api/v1/resources/1")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isInternalServerError())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON));
}
```

### Why This Matters
Spring Boot's Whitelabel error page returns `text/html` by default. If the global
exception handler is missing or misconfigured, clients receive `<html>Whitelabel Error...`
instead of `{"success":false,...}`. This breaks every JSON-parsing client.

---

**ENFORCEMENT:** Edge case tests are mandatory for any service method that:
1. Accepts a `String` field that has a `@Length` constraint
2. Has a `findById` → Optional → throw pattern
3. Calls `deleteById` (must have idempotent test)
4. Publishes an event (must have event-type-distinctness test)
5. Has an `existsByXxxIgnoreCase` duplicate check (must have case-variant test)

PRs introducing any of the above patterns without corresponding edge case tests will
fail code review regardless of coverage metric results.

**SEE ALSO:**
- 35-positive-testing-standards.md -- happy-path tests for every layer
- 36-negative-testing-standards.md -- error-path tests for every layer
- 16-validation-sequence-pattern.md -- @GroupSequence configuration for ordered validation
- 38-test-mocking-strategy.md -- argThat() patterns for complex assertion
