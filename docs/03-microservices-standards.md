---
description: "Level 2.2 - Spring Boot microservices standards (Java)"
paths:
  - "src/**/*.java"
  - "**/application*.yml"
  - "**/application*.yaml"
priority: critical
conditional: "Spring Boot project detected (pom.xml or build.gradle with spring-boot-starter)"
---

# Microservices Standards (Level 2.2 - Spring Boot Java)

**PURPOSE:** Enforce Spring Boot microservices coding standards for consistency, scalability, and maintainability.

**CONDITIONAL:** This rule applies ONLY when Spring Boot is detected in the project.

---

## 1. Project Structure (MANDATORY)

✅ **Base package naming convention:**

```
com.techdeveloper.{projectname}.{servicename}

Example: com.techdeveloper.ecommerce.productservice
```

✅ **Package organization:**

```
src/main/java/com/techdeveloper/ecommerce/product/
├── ProductServiceApplication.java          # Main class
│
├── controller/
│   ├── ProductController.java              # REST endpoints (public)
│   └── ProductCategoryController.java
│
├── dto/                                    # Data Transfer Objects (public)
│   ├── ProductResponseDto.java
│   ├── ProductCategoryResponseDto.java
│   └── ApiResponseDto.java                # Response wrapper
│
├── form/                                   # Request objects (public)
│   ├── ProductCreateForm.java
│   ├── ProductUpdateForm.java
│   └── ValidationMessageConstants.java
│
├── service/                                # Service interfaces (public)
│   ├── ProductService.java
│   └── ProductCategoryService.java
│
├── service.impl/                           # Implementations (package-private)
│   ├── ProductServiceImpl.java
│   ├── ProductServiceHelper.java
│   └── ProductCategoryServiceImpl.java
│
├── entity/                                 # Database entities (package-private)
│   ├── Product.java
│   └── ProductCategory.java
│
├── repository/                             # Data access (package-private)
│   ├── ProductRepository.java
│   └── ProductCategoryRepository.java
│
├── exception/                              # Custom exceptions
│   ├── ProductNotFoundException.java
│   ├── DuplicateProductException.java
│   └── GlobalExceptionHandler.java
│
├── client/                                 # Feign clients (package-private)
│   └── InventoryClient.java
│
├── config/                                 # Configuration classes
│   ├── DataSourceConfig.java
│   └── SecurityConfig.java
│
└── constant/                               # Constants
    ├── ApiConstants.java
    ├── MessageConstants.java
    └── ValidationMessageConstants.java
```

✅ **Access modifiers:**
- Service interfaces: `public`
- Service implementations: package-private (no modifier)
- Helper classes: package-private
- Entities: package-private
- Controllers: `public`
- Repositories: package-private

---

## 2. Spring Cloud Config Server (MANDATORY)

✅ **Configuration server structure:**

```
config-server/
└── configurations/
    ├── application.yml              # Global (all services)
    ├── {projectname}/
    │   ├── common/
    │   │   ├── database.yml
    │   │   ├── redis.yml
    │   │   ├── logging.yml
    │   │   └── security.yml
    │   └── services/
    │       ├── product-service.yml
    │       ├── order-service.yml
    │       └── payment-service.yml
    └── shared/
        └── audit-config.yml
```

✅ **Microservice application.yml (MINIMAL):**

```yaml
spring:
  application:
    name: product-service
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      fail-fast: true
      retry:
        initial-interval: 1000
        max-interval: 2000
        max-attempts: 6

secret-manager:
  client:
    enabled: true
    project-name: "ecommerce"
    base-url: "http://localhost:8085/api/v1/secrets"
```

❌ **NEVER add these to microservice application.yml:**
- Database configuration (host, port, credentials)
- Port numbers
- Redis/cache configuration
- Any environment-specific settings
- Feature flags

✅ **Config Server stores all environment configs:**

```yaml
# config-server/configurations/ecommerce/services/product-service.yml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/product_db"
    username: "${SECRET:db-username}"
    password: "${SECRET:db-password}"
  jpa:
    hibernate:
      ddl-auto: validate
  redis:
    host: localhost
    port: 6379

server:
  port: 8001
  servlet:
    context-path: /api/v1

logging:
  level:
    root: INFO
    com.techdeveloper: DEBUG
```

---

## 3. Secret Management (MANDATORY)

✅ **All secrets in Secret Manager:**

```yaml
# Config Server references secrets
spring:
  datasource:
    password: ${SECRET:db-password}
  rabbitmq:
    password: ${SECRET:rabbitmq-password}

jwt:
  secret: ${SECRET:jwt-secret}
  expiration: 3600

mail:
  password: ${SECRET:mail-password}
```

✅ **Secret naming convention:**
- `db-username`, `db-password`
- `jwt-secret`
- `api-key-{provider}`
- `mail-password`
- `rabbitmq-password`

❌ **NEVER hardcode secrets:**

```java
// ✗ WRONG - Exposed in code!
private String jwtSecret = "my-secret-key-123";
private String dbPassword = "SuperSecret123";

// ✓ CORRECT - From environment/config
@Value("${SECRET:jwt-secret}")
private String jwtSecret;
```

❌ **NEVER commit .env or credentials files:**

```bash
# .gitignore
.env
.env.local
application-secrets.yml
secrets.properties
```

---

## 4. Response Format (MANDATORY)

✅ **All APIs return ApiResponseDto<T>:**

```java
public class ApiResponseDto<T> {
    private String status;          // "SUCCESS" or "ERROR"
    private String message;         // Human-readable message
    private T data;                 // Actual data (or null)
    private LocalDateTime timestamp; // ISO 8601 timestamp
    private String traceId;         // For distributed tracing

    public static <T> ApiResponseDto<T> success(String message, T data) {
        ApiResponseDto<T> response = new ApiResponseDto<>();
        response.status = "SUCCESS";
        response.message = message;
        response.data = data;
        response.timestamp = LocalDateTime.now();
        return response;
    }

    public static ApiResponseDto<?> error(String message) {
        ApiResponseDto<?> response = new ApiResponseDto<>();
        response.status = "ERROR";
        response.message = message;
        response.data = null;
        response.timestamp = LocalDateTime.now();
        return response;
    }
}
```

✅ **Example responses:**

```json
// Success response
{
  "status": "SUCCESS",
  "message": "Product retrieved successfully",
  "data": {
    "id": 123,
    "name": "Laptop",
    "price": 999.99,
    "category": "Electronics"
  },
  "timestamp": "2026-03-08T19:26:00Z",
  "traceId": "a1b2c3d4e5f6"
}

// Error response
{
  "status": "ERROR",
  "message": "Product not found",
  "data": null,
  "timestamp": "2026-03-08T19:26:00Z",
  "traceId": "a1b2c3d4e5f6"
}
```

✅ **Controller pattern:**

```java
@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductService productService;

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponseDto<ProductResponseDto>> getById(
        @PathVariable Long id
    ) {
        ProductResponseDto product = productService.findById(id);
        return ResponseEntity.ok(
            ApiResponseDto.success(MessageConstants.PRODUCT_RETRIEVED, product)
        );
    }

    @PostMapping
    public ResponseEntity<ApiResponseDto<ProductResponseDto>> create(
        @Valid @RequestBody ProductCreateForm form
    ) {
        ProductResponseDto product = productService.create(form);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(ApiResponseDto.success(MessageConstants.PRODUCT_CREATED, product));
    }
}
```

❌ **NEVER return raw DTOs:**

```java
// ✗ WRONG - Not wrapped!
@GetMapping("/{id}")
public ProductResponseDto getById(@PathVariable Long id) {
    return productService.findById(id);
}

// ✓ CORRECT - Wrapped in ApiResponseDto
@GetMapping("/{id}")
public ResponseEntity<ApiResponseDto<ProductResponseDto>> getById(@PathVariable Long id) {
    return ResponseEntity.ok(
        ApiResponseDto.success("Product retrieved", productService.findById(id))
    );
}
```

---

## 5. Form Validation (MANDATORY)

✅ **All request forms extend ValidationMessageConstants:**

```java
public class ProductCreateForm extends ValidationMessageConstants {

    @NotBlank(message = PRODUCT_NAME_REQUIRED)
    @Size(min = 3, max = 100, message = PRODUCT_NAME_SIZE)
    private String name;

    @NotNull(message = PRODUCT_PRICE_REQUIRED)
    @DecimalMin(value = "0.0", inclusive = false, message = PRODUCT_PRICE_MIN)
    private BigDecimal price;

    @NotNull(message = PRODUCT_CATEGORY_REQUIRED)
    private Long categoryId;

    @Pattern(regexp = "^(ACTIVE|INACTIVE)$", message = PRODUCT_STATUS_INVALID)
    private String status;

    @Email(message = INVALID_EMAIL)
    private String contactEmail;

    // Getters/setters
}

public class ValidationMessageConstants {
    public static final String PRODUCT_NAME_REQUIRED = "Product name is required";
    public static final String PRODUCT_NAME_SIZE = "Product name must be 3-100 characters";
    public static final String PRODUCT_PRICE_REQUIRED = "Product price is required";
    public static final String PRODUCT_PRICE_MIN = "Product price must be greater than 0";
    public static final String PRODUCT_CATEGORY_REQUIRED = "Product category is required";
    public static final String PRODUCT_STATUS_INVALID = "Status must be ACTIVE or INACTIVE";
    public static final String INVALID_EMAIL = "Please provide a valid email address";
}
```

❌ **NEVER hardcode validation messages:**

```java
// ✗ WRONG
@NotBlank(message = "Product name is required")
private String name;

// ✓ CORRECT
@NotBlank(message = PRODUCT_NAME_REQUIRED)
private String name;
```

---

## 6. Service Layer Pattern (MANDATORY)

✅ **Service interface (public):**

```java
public interface ProductService {
    ProductResponseDto findById(Long id);
    ProductResponseDto create(ProductCreateForm form);
    ProductResponseDto update(Long id, ProductUpdateForm form);
    void delete(Long id);
    Page<ProductResponseDto> findAll(int page, int pageSize);
}
```

✅ **Service implementation (package-private):**

```java
@Service
@Transactional
class ProductServiceImpl extends ProductServiceHelper implements ProductService {

    private final ProductRepository productRepository;
    private final ProductMapper productMapper;

    public ProductServiceImpl(ProductRepository productRepository, ProductMapper productMapper) {
        this.productRepository = productRepository;
        this.productMapper = productMapper;
    }

    @Override
    @Transactional(readOnly = true)
    public ProductResponseDto findById(Long id) {
        Product product = findProductById(id);  // From helper
        return productMapper.toResponseDto(product);
    }

    @Override
    public ProductResponseDto create(ProductCreateForm form) {
        validateProductName(form.getName());  // From helper
        Product product = buildProductEntity(form);
        product = productRepository.save(product);
        return productMapper.toResponseDto(product);
    }

    @Override
    public ProductResponseDto update(Long id, ProductUpdateForm form) {
        Product product = findProductById(id);
        product.setName(form.getName());
        product.setPrice(form.getPrice());
        product = productRepository.save(product);
        return productMapper.toResponseDto(product);
    }

    @Override
    public void delete(Long id) {
        Product product = findProductById(id);
        productRepository.delete(product);
    }
}
```

✅ **Service helper (package-private):**

```java
abstract class ProductServiceHelper {

    @Autowired
    protected ProductRepository productRepository;

    protected Product findProductById(Long id) {
        return productRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
    }

    protected void validateProductName(String name) {
        if (productRepository.existsByNameIgnoreCase(name)) {
            throw new DuplicateProductException(name);
        }
    }

    protected Product buildProductEntity(ProductCreateForm form) {
        Product product = new Product();
        product.setName(form.getName());
        product.setPrice(form.getPrice());
        return product;
    }
}
```

✅ **@Transactional on write operations:**

```java
@Override
@Transactional  // ✓ Mark all write ops
public ProductResponseDto create(ProductCreateForm form) {
    Product product = buildProductEntity(form);
    return productMapper.toResponseDto(productRepository.save(product));
}

@Override
@Transactional
public ProductResponseDto update(Long id, ProductUpdateForm form) {
    // Update logic
}

@Override
@Transactional
public void delete(Long id) {
    // Delete logic
}

@Override
@Transactional(readOnly = true)  // ✓ Mark read-only
public ProductResponseDto findById(Long id) {
    return productMapper.toResponseDto(findProductById(id));
}
```

---

## 7. Entity Pattern (MANDATORY)

✅ **Entity with audit fields:**

```java
@Entity
@Table(name = "products")
class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @Column(name = "price", nullable = false, precision = 10, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 20)
    private ProductStatus status;

    // ✓ MANDATORY audit fields
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @Column(name = "created_by")
    private Long createdBy;

    @Column(name = "updated_by")
    private Long updatedBy;

    // ✓ Auto-populate audit fields
    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // Getters/setters
}
```

❌ **NEVER use camelCase in database:**

```java
// ✗ WRONG - DB will use camelCase
@Column(name = "createdAt")
private LocalDateTime createdAt;

// ✓ CORRECT - Explicit snake_case
@Column(name = "created_at")
private LocalDateTime createdAt;
```

---

## 8. Repository Pattern (MANDATORY)

✅ **Repository interface (package-private):**

```java
interface ProductRepository extends JpaRepository<Product, Long> {

    Optional<Product> findByNameIgnoreCase(String name);

    boolean existsByNameIgnoreCase(String name);

    @Query("SELECT p FROM Product p WHERE p.status = :status")
    List<Product> findByStatus(@Param("status") ProductStatus status);

    @Query("SELECT p FROM Product p WHERE p.name LIKE %:keyword%")
    Page<Product> searchByName(
        @Param("keyword") String keyword,
        Pageable pageable
    );
}
```

✅ **Use Spring Data query methods:**
- `findBy*`
- `existsBy*`
- `countBy*`
- `deleteBy*`

✅ **Complex queries use @Query:**

```java
@Query("SELECT p FROM Product p " +
       "WHERE p.status = :status " +
       "AND p.price BETWEEN :minPrice AND :maxPrice " +
       "ORDER BY p.createdAt DESC")
List<Product> findActiveInPriceRange(
    @Param("status") ProductStatus status,
    @Param("minPrice") BigDecimal minPrice,
    @Param("maxPrice") BigDecimal maxPrice
);
```

❌ **NEVER use raw SQL:**

```java
// ✗ WRONG - Raw SQL query
@Query(value = "SELECT * FROM products WHERE status = ?", nativeQuery = true)
List<Product> findByStatus(String status);

// ✓ CORRECT - JPQL
@Query("SELECT p FROM Product p WHERE p.status = :status")
List<Product> findByStatus(@Param("status") ProductStatus status);
```

---

## 9. Exception Handling (MANDATORY)

✅ **Custom exception classes:**

```java
public abstract class ApplicationException extends RuntimeException {
    protected String code;
    protected int httpStatus;

    public ApplicationException(String message) {
        super(message);
    }

    public String getCode() { return code; }
    public int getHttpStatus() { return httpStatus; }
}

public class ProductNotFoundException extends ApplicationException {
    public ProductNotFoundException(Long id) {
        super("Product not found with id: " + id);
        this.code = "PRODUCT_NOT_FOUND";
        this.httpStatus = HttpStatus.NOT_FOUND.value();
    }
}

public class DuplicateProductException extends ApplicationException {
    public DuplicateProductException(String name) {
        super("Product already exists: " + name);
        this.code = "DUPLICATE_PRODUCT";
        this.httpStatus = HttpStatus.CONFLICT.value();
    }
}
```

✅ **Global exception handler:**

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiResponseDto<?>> handleProductNotFound(
        ProductNotFoundException ex
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(ApiResponseDto.error(ex.getMessage()));
    }

    @ExceptionHandler(DuplicateProductException.class)
    public ResponseEntity<ApiResponseDto<?>> handleDuplicate(
        DuplicateProductException ex
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(ApiResponseDto.error(ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponseDto<?>> handleValidation(
        MethodArgumentNotValidException ex
    ) {
        String message = ex.getBindingResult().getFieldError().getDefaultMessage();
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(ApiResponseDto.error(message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponseDto<?>> handleGeneric(Exception ex) {
        logger.error("Unexpected error", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(ApiResponseDto.error("Internal server error"));
    }
}
```

---

## 10. Logging Standards

✅ **Use SLF4J with structured logging:**

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class ProductService {
    private static final Logger logger = LoggerFactory.getLogger(ProductService.class);

    public ProductResponseDto create(ProductCreateForm form) {
        try {
            Product product = buildProductEntity(form);
            product = productRepository.save(product);

            logger.info(
                "Product created successfully: id={}, name={}, price={}",
                product.getId(), product.getName(), product.getPrice()
            );

            return productMapper.toResponseDto(product);

        } catch (DuplicateProductException e) {
            logger.warn("Product creation failed: duplicate name={}", form.getName());
            throw e;
        } catch (Exception e) {
            logger.error("Product creation failed with unexpected error", e);
            throw new ApplicationException("Failed to create product");
        }
    }
}
```

❌ **NEVER log sensitive data:**

```java
// ✗ WRONG - Exposes password!
logger.debug("Login attempt: user={}, password={}", email, password);

// ✓ CORRECT - Log safely
logger.info("User login successful: userId={}", user.getId());
```

---

## 11. Database Migrations

✅ **Use Liquibase or Flyway for migrations:**

```xml
<!-- src/main/resources/db/migration/V001__Create_products_table.sql -->
CREATE TABLE products (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by BIGINT,
    updated_by BIGINT
);

CREATE INDEX idx_products_status ON products(status);
```

```yaml
# application.yml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
    baselineOnMigrate: true
```

---

## 12. Testing Standards

✅ **Unit and integration tests:**

```java
@SpringBootTest
class ProductServiceTest {

    @MockBean
    private ProductRepository productRepository;

    @InjectMocks
    private ProductServiceImpl productService;

    @Test
    void testFindByIdSuccess() {
        // Arrange
        Long productId = 1L;
        Product product = new Product();
        product.setId(productId);
        when(productRepository.findById(productId)).thenReturn(Optional.of(product));

        // Act
        ProductResponseDto result = productService.findById(productId);

        // Assert
        assertNotNull(result);
        assertEquals(productId, result.getId());
    }

    @Test
    void testFindByIdNotFound() {
        // Arrange
        when(productRepository.findById(9999L)).thenReturn(Optional.empty());

        // Act & Assert
        assertThrows(ProductNotFoundException.class, () -> {
            productService.findById(9999L);
        });
    }
}
```

---

## 13. Feign Client Pattern

✅ **Use Feign for inter-service communication:**

```java
@FeignClient(name = "inventory-service", url = "${inventory.service.url}")
interface InventoryClient {

    @GetMapping("/api/v1/inventory/{productId}")
    InventoryDto getInventory(@PathVariable Long productId);

    @PostMapping("/api/v1/inventory/reserve")
    ReservationDto reserve(@RequestBody ReservationRequest request);
}

@Service
class ProductService {
    private final InventoryClient inventoryClient;

    public ProductResponseDto create(ProductCreateForm form) {
        // Create product
        Product product = buildProductEntity(form);
        product = productRepository.save(product);

        // Reserve inventory
        try {
            inventoryClient.reserve(
                new ReservationRequest(product.getId(), form.getInitialStock())
            );
        } catch (FeignException e) {
            logger.warn("Failed to reserve inventory for product: {}", product.getId());
        }

        return productMapper.toResponseDto(product);
    }
}
```

---

**ENFORCEMENT:** These standards are MANDATORY for all Spring Boot microservices. Violations caught during code review and pre-commit hooks.

**SEE ALSO (Rules 13-32 -- Spring Boot deep-dive standards):**
- 13-spring-cloud-infrastructure.md -- Config Server, Eureka, gateway, retry/failover (expands Section 2)
- 14-entity-design-patterns.md -- @DynamicInsert, sequence IDs, optimistic locking (expands Section 7)
- 15-dto-form-separation.md -- Form vs Dto packages, immutability, serialization (expands Sections 4-5)
- 16-validation-sequence-pattern.md -- Ordered validation groups, @Validated vs @Valid (expands Section 5)
- 17-api-response-wrapper.md -- ApiResponseDto envelope, status propagation (expands Section 4)
- 18-service-layer-conventions.md -- Interface+Impl+Helper triple, transaction placement (expands Section 6)
- 19-exception-handling-hierarchy.md -- Exception hierarchy, CommonExceptionHandler, HTTP mapping (expands Section 9)
- 20-inter-service-communication.md -- Feign via gateway, contextId, circuit breaker (expands Section 13)
- 21-caching-strategy.md -- L1+L2 hybrid, TTL tiers, financial data exceptions
- 22-common-library-design.md -- common-lib structure, provided scope, base classes
- 23-enum-as-domain-model.md -- State machine enums, isTerminal(), canTransitionTo()
- 24-constants-organization.md -- ServiceMessageConstants, ValidationMessageConstants, ApiConstants
- 25-jpa-auditing-pattern.md -- AuditorAwareImpl, @EnableJpaAuditing, @CreatedBy
- 26-openapi-documentation.md -- @Tag, @Operation, @ApiResponses, JWT security scheme
- 27-centralized-logging.md -- Logback HTTP appender, async batching, MDC (expands Section 10)
- 28-test-coverage-enforcement.md -- JaCoCo 100% per-package, JUnit 5 naming (expands Section 12)
- 29-container-deployment.md -- Dockerfile, non-root user, JVM container flags, HEALTHCHECK
- 30-maven-build-conventions.md -- Parent POM, plugin stack, dependency scoping
- 31-security-authentication.md -- Spring Security stateless, JWT filter chain, CORS
- 32-repository-conventions.md -- JpaRepository<E,Serializable>, JPQL, Sort/Pageable (expands Section 8)
