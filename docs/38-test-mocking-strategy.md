---
description: "Level 2.3 - Per-layer test isolation strategies, MockedStatic, verify() and argThat() patterns"
paths:
  - "src/test/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Test Mocking Strategy (Level 2.3 - Spring Boot)

**PURPOSE:** Define the correct isolation strategy for each application layer in a Spring Boot
microservice. Choosing the wrong isolation strategy (e.g., using @SpringBootTest for a unit
test) adds seconds of startup time per test, increases flakiness, and hides which component
actually broke. Using the right strategy makes each test atomic, fast, and pinpointed.

**APPLIES WHEN:** Any Spring Boot REST microservice with JUnit 5 and Mockito.

---

## Mocking Strategy Quick Reference

| Layer | Strategy | Key Annotation / Mechanism | Startup Time | Why This Layer |
|-------|----------|---------------------------|-------------|----------------|
| Bootstrap | `MockedStatic<SpringApplication>` | `@ExtendWith(MockitoExtension.class)` | < 1ms | Prevents real Spring context startup |
| Configuration | None (reflection only) | Plain `new ConfigClass()` | < 1ms | Constants require no dependencies |
| Controller | `@Mock Service`, `@InjectMocks Controller` | `@ExtendWith(MockitoExtension.class)` | < 1ms | Tests HTTP contract without MVC wiring |
| Service | `@Mock Repository`, `@Mock EventPublisher` | `@ExtendWith(MockitoExtension.class)` | < 1ms | Isolates business logic from DB |
| Entity | None | Direct instantiation via `new` | < 1ms | POJO — no external dependencies |
| Exception Handler | `@InjectMocks Handler` (no mocks) | `@ExtendWith(MockitoExtension.class)` | < 1ms | Pure transformation logic |
| Form Validation | `Validation.buildDefaultValidatorFactory()` | JUnit 5, no Mockito | < 5ms | Invokes Hibernate Validator directly |
| Event Publisher | `@Mock RedisTemplate`, `@InjectMocks Publisher` | `@ExtendWith(MockitoExtension.class)` | < 1ms | Verifies event payload without Redis |

---

## 1. Bootstrap Layer — MockedStatic Pattern

### What We Follow
Use `MockedStatic<SpringApplication>` in a try-with-resources block to intercept the
static call to `SpringApplication.run()` without starting a Spring context.

### How To Implement

```java
// CORRECT -- MockedStatic for bootstrap test
@ExtendWith(MockitoExtension.class)
class ApplicationMainMethodTest {

    @Test
    @DisplayName("should invoke SpringApplication.run() exactly once")
    void shouldInvokeSpringApplicationRunExactlyOnce() {
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            // Configure the mock BEFORE calling main()
            mocked.when(() -> SpringApplication.run(
                any(Class.class), any(String[].class))).thenReturn(null);

            MyServiceApplication.main(new String[]{});

            // Verify the call happened with the correct class argument
            mocked.verify(() -> SpringApplication.run(
                eq(MyServiceApplication.class), any(String[].class)), times(1));
        }
        // MockedStatic is automatically closed; SpringApplication.run() is un-mocked
    }

    @Test
    @DisplayName("should capture and verify args forwarded to SpringApplication.run()")
    void shouldCaptureArgsForwardedToSpringApplicationRun() {
        String[] args = {"--spring.profiles.active=test"};
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            ArgumentCaptor<String[]> captor = ArgumentCaptor.forClass(String[].class);
            mocked.when(() -> SpringApplication.run(any(Class.class), captor.capture()))
                  .thenReturn(null);

            MyServiceApplication.main(args);

            assertThat(captor.getValue()).containsExactly("--spring.profiles.active=test");
        }
    }
}

// WRONG -- loads Spring context just to test annotation presence
@SpringBootTest
class ApplicationAnnotationTest {
    @Test
    void testAnnotation() {
        // This starts the full Spring context (3-10s) just to check annotations
    }
}
```

### Why This Matters
`@SpringBootTest` loads the full application context — every bean, every datasource
connection, every cache. Using `MockedStatic` replaces that 3-10 second startup with a
< 1ms reflection call.

---

## 2. Controller Layer — @Mock Service + @InjectMocks Controller

### What We Follow
Mock the service interface. Inject the mock into the controller via `@InjectMocks`.
Call controller methods directly — no `MockMvc`, no `@WebMvcTest`.

### How To Implement

```java
// CORRECT -- Pure Mockito controller test
@ExtendWith(MockitoExtension.class)
class ResourceControllerTest {

    @Mock
    private ResourceService resourceService; // mock the interface, not the impl

    @InjectMocks
    private ResourceRestController controller; // inject mock into controller

    @Test
    @DisplayName("should return 201 and invoke service.add() exactly once")
    void shouldReturn201AndInvokeServiceAddExactlyOnce() {
        ResourceForm form = new ResourceForm("Name", "/path");
        ApiResponse<ResourceDto> serviceResult = ApiResponse.created(new ResourceDto(1L, "Name", "/path"));
        when(resourceService.add(any(ResourceForm.class))).thenReturn(serviceResult);

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.create(form);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        verify(resourceService, times(1)).add(any(ResourceForm.class));
    }

    @Test
    @DisplayName("should propagate service exception without wrapping it")
    void shouldPropagateServiceExceptionWithoutWrapping() {
        when(resourceService.getById(999L))
            .thenThrow(new ResourceNotFoundException("not found: 999"));

        assertThatThrownBy(() -> controller.getById(999L))
            .isInstanceOf(ResourceNotFoundException.class)
            .hasMessageContaining("999");
    }
}

// WRONG -- @WebMvcTest loads Spring MVC, security filters, etc.
@WebMvcTest(ResourceRestController.class)
class ResourceControllerWebMvcTest {
    @Autowired private MockMvc mockMvc;
    // Web MVC layer adds: security config, message converters, exception resolver
    // These hide what the controller method itself does
}
```

### Why This Matters
`@WebMvcTest` adds Spring Security filters, Jackson deserialization, HTTP connection
handling, and exception resolvers. When a test fails you do not know if the controller
logic failed or if the framework layer introduced a transformation.

---

## 3. Service Layer — @Mock Repository + @Mock EventPublisher

### What We Follow
Mock the repository interface and any event publishers. Inject both into the service
implementation. Use `verify()` to confirm repository delegation and `argThat()` to
validate complex objects (Sort, events).

### How To Implement

```java
// CORRECT -- Service isolation with @Mock repository
@ExtendWith(MockitoExtension.class)
class ResourceServiceImplTest {

    @Mock
    private ResourceRepository resourceRepository;

    @Mock
    private EventPublisher eventPublisher;

    @InjectMocks
    private ResourceServiceImpl resourceService;

    @Test
    @DisplayName("should call repository with Sort.by(ASC, id)")
    void shouldCallRepositoryWithSortByIdAsc() {
        when(resourceRepository.findAll(any(Sort.class))).thenReturn(Collections.emptyList());

        resourceService.getAll();

        // argThat validates the EXACT Sort object — not just any(Sort.class)
        verify(resourceRepository).findAll(
            argThat(sort -> sort.equals(Sort.by(Sort.Direction.ASC, "id"))));
    }

    @Test
    @DisplayName("should publish DELETE event with correct type and entityId")
    void shouldPublishDeleteEventWithCorrectTypeAndEntityId() {
        doNothing().when(resourceRepository).deleteById(1L);

        resourceService.delete(1L);

        // argThat validates both fields of the published event
        verify(eventPublisher, times(1)).publish(argThat(event ->
            event.getEventType() == EventType.DELETE &&
            event.getEntityId().equals(1L)));
    }

    @Test
    @DisplayName("should never call save() when duplicate name check fails")
    void shouldNeverCallSaveWhenDuplicateNameCheckFails() {
        when(resourceRepository.existsByNameIgnoreCase("dup")).thenReturn(true);

        assertThatThrownBy(() -> resourceService.add(new ResourceForm("dup", "/path")));

        verify(resourceRepository, never()).save(any());
    }
}
```

### Common verify() Patterns

```java
// Verify called exactly once
verify(repo, times(1)).save(any(ResourceEntity.class));

// Verify never called (precondition failed before reaching save)
verify(repo, never()).save(any());

// Verify called with exact argument value
verify(repo, times(1)).deleteById(eq(1L));

// Verify called with complex argument condition
verify(repo).findAll(argThat(sort ->
    sort.equals(Sort.by(Sort.Direction.ASC, "id"))));

// Verify event published with matching fields
verify(publisher).publish(argThat(event ->
    event.getEventType() == EventType.CREATE &&
    event.getEntityId() == null));
```

### Why This Matters
Mocking the `@DataJpaTest` layer (H2 + JPA) runs the query planner on H2 which has
different SQL semantics than PostgreSQL. Pure Mockito bypasses the query planner entirely
and tests only the service logic that belongs to Java, not to SQL.

---

## 4. Entity Layer — No Mocks (Direct Instantiation)

### What We Follow
Instantiate entities directly with constructors and setters. Use reflection only for
contract validation (Serializable, serialVersionUID). No Mockito needed.

### How To Implement

```java
// CORRECT -- Direct instantiation, no mocks
class ResourceEntityTest {

    @Test
    @DisplayName("should satisfy equals contract: reflexive, symmetric, null-safe")
    void shouldSatisfyEqualsContract() {
        ResourceEntity e1 = new ResourceEntity(1L, "Name", "/path");
        ResourceEntity e2 = new ResourceEntity(1L, "Name", "/path");

        assertThat(e1).isEqualTo(e1);           // reflexive
        assertThat(e1).isEqualTo(e2);           // symmetric
        assertThat(e2).isEqualTo(e1);           // symmetric reverse
        assertThat(e1.equals(null)).isFalse();  // null-safe
        assertThat(e1.equals("string")).isFalse(); // type-safe
    }

    @Test
    @DisplayName("should be serializable with serialVersionUID")
    void shouldBeSerializableWithSerialVersionUid() throws NoSuchFieldException {
        assertThat(ResourceEntity.class).isAssignableTo(Serializable.class);
        ResourceEntity.class.getDeclaredField("serialVersionUID"); // throws if missing
    }
}

// WRONG -- creating a @Mock of an entity
@Mock ResourceEntity mockEntity; // never mock entities — they are data objects
// Mocked entities return null for all unstubbed fields, producing misleading test results
```

### Why This Matters
A mocked entity returns null for every getter unless explicitly stubbed. This masks bugs
where the entity constructor fails to set a field — the test passes because the mock was
set up to return a non-null value, hiding the real implementation gap.

---

## 5. Exception Handler Layer — @InjectMocks Only (No Mocks)

### What We Follow
`@InjectMocks` the handler class. Pass exception instances directly to handler methods.
No mocks required — handlers contain pure data transformation logic.

### How To Implement

```java
// CORRECT -- Exception handler with no mocks
@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerTest {

    @InjectMocks
    private GlobalExceptionHandler handler;

    @Test
    @DisplayName("should map DuplicateResourceException to 409 CONFLICT response")
    void shouldMapDuplicateResourceExceptionTo409Conflict() {
        DuplicateResourceException ex = new DuplicateResourceException("already exists");

        ResponseEntity<ApiResponse<Void>> response = handler.handleDuplicate(ex);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody().isSuccess()).isFalse();
        assertThat(response.getBody().getMessage()).isNotBlank();
        assertThat(response.getStatusCodeValue()).isEqualTo(response.getBody().getStatus());
    }
}
```

### Why This Matters
Exception handlers are deterministic: given an exception, they always produce the same
response. There is no dependency injection, no I/O, no external state. Adding mocks
introduces setup overhead and obscures the actual logic being tested.

---

## 6. Form Validation Layer — Hibernate Validator Directly

### What We Follow
Build the validator from the factory. Pass form instances to `validator.validate()`.
Use `ValidationSequence.class` as the group to enforce constraint ordering.

### How To Implement

```java
// CORRECT -- Hibernate Validator invoked directly
class ResourceFormValidationTest {

    private Validator validator;

    @BeforeEach
    void setUp() {
        // Build the validator WITHOUT Spring — same behaviour, no Spring context
        ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @Test
    @DisplayName("should produce NotNull violation first when name is null (sequence order)")
    void shouldProduceNotNullViolationFirstWhenNameIsNull() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm(null, "/path"), ValidationSequence.class);

        // Sequence stops at first failing group — only 1 violation expected
        assertThat(violations).hasSize(1);
        assertThat(violations.iterator().next().getConstraintDescriptor().getAnnotation())
            .isInstanceOf(NotNull.class);
    }

    @Test
    @DisplayName("should produce Length violation for name exceeding 50 characters")
    void shouldProduceLengthViolationForNameExceeding50Characters() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("A".repeat(51), "/path"),
                               ValidationSequence.class);
        assertThat(violations).hasSize(1);
        ConstraintViolation<ResourceForm> violation = violations.iterator().next();
        assertThat(violation.getPropertyPath().toString()).isEqualTo("name");
    }
}

// WRONG -- uses @SpringBootTest to test a bean validation form
@SpringBootTest
class ResourceFormValidationIntegrationTest {
    // Starts entire Spring context just to call validator.validate() — 5-10 second overhead
}
```

### Why This Matters
`Validation.buildDefaultValidatorFactory()` creates the exact same validator that Spring
injects at runtime (Spring delegates to Hibernate Validator internally). Using it directly
provides identical validation behaviour without Spring overhead.

---

## 7. Event Publisher Layer — @Mock RedisTemplate + argThat Payload Validation

### What We Follow
Mock `RedisTemplate`. Use `argThat()` — not `any()` — to validate the published event
object's fields. Never use `any()` for event validation; it hides incorrect event types
and wrong entity IDs.

### How To Implement

```java
// CORRECT -- argThat validates event payload fields
@ExtendWith(MockitoExtension.class)
class CacheEventPublisherTest {

    @Mock
    private RedisTemplate<String, CacheInvalidationEvent> redisTemplate;

    @InjectMocks
    private CacheEventPublisher publisher;

    @Test
    @DisplayName("should publish UPDATE event with correct type and entityId via argThat")
    void shouldPublishUpdateEventWithCorrectTypeAndEntityId() {
        doNothing().when(redisTemplate).convertAndSend(anyString(), any());

        publisher.publishUpdate(42L);

        verify(redisTemplate).convertAndSend(
            anyString(),
            argThat(event ->
                event.getEventType() == EventType.UPDATE &&
                event.getEntityId().equals(42L) &&
                event.getEntityType().equals(EntityType.RESOURCE)));
    }
}

// WRONG -- any() does not validate the event structure
verify(redisTemplate).convertAndSend(anyString(), any());
// This passes even if the publisher sends a CREATE event when DELETE was expected.
```

### Why This Matters
`any()` accepts every `CacheInvalidationEvent`, including one with the wrong `EventType`
or a null `EntityId`. Using `argThat()` with field-level assertions is the only way to
verify the event's contents without introducing a domain-specific `equals()` in the event class.

---

## 8. Anti-Patterns to Avoid

```java
// ANTI-PATTERN 1: @SpringBootTest for unit-level tests
@SpringBootTest // loads full context = 3-10s startup per test class
class ServiceUnitTest { ... }
// Use: @ExtendWith(MockitoExtension.class)

// ANTI-PATTERN 2: any() for critical argument validation
verify(repo).findAll(any(Sort.class));
// Use: verify(repo).findAll(argThat(s -> s.equals(Sort.by(ASC, "id"))))

// ANTI-PATTERN 3: Mocking entities
@Mock ResourceEntity entity; // mock returns null for all unstubbed getters
// Use: new ResourceEntity(1L, "Name", "/path")

// ANTI-PATTERN 4: @WebMvcTest when testing controller delegation
@WebMvcTest(ResourceController.class) // adds security, message converters, filters
// Use: @Mock Service + @InjectMocks Controller + direct method call

// ANTI-PATTERN 5: Not using try-with-resources for MockedStatic
MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class);
// If the test fails before mocked.close(), the static mock leaks to other tests
// Use: try (MockedStatic<X> mocked = mockStatic(X.class)) { ... }

// ANTI-PATTERN 6: verify() without times() when count matters
verify(repo).save(any()); // allows save() to be called 0 or more times
// Use: verify(repo, times(1)).save(any()) when exactly one save is expected
//      verify(repo, never()).save(any()) when save must NOT be called
```

---

**ENFORCEMENT:** PRs that introduce `@SpringBootTest` for a class that has no external
dependency (no DB, no message broker, no HTTP client) must be refactored to use
`@ExtendWith(MockitoExtension.class)` before merge. Test execution time budget per
class: unit tests < 50ms, integration tests < 5s.

**SEE ALSO:**
- 35-positive-testing-standards.md -- what to verify per layer (positive)
- 36-negative-testing-standards.md -- what to verify per layer (negative)
- 37-edge-case-testing-standards.md -- boundary and argThat patterns
- 28-test-coverage-enforcement.md -- JaCoCo 100% per-package gate
