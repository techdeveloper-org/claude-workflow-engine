---
description: "Level 2.2 - JpaRepository typing, query method naming, JPQL over native, Sort/Pageable"
paths:
  - "src/**/repository/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Repository Conventions (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce consistent repository interface design so that data access is type-safe,
query methods follow predictable naming conventions, and native SQL is never used where JPQL
suffices. Prevents raw queries leaking database-specific SQL into the codebase and prevents
`public` repository interfaces that allow callers outside the package to bypass the service layer.

**APPLIES WHEN:** Spring Boot project with spring-boot-starter-data-jpa.

---

## 1. JpaRepository with Serializable ID Type

### What We Follow
Repository interfaces extend `JpaRepository<{Entity}, Serializable>`. Using `Serializable`
rather than `Long` makes the repository usable with any ID type (Long, String, UUID)
without changing the interface when the ID type evolves.

### How To Implement

```java
// CORRECT -- Serializable ID type, package-private interface
interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {
    // methods...
}

// WRONG -- concrete Long type, public access modifier
public interface {Entity}Repository extends JpaRepository<{Entity}, Long> {
    // public allows controllers to @Autowire the repository directly -- bypass service layer
}
```

Access modifier rules:
- Repository interface: no modifier (package-private)
- Spring can still inject it into service classes in the same package or via component scan

### Why This Matters
A `public` repository interface allows `@Autowired {Entity}Repository` in controllers,
bypassing transaction management and business logic in the service layer.

---

## 2. Spring Data Query Method Naming

### What We Follow
Use Spring Data's derived query method naming for simple queries. Method names must be
explicit: include the field name, the condition, and any sort or limit qualifier.

### How To Implement

```java
// CORRECT -- derived query methods
interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {

    // Exact match
    Optional<{Entity}> findBy{Field}({FieldType} {field});

    // Case-insensitive match
    Optional<{Entity}> findBy{Field}IgnoreCase(String {field});

    // Existence check
    boolean existsBy{Field}({FieldType} {field});

    // Count
    long countBy{Field}({FieldType} {field});

    // Status filter with sort
    List<{Entity}> findByStatus({Entity}Status status, Sort sort);

    // Pagination
    Page<{Entity}> findByStatus({Entity}Status status, Pageable pageable);

    // Multi-field
    Optional<{Entity}> findBy{Field}And{OtherField}({FieldType} {field}, {OtherType} {otherField});
}

// WRONG -- abbreviated names that lose meaning
List<{Entity}> getByStatus({Entity}Status s);   // what is 's'?
List<{Entity}> findAll();                        // ambiguous; findAll() already exists
```

### Why This Matters
Non-descriptive or inconsistent method names require developers to read the implementation
to understand what query is executed, defeating the self-documenting purpose of derived methods.

---

## 3. @Query with JPQL for Complex Queries

### What We Follow
Complex queries use `@Query` with JPQL (entity class names and field names, not table
and column names). `nativeQuery=true` is forbidden unless the query requires a
database-specific feature unavailable in JPQL.

### How To Implement

```java
// CORRECT -- JPQL uses entity and field names
interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {

    @Query("SELECT e FROM {Entity} e WHERE e.status = :status AND e.createdAt >= :from")
    List<{Entity}> findByStatusAndCreatedAfter(
            @Param("status") {Entity}Status status,
            @Param("from") LocalDateTime from);

    @Query("SELECT e FROM {Entity} e LEFT JOIN FETCH e.related WHERE e.id = :id")
    Optional<{Entity}> findByIdWithRelated(@Param("id") Long id);
}

// WRONG -- native SQL with table and column names
@Query(value = "SELECT * FROM {entity_table} WHERE status = :status AND created_at >= :from",
       nativeQuery = true)
List<{Entity}> findByStatusAndCreatedAfter(
        @Param("status") String status,
        @Param("from") LocalDateTime from);
// Table name is now coupled to the schema; breaks if table is renamed
```

Exception: `nativeQuery=true` is permitted ONLY for:
- Database-specific window functions not supported by JPQL
- Complex aggregations requiring `WITH` (CTE) syntax
- Performance-critical queries where the JPQL-generated SQL is provably inefficient

Document the reason inline when `nativeQuery=true` is used.

### Why This Matters
Native SQL ties the code to the database table schema. A column rename or table rename
requires finding every native query, whereas JPQL is automatically updated when the entity
field is refactored.

---

## 4. Sort and Pageable Parameters

### What We Follow
List queries accept `Sort` or `Pageable` as parameters rather than hardcoding order
or fetching all records. The caller (service layer) provides the sort criteria.

### How To Implement

```java
// CORRECT -- caller controls sort and pagination
interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {

    Page<{Entity}> findByStatus({Entity}Status status, Pageable pageable);

    List<{Entity}> findByStatus({Entity}Status status, Sort sort);
}

// Service usage
public ApiResponseDto<Page<{Entity}Dto>> list{Entity}(int page, int size) {
    Pageable pageable = PageRequest.of(page, size,
        Sort.by(Sort.Direction.DESC, "createdAt"));
    Page<{Entity}> entities = {entity}Repository.findByStatus(
        {Entity}Status.ACTIVE, pageable);
    // ...
}

// WRONG -- hardcoded ORDER BY inside repository, no pagination
interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {
    @Query("SELECT e FROM {Entity} e ORDER BY e.createdAt DESC")
    List<{Entity}> findAllOrderByCreatedAt();
    // Fetches ALL rows; no pagination possible; sort not caller-controllable
}
```

### Why This Matters
Queries without pagination fetch unbounded result sets. On a table with 1 million rows,
a `findAll()` or `findByStatus()` without Pageable loads the entire result into JVM heap.

---

## 5. Projection Interfaces for Read-Only Summaries

### What We Follow
When a query only needs a subset of entity fields (list views, dropdowns, search results),
use a projection interface instead of loading the full entity.

### How To Implement

```java
// CORRECT -- projection for list view (only id and name needed)
interface {Entity}Summary {
    Long getId();
    String get{Field}();
    String getStatusDisplayName();
}

interface {Entity}Repository extends JpaRepository<{Entity}, Serializable> {
    List<{Entity}Summary> findByStatusNot({Entity}Status status, Sort sort);
}

// WRONG -- loading full entity when only 2 fields are used
List<{Entity}> findByStatusNot({Entity}Status status);
// Loads all columns including blobs/clobs not needed for the list view
```

### Why This Matters
Loading full entities for summary views transfers unnecessary data from the database,
consumes more heap memory, and increases serialization overhead in the response.

---

**ENFORCEMENT:** Level 2 loading -- ArchUnit test: all interfaces in `repository/` must be
package-private. Code review: no `nativeQuery=true` without an explanatory comment.
SonarQube: detect `findAll()` calls in service methods that lack pagination.

**SEE ALSO:**
- 14-entity-design-patterns.md -- entity class structure that repositories operate on
- 18-service-layer-conventions.md -- service layer as the only caller of repositories
- 25-jpa-auditing-pattern.md -- AuditorAware configuration used by audited entities
