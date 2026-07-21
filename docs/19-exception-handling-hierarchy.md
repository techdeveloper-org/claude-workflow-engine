---
description: "Level 2.2 - Custom exceptions, GlobalExceptionHandler, HTTP status mapping"
paths:
  - "src/**/exception/**/*.java"
  - "src/**/*ExceptionHandler.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Exception Handling Hierarchy (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a consistent exception class hierarchy and centralized handler so that
every HTTP error response has the same `ApiResponseDto<Void>` shape, every exception maps
to the correct HTTP status code, and no stack trace or internal detail is ever exposed to
the API consumer.

**APPLIES WHEN:** Spring Boot project with `@RestController` endpoints.

---

## 1. Exception Class Hierarchy

### What We Follow
A base `ApplicationException` in common-lib is the root. Domain exceptions extend a
`DomainException` sub-class. Infrastructure exceptions extend `InfrastructureException`.
Each leaf exception carries the fields needed to produce a useful error message.

### How To Implement

```java
// CORRECT -- hierarchy in common-lib
public abstract class ApplicationException extends RuntimeException {
    private final int httpStatus;

    protected ApplicationException(String message, int httpStatus) {
        super(message);
        this.httpStatus = httpStatus;
    }

    protected ApplicationException(String message, int httpStatus, Throwable cause) {
        super(message, cause);
        this.httpStatus = httpStatus;
    }

    public int getHttpStatus() { return httpStatus; }
}

public abstract class DomainException extends ApplicationException {
    protected DomainException(String message, int httpStatus) {
        super(message, httpStatus);
    }
}

// Per-service leaf exceptions in service's exception/ package
public class {Entity}NotFoundException extends DomainException {
    private final String {entity}Id;

    public {Entity}NotFoundException(String {entity}Id) {
        super("{Entity} not found: " + {entity}Id, 404);
        this.{entity}Id = {entity}Id;
    }

    public String get{Entity}Id() { return {entity}Id; }
}

public class Duplicate{Entity}Exception extends DomainException {
    public Duplicate{Entity}Exception(String identifier) {
        super("{Entity} already exists: " + identifier, 409);
    }
}

// WRONG -- extending Java's built-in exceptions directly
public class {Entity}NotFoundException extends RuntimeException {
    // No HTTP status; GlobalExceptionHandler cannot derive correct status code
}
```

### Why This Matters
Encoding the HTTP status in the exception class means the handler does not need a large
switch/if-else block to map exception types to status codes.

---

## 2. CommonExceptionHandler in common-lib

### What We Follow
`CommonExceptionHandler` in common-lib handles the exception types that are common to
every service: `MethodArgumentNotValidException` (validation failures), and `Exception`
(fallback for unexpected errors). It is NOT annotated with `@RestControllerAdvice` --
the per-service handler extends it and carries the annotation.

### How To Implement

```java
// CORRECT -- base handler in common-lib (no @RestControllerAdvice here)
public abstract class CommonExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponseDto<Void>> handleValidationErrors(
            MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
            .map(fe -> fe.getField() + ": " + fe.getDefaultMessage())
            .collect(Collectors.joining("; "));

        return ResponseEntity
            .status(HttpStatus.BAD_REQUEST)
            .body(ApiResponseDto.<Void>builder()
                .message(message)
                .success(false)
                .status(400)
                .timestamp(LocalDateTime.now())
                .build());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponseDto<Void>> handleGenericException(Exception ex) {
        // Log the full exception internally; return only safe message to client
        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(ApiResponseDto.<Void>builder()
                .message("An unexpected error occurred. Please try again later.")
                .success(false)
                .status(500)
                .timestamp(LocalDateTime.now())
                .build());
    }
}

// Per-service handler extends base and adds domain exceptions
@RestControllerAdvice
public class GlobalExceptionHandler extends CommonExceptionHandler {

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

    @ExceptionHandler(Duplicate{Entity}Exception.class)
    public ResponseEntity<ApiResponseDto<Void>> handleDuplicate{Entity}(
            Duplicate{Entity}Exception ex) {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(ApiResponseDto.<Void>builder()
                .message(ex.getMessage())
                .success(false)
                .status(409)
                .timestamp(LocalDateTime.now())
                .build());
    }
}

// WRONG -- catch-all in service methods exposing stack trace
catch (Exception e) {
    return ResponseEntity.status(500)
        .body(Map.of("error", e.getStackTrace()[0].toString()));  // Internal detail exposed
}
```

### Why This Matters
Per-service catch blocks that build error responses mean the same logic is duplicated in
every service and controller. The centralized handler in common-lib handles it once.

---

## 3. HTTP Status Mapping Rules

### What We Follow
Every domain exception maps to a specific HTTP status via the `httpStatus` field set
in the exception constructor.

```
{Entity}NotFoundException           -> 404 Not Found
Duplicate{Entity}Exception          -> 409 Conflict
InvalidOperation{Entity}Exception   -> 400 Bad Request
Unauthorized{Entity}Exception       -> 401 Unauthorized
Forbidden{Entity}Exception          -> 403 Forbidden
ExternalService{X}Exception         -> 502 Bad Gateway
RateLimitExceededException          -> 429 Too Many Requests
MethodArgumentNotValidException     -> 400 Bad Request (handled in CommonExceptionHandler)
Uncaught Exception (fallback)       -> 500 Internal Server Error
```

### How To Implement

```java
// CORRECT -- status encoded in the exception
public class InvalidOperation{Entity}Exception extends DomainException {
    public InvalidOperation{Entity}Exception(String reason) {
        super("Invalid operation on {Entity}: " + reason, 400);
    }
}

// WRONG -- handler contains a large if/else for status mapping
@ExceptionHandler(DomainException.class)
public ResponseEntity<?> handle(DomainException ex) {
    int status;
    if (ex instanceof {Entity}NotFoundException) {
        status = 404;
    } else if (ex instanceof Duplicate{Entity}Exception) {
        status = 409;
    }
    // ... continues for every type -- breaks open/closed principle
}
```

### Why This Matters
Centralizing the status in the exception means adding a new exception type does not require
modifying the handler -- just create the exception with the correct status.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit verifies that all classes in `exception/`
extend either `DomainException` or `InfrastructureException`. Code review: no
`@ExceptionHandler(Exception.class)` in per-service handlers (belongs in common-lib only).

**SEE ALSO:**
- 17-api-response-wrapper.md -- ApiResponseDto<Void> shape for error responses
- 22-common-library-design.md -- CommonExceptionHandler placement in common-lib
- 18-service-layer-conventions.md -- exceptions thrown from service helper methods
