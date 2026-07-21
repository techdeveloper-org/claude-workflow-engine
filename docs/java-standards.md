# Java Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Null Safety

### Rule 1.1: Use `Optional` for Return Types That May Be Absent, Never for Fields or Parameters
- `Optional<T>` signals "this method may not have a value" to callers at the type level
- Do NOT use `Optional` for class fields or method parameters - it adds indirection without benefit there
- Never call `Optional.get()` without checking `isPresent()` first - prefer `orElseThrow`, `orElse`, or `map`

```java
// BAD - Optional field, adds indirection with no benefit
public class User {
    private Optional<String> middleName; // wrong - use null or "" and document it
}

// BAD - unwrapping without checking
Optional<User> maybeUser = userRepository.findById(id);
User user = maybeUser.get(); // throws NoSuchElementException if absent

// GOOD - Optional as a return type, resolved explicitly
public Optional<User> findById(String id) {
    return Optional.ofNullable(userMap.get(id));
}

User user = userRepository.findById(id)
    .orElseThrow(() -> new UserNotFoundException(id));

// GOOD - chaining without ever calling get()
String displayName = userRepository.findById(id)
    .map(User::getName)
    .orElse("Unknown User");
```

### Rule 1.2: Prefer `Objects.requireNonNull` at Boundaries Over Manual Null Checks
- Fail fast with a clear message at the point a null enters the system, not three calls later

```java
// BAD - null propagates until something crashes unpredictably
public OrderService(OrderRepository repo) {
    this.repo = repo;
}

// GOOD - fails immediately with a clear message
public OrderService(OrderRepository repo) {
    this.repo = Objects.requireNonNull(repo, "repo must not be null");
}
```

### Rule 1.3: Use `@Nullable` / `@NonNull` Annotations on Public APIs
- Annotate public method parameters and return types so IDEs and static analyzers catch misuse at compile time
- Use a single annotation source consistently (JSR-305, JetBrains, or Spring's) - do not mix

```java
// GOOD - explicit nullability contract
public User findById(@NonNull String id) {
    ...
}

@Nullable
public String getMiddleName() {
    return middleName;
}
```

---

## 2. Exception Handling

### Rule 2.1: Never Catch `Exception` or `Throwable` Generically
- Catch the specific exception types you can actually handle
- A blanket `catch (Exception e)` hides bugs (NPEs, class cast errors) alongside expected failures

```java
// BAD - swallows everything including programming errors
try {
    processOrder(order);
} catch (Exception e) {
    log.error("failed");
}

// GOOD - catch what you expect, let the rest propagate
try {
    processOrder(order);
} catch (InsufficientStockException | PaymentDeclinedException e) {
    log.warn("Order {} failed: {}", order.getId(), e.getMessage());
    throw new OrderProcessingException(order.getId(), e);
}
```

### Rule 2.2: Prefer Unchecked Exceptions for Application Errors
- Checked exceptions force every caller up the stack to declare or catch them, which encourages blanket `catch (Exception e)`
- Reserve checked exceptions for truly recoverable conditions the caller is expected to handle differently

```java
// BAD - checked exception forces boilerplate everywhere it's called
public class InsufficientFundsException extends Exception { }

// GOOD - unchecked, with a clear name and context
public class InsufficientFundsException extends RuntimeException {
    public InsufficientFundsException(String accountId, BigDecimal shortfall) {
        super("Account " + accountId + " short by " + shortfall);
    }
}
```

### Rule 2.3: Never Discard the Original Exception When Wrapping
- Always pass the caught exception as the cause so the stack trace is preserved

```java
// BAD - loses the original stack trace
catch (SQLException e) {
    throw new DataAccessException("query failed");
}

// GOOD - preserves the cause chain
catch (SQLException e) {
    throw new DataAccessException("query failed: " + e.getMessage(), e);
}
```

---

## 3. Collections and Streams

### Rule 3.1: Prefer Immutable Collection Factories Over `new ArrayList<>()` for Fixed Data
- `List.of()`, `Set.of()`, `Map.of()` (Java 9+) communicate intent and reject nulls/mutation at creation

```java
// BAD - mutable list for data that never changes
List<String> roles = new ArrayList<>();
roles.add("ADMIN");
roles.add("USER");

// GOOD - immutable, communicates intent
List<String> roles = List.of("ADMIN", "USER");
```

### Rule 3.2: Use Streams for Transformation Pipelines, Not for Simple Iteration
- A stream pipeline with `.map().filter().collect()` is clearer than a manual loop for transformations
- A single `forEach` for a side effect is often less readable than an enhanced `for` loop - don't force streams where a loop is clearer

```java
// GOOD - stream pipeline for transformation
List<String> activeUserEmails = users.stream()
    .filter(User::isActive)
    .map(User::getEmail)
    .collect(Collectors.toList());

// GOOD - plain loop is clearer for a simple side effect
for (User user : users) {
    auditLog.record(user.getId());
}

// BAD - stream forced onto a simple side-effecting loop
users.stream().forEach(user -> auditLog.record(user.getId()));
```

### Rule 3.3: Avoid `.collect(Collectors.toList())` Boilerplate When `.toList()` Is Available
- Java 16+ provides `Stream.toList()` returning an unmodifiable list, shorter and clearer

```java
// OLDER - verbose
List<String> names = users.stream().map(User::getName).collect(Collectors.toList());

// GOOD (Java 16+) - concise, unmodifiable result
List<String> names = users.stream().map(User::getName).toList();
```

---

## 4. Records and Immutability

### Rule 4.1: Use `record` for Immutable Data Carriers (Java 16+)
- Records auto-generate constructor, accessors, `equals`, `hashCode`, and `toString`
- Use for DTOs, value objects, and API request/response payloads

```java
// BAD - hand-rolled immutable class with boilerplate
public final class Money {
    private final long amount;
    private final String currency;

    public Money(long amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }
    public long getAmount() { return amount; }
    public String getCurrency() { return currency; }
    // equals, hashCode, toString omitted for brevity - all hand-written
}

// GOOD - record generates all of the above
public record Money(long amount, String currency) {
    public Money {
        if (amount < 0) throw new IllegalArgumentException("amount must be non-negative");
    }
}
```

### Rule 4.2: Prefer `final` Fields and Defensive Copies for Mutable State
- Mark fields `final` wherever the value is set once
- Defensively copy mutable collections/arrays passed into constructors to prevent external mutation

```java
// BAD - caller can mutate internal state after construction
public class Order {
    private List<Item> items;
    public Order(List<Item> items) { this.items = items; }
}

// GOOD - defensive copy, immutable exposure
public class Order {
    private final List<Item> items;
    public Order(List<Item> items) { this.items = List.copyOf(items); }
    public List<Item> getItems() { return items; }
}
```

---

## 5. Concurrency

### Rule 5.1: Prefer `CompletableFuture` Composition Over Manual Thread Management
- Compose async work with `.thenApply`, `.thenCompose`, `.thenCombine` instead of manually creating and joining `Thread` objects

```java
// BAD - manual thread management, no error propagation
Thread t = new Thread(() -> {
    User user = fetchUser(id);
    process(user);
});
t.start();

// GOOD - composable, propagates exceptions
CompletableFuture.supplyAsync(() -> fetchUser(id))
    .thenApply(this::process)
    .exceptionally(ex -> {
        log.error("Failed to process user {}", id, ex);
        return null;
    });
```

### Rule 5.2: Always Shut Down `ExecutorService` Instances
- An `ExecutorService` that is never shut down leaks threads and prevents JVM exit
- Use try-with-resources (Java 19+ `AutoCloseable` executors) or an explicit `shutdown()` in a `finally` block

```java
// BAD - executor never shut down
ExecutorService pool = Executors.newFixedThreadPool(4);
pool.submit(task);

// GOOD - explicit lifecycle management
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    pool.submit(task).get();
} finally {
    pool.shutdown();
}
```

### Rule 5.3: Use `java.util.concurrent` Collections for Shared Mutable State
- Never share a plain `HashMap` or `ArrayList` across threads without external synchronization
- Prefer `ConcurrentHashMap`, `CopyOnWriteArrayList`, or immutable snapshots over manual `synchronized` blocks where possible

```java
// BAD - HashMap shared across threads without synchronization
private final Map<String, Session> sessions = new HashMap<>();

// GOOD - concurrent-safe by construction
private final Map<String, Session> sessions = new ConcurrentHashMap<>();
```

---

## 6. Resource Management

### Rule 6.1: Always Use Try-With-Resources for `AutoCloseable`
- Never rely on manual `close()` calls in a `finally` block when try-with-resources is available
- Multiple resources can be declared in one try-with-resources statement, closed in reverse order

```java
// BAD - resource leaked if readLine() throws
BufferedReader reader = new BufferedReader(new FileReader(path));
String line = reader.readLine();
reader.close();

// GOOD - resource always closed, even on exception
try (BufferedReader reader = new BufferedReader(new FileReader(path))) {
    String line = reader.readLine();
}
```

---

## 7. Generics

### Rule 7.1: Use Bounded Wildcards for Producer/Consumer Parameters (PECS)
- **P**roducer **E**xtends, **C**onsumer **S**uper: use `? extends T` when reading from a structure, `? super T` when writing to it

```java
// BAD - overly restrictive, only accepts List<Number> exactly
public void sum(List<Number> numbers) { ... }

// GOOD - accepts List<Integer>, List<Double>, etc.
public double sum(List<? extends Number> numbers) {
    return numbers.stream().mapToDouble(Number::doubleValue).sum();
}

// GOOD - consumer accepts List<Number> or any supertype
public void addIntegers(List<? super Integer> list) {
    list.add(1);
    list.add(2);
}
```

### Rule 7.2: Avoid Raw Types
- Raw types (`List` instead of `List<String>`) disable generic type checking and produce unchecked warnings

```java
// BAD - raw type, no compile-time type safety
List names = new ArrayList();
names.add("Alice");
names.add(42); // compiles, fails at runtime elsewhere

// GOOD - parameterized type
List<String> names = new ArrayList<>();
names.add("Alice");
```

---

## 8. Naming Conventions

### Rule 8.1: Follow Standard Java Casing
- Classes and interfaces: `PascalCase`
- Methods and fields: `camelCase`
- Constants (`static final`): `UPPER_SNAKE_CASE`
- Packages: all lowercase, no underscores

```java
// GOOD
public class OrderService { }
public interface PaymentGateway { }

public class Order {
    private static final int MAX_ITEMS = 100;
    private String customerId;

    public BigDecimal calculateTotal() { ... }
}
```

### Rule 8.2: Boolean Methods and Fields Read as Predicates
- Prefix with `is`, `has`, `can`, or `should`

```java
// BAD
boolean active;
boolean permission();

// GOOD
boolean isActive;
boolean hasPermission();
```

---

## 9. Testing

### Rule 9.1: Use JUnit 5 with Descriptive `@DisplayName` and AAA Structure
- Structure tests as Arrange-Act-Assert with a blank line between each section
- Use `@DisplayName` for human-readable descriptions, keep method names in `should_expectedBehavior_when_condition` form

```java
@Test
@DisplayName("throws InsufficientFundsException when balance is below withdrawal amount")
void withdraw_should_throwException_when_balanceInsufficient() {
    // Arrange
    Account account = new Account(BigDecimal.valueOf(50));

    // Act & Assert
    assertThrows(InsufficientFundsException.class,
        () -> account.withdraw(BigDecimal.valueOf(100)));
}
```

### Rule 9.2: Use `@ParameterizedTest` Instead of Copy-Pasted Test Methods
- Reduces duplication and makes edge cases explicit in one place

```java
@ParameterizedTest
@ValueSource(strings = {"", " ", "\t", "\n"})
void isBlank_should_returnTrue_when_inputIsWhitespaceOnly(String input) {
    assertTrue(StringUtils.isBlank(input));
}
```

---

## 10. Common LLM Mistakes to Avoid

- Catching `Exception` or `Throwable` generically instead of specific exception types
- Calling `Optional.get()` without checking `isPresent()` or using `orElseThrow`
- Using checked exceptions for application-level errors, forcing `throws Exception` up the call stack
- Sharing a plain `HashMap`/`ArrayList` across threads without synchronization or a concurrent collection
- Forgetting to close `AutoCloseable` resources outside of try-with-resources
- Using raw types (`List` instead of `List<String>`) and suppressing the resulting warnings
- Writing hand-rolled immutable classes instead of `record` on Java 16+
- Wrapping an exception without passing the original as the `cause`, losing the stack trace
- Using `Thread` directly instead of `ExecutorService`/`CompletableFuture` for concurrent work
- Forgetting to shut down an `ExecutorService`, leaking threads
