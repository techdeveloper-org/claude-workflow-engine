---
description: "Level 2.2 - Message constants, validation constants, API constants, usage pattern"
paths:
  - "src/**/constant/**/*.java"
  - "src/**/constants/**/*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Constants Organization (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce that all string literals used for messages, validation messages, and
API paths are declared as `public static final String` constants in dedicated constant classes.
Prevents hardcoded strings scattered across controllers, services, and form annotations that
become impossible to maintain consistently.

**APPLIES WHEN:** Spring Boot project with REST controllers and Bean Validation forms.

---

## 1. Three Constant Classes Per Service

### What We Follow
Every service defines three constant classes:
1. `ServiceMessageConstants` -- success/error messages for service responses
2. `ValidationMessageConstants` -- constraint violation messages (extended by Form classes)
3. `ApiConstants` -- endpoint paths and header names

### How To Implement

```
CORRECT -- constant class location
src/main/java/{org}/{project}/{service}/
  constant/
    ServiceMessageConstants.java
    ValidationMessageConstants.java
    ApiConstants.java

WRONG -- constants scattered across files
{Entity}Controller.java:
  private static final String SUCCESS = "Success";  // hidden in controller
{Entity}CreateForm.java:
  @NotNull(message = "Name is required")  // literal in annotation
```

All constants are `public static final`:

```java
// CORRECT -- ServiceMessageConstants
public final class ServiceMessageConstants {

    public static final String {ENTITY}_CREATED_SUCCESS = "{Entity} created successfully";
    public static final String {ENTITY}_UPDATED_SUCCESS = "{Entity} updated successfully";
    public static final String {ENTITY}_DELETED_SUCCESS = "{Entity} deleted successfully";
    public static final String {ENTITY}_FETCHED_SUCCESS = "{Entity} retrieved successfully";
    public static final String {ENTITY}_LIST_SUCCESS    = "{Entity} list retrieved successfully";

    public static final String {ENTITY}_NOT_FOUND      = "{Entity} not found";
    public static final String {ENTITY}_DUPLICATE      = "{Entity} already exists";
    public static final String {ENTITY}_INVALID_STATE  = "Invalid operation for current {Entity} state";

    private ServiceMessageConstants() {}
}

// WRONG -- messages in service implementation
return ApiResponseDto.<{Entity}Dto>builder()
    .message("Product created successfully")  // hardcoded; invisible to search
    .build();
```

### Why This Matters
Hardcoded messages cannot be found by searching constant names. A product name change
requires a text search across the entire codebase with risk of missing occurrences.

---

## 2. ValidationMessageConstants Extended by Forms

### What We Follow
`ValidationMessageConstants` is a base class (not final, not interface) so that Form
classes can extend it and use its constants as annotation `message` attribute values.
Java annotation attributes require compile-time constants, and `super.FIELD_REQUIRED`
does not work -- extending puts the constants in scope directly.

### How To Implement

```java
// CORRECT -- ValidationMessageConstants as extendable class in common-lib
public class ValidationMessageConstants {

    // Null checks
    public static final String FIELD_REQUIRED   = "Field is required";
    public static final String DATE_REQUIRED    = "Date is required";
    public static final String STATUS_REQUIRED  = "Status is required";

    // Blank checks
    public static final String FIELD_BLANK      = "Field must not be blank";
    public static final String NAME_BLANK       = "Name must not be blank";

    // Length checks
    public static final String NAME_TOO_LONG    = "Name must not exceed {max} characters";
    public static final String CODE_TOO_SHORT   = "Code must be at least {min} characters";

    // Pattern checks
    public static final String INVALID_EMAIL    = "Must be a valid email address";
    public static final String INVALID_PHONE    = "Phone number format is invalid";

    protected ValidationMessageConstants() {}
}

// Form extends to use constants in annotations
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class {Entity}CreateForm extends ValidationMessageConstants {

    @NotNull(message = FIELD_REQUIRED, groups = NotNullGroup.class)
    @NotBlank(message = FIELD_BLANK, groups = NotBlankGroup.class)
    @Length(max = 255, message = NAME_TOO_LONG, groups = LengthGroup.class)
    private String name;
}

// WRONG -- interface (cannot extend, annotation values cannot reference interface static fields
// if the interface is in a different compilation unit in older Java)
public interface ValidationMessageConstants {
    String FIELD_REQUIRED = "Field is required";
}
```

### Why This Matters
If `ValidationMessageConstants` is an interface, Form classes must use the fully qualified
`ValidationMessageConstants.FIELD_REQUIRED` in annotations -- verbose. Extension puts
constants directly in scope for cleaner annotation syntax.

---

## 3. ApiConstants for Endpoint Paths

### What We Follow
API path segments and header names are constants in `ApiConstants`. Controllers use
these constants in `@RequestMapping` and `@GetMapping` annotations.

### How To Implement

```java
// CORRECT -- ApiConstants
public final class ApiConstants {

    public static final String API_VERSION      = "/api/v1";
    public static final String {ENTITY}_BASE    = "/api/v1/{entity-path}";
    public static final String BY_ID            = "/{id}";
    public static final String SEARCH           = "/search";
    public static final String STATUS_UPDATE    = "/status";

    // Header names
    public static final String CORRELATION_ID_HEADER = "X-Correlation-ID";
    public static final String AUTHORIZATION_HEADER  = "Authorization";

    private ApiConstants() {}
}

// Controller usage
@RestController
@RequestMapping(ApiConstants.{ENTITY}_BASE)
public class {Entity}Controller {

    @GetMapping(ApiConstants.BY_ID)
    public ResponseEntity<ApiResponseDto<{Entity}Dto>> get{Entity}(
            @PathVariable Long id) { ... }

    @PutMapping(ApiConstants.BY_ID + ApiConstants.STATUS_UPDATE)
    public ResponseEntity<ApiResponseDto<Void>> updateStatus(
            @PathVariable Long id, ...) { ... }
}

// WRONG -- path literals in annotations
@RequestMapping("/api/v1/{entity-path}")
public class {Entity}Controller {
    @GetMapping("/{id}")              // Hardcoded; changes require touching every method
    @PutMapping("/{id}/status")       // Duplicated literal
}
```

### Why This Matters
Hardcoded path strings in annotations are invisible to refactoring tools. A path change
requires a text search with risk of missing annotated methods.

---

**ENFORCEMENT:** Level 2 loading -- SonarQube rule: no string literals in `@NotNull`,
`@NotBlank`, `@Pattern`, or `@Length` `message` attributes. Code review: no string
literal arguments to `ApiResponseDto.builder().message(...)`.

**SEE ALSO:**
- 15-dto-form-separation.md -- Form classes extending ValidationMessageConstants
- 16-validation-sequence-pattern.md -- group annotations using constants
- 17-api-response-wrapper.md -- service layer using ServiceMessageConstants
