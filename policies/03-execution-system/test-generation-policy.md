# Test Generation Policy

**Version:** 1.0.0
**Priority:** MEDIUM
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines when and how the pipeline auto-generates unit tests for changed/new code.
Test generation uses templates per language and is guided by CallGraph data to
prioritize high-risk untested methods.

---

## When to Generate Tests

| Trigger | Step | Mandatory |
|---------|------|-----------|
| New public method added | Step 11 (Quality Gate 2) | YES |
| Coverage below threshold | Step 11 (Quality Gate 2) | YES |
| Risk-prioritized gap detected | Step 11 (Quality Gate 2) | YES |
| User requests test generation | Any step | YES |
| Breaking change detected | Step 11 (Quality Gate 3) | RECOMMENDED |

---

## Language Templates

### Python (pytest)

```python
# Template: test_{module_name}.py
import pytest
from {module} import {class_or_function}

class Test{ClassName}:
    def test_{method_name}_success(self):
        # Arrange
        # Act
        result = {method_call}
        # Assert
        assert result == expected

    def test_{method_name}_error(self):
        with pytest.raises({ExpectedException}):
            {method_call_with_bad_input}
```

### Java (JUnit 5)

```java
// Template: {ClassName}Test.java
@ExtendWith(MockitoExtension.class)
class {ClassName}Test {
    @Mock private {Dependency} {dependency};
    @InjectMocks private {ClassName} {instance};

    @Test
    void {methodName}_shouldReturnExpected_whenValidInput() {
        // Arrange
        // Act
        // Assert
    }
}
```

### TypeScript (Jest)

```typescript
// Template: {module}.test.ts
describe('{ClassName}', () => {
    it('should {expected_behavior} when {condition}', () => {
        // Arrange
        // Act
        // Assert
    });
});
```

### Kotlin (JUnit 5)

```kotlin
// Template: {ClassName}Test.kt
class {ClassName}Test {
    @Test
    fun `{methodName} should return expected when valid input`() {
        // Arrange
        // Act
        // Assert
    }
}
```

---

## Prioritization (Risk-Based)

Tests are generated in order of risk, using CallGraph data:

| Priority | Criteria | Rationale |
|----------|----------|-----------|
| 1 (Highest) | Public API methods | External-facing, most impact |
| 2 | Methods with 5+ callers | High fan-in = high blast radius |
| 3 | Cyclomatic complexity > 10 | Complex logic needs more tests |
| 4 | Recently modified methods | Changed code is most likely to have bugs |
| 5 (Lowest) | Private utility methods | Low external impact |

---

## Integration Test Generation

For methods that interact with external services:

| Integration Type | Test Approach |
|-----------------|---------------|
| Database (JPA/SQLAlchemy) | In-memory DB (H2/SQLite) |
| HTTP API | Mock server (WireMock/responses) |
| Message Queue | Embedded broker (EmbeddedKafka) |
| File System | Temp directory (pytest tmp_path) |

---

## Coverage Targets

| Project Type | Unit Test Target | Integration Test Target |
|-------------|-----------------|------------------------|
| New project | 60% | 40% |
| Existing (mature) | Current + 5% | Current + 2% |
| Critical path | 90% | 70% |
| Utility/helper | 50% | N/A |

---

## Naming Conventions

| Language | Test File Pattern | Test Method Pattern |
|----------|-------------------|-------------------|
| Python | `test_{module}.py` | `test_{method}_{scenario}` |
| Java | `{Class}Test.java` | `{method}_should{Expected}_when{Condition}` |
| TypeScript | `{module}.test.ts` | `should {expected} when {condition}` |
| Kotlin | `{Class}Test.kt` | `{method} should {expected} when {condition}` |

---

## Implementation

- **Generator:** `scripts/langgraph_engine/test_generator.py`
- **Integration:** `scripts/langgraph_engine/integration_test_generator.py`
- **Coverage:** `scripts/langgraph_engine/coverage_analyzer.py`
- **Tests:** `tests/test_test_generator.py`
