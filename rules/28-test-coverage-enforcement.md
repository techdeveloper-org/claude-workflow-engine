---
description: "Level 2.2 - JaCoCo per-package 100%, JUnit 5 patterns, application class testing"
paths:
  - "src/test/**/*.java"
  - "pom.xml"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Test Coverage Enforcement (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce 100% test coverage per package via JaCoCo, consistent JUnit 5 test
naming conventions, and explicit testing of the Spring Boot application class. Prevents
coverage debt from accumulating silently and ensures every code path is verified before merge.

**APPLIES WHEN:** Spring Boot project with maven-surefire-plugin and JaCoCo.

---

## 1. JaCoCo Plugin Configuration with Per-Package Enforcement

### What We Follow
JaCoCo is configured to enforce 100% coverage across all six counter types (LINE, BRANCH,
CLASS, METHOD, INSTRUCTION, COMPLEXITY) per package. There are no blanket exclusions.

### How To Implement

```xml
<!-- CORRECT -- JaCoCo plugin in pom.xml -->
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>prepare-agent</id>
            <goals><goal>prepare-agent</goal></goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>test</phase>
            <goals><goal>report</goal></goals>
        </execution>
        <execution>
            <id>check</id>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
            <configuration>
                <rules>
                    <rule>
                        <element>PACKAGE</element>
                        <limits>
                            <limit>
                                <counter>LINE</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                            <limit>
                                <counter>BRANCH</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                            <limit>
                                <counter>CLASS</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                            <limit>
                                <counter>METHOD</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                            <limit>
                                <counter>INSTRUCTION</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                            <limit>
                                <counter>COMPLEXITY</counter>
                                <value>COVEREDRATIO</value>
                                <minimum>1.00</minimum>
                            </limit>
                        </limits>
                    </rule>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>

<!-- WRONG -- bundle-level threshold hides package-level gaps -->
<rule>
    <element>BUNDLE</element>
    <limits>
        <limit>
            <counter>LINE</counter>
            <value>COVEREDRATIO</value>
            <minimum>0.80</minimum>
        </limit>
    </limits>
</rule>
<!-- 80% bundle-level passes even if an entire package has 0% coverage -->
```

### Why This Matters
A bundle-level threshold allows entire packages to have zero coverage as long as other
packages compensate with extra coverage. Per-package enforcement prevents these blind spots.

---

## 2. JUnit 5 Test Naming Convention

### What We Follow
Test class names end in `UnitTest` for isolated unit tests and `IntegrationTest` for tests
that require Spring context, a database, or external connections. Test method names use
camelCase starting with `should`.

### How To Implement

```java
// CORRECT -- unit test (no Spring context)
@ExtendWith(MockitoExtension.class)
class {Entity}ServicesImplUnitTest {

    @Mock
    private {Entity}Repository {entity}Repository;

    @InjectMocks
    private {Entity}ServicesImpl {entity}Services;

    @Test
    @DisplayName("should create {Entity} successfully when form is valid")
    void shouldCreate{Entity}WhenFormIsValid() {
        // Arrange
        {Entity}CreateForm form = new {Entity}CreateForm();
        form.set{Field}("test-value");

        {Entity} savedEntity = new {Entity}();
        savedEntity.setId(1L);
        savedEntity.set{Field}("test-value");
        given({entity}Repository.save(any({Entity}.class))).willReturn(savedEntity);

        // Act
        ApiResponseDto<{Entity}Dto> result = {entity}Services.create(form);

        // Assert
        assertThat(result.isSuccess()).isTrue();
        assertThat(result.getStatus()).isEqualTo(201);
        assertThat(result.getData().get{Field}()).isEqualTo("test-value");
        then({entity}Repository).should().save(any({Entity}.class));
    }

    @Test
    @DisplayName("should throw {Entity}NotFoundException when entity does not exist")
    void shouldThrow{Entity}NotFoundExceptionWhenEntityNotFound() {
        given({entity}Repository.findById(99L)).willReturn(Optional.empty());

        assertThatThrownBy(() -> {entity}Services.get{Entity}ById(99L))
            .isInstanceOf({Entity}NotFoundException.class)
            .hasMessageContaining("99");
    }
}

// CORRECT -- repository integration test with H2
@DataJpaTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
class {Entity}RepositoryIntegrationTest {

    @Autowired
    private {Entity}Repository {entity}Repository;

    @Test
    @DisplayName("should find {Entity} by {field} ignoring case")
    void shouldFind{Entity}By{Field}IgnoreCase() {
        {Entity} entity = new {Entity}();
        entity.set{Field}("TestValue");
        entity.setStatus({Entity}Status.ACTIVE);
        {entity}Repository.save(entity);

        Optional<{Entity}> result = {entity}Repository.findBy{Field}IgnoreCase("testvalue");

        assertThat(result).isPresent();
        assertThat(result.get().get{Field}()).isEqualTo("TestValue");
    }
}

// WRONG -- test without @DisplayName, without Arrange/Act/Assert structure
@Test
public void test1() {
    {Entity}CreateForm form = new {Entity}CreateForm();
    form.set{Field}("x");
    ApiResponseDto<?> result = service.create(form);
    assertTrue(result.isSuccess());
}
```

### Why This Matters
Tests without `@DisplayName` produce unreadable failure reports. Test names like `test1`
provide no information about what failed or why.

---

## 3. Application Class Test

### What We Follow
The Spring Boot application class has a dedicated test that verifies the class is annotated
correctly and that `SpringApplication.run()` can be called without throwing.

### How To Implement

```java
// CORRECT -- application class test
@SpringBootTest
class {Entity}ServiceApplicationTest {

    @Test
    @DisplayName("should load Spring application context successfully")
    void contextLoads() {
        // Context loads successfully if no exception is thrown
    }

    @Test
    @DisplayName("should have @SpringBootApplication annotation")
    void shouldHaveSpringBootApplicationAnnotation() {
        assertThat({Entity}ServiceApplication.class)
            .hasAnnotation(SpringBootApplication.class);
    }

    @Test
    @DisplayName("should have @EnableDiscoveryClient annotation")
    void shouldHaveEnableDiscoveryClientAnnotation() {
        assertThat({Entity}ServiceApplication.class)
            .hasAnnotation(EnableDiscoveryClient.class);
    }
}

// WRONG -- no test for application class (leaves main() at 0% coverage per JaCoCo)
// JaCoCo reports the application class as uncovered, failing the per-package 100% check
```

### Why This Matters
JaCoCo counts the `main(String[] args)` method and class-level annotations in its coverage
metrics. Without a test for the application class, the entire entry package fails coverage.

---

**ENFORCEMENT:** `mvn verify` executes JaCoCo check and fails the build if any package
drops below 100% on any counter. CI pipeline gate: build fails on coverage regression.
Code review: every PR adding a new class must include the corresponding test class.

**SEE ALSO:**
- 30-maven-build-conventions.md -- JaCoCo plugin placement in POM build section
- 18-service-layer-conventions.md -- constructor injection that enables unit testing without Spring
- 19-exception-handling-hierarchy.md -- exception classes that need branch coverage tests
