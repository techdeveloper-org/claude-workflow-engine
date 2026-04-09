---
description: "Level 2.3 - Negative (error-path) test scenarios for every Spring Boot layer including security/path-params/error-structure"
paths:
  - "src/test/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Negative Testing Standards (Level 2.3 - Spring Boot)

**PURPOSE:** Define the mandatory error-path test scenarios for every Spring Boot REST
microservice layer. A negative test verifies that the system fails correctly — throwing
the right exception, returning the right HTTP status, and never leaking internal details
when given invalid inputs or violating business constraints.

**APPLIES WHEN:** Any Spring Boot REST microservice with Controller → Service → Repository layers.

---

## 1. Bootstrap Layer — Negative Tests

### What We Follow
The bootstrap layer negative tests verify that `main()` does not throw on invalid
argument inputs — null and empty are both valid JVM argument states.

### How To Implement

```java
// CORRECT -- Bootstrap negative tests
@ExtendWith(MockitoExtension.class)
class ApplicationBootstrapNegativeTest {

    // N9: main() with null args does not throw
    @Test
    @DisplayName("should not throw when main() is called with null args")
    void shouldNotThrowWhenMainCalledWithNullArgs() {
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            mocked.when(() -> SpringApplication.run(any(Class.class), any()))
                  .thenReturn(null);

            assertThatNoException().isThrownBy(() -> MyServiceApplication.main(null));
        }
    }

    // N10: main() with empty args does not throw, run() still invoked
    @Test
    @DisplayName("should not throw and should still invoke SpringApplication.run() with empty args")
    void shouldNotThrowAndInvokeRunWithEmptyArgs() {
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            mocked.when(() -> SpringApplication.run(any(Class.class), any()))
                  .thenReturn(null);

            assertThatNoException().isThrownBy(() -> MyServiceApplication.main(new String[]{}));
            mocked.verify(() -> SpringApplication.run(
                eq(MyServiceApplication.class), any(String[].class)), times(1));
        }
    }
}
```

### Why This Matters
Kubernetes liveness/readiness probes, test containers, and integration test harnesses
frequently launch the main class with null or empty args. A crash here prevents the
container from starting.

---

## 2. Configuration Layer — Negative Tests

### What We Follow
Constants must never return null. This confirms that static initializers ran correctly
and that no constant field was accidentally set to null.

### How To Implement

```java
// CORRECT -- Config negative tests
class CacheConfigNegativeTest {

    // N16: No constant returns null
    @Test
    @DisplayName("should not have any null constant values in CacheConfig")
    void shouldNotHaveNullConstantValues() {
        assertThat(CacheConfig.CACHE_BY_ID).isNotNull();
        assertThat(CacheConfig.CACHE_ALL).isNotNull();
        assertThat(CacheConfig.CACHE_COUNT).isNotNull();
    }
}
```

### Why This Matters
A null cache name silently routes all cache puts/gets to a null-keyed bucket in some
CacheManager implementations, causing all-or-nothing cache behaviour that is extremely
difficult to diagnose in production.

---

## 3. Controller Layer — Negative Tests

### What We Follow
Every error path must propagate the correct domain exception. The controller must not
swallow exceptions — they propagate to the `@ControllerAdvice` handler.

### How To Implement

```java
// CORRECT -- Controller layer negative tests
@ExtendWith(MockitoExtension.class)
class ResourceRestControllerNegativeTest {

    @Mock private ResourceService resourceService;
    @InjectMocks private ResourceRestController controller;

    // N24: POST with duplicate name propagates DuplicateResourceException
    @Test
    @DisplayName("should propagate DuplicateResourceException when name is a duplicate")
    void shouldPropagateDuplicateResourceExceptionWhenNameIsDuplicate() {
        ResourceForm form = new ResourceForm("ExistingName", "/new-path");
        when(resourceService.add(any()))
            .thenThrow(new DuplicateResourceException("Resource already exists."));

        assertThatThrownBy(() -> controller.create(form))
            .isInstanceOf(DuplicateResourceException.class)
            .hasMessageContaining("already exists");
    }

    // N25: POST with duplicate path propagates ResourceConflictException
    @Test
    @DisplayName("should propagate ResourceConflictException when path is a duplicate")
    void shouldPropagateResourceConflictExceptionWhenPathIsDuplicate() {
        ResourceForm form = new ResourceForm("NewName", "/existing-path");
        when(resourceService.add(any()))
            .thenThrow(new ResourceConflictException("Path already exists."));

        assertThatThrownBy(() -> controller.create(form))
            .isInstanceOf(ResourceConflictException.class);
    }

    // N26: GET by non-existent ID propagates ResourceNotFoundException
    @Test
    @DisplayName("should propagate ResourceNotFoundException when resource ID does not exist")
    void shouldPropagateResourceNotFoundExceptionWhenIdDoesNotExist() {
        when(resourceService.getById(999L))
            .thenThrow(new ResourceNotFoundException("Resource not found: 999"));

        assertThatThrownBy(() -> controller.getById(999L))
            .isInstanceOf(ResourceNotFoundException.class)
            .hasMessageContaining("999");
    }

    // N27: PUT on non-existent ID propagates ResourceNotFoundException
    @Test
    @DisplayName("should propagate ResourceNotFoundException when update ID does not exist")
    void shouldPropagateResourceNotFoundExceptionWhenUpdateIdDoesNotExist() {
        when(resourceService.update(eq(999L), any()))
            .thenThrow(new ResourceNotFoundException("Resource not found: 999"));

        assertThatThrownBy(() -> controller.update(999L, new ResourceForm()))
            .isInstanceOf(ResourceNotFoundException.class);
    }

    // Verify service is NOT called again after exception (no retry)
    @Test
    @DisplayName("should invoke service exactly once even when exception is thrown")
    void shouldInvokeServiceExactlyOnceEvenOnException() {
        when(resourceService.getById(999L))
            .thenThrow(new ResourceNotFoundException("not found"));

        assertThatThrownBy(() -> controller.getById(999L));

        verify(resourceService, times(1)).getById(999L);
    }
}
```

### Why This Matters
Controllers that swallow exceptions and return 200 OK hide domain errors from clients.
Verifying that exceptions propagate ensures the `@ControllerAdvice` handler transforms
them into the correct structured error response.

---

## 4. Service Layer — Negative Tests

### What We Follow
Every constraint violation (duplicate, not found) must throw a typed domain exception.
Repository save must never be called when a precondition fails.

### How To Implement

```java
// CORRECT -- Service layer negative tests
@ExtendWith(MockitoExtension.class)
class ResourceServiceImplNegativeTest {

    @Mock private ResourceRepository resourceRepository;
    @Mock private EventPublisher eventPublisher;
    @InjectMocks private ResourceServiceImpl resourceService;

    // N40: Add with duplicate name throws DuplicateResourceException
    @Test
    @DisplayName("should throw DuplicateResourceException when name already exists")
    void shouldThrowDuplicateResourceExceptionWhenNameExists() {
        when(resourceRepository.existsByNameIgnoreCase("Duplicate"))
            .thenReturn(true);

        assertThatThrownBy(() -> resourceService.add(new ResourceForm("Duplicate", "/path")))
            .isInstanceOf(DuplicateResourceException.class);

        verify(resourceRepository, never()).save(any());
    }

    // N41: Add with duplicate path throws ResourceConflictException
    @Test
    @DisplayName("should throw ResourceConflictException when path already exists")
    void shouldThrowResourceConflictExceptionWhenPathExists() {
        when(resourceRepository.existsByNameIgnoreCase("NewName")).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCase("/dup")).thenReturn(true);

        assertThatThrownBy(() -> resourceService.add(new ResourceForm("NewName", "/dup")))
            .isInstanceOf(ResourceConflictException.class);

        verify(resourceRepository, never()).save(any());
    }

    // N42: Get by non-existent ID throws ResourceNotFoundException
    @Test
    @DisplayName("should throw ResourceNotFoundException when resource ID does not exist")
    void shouldThrowResourceNotFoundExceptionWhenIdDoesNotExist() {
        when(resourceRepository.findById(999L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> resourceService.getById(999L))
            .isInstanceOf(ResourceNotFoundException.class);
    }

    // N43: Update non-existent ID throws ResourceNotFoundException
    @Test
    @DisplayName("should throw ResourceNotFoundException when update ID does not exist")
    void shouldThrowResourceNotFoundExceptionWhenUpdateIdDoesNotExist() {
        when(resourceRepository.findById(999L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> resourceService.update(999L, new ResourceForm("Name", "/path")))
            .isInstanceOf(ResourceNotFoundException.class);

        verify(resourceRepository, never()).save(any());
    }

    // N44: Update with duplicate name (excluding self) throws
    @Test
    @DisplayName("should throw DuplicateResourceException when updated name is taken by another resource")
    void shouldThrowDuplicateResourceExceptionWhenNameTakenByAnotherResource() {
        ResourceEntity existing = new ResourceEntity(1L, "OldName", "/old");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("TakenName", 1L)).thenReturn(true);

        assertThatThrownBy(() -> resourceService.update(1L, new ResourceForm("TakenName", "/new")))
            .isInstanceOf(DuplicateResourceException.class);

        verify(resourceRepository, never()).save(any());
    }

    // N45: Update with duplicate path (excluding self) throws
    @Test
    @DisplayName("should throw ResourceConflictException when updated path is taken by another resource")
    void shouldThrowResourceConflictExceptionWhenPathTakenByAnotherResource() {
        ResourceEntity existing = new ResourceEntity(1L, "Name", "/old");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("Name", 1L)).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCaseAndIdNot("/taken", 1L)).thenReturn(true);

        assertThatThrownBy(() -> resourceService.update(1L, new ResourceForm("Name", "/taken")))
            .isInstanceOf(ResourceConflictException.class);

        verify(resourceRepository, never()).save(any());
    }
}
```

### Why This Matters
`verify(repo, never()).save(any())` ensures that failed precondition checks are a true
early-exit, not a failed save that leaks a partial write through JPA dirty-checking.

---

## 5. Entity Layer — Negative Tests

### What We Follow
The entity equality contract must handle null comparisons and type mismatches without
throwing exceptions. Constructors with null parameters must not throw.

### How To Implement

```java
// CORRECT -- Entity negative tests
class ResourceEntityNegativeTest {

    // N62: Different IDs → not equal
    @Test
    @DisplayName("should not be equal when two instances have different IDs")
    void shouldNotBeEqualWhenInstancesHaveDifferentIds() {
        ResourceEntity e1 = new ResourceEntity(1L, "Name", "/path");
        ResourceEntity e2 = new ResourceEntity(2L, "Name", "/path");
        assertThat(e1).isNotEqualTo(e2);
    }

    // N63: Null comparison — returns false, no NPE
    @Test
    @DisplayName("should return false and not throw when compared to null")
    void shouldReturnFalseAndNotThrowWhenComparedToNull() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        assertThat(entity.equals(null)).isFalse();
    }

    // N64: Different type — returns false
    @Test
    @DisplayName("should return false when compared to a different type")
    void shouldReturnFalseWhenComparedToDifferentType() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        assertThat(entity.equals("a string")).isFalse();
        assertThat(entity.equals(1L)).isFalse();
    }

    // N65: Constructor with null name — no NPE
    @Test
    @DisplayName("should not throw when constructor is called with null name")
    void shouldNotThrowWhenConstructorCalledWithNullName() {
        assertThatNoException().isThrownBy(() -> new ResourceEntity(1L, null, "/path"));
    }

    // N66: Constructor with null path — no NPE
    @Test
    @DisplayName("should not throw when constructor is called with null path")
    void shouldNotThrowWhenConstructorCalledWithNullPath() {
        assertThatNoException().isThrownBy(() -> new ResourceEntity(1L, "Name", null));
    }
}
```

### Why This Matters
Java collections (HashMap, HashSet) call `equals(null)` internally during lookups.
An NPE in `equals()` crashes any code that puts entities into a collection and then
searches for them.

---

## 6. Exception Handler Layer — Negative Tests

### What We Follow
Every handler must return `success = false`. This is a consistency contract — clients
that check this flag must be able to rely on it being false for every exception type.

### How To Implement

```java
// CORRECT -- Exception handler negative tests
@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerNegativeTest {

    @InjectMocks private GlobalExceptionHandler handler;

    // N78: DuplicateNameException response has success=false
    @Test
    @DisplayName("should return success=false in response body for DuplicateNameException")
    void shouldReturnSuccessFalseForDuplicateNameException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicateName(new DuplicateResourceException("exists"));
        assertThat(response.getBody().isSuccess()).isFalse();
    }

    // N79: DuplicatePathException response has success=false
    @Test
    @DisplayName("should return success=false in response body for DuplicatePathException")
    void shouldReturnSuccessFalseForDuplicatePathException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicatePath(new ResourceConflictException("path exists"));
        assertThat(response.getBody().isSuccess()).isFalse();
    }

    // Additional: ResourceNotFoundException → 404 with success=false
    @Test
    @DisplayName("should return 404 NOT FOUND with success=false for ResourceNotFoundException")
    void shouldReturn404ForResourceNotFoundException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleNotFound(new ResourceNotFoundException("not found"));
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody().isSuccess()).isFalse();
    }
}
```

### Why This Matters
A handler that accidentally returns `success=true` inside an error response body will
cause clients to process error responses as success, leading to data corruption in
downstream systems that trust the `success` flag without inspecting the HTTP status.

---

## 7. Form Validation Layer — Negative Tests

### What We Follow
Every constraint annotation must be individually exercised with the minimum input that
triggers it. Validation sequence order must be verified (only one violation at a time
when values are null/empty/blank).

### How To Implement

```java
// CORRECT -- Form validation negative tests
class ResourceFormValidationNegativeTest {

    private Validator validator;

    @BeforeEach
    void setUp() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    private Set<ConstraintViolation<ResourceForm>> validate(ResourceForm form) {
        return validator.validate(form, ValidationSequence.class);
    }

    // N88: Null name → @NotNull violation on name field
    @Test
    @DisplayName("should have NotNull violation on name when name is null")
    void shouldHaveNotNullViolationWhenNameIsNull() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm(null, "/path"));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getPropertyPath().toString()).isEqualTo("name");
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(NotNull.class);
    }

    // N89: Empty name → @NotEmpty violation
    @Test
    @DisplayName("should have NotEmpty violation on name when name is empty string")
    void shouldHaveNotEmptyViolationWhenNameIsEmpty() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("", "/path"));
        assertThat(violations).hasSize(1);
        ConstraintViolation<?> v = violations.iterator().next();
        assertThat(v.getPropertyPath().toString()).isEqualTo("name");
        assertThat(v.getConstraintDescriptor().getAnnotation()).isInstanceOf(NotEmpty.class);
    }

    // N90: Blank name (spaces only) → @NotBlank violation
    @Test
    @DisplayName("should have NotBlank violation on name when name is whitespace only")
    void shouldHaveNotBlankViolationWhenNameIsBlank() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("   ", "/path"));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(NotBlank.class);
    }

    // N91: Name > 50 chars (51) → @Length violation
    @Test
    @DisplayName("should have Length violation on name when name exceeds 50 characters")
    void shouldHaveLengthViolationWhenNameExceeds50Characters() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("A".repeat(51), "/path"));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(Length.class);
    }

    // N92: Name > 50 chars (100) → @Length violation
    @Test
    @DisplayName("should have Length violation on name when name is 100 characters")
    void shouldHaveLengthViolationWhenNameIs100Characters() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("A".repeat(100), "/path"));
        assertThat(violations).hasSize(1);
    }

    // N93: Null path → @NotNull violation on path field
    @Test
    @DisplayName("should have NotNull violation on path when path is null")
    void shouldHaveNotNullViolationWhenPathIsNull() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("Name", null));
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getPropertyPath().toString()).isEqualTo("path");
    }

    // N94: Empty path → @NotEmpty violation
    @Test
    @DisplayName("should have NotEmpty violation on path when path is empty")
    void shouldHaveNotEmptyViolationWhenPathIsEmpty() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("Name", ""));
        assertThat(violations).hasSize(1);
    }

    // N95: Blank path (tabs) → @NotBlank violation
    @Test
    @DisplayName("should have NotBlank violation on path when path contains only tabs")
    void shouldHaveNotBlankViolationWhenPathContainsOnlyTabs() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("Name", "\t\t\t"));
        assertThat(violations).hasSize(1);
    }

    // N96: Path > 50 chars → @Length violation
    @Test
    @DisplayName("should have Length violation on path when path exceeds 50 characters")
    void shouldHaveLengthViolationWhenPathExceeds50Characters() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validate(new ResourceForm("Name", "/p".repeat(26))); // 52 chars
        assertThat(violations).hasSize(1);
    }
}
```

### Why This Matters
Validation constraint tests document the exact boundary where inputs become invalid.
Without them, a developer who accidentally changes `@Length(max = 50)` to `@Length(max = 500)`
has no test failure to catch the regression.

---

## 8. Event Publisher Layer — Negative Tests

### What We Follow
Event publishing must succeed even for edge-case entity IDs. The publisher must not
silently swallow a failed `convertAndSend` call.

### How To Implement

```java
// CORRECT -- Event publisher negative tests
@ExtendWith(MockitoExtension.class)
class CacheEventPublisherNegativeTest {

    @Mock private RedisTemplate<String, CacheInvalidationEvent> redisTemplate;
    @InjectMocks private CacheEventPublisher publisher;

    // N106: UPDATE with non-existent ID still publishes the event
    @Test
    @DisplayName("should still publish UPDATE event when entity ID does not exist in database")
    void shouldStillPublishUpdateEventWhenEntityIdDoesNotExistInDatabase() {
        doNothing().when(redisTemplate).convertAndSend(anyString(), any());

        publisher.publishUpdate(999L);

        verify(redisTemplate, times(1)).convertAndSend(anyString(), argThat(event ->
            event.getEventType() == EventType.UPDATE && event.getEntityId().equals(999L)));
    }
}
```

### Why This Matters
The event publisher does not (and should not) validate whether the entity ID exists in
the database. That is the caller's responsibility. Testing that it still publishes for
unknown IDs ensures the publisher is a pure fire-and-forget transport layer.

---

---

## 9. Security Layer — Negative Tests (SEC3–SEC6)

### What We Follow
Every protected endpoint must reject unauthenticated requests (401), invalid tokens (401),
and malicious input payloads (400/422). The error response must never leak internal details.

### How To Implement

```java
// CORRECT -- Security negative tests
@ExtendWith(MockitoExtension.class)
class SecurityNegativeTest {

    // SEC3: Unauthenticated request returns 401
    @Test
    @DisplayName("should return 401 Unauthorized when no Authorization header is present")
    void shouldReturn401WhenNoAuthorizationHeader() {
        mockMvc.perform(get("/api/v1/resources/1")
                .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.success").value(false))
            .andExpect(jsonPath("$.message").isNotEmpty());
    }

    // SEC4: Expired/invalid token returns 401, not 403 or 500
    @Test
    @DisplayName("should return 401 when Authorization header has invalid/expired JWT")
    void shouldReturn401WhenTokenIsInvalid() {
        mockMvc.perform(get("/api/v1/resources/1")
                .header("Authorization", "Bearer invalid.jwt.token")
                .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.success").value(false))
            .andExpect(jsonPath("$.message").doesNotContain("StackTrace"))
            .andExpect(jsonPath("$.message").doesNotContain("io.jsonwebtoken"));
    }

    // SEC5: SQL injection in name field returns 400, not 500
    @Test
    @DisplayName("should return 400 when name field contains SQL injection payload")
    void shouldReturn400WhenNameContainsSqlInjection() {
        String sqlInjection = "'; DROP TABLE resources; --";
        mockMvc.perform(post("/api/v1/resources")
                .header("Authorization", "Bearer " + validJwtToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\": \"" + sqlInjection + "\", \"path\": \"/safe\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.success").value(false));

        // Service must NOT be invoked -- validation rejects before business logic
        verify(resourceService, never()).add(any());
    }

    // SEC6: XSS payload in name field is handled safely
    @Test
    @DisplayName("should handle XSS payload safely -- store verbatim or reject, never execute")
    void shouldHandleXssPayloadSafely() {
        String xssPayload = "<script>alert('xss')</script>";
        MvcResult result = mockMvc.perform(post("/api/v1/resources")
                .header("Authorization", "Bearer " + validJwtToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\": \"" + xssPayload + "\", \"path\": \"/safe\"}"))
            .andReturn();

        int status = result.getResponse().getStatus();
        // Either stored verbatim (201) or rejected (400/422) -- never 500
        assertThat(status).isIn(201, 400, 422);
    }
}
```

### Why This Matters
A 500 response to SQL injection leaks database schema information. An invalid JWT that
returns 200 instead of 401 means the auth filter is disabled or misconfigured.

---

## 10. Path Parameters — Negative Tests (PP1)

### What We Follow
Non-numeric path parameters must be rejected at the framework level before reaching
the service layer.

### How To Implement

```java
// PP1: Non-numeric ID in path returns 400
@Test
@DisplayName("should return 400 when path parameter is non-numeric string")
void shouldReturn400WhenPathParamIsNonNumeric() {
    mockMvc.perform(get("/api/v1/resources/abc")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isBadRequest());
}
```

### Why This Matters
Spring MVC auto-converts path params to Long. A non-numeric value causes a
`MethodArgumentTypeMismatchException` which the global handler must convert to 400.

---

## 11. Error Structure — Negative Tests (ERR1–ERR2)

### What We Follow
Unhandled exceptions must produce a structured `ApiResponse` envelope, not a naked
stack trace or Spring Boot's default Whitelabel error page.

### How To Implement

```java
// ERR1: Unhandled exception returns ApiResponse envelope with success=false
@Test
@DisplayName("should return 500 with ApiResponse envelope when unhandled exception occurs")
void shouldReturn500WithApiResponseEnvelopeOnUnhandledException() {
    when(resourceService.getById(anyLong())).thenThrow(new RuntimeException("unexpected"));

    mockMvc.perform(get("/api/v1/resources/1")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.success").value(false))
        .andExpect(jsonPath("$.message").isNotEmpty());
}

// ERR2: 500 error response does not leak stack trace or class names
@Test
@DisplayName("should not leak stack trace or internal class names in 500 response")
void shouldNotLeakStackTraceIn500Response() {
    when(resourceService.getById(anyLong())).thenThrow(new RuntimeException("db pool exhausted"));

    MvcResult result = mockMvc.perform(get("/api/v1/resources/1")
            .header("Authorization", "Bearer " + validJwtToken)
            .contentType(MediaType.APPLICATION_JSON))
        .andReturn();

    String body = result.getResponse().getContentAsString();
    assertThat(body).doesNotContain("RuntimeException");
    assertThat(body).doesNotContain("at com.");
    assertThat(body).doesNotContain(".java:");
}
```

### Why This Matters
Spring Boot's default error handler returns `{"timestamp":...,"status":500,"error":"Internal Server Error","path":"/api/..."}`
which does not match the `ApiResponse` envelope. Clients parsing `response.success` crash on this format.

---

**ENFORCEMENT:** Every exception type in the service and handler layers must have a
corresponding negative test before merge. PRs that add a new `@ExceptionHandler` method
without a negative test covering `success=false` and the correct HTTP status will fail
the coverage gate.

**SEE ALSO:**
- 19-exception-handling-hierarchy.md -- exception class hierarchy and HTTP status mapping
- 35-positive-testing-standards.md -- happy-path tests for every layer
- 37-edge-case-testing-standards.md -- boundary and combined-failure tests
- 38-test-mocking-strategy.md -- isolation strategies and verify() patterns
