# Spring Boot Framework Standards

> Auto-loaded by Level 2 Standards System
> Layered on top of the language-level Java standards (`docs/java-standards.md`). This project already
> bundles 20 detailed Spring Boot microservices pattern docs (`docs/13-spring-cloud-infrastructure.md`
> through `docs/32-repository-conventions.md`) covering entity design, DTO/form separation, validation
> sequencing, the API response wrapper, service-layer conventions, the exception hierarchy, inter-service
> communication, caching, JPA auditing, OpenAPI docs, logging, test coverage, container deployment, Maven
> conventions, security/auth, and repository conventions. This file covers core framework mechanics those
> don't: dependency injection, transactions, configuration, profiles, and test slices.

---

## 1. Dependency Injection

### Rule 1.1: Use Constructor Injection, Never Field Injection
- Constructor injection makes dependencies explicit, enables `final` fields, and fails fast at startup if a bean is missing
- `@Autowired` on a field hides the dependency graph and makes the class impossible to instantiate without Spring

```java
// BAD - field injection, dependency is invisible from the constructor
@Service
public class OrderService {
    @Autowired
    private OrderRepository orderRepository;
    @Autowired
    private PaymentGateway paymentGateway;
}

// GOOD - constructor injection, dependencies are explicit and final
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public OrderService(OrderRepository orderRepository, PaymentGateway paymentGateway) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }
}
```

### Rule 1.2: Don't Reach for `@Autowired` on a Single Constructor - It's Implicit Since Spring 4.3
- Spring auto-detects a single constructor as the injection point; the annotation is redundant noise there
- Only annotate explicitly when a class has multiple constructors and one must be chosen

```java
// UNNECESSARY - @Autowired is implicit for a single constructor
@Service
public class OrderService {
    @Autowired
    public OrderService(OrderRepository repo) { ... }
}

// GOOD - clean, Spring infers it
@Service
public class OrderService {
    public OrderService(OrderRepository repo) { ... }
}
```

---

## 2. Transaction Boundaries

### Rule 2.1: Put `@Transactional` on Service Methods, Never on Controllers or Repositories
- The service layer is where a business operation's atomic boundary is defined
- `@Transactional` on a controller method ties the HTTP request lifecycle to the database transaction; on a repository it's usually redundant (Spring Data already wraps single operations)

```java
// BAD - transaction boundary on the controller
@RestController
public class OrderController {
    @Transactional
    @PostMapping("/orders")
    public OrderDto create(@RequestBody OrderRequest request) { ... }
}

// GOOD - transaction boundary on the service, where the business operation is defined
@Service
public class OrderService {
    @Transactional
    public Order createOrder(OrderRequest request) {
        Order order = orderRepository.save(new Order(request));
        inventoryService.reserve(order.getItems());
        return order;
    }
}
```

### Rule 2.2: Be Explicit About Read-Only Transactions
- `@Transactional(readOnly = true)` lets the persistence provider skip dirty checking and flush, and some drivers route read-only transactions to a replica

```java
// GOOD
@Transactional(readOnly = true)
public OrderDto getOrder(Long id) {
    return orderRepository.findById(id)
        .map(this::toDto)
        .orElseThrow(() -> new OrderNotFoundException(id));
}
```

### Rule 2.3: Know That Self-Invocation Bypasses `@Transactional`
- Calling a `@Transactional` method from another method in the *same* class does not go through the Spring proxy, so the transaction annotation is silently ignored
- Split the transactional method into a separate bean, or inject a self-reference, if this pattern is unavoidable

```java
// BAD - internal call bypasses the proxy, @Transactional on updateStock does nothing
@Service
public class InventoryService {
    public void reserve(List<Item> items) {
        for (Item item : items) {
            updateStock(item);  // self-invocation - no transaction applied
        }
    }

    @Transactional
    public void updateStock(Item item) { ... }
}

// GOOD - moved to a separate bean so the proxy is actually invoked
@Service
public class InventoryService {
    private final StockUpdater stockUpdater;
    public void reserve(List<Item> items) {
        items.forEach(stockUpdater::updateStock);
    }
}

@Service
public class StockUpdater {
    @Transactional
    public void updateStock(Item item) { ... }
}
```

---

## 3. Configuration

### Rule 3.1: Use `@ConfigurationProperties` for Grouped Settings, `@Value` Only for a Single One-Off
- A class of related properties (timeouts, retry counts, feature flags for one subsystem) should bind as a typed, validated group

```yaml
# application.yml
payment:
  gateway-url: https://api.payments.example.com
  timeout-ms: 5000
  max-retries: 3
```

```java
// GOOD - typed, validated group binding
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
    @NotBlank String gatewayUrl,
    @Positive int timeoutMs,
    @Min(0) int maxRetries
) {}

// ACCEPTABLE - single unrelated value
@Value("${app.version}")
private String appVersion;
```

### Rule 3.2: Never Hardcode Environment-Specific Values - Externalize via Profiles
- Database URLs, external service endpoints, and feature flags belong in `application-{profile}.yml`, not in Java code or a single shared `application.yml`

```yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev

# application-prod.yml
spring:
  datasource:
    url: ${DATABASE_URL}
```

---

## 4. Bean Scope and Lifecycle

### Rule 4.1: Default to Singleton Scope - Be Deliberate About Anything Else
- Spring beans are singletons by default; introducing `@Scope("prototype")` or request/session scope must be a deliberate choice with a documented reason (e.g., holding per-request mutable state)

```java
// BAD - mutable instance field on a singleton bean, shared across all callers/threads
@Service
public class ReportGenerator {
    private List<String> rows = new ArrayList<>();  // shared mutable state - race condition

    public void addRow(String row) { rows.add(row); }
}

// GOOD - no shared mutable state; state is local to the method call
@Service
public class ReportGenerator {
    public Report generate(List<String> rows) {
        return new Report(rows);
    }
}
```

### Rule 4.2: Avoid Circular Bean Dependencies - Redesign Instead of Using `@Lazy` to Paper Over Them
- A circular dependency between two `@Service` beans usually signals a missing abstraction (extract the shared logic into a third bean) rather than a problem `@Lazy` should silently solve

---

## 5. Testing Slices

### Rule 5.1: Use the Narrowest Test Slice That Covers What You're Testing
- `@SpringBootTest` boots the entire application context - slow, and overkill for testing a single layer
- Use `@WebMvcTest` for controllers, `@DataJpaTest` for repositories, plain unit tests (no Spring context) for services with mocked dependencies

```java
// GOOD - fast, no Spring context at all, dependencies mocked
class OrderServiceTest {
    private final OrderRepository orderRepository = mock(OrderRepository.class);
    private final OrderService orderService = new OrderService(orderRepository);

    @Test
    void createOrder_savesAndReturnsOrder() { ... }
}

// GOOD - loads only the web layer, MockMvc, no real database
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mockMvc;
    @MockBean OrderService orderService;
}

// GOOD - loads only the JPA layer against an embedded database
@DataJpaTest
class OrderRepositoryTest {
    @Autowired OrderRepository orderRepository;
}

// USE SPARINGLY - full context, reserve for true end-to-end scenarios
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderApiIntegrationTest { ... }
```

---

## 6. Actuator and Observability

### Rule 6.1: Expose Only the Actuator Endpoints You Actually Need, Never `*` in Production
- `management.endpoints.web.exposure.include: "*"` exposes `/heapdump`, `/env`, `/shutdown` publicly if unsecured — an information disclosure and DoS risk

```yaml
# BAD - exposes everything, including sensitive/dangerous endpoints
management:
  endpoints:
    web:
      exposure:
        include: "*"

# GOOD - explicit allowlist
management:
  endpoints:
    web:
      exposure:
        include: health, info, metrics, prometheus
```

---

## 7. Common LLM Mistakes to Avoid

- Using `@Autowired` field injection instead of constructor injection
- Putting `@Transactional` on a controller method instead of the service method that defines the business operation
- Calling a `@Transactional` method from within the same class (self-invocation), silently bypassing the proxy
- Using `@Value` for a whole group of related settings instead of a typed `@ConfigurationProperties` record
- Hardcoding environment-specific URLs/credentials instead of using Spring profiles
- Loading the full `@SpringBootTest` context to test a single controller or repository instead of `@WebMvcTest`/`@DataJpaTest`
- Introducing `@Scope("prototype")` or mutable instance fields on a singleton bean without recognizing the shared-state/thread-safety implications
- Exposing all Actuator endpoints (`include: "*"`) in a production configuration
- Reaching for `@Lazy` to silence a circular-dependency error instead of extracting the shared logic into a third bean
