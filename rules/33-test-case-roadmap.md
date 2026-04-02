---
description: "Level 2.2 - Universal test scenario roadmap: layer-by-layer checklist for any application"
paths:
  - "src/"
  - "tests/"
  - "test/"
  - "spec/"
  - "__tests__/"
priority: critical
conditional: "Any project with automated tests (language/framework agnostic)"
---

# Test Case Scenario Roadmap (Level 2.2 - Universal)

**PURPOSE:** Provide a layer-by-layer test scenario checklist that any engineer can apply to
any application regardless of language or framework. Each scenario is concrete, traceable to
a real pattern observed in production codebases, and carries an "Applicable when" condition
so the list serves as a roadmap rather than a mandate. Engineers select the scenarios that
match their system's features and skip those that do not apply.

**APPLIES WHEN:** Any project with automated tests. Scenarios within each section carry
individual applicability conditions. Review the roadmap at the start of every new feature,
and again during code review to catch untested behaviors before merge.

---

## 1. Application Entry Point Tests

Tests that verify the application bootstraps correctly, holds its required structural
contracts, and can be started without error. These tests catch regressions in class-level
declarations that no other layer will catch.

### 1.1 Entry Point Class Has Required Bootstrap Annotations

- **What it tests:** Confirms the main application class carries all annotations required
  for framework bootstrap (auto-configuration, service discovery, transaction management,
  etc.).
- **Applicable when:** The application has an explicit entry point class that aggregates
  framework-enabling annotations.
- **Priority:** HIGH
- **Example test name:** `test_applicationClass_should_haveBootstrapAnnotations_when_classIsLoaded`

### 1.2 Entry Point Class Is Public and Concrete

- **What it tests:** Confirms the entry point class is public, non-abstract, and not an
  interface so the runtime can instantiate it.
- **Applicable when:** The runtime requires instantiation of the entry point class.
- **Priority:** HIGH
- **Example test name:** `test_applicationClass_should_bePublicAndConcrete_when_reflectionIsUsed`

### 1.3 Entry Point Method Exists with Correct Signature

- **What it tests:** Confirms the application start method exists with the exact signature
  the runtime requires (correct return type, access modifiers, and parameter types).
- **Applicable when:** The language or framework mandates a specific signature for the
  application start method (e.g., `public static void main(String[])`).
- **Priority:** HIGH
- **Example test name:** `test_mainMethod_should_existWithCorrectSignature_when_classIsInspected`

### 1.4 Entry Point Method Delegates to Framework Runner

- **What it tests:** Confirms the start method delegates to the framework's application
  runner rather than implementing custom startup logic inline.
- **Applicable when:** The application uses a framework that provides a canonical run
  method (e.g., `SpringApplication.run`).
- **Priority:** MEDIUM
- **Example test name:** `test_mainMethod_should_invokeFrameworkRunner_when_calledWithArgs`

### 1.5 Entry Point Method Handles Absent Arguments

- **What it tests:** Confirms the start method does not throw when called with null, an
  empty argument array, or multiple arguments.
- **Applicable when:** The entry point method accepts command-line or startup arguments.
- **Priority:** MEDIUM
- **Example test name:** `test_mainMethod_should_notThrow_when_argsAreNullOrEmpty`

### 1.6 Entry Point Class Lives in the Correct Package

- **What it tests:** Confirms the entry point class resides in the root package so that
  component scanning, auto-wiring, or module resolution starts from the correct location.
- **Applicable when:** The framework resolves components based on the package of the entry
  point class.
- **Priority:** MEDIUM
- **Example test name:** `test_applicationClass_should_beInRootPackage_when_packageIsInspected`

---

## 2. Model / Domain Object Tests

Tests that verify the structural contracts of domain objects: construction, field access,
equality, serialization, and boundary values. These tests protect against regressions
introduced by generated code tools (Lombok, code generators) or schema changes.

### 2.1 Parameterized Constructor Sets All Fields

- **What it tests:** Confirms that when a model is created with a parameterized constructor,
  every supplied argument is stored in the corresponding field with no silent dropping.
- **Applicable when:** The model has a constructor that accepts field values directly.
- **Priority:** HIGH
- **Example test name:** `test_constructor_should_setAllFields_when_validParametersSupplied`

### 2.2 No-Args Constructor Produces Empty State

- **What it tests:** Confirms that the default no-argument constructor creates a model
  with all fields in their zero/null default state, not partially populated.
- **Applicable when:** The model has or requires a no-args constructor.
- **Priority:** HIGH
- **Example test name:** `test_noArgsConstructor_should_produceNullFields_when_called`

### 2.3 Getters and Setters Round-Trip Correctly

- **What it tests:** Confirms that each setter stores the value and the corresponding
  getter returns exactly that value with no transformation.
- **Applicable when:** The model exposes mutable fields through getters and setters.
- **Priority:** HIGH
- **Example test name:** `test_setter_should_storeValue_when_getterIsCalledAfterwards`

### 2.4 Equals Is Reflexive, Symmetric, and Transitive

- **What it tests:** Confirms the equality contract: an object equals itself, two objects
  with the same state are equal to each other, and a model is not equal to null or a
  different type.
- **Applicable when:** The model overrides equals (manually or via code generation).
- **Priority:** HIGH
- **Example test name:** `test_equals_should_returnTrue_when_twoObjectsHaveSameState`

### 2.5 Equal Objects Produce the Same Hash Code

- **What it tests:** Confirms that two objects that are equal under equals() return
  identical hash codes, preserving the hash code contract required for use in maps and sets.
- **Applicable when:** The model overrides hashCode.
- **Priority:** HIGH
- **Example test name:** `test_hashCode_should_beEqual_when_objectsAreEqual`

### 2.6 toString Contains Identifying Information

- **What it tests:** Confirms that toString returns a non-empty string that contains
  the class name and at least one meaningful field value to support debugging.
- **Applicable when:** The model overrides or auto-generates toString.
- **Priority:** LOW
- **Example test name:** `test_toString_should_containClassName_when_called`

### 2.7 Model Supports Serialization

- **What it tests:** Confirms the model implements the serialization interface required
  by caches, message brokers, or HTTP session stores that serialize objects.
- **Applicable when:** The model is stored in a distributed cache, sent over a message
  queue, or placed in an HTTP session.
- **Priority:** HIGH
- **Example test name:** `test_model_should_implementSerializable_when_checkedAtRuntime`

### 2.8 Field Accepts Maximum Allowed Length

- **What it tests:** Confirms a string field can hold a value of exactly the maximum
  defined length without truncation or error.
- **Applicable when:** The model documents or enforces a maximum field length (e.g., 50
  characters as defined in the category-service entity).
- **Priority:** MEDIUM
- **Example test name:** `test_setName_should_acceptValue_when_lengthEqualsMaximum`

### 2.9 Version / Optimistic Locking Field Is Initialized

- **What it tests:** Confirms that the version field used for optimistic locking has a
  defined initial value (typically 0 or null) after construction and is non-negative after
  a persist cycle.
- **Applicable when:** The model carries a version field for optimistic concurrency control.
- **Priority:** HIGH
- **Example test name:** `test_versionField_should_beInitialized_when_entityIsCreated`

---

## 3. Input Validation / Request Object Tests

Tests that verify the validation layer rejects bad input and propagates accurate error
messages. These scenarios were directly observed in the category-service `CategoryForm`
validation suite which uses ordered constraint groups (NotNull -> NotEmpty -> NotBlank ->
Length).

### 3.1 Valid Input Produces No Violations

- **What it tests:** Confirms that a properly populated request object with all fields
  within accepted ranges produces zero constraint violations.
- **Applicable when:** The request object carries field-level validation constraints.
- **Priority:** HIGH
- **Example test name:** `test_validation_should_produceNoViolations_when_allFieldsAreValid`

### 3.2 Null Field Produces Correct Null Violation Message

- **What it tests:** Confirms that submitting null for a required field produces exactly
  one violation with the expected "cannot be null" message on the correct property path.
- **Applicable when:** The request object has fields marked as not-null.
- **Priority:** HIGH
- **Example test name:** `test_validation_should_rejectNull_when_fieldIsMarkedNotNull`

### 3.3 Empty String Produces Correct Empty Violation Message

- **What it tests:** Confirms that submitting an empty string for a required field produces
  the expected "cannot be empty" message rather than falling through to a different error.
- **Applicable when:** The request object has fields marked as not-empty.
- **Priority:** HIGH
- **Example test name:** `test_validation_should_rejectEmpty_when_fieldIsMarkedNotEmpty`

### 3.4 Whitespace-Only String Produces Correct Blank Violation Message

- **What it tests:** Confirms that submitting a string of only spaces or tabs for a
  required field produces the expected "cannot be blank" message.
- **Applicable when:** The request object has fields marked as not-blank.
- **Priority:** HIGH
- **Example test name:** `test_validation_should_rejectBlankString_when_fieldIsMarkedNotBlank`

### 3.5 String Exceeding Maximum Length Produces Length Violation

- **What it tests:** Confirms that submitting a string one character longer than the
  maximum produces exactly one length violation with the correct message.
- **Applicable when:** The request object enforces maximum character length on a field
  (e.g., max 50 characters on name and path in the category form).
- **Priority:** HIGH
- **Example test name:** `test_validation_should_rejectString_when_lengthExceedsMaximum`

### 3.6 Single-Character String Satisfies Minimum Length

- **What it tests:** Confirms that the shortest allowed non-empty value (1 character)
  passes validation, establishing the lower boundary.
- **Applicable when:** The request object enforces a minimum character length.
- **Priority:** MEDIUM
- **Example test name:** `test_validation_should_accept_when_lengthEqualsMinimum`

### 3.7 Validation Groups Execute in the Defined Order

- **What it tests:** Confirms that when multiple violations would apply (e.g., a value
  is both null and too short), only the first group's violation is reported, not multiple
  conflicting messages simultaneously.
- **Applicable when:** The request object uses ordered validation groups or a validation
  sequence annotation.
- **Priority:** HIGH
- **Example test name:** `test_validation_should_reportFirstGroupOnly_when_multipleGroupsWouldFire`

### 3.8 Multiple Invalid Fields Are All Reported

- **What it tests:** Confirms that when more than one field carries a violation, all
  violations are collected and returned together rather than stopping at the first.
- **Applicable when:** The validation framework is configured to collect all violations
  (not fail-fast mode).
- **Priority:** HIGH
- **Example test name:** `test_validation_should_reportAllViolations_when_multipleFieldsAreInvalid`

### 3.9 Violation Property Path Identifies Correct Field Name

- **What it tests:** Confirms that the property path on each constraint violation names
  the actual field (e.g., "name" or "path") rather than an empty or generic path.
- **Applicable when:** The validation framework reports property paths in violations.
- **Priority:** MEDIUM
- **Example test name:** `test_violation_should_containCorrectPropertyPath_when_fieldFails`

### 3.10 Special Characters and Unicode Pass Validation

- **What it tests:** Confirms that strings containing valid special characters or accented
  Unicode letters are not incorrectly rejected by a pattern constraint.
- **Applicable when:** The request object does not restrict character sets beyond length.
- **Priority:** MEDIUM
- **Example test name:** `test_validation_should_accept_when_valueContainsSpecialCharacters`

---

## 4. Data Access Layer Tests

Tests that verify custom query methods return correct results and that database constraint
semantics match application-level expectations. These scenarios trace directly to the four
custom methods on the category-service `CategoryRepository`.

### 4.1 Existence Check Returns True for Matching Record

- **What it tests:** Confirms that an existence check method returns true when a record
  matching the given criteria exists in the store.
- **Applicable when:** The data access layer exposes boolean existence check methods.
- **Priority:** HIGH
- **Example test name:** `test_existsByName_should_returnTrue_when_recordExists`

### 4.2 Existence Check Returns False for Absent Record

- **What it tests:** Confirms that the same existence check returns false when no matching
  record is present, including after all records have been deleted.
- **Applicable when:** The data access layer exposes boolean existence check methods.
- **Priority:** HIGH
- **Example test name:** `test_existsByName_should_returnFalse_when_noRecordExists`

### 4.3 Case-Insensitive Lookup Matches Regardless of Letter Case

- **What it tests:** Confirms that a case-insensitive query method treats "DASHBOARD",
  "dashboard", and "Dashboard" as the same value and returns a match for each.
- **Applicable when:** The data access layer has queries declared with case-insensitive
  semantics (e.g., `IgnoreCase` suffix in Spring Data).
- **Priority:** HIGH
- **Example test name:** `test_existsByNameIgnoreCase_should_match_when_caseVaries`

### 4.4 Exclusion Query Returns False for the Excluded Record

- **What it tests:** Confirms that a query designed to check existence while excluding a
  specific ID returns false when the only matching record is the one being excluded. This
  is the critical test for "update uniqueness" logic.
- **Applicable when:** The data access layer has methods that exclude a given ID from the
  existence check (e.g., `existsByNameIgnoreCaseAndIdNot`).
- **Priority:** HIGH
- **Example test name:** `test_existsByNameAndIdNot_should_returnFalse_when_onlyMatchIsExcludedId`

### 4.5 Exclusion Query Returns True When Another Record Conflicts

- **What it tests:** Confirms that the exclusion query returns true when a different record
  (not the excluded ID) holds the conflicting value, so the update is correctly blocked.
- **Applicable when:** The data access layer has exclusion-based existence check methods.
- **Priority:** HIGH
- **Example test name:** `test_existsByNameAndIdNot_should_returnTrue_when_differentRecordConflicts`

### 4.6 List Query Returns Results Sorted in Correct Order

- **What it tests:** Confirms that a query returning multiple records applies the declared
  sort order (e.g., ascending by ID) so callers receive a predictable sequence.
- **Applicable when:** The data access layer is called with explicit sort parameters.
- **Priority:** MEDIUM
- **Example test name:** `test_findAll_should_returnAscendingOrder_when_sortedById`

### 4.7 Standard CRUD Operations Function Through the Data Access Interface

- **What it tests:** Confirms that save, findById, deleteById, and count all work correctly
  against a real or in-memory store, covering the inherited interface methods that the
  application relies on.
- **Applicable when:** The data access layer extends a framework-provided CRUD interface
  without fully overriding its methods.
- **Priority:** HIGH
- **Example test name:** `test_save_should_persistAndReturnEntityWithId_when_entityIsNew`

---

## 5. Business Logic / Service Layer Tests

Tests that verify the service layer enforces all business rules, handles happy-path CRUD
correctly, interacts with downstream dependencies in the right sequence, and publishes
events where expected. These scenarios reflect the full test suite of `CategoryServicesImpl`.

### 5.1 Create Returns Success Response with Correct Status and Message

- **What it tests:** Confirms that adding a new record with valid, non-duplicate input
  returns a success response with the expected HTTP status code and message constant.
- **Applicable when:** The service has a create/add operation.
- **Priority:** HIGH
- **Example test name:** `test_add_should_returnCreatedStatus_when_inputIsValid`

### 5.2 Create Invokes Persistence and Publishes Creation Event

- **What it tests:** Confirms that the create operation calls the data store's save method
  exactly once and, when event publishing is active, publishes a creation event.
- **Applicable when:** The service publishes domain events on state changes.
- **Priority:** HIGH
- **Example test name:** `test_add_should_saveEntityAndPublishEvent_when_inputIsValid`

### 5.3 Create Throws Uniqueness Exception for Duplicate Name

- **What it tests:** Confirms that submitting a name that already exists triggers the
  name-specific conflict exception before any save or event-publish call occurs.
- **Applicable when:** The service enforces name uniqueness.
- **Priority:** HIGH
- **Example test name:** `test_add_should_throwNameConflictException_when_nameAlreadyExists`

### 5.4 Create Throws Uniqueness Exception for Duplicate Path

- **What it tests:** Confirms that submitting a path that already exists triggers the
  path-specific conflict exception, and that the name check runs first (path check is
  skipped if the name is already a duplicate).
- **Applicable when:** The service enforces path uniqueness as a secondary check after
  name uniqueness.
- **Priority:** HIGH
- **Example test name:** `test_add_should_throwPathConflictException_when_pathAlreadyExists`

### 5.5 Create Does Not Persist When Validation Fails

- **What it tests:** Confirms that when a uniqueness exception is thrown, the data store's
  save method is never called, keeping the store in a consistent state.
- **Applicable when:** The service validates before persisting.
- **Priority:** HIGH
- **Example test name:** `test_add_should_neverCallSave_when_uniquenessCheckFails`

### 5.6 Update Returns Success Response for Valid Existing Record

- **What it tests:** Confirms that updating a record that exists with a new name and path
  that are unique to other records returns a success response.
- **Applicable when:** The service has an update operation.
- **Priority:** HIGH
- **Example test name:** `test_update_should_returnOkStatus_when_recordExistsAndInputIsValid`

### 5.7 Update Throws Not-Found Exception for Absent ID

- **What it tests:** Confirms that updating a record with an ID that does not exist in the
  store throws the appropriate not-found exception before any conflict checks or saves.
- **Applicable when:** The service verifies existence before updating.
- **Priority:** HIGH
- **Example test name:** `test_update_should_throwNotFoundException_when_idDoesNotExist`

### 5.8 Update Allows Same Data on the Same Record Without Conflict

- **What it tests:** Confirms that updating a record with its own current name and path
  (unchanged) does not trigger a uniqueness exception because the exclusion query correctly
  excludes the record being updated.
- **Applicable when:** The service uses exclusion-based uniqueness checks during updates.
- **Priority:** HIGH
- **Example test name:** `test_update_should_succeed_when_sameDataIsSubmittedForSameRecord`

### 5.9 Update Publishes Update Event on Success

- **What it tests:** Confirms that a successful update publishes an update event with the
  correct entity ID and event type.
- **Applicable when:** The service publishes domain events on state changes.
- **Priority:** HIGH
- **Example test name:** `test_update_should_publishUpdateEvent_when_recordIsUpdated`

### 5.10 Read Single Record Returns Correct DTO for Existing ID

- **What it tests:** Confirms that fetching a record by ID returns a response containing
  a data object with the matching ID, name, and path from the store.
- **Applicable when:** The service has a get-by-ID operation.
- **Priority:** HIGH
- **Example test name:** `test_getById_should_returnCategoryDto_when_recordExists`

### 5.11 Read Single Record Throws Not-Found Exception for Absent ID

- **What it tests:** Confirms that requesting a record by an ID that does not exist throws
  the not-found exception rather than returning null or an empty response body.
- **Applicable when:** The service has a get-by-ID operation.
- **Priority:** HIGH
- **Example test name:** `test_getById_should_throwNotFoundException_when_idDoesNotExist`

### 5.12 Read All Records Returns Sorted Set in Correct Order

- **What it tests:** Confirms that the list-all operation returns a set of DTOs sorted
  by the defined ordering (e.g., ascending by ID) and that the insertion-ordered structure
  preserves that sort.
- **Applicable when:** The service returns all records with a defined sort.
- **Priority:** HIGH
- **Example test name:** `test_getAll_should_returnAscendingOrderedSet_when_multipleRecordsExist`

### 5.13 Read All Records Returns Empty Set When No Records Exist

- **What it tests:** Confirms that when the store contains no records, the list-all
  operation returns an empty set rather than null, and still returns a success response.
- **Applicable when:** The service has a list-all operation.
- **Priority:** HIGH
- **Example test name:** `test_getAll_should_returnEmptySet_when_storeIsEmpty`

### 5.14 Delete Invokes Store Removal and Publishes Deletion Event

- **What it tests:** Confirms that the delete operation calls the store's delete method
  with the correct ID and publishes a deletion event.
- **Applicable when:** The service has a delete operation and publishes domain events.
- **Priority:** HIGH
- **Example test name:** `test_delete_should_removeFromStoreAndPublishEvent_when_idIsValid`

### 5.15 Count Returns Correct Numeric Value

- **What it tests:** Confirms that the count operation delegates to the store's count
  method and wraps the result in the standard response wrapper.
- **Applicable when:** The service exposes a count operation.
- **Priority:** MEDIUM
- **Example test name:** `test_counts_should_returnTotalCount_when_storeHasRecords`

### 5.16 Helper / Utility Methods Produce Correct Transformations

- **What it tests:** Confirms that entity-to-DTO conversion or other helper logic in a
  base class or utility correctly maps all fields without dropping data.
- **Applicable when:** The service inherits from or uses a helper class containing shared
  conversion logic.
- **Priority:** MEDIUM
- **Example test name:** `test_toDto_should_mapAllFields_when_entityIsFullyPopulated`

---

## 6. API / Handler Layer Tests

Tests that verify the HTTP handler correctly delegates to the service layer, propagates
validation errors as expected HTTP status codes, and wraps responses in the declared
response structure. These scenarios trace directly to `CategoryRestControllerTest`.

### 6.1 Create Endpoint Returns 201 Created on Success

- **What it tests:** Confirms that a valid POST request results in a 201 HTTP status with
  a success body, and that the handler called the service's create method exactly once.
- **Applicable when:** The API has a create endpoint.
- **Priority:** HIGH
- **Example test name:** `test_addEndpoint_should_return201_when_serviceSucceeds`

### 6.2 Update Endpoint Returns 200 OK on Success

- **What it tests:** Confirms that a valid PUT request to an existing resource ID results
  in a 200 HTTP status and a success body.
- **Applicable when:** The API has an update endpoint.
- **Priority:** HIGH
- **Example test name:** `test_updateEndpoint_should_return200_when_serviceSucceeds`

### 6.3 Get Single Endpoint Returns 200 with Correct Data

- **What it tests:** Confirms that a valid GET request for an existing ID returns 200 and
  that the response body contains the expected DTO data.
- **Applicable when:** The API has a get-by-ID endpoint.
- **Priority:** HIGH
- **Example test name:** `test_getByIdEndpoint_should_return200WithData_when_resourceExists`

### 6.4 Get All Endpoint Returns 200 with Collection

- **What it tests:** Confirms that the list endpoint returns 200 with a collection of
  items in the response body, and an empty collection when no items exist.
- **Applicable when:** The API has a list-all endpoint.
- **Priority:** HIGH
- **Example test name:** `test_getAllEndpoint_should_return200WithCollection_when_called`

### 6.5 Delete Endpoint Returns 200 on Success

- **What it tests:** Confirms that a DELETE request results in 200 and that the handler
  called the service's delete method with the correct path parameter.
- **Applicable when:** The API has a delete endpoint.
- **Priority:** HIGH
- **Example test name:** `test_deleteEndpoint_should_return200_when_serviceSucceeds`

### 6.6 Count Endpoint Returns 200 with Numeric Value

- **What it tests:** Confirms that the count endpoint returns 200 with a numeric value in
  the data field of the response wrapper.
- **Applicable when:** The API has a count or statistics endpoint.
- **Priority:** MEDIUM
- **Example test name:** `test_countsEndpoint_should_return200WithCount_when_called`

### 6.7 Handler Propagates Service Exception as Correct HTTP Status

- **What it tests:** Confirms that when the service throws a domain exception (not-found,
  conflict), the handler re-throws or forwards it to the global error handler, which maps
  it to the expected HTTP status (404, 409, etc.).
- **Applicable when:** The handler delegates exception mapping to a global error handler.
- **Priority:** HIGH
- **Example test name:** `test_handler_should_propagateException_when_serviceThrows`

### 6.8 Handler Delegates Path Variable to Service Unchanged

- **What it tests:** Confirms that the numeric ID extracted from the URL path variable is
  passed to the service method unchanged, not transformed or defaulted.
- **Applicable when:** The API handler extracts resource identifiers from the URL path.
- **Priority:** MEDIUM
- **Example test name:** `test_handler_should_passPathVariableToService_when_requestContainsId`

### 6.9 Response Body Wraps Data in the Declared Response Wrapper Structure

- **What it tests:** Confirms that the response body uses the application's standard
  response wrapper (e.g., `ApiResponseDto`) with expected fields: data, message, status,
  success flag.
- **Applicable when:** The API uses a response wrapper object.
- **Priority:** HIGH
- **Example test name:** `test_response_should_useResponseWrapper_when_endpointIsInvoked`

---

## 7. Error / Exception Handling Tests

Tests that verify each exception type maps to the correct HTTP status code, that the
response body carries the expected structure and message, and that concurrent conflict
scenarios are handled gracefully. These scenarios trace directly to
`GlobalExceptionHandlerTest` and the `DataIntegrityViolationException` handler.

### 7.1 Duplicate Name Exception Maps to 409 Conflict

- **What it tests:** Confirms the global handler converts a duplicate-name exception into
  a 409 HTTP status with `success = false` and the exception's message in the response.
- **Applicable when:** The application has a distinct exception type for name conflicts.
- **Priority:** HIGH
- **Example test name:** `test_handler_should_return409_when_duplicateNameExceptionIsThrown`

### 7.2 Duplicate Path Exception Maps to 409 Conflict

- **What it tests:** Confirms the global handler converts a duplicate-path exception into
  409 with the correct message, distinct from the name-conflict message.
- **Applicable when:** The application has a distinct exception type for path or URL
  conflicts.
- **Priority:** HIGH
- **Example test name:** `test_handler_should_return409_when_duplicatePathExceptionIsThrown`

### 7.3 Not-Found Exception Maps to 404

- **What it tests:** Confirms the handler returns 404 with `success = false` and the
  correct error message when a resource is not found.
- **Applicable when:** The application has a not-found exception type.
- **Priority:** HIGH
- **Example test name:** `test_handler_should_return404_when_notFoundExceptionIsThrown`

### 7.4 Validation Exception Maps to 400

- **What it tests:** Confirms that bean validation constraint violations result in a 400
  response with structured field-level error details in the body.
- **Applicable when:** The API uses framework-level input validation.
- **Priority:** HIGH
- **Example test name:** `test_handler_should_return400_when_validationConstraintsAreViolated`

### 7.5 Database Constraint Violation Maps to 409

- **What it tests:** Confirms that a database-level constraint violation exception (raised
  during concurrent duplicate inserts that pass application-level checks) is caught and
  mapped to 409, not 500.
- **Applicable when:** The application handles database constraint violations explicitly
  (as seen in `GlobalExceptionHandler.handleDataIntegrityViolationException`).
- **Priority:** HIGH
- **Example test name:** `test_handler_should_return409_when_dbConstraintViolationOccurs`

### 7.6 Error Response Has Success Flag Set to False

- **What it tests:** Confirms that every error handler sets `success = false` in the
  response body, so clients never receive a false positive success indicator.
- **Applicable when:** The API uses a response wrapper with a boolean success field.
- **Priority:** HIGH
- **Example test name:** `test_errorResponse_should_haveSuccessFalse_when_exceptionIsHandled`

### 7.7 Error Response Carries the Exception Message, Not a Generic Fallback

- **What it tests:** Confirms that the message field in the error response contains the
  specific exception message, preserving context for the client.
- **Applicable when:** The handler copies the exception message into the response body.
- **Priority:** HIGH
- **Example test name:** `test_errorResponse_should_containExceptionMessage_when_handled`

### 7.8 Error Response Data Field Is Null

- **What it tests:** Confirms that error responses never populate the data field of the
  response wrapper, preventing accidental partial-data leakage on failure.
- **Applicable when:** The API uses a response wrapper with a nullable data field.
- **Priority:** MEDIUM
- **Example test name:** `test_errorResponse_should_haveNullData_when_exceptionIsHandled`

### 7.9 Multiple Invocations of the Same Handler Return Consistent Results

- **What it tests:** Confirms that invoking the same exception handler twice with the same
  exception type produces responses that are structurally and semantically identical.
- **Applicable when:** The handler is a stateless function that should behave idempotently.
- **Priority:** LOW
- **Example test name:** `test_handler_should_returnConsistentResponse_when_calledMultipleTimes`

---

## 8. Configuration Tests

Tests that verify configuration classes are instantiable, that named constants have the
values the application code depends on, and that configuration beans are created with the
expected structure. These scenarios trace directly to `CacheConfigTest` and
`SwaggerConfigTest`.

### 8.1 Configuration Class Can Be Instantiated

- **What it tests:** Confirms the configuration class has a callable constructor and does
  not throw during instantiation outside a dependency injection container.
- **Applicable when:** The application has configuration classes that hold constants or
  bean definitions.
- **Priority:** MEDIUM
- **Example test name:** `test_configClass_should_instantiate_when_constructorIsCalled`

### 8.2 Cache Name Constants Have Correct String Values

- **What it tests:** Confirms each cache name constant string matches the value referenced
  by the cache annotations in the service layer, preventing silent cache mismatches.
- **Applicable when:** The application uses named caches and centralizes cache names in
  constants (e.g., `CacheConfig.CATEGORY_BY_ID_CACHE = "categoryById"`).
- **Priority:** HIGH
- **Example test name:** `test_cacheNameConstant_should_haveExpectedValue_when_compared`

### 8.3 API Documentation Bean Returns Non-Null Object with Expected Metadata

- **What it tests:** Confirms that the method or factory that creates the API documentation
  bean (OpenAPI, Swagger, or similar) returns a non-null object with title, version, and
  server information populated.
- **Applicable when:** The application configures API documentation programmatically.
- **Priority:** MEDIUM
- **Example test name:** `test_openApiBean_should_haveInfoPopulated_when_beanIsCreated`

### 8.4 Default Port Method Returns Correct Fallback Value

- **What it tests:** Confirms that a method providing a default configuration value
  (e.g., default port when environment variable is absent) returns the documented fallback.
- **Applicable when:** Configuration classes expose methods that provide defaults used as
  fallback values for injected properties.
- **Priority:** MEDIUM
- **Example test name:** `test_defaultPort_should_returnExpectedValue_when_called`

### 8.5 Feature Flag Defaults to Expected Off/On State

- **What it tests:** Confirms that a boolean feature flag is in the expected default state
  (off or on) when no explicit configuration is provided.
- **Applicable when:** The application uses feature flags controlled by configuration.
- **Priority:** MEDIUM
- **Example test name:** `test_featureFlag_should_beOffByDefault_when_noConfigPresent`

---

## 9. Event / Message Publishing Tests

Tests that verify domain events are published with the correct payload, type, and
transport invocation. These scenarios trace directly to `CacheEventPublisherTest` which
tests three distinct event types (CREATE, UPDATE, DELETE) over Redis Pub/Sub.

### 9.1 Creation Event Is Published with Correct Event Type

- **What it tests:** Confirms that the publisher's creation method sends a message whose
  event type field is set to CREATE, so downstream consumers can filter correctly.
- **Applicable when:** The service publishes domain events on record creation.
- **Priority:** HIGH
- **Example test name:** `test_publishCreate_should_sendEventWithCreateType_when_called`

### 9.2 Update Event Is Published with Correct Event Type and Entity ID

- **What it tests:** Confirms that the update event message carries UPDATE event type and
  includes the correct entity ID so consumers know which record changed.
- **Applicable when:** The service publishes domain events on record updates.
- **Priority:** HIGH
- **Example test name:** `test_publishUpdate_should_sendEventWithUpdateTypeAndId_when_called`

### 9.3 Deletion Event Is Published with Correct Event Type and Entity ID

- **What it tests:** Confirms that the deletion event message carries DELETE event type and
  the entity ID of the deleted record.
- **Applicable when:** The service publishes domain events on record deletions.
- **Priority:** HIGH
- **Example test name:** `test_publishDelete_should_sendEventWithDeleteTypeAndId_when_called`

### 9.4 Creation Event Does Not Carry an Entity ID

- **What it tests:** Confirms that creation events have a null entity ID because the new
  record's ID is not required by the consuming service to invalidate a list cache.
- **Applicable when:** Creation events are designed without an entity-ID field (as observed
  in `CacheEventPublisherTest.publishCategoryCreated` asserting `entityId == null`).
- **Priority:** MEDIUM
- **Example test name:** `test_publishCreate_should_haveNullEntityId_when_eventIsPublished`

### 9.5 Transport Method Is Called Exactly Once Per Publish Invocation

- **What it tests:** Confirms that each call to a publish method invokes the underlying
  transport (e.g., Redis `convertAndSend`) exactly once, not zero times (silent drop) or
  multiple times (duplicate delivery).
- **Applicable when:** The publisher wraps a transport client that must be called exactly
  once per event.
- **Priority:** HIGH
- **Example test name:** `test_publisher_should_callTransportOnce_when_publishMethodIsInvoked`

### 9.6 Event Carries Correct Entity Type Classification

- **What it tests:** Confirms that each published event identifies the entity type (e.g.,
  CATEGORY, PRODUCT) so consumers can route events to the correct invalidation handler.
- **Applicable when:** The event message includes an entity type discriminator field.
- **Priority:** HIGH
- **Example test name:** `test_event_should_haveCorrectEntityType_when_published`

---

## 10. Integration Test Scenarios (Aspirational)

These scenarios require a running data store, message broker, or real dependencies. They
are marked aspirational because they are not present in the observed unit test suite but
represent gaps that integration tests should eventually cover.

### 10.1 Cache Is Populated on First Read and Served on Second Read Without Store Access

- **What it tests:** Confirms that after the first read hits the store, subsequent reads
  for the same key return the cached value and the store is not queried again within the
  cache TTL window.
- **Applicable when:** The service layer uses a cache with a named region and TTL.
- **Priority:** HIGH
- **Example test name:** `test_cache_should_serveSecondRead_without_storeAccess_when_ttlActive`

### 10.2 Write Operation Evicts the Affected Cache Entries

- **What it tests:** Confirms that after an update or delete, the relevant cache entries
  are evicted so the next read hits the store rather than returning stale data.
- **Applicable when:** The service evicts cache entries on write operations.
- **Priority:** HIGH
- **Example test name:** `test_cacheEviction_should_removeEntry_when_updateOccurs`

### 10.3 Transaction Rolls Back and Store Is Unchanged When Service Fails

- **What it tests:** Confirms that if an exception is thrown mid-transaction, the database
  is returned to its state before the transaction started.
- **Applicable when:** The service uses transactions on write operations.
- **Priority:** HIGH
- **Example test name:** `test_transaction_should_rollback_when_exceptionOccursMidOperation`

### 10.4 Concurrent Duplicate Inserts Are Resolved by Database Constraint

- **What it tests:** Confirms that when two requests pass application-level uniqueness
  checks simultaneously and both attempt a database insert, the database unique constraint
  prevents the duplicate and the application returns 409 to the second caller.
- **Applicable when:** The application handles `DataIntegrityViolationException` (or
  equivalent) as observed in the GlobalExceptionHandler.
- **Priority:** HIGH
- **Example test name:** `test_concurrentInsert_should_return409_when_dbConstraintCatchesDuplicate`

### 10.5 Optimistic Locking Rejects Stale Update

- **What it tests:** Confirms that updating a record using a stale version number (the
  record was modified by another request since it was read) raises an optimistic locking
  exception rather than silently overwriting the newer version.
- **Applicable when:** The model carries a version field for optimistic concurrency control.
- **Priority:** HIGH
- **Example test name:** `test_update_should_failWithOptimisticLockException_when_versionIsStale`

### 10.6 Sort Order Is Preserved in the Returned Collection

- **What it tests:** Confirms that the list returned by the service maintains ascending ID
  order end-to-end after being retrieved, mapped to DTOs, and inserted into an ordered
  collection structure.
- **Applicable when:** The service uses a sort on the query and an order-preserving
  collection type such as LinkedHashSet.
- **Priority:** MEDIUM
- **Example test name:** `test_getAll_should_preserveSortOrder_when_collectedIntoLinkedHashSet`

### 10.7 External Service Call Fails Gracefully Without Crashing the Primary Operation

- **What it tests:** Confirms that if an event publisher or external HTTP call fails after
  the primary database operation succeeds, the primary operation result is still returned
  to the caller and the failure is logged without propagation.
- **Applicable when:** The service calls an external dependency (event broker, third-party
  API) after completing a primary database operation.
- **Priority:** MEDIUM
- **Example test name:** `test_service_should_succeedPrimary_when_eventPublishFails`

---

## 11. Cross-Cutting Test Scenarios

Scenarios that span multiple layers or apply to the application as a whole, including
concurrency safety, security boundaries, resilience, and observability.

### 11.1 Unauthenticated Request to Protected Endpoint Returns 401

- **What it tests:** Confirms that endpoints requiring authentication reject requests
  that carry no credentials with a 401 Unauthorized response, not a 200 or 500.
- **Applicable when:** The application has authentication-protected endpoints.
- **Priority:** HIGH
- **Example test name:** `test_endpoint_should_return401_when_noCredentialsProvided`

### 11.2 Unauthorized User Cannot Access Another User's Resources

- **What it tests:** Confirms that a request authenticated as user A cannot read, modify,
  or delete resources owned by user B (IDOR prevention).
- **Applicable when:** The application has per-resource ownership or role-based access.
- **Priority:** HIGH
- **Example test name:** `test_endpoint_should_return403_when_userAccessesAnotherUsersResource`

### 11.3 SQL-Like Special Characters in Input Do Not Cause Unexpected Behavior

- **What it tests:** Confirms that submitting values containing SQL metacharacters
  (apostrophes, dashes, percent signs) through the API does not cause query errors or
  altered query semantics. The data is stored and retrieved as literal characters.
- **Applicable when:** The application accepts free-text input and stores it in a database.
- **Priority:** HIGH
- **Example test name:** `test_service_should_treatSqlCharactersAsLiteral_when_storedAndRetrieved`

### 11.4 Response Time Stays Within Defined Threshold Under Normal Load

- **What it tests:** Confirms that a read operation returning cached data completes within
  an acceptable latency budget (e.g., under 50 ms for cached, under 500 ms for database).
- **Applicable when:** The application has documented performance SLOs or cache-based
  performance claims.
- **Priority:** MEDIUM
- **Example test name:** `test_cachedRead_should_completeWithinLatencyBudget_when_cacheIsWarm`

### 11.5 Application Logs the Correct Event Type When a Record Is Created

- **What it tests:** Confirms that the expected log entry is emitted at the correct level
  (INFO, WARN, ERROR) when a specific business operation is executed, supporting
  observability without requiring production log access.
- **Applicable when:** The application uses structured or keyed log events for business
  operations.
- **Priority:** MEDIUM
- **Example test name:** `test_service_should_emitInfoLog_when_recordIsCreatedSuccessfully`

### 11.6 Health Check Endpoint Returns Healthy Status When Application Is Running

- **What it tests:** Confirms that the health or readiness endpoint returns a 200 response
  indicating the application is operational, verifiable in automated deployment pipelines.
- **Applicable when:** The application exposes a health check endpoint.
- **Priority:** HIGH
- **Example test name:** `test_healthEndpoint_should_return200_when_applicationIsRunning`

### 11.7 Oversized Payload Is Rejected Before Reaching Business Logic

- **What it tests:** Confirms that a request body exceeding the configured maximum size
  is rejected with 400 or 413 at the validation or framework layer before any service
  method is invoked.
- **Applicable when:** The application enforces a maximum request body size.
- **Priority:** MEDIUM
- **Example test name:** `test_endpoint_should_rejectPayload_when_sizeExceedsMaximum`

### 11.8 Test Suite Is Fully Independent and Order-Agnostic

- **What it tests:** Confirms that individual test methods do not share mutable state,
  so the full suite produces the same outcome regardless of execution order or parallelism.
- **Applicable when:** Any project with automated tests.
- **Priority:** HIGH
- **Example test name:** `(enforced by test framework configuration, not a single test)`

---

**ENFORCEMENT:** Level 2 loading -- code review checklist. Test scenarios are cross-referenced
during Step 10 (Implementation) and Step 11 (Code Review) to verify coverage before merge.
Engineers select applicable scenarios from the roadmap based on the feature being implemented.

**SEE ALSO:**
- 28-test-coverage-enforcement.md -- JaCoCo coverage thresholds and JUnit 5 naming conventions
- 18-service-layer-conventions.md -- Interface+Impl+Helper pattern tested in Section 5
- 19-exception-handling-hierarchy.md -- Exception hierarchy tested in Section 7
- 17-api-response-wrapper.md -- ApiResponseDto structure validated in Sections 6 and 7
- 32-repository-conventions.md -- Repository query methods tested in Section 4
