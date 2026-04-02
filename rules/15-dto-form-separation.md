---
description: "Level 2.2 - Request objects (Form) vs response objects (Dto), serialization rules, immutability"
paths:
  - "src/**/dto/**/*.java"
  - "src/**/form/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# DTO/Form Separation (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce strict separation between inbound request objects (Form) and outbound
response objects (Dto). Prevents accidental exposure of internal fields in responses,
prevents accepting unexpected fields from clients, and makes the API contract explicit.

**APPLIES WHEN:** Spring Boot project with REST controllers receiving and returning JSON.

---

## 1. Package and Naming Convention

### What We Follow
Request objects live in the `form/` package and carry the `Form` suffix.
Response objects live in the `dto/` package and carry the `Dto` suffix.
Never reuse the same class for both input and output.

### How To Implement

```
CORRECT -- package structure
src/main/java/{org}/{project}/{service}/
  form/
    {Entity}CreateForm.java       <- inbound create request
    {Entity}UpdateForm.java       <- inbound update request
  dto/
    {Entity}Dto.java              <- outbound response
    {Entity}SummaryDto.java       <- outbound list/summary response
  service/
    ApiResponseDto.java           <- lives in common-lib, not per-service

WRONG -- single class for both purposes
src/main/java/{org}/{project}/{service}/
  model/
    {Entity}Request.java          <- used for both request body AND response
    {Entity}DTO.java              <- inconsistent suffix casing
```

### Why This Matters
Using the same class for request and response causes Jackson to serialize internal
fields (entity IDs, audit timestamps, version numbers) that clients should never see.

---

## 2. Form Class Structure

### What We Follow
Form classes are annotated with `@Data` (Lombok), extend `ValidationMessageConstants` to
use constant-driven validation messages, and carry `@JsonIgnoreProperties(ignoreUnknown=true)`
so unknown fields in the request body are silently ignored rather than causing a 400.

### How To Implement

```java
// CORRECT -- Form class
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class {Entity}CreateForm extends ValidationMessageConstants {

    @NotNull(message = FIELD_REQUIRED, groups = NotNullGroup.class)
    @NotBlank(message = FIELD_BLANK, groups = NotBlankGroup.class)
    @Length(max = 255, message = FIELD_TOO_LONG, groups = LengthGroup.class)
    @Column(name = "{field}")
    private String {field};

    @NotNull(message = STATUS_REQUIRED, groups = NotNullGroup.class)
    private {Entity}Status status;
}

// WRONG -- Form class without ignoreUnknown, with hardcoded messages
public class {Entity}CreateForm {
    @NotNull(message = "Field is required")  // hardcoded string
    private String {field};
    // No @JsonIgnoreProperties -- extra JSON fields throw 400 errors
}
```

### Why This Matters
Without `@JsonIgnoreProperties(ignoreUnknown=true)`, adding a field to the client's
request body breaks the API for all existing clients -- a backwards-incompatible change.

---

## 3. Dto Class Structure

### What We Follow
Dto classes are immutable: `@Builder`, `@Getter` (no setter), `@AllArgsConstructor`,
`@NoArgsConstructor`. They carry `@JsonInclude(Include.NON_NULL)` to exclude null fields
from the JSON response. They implement `Serializable` for Redis caching.

### How To Implement

```java
// CORRECT -- Dto class
@Builder
@Getter
@AllArgsConstructor
@NoArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class {Entity}Dto implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private String {field};
    private {Entity}Status status;
    private String statusDisplayName;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}

// WRONG -- mutable Dto with setters
@Data  // @Data generates setters -- Dto should NOT have setters
public class {Entity}Dto {
    private Long id;
    // No @JsonInclude -- null fields appear in response as "field": null
    // No Serializable -- cannot be cached in Redis
}
```

### Why This Matters
A Dto with setters can be accidentally mutated after it is returned from the service layer,
causing unpredictable responses if the controller or aspect advice modifies it.

---

## 4. ApiResponseDto as Shared Wrapper

### What We Follow
`ApiResponseDto<T>` lives in the common-lib and is the ONLY response wrapper used across
all services. It is never redefined per service.

### How To Implement

```java
// CORRECT -- ApiResponseDto in common-lib (shared once)
@Builder
@Getter
@AllArgsConstructor
@NoArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ApiResponseDto<T> implements Serializable {

    private static final long serialVersionUID = 1L;

    private T data;
    private String message;
    private boolean success;
    private int status;
    private LocalDateTime timestamp;
}

// Controller usage
return ResponseEntity
    .status(HttpStatus.CREATED)
    .body(ApiResponseDto.<{Entity}Dto>builder()
        .data({entity}Dto)
        .message(ServiceMessageConstants.{ENTITY}_CREATED)
        .success(true)
        .status(201)
        .timestamp(LocalDateTime.now())
        .build());

// WRONG -- raw Dto returned from controller
@PostMapping
public {Entity}Dto create(@RequestBody {Entity}CreateForm form) {
    return {entity}Service.create(form);  // No envelope, no status, no message
}
```

### Why This Matters
Inconsistent response shapes force clients to handle different structures for each endpoint,
increasing integration complexity and error-handling code on the client side.

---

**ENFORCEMENT:** Level 2 loading -- code review checklist. Architecture tests
(ArchUnit) verify that classes in `dto/` have no setters and that `form/` classes
do not appear in `@RestController` return types.

**SEE ALSO:**
- 16-validation-sequence-pattern.md -- validation annotations on Form classes
- 17-api-response-wrapper.md -- controller usage of ApiResponseDto
- 24-constants-organization.md -- ValidationMessageConstants and ServiceMessageConstants
- 22-common-library-design.md -- ApiResponseDto placement in common-lib
