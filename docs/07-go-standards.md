# Go Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Error Handling - No Silent Errors

### Rule 1.1: Always Handle Returned Errors
- Go functions signal failure through return values, not exceptions
- Every error return must be checked - never discard with `_` unless truly intentional and documented

```go
// BAD - discarding error silently
data, _ := os.ReadFile("config.json")

// BAD - using _ when error matters
conn, _ := db.Connect(dsn)
defer conn.Close()

// GOOD - check every error
data, err := os.ReadFile("config.json")
if err != nil {
    return fmt.Errorf("reading config: %w", err)
}
```

### Rule 1.2: Wrap Errors with Context Using `%w`
- Use `fmt.Errorf("context: %w", err)` to wrap errors with context
- Wrapping preserves the error chain for `errors.Is` and `errors.As` checks
- Do NOT use `errors.New("context: " + err.Error())` - it breaks error unwrapping

```go
// BAD - breaks error chain
func findUser(id string) (*User, error) {
    user, err := db.QueryRow(...)
    if err != nil {
        return nil, errors.New("db error: " + err.Error())
    }
    return user, nil
}

// GOOD - wraps with context, preserves chain
func findUser(id string) (*User, error) {
    user, err := db.QueryRow(...)
    if err != nil {
        return nil, fmt.Errorf("findUser %s: %w", id, err)
    }
    return user, nil
}
```

### Rule 1.3: Define Sentinel Errors for Callers to Check
- Use `var ErrNotFound = errors.New("not found")` for errors callers need to check
- Check with `errors.Is(err, ErrNotFound)` not with string comparison

```go
// GOOD - sentinel error for expected conditions
var (
    ErrNotFound    = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
)

func GetOrder(id string) (*Order, error) {
    order, exists := store[id]
    if !exists {
        return nil, fmt.Errorf("order %s: %w", id, ErrNotFound)
    }
    return order, nil
}

// Caller checks:
if errors.Is(err, ErrNotFound) {
    // handle not found
}
```

---

## 2. Goroutine Patterns

### Rule 2.1: Never Start a Goroutine Without Knowing When It Stops
- Every goroutine needs a defined exit condition
- Goroutine leaks cause memory leaks and prevent clean shutdown

```go
// BAD - goroutine runs forever, no way to stop it
go func() {
    for {
        process()
    }
}()

// GOOD - goroutine respects context cancellation
func startWorker(ctx context.Context) {
    go func() {
        for {
            select {
            case <-ctx.Done():
                return
            default:
                process()
            }
        }
    }()
}
```

### Rule 2.2: Use `sync.WaitGroup` for Goroutine Lifecycle
- Call `wg.Add(n)` before starting goroutines, not inside them
- Always defer `wg.Done()` as the first statement in the goroutine

```go
// BAD - race condition on Add
for _, item := range items {
    go func(i Item) {
        wg.Add(1)  // too late, race with Wait
        defer wg.Done()
        process(i)
    }(item)
}

// GOOD - Add before goroutine starts
var wg sync.WaitGroup
for _, item := range items {
    wg.Add(1)
    go func(i Item) {
        defer wg.Done()
        process(i)
    }(item)
}
wg.Wait()
```

### Rule 2.3: Limit Goroutine Concurrency with Semaphores
- Unbounded goroutine creation exhausts resources
- Use a buffered channel as a semaphore to bound concurrency

```go
// BAD - creates 10,000 goroutines simultaneously
for _, item := range largeSlice {
    go process(item)
}

// GOOD - limits to maxWorkers concurrent goroutines
const maxWorkers = 10
sem := make(chan struct{}, maxWorkers)

for _, item := range largeSlice {
    sem <- struct{}{}  // acquire
    go func(i Item) {
        defer func() { <-sem }()  // release
        process(i)
    }(item)
}
```

---

## 3. Channel Usage

### Rule 3.1: Close Channels From the Sender, Not the Receiver
- Only the goroutine that sends to a channel should close it
- Closing a closed channel panics; closing a channel with active senders causes data races

```go
// BAD - receiver closes channel
func consumer(ch <-chan int) {
    for v := range ch {
        process(v)
    }
    close(ch)  // wrong - consumer should not close
}

// GOOD - sender closes after done
func producer(ch chan<- int) {
    defer close(ch)
    for _, v := range data {
        ch <- v
    }
}
```

### Rule 3.2: Use `select` with `default` for Non-Blocking Operations
- A `select` without `default` blocks until a case is ready
- Add `default` when you want non-blocking channel operations

```go
// GOOD - non-blocking send
func trySend(ch chan<- Event, event Event) bool {
    select {
    case ch <- event:
        return true
    default:
        return false  // channel full, drop event
    }
}

// GOOD - non-blocking receive with timeout
select {
case result := <-resultCh:
    handle(result)
case <-time.After(5 * time.Second):
    log.Println("timeout waiting for result")
case <-ctx.Done():
    return ctx.Err()
}
```

---

## 4. Defer, Panic, and Recover

### Rule 4.1: Use `defer` for Resource Cleanup
- Always defer cleanup of opened resources immediately after the Open/Create call
- Deferred calls execute even if the function panics

```go
// BAD - forgetting to close in error paths
f, err := os.Open(path)
if err != nil {
    return err
}
// ... if this panics, f is never closed
f.Close()

// GOOD - defer immediately after successful open
f, err := os.Open(path)
if err != nil {
    return err
}
defer f.Close()
```

### Rule 4.2: Only Use `panic` for Unrecoverable Programming Errors
- `panic` is not an error handling mechanism - it is for invariant violations
- Never `panic` on expected runtime errors (network failures, file not found, invalid input)
- Use `panic` for: nil pointer dereference detected early, violated internal invariant, developer error

```go
// BAD - panicking on expected runtime error
func ReadConfig(path string) Config {
    data, err := os.ReadFile(path)
    if err != nil {
        panic(err)  // should return error
    }
    // ...
}

// GOOD - return error
func ReadConfig(path string) (Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return Config{}, fmt.Errorf("reading config: %w", err)
    }
    // ...
}

// ACCEPTABLE panic - nil pointer guard for programming error
func (s *Service) Process(ctx context.Context) {
    if s == nil {
        panic("Service.Process called on nil receiver")
    }
    // ...
}
```

### Rule 4.3: Recover Only at Top-Level Boundaries
- Use `recover()` only in deferred functions at the top of call stacks (HTTP handlers, goroutines)
- Always convert panics to errors and log them

```go
// GOOD - recover at HTTP handler boundary
func safeHandler(h http.HandlerFunc) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if rec := recover(); rec != nil {
                log.Printf("panic in handler: %v\n%s", rec, debug.Stack())
                http.Error(w, "Internal Server Error", http.StatusInternalServerError)
            }
        }()
        h(w, r)
    }
}
```

---

## 5. Interface Design - Small Interfaces

### Rule 5.1: Keep Interfaces Small - One to Three Methods
- Large interfaces are hard to satisfy and hard to mock in tests
- Go proverb: "The bigger the interface, the weaker the abstraction"
- Accept interfaces as parameters; return concrete types

```go
// BAD - large interface is hard to implement and test
type UserService interface {
    Create(user User) error
    Update(user User) error
    Delete(id string) error
    FindByID(id string) (*User, error)
    FindByEmail(email string) (*User, error)
    List(page, size int) ([]User, error)
    Count() (int, error)
}

// GOOD - focused interfaces per use case
type UserFinder interface {
    FindByID(ctx context.Context, id string) (*User, error)
}

type UserWriter interface {
    Save(ctx context.Context, user *User) error
}

// Consumers declare only what they need
type OrderHandler struct {
    users UserFinder
}
```

### Rule 5.2: Define Interfaces at the Consumer, Not the Producer
- Interfaces should be defined where they are used, not where they are implemented
- The consumer knows what behavior it needs; the producer should not know who consumes it

```go
// BAD - producer defines the interface (Java style)
// user_service.go
type UserServiceInterface interface {
    FindByID(id string) (*User, error)
}
type UserService struct{}
func (s *UserService) FindByID(id string) (*User, error) { ... }

// GOOD - consumer defines the interface it needs
// order_handler.go
type userLookup interface {  // defined here, in the consuming package
    FindByID(ctx context.Context, id string) (*User, error)
}

type OrderHandler struct {
    users userLookup  // UserService satisfies this implicitly
}
```

---

## 6. Naming Conventions

### Rule 6.1: Use MixedCaps, Not Underscores
- Go uses `MixedCaps` (exported) and `mixedCaps` (unexported), not `snake_case`
- Never use `snake_case` for Go identifiers

```go
// BAD - snake_case
user_id := "123"
func get_user(user_id string) {}
type User_Service struct{}

// GOOD - MixedCaps
userID := "123"
func getUser(userID string) {}
type UserService struct{}
```

### Rule 6.2: Acronyms Are All-Caps or All-Lowercase
- Acronyms like `ID`, `URL`, `HTTP`, `JSON` are all caps when exported, all lowercase when unexported

```go
// BAD
type UserId string
func GetUrl() string {}
var httpClient = &http.Client{}

// GOOD
type UserID string
func GetURL() string {}
var httpClient = &http.Client{}  // unexported: lowercase
var HTTPClient = &http.Client{}  // exported: all caps
```

### Rule 6.3: Error Variables Start with `Err`, Error Types End with `Error`
```go
// Sentinel errors
var ErrNotFound = errors.New("not found")
var ErrInvalidInput = errors.New("invalid input")

// Error types (for errors.As)
type ValidationError struct {
    Field   string
    Message string
}
func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation error on %s: %s", e.Field, e.Message)
}
```

---

## 7. Package Organization

### Rule 7.1: Package Names Are Lowercase, Single Words
- No underscores, no mixed case in package names
- Package name should describe what it provides, not what it contains

```go
// BAD
package userService
package user_service
package models

// GOOD
package user
package order
package http   // but only if it adds value - most internal packages
```

### Rule 7.2: Avoid Package-Level Variables for Mutable State
- Package-level vars create hidden global state that is hard to test
- Use dependency injection instead of package-level state

```go
// BAD - package-level database instance
var db *sql.DB

func init() {
    var err error
    db, err = sql.Open("postgres", os.Getenv("DATABASE_URL"))
    if err != nil {
        panic(err)
    }
}

// GOOD - inject dependency
type UserRepository struct {
    db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
    return &UserRepository{db: db}
}
```

---

## 8. Testing - Table-Driven Tests

### Rule 8.1: Use Table-Driven Tests for Multiple Cases
- Table-driven tests reduce code duplication and make it easy to add cases
- Name test cases descriptively; use `t.Run` for subtests

```go
// GOOD - table-driven test
func TestFormatCurrency(t *testing.T) {
    tests := []struct {
        name     string
        amount   float64
        currency string
        want     string
    }{
        {"whole dollars", 100.0, "USD", "$100.00"},
        {"cents", 1.5, "USD", "$1.50"},
        {"zero", 0, "USD", "$0.00"},
        {"negative", -10.5, "USD", "-$10.50"},
    }

    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            got := FormatCurrency(tc.amount, tc.currency)
            if got != tc.want {
                t.Errorf("FormatCurrency(%v, %s) = %q, want %q",
                    tc.amount, tc.currency, got, tc.want)
            }
        })
    }
}
```

### Rule 8.2: Use Interfaces for Testable Dependencies
- Inject dependencies as interfaces so tests can provide fakes
- Do not use `gomock` or `testify/mock` when a simple struct with the right methods is enough

```go
// Fake for testing - no mock framework needed
type fakeUserRepo struct {
    users map[string]*User
}

func (r *fakeUserRepo) FindByID(_ context.Context, id string) (*User, error) {
    u, ok := r.users[id]
    if !ok {
        return nil, ErrNotFound
    }
    return u, nil
}

func TestOrderService_PlaceOrder(t *testing.T) {
    repo := &fakeUserRepo{
        users: map[string]*User{"usr-1": {ID: "usr-1", Name: "Alice"}},
    }
    svc := NewOrderService(repo)
    // test with fake
}
```

---

## 9. context.Context Usage

### Rule 9.1: Always Pass context.Context as the First Argument
- Functions that do I/O, make network calls, or can be cancelled must accept `context.Context`
- `context.Context` is always the first parameter, named `ctx`
- Never store `context.Context` in a struct

```go
// BAD - no context, cannot be cancelled
func (r *UserRepo) FindByID(id string) (*User, error) {
    return r.db.QueryRow("SELECT ...", id)
}

// BAD - context stored in struct
type Service struct {
    ctx context.Context  // wrong
}

// GOOD - context as first parameter
func (r *UserRepo) FindByID(ctx context.Context, id string) (*User, error) {
    return r.db.QueryRowContext(ctx, "SELECT ...", id)
}
```

### Rule 9.2: Propagate Context Cancellation
- Use `ctx.Done()` channel to detect cancellation in long-running operations
- Pass context to all downstream calls that accept it

```go
// BAD - ignores context cancellation
func processItems(ctx context.Context, items []Item) error {
    for _, item := range items {
        process(item)  // does not check ctx
    }
    return nil
}

// GOOD - checks context between iterations
func processItems(ctx context.Context, items []Item) error {
    for _, item := range items {
        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
        }
        if err := process(ctx, item); err != nil {  // passes ctx
            return fmt.Errorf("processing item %s: %w", item.ID, err)
        }
    }
    return nil
}
```

---

## 10. Memory Management

### Rule 10.1: Pre-allocate Slices and Maps When Size is Known
- `make([]T, 0, n)` pre-allocates backing array, avoiding repeated re-allocation during `append`
- `make(map[K]V, n)` hints the map size to reduce rehashing

```go
// BAD - slice grows by re-allocating repeatedly
results := []string{}
for _, item := range items {
    results = append(results, process(item))
}

// GOOD - pre-allocate when length is known
results := make([]string, 0, len(items))
for _, item := range items {
    results = append(results, process(item))
}
```

### Rule 10.2: Avoid Memory Leaks with Goroutines and Channels
- Goroutines holding references to large objects prevent GC
- Channel sends that block forever leak the goroutine and the closure's captured variables

```go
// BAD - goroutine leaks if resultCh is never read
func doWork(data []byte) {
    resultCh := make(chan Result)
    go func() {
        resultCh <- compute(data)  // blocks forever if no receiver
    }()
}

// GOOD - buffered channel or explicit cancellation
func doWork(ctx context.Context, data []byte) (Result, error) {
    resultCh := make(chan Result, 1)
    go func() {
        resultCh <- compute(data)
    }()
    select {
    case result := <-resultCh:
        return result, nil
    case <-ctx.Done():
        return Result{}, ctx.Err()
    }
}
```

---

## 11. Common LLM Mistakes to Avoid

- Ignoring error returns with `_` on operations that can fail in production
- Using `panic` for network or database errors instead of returning errors
- Closing channels from the receiver goroutine (causes panic in the sender)
- Forgetting to pass `context.Context` to database and HTTP calls
- Using `sync.Mutex` in copied structs (copy the lock, not just the pointer)
- Generating Java-style large interfaces instead of small, focused Go interfaces
- Using `snake_case` for variable and function names instead of `camelCase`
- Not pre-allocating slices/maps when the capacity is known ahead of time
- Starting goroutines without a defined exit condition (goroutine leaks)
