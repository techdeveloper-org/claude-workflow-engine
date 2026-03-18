# Rust Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Ownership and Borrowing Rules

### Rule 1.1: Prefer Borrowing Over Cloning
- Clone creates a deep copy and allocates heap memory - use it only when ownership is required
- Pass references (`&T` or `&mut T`) when the function only needs to read or modify without taking ownership
- Clone is acceptable for small Copy types and when it simplifies code without a performance cost

```rust
// BAD - unnecessary clone allocates heap memory
fn print_name(name: String) {
    println!("{}", name);
}
let user_name = String::from("Alice");
print_name(user_name.clone());  // name is still needed after this

// GOOD - borrow instead of clone
fn print_name(name: &str) {
    println!("{}", name);
}
let user_name = String::from("Alice");
print_name(&user_name);  // no allocation, user_name still usable
```

### Rule 1.2: Minimize the Scope of Mutable References
- Hold `&mut` borrows for the shortest possible time
- Rust enforces no aliasing of mutable references - keeping them narrow prevents borrow checker fights

```rust
// BAD - mutable borrow held longer than needed
fn process(data: &mut Vec<i32>) {
    let first = &mut data[0];
    expensive_operation();  // holds mut borrow during unrelated work
    *first += 1;
}

// GOOD - narrow the mutable borrow
fn process(data: &mut Vec<i32>) {
    expensive_operation();  // mut borrow not held here
    data[0] += 1;           // mut borrow only during mutation
}
```

### Rule 1.3: Use `Arc<T>` and `Mutex<T>` Only When Shared Ownership Is Required
- Do not default to `Arc<Mutex<T>>` for all shared state - it adds overhead and can deadlock
- Use `Rc<T>` for single-threaded shared ownership, `Arc<T>` for multi-threaded
- Consider channel-based communication over shared mutable state

```rust
// BAD - wrapping everything in Arc<Mutex<>> as a habit
let state = Arc::new(Mutex::new(AppState::default()));

// GOOD - only use Arc<Mutex<>> when truly shared across threads
// For single-threaded contexts: pass references directly
// For multi-threaded: use channels or Arc<RwLock<>> for reader-heavy access
use std::sync::{Arc, RwLock};
let config = Arc::new(RwLock::new(Config::default()));  // many readers, rare writes
```

---

## 2. Lifetime Annotations

### Rule 2.1: Annotate Lifetimes Only When the Compiler Requires It
- Rust infers lifetimes in most cases (lifetime elision rules)
- Add explicit lifetime annotations when the compiler asks or when it clarifies the contract
- Name lifetimes descriptively for complex signatures: `'config`, `'request`

```rust
// Compiler infers lifetime - no annotation needed (elision rule applies)
fn first_word(s: &str) -> &str {
    let bytes = s.as_bytes();
    for (i, &item) in bytes.iter().enumerate() {
        if item == b' ' { return &s[0..i]; }
    }
    &s[..]
}

// Explicit lifetime needed - compiler cannot infer which input the output borrows from
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// Struct holding a reference requires lifetime annotation
struct Excerpt<'a> {
    part: &'a str,
}
```

### Rule 2.2: Prefer Owned Types in Structs When Lifetime Complexity Is High
- Struct lifetimes make the struct harder to use and require callers to manage lifetimes
- Clone/allocate in structs to avoid lifetime annotations unless performance is critical

```rust
// HARDER TO USE - struct tied to the lifetime of the input string
struct Parser<'a> {
    input: &'a str,
    position: usize,
}

// EASIER TO USE - owns its data, no lifetime needed
struct Parser {
    input: String,
    position: usize,
}
```

---

## 3. Error Handling - Result and Option

### Rule 3.1: Never Use `unwrap()` in Production Code
- `unwrap()` panics on `None` or `Err` - this crashes the entire thread/process
- Use `?` operator to propagate errors, or match to handle them explicitly
- `unwrap()` is acceptable ONLY in tests and in contexts where a panic is truly impossible

```rust
// BAD - panics in production if config file is missing
let config = std::fs::read_to_string("config.toml").unwrap();

// BAD - panics if user not found
let user = users.get(&user_id).unwrap();

// GOOD - propagate with ?
fn load_config() -> Result<Config, ConfigError> {
    let content = std::fs::read_to_string("config.toml")
        .map_err(|e| ConfigError::Io(e))?;
    let config: Config = toml::from_str(&content)
        .map_err(|e| ConfigError::Parse(e))?;
    Ok(config)
}

// GOOD - handle None explicitly
let user = users.get(&user_id)
    .ok_or_else(|| UserError::NotFound(user_id.clone()))?;
```

### Rule 3.2: Never Use `expect()` in Production Code
- `expect()` is `unwrap()` with a message - it still panics
- Acceptable in examples, tests, and startup code where failure is truly fatal

```rust
// BAD in production - still panics
let port: u16 = env::var("PORT").expect("PORT must be set").parse().expect("PORT must be a number");

// GOOD - return Result
fn get_port() -> Result<u16, ConfigError> {
    let port_str = env::var("PORT")
        .map_err(|_| ConfigError::MissingVar("PORT"))?;
    port_str.parse::<u16>()
        .map_err(|_| ConfigError::InvalidVar("PORT", "must be a valid port number"))
}
```

### Rule 3.3: Use `?` to Propagate Errors - Do Not Nest Match Arms
- The `?` operator is the idiomatic way to propagate errors in Rust
- Avoid deeply nested `match` on `Result` - it becomes hard to read

```rust
// BAD - nested match is verbose and hard to read
fn read_number(path: &str) -> Result<i32, AppError> {
    match std::fs::read_to_string(path) {
        Ok(content) => {
            match content.trim().parse::<i32>() {
                Ok(n) => Ok(n),
                Err(e) => Err(AppError::Parse(e)),
            }
        }
        Err(e) => Err(AppError::Io(e)),
    }
}

// GOOD - ? operator propagates cleanly
fn read_number(path: &str) -> Result<i32, AppError> {
    let content = std::fs::read_to_string(path)?;
    let n = content.trim().parse::<i32>()?;
    Ok(n)
}
```

### Rule 3.4: Define Custom Error Types for Libraries
- Use `thiserror` for defining error types in libraries and services
- Use `anyhow` for application-level code where you just need to propagate context

```rust
// Library error type using thiserror
use thiserror::Error;

#[derive(Debug, Error)]
pub enum OrderError {
    #[error("order {0} not found")]
    NotFound(String),

    #[error("order {id} already shipped: cannot modify")]
    AlreadyShipped { id: String },

    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}

// Application code using anyhow for flexible error propagation
use anyhow::{Context, Result};

fn run() -> Result<()> {
    let config = load_config().context("loading application config")?;
    start_server(config).context("starting HTTP server")?;
    Ok(())
}
```

---

## 4. Trait Design

### Rule 4.1: Keep Traits Focused on One Capability
- Traits with many methods are hard to implement and hard to bound
- Split large traits into smaller, composable ones

```rust
// BAD - large trait with too many responsibilities
pub trait UserService {
    fn find_by_id(&self, id: &str) -> Result<User, UserError>;
    fn find_by_email(&self, email: &str) -> Result<User, UserError>;
    fn create(&self, user: NewUser) -> Result<User, UserError>;
    fn update(&self, user: User) -> Result<User, UserError>;
    fn delete(&self, id: &str) -> Result<(), UserError>;
    fn send_welcome_email(&self, user: &User) -> Result<(), EmailError>;
}

// GOOD - focused traits per capability
pub trait UserRepository {
    fn find_by_id(&self, id: &str) -> Result<Option<User>, DbError>;
    fn save(&mut self, user: &User) -> Result<(), DbError>;
}

pub trait EmailSender {
    fn send(&self, to: &str, subject: &str, body: &str) -> Result<(), EmailError>;
}
```

### Rule 4.2: Use `impl Trait` in Function Signatures for Simple Cases
- `impl Trait` in argument position is cleaner than `T: Trait` for single-use generics
- Use named generics when the type parameter appears multiple times or you need to name it

```rust
// BAD - named generic used only once
fn process<T: Iterator<Item = String>>(items: T) { ... }

// GOOD - impl Trait is cleaner for single-use
fn process(items: impl Iterator<Item = String>) { ... }

// GOOD - named generic when needed in multiple places
fn zip_with<T, F>(a: T, b: T, f: F) -> impl Iterator
where
    T: Iterator,
    F: Fn(T::Item, T::Item) -> T::Item,
{ ... }
```

---

## 5. Module Organization

### Rule 5.1: Use `mod.rs` or File-Level Modules, Not Both
- Rust supports two styles: `module/mod.rs` and `module.rs`
- Pick one style per project; mixing causes confusion
- Prefer file-level modules (`module.rs`) in modern Rust code (2018 edition+)

```
// GOOD - file-level modules (modern style)
src/
  main.rs
  user.rs        <- mod user; in main.rs
  user/
    repository.rs
    service.rs

// ACCEPTABLE - directory modules (older style)
src/
  main.rs
  user/
    mod.rs
    repository.rs
    service.rs
```

### Rule 5.2: Control Visibility Explicitly
- `pub` makes an item public to everyone - use it only for the public API
- `pub(crate)` shares within the crate only
- `pub(super)` shares with the parent module only
- Keep most implementation details private

```rust
// BAD - exposing internals publicly
pub struct Order {
    pub id: String,
    pub internal_state: OrderState,  // should not be public
    pub db_row_id: i64,              // should not be public
}

// GOOD - controlled visibility
pub struct Order {
    pub id: String,
    pub status: OrderStatus,
    state: OrderState,     // private implementation detail
    db_row_id: i64,        // private persistence detail
}

impl Order {
    pub fn is_shipped(&self) -> bool {
        matches!(self.state, OrderState::Shipped)
    }
}
```

---

## 6. Unsafe Usage

### Rule 6.1: Minimize Unsafe Blocks - Isolate and Document
- `unsafe` code opts out of Rust's safety guarantees
- Confine `unsafe` to the smallest possible scope
- Every `unsafe` block must have a comment explaining why it is sound

```rust
// BAD - large unsafe block with mixed safe and unsafe operations
unsafe {
    let ptr = data.as_ptr();
    let safe_computation = 1 + 1;  // this does not need to be unsafe
    *ptr.add(offset) = value;      // this is the actual unsafe operation
}

// GOOD - minimal unsafe scope with justification comment
let ptr = data.as_ptr();
let safe_computation = 1 + 1;
// SAFETY: offset is bounds-checked above (line N), data is valid for writes
unsafe { *ptr.add(offset) = value; }
```

---

## 7. Cargo Clippy Compliance

### Rule 7.1: Fix All Clippy Warnings Before Committing
- Run `cargo clippy -- -D warnings` to treat warnings as errors
- Do not allow clippy lints without explicit justification
- Common clippy fixes that LLMs commonly miss:

```rust
// Clippy: use .is_empty() instead of len() == 0
if items.len() == 0 { ... }      // BAD
if items.is_empty() { ... }      // GOOD

// Clippy: use if let instead of match with _ => ()
match opt { Some(v) => use(v), None => () }  // BAD
if let Some(v) = opt { use(v); }              // GOOD

// Clippy: use .map() instead of match on Option
match opt { Some(v) => Some(transform(v)), None => None }  // BAD
opt.map(transform)                                          // GOOD

// Clippy: avoid needless_return
fn double(x: i32) -> i32 { return x * 2; }  // BAD
fn double(x: i32) -> i32 { x * 2 }          // GOOD
```

---

## 8. Documentation Comments

### Rule 8.1: Document Public API Items
- All `pub` functions, structs, traits, and modules should have `///` doc comments
- Include examples in doc comments using ```rust code blocks
- Document panics with `# Panics` section if the function can panic

```rust
/// Finds an order by its unique identifier.
///
/// Returns `None` if no order exists with the given ID.
///
/// # Examples
///
/// ```
/// let repo = OrderRepository::new(db);
/// match repo.find_by_id("ord-123").await? {
///     Some(order) => println!("Found: {}", order.id),
///     None => println!("Order not found"),
/// }
/// ```
///
/// # Errors
///
/// Returns `DbError` if the database query fails.
pub async fn find_by_id(&self, id: &str) -> Result<Option<Order>, DbError> {
    // ...
}
```

---

## 9. Testing Patterns

### Rule 9.1: Use `#[cfg(test)]` Modules for Unit Tests
- Place unit tests in the same file as the code under test inside a `#[cfg(test)]` module
- Integration tests go in the `tests/` directory

```rust
// In src/order.rs
pub fn calculate_total(items: &[OrderItem]) -> Money {
    items.iter().map(|i| i.price * i.quantity).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn total_of_empty_order_is_zero() {
        assert_eq!(calculate_total(&[]), Money::ZERO);
    }

    #[test]
    fn total_sums_all_items() {
        let items = vec![
            OrderItem { price: Money::from(10), quantity: 2 },
            OrderItem { price: Money::from(5), quantity: 3 },
        ];
        assert_eq!(calculate_total(&items), Money::from(35));
    }
}
```

### Rule 9.2: Use `tokio::test` for Async Tests
- Annotate async test functions with `#[tokio::test]`
- Use `#[tokio::test(flavor = "multi_thread")]` for tests that need multi-threaded runtime

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn fetch_user_returns_none_when_not_found() {
        let repo = InMemoryUserRepository::new();
        let result = repo.find_by_id("nonexistent").await;
        assert!(matches!(result, Ok(None)));
    }
}
```

---

## 10. Async with Tokio

### Rule 10.1: Do Not Block the Async Runtime
- Calling blocking operations (file I/O, CPU-heavy work) on an async thread starves other tasks
- Use `tokio::task::spawn_blocking` for blocking operations inside async code

```rust
// BAD - blocks the Tokio thread with synchronous file I/O
async fn load_data() -> Result<Vec<u8>, IoError> {
    std::fs::read("large_file.bin").map_err(IoError::from)  // blocking!
}

// GOOD - offload blocking I/O to the blocking thread pool
async fn load_data() -> Result<Vec<u8>, IoError> {
    tokio::task::spawn_blocking(|| std::fs::read("large_file.bin"))
        .await
        .map_err(|e| IoError::Join(e))?
        .map_err(IoError::Io)
}

// BEST - use async file I/O directly
async fn load_data() -> Result<Vec<u8>, IoError> {
    tokio::fs::read("large_file.bin").await.map_err(IoError::from)
}
```

### Rule 10.2: Cancel-Safe Async Functions
- When a future is dropped (cancelled), any work not committed to an external system is lost
- Be aware of which tokio operations are cancel-safe and which are not

```rust
// tokio::io::AsyncReadExt::read() is NOT cancel-safe - may partially read
// tokio::sync::mpsc::Receiver::recv() IS cancel-safe
// tokio::time::sleep() IS cancel-safe

// Use select! carefully - branches that lose the race are cancelled
tokio::select! {
    result = socket.read(&mut buf) => {  // careful: partial read if cancelled
        // handle result
    }
    _ = shutdown_signal() => {
        // shutdown
    }
}
```

---

## 11. Common LLM Mistakes to Avoid

- Using `.unwrap()` or `.expect()` on `Result` or `Option` in non-test, non-startup code
- Cloning everything to avoid borrow checker issues instead of restructuring ownership
- Defining `impl From<SomeError> for Box<dyn Error>` instead of a proper error enum
- Generating `pub` on all struct fields instead of using accessor methods
- Using `String` parameters instead of `&str` (always prefer borrowing string slices)
- Blocking the Tokio runtime with `std::fs` or `std::thread::sleep` inside `async fn`
- Forgetting to add `#[allow(dead_code)]` comment justification or fixing the root cause
- Using `unsafe` without a `// SAFETY:` comment explaining why the code is sound
- Adding unnecessary `.clone()` calls inside iterators when a reference would work
- Using `Box<dyn Error>` as a return type in library code instead of a concrete error type
