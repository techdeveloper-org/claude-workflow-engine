---
description: "Level 2.2 - Parent POM, plugin stack, library packaging, dependency management"
paths:
  - "pom.xml"
  - "**/pom.xml"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Maven Build Conventions (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a consistent POM structure across all services and the common library
so that builds are reproducible, dependencies are managed centrally, and the required plugin
stack (spring-boot, jacoco, compiler, source) is always present.

**APPLIES WHEN:** Maven-based Spring Boot project (pom.xml at project root).

---

## 1. Parent POM Declaration

### What We Follow
Every service and the common library declare `spring-boot-starter-parent` as the parent.
This provides: dependency version management, plugin configuration defaults, resource
filtering, and Java version inheritance.

### How To Implement

```xml
<!-- CORRECT -- spring-boot-starter-parent as parent -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.x</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2023.x.x</spring-cloud.version>
</properties>

<!-- WRONG -- no parent, manually specifying plugin versions -->
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.x.x</version>
            <!-- Must now specify every plugin version manually -->
        </plugin>
    </plugins>
</build>
```

### Why This Matters
Without the parent POM, every plugin version must be declared manually. Version mismatches
between services cause different build behaviors for the same source code.

---

## 2. Spring Cloud BOM via dependencyManagement

### What We Follow
Spring Cloud dependency versions are managed through the BOM (Bill of Materials) imported
in `<dependencyManagement>`. Individual Cloud dependencies never specify a `<version>` tag.

### How To Implement

```xml
<!-- CORRECT -- Spring Cloud BOM import -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- No version tag needed -- managed by BOM -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>

<!-- WRONG -- version specified on individual Cloud starters -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <version>4.x.x</version>  <!-- Version drift from BOM -->
</dependency>
```

### Why This Matters
Spring Cloud versions must be aligned with the Spring Boot version. Manual version
specification breaks this alignment and causes `ClassNotFoundException` at startup.

---

## 3. Required Plugin Stack

### What We Follow
Every service POM declares four plugins in `<build><plugins>`:
1. `spring-boot-maven-plugin` -- produces the executable JAR
2. `jacoco-maven-plugin` -- coverage enforcement (see 28-test-coverage-enforcement.md)
3. `maven-compiler-plugin` -- annotation processing for Lombok
4. `maven-source-plugin` -- attach sources (common-lib only; optional for services)

### How To Implement

```xml
<!-- CORRECT -- required plugin stack -->
<build>
    <plugins>

        <!-- 1. Executable JAR -->
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <excludes>
                    <exclude>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                    </exclude>
                </excludes>
            </configuration>
        </plugin>

        <!-- 2. Coverage enforcement -- see 28-test-coverage-enforcement.md for full config -->
        <plugin>
            <groupId>org.jacoco</groupId>
            <artifactId>jacoco-maven-plugin</artifactId>
            <!-- full configuration in 28-test-coverage-enforcement.md -->
        </plugin>

        <!-- 3. Annotation processing for Lombok -->
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>

        <!-- 4. Attach sources (common-lib only) -->
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-source-plugin</artifactId>
            <executions>
                <execution>
                    <id>attach-sources</id>
                    <goals><goal>jar-no-fork</goal></goals>
                </execution>
            </executions>
        </plugin>

    </plugins>
</build>

<!-- WRONG -- spring-boot-maven-plugin without Lombok exclusion -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <!-- Lombok is packaged into the fat JAR unnecessarily -- adds ~2MB -->
</plugin>
```

### Why This Matters
Without Lombok excluded from the executable JAR, the JAR includes Lombok's source-generation
code at runtime. Without the compiler annotation processor path, Lombok annotations silently
produce no-op code -- `@Data` generates nothing and `NullPointerException` follows.

---

## 4. Dependency Scoping Rules

### What We Follow
Test dependencies use `<scope>test</scope>`. Common-lib dependencies that are used
only at runtime by consumers use `<scope>provided</scope>` to avoid forcing transitive
imports. H2 is always test scope.

### How To Implement

```xml
<!-- CORRECT -- correct scoping -->
<dependencies>

    <!-- H2 is never a runtime dependency -->
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- JUnit 5 -- test scope -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- In common-lib: mark all dependencies provided so consumers choose their own versions -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
        <scope>provided</scope>
    </dependency>

</dependencies>

<!-- WRONG -- H2 without test scope ends up in production classpath -->
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <!-- No scope -- defaults to compile; H2 in production JAR -->
</dependency>
```

### Why This Matters
H2 on the production classpath can be auto-configured by Spring Boot if the `spring.datasource`
property is misconfigured, causing the service to silently start against an in-memory database
rather than failing with a clear configuration error.

---

**ENFORCEMENT:** `mvn verify` validates the full plugin stack executes correctly.
CI pipeline: `mvn dependency:analyze` to detect unused declared or used undeclared dependencies.
Code review: pom.xml diff reviewed for scope changes and version overrides.

**SEE ALSO:**
- 28-test-coverage-enforcement.md -- full JaCoCo plugin configuration
- 22-common-library-design.md -- common-lib dependency scoping (provided scope)
- 29-container-deployment.md -- Docker COPY consuming the JAR produced by spring-boot-maven-plugin
