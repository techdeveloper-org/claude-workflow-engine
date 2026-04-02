---
description: "Level 2.2 - Ordered validation groups, ValidationSequence, constant-driven messages"
paths:
  - "src/**/form/**/*.java"
  - "src/**/validation/**/*.java"
  - "src/**/controller/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Validation Sequence Pattern (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce ordered validation so that constraint annotations are evaluated in a
predictable sequence (null-check before blank-check before length-check before pattern-check).
Prevents confusing error messages like "must not be blank" appearing for a field that was null
rather than empty. Enforces constant-driven messages for maintainability.

**APPLIES WHEN:** Spring Boot project with Bean Validation (spring-boot-starter-validation).

---

## 1. Validation Group Interfaces

### What We Follow
Define five ordered group interfaces, one per constraint category. Groups are independent
marker interfaces with no methods.

### How To Implement

```java
// CORRECT -- one interface per constraint level
public interface NotNullGroup {}
public interface NotEmptyGroup {}
public interface NotBlankGroup {}
public interface LengthGroup {}
public interface PatternGroup {}

// ValidationSequence orders them via @GroupSequence
@GroupSequence({NotNullGroup.class, NotEmptyGroup.class, NotBlankGroup.class,
                LengthGroup.class, PatternGroup.class})
public interface ValidationSequence {}

// WRONG -- no groups, all constraints evaluated simultaneously
// produces confusing cascaded errors for a single missing field
public class {Entity}CreateForm {
    @NotNull
    @NotBlank
    @Length(max = 255)
    private String {field};
}
```

### Why This Matters
Without ordered groups, Bean Validation fires all annotations simultaneously. A null field
triggers both `@NotNull` and `@NotBlank` errors -- clients get duplicate messages for
the same root cause.

---

## 2. Controller Uses @Validated(ValidationSequence.class)

### What We Follow
Every controller method that accepts a Form body uses `@Validated(ValidationSequence.class)`,
not `@Valid`. The difference is that `@Validated` supports group-ordered validation;
`@Valid` always evaluates all constraints simultaneously.

### How To Implement

```java
// CORRECT -- @Validated with explicit sequence
@RestController
@RequestMapping("/api/{service-path}")
@RequiredArgsConstructor
@Tag(name = "{Entity} Management")
public class {Entity}Controller {

    private final {Entity}Services {entity}Services;

    @PostMapping
    public ResponseEntity<ApiResponseDto<{Entity}Dto>> create(
            @RequestBody @Validated(ValidationSequence.class) {Entity}CreateForm form) {
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body({entity}Services.create(form));
    }
}

// WRONG -- @Valid bypasses group ordering
@PostMapping
public ResponseEntity<ApiResponseDto<{Entity}Dto>> create(
        @RequestBody @Valid {Entity}CreateForm form) {
    // All annotations evaluated at once -- ordering ignored
}
```

### Why This Matters
Using `@Valid` instead of `@Validated(ValidationSequence.class)` defeats the entire purpose
of the group ordering, causing cascaded error messages on client input.

---

## 3. Form Fields Use Group-Specific Annotations

### What We Follow
Every validation annotation on a Form field specifies the exact group it belongs to.
Message values are always constants from `ValidationMessageConstants`, never literal strings.

### How To Implement

```java
// CORRECT -- group-specific annotations with constant messages
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class {Entity}CreateForm extends ValidationMessageConstants {

    @NotNull(message = FIELD_REQUIRED, groups = NotNullGroup.class)
    @NotBlank(message = FIELD_BLANK, groups = NotBlankGroup.class)
    @Length(min = 1, max = 255, message = FIELD_LENGTH, groups = LengthGroup.class)
    @Pattern(regexp = "^[a-zA-Z0-9 _-]+$", message = FIELD_PATTERN, groups = PatternGroup.class)
    private String {field};

    @NotNull(message = STATUS_REQUIRED, groups = NotNullGroup.class)
    private {Entity}Status status;

    @NotNull(message = AMOUNT_REQUIRED, groups = NotNullGroup.class)
    @DecimalMin(value = "0.01", message = AMOUNT_MIN, groups = LengthGroup.class)
    private BigDecimal amount;
}

// WRONG -- hardcoded messages, no groups
public class {Entity}CreateForm {
    @NotNull(message = "Name is required")    // hardcoded
    @NotBlank(message = "Name must not be blank")  // evaluated simultaneously with above
    private String {field};
}
```

### Why This Matters
Hardcoded validation messages scattered across Form classes cannot be updated in one place.
A message change requires a find-replace across every Form in every service.

---

## 4. ValidationMessageConstants Class

### What We Follow
All validation messages are `public static final String` constants in `ValidationMessageConstants`
in the common-lib. Form classes extend this class to use the constants as annotation values.

### How To Implement

```java
// CORRECT -- ValidationMessageConstants in common-lib
public class ValidationMessageConstants {

    // Null checks
    public static final String FIELD_REQUIRED = "Field is required";
    public static final String STATUS_REQUIRED = "Status is required";
    public static final String AMOUNT_REQUIRED = "Amount is required";

    // Blank checks
    public static final String FIELD_BLANK = "Field must not be blank";

    // Length checks
    public static final String FIELD_LENGTH = "Field length must be between {min} and {max}";
    public static final String AMOUNT_MIN = "Amount must be at least 0.01";

    // Pattern checks
    public static final String FIELD_PATTERN = "Field contains invalid characters";

    protected ValidationMessageConstants() {}
}

// Form extending constants
public class {Entity}CreateForm extends ValidationMessageConstants {
    @NotNull(message = FIELD_REQUIRED, groups = NotNullGroup.class)
    private String {field};
}

// WRONG -- constants defined inline in each Form
public class {Entity}CreateForm {
    private static final String NAME_REQUIRED = "Name is required";  // duplicated per form
}
```

### Why This Matters
Without a shared constants class, the same message text is copied across tens of Form classes.
A product naming change (e.g., "Field" -> "Name") requires updating every occurrence manually.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test verifies that all `@RequestBody` parameters
in controllers are annotated with `@Validated(ValidationSequence.class)` and not `@Valid`.
Code review checklist includes: no string literals in validation message attributes.

**SEE ALSO:**
- 15-dto-form-separation.md -- Form class structure and package conventions
- 24-constants-organization.md -- ValidationMessageConstants placement and naming
- 19-exception-handling-hierarchy.md -- GlobalExceptionHandler handling MethodArgumentNotValidException
