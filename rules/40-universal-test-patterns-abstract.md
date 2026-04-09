---
description: "Level 2.3 - Language-agnostic universal test patterns for REST microservices (122 scenarios across 8 layers)"
paths:
  - "src/test/**"
  - "tests/**"
  - "test/**"
  - "*_test.go"
priority: critical
conditional: "Any REST microservice project detected"
---

# Universal Test Patterns (Level 2.3 - Language-Agnostic)

**PURPOSE:** This file is the abstract source of truth for ALL test scenarios across every REST
microservice regardless of programming language or framework. It defines WHAT must be tested
(the concept, the assertion target, the universality argument) without prescribing HOW to write
the test in any particular syntax. Language-specific rules files (35-39 for Java/Spring Boot,
41 for Python/FastAPI, 42 for Node.js/Express, 43 for Go) derive their implementation examples
directly from the scenario IDs defined here. When a new scenario is added here, every language
file must implement it. When a scenario is removed here, every language file removes it. This
file is the single authoritative source that prevents scenario drift across the polyglot fleet.

**APPLIES WHEN:** Any REST microservice regardless of language or framework. All 8 layers apply
to any microservice that follows the Controller/Route-Handler → Service/Business-Logic →
Repository/Data-Access architectural pattern with a response envelope, input validation, domain
entities, error handlers, and event publishing.

---

## Language Mapping Reference

| Concept | Java/Spring Boot | Python/FastAPI | Node.js/Express | Go |
|---------|-----------------|----------------|-----------------|-----|
| Test Framework | JUnit 5 | pytest | Jest/Vitest | testing + testify |
| Mock Library | Mockito | unittest.mock / pytest-mock | jest.fn() / jest.mock() | gomock / testify/mock |
| HTTP Test Client | Pure method call (no MockMvc) | httpx.AsyncClient / TestClient | supertest | net/http/httptest |
| Assertion Library | AssertJ | pytest assert / assertpy | expect (Jest) | testify/assert |
| Validation Framework | Hibernate Validator (JSR-380) | Pydantic v2 / marshmallow | Zod / class-validator | go-playground/validator |
| Static Mock | MockedStatic | @patch / monkeypatch | jest.spyOn | monkey-patching / build tags |
| Response Wrapper | ResponseEntity&lt;ApiResponse&lt;T&gt;&gt; | JSONResponse / dict | res.json() | http.ResponseWriter + JSON |
| ORM/Repository | Spring Data JPA | SQLAlchemy / Tortoise | Prisma / TypeORM / Drizzle | GORM / sqlx |
| Event Publishing | RedisTemplate.convertAndSend | redis.publish() / aio_pika | ioredis.publish() / amqplib | go-redis Publish() |
| Config Constants | static final fields | settings / env vars | config object / .env | const / env vars |

---

## Layer 1: Application Bootstrap

**Applicable To:** Every microservice that has an entry-point class or module that starts the
framework (Spring Boot `main()`, FastAPI `app = FastAPI()` + uvicorn startup, Express `app.listen()`,
Go `http.ListenAndServe()`).

**Isolation Principle:** Never start the real framework or network stack during bootstrap tests.
Use static method interception (MockedStatic, monkeypatch, jest.spyOn, build tags) to intercept
the framework's startup call. The test verifies the entry-point's structural contract — what
decorators/annotations it carries and what it delegates to — without paying framework startup cost.
Bootstrap tests must complete in under 5 ms each.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P1 | Entry-point class/module has required framework decorator or annotation | The class or module carries the annotation that activates the framework (e.g., @SpringBootApplication, the FastAPI app factory invocation, the Express app instantiation, the Go main package declaration) | Reflection or metadata check confirms the decorator/annotation is present on the entry-point type | Every framework requires a specific bootstrap marker; its absence means the app silently fails to start, making this a mandatory structural check |
| P2 | Service discovery registration is enabled (if microservice) | The entry-point carries the annotation or configuration that registers the service with the discovery client (Eureka, Consul, etc.) | Metadata check on entry-point class confirms discovery annotation is present | Microservices that miss the discovery registration are invisible to the service mesh; the bootstrap test catches this at unit-test time rather than at deployment |
| P3 | Transaction management is enabled (if database-backed) | The entry-point or configuration class carries the transaction-management enablement marker | Metadata check confirms transaction annotation is present | Missing transaction enablement causes write operations to execute outside a transaction boundary, leading to partial-commit data corruption that is invisible without this test |
| P4 | Entry-point function is callable with the correct signature | The main/startup function accepts the expected parameter types (string array, no args, context, etc.) | Reflection or signature inspection confirms parameter types and count match the framework's expected signature | An incorrect signature compiles/parses without error in most languages but causes a runtime panic or startup failure; this test catches the mismatch before deployment |
| P5 | Entry-point delegates to framework startup, not custom logic | When the entry-point function is called, it invokes the framework's startup function exactly once | Mock/spy on the framework startup call; assert it was called exactly once with the correct arguments | Entry-points that implement custom startup logic instead of delegating to the framework bypass the framework's initialization guarantees (dependency injection, lifecycle hooks, health checks) |
| P6 | Entry-point forwards all CLI arguments to the framework startup | Arguments passed to the entry-point function are forwarded unchanged to the framework's startup call | Capture the arguments received by the mocked/spied framework startup; assert they equal the arguments passed to entry-point | Frameworks use CLI arguments for profile selection, port override, and config override; silently dropping them causes environment-specific configuration to be ignored |
| P7 | Entry-point class has expected structure (single constructor or init) | The entry-point type has exactly one constructor/initializer and no unexpected superclass | Reflection check on constructor count and superclass | Multiple constructors on the entry-point indicate accidental complexity; an unexpected superclass indicates an inheritance mistake that changes initialization order |
| P8 | Entry-point has no custom superclass or base-class | The entry-point class does not extend any class other than the language default (Object in Java, object in Python, nothing in Go) | Reflection check on superclass name | Extending a custom base class in the entry-point creates a hidden initialization dependency that is invisible at the call site and cannot be mocked without starting the real class hierarchy |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N9 | Entry-point with null/None/nil arguments does not crash | Calling the entry-point function with null/None/nil as the argument array does not throw, panic, or raise an unhandled exception | No exception/panic is raised; framework startup mock is still invoked or gracefully skipped | JVM and CLR pass null args to main() from some test harnesses; Go's os.Args can be empty; Python sys.argv can be manipulated; robustness to nil/null input is required for safe test execution |
| N10 | Entry-point with empty arguments still invokes framework startup | Calling the entry-point function with an empty argument array (zero elements) still delegates to the framework startup | Framework startup mock/spy receives the call exactly once even when args is empty | Empty args is the most common test invocation; if the entry-point conditionally delegates only when args are present, the framework never starts in production with default configuration |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E11 | Entry-point with multiple CLI flags forwards all without loss | Calling the entry-point with several flags (e.g., --profile=test, --port=9090, --debug) forwards every flag to the framework startup call without modification or truncation | Capture the argument array at the framework startup mock; assert it contains all input flags with identical values | Partial forwarding (forwarding only the first argument, or dropping flags after a separator) causes profile-specific and environment-specific configuration to silently fail in CI where multiple flags are commonly passed |

---

## Layer 2: Configuration

**Applicable To:** Every microservice that has a configuration class, constants module, or
settings object that defines cache names, queue names, timeout values, or other cross-layer
string constants.

**Isolation Principle:** Configuration tests require no mocks. Instantiate the configuration
class or module directly using its default constructor or the settings factory. Verify constant
values and class-level properties through direct field access or property inspection. These
tests must complete in under 1 ms each because they perform no I/O.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P12 | Config module/class instantiates without error | Calling the default constructor or the settings factory produces a valid configuration object without throwing, raising, or panicking | Instance is non-null/non-nil and is of the expected type | A configuration class that fails to instantiate causes the entire service to fail at startup with an unhelpful error; this test isolates the failure to the configuration class before integration |
| P13 | Cache name constant for single-entity lookup has correct value | The cache name constant used for "get by ID" operations equals the expected string value | Constant field or property value equals the expected literal string | Cache names are used as keys in the cache store; a typo means cache misses for every lookup, silently degrading to full database queries without any error signal |
| P14 | Cache name constant for collection lookup has correct value | The cache name constant used for "get all" or "list" operations equals the expected string value | Constant field or property value equals the expected literal string | Same rationale as P13 but for collection-level cache keys; a wrong value causes repeated full-table scans |
| P15 | Cache name constant for count query has correct value | The cache name constant used for "count" operations equals the expected string value | Constant field or property value equals the expected literal string | Count queries are typically the most expensive SELECT in an aggregate-heavy service; incorrect cache names disable the count cache, causing repeated expensive COUNT(*) queries |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N16 | No configuration constant is null/None/nil/empty | Every constant field or property in the configuration class has a non-null, non-None, non-nil, non-empty-string value | Iterate all constant fields via reflection or explicit assertion; assert each is non-null and non-blank | A null cache name causes a null-key lookup in the cache store which either silently misses every time (Redis) or throws a NullPointerException (Caffeine) depending on the implementation |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E17 | All configuration constants are distinct (no duplicate values) | No two constant fields in the configuration class share the same string value | Collect all constant values into a set; assert set size equals field count | Two cache names that share a value cause one cache to evict or overwrite the other's entries; in a Spring Cache + Caffeine setup this causes silent data corruption between cache regions |

---

## Layer 3: Controller / Route Handler

**Applicable To:** Every microservice that exposes HTTP endpoints. This layer tests the HTTP
contract: method, path, status code, response body structure, and delegation to the service layer.

**Isolation Principle:** Mock the service layer. Call the controller/handler method directly
without starting an HTTP server or MVC framework. Verify what the controller returns and what
it delegates to the service. Do not use integration-style test clients (MockMvc, TestClient,
supertest) for these unit tests — pure method invocation is faster and more isolated. HTTP
integration tests belong in a separate integration test suite.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P18 | POST create endpoint returns 201 CREATED with response body | Calling the create handler with a valid form/request body returns HTTP 201 and a non-null response body containing the created resource's DTO | HTTP status code is 201; response body is non-null; success flag is true | Every REST API must return 201 (not 200) for creation; returning 200 breaks clients that use status codes to detect newly created resources for cache invalidation and UI state updates |
| P19 | PUT update endpoint returns 200 OK with updated body | Calling the update handler with a valid ID and form/request body returns HTTP 200 and a response body containing the updated resource's DTO | HTTP status code is 200; response body contains updated field values; success flag is true | Update operations must return the current state of the resource after the update so clients do not need a separate GET to refresh their state |
| P20 | GET by ID endpoint returns 200 OK with single resource | Calling the get-by-ID handler with a valid ID returns HTTP 200 and a response body containing exactly one resource DTO | HTTP status code is 200; response body contains a single resource; all DTO fields are populated | The by-ID endpoint is the canonical read path; its correct status and body are the baseline expectation for all other layers that delegate to it |
| P21 | GET all endpoint returns 200 OK with ordered collection | Calling the get-all handler returns HTTP 200 and a response body containing an ordered collection (list, array, or slice) of resource DTOs | HTTP status code is 200; response body contains an ordered collection type; collection is not null | Returning an unordered collection or a single object instead of a collection breaks all clients that iterate the result set |
| P22 | DELETE endpoint returns 200 OK or 204 NO CONTENT | Calling the delete handler with a valid ID returns either HTTP 200 with a success response or HTTP 204 with no body | HTTP status code is 200 or 204; if 200, success flag is true; if 204, body is null/empty | The correct status code for delete depends on the API contract; the test enforces whichever the contract specifies and detects accidental drift to other codes |
| P23 | GET count endpoint returns 200 OK with numeric value | Calling the count handler returns HTTP 200 and a response body containing a numeric (integer or long) value | HTTP status code is 200; response body contains a numeric type; value is zero or positive | Count endpoints are commonly used for pagination UIs and analytics; incorrect types (string instead of number) cause silent deserialization errors in typed clients |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N24 | POST with duplicate name propagates conflict error (409) | When the service layer throws a duplicate-name exception, the controller's response status is 409 Conflict and the body contains success=false | HTTP status code is 409; success field is false; response body is non-null | Controllers must not swallow typed exceptions from the service; if they catch and re-wrap, they must preserve the 409 status code that clients use to detect and report name conflicts |
| N25 | POST with duplicate path/slug propagates conflict error (409) | When the service layer throws a duplicate-path exception, the controller's response status is 409 Conflict | HTTP status code is 409; success field is false | Duplicate path validation is a separate constraint from duplicate name; both must be tested independently to ensure the controller propagates each correctly |
| N26 | GET with non-existent ID propagates not-found error (404) | When the service layer throws a not-found exception, the controller's response status is 404 Not Found | HTTP status code is 404; success field is false | Controllers must propagate 404 rather than returning 200 with a null body; clients check status codes for routing decisions and null bodies cause NullPointerExceptions in typed deserializers |
| N27 | PUT with non-existent ID propagates not-found error (404) | When the service layer throws a not-found exception for the update target, the controller's response status is 404 | HTTP status code is 404; success field is false | Update operations on non-existent resources must signal 404, not 200 or 400; 404 is the correct semantic for "the resource you are trying to update does not exist" |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E28 | GET all with empty data returns empty collection, NOT null | When the service returns an empty collection, the controller returns 200 with an empty list/array/slice — never null | HTTP status code is 200; response body data field is an empty collection (size 0, not null) | Null collections cause NullPointerExceptions in clients that iterate; empty collection is always the safe, correct contract for "no results found" |
| E29 | GET all preserves ordered collection type (insertion order) | The collection type returned by the controller is ordered (List, array, slice) not unordered (Set, map, dict without order) | Response body data field is an ordered sequence type, not a set or unordered map | Unordered collection types (Set, HashSet) cause non-deterministic ordering in JSON serialization; clients that rely on consistent ordering (e.g., displaying the most recently created item first) will see random ordering |
| E30 | Service/handler function invoked exactly once per request (no double-call) | When the controller handles a single request, it calls the corresponding service method exactly once | Mock verify on the service mock asserts call count equals 1 | Accidental double-calls to service methods cause duplicate database writes, duplicate cache invalidations, and duplicate event publications; this test catches the bug before it reaches production |

---

## Layer 4: Service / Business Logic

**Applicable To:** Every microservice that has a service layer containing business logic,
validation, and coordination between the repository and event publisher.

**Isolation Principle:** Mock the repository layer and the event publisher. Call service methods
directly. Verify the arguments passed to repository and publisher mocks using argument captors or
argument matchers. Do not use real databases or real message brokers in service unit tests.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P31 | Add resource returns populated DTO with correct fields | After the service's add/create method is called with a valid form, it returns a non-null DTO with all expected fields populated | Returned DTO is non-null; ID field is populated (set by repository); name and path fields equal the input values | The add method is the primary write path; a DTO missing fields (ID is null, name is wrong) indicates the service is not correctly mapping from the saved entity back to the DTO |
| P32 | Update resource returns updated DTO | After the service's update method is called with a valid ID and form, it returns a DTO reflecting the new field values | Returned DTO fields equal the values from the update form, not the original entity values | If the service returns the pre-update entity instead of the post-update entity, clients display stale data without an error signal |
| P33 | Get by ID returns DTO with all fields correctly mapped | After the service's get-by-ID method is called with a valid ID, it returns a DTO with all fields mapped from the entity | ID, name, path, and all other entity fields are present and equal in the returned DTO | Incorrect field mapping (e.g., name mapped to path field) causes incorrect display in the UI without triggering any error |
| P34 | Get all passes sort-by-ID-ascending to repository | When the service's get-all method is called, it invokes the repository's find-all method with a sort specification of ID ascending | Argument captor on the repository call captures a sort specification with direction=ASC and field=id | Services that pass no sort argument to the repository get database-default ordering which is undefined and non-deterministic; explicit sort ensures consistent pagination |
| P35 | Get all returns items in ID-ascending order | The collection returned by get-all has items sorted by ID from smallest to largest | Assert that the returned collection's IDs form a non-decreasing sequence | Non-deterministic ordering causes flaky tests downstream and confuses users who expect the most recently created item to appear in a consistent position |
| P36 | Delete triggers DELETE cache invalidation event | After the service's delete method is called, it publishes exactly one event of the DELETE type on the expected channel | Event publisher mock receives exactly one call with event type DELETE and the correct entity ID | Skipping the cache invalidation event after delete causes stale data to remain in the cache; subsequent gets return the deleted entity until TTL expiry |
| P37 | Count returns correct non-zero count | When the repository contains N entities, the service's count method returns N | Returned value equals the expected non-zero integer | A count that always returns zero (due to a missing repository delegation) is indistinguishable from "empty" and causes pagination to show 0 pages even when data exists |
| P38 | Count returns zero when repository is empty | When the repository contains no entities, the service's count method returns zero | Returned value equals zero (integer, not null) | A null return instead of zero causes NullPointerException in any arithmetic that divides by the count or uses it for pagination math |
| P39 | Update with identical data (idempotent) succeeds without error | Calling the update method twice with the same form data (same name, same path) on the same entity ID succeeds on the second call without throwing a duplicate exception | No exception is raised; returned DTO on second call reflects the same values as the first | Many update forms submit unchanged data; the service must distinguish "same resource updating its own values" from "a different resource trying to take the same name/path" |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N40 | Add with duplicate name throws typed duplicate exception | When a resource with the given name already exists, the add method throws the service's typed duplicate-name exception, not a generic exception | A typed exception specific to "duplicate name" is thrown; generic Exception or NullPointerException is not thrown | Typed exceptions allow the exception handler layer to map specifically to 409 Conflict; generic exceptions fall through to the catch-all 500 handler |
| N41 | Add with duplicate path throws typed conflict exception | When a resource with the given path already exists, the add method throws the service's typed duplicate-path exception | A typed exception specific to "duplicate path" is thrown | Duplicate name and duplicate path are separate constraints; both must throw typed exceptions for the handler to produce distinct 409 messages |
| N42 | Get by non-existent ID throws typed not-found exception | When the repository returns empty/null for the given ID, get-by-ID throws the service's typed not-found exception | A typed exception specific to "not found" is thrown; null is not returned | Returning null instead of throwing causes NullPointerException at the call site rather than a meaningful 404 response |
| N43 | Update non-existent ID throws typed not-found exception | When the repository returns empty/null for the given ID in the update method, update throws the service's typed not-found exception | A typed not-found exception is thrown; null is not returned | Update must verify the entity exists before applying changes; silently creating a new entity on update (upsert) when the contract specifies update-only is a data integrity violation |
| N44 | Update with name taken by another resource throws duplicate exception | When the name from the update form is already held by a different resource (different ID), the update method throws the typed duplicate-name exception | A typed duplicate-name exception is thrown; the check must exclude the current entity (same ID must not trigger this exception) | Without this check, renaming a resource to a name that another resource holds is incorrectly allowed, creating two resources with the same name |
| N45 | Update with path taken by another resource throws duplicate exception | When the path from the update form is already held by a different resource (different ID), the update method throws the typed duplicate-path exception | A typed duplicate-path exception is thrown; the check must exclude the current entity | Same rationale as N44 but for path uniqueness; path and name uniqueness are separate constraints that both require self-exclusion logic |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E46 | Case-insensitive duplicate detection blocks "Resource" when "resource" exists | When a resource with the lowercase name "resource" exists, attempting to add "Resource" (mixed case) triggers the duplicate-name exception | Typed duplicate-name exception is thrown for case-variant of an existing name | Case-sensitive duplicate checks allow "Admin" and "admin" to coexist, causing data inconsistency and user confusion; case-insensitive checks are required for user-visible names |
| E47 | Get all with empty repository returns empty collection, not null | When the repository returns an empty list/slice/array, the service returns an empty collection (size 0) | Returned collection is non-null and has size zero | Service methods that return null on empty cause NullPointerException in the controller when it tries to serialize the response |
| E48 | Delete non-existent ID raises no error (idempotent delete) | Calling delete with an ID that does not exist in the repository does not throw any exception | No exception is raised; the delete completes silently | Idempotent delete is the REST standard for DELETE; if delete throws on non-existent ID, clients must always do a GET-before-DELETE which doubles the request count |
| E49 | Delete with null/None/nil event publisher does not crash | When the event publisher dependency is null/None/nil, calling delete does not throw a NullPointerException/nil dereference | No null-pointer exception is raised | Event publisher may be optional or conditionally wired; the service must guard against null publisher to maintain delete functionality in environments where caching is disabled |
| E50 | Sort argument validated exactly: correct direction and field name | The sort argument passed to the repository specifies both ASC direction AND the id field — not just any sort | Argument captor captures the sort specification; assert direction=ASC and property=id (not name, not created_at) | A sort on the wrong field (e.g., name instead of id) gives alphabetical instead of insertion-order results; a sort on id DESC reverses the expected order; both cause pagination bugs |

---

## Layer 5: Entity / Model

**Applicable To:** Every microservice that has a persistence entity, domain model, or data
class with fields, constructors, getters/setters, equality, hashing, and string representation.

**Isolation Principle:** No mocks required. Instantiate entities directly using constructors or
factory methods. Test all contracts through public methods only. Entity tests must complete in
under 1 ms each.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P51 | Parameterized constructor/factory sets all fields | After calling the constructor with specific values for all fields, each getter/property returns the value that was passed to the constructor | Each field accessor returns the corresponding constructor argument exactly | A constructor that silently drops a field (assigns null) causes the field to be missing in every entity created through that constructor |
| P52 | Default constructor creates a non-null instance | Calling the no-argument constructor produces a non-null/non-nil instance without throwing | Instance is non-null and is of the expected type | Many frameworks (JPA, Jackson, ORM hydration) require a no-argument constructor; if it throws, the framework silently falls back to other strategies or fails with an unhelpful error |
| P53 | All getters/properties return values set by corresponding setters | For each field, calling the setter with a value and then calling the getter returns that exact value | Getter return equals the value passed to the setter for every field | A getter that returns a hardcoded default instead of the field value causes all read operations to return incorrect data |
| P54 | Equality — two instances with same data are equal | Creating two entity instances with identical field values produces two instances where equals/== returns true | equals() or structural equality returns true; both instances are considered equivalent | Entity equality is used in Set deduplication, List.contains() checks, and cache hit comparisons; incorrect equals causes duplicates to appear in sets and misses in contains |
| P55 | Hash — equal objects produce the same hash code | Two instances that are equal (P54) produce the same hash code | hashCode() or equivalent produces the same value for both instances | Java HashMap, Python dict, Go map, and caching systems use hash codes for bucket selection; unequal hash codes for equal objects cause the objects to appear in different buckets and be treated as different entries |
| P56 | Equality — reflexive: object equals itself | An entity instance is equal to itself | equals(self, self) returns true | Reflexivity is a formal contract of the equals/equality relation; violating it causes bugs in every data structure that uses equals for membership testing |
| P57 | String representation — not null or empty | Calling the string representation method/operator produces a non-null, non-empty string | toString() / __str__ / String() returns a non-null, non-empty string | Null or empty string representations cause log messages to be useless for debugging ("null" or "" instead of the entity's identity) |
| P58 | String representation — contains the type or class name | The string representation includes the entity type name | Returned string contains the class/struct name (e.g., "Category", "Product") | Type-prefixed string representations are essential for debugging across polyglot log aggregation where the JSON type field may be missing |
| P59 | String representation — contains field values | The string representation includes at least the ID and name field values | Returned string contains the entity's ID and name values | A representation that omits all field values (just the class name) is useless for debugging; at minimum ID and name are needed to identify the specific instance |
| P60 | Serialization — entity can be serialized to JSON or binary | Serializing the entity to JSON (or the language's native binary format) and deserializing it produces an equivalent instance | Serialized → deserialized instance equals the original; all fields are preserved | Serialization failures are common causes of 500 errors in production; testing at the entity level identifies the failure earlier than at the API layer |
| P61 | Serialization version field exists where applicable | If the entity uses versioned serialization (serialVersionUID in Java, version in protobuf), the version field is explicitly declared | Version field is present and has the expected value | Missing serialization version causes incompatibility errors when entity classes change and old serialized data is read from cache or message queues |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N62 | Equality — different IDs means not equal | Two entity instances with different IDs but otherwise identical fields are not equal | equals() or structural equality returns false when IDs differ | Entity identity is defined by ID; ignoring ID in equals creates a system where two different database rows appear to be the same object, causing incorrect cache hits and Set deduplication errors |
| N63 | Equality — comparison to null/None/nil returns false, no crash | Calling equals with null/None/nil as the argument returns false without throwing | equals(entity, null) returns false; no NullPointerException or nil panic | Java's Object.equals() contract requires null-safety; Go and Python have similar conventions; violating this causes crashes in collection operations that pass null for comparison |
| N64 | Equality — comparison to a different type returns false | Comparing an entity to an object of a different type returns false without throwing | equals(entity, "string") or equals(entity, 42L) returns false | Collections that contain mixed types use equals for element lookup; an entity that incorrectly claims equality to a String causes incorrect membership results |
| N65 | Constructor with null/None/nil name does not crash | Creating an entity with null/None/nil passed as the name argument does not throw in the constructor | No NullPointerException, nil panic, or validation error is raised by the constructor | Constructors should not validate; validation is the form/validator layer's responsibility; a throwing constructor breaks ORMs that hydrate entities field-by-field through reflection |
| N66 | Constructor with null/None/nil path does not crash | Creating an entity with null/None/nil passed as the path argument does not throw in the constructor | No NullPointerException or nil panic is raised by the constructor | Same rationale as N65; ORM hydration, JSON deserialization, and copy utilities all create instances with null fields during intermediate states |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E67 | Boundary — name at exactly maximum allowed length | An entity created with a name of exactly the maximum allowed character length (e.g., 255 characters) is stored and retrieved without truncation or error | Name field value equals the input string; no length-related error is raised | Databases and validators often enforce a strict maximum; a name of 255 characters must be accepted, while 256 must be rejected; this boundary test verifies the inclusive boundary |
| E68 | Boundary — path at exactly maximum allowed length | An entity created with a path of exactly the maximum allowed character length is stored and retrieved without truncation or error | Path field value equals the input string of maximum length | Same rationale as E67 applied to the path field; path fields often have shorter maximums due to URL length limits |
| E69 | Boundary — maximum integer/long ID value does not overflow | Setting the entity's ID to the maximum value for the platform's integer type (Long.MAX_VALUE, math.MaxInt64) does not cause overflow or incorrect serialization | ID field stores and retrieves the maximum integer value correctly | IDs near the maximum value are reached in high-volume systems; overflow causes IDs to wrap to negative or zero, breaking sort order and uniqueness |
| E70 | Boundary — minimum valid ID value (1) is accepted | Setting the entity's ID to 1 (the minimum valid positive integer ID) produces a valid entity | ID field stores and retrieves the value 1 without error | Some validation rules accidentally reject ID=1 with an "ID must be greater than 1" check instead of "ID must be positive"; this test ensures ID=1 is explicitly valid |
| E71 | Special characters in name stored and retrieved exactly | An entity with a name containing special characters (Unicode, emoji, apostrophes, slashes, HTML-like characters) stores the value and retrieves it without modification | Retrieved name equals the stored name character-for-character; no escaping, encoding, or truncation is applied | Incorrect HTML encoding, Unicode normalization, or charset mismatches can silently corrupt names; this test catches the corruption at the entity layer |
| E72 | Whitespace-only string stored without transformation | An entity with a name consisting entirely of whitespace characters (spaces, tabs) stores the value and retrieves it without trimming | Retrieved name equals the whitespace-only input; no automatic trimming is applied | Automatic trimming in setters is a hidden side effect that violates the principle of least surprise; trimming should be explicit in the form/validator layer, not in the entity |
| E73 | Two instances with null/None/nil IDs and same data are equal | When two entities are created with null/None/nil ID and the same name and path, they compare as equal | equals() returns true for two null-ID instances with identical non-ID fields | JPA and similar ORMs create entities with null IDs before persistence; two pre-persist instances with the same data should be treated as the same logical entity in Set-based deduplication |

---

## Layer 6: Error / Exception Handler

**Applicable To:** Every microservice that has a centralized error-handling mechanism (Spring
Boot @ControllerAdvice, FastAPI exception_handler, Express error middleware, Go error-returning
handler pattern) that maps domain exceptions to HTTP error responses.

**Isolation Principle:** Instantiate the handler directly with no mocks. Call handler methods
with pre-constructed exception instances. Verify the response body structure and HTTP status
code. No framework or Spring context required.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P74 | Duplicate-name error maps to conflict response with correct structure | When the handler receives a duplicate-name exception, it returns a response with success=false, a 409 status code, and a non-blank message | success is false; HTTP status code field equals 409; message is non-blank and non-null; data field is null | If the handler returns 200 instead of 409 for a conflict, clients interpret the response as success and do not display the duplicate-name error to the user |
| P75 | Duplicate-path error maps to conflict response with same structure | When the handler receives a duplicate-path exception, it returns a response with success=false, 409 status, and non-blank message | Same structure as P74; both duplicate exceptions must produce the same response shape | Inconsistent error response shapes for different exception types break clients that use a single error-parsing code path |
| P76 | Data integrity / constraint error maps to conflict response with non-leaking message | When the handler receives a data integrity exception (from the ORM or database layer), it returns a 409 response with a user-friendly message that does not expose SQL or internal details | Response message does not contain SQL keywords, table names, column names, or stack trace fragments | Database constraint violation messages from JDBC/GORM/SQLAlchemy contain table and column names; exposing these in the API response leaks the database schema to attackers |
| P77 | HTTP status code in response header matches status field in response body | For every exception handler method, the HTTP status in the ResponseEntity/HTTPResponse header equals the integer status field in the response body wrapper | ResponseEntity.getStatusCodeValue() == response.getBody().getStatus() (or equivalent) | Mismatched status codes cause client-side bugs where the network layer sees 409 but the body parser sees 200, leading to inconsistent error handling |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N78 | Duplicate-name handler explicitly sets success=false | The duplicate-name error handler method explicitly assigns false to the success field, not null or a default | success field is boolean false, not null, not true, not absent | A null success field is treated as false in some clients but throws NullPointerException in typed clients; explicit false is the only safe value |
| N79 | Duplicate-path handler explicitly sets success=false | The duplicate-path error handler method explicitly assigns false to the success field | success field is boolean false, not null, not true, not absent | Same rationale as N78 |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E80 | All conflict-class handlers return identical HTTP status code | Every handler method that handles a conflict-category exception (duplicate name, duplicate path, data integrity) returns the same HTTP status code (409) | All conflict handlers return status 409; no conflict handler returns 400 or 500 | Inconsistent status codes for the same semantic situation (conflict) require clients to handle multiple codes for the same condition; standardizing on 409 allows a single conflict-handling code path |
| E81 | All conflict-class handlers return success=false consistently | Every handler method that handles a conflict-category exception sets success=false in the response body | All conflict handlers set success to boolean false | A single handler that returns success=true for a conflict exception breaks the client's ability to detect failure through the wrapper's success flag |

---

## Layer 7: Input Validation

**Applicable To:** Every microservice that has form objects, request DTOs, or input models
with validation constraints (not-null, not-blank, size limits).

**Isolation Principle:** Use the validation framework's validator factory directly. Build the
validator once per test class for performance. Execute validation against constructed form
instances. Assert on violation counts and violation field paths. No mocks, no HTTP, no Spring context.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P82 | Valid input produces zero violations | A form/DTO constructed with a valid name and valid path produces zero constraint violations | Violation set size equals 0 | The happy-path validation test confirms the validator is wired correctly and does not block valid input |
| P83 | Minimum valid length (1 character) produces zero violations | A form/DTO with a single-character name and single-character path produces zero violations | Violation set size equals 0 | Minimum boundary validation ensures the @NotBlank or @Size(min=1) constraint is correctly inclusive at 1; a constraint that rejects 1 character blocks legitimate single-character names |
| P84 | Maximum valid name length produces zero violations | A form/DTO with a name of exactly the maximum allowed length (e.g., 255 characters) produces zero violations | Violation set size equals 0 for a name at the exact maximum length | Verifies the @Size(max=255) constraint is inclusive at 255; off-by-one errors (max=254 when the spec says 255) are caught here |
| P85 | Maximum valid path length produces zero violations | A form/DTO with a path of exactly the maximum allowed length produces zero violations | Violation set size equals 0 for a path at the exact maximum length | Same rationale as P84 applied to the path field; path and name may have different maximums |
| P86 | Special characters in input produce zero violations | A form/DTO with a name containing valid special characters (hyphens, underscores, Unicode) produces zero violations | Violation set size equals 0 | Validation constraints must not accidentally reject special characters that are permitted by the business rules (e.g., product names with hyphens, international characters) |
| P87 | Numeric characters in input produce zero violations | A form/DTO with a name consisting entirely of digit characters (e.g., "12345") produces zero violations | Violation set size equals 0 | Validation must not confuse "numeric-looking string" with "number type"; a name like "123" is a valid string name |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N88 | Null/None/undefined name produces a required-field violation on "name" | A form/DTO with a null name field produces at least one violation where the property path identifies the "name" field | Violation set contains a violation with property path "name"; violation count is at least 1 | The property path on the violation is what the API returns to the client; a violation on "form" instead of "name" produces an unhelpful error message |
| N89 | Empty string name produces a non-empty violation on "name" | A form/DTO with an empty string ("") name produces a violation indicating non-empty requirement | Violation with property path "name" is present; violation message references emptiness | @NotEmpty and @NotBlank have different semantics; this test ensures the correct constraint is applied |
| N90 | Whitespace-only name produces a non-blank violation on "name" | A form/DTO with a whitespace-only name ("   ") produces a violation indicating non-blank requirement | Violation with property path "name" is present; constraint is @NotBlank or equivalent | @NotBlank (not only whitespace) differs from @NotEmpty (non-zero length); a whitespace-only name must be rejected |
| N91 | Name exceeding max length by exactly 1 character produces a length violation | A form/DTO with a name of max_length + 1 characters produces a size/length violation on "name" | Violation with property path "name" is present; violation references size constraint; max + 1 is the minimum rejection boundary | Off-by-one boundary testing for the upper limit; confirms the exclusive upper boundary is max_length + 1 |
| N92 | Name far exceeding max length (2x) produces a length violation | A form/DTO with a name of max_length * 2 characters produces a size/length violation on "name" | Violation with property path "name" is present; confirms violation is not absorbed or ignored for large inputs | Validators must not truncate input to max_length and silently accept it; they must reject any input that exceeds the maximum |
| N93 | Null/None/undefined path produces a required-field violation on "path" | A form/DTO with a null path field produces at least one violation where the property path identifies the "path" field | Violation set contains a violation with property path "path" | Path and name have independent required-field constraints; this test verifies path's constraint is wired separately from name's |
| N94 | Empty string path produces a non-empty violation on "path" | A form/DTO with an empty string ("") path produces a violation on "path" | Violation with property path "path" is present | Same rationale as N89 applied to the path field |
| N95 | Whitespace-only path (tabs) produces a non-blank violation on "path" | A form/DTO with a tab-only path ("\t\t") produces a non-blank violation on "path" | Violation with property path "path" is present | Tab characters are whitespace; @NotBlank must reject them; this test uses tabs instead of spaces to verify the constraint handles all whitespace variants |
| N96 | Path exceeding max length produces a length violation | A form/DTO with a path exceeding the maximum allowed length produces a size/length violation on "path" | Violation with property path "path" is present; violation references size constraint | Same rationale as N91 applied to the path field |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E97 | Both fields null produces exactly 2 violations, one per field | A form/DTO with both name and path set to null produces exactly 2 violations — one for "name" and one for "path" | Violation count equals 2; violation property paths are "name" and "path" respectively | If both fields share the same validation annotation instance (copy-paste error), nulling both may produce only 1 violation; this test catches the shared-annotation bug |
| E98 | Both fields empty produces at least 2 violations | A form/DTO with both name and path set to empty string ("") produces at least 2 violations | Violation count is at least 2; violations reference "name" and "path" | At least 2 ensures both fields are independently validated; it allows for additional cross-field violations if present |
| E99 | Both fields whitespace produces at least 2 violations | A form/DTO with both name and path set to whitespace-only values produces at least 2 violations | Violation count is at least 2 | Same rationale as E98 for whitespace-only inputs |
| E100 | Both fields exceeding max length produces exactly 2 length violations | A form/DTO with both name and path exceeding their respective maximums produces exactly 2 length violations | Violation count equals 2; both violations reference the size constraint on their respective field | Exactly 2 ensures size violations on one field do not incorrectly appear as violations on the other field |
| E101 | Validation priority: required-field violation fires before length violation, not both simultaneously | When a field is null, only a required-field violation is produced, not a length violation in addition | Violation count for a null field is 1 (required), not 2 (required + length) | Some validation frameworks apply all constraints to null simultaneously; the correct behavior is to short-circuit at the required constraint so the user receives one actionable message, not two conflicting messages |

---

## Layer 8: Event / Message Publisher

**Applicable To:** Every microservice that publishes domain events (cache invalidation events,
audit events, integration events) through a message broker, Redis pub/sub, AMQP, or Kafka.

**Isolation Principle:** Mock the message broker client (RedisTemplate, redis.client, ioredis,
go-redis). Instantiate the publisher with the mock injected. Call publisher methods. Use argument
captors or mock call inspection to verify the published event's type, channel, and entity reference.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| P102 | CREATE event contains correct entity type with null entity ID | When the publisher's create-event method is called, the published event payload contains the entity type name and a null/zero entity ID | Published event contains: type=CREATE, entityType=[expected type name], entityId=null/zero | CREATE events are published before persistence completes (the entity has no ID yet); publishing with a non-null ID indicates the event is published after persist (which is still acceptable) or that a stale ID from a previous operation leaked |
| P103 | CREATE event entity ID is null (not yet persisted) | The entity ID in the CREATE event payload is null or zero at the time of publication | entityId field in the published event is null or zero | Some implementations accidentally set the entity ID on the event from a previous operation; null/zero confirms the event is correctly representing a pre-persist state |
| P104 | UPDATE event contains correct entity type AND populated entity ID | When the publisher's update-event method is called with a specific entity ID, the published event contains the entity type and that exact non-null, non-zero entity ID | Published event contains: type=UPDATE, entityType=[expected type], entityId=[the provided ID], where entityId > 0 | UPDATE events must carry the ID so the cache consumer knows which specific entry to invalidate; an event with a null or wrong ID causes incorrect cache entries to survive |
| P105 | DELETE event contains correct entity type AND populated entity ID | When the publisher's delete-event method is called with a specific entity ID, the published event contains the entity type and that exact non-null ID | Published event contains: type=DELETE, entityType=[expected type], entityId=[the provided ID] | Same rationale as P104; DELETE cache invalidation requires the specific ID of the deleted entry |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| N106 | UPDATE with non-existent ID still publishes the event | When the publisher's update-event method is called with an ID that may not exist in the repository, the event is published regardless | Broker mock receives exactly one publish call; no exception is thrown | The publisher must not validate entity existence before publishing; existence validation is the service layer's responsibility; the publisher is a dumb event forwarder |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| E107 | CREATE, UPDATE, DELETE events have structurally distinct event types | Three separate events — one CREATE, one UPDATE, one DELETE — each have a different value for their event-type field | Event type fields are distinct: CREATE != UPDATE, UPDATE != DELETE, CREATE != DELETE | If all three event types use the same string (e.g., all use "CACHE_EVENT"), the cache consumer cannot distinguish which operation occurred and applies the wrong invalidation strategy |

---

## Cross-Cutting Patterns (All Layers)

These seven patterns span multiple layers and must be enforced consistently across the entire
codebase. Each pattern, when broken in one layer, silently corrupts behavior in all consuming
layers. Test coverage for these patterns must exist in at least two layers per pattern.

**Pattern 1 — Response Wrapper Consistency**
**Spans:** Controller Layer (Layer 3) + Exception Handler Layer (Layer 6)
**Contract:** Every endpoint — success and error — returns the identical response wrapper structure.
The wrapper contains: a boolean success field, an integer status code field, a string message
field, and a typed data field. Success responses set success=true, status=2xx, message=non-blank,
data=non-null. Error responses set success=false, status=4xx/5xx, message=non-blank, data=null.
No endpoint returns a raw DTO on success while returning a wrapped error on failure.
**Why It Breaks Silently:** A client that parses the wrapper on the success path and receives a
raw DTO on the error path throws a deserialization exception at runtime rather than at
compile/test time. The exception manifests as a 500 from the client's perspective, not a clear
API contract violation.

**Pattern 2 — success=false on All Error Responses**
**Spans:** Controller Layer (Layer 3) + Exception Handler Layer (Layer 6)
**Contract:** Every handler that processes an exception must explicitly set success=false on
the response wrapper. The field must be boolean false, not null, not absent, not a default.
**Why It Breaks Silently:** Clients use the success field as the primary pass/fail signal before
reading the status code. A null success field (which serializes to false in some languages but
throws NullPointerException in others) causes inconsistent behavior across different client
implementations for the same API.

**Pattern 3 — HTTP Status Matches Body Status Field**
**Spans:** Controller Layer (Layer 3) + Exception Handler Layer (Layer 6)
**Contract:** The HTTP status code in the response header (ResponseEntity status, res.status(),
http.StatusCode) must equal the integer status field in the response body wrapper for every
response — success and error.
**Why It Breaks Silently:** HTTP middlewares, API gateways, and load balancers use the HTTP
status code to route, retry, and log requests. If the HTTP status is 200 but the body says 409,
the gateway logs a success while the client sees an error. The mismatch causes retry logic to
not retry errors it should retry and to retry successes it should not.

**Pattern 4 — Case-Insensitive Duplicate Detection**
**Spans:** Service Layer (Layer 4)
**Contract:** Duplicate-name and duplicate-path checks must be case-insensitive. A name "Admin"
must be rejected when "admin" already exists. The service layer must normalize case (lowercase
or uppercase) before querying for existence.
**Why It Breaks Silently:** Case-sensitive duplicate checks allow "Admin" and "admin" to coexist
in the database. The resulting data inconsistency is invisible until a user searches for "admin"
and receives two results, or until a migration query expecting unique names fails.

**Pattern 5 — Idempotent Delete**
**Spans:** Service Layer (Layer 4)
**Contract:** Deleting a resource that does not exist must complete without error. The delete
operation is a statement of intent ("this resource should not exist") rather than a query about
current state. Throwing an error on delete-of-non-existent breaks client retry logic.
**Why It Breaks Silently:** When a network partition causes a client to retry a delete request,
the second delete arrives after the first has already removed the resource. A non-idempotent
delete throws on the second call, causing the client to interpret a successful deletion as an
error. The resource is deleted but the client believes the operation failed.

**Pattern 6 — Sort Validation with Exact Field and Direction**
**Spans:** Service Layer (Layer 4)
**Contract:** Tests for sort behavior must assert both the sort direction (ASC/DESC) and the
sort field name (id, createdAt, name). Asserting only "some sort was applied" is insufficient.
Asserting only the direction without the field name allows sorting by the wrong field.
**Why It Breaks Silently:** A service that sorts by name instead of id produces alphabetical
ordering instead of insertion-order. Pagination clients that rely on consistent ID-based ordering
to avoid duplicate or missing items will see non-deterministic gaps when sorted by name.

**Pattern 7 — Cache Event Coverage for CREATE, UPDATE, DELETE**
**Spans:** Service Layer (Layer 4) + Event Publisher Layer (Layer 8)
**Contract:** All three mutation operations — CREATE, UPDATE, DELETE — must publish cache
invalidation events. Missing a CREATE event allows the collection cache to serve stale data
that excludes the new entity. Missing an UPDATE event serves the pre-update entity from cache.
Missing a DELETE event serves the deleted entity from cache.
**Why It Breaks Silently:** Cache staleness is not an error condition; the service returns 200
with stale data. The bug only manifests as data inconsistency that is discovered by users
comparing what they see in the UI with what exists in the database.

---

## Mocking Strategy Reference (Abstract)

| Layer | What To Mock | What NOT To Mock | Why |
|-------|-------------|-----------------|-----|
| Layer 1 — Bootstrap | The framework's static startup call (SpringApplication.run, uvicorn.run, app.listen, http.ListenAndServe) | The entry-point class itself; its constructor; any configuration constants | Mocking the static call prevents a real framework context from starting while still verifying the entry-point delegates correctly |
| Layer 2 — Configuration | Nothing | The configuration class itself; constant fields | Configuration classes have no dependencies to mock; they are tested by direct instantiation and field inspection |
| Layer 3 — Controller | The service layer (all public methods the controller calls) | The HTTP framework/server; middleware; serialization | The controller's job is to receive input, delegate to service, and return a response; mocking the service tests only this delegation contract without network overhead |
| Layer 4 — Service | The repository layer; the event publisher | The service itself; domain entities; validation logic inside the service | The service's job is business logic orchestration; mocking repository and publisher isolates business logic from persistence and messaging |
| Layer 5 — Entity | Nothing | The entity's own constructors or methods | Entities are plain data objects; they have no external dependencies to mock; all behavior is tested through direct instantiation |
| Layer 6 — Exception Handler | Nothing (no mocks required) | The exception classes themselves; the response wrapper constructor | Exception handlers are pure transformation functions that map exception instances to response objects; they have no dependencies |
| Layer 7 — Validation | Nothing | The validation framework itself; the form class | The validation framework (Hibernate Validator, Pydantic, Zod, go-playground/validator) is real; only the form instance is constructed by the test |
| Layer 8 — Event Publisher | The message broker client (RedisTemplate, redis.client, go-redis client) | The event payload class; the publisher itself (it is the system under test) | The publisher's job is to construct an event payload and forward it to the broker; mocking the broker tests the event construction and routing logic |

---

## Quick-Reference Checklist

For every new service or service module, verify each item before marking the feature complete:

Bootstrap Layer:
- [ ] P1: Entry-point annotation/decorator present
- [ ] P2: Service discovery annotation present (if applicable)
- [ ] P3: Transaction management annotation present (if applicable)
- [ ] P4: Entry-point function has correct signature
- [ ] P5: Entry-point delegates to framework startup
- [ ] P6: Entry-point forwards all CLI arguments
- [ ] P7: Entry-point has expected constructor structure
- [ ] P8: Entry-point has no unexpected superclass
- [ ] N9: Null/None/nil args do not crash
- [ ] N10: Empty args still invoke framework startup
- [ ] E11: Multiple CLI flags all forwarded

Configuration Layer:
- [ ] P12: Config instantiates without error
- [ ] P13: Single-entity cache name constant correct
- [ ] P14: Collection cache name constant correct
- [ ] P15: Count cache name constant correct
- [ ] N16: No constant is null or empty
- [ ] E17: All constants are distinct

Controller Layer:
- [ ] P18: POST returns 201 with body
- [ ] P19: PUT returns 200 with updated body
- [ ] P20: GET by ID returns 200 with single resource
- [ ] P21: GET all returns 200 with ordered collection
- [ ] P22: DELETE returns 200 or 204
- [ ] P23: GET count returns 200 with numeric value
- [ ] N24: Duplicate name propagates 409
- [ ] N25: Duplicate path propagates 409
- [ ] N26: Non-existent ID on GET propagates 404
- [ ] N27: Non-existent ID on PUT propagates 404
- [ ] E28: Empty data returns empty collection, not null
- [ ] E29: GET all preserves ordered collection type
- [ ] E30: Service invoked exactly once per request

Service Layer:
- [ ] P31: Add returns populated DTO
- [ ] P32: Update returns updated DTO
- [ ] P33: Get by ID maps all fields
- [ ] P34: Get all passes sort-by-ID-ASC to repository
- [ ] P35: Get all returns items in ID-ascending order
- [ ] P36: Delete publishes DELETE cache event
- [ ] P37: Count returns non-zero correctly
- [ ] P38: Count returns zero for empty
- [ ] P39: Idempotent update with identical data succeeds
- [ ] N40: Duplicate name throws typed exception
- [ ] N41: Duplicate path throws typed exception
- [ ] N42: Non-existent ID on get throws typed exception
- [ ] N43: Non-existent ID on update throws typed exception
- [ ] N44: Name taken by other resource throws exception (self-excluded)
- [ ] N45: Path taken by other resource throws exception (self-excluded)
- [ ] E46: Case-insensitive duplicate detection
- [ ] E47: Empty repository returns empty collection, not null
- [ ] E48: Delete of non-existent ID is idempotent
- [ ] E49: Null event publisher does not crash delete
- [ ] E50: Sort validated with exact direction and field name

Entity Layer:
- [ ] P51: Parameterized constructor sets all fields
- [ ] P52: Default constructor creates non-null instance
- [ ] P53: All getters return values set by setters
- [ ] P54: Same data equals
- [ ] P55: Equal objects have same hash
- [ ] P56: Object equals itself (reflexive)
- [ ] P57: String representation is non-null and non-empty
- [ ] P58: String representation contains type name
- [ ] P59: String representation contains field values
- [ ] P60: Entity serializes and deserializes correctly
- [ ] P61: Serialization version field declared (if applicable)
- [ ] N62: Different IDs means not equal
- [ ] N63: Null comparison returns false, no crash
- [ ] N64: Different type comparison returns false
- [ ] N65: Null name constructor does not crash
- [ ] N66: Null path constructor does not crash
- [ ] E67: Name at max length accepted
- [ ] E68: Path at max length accepted
- [ ] E69: Max integer ID does not overflow
- [ ] E70: ID=1 is valid
- [ ] E71: Special characters stored exactly
- [ ] E72: Whitespace-only string stored without trimming
- [ ] E73: Two null-ID instances with same data are equal

Error Handler Layer:
- [ ] P74: Duplicate-name maps to 409 with correct structure
- [ ] P75: Duplicate-path maps to 409 with correct structure
- [ ] P76: Data integrity error maps to 409 with non-leaking message
- [ ] P77: HTTP status matches body status field
- [ ] N78: Duplicate-name handler sets success=false explicitly
- [ ] N79: Duplicate-path handler sets success=false explicitly
- [ ] E80: All conflict handlers return 409
- [ ] E81: All conflict handlers set success=false

Validation Layer:
- [ ] P82: Valid input produces zero violations
- [ ] P83: Single-character minimum valid
- [ ] P84: Max name length accepted
- [ ] P85: Max path length accepted
- [ ] P86: Special characters valid
- [ ] P87: Numeric string name valid
- [ ] N88: Null name → required violation on "name" field
- [ ] N89: Empty name → non-empty violation
- [ ] N90: Whitespace-only name → non-blank violation
- [ ] N91: Name max+1 characters → length violation
- [ ] N92: Name at 2x max → length violation
- [ ] N93: Null path → required violation on "path" field
- [ ] N94: Empty path → non-empty violation
- [ ] N95: Tab-only path → non-blank violation
- [ ] N96: Path exceeds max → length violation
- [ ] E97: Both null → exactly 2 violations
- [ ] E98: Both empty → at least 2 violations
- [ ] E99: Both whitespace → at least 2 violations
- [ ] E100: Both over max → exactly 2 length violations
- [ ] E101: Null triggers required (not required + length simultaneously)

Event Publisher Layer:
- [ ] P102: CREATE event has correct type and null entity ID
- [ ] P103: CREATE event entity ID is null
- [ ] P104: UPDATE event has correct type and populated entity ID
- [ ] P105: DELETE event has correct type and populated entity ID
- [ ] N106: UPDATE with non-existent ID still publishes event
- [ ] E107: CREATE, UPDATE, DELETE event types are structurally distinct

Cross-Cutting Patterns:
- [ ] Pattern 1: Response wrapper consistent between controller and handler
- [ ] Pattern 2: success=false on all error responses
- [ ] Pattern 3: HTTP status matches body status field
- [ ] Pattern 4: Case-insensitive duplicate detection in service
- [ ] Pattern 5: Idempotent delete in service
- [ ] Pattern 6: Sort validated with exact field and direction
- [ ] Pattern 7: Cache events for CREATE, UPDATE, and DELETE

---

## Final Count Summary

| Category | Count |
|----------|-------|
| Positive | 44 |
| Negative | 35 |
| Edge Case | 31 |
| Cross-Cutting Patterns | 7 |
| **Total Scenarios** | **110 core + 7 cross-cutting** |
| **Total with Cross-Cutting** | **117** |

**Breakdown by Layer:**

| Layer | Positive | Negative | Edge | Total |
|-------|----------|----------|------|-------|
| Layer 1 — Bootstrap | P1–P8 (8) | N9–N10 (2) | E11 (1) | 11 |
| Layer 2 — Configuration | P12–P15 (4) | N16 (1) | E17 (1) | 6 |
| Layer 3 — Controller | P18–P23 (6) | N24–N27 (4) | E28–E30 (3) | 13 |
| Layer 4 — Service | P31–P39 (9) | N40–N45 (6) | E46–E50 (5) | 20 |
| Layer 5 — Entity | P51–P61 (11) | N62–N66 (5) | E67–E73 (7) | 23 |
| Layer 6 — Error Handler | P74–P77 (4) | N78–N79 (2) | E80–E81 (2) | 8 |
| Layer 7 — Validation | P82–P87 (6) | N88–N96 (9) | E97–E101 (5) | 20 |
| Layer 8 — Event Publisher | P102–P105 (4) | N106 (1) | E107 (1) | 6 |
| Layer 9 — Security | SEC1–SEC2 (2) | SEC3–SEC6 (4) | SEC7–SEC8 (2) | 8 |
| Layer 10 — Path Parameters | — | PP1 (1) | PP2–PP4 (3) | 4 |
| Layer 11 — Error Structure | — | ERR1–ERR2 (2) | ERR3 (1) | 3 |
| **Total** | **54** | **37** | **31** | **122** |

---

## Layer ID Ranges

| Layer | ID Range | Count | Notes |
|-------|----------|-------|-------|
| 1 — Bootstrap | P1–P8, N9–N10, E11 | 11 | |
| 2 — Configuration | P12–P15, N16, E17 | 6 | |
| 3 — Controller/Handler | P18–P23, N24–N27, E28–E30 | 13 | |
| 4 — Service | P31–P39, N40–N45, E46–E50 | 20 | |
| 5 — Entity/Model | P51–P61, N62–N66, E67–E73 | 23 | |
| 6 — Error Handler | P74–P77, N78–N79, E80–E81 | 8 | |
| 7 — Validation | P82–P87, N88–N96, E97–E101 | 20 | |
| 8 — Event Publisher | P102–P105, N106, E107 | 6 | |
| **9 — Security** | **SEC1–SEC8** | **8** | **NEW** |
| **10 — Path Parameters** | **PP1–PP4** | **4** | **NEW** |
| **11 — Error Structure** | **ERR1–ERR3** | **3** | **NEW** |
| **Total** | | **122** | Was 107, added 15 |

Gaps in numbering (e.g., P8→P12, P15→P18) are intentional layer-boundary reservations.

---

## Layer 9: Security Tests (SEC1–SEC8)

**Applicable To:** Every REST service exposed to untrusted input (public APIs, mobile backends, SPAs).
**Isolation Principle:** Use the HTTP test client (supertest/TestClient/httptest) to send malicious payloads. Assert the response status code and verify no internal details leak.

### Positive Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| SEC1 | Authenticated request to protected endpoint succeeds | Valid auth token → 200 OK | Response status 200, body has expected data | Every app with auth needs this baseline |
| SEC2 | Health/readiness endpoints are publicly accessible without auth | GET /health → 200 without token | No 401 on unauthenticated health check | Kubernetes probes fail without this |

### Negative Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| SEC3 | Unauthenticated request to protected endpoint returns 401 | No token → 401 Unauthorized | Status 401, body success=false, no data leaked | Fundamental auth contract |
| SEC4 | Expired/invalid token returns 401, not 403 or 500 | Malformed JWT → 401 | Status 401, error message does not contain stack trace | Token validation is present in every secured app |
| SEC5 | SQL injection in name field returns 400/422, not 500 | name=`'; DROP TABLE resources; --` → 400 | No 500 Internal Server Error, no SQL error in response | Prevents info disclosure via DB errors |
| SEC6 | XSS payload in name field is handled safely | name=`<script>alert(1)</script>` → stored verbatim or rejected 422 | Response does not execute or reflect unescaped HTML | Every web API processes user strings |

### Edge Case Scenarios

| ID | Scenario | What To Verify | Assertion Target (Generic) | Universality |
|----|----------|---------------|---------------------------|--------------|
| SEC7 | Oversized request body returns 413 or 400, not 500 | POST with 10MB JSON body → 413/400 | No OOM crash, no 500, correct status code | Every API has a body size limit |
| SEC8 | Missing Content-Type header returns 415 or 400, not 500 | POST without Content-Type → 415/400 | Graceful rejection, not a parsing crash | Malformed requests are common in the wild |

---

## Additional Scenarios: Path Parameters (PP1–PP4)

**Applicable To:** Every REST endpoint that accepts path parameters (e.g., GET /resources/{id}).
**Isolation Principle:** Send malformed path parameters via HTTP test client.

| ID | Type | Scenario | What To Verify | Assertion Target |
|----|------|----------|---------------|-----------------|
| PP1 | Negative | Non-numeric ID in path (GET /resources/abc) | Returns 400, not 500 | No NumberFormatException/ValueError in response body |
| PP2 | Edge | Negative integer ID (GET /resources/-1) | Returns 400 or 404, not 500 | Graceful handling, not a crash |
| PP3 | Edge | Zero ID (GET /resources/0) | Returns 400 or 404, not 500 | Zero is not a valid auto-generated ID |
| PP4 | Edge | Very large ID beyond integer range (GET /resources/99999999999999999999) | Returns 400, not 500 | No integer overflow crash |

## Additional Scenarios: Internal Error Structure (ERR1–ERR3)

**Applicable To:** Every REST service that can encounter unexpected errors.
**Isolation Principle:** Force a 500 error via mocked dependency failure.

| ID | Type | Scenario | What To Verify | Assertion Target |
|----|------|----------|---------------|-----------------|
| ERR1 | Negative | Unhandled exception produces structured error response | 500 response uses ApiResponse envelope with success=false | No naked exception trace in response body |
| ERR2 | Negative | Error response does not leak stack trace | 500 body.message is generic (e.g., "Internal Server Error") | No file paths, line numbers, or class names in message |
| ERR3 | Edge | Error response Content-Type is application/json | Even 500 errors return JSON, not text/html | Clients parsing JSON don't get unexpected HTML error pages |

---

## Derived Language Files

| File | Language / Framework | Status | Derives From |
|------|---------------------|--------|--------------|
| 35-positive-testing-standards.md | Java / Spring Boot | Complete | P-series scenarios from this abstract |
| 36-negative-testing-standards.md | Java / Spring Boot | Complete | N-series scenarios from this abstract |
| 37-edge-case-testing-standards.md | Java / Spring Boot | Complete | E-series scenarios from this abstract |
| 38-test-mocking-strategy.md | Java / Spring Boot | Complete | Mocking Strategy Reference from this abstract |
| 39-cross-cutting-test-patterns.md | Java / Spring Boot | Complete | Cross-Cutting Patterns section from this abstract |
| 41-testing-standards-python-fastapi.md | Python / FastAPI | Derived from this abstract | All 107 scenarios + 7 cross-cutting |
| 42-testing-standards-nodejs-express.md | Node.js / TypeScript / Express | Derived from this abstract | All 107 scenarios + 7 cross-cutting |
| 43-testing-standards-go.md | Go / net/http or Gin | Derived from this abstract | All 107 scenarios + 7 cross-cutting |

---

## See Also

- **35-positive-testing-standards.md** — Java/Spring Boot positive scenario implementations (P1–P61, P74–P77, P82–P87, P102–P105)
- **36-negative-testing-standards.md** — Java/Spring Boot negative scenario implementations (N9–N10, N16, N24–N27, N40–N45, N62–N66, N78–N79, N88–N96, N106)
- **37-edge-case-testing-standards.md** — Java/Spring Boot edge case implementations (E11, E17, E28–E30, E46–E50, E67–E73, E80–E81, E97–E101, E107)
- **38-test-mocking-strategy.md** — Java/Spring Boot per-layer mocking strategies with code examples
- **39-cross-cutting-test-patterns.md** — Java/Spring Boot cross-cutting pattern test implementations
- **41-testing-standards-python-fastapi.md** — Python/FastAPI implementation of all scenarios
- **42-testing-standards-nodejs-express.md** — Node.js/TypeScript/Express implementation of all scenarios
- **43-testing-standards-go.md** — Go implementation of all scenarios
