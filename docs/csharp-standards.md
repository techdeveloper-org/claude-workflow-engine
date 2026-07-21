# C# Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Nullable Reference Types

### Rule 1.1: Enable Nullable Reference Types Project-Wide
- Add `<Nullable>enable</Nullable>` to the `.csproj` - this makes the compiler track and warn on possible null dereferences
- Do NOT disable it per-file with `#nullable disable` except in generated code

```xml
<!-- GOOD - .csproj -->
<PropertyGroup>
  <Nullable>enable</Nullable>
</PropertyGroup>
```

```csharp
// BAD - disables the compiler's null-tracking for no reason
#nullable disable
public class UserService { ... }

// GOOD - nullability is explicit in the signature
public User? FindById(string id) { ... }       // may return null
public User GetById(string id) { ... }          // never returns null, throws instead
```

### Rule 1.2: Use `?.` and `??` Instead of Manual Null Checks
- `?.` (null-conditional) and `??` (null-coalescing) are more concise and less error-prone than nested `if` checks
- Use `??=` to assign only when the target is null

```csharp
// BAD - verbose manual checks
string city;
if (user != null && user.Address != null) {
    city = user.Address.City;
} else {
    city = "Unknown";
}

// GOOD - concise and null-safe
string city = user?.Address?.City ?? "Unknown";

// GOOD - assign-if-null
_cache ??= new Dictionary<string, User>();
```

### Rule 1.3: Never Use the Null-Forgiving Operator (`!`) Without a Comment Explaining Why
- `!` tells the compiler "trust me, this isn't null" - it suppresses the warning but not the runtime risk
- Acceptable only when nullability is genuinely guaranteed by logic the compiler can't see, with a comment

```csharp
// BAD - silences the warning without justification
var name = user.Name!;

// ACCEPTABLE - guarded by preceding logic, documented
if (users.Count == 0) throw new InvalidOperationException("no users");
var first = users.FirstOrDefault(u => u.IsActive);
// Safe: FirstOrDefault only returns null if no match, and we just checked Count > 0
var name = first!.Name;
```

---

## 2. Exception Handling

### Rule 2.1: Never Catch `Exception` Without Rethrowing or Handling Specifically
- Catch specific exception types you can meaningfully handle
- A bare `catch (Exception ex)` that only logs and swallows hides bugs

```csharp
// BAD - swallows everything
try {
    ProcessOrder(order);
} catch (Exception ex) {
    _logger.LogError(ex, "failed");
}

// GOOD - catch what you expect, let unexpected errors propagate
try {
    ProcessOrder(order);
} catch (InsufficientStockException ex) {
    _logger.LogWarning(ex, "Order {OrderId} failed: insufficient stock", order.Id);
    throw new OrderProcessingException(order.Id, ex);
}
```

### Rule 2.2: Use `throw;` Not `throw ex;` to Rethrow
- `throw;` preserves the original stack trace; `throw ex;` resets it to the rethrow point, losing the original failure location

```csharp
// BAD - resets the stack trace
catch (SqlException ex) {
    _logger.LogError(ex, "query failed");
    throw ex;
}

// GOOD - preserves the original stack trace
catch (SqlException ex) {
    _logger.LogError(ex, "query failed");
    throw;
}
```

### Rule 2.3: Define Custom Exceptions for Domain Errors
- Inherit from `Exception`, provide a constructor that takes context, and a clear message

```csharp
// GOOD
public class InsufficientFundsException : Exception
{
    public string AccountId { get; }
    public decimal Shortfall { get; }

    public InsufficientFundsException(string accountId, decimal shortfall)
        : base($"Account {accountId} short by {shortfall:C}")
    {
        AccountId = accountId;
        Shortfall = shortfall;
    }
}
```

---

## 3. Async/Await

### Rule 3.1: Use `async`/`await` All the Way Down - Never Block on Async Code
- Calling `.Result` or `.Wait()` on a `Task` can deadlock in contexts with a synchronization context (e.g. ASP.NET classic, UI apps)
- Propagate `async` through the call chain instead of blocking

```csharp
// BAD - can deadlock, blocks the calling thread
public User GetUser(string id)
{
    return _repository.GetByIdAsync(id).Result;
}

// GOOD - async all the way through
public async Task<User> GetUserAsync(string id)
{
    return await _repository.GetByIdAsync(id);
}
```

### Rule 3.2: Use `ConfigureAwait(false)` in Library Code
- Prevents unnecessary context-switching back to the original synchronization context in reusable library code
- Not needed in ASP.NET Core (no synchronization context) but still a safe default for shared libraries

```csharp
// GOOD - library code, avoids capturing the caller's context
public async Task<User> GetByIdAsync(string id)
{
    return await _dbContext.Users.FindAsync(id).ConfigureAwait(false);
}
```

### Rule 3.3: Name Async Methods with an `Async` Suffix and Return `Task`/`Task<T>`
- Never use `async void` except for top-level event handlers - exceptions thrown from `async void` cannot be caught by the caller

```csharp
// BAD - async void, exceptions crash the process instead of being catchable
public async void SaveUser(User user) { await _repo.SaveAsync(user); }

// GOOD - Task-returning, awaitable and exceptions propagate normally
public async Task SaveUserAsync(User user) { await _repo.SaveAsync(user); }
```

---

## 4. LINQ and Collections

### Rule 4.1: Prefer LINQ Method Syntax for Transformations, Plain Loops for Side Effects
- `.Where().Select()` reads clearly for filtering/mapping
- Don't force `.ForEach()` for side effects on `IEnumerable<T>` - use a `foreach` loop instead (only `List<T>.ForEach` exists natively, and even then a loop is often clearer)

```csharp
// GOOD - LINQ for transformation
var activeEmails = users.Where(u => u.IsActive).Select(u => u.Email).ToList();

// GOOD - plain loop for a side effect
foreach (var user in users) {
    _auditLog.Record(user.Id);
}
```

### Rule 4.2: Avoid Multiple Enumeration of `IEnumerable<T>`
- Each enumeration of a lazy `IEnumerable<T>` (e.g. from LINQ or a generator) re-runs the query
- Materialize with `.ToList()` or `.ToArray()` when the sequence is iterated more than once

```csharp
// BAD - query runs twice, and if the source is a DB query, that's two round trips
IEnumerable<User> activeUsers = _repository.GetAll().Where(u => u.IsActive);
var count = activeUsers.Count();
var first = activeUsers.FirstOrDefault();

// GOOD - materialized once
var activeUsers = _repository.GetAll().Where(u => u.IsActive).ToList();
var count = activeUsers.Count;
var first = activeUsers.FirstOrDefault();
```

---

## 5. Records and Immutability

### Rule 5.1: Use `record` for Immutable Data Carriers (C# 9+)
- Records provide value-based equality, `with`-expressions, and a concise syntax for DTOs and value objects

```csharp
// BAD - hand-rolled immutable class with manual equality
public class Money
{
    public long Amount { get; }
    public string Currency { get; }
    public Money(long amount, string currency) { Amount = amount; Currency = currency; }
    public override bool Equals(object? obj) => obj is Money m && m.Amount == Amount && m.Currency == Currency;
    public override int GetHashCode() => HashCode.Combine(Amount, Currency);
}

// GOOD - record generates equality, ToString, and supports 'with'
public record Money(long Amount, string Currency);

var price = new Money(1000, "USD");
var discounted = price with { Amount = 800 };
```

### Rule 5.2: Prefer Init-Only Properties for Immutable Objects That Aren't Records
- `init` allows setting a property only during object initialization, then it becomes read-only

```csharp
// GOOD
public class OrderRequest
{
    public string CustomerId { get; init; } = string.Empty;
    public List<string> ItemIds { get; init; } = new();
}
```

---

## 6. Resource Management

### Rule 6.1: Always Use `using` for `IDisposable`
- Prefer the `using` declaration (C# 8+) over nested blocks when the resource should live to the end of the enclosing scope

```csharp
// BAD - resource leaked if an exception is thrown before Dispose()
var connection = new SqlConnection(connectionString);
connection.Open();
// ... work ...
connection.Dispose();

// GOOD - using declaration, disposed at end of scope even on exception
using var connection = new SqlConnection(connectionString);
connection.Open();
// ... work ...
```

### Rule 6.2: Implement `IDisposable` Correctly When a Class Owns Unmanaged or Disposable Resources
- Follow the standard dispose pattern; don't just add a `Dispose()` method that does nothing meaningful

```csharp
// GOOD
public class ReportGenerator : IDisposable
{
    private readonly FileStream _stream;
    private bool _disposed;

    public ReportGenerator(string path) => _stream = new FileStream(path, FileMode.Create);

    public void Dispose()
    {
        if (_disposed) return;
        _stream.Dispose();
        _disposed = true;
        GC.SuppressFinalize(this);
    }
}
```

---

## 7. Pattern Matching

### Rule 7.1: Use Pattern Matching Instead of Chained `is`/Cast or `switch` on Type Checks
- C# pattern matching (`is` patterns, `switch` expressions) is more concise and null-safe than manual casting

```csharp
// BAD - manual cast after type check
if (shape is Circle) {
    var circle = (Circle)shape;
    return Math.PI * circle.Radius * circle.Radius;
}

// GOOD - pattern matching combines the check and the binding
if (shape is Circle circle) {
    return Math.PI * circle.Radius * circle.Radius;
}

// GOOD - switch expression, exhaustive with a discard pattern
double Area(Shape shape) => shape switch
{
    Circle c => Math.PI * c.Radius * c.Radius,
    Square s => s.Side * s.Side,
    _ => throw new ArgumentException($"Unknown shape: {shape.GetType().Name}")
};
```

---

## 8. Naming Conventions

### Rule 8.1: Follow Standard .NET Casing
- Classes, methods, properties, public fields, and namespaces: `PascalCase`
- Local variables and private fields: `camelCase`, private fields optionally prefixed with `_`
- Interfaces: `PascalCase` prefixed with `I`

```csharp
// GOOD
public interface IPaymentGateway { }

public class OrderService
{
    private readonly IPaymentGateway _paymentGateway;
    private int _retryCount;

    public decimal CalculateTotal(Order order) { ... }
}
```

### Rule 8.2: Boolean Properties Read as Predicates
- Prefix with `Is`, `Has`, `Can`, or `Should`

```csharp
// BAD
public bool Active { get; set; }

// GOOD
public bool IsActive { get; set; }
public bool HasPermission { get; set; }
```

---

## 9. Testing

### Rule 9.1: Use xUnit with Arrange-Act-Assert and `[Theory]` for Parameterized Cases
- Structure tests with a blank line between Arrange, Act, and Assert
- Use `[Theory]` + `[InlineData]` instead of copy-pasted `[Fact]` methods for the same behavior with different inputs

```csharp
public class AccountTests
{
    [Fact]
    public void Withdraw_ThrowsInsufficientFundsException_WhenBalanceIsInsufficient()
    {
        // Arrange
        var account = new Account(balance: 50m);

        // Act & Assert
        Assert.Throws<InsufficientFundsException>(() => account.Withdraw(100m));
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("\t")]
    public void IsBlank_ReturnsTrue_WhenInputIsWhitespaceOnly(string input)
    {
        Assert.True(StringUtils.IsBlank(input));
    }
}
```

---

## 10. Common LLM Mistakes to Avoid

- Calling `.Result` or `.Wait()` on a `Task` instead of `await`, risking deadlocks
- Using `async void` for anything other than top-level event handlers
- Using `throw ex;` instead of `throw;` when rethrowing, losing the original stack trace
- Using the null-forgiving operator (`!`) without a comment justifying why the value can't be null
- Enumerating an `IEnumerable<T>` multiple times instead of materializing with `.ToList()`
- Catching `Exception` generically instead of specific exception types
- Writing hand-rolled immutable classes instead of `record` on C# 9+
- Forgetting `using` for `IDisposable` resources, or implementing `IDisposable` without the standard dispose pattern
- Using manual `is` + cast instead of pattern matching (`is Type variable`)
- Disabling nullable reference types (`#nullable disable`) instead of fixing the underlying nullability issue
