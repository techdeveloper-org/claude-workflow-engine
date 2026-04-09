---
description: "Level 2.3 - Positive (happy-path) test scenarios for every Spring Boot layer including security/path-params/error-structure"
paths:
  - "src/test/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Positive Testing Standards (Level 2.3 - Spring Boot)

**PURPOSE:** Define the mandatory happy-path test scenarios that every Spring Boot REST
microservice must cover, organized by application layer. A positive test verifies that
the system does exactly what it should when given valid inputs and correct preconditions.
Missing positive tests cause silent gaps in coverage reports and false confidence at merge time.

**APPLIES WHEN:** Any Spring Boot REST microservice with Controller → Service → Repository layers.

---

## 1. Bootstrap Layer — Positive Tests

### What We Follow
Every main application class must have tests that verify required annotations are present
and that `main()` correctly delegates to `SpringApplication.run()`.

### How To Implement

```java
// CORRECT -- Application bootstrap positive tests
@ExtendWith(MockitoExtension.class)
class ApplicationBootstrapTest {

    // P1: @SpringBootApplication annotation present
    @Test
    @DisplayName("should have @SpringBootApplication annotation")
    void shouldHaveSpringBootApplicationAnnotation() {
        assertThat(MyServiceApplication.class)
            .isAnnotationPresent(SpringBootApplication.class);
    }

    // P2: @EnableDiscoveryClient annotation present
    @Test
    @DisplayName("should have @EnableDiscoveryClient annotation")
    void shouldHaveEnableDiscoveryClientAnnotation() {
        assertThat(MyServiceApplication.class)
            .isAnnotationPresent(EnableDiscoveryClient.class);
    }

    // P3: @EnableTransactionManagement annotation present
    @Test
    @DisplayName("should have @EnableTransactionManagement annotation")
    void shouldHaveEnableTransactionManagementAnnotation() {
        assertThat(MyServiceApplication.class)
            .isAnnotationPresent(EnableTransactionManagement.class);
    }

    // P4: main() is public and static
    @Test
    @DisplayName("should have public static main method with String[] parameter")
    void shouldHavePublicStaticMainMethod() throws NoSuchMethodException {
        Method main = MyServiceApplication.class.getMethod("main", String[].class);
        assertThat(Modifier.isPublic(main.getModifiers())).isTrue();
        assertThat(Modifier.isStatic(main.getModifiers())).isTrue();
    }

    // P5: main() delegates to SpringApplication.run()
    @Test
    @DisplayName("should delegate to SpringApplication.run() when main is called")
    void shouldDelegateToSpringApplicationRun() {
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            mocked.when(() -> SpringApplication.run(any(Class.class), any(String[].class)))
                  .thenReturn(null);

            MyServiceApplication.main(new String[]{});

            mocked.verify(() -> SpringApplication.run(
                eq(MyServiceApplication.class), any(String[].class)), times(1));
        }
    }

    // P6: main() forwards args to SpringApplication.run()
    @Test
    @DisplayName("should forward all args to SpringApplication.run()")
    void shouldForwardArgsToSpringApplicationRun() {
        String[] args = {"--server.port=9090"};
        try (MockedStatic<SpringApplication> mocked = mockStatic(SpringApplication.class)) {
            ArgumentCaptor<String[]> captor = ArgumentCaptor.forClass(String[].class);
            mocked.when(() -> SpringApplication.run(any(Class.class), captor.capture()))
                  .thenReturn(null);

            MyServiceApplication.main(args);

            assertThat(captor.getValue()).isEqualTo(args);
        }
    }

    // P7: Class is public with exactly one constructor
    @Test
    @DisplayName("should have exactly one public no-args constructor")
    void shouldHaveExactlyOnePublicConstructor() {
        Constructor<?>[] ctors = MyServiceApplication.class.getDeclaredConstructors();
        assertThat(ctors).hasSize(1);
        assertThat(Modifier.isPublic(ctors[0].getModifiers())).isTrue();
    }

    // P8: Class extends Object (no custom superclass)
    @Test
    @DisplayName("should extend Object with no custom superclass")
    void shouldExtendObject() {
        assertThat(MyServiceApplication.class.getSuperclass()).isEqualTo(Object.class);
    }
}
```

### Why This Matters
JaCoCo counts the `main()` method and class annotations in its per-package metrics.
Without these tests the entire entry package fails the 100% coverage gate.

---

## 2. Configuration Layer — Positive Tests

### What We Follow
Configuration classes must be verified to instantiate correctly and expose the exact
expected constant values that the rest of the codebase relies on.

### How To Implement

```java
// CORRECT -- Config positive tests
class CacheConfigTest {

    // P12: Config class instantiates without error
    @Test
    @DisplayName("should instantiate CacheConfig without error")
    void shouldInstantiateCacheConfigSuccessfully() {
        CacheConfig config = new CacheConfig();
        assertThat(config).isNotNull();
    }

    // P13: Single-entity cache name constant is correct
    @Test
    @DisplayName("should have correct CACHE_BY_ID constant value")
    void shouldHaveCorrectCacheByIdConstant() {
        assertThat(CacheConfig.CACHE_BY_ID).isEqualTo("entityById");
    }

    // P14: Collection cache name constant is correct
    @Test
    @DisplayName("should have correct CACHE_ALL constant value")
    void shouldHaveCorrectCacheAllConstant() {
        assertThat(CacheConfig.CACHE_ALL).isEqualTo("allEntities");
    }

    // P15: Count cache name constant is correct
    @Test
    @DisplayName("should have correct CACHE_COUNT constant value")
    void shouldHaveCorrectCacheCountConstant() {
        assertThat(CacheConfig.CACHE_COUNT).isEqualTo("entityCount");
    }
}
```

### Why This Matters
Incorrect cache constant names cause silent cache misses — the application compiles and
runs but returns stale or uncached data. String assertion catches typos before they hit staging.

---

## 3. Controller Layer — Positive Tests

### What We Follow
Every HTTP endpoint must be tested for the correct status code and response body structure
on the happy path. Use pure Mockito — no `@WebMvcTest`, no Spring context.

### How To Implement

```java
// CORRECT -- Controller layer positive tests
@ExtendWith(MockitoExtension.class)
class ResourceRestControllerTest {

    @Mock private ResourceService resourceService;
    @InjectMocks private ResourceRestController controller;

    // P18: POST create returns 201 CREATED
    @Test
    @DisplayName("should return 201 CREATED when resource is created successfully")
    void shouldReturn201WhenResourceCreated() {
        ResourceForm form = new ResourceForm("ValidName", "/valid-path");
        ApiResponse<ResourceDto> serviceResponse = ApiResponse.created(mockDto());
        when(resourceService.add(any(ResourceForm.class))).thenReturn(serviceResponse);

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.create(form);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().isSuccess()).isTrue();
    }

    // P19: PUT update returns 200 OK
    @Test
    @DisplayName("should return 200 OK when resource is updated successfully")
    void shouldReturn200WhenResourceUpdated() {
        when(resourceService.update(eq(1L), any(ResourceForm.class)))
            .thenReturn(ApiResponse.ok(mockDto()));

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.update(1L, new ResourceForm());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().isSuccess()).isTrue();
    }

    // P20: GET by ID returns 200 OK with body
    @Test
    @DisplayName("should return 200 OK with resource DTO when ID exists")
    void shouldReturn200WithDtoWhenIdExists() {
        ResourceDto dto = new ResourceDto(1L, "Name", "/path");
        when(resourceService.getById(1L)).thenReturn(ApiResponse.ok(dto));

        ResponseEntity<ApiResponse<ResourceDto>> response = controller.getById(1L);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().getData().getId()).isEqualTo(1L);
    }

    // P21: GET all returns 200 OK with LinkedHashSet
    @Test
    @DisplayName("should return 200 OK with LinkedHashSet of all resources")
    void shouldReturn200WithLinkedHashSetOfAllResources() {
        LinkedHashSet<ResourceDto> set = new LinkedHashSet<>(List.of(mockDto()));
        when(resourceService.getAll()).thenReturn(ApiResponse.ok(set));

        ResponseEntity<ApiResponse<Set<ResourceDto>>> response = controller.getAll();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().getData()).isInstanceOf(LinkedHashSet.class);
    }

    // P22: DELETE returns 200 OK
    @Test
    @DisplayName("should return 200 OK when resource is deleted successfully")
    void shouldReturn200WhenResourceDeleted() {
        when(resourceService.delete(1L)).thenReturn(ApiResponse.ok(null));

        ResponseEntity<ApiResponse<Void>> response = controller.delete(1L);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    // P23: GET count returns 200 OK with count value
    @Test
    @DisplayName("should return 200 OK with resource count")
    void shouldReturn200WithResourceCount() {
        when(resourceService.getCount()).thenReturn(ApiResponse.ok(5L));

        ResponseEntity<ApiResponse<Long>> response = controller.getCount();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().getData()).isEqualTo(5L);
    }
}
```

### Why This Matters
Every endpoint has an HTTP contract. Testing status codes and delegation in isolation
catches broken contracts in milliseconds without loading the Spring application context.

---

## 4. Service Layer — Positive Tests

### What We Follow
Every service method must be tested on its happy path: correct repository delegation,
entity-to-DTO mapping, cache event publishing, and count retrieval.

### How To Implement

```java
// CORRECT -- Service layer positive tests
@ExtendWith(MockitoExtension.class)
class ResourceServiceImplTest {

    @Mock private ResourceRepository resourceRepository;
    @Mock private EventPublisher eventPublisher;
    @InjectMocks private ResourceServiceImpl resourceService;

    // P31: Add resource — success returns populated DTO
    @Test
    @DisplayName("should return 201 with DTO when valid resource is added")
    void shouldReturn201WithDtoWhenResourceAdded() {
        ResourceForm form = new ResourceForm("Name", "/path");
        ResourceEntity saved = new ResourceEntity(1L, "Name", "/path");
        when(resourceRepository.existsByNameIgnoreCase("Name")).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCase("/path")).thenReturn(false);
        when(resourceRepository.save(any(ResourceEntity.class))).thenReturn(saved);

        ApiResponse<ResourceDto> result = resourceService.add(form);

        assertThat(result.getStatus()).isEqualTo(201);
        assertThat(result.getData().getName()).isEqualTo("Name");
        verify(resourceRepository, times(1)).save(any(ResourceEntity.class));
    }

    // P32: Update resource — success returns updated DTO
    @Test
    @DisplayName("should return 200 with updated DTO when resource is updated")
    void shouldReturn200WithUpdatedDtoWhenResourceUpdated() {
        ResourceForm form = new ResourceForm("Updated", "/updated");
        ResourceEntity existing = new ResourceEntity(1L, "Old", "/old");
        ResourceEntity saved = new ResourceEntity(1L, "Updated", "/updated");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("Updated", 1L)).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCaseAndIdNot("/updated", 1L)).thenReturn(false);
        when(resourceRepository.save(any(ResourceEntity.class))).thenReturn(saved);

        ApiResponse<ResourceDto> result = resourceService.update(1L, form);

        assertThat(result.getStatus()).isEqualTo(200);
        assertThat(result.getData().getName()).isEqualTo("Updated");
    }

    // P33: Get by ID — returns DTO with correct field mapping
    @Test
    @DisplayName("should return DTO with all fields mapped when resource exists by ID")
    void shouldReturnDtoWithAllFieldsMappedWhenResourceExistsById() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(entity));

        ApiResponse<ResourceDto> result = resourceService.getById(1L);

        assertThat(result.getData().getId()).isEqualTo(1L);
        assertThat(result.getData().getName()).isEqualTo("Name");
        assertThat(result.getData().getPath()).isEqualTo("/path");
    }

    // P34-P35: Get all — items sorted by ID ASC
    @Test
    @DisplayName("should call repository with Sort.by ASC id and return sorted results")
    void shouldCallRepositoryWithSortByIdAscAndReturnSortedResults() {
        List<ResourceEntity> entities = List.of(
            new ResourceEntity(1L, "A", "/a"),
            new ResourceEntity(2L, "B", "/b"));
        when(resourceRepository.findAll(any(Sort.class))).thenReturn(entities);

        ApiResponse<Set<ResourceDto>> result = resourceService.getAll();

        verify(resourceRepository).findAll(argThat(sort ->
            sort.equals(Sort.by(Sort.Direction.ASC, "id"))));
        assertThat(result.getData()).hasSize(2);
    }

    // P36: Delete — success publishes DELETE cache event
    @Test
    @DisplayName("should publish DELETE cache event when resource is deleted")
    void shouldPublishDeleteCacheEventWhenResourceIsDeleted() {
        doNothing().when(resourceRepository).deleteById(1L);

        resourceService.delete(1L);

        verify(eventPublisher, times(1)).publish(argThat(event ->
            event.getEventType() == EventType.DELETE && event.getEntityId().equals(1L)));
    }

    // P37-P38: Count — returns repository count value correctly
    @Test
    @DisplayName("should return correct count from repository")
    void shouldReturnCorrectCountFromRepository() {
        when(resourceRepository.count()).thenReturn(5L);

        ApiResponse<Long> result = resourceService.getCount();

        assertThat(result.getData()).isEqualTo(5L);
    }

    @Test
    @DisplayName("should return zero count when repository is empty")
    void shouldReturnZeroCountWhenRepositoryIsEmpty() {
        when(resourceRepository.count()).thenReturn(0L);

        ApiResponse<Long> result = resourceService.getCount();

        assertThat(result.getData()).isEqualTo(0L);
    }

    // P39: Update with same data (idempotent) — succeeds without error
    @Test
    @DisplayName("should succeed when update is called with identical data")
    void shouldSucceedWhenUpdateCalledWithIdenticalData() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        ResourceForm form = new ResourceForm("Name", "/path");
        when(resourceRepository.findById(1L)).thenReturn(Optional.of(entity));
        when(resourceRepository.existsByNameIgnoreCaseAndIdNot("Name", 1L)).thenReturn(false);
        when(resourceRepository.existsByPathIgnoreCaseAndIdNot("/path", 1L)).thenReturn(false);
        when(resourceRepository.save(any())).thenReturn(entity);

        assertThatNoException().isThrownBy(() -> resourceService.update(1L, form));
    }
}
```

### Why This Matters
Service layer holds all business rules. Happy-path tests verify that entity-to-DTO
mapping is complete, sort contracts are respected, and cache events are published on
every mutating operation.

---

## 5. Entity Layer — Positive Tests

### What We Follow
Every JPA entity must have tests for constructors, getters, setters, and the equality
contract (equals/hashCode/toString/Serializable).

### How To Implement

```java
// CORRECT -- Entity positive tests (no mocks, direct instantiation)
class ResourceEntityTest {

    // P51: Parameterized constructor sets all fields
    @Test
    @DisplayName("should set all fields when parameterized constructor is called")
    void shouldSetAllFieldsWhenParameterizedConstructorCalled() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        assertThat(entity.getId()).isEqualTo(1L);
        assertThat(entity.getName()).isEqualTo("Name");
        assertThat(entity.getPath()).isEqualTo("/path");
    }

    // P52: No-args constructor creates non-null instance
    @Test
    @DisplayName("should create non-null instance with no-args constructor")
    void shouldCreateNonNullInstanceWithNoArgsConstructor() {
        ResourceEntity entity = new ResourceEntity();
        assertThat(entity).isNotNull();
    }

    // P53: Getters return values set by setters
    @Test
    @DisplayName("should return correct value from getter after setter is called")
    void shouldReturnCorrectValueFromGetterAfterSetterCalled() {
        ResourceEntity entity = new ResourceEntity();
        entity.setId(42L);
        entity.setName("Test");
        entity.setPath("/test");

        assertThat(entity.getId()).isEqualTo(42L);
        assertThat(entity.getName()).isEqualTo("Test");
        assertThat(entity.getPath()).isEqualTo("/test");
    }

    // P54-P56: equals() contracts
    @Test
    @DisplayName("should be equal when two instances have identical field values")
    void shouldBeEqualWhenTwoInstancesHaveIdenticalFieldValues() {
        ResourceEntity e1 = new ResourceEntity(1L, "Name", "/path");
        ResourceEntity e2 = new ResourceEntity(1L, "Name", "/path");
        assertThat(e1).isEqualTo(e2);
    }

    @Test
    @DisplayName("should be equal to itself (reflexive)")
    void shouldBeEqualToItself() {
        ResourceEntity entity = new ResourceEntity(1L, "Name", "/path");
        assertThat(entity).isEqualTo(entity);
    }

    // P55: hashCode contract
    @Test
    @DisplayName("should have same hashCode when two equal instances are compared")
    void shouldHaveSameHashCodeForEqualInstances() {
        ResourceEntity e1 = new ResourceEntity(1L, "Name", "/path");
        ResourceEntity e2 = new ResourceEntity(1L, "Name", "/path");
        assertThat(e1.hashCode()).isEqualTo(e2.hashCode());
    }

    // P57-P59: toString contract
    @Test
    @DisplayName("should return non-null non-empty toString")
    void shouldReturnNonNullToString() {
        assertThat(new ResourceEntity(1L, "Name", "/path").toString()).isNotNull();
    }

    @Test
    @DisplayName("should contain class name in toString output")
    void shouldContainClassNameInToString() {
        assertThat(new ResourceEntity(1L, "Name", "/path").toString())
            .contains("ResourceEntity");
    }

    @Test
    @DisplayName("should contain field values in toString output")
    void shouldContainFieldValuesInToString() {
        assertThat(new ResourceEntity(1L, "Name", "/path").toString())
            .contains("1", "Name", "/path");
    }

    // P60-P61: Serialization contract
    @Test
    @DisplayName("should implement Serializable")
    void shouldImplementSerializable() {
        assertThat(ResourceEntity.class).isAssignableTo(Serializable.class);
    }

    @Test
    @DisplayName("should have serialVersionUID field declared")
    void shouldHaveSerialVersionUidField() throws NoSuchFieldException {
        assertThatNoException().isThrownBy(() ->
            ResourceEntity.class.getDeclaredField("serialVersionUID"));
    }
}
```

### Why This Matters
Broken entity equals/hashCode contracts silently corrupt `HashSet` collections and
JPA second-level cache lookups. Missing `serialVersionUID` causes `InvalidClassException`
in distributed deployments using Java serialization for session clustering.

---

## 6. Exception Handler Layer — Positive Tests

### What We Follow
Every `@ControllerAdvice` method must be tested to verify it produces the correct
HTTP status code, a non-null response body, and a non-null message field.

### How To Implement

```java
// CORRECT -- Exception handler positive tests
@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerTest {

    @InjectMocks private GlobalExceptionHandler handler;

    // P74: DuplicateNameException → 409 with correct structure
    @Test
    @DisplayName("should return 409 CONFLICT with structured body for DuplicateNameException")
    void shouldReturn409ConflictForDuplicateNameException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicateName(new DuplicateResourceException("Resource exists."));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().isSuccess()).isFalse();
        assertThat(response.getBody().getMessage()).isNotEmpty();
    }

    // P75: DuplicatePathException → 409 with correct structure
    @Test
    @DisplayName("should return 409 CONFLICT with structured body for DuplicatePathException")
    void shouldReturn409ConflictForDuplicatePathException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicatePath(new ResourceConflictException("Path exists."));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody().isSuccess()).isFalse();
        assertThat(response.getBody().getMessage()).isNotEmpty();
    }

    // P76: DataIntegrityViolationException → 409 with full body verification
    @Test
    @DisplayName("should return 409 CONFLICT with success=false and non-leaking message for DataIntegrityViolationException")
    void shouldReturn409ForDataIntegrityViolationException() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDataIntegrity(new DataIntegrityViolationException("constraint"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().isSuccess()).isFalse();
        assertThat(response.getBody().getMessage()).isNotBlank();
        // Must not leak internal constraint details (SQL table names, column names)
        assertThat(response.getBody().getMessage()).doesNotContain("constraint");
        assertThat(response.getStatusCodeValue()).isEqualTo(response.getBody().getStatus());
    }

    // P77: ResponseEntity status matches body status field
    @Test
    @DisplayName("should have matching HTTP status code and body status field")
    void shouldHaveMatchingHttpStatusAndBodyStatusField() {
        ResponseEntity<ApiResponse<Void>> response =
            handler.handleDuplicateName(new DuplicateResourceException("exists"));

        assertThat(response.getStatusCodeValue())
            .isEqualTo(response.getBody().getStatus());
    }
}
```

### Why This Matters
Exception handler responses are often the only signal a client has when an operation
fails. A well-structured error response with `success=false` and a non-empty message
prevents clients from guessing the failure reason.

---

## 7. Form Validation Layer — Positive Tests

### What We Follow
Every valid input variant must be tested against the validator to confirm zero violations.
This includes minimum-length, maximum-length, and special-character inputs.

### How To Implement

```java
// CORRECT -- Form validation positive tests
class ResourceFormValidationTest {

    private Validator validator;

    @BeforeEach
    void setUp() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    // P82: Valid form — no violations
    @Test
    @DisplayName("should have no violations for a valid form with name and path")
    void shouldHaveNoViolationsForValidForm() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("ValidName", "/valid-path"),
                               ValidationSequence.class);
        assertThat(violations).isEmpty();
    }

    // P83: Minimum valid name (1 character)
    @Test
    @DisplayName("should have no violations when name has exactly 1 character")
    void shouldHaveNoViolationsWhenNameIsOneCharacter() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("A", "/path"), ValidationSequence.class);
        assertThat(violations).isEmpty();
    }

    // P84: Maximum valid name (50 characters)
    @Test
    @DisplayName("should have no violations when name has exactly 50 characters")
    void shouldHaveNoViolationsWhenNameIsMaxLength() {
        String maxName = "A".repeat(50);
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm(maxName, "/path"), ValidationSequence.class);
        assertThat(violations).isEmpty();
    }

    // P85: Maximum valid path (50 characters)
    @Test
    @DisplayName("should have no violations when path has exactly 50 characters")
    void shouldHaveNoViolationsWhenPathIsMaxLength() {
        String maxPath = "/p".repeat(25); // exactly 50 chars
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("Name", maxPath), ValidationSequence.class);
        assertThat(violations).isEmpty();
    }

    // P86: Special characters in name — valid
    @Test
    @DisplayName("should have no violations when name contains special characters")
    void shouldHaveNoViolationsWhenNameContainsSpecialCharacters() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("Res & Name (2024)", "/path"),
                               ValidationSequence.class);
        assertThat(violations).isEmpty();
    }

    // P87: Numbers in name — valid
    @Test
    @DisplayName("should have no violations when name contains numbers")
    void shouldHaveNoViolationsWhenNameContainsNumbers() {
        Set<ConstraintViolation<ResourceForm>> violations =
            validator.validate(new ResourceForm("Resource123", "/path"),
                               ValidationSequence.class);
        assertThat(violations).isEmpty();
    }
}
```

### Why This Matters
Positive validation tests document the exact acceptance boundaries. Without them,
teams unknowingly tighten constraints (e.g., reducing max from 50 to 30 chars) and
break existing clients that were within the original contract.

---

## 8. Event Publisher Layer — Positive Tests

### What We Follow
Every event type (CREATE, UPDATE, DELETE) must be verified for correct event type,
entity type, and entity ID in the published payload.

### How To Implement

```java
// CORRECT -- Event publisher positive tests
@ExtendWith(MockitoExtension.class)
class CacheEventPublisherTest {

    @Mock private RedisTemplate<String, CacheInvalidationEvent> redisTemplate;
    @InjectMocks private CacheEventPublisher publisher;

    // P102-P103: CREATE event with null entityId
    @Test
    @DisplayName("should publish CREATE event with correct entity type and null entityId")
    void shouldPublishCreateEventWithCorrectEntityTypeAndNullEntityId() {
        doNothing().when(redisTemplate).convertAndSend(anyString(), any());

        publisher.publishCreate(null);

        verify(redisTemplate).convertAndSend(anyString(), argThat(event ->
            event.getEntityType().equals(EntityType.RESOURCE) &&
            event.getEventType() == EventType.CREATE &&
            event.getEntityId() == null));
    }

    // P104: UPDATE event with populated entityId
    @Test
    @DisplayName("should publish UPDATE event with correct entity type and entityId")
    void shouldPublishUpdateEventWithCorrectEntityTypeAndEntityId() {
        doNothing().when(redisTemplate).convertAndSend(anyString(), any());

        publisher.publishUpdate(1L);

        verify(redisTemplate).convertAndSend(anyString(), argThat(event ->
            event.getEntityType().equals(EntityType.RESOURCE) &&
            event.getEventType() == EventType.UPDATE &&
            event.getEntityId().equals(1L)));
    }

    // P105: DELETE event with populated entityId
    @Test
    @DisplayName("should publish DELETE event with correct entity type and entityId")
    void shouldPublishDeleteEventWithCorrectEntityTypeAndEntityId() {
        doNothing().when(redisTemplate).convertAndSend(anyString(), any());

        publisher.publishDelete(1L);

        verify(redisTemplate).convertAndSend(anyString(), argThat(event ->
            event.getEntityType().equals(EntityType.RESOURCE) &&
            event.getEventType() == EventType.DELETE &&
            event.getEntityId().equals(1L)));
    }
}
```

### Why This Matters
Incorrect event type or wrong entity type in the published payload causes the consumer
to either ignore the event or invalidate the wrong cache key — both are invisible without
this test.

---

---

## 9. Security Layer — Positive Tests (SEC1–SEC2)

### What We Follow
Protected endpoints must succeed with valid authentication. Public endpoints (health, readiness)
must be accessible without authentication.

### How To Implement

```java
// CORRECT -- Security positive tests with MockMvc + @WithMockUser
@ExtendWith(MockitoExtension.class)
class SecurityPositiveTest {

    // SEC1: Authenticated request to protected endpoint succeeds
    @Test
    @DisplayName("should return 200 OK when request has valid authentication")
    void shouldReturn200WhenRequestHasValidAuth() {
        // Using MockMvc with security context
        mockMvc.perform(get("/api/v1/resources/1")
                .header("Authorization", "Bearer " + validJwtToken)
                .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.success").value(true))
            .andExpect(jsonPath("$.data.id").value(1));
    }

    // SEC2: Health endpoint accessible without authentication
    @Test
    @DisplayName("should return 200 OK on /actuator/health without authentication")
    void shouldReturn200OnHealthEndpointWithoutAuth() {
        mockMvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }
}
```

### Why This Matters
If the auth filter rejects valid tokens, the entire API is inaccessible. If health endpoints
require auth, Kubernetes liveness/readiness probes fail and the pod enters CrashLoopBackOff.

---

## 10. Path Parameters — Positive Tests (PP — no positive IDs, positive path tests are already in P20)

No additional positive path parameter tests needed — P20 (GET by valid ID → 200) already covers the happy path.

---

## 11. Error Structure — Positive Tests (ERR — no positive IDs)

No additional positive error structure tests needed — P74-P77 already verify correct error response structure on success paths.

---

**ENFORCEMENT:** Every PR introducing a new layer (controller, service, entity, handler,
form, publisher) must include all corresponding positive-scenario tests from this catalog
before the coverage gate runs. Missing positive tests will cause branch/method coverage
failures under JaCoCo 100% per-package enforcement.

**SEE ALSO:**
- 28-test-coverage-enforcement.md -- JaCoCo 100% per-package gate
- 36-negative-testing-standards.md -- error-path tests for every layer
- 37-edge-case-testing-standards.md -- boundary and null-safety tests
- 38-test-mocking-strategy.md -- which isolation strategy to use per layer
