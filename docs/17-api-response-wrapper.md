---
description: "Level 2.2 - Unified response envelope, status propagation, error responses"
paths:
  - "src/**/controller/**/*.java"
  - "src/**/dto/ApiResponseDto.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# API Response Wrapper (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a single response envelope shape across all REST endpoints so that
clients always receive a consistent structure with data, message, success flag, HTTP status
code, and timestamp. Prevents raw entity or Dto returns that expose inconsistent shapes
and require per-endpoint client-side parsing logic.

**APPLIES WHEN:** Spring Boot REST controllers returning JSON.

---

## 1. All Endpoints Return ResponseEntity<ApiResponseDto<T>>

### What We Follow
Every controller method returns `ResponseEntity<ApiResponseDto<T>>` where T is the specific
Dto type. The HTTP status code is derived from `apiResponseDto.getStatus()`, not hardcoded
in the controller method itself.

### How To Implement

```java
// CORRECT -- unified envelope return
@GetMapping("/{id}")
public ResponseEntity<ApiResponseDto<{Entity}Dto>> get{Entity}ById(
        @PathVariable Long id) {
    ApiResponseDto<{Entity}Dto> response = {entity}Services.get{Entity}ById(id);
    return ResponseEntity
        .status(HttpStatus.valueOf(response.getStatus()))
        .body(response);
}

@PostMapping
public ResponseEntity<ApiResponseDto<{Entity}Dto>> create(
        @RequestBody @Validated(ValidationSequence.class) {Entity}CreateForm form) {
    ApiResponseDto<{Entity}Dto> response = {entity}Services.create(form);
    return ResponseEntity
        .status(HttpStatus.valueOf(response.getStatus()))
        .body(response);
}

// WRONG -- raw Dto return, status hardcoded in controller
@GetMapping("/{id}")
public {Entity}Dto get{Entity}ById(@PathVariable Long id) {
    return {entity}Services.get{Entity}ById(id);  // No envelope, no message
}
```

### Why This Matters
When the controller hardcodes the HTTP status, the controller and service layer both need
updating when the status changes. Deriving from the envelope keeps the decision in one place.

---

## 2. Success Response Structure

### What We Follow
Success responses set `success=true`, provide a human-readable `message` from
`ServiceMessageConstants`, and set `status` to the appropriate 2xx code.

### How To Implement

```java
// CORRECT -- success response in service layer
public ApiResponseDto<{Entity}Dto> create({Entity}CreateForm form) {
    {Entity} entity = build{Entity}(form);
    {entity}Repository.save(entity);
    {Entity}Dto dto = mapToDto(entity);

    return ApiResponseDto.<{Entity}Dto>builder()
        .data(dto)
        .message(ServiceMessageConstants.{ENTITY}_CREATED_SUCCESS)
        .success(true)
        .status(201)
        .timestamp(LocalDateTime.now())
        .build();
}

public ApiResponseDto<{Entity}Dto> get{Entity}ById(Long id) {
    {Entity} entity = findById(id);  // throws {Entity}NotFoundException if absent
    return ApiResponseDto.<{Entity}Dto>builder()
        .data(mapToDto(entity))
        .message(ServiceMessageConstants.{ENTITY}_FETCHED_SUCCESS)
        .success(true)
        .status(200)
        .timestamp(LocalDateTime.now())
        .build();
}

// WRONG -- building response in the controller
@GetMapping("/{id}")
public ResponseEntity<ApiResponseDto<{Entity}Dto>> get{Entity}ById(@PathVariable Long id) {
    {Entity}Dto dto = {entity}Services.get{Entity}ById(id);  // service returns raw Dto
    return ResponseEntity.ok(ApiResponseDto.<{Entity}Dto>builder()
        .data(dto)
        .success(true)
        .status(200)
        .build());  // controller builds envelope -- violates single-responsibility
}
```

### Why This Matters
Building the response envelope in the controller mixes HTTP layer concerns into the controller.
The service layer owns the business outcome including what message and status to return.

---

## 3. Void Operations Use ApiResponseDto<Void>

### What We Follow
Operations that do not return data (delete, status-change, trigger-action) return
`ApiResponseDto<Void>` with a descriptive message confirming the action.

### How To Implement

```java
// CORRECT -- void operation
@DeleteMapping("/{id}")
public ResponseEntity<ApiResponseDto<Void>> delete{Entity}(
        @PathVariable Long id) {
    ApiResponseDto<Void> response = {entity}Services.delete{Entity}(id);
    return ResponseEntity
        .status(HttpStatus.valueOf(response.getStatus()))
        .body(response);
}

// Service method
public ApiResponseDto<Void> delete{Entity}(Long id) {
    {Entity} entity = findById(id);
    {entity}Repository.delete(entity);

    return ApiResponseDto.<Void>builder()
        .data(null)
        .message(ServiceMessageConstants.{ENTITY}_DELETED_SUCCESS)
        .success(true)
        .status(200)
        .timestamp(LocalDateTime.now())
        .build();
}

// WRONG -- returning 204 No Content with empty body
@DeleteMapping("/{id}")
public ResponseEntity<Void> delete{Entity}(@PathVariable Long id) {
    {entity}Services.delete{Entity}(id);
    return ResponseEntity.noContent().build();  // Client gets no confirmation message
}
```

### Why This Matters
204 No Content forces clients to infer success from the HTTP status alone. An envelope
with a message confirms what was done, which is valuable for audit logging on the client.

---

## 4. Error Response Shape Matches Success Shape

### What We Follow
Error responses also return `ApiResponseDto<Void>` with `success=false` and the appropriate
error message. The data field is null (excluded by `@JsonInclude(NON_NULL)`). Error
responses are built in the `GlobalExceptionHandler`, never in controllers.

### How To Implement

```java
// CORRECT -- error response in GlobalExceptionHandler
@ExceptionHandler({Entity}NotFoundException.class)
public ResponseEntity<ApiResponseDto<Void>> handle{Entity}NotFound(
        {Entity}NotFoundException ex) {
    return ResponseEntity
        .status(HttpStatus.NOT_FOUND)
        .body(ApiResponseDto.<Void>builder()
            .message(ex.getMessage())
            .success(false)
            .status(404)
            .timestamp(LocalDateTime.now())
            .build());
}

// WRONG -- different error shape that omits the envelope
@ExceptionHandler({Entity}NotFoundException.class)
public ResponseEntity<Map<String, String>> handle{Entity}NotFound(
        {Entity}NotFoundException ex) {
    return ResponseEntity.status(404)
        .body(Map.of("error", ex.getMessage()));  // Different shape -- breaks clients
}
```

### Why This Matters
Clients that parse `response.data` for success cases and `response.error` for failures
must handle two different shapes. A consistent envelope means one parsing strategy for all cases.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test verifies that all public methods in
`@RestController` classes return `ResponseEntity<ApiResponseDto<?>>`.
Code review gate: no method in controller builds `ApiResponseDto` directly.

**SEE ALSO:**
- 15-dto-form-separation.md -- ApiResponseDto wrapper class definition (shared structure; this rule covers controller usage)
- 18-service-layer-conventions.md -- service methods return ApiResponseDto
- 19-exception-handling-hierarchy.md -- GlobalExceptionHandler building error ApiResponseDto
- 22-common-library-design.md -- ApiResponseDto lives in common-lib, shared across all services
- 24-constants-organization.md -- ServiceMessageConstants for message strings
