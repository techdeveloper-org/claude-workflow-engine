# Swift Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Optionals - Safe Unwrapping

### Rule 1.1: Prefer `guard let` Over `if let` for Early Exit
- `guard let` unwraps and makes the value available for the rest of the scope
- Use `guard let` at function entry to validate preconditions
- Use `if let` when the unwrapped value is only needed within the conditional block

```swift
// BAD - deeply nested if let
func processOrder(orderId: String?) {
    if let id = orderId {
        if let order = findOrder(id: id) {
            if let user = order.user {
                send(to: user, order: order)
            }
        }
    }
}

// GOOD - guard let exits early and keeps code flat
func processOrder(orderId: String?) {
    guard let id = orderId else {
        logger.warn("processOrder called with nil orderId")
        return
    }
    guard let order = findOrder(id: id) else {
        logger.warn("Order \(id) not found")
        return
    }
    guard let user = order.user else {
        logger.warn("Order \(id) has no associated user")
        return
    }
    send(to: user, order: order)
}
```

### Rule 1.2: Never Force-Unwrap (`!`) in Production Code
- Force-unwrap crashes the app if the value is `nil`
- Only acceptable in unit tests (to fail the test) and in IBOutlets (system-guaranteed)
- Use `guard let`, `if let`, `??`, or `map`/`flatMap` instead

```swift
// BAD - crashes if userID is nil or URL is invalid
let userID = data["id"] as! String
let url = URL(string: rawURL)!

// GOOD - handle nil explicitly
guard let userID = data["id"] as? String else {
    throw ParseError.missingField("id")
}
guard let url = URL(string: rawURL) else {
    throw ValidationError.invalidURL(rawURL)
}

// GOOD - use ?? for default values
let displayName = user.name ?? "Unknown User"
```

### Rule 1.3: Use Optional Chaining for Optional Property Access
- Optional chaining (`?.`) returns `nil` if any link is `nil` instead of crashing

```swift
// BAD - multiple if let for property access
if let user = session.currentUser {
    if let address = user.primaryAddress {
        label.text = address.city
    }
}

// GOOD - optional chaining
label.text = session.currentUser?.primaryAddress?.city ?? "Unknown City"
```

---

## 2. Protocol-Oriented Programming

### Rule 2.1: Define Capabilities as Protocols, Not Inheritance
- Prefer protocol composition over deep class inheritance hierarchies
- Use `protocol` to define capabilities; use `extension` to provide default implementations
- Structs can conform to protocols - you do not need classes for protocol adoption

```swift
// BAD - inheritance-based with rigid hierarchy
class Animal {
    func breathe() { }
}
class Bird: Animal {
    func fly() { }
}
class Penguin: Bird {  // penguins cannot fly, but Bird.fly() exists
    override func fly() { /* cannot fly */ }
}

// GOOD - protocol-based with composition
protocol Breathable {
    func breathe()
}
protocol Flyable {
    func fly()
}

struct Bird: Breathable, Flyable {
    func breathe() { }
    func fly() { }
}
struct Penguin: Breathable {  // does not conform to Flyable
    func breathe() { }
}
```

### Rule 2.2: Use Protocol Extensions for Default Implementations
- Protocol extensions provide default behavior for conforming types
- This avoids repeating the same implementation in every conforming type

```swift
protocol Loggable {
    var logIdentifier: String { get }
    func log(_ message: String)
}

// Default implementation via extension
extension Loggable {
    func log(_ message: String) {
        print("[\(logIdentifier)] \(message)")
    }
}

// Conforming types get log() for free
struct OrderService: Loggable {
    var logIdentifier: String { "OrderService" }
    // log() is available without implementing it
}
```

---

## 3. Value Types vs Reference Types

### Rule 3.1: Default to Structs (Value Types)
- Structs are value types - copies are independent; no shared mutable state
- Use `struct` for models, data transfer objects, and domain values
- Use `class` only when reference semantics are needed (shared identity, inheritance, ObjC interop)

```swift
// GOOD - struct for data model
struct User {
    let id: UUID
    var name: String
    var email: String
}

// Modifying a copy does not affect the original
var alice = User(id: UUID(), name: "Alice", email: "alice@example.com")
var aliceCopy = alice
aliceCopy.name = "Alice Modified"
// alice.name is still "Alice"

// GOOD - class when shared identity/state is needed
class SessionManager {
    var currentUser: User?
    static let shared = SessionManager()
    private init() {}
}
```

### Rule 3.2: Make Value Types Immutable When Possible
- Use `let` for value type properties that do not change after initialization
- Prefer immutable values; mutate only when genuinely necessary

```swift
// BAD - everything mutable by default
struct Order {
    var id: UUID
    var createdAt: Date
    var items: [OrderItem]
    var status: OrderStatus
}

// GOOD - immutable what should be immutable
struct Order {
    let id: UUID          // never changes
    let createdAt: Date   // never changes
    var items: [OrderItem]    // can change (add/remove items)
    var status: OrderStatus   // can change (shipped, etc.)
}
```

---

## 4. SwiftUI Patterns

### Rule 4.1: Keep Views Focused - Extract Subviews
- A View body that exceeds 30-40 lines should be broken into subviews
- Extract subviews as computed properties or separate View structs

```swift
// BAD - monolithic view body
struct OrderListView: View {
    var body: some View {
        NavigationView {
            List(orders) { order in
                HStack {
                    VStack(alignment: .leading) {
                        Text(order.id).font(.headline)
                        Text(order.status.displayName).font(.caption).foregroundColor(.secondary)
                    }
                    Spacer()
                    Text(order.total.formatted()).font(.body).bold()
                }
                .padding(.vertical, 4)
            }
            .navigationTitle("Orders")
        }
    }
}

// GOOD - extracted subview
struct OrderListView: View {
    var body: some View {
        NavigationView {
            List(orders) { order in
                OrderRowView(order: order)
            }
            .navigationTitle("Orders")
        }
    }
}

struct OrderRowView: View {
    let order: Order

    var body: some View {
        HStack {
            orderInfo
            Spacer()
            Text(order.total.formatted()).font(.body).bold()
        }
        .padding(.vertical, 4)
    }

    private var orderInfo: some View {
        VStack(alignment: .leading) {
            Text(order.id).font(.headline)
            Text(order.status.displayName).font(.caption).foregroundColor(.secondary)
        }
    }
}
```

### Rule 4.2: Use `@State` for Local UI State, `@Binding` for Child Communication
- `@State` is private local state owned by the view - do not pass it down
- `@Binding` creates a two-way connection to state owned by a parent view
- Do NOT use `@State` for business data - use a ViewModel or `@Observable`

```swift
// BAD - @State for data that belongs in a ViewModel
struct UserProfileView: View {
    @State private var userName: String = ""
    @State private var userEmail: String = ""
    @State private var isLoading: Bool = false
}

// GOOD - @State for local UI concerns only
struct UserProfileView: View {
    @State private var isEditingName: Bool = false  // UI state: is the name field focused?
    @Bindable var viewModel: UserProfileViewModel   // business state in ViewModel

    var body: some View {
        TextField("Name", text: $viewModel.name)
    }
}

// GOOD - @Binding for parent-owned state passed to child
struct ToggleRow: View {
    let label: String
    @Binding var isOn: Bool  // owned by parent, two-way binding

    var body: some View {
        Toggle(label, isOn: $isOn)
    }
}
```

### Rule 4.3: Use `@Observable` for ViewModels (iOS 17+) or `ObservableObject` (iOS 16-)
- `@Observable` (iOS 17+) is simpler - no need for `@Published` on every property
- `ObservableObject` with `@Published` for iOS 16 support

```swift
// iOS 17+ - @Observable macro
@Observable
class OrderViewModel {
    var orders: [Order] = []
    var isLoading: Bool = false
    var errorMessage: String?

    func loadOrders() async {
        isLoading = true
        defer { isLoading = false }
        do {
            orders = try await orderService.fetchAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// iOS 16 compatible - ObservableObject
final class OrderViewModel: ObservableObject {
    @Published var orders: [Order] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
}
```

---

## 5. Error Handling

### Rule 5.1: Use `throws` / `do-catch` for Recoverable Errors
- Define errors as enums conforming to `Error` (or `LocalizedError` for user messages)
- Throw errors instead of returning `nil` when a failure reason matters to the caller

```swift
// BAD - nil return hides the failure reason
func parseDate(from string: String) -> Date? {
    return dateFormatter.date(from: string)
}

// GOOD - throw with context
enum DateParseError: LocalizedError {
    case invalidFormat(String)
    case outOfRange(Date)

    var errorDescription: String? {
        switch self {
        case .invalidFormat(let s): return "Invalid date format: \(s)"
        case .outOfRange(let d): return "Date out of supported range: \(d)"
        }
    }
}

func parseDate(from string: String) throws -> Date {
    guard let date = dateFormatter.date(from: string) else {
        throw DateParseError.invalidFormat(string)
    }
    return date
}
```

### Rule 5.2: Use `Result<T, E>` for Async Completion Handlers
- `Result` makes success and failure explicit in callback-based APIs
- Prefer `async throws` over `Result` in new code (Swift 5.5+)

```swift
// Legacy callback-based API (pre-Swift 5.5)
func fetchOrder(id: String, completion: @escaping (Result<Order, OrderError>) -> Void) {
    // ...
    completion(.success(order))
    // or
    completion(.failure(.notFound(id)))
}

// Modern async/await (preferred for new code)
func fetchOrder(id: String) async throws -> Order {
    guard let order = await orderRepository.find(id: id) else {
        throw OrderError.notFound(id)
    }
    return order
}
```

---

## 6. Naming Conventions (Apple Style)

### Rule 6.1: Method Names Should Read as English Sentences at the Call Site
- Follow Swift API Design Guidelines: methods should read naturally at call sites
- Booleans use `is`, `has`, `can`, `should` prefixes
- Avoid abbreviations; clarity at the call site is more important than brevity in the definition

```swift
// BAD - abbreviated, not clear at call site
func usr(by id: String) -> User? { }
func chkAuth() -> Bool { }
var ordCnt: Int { }

// GOOD - reads naturally
func user(withID id: String) -> User? { }
func isAuthenticated() -> Bool { }
var orderCount: Int { }

// Call site reads naturally:
if isAuthenticated() { }
let count = orderCount
```

### Rule 6.2: Type Names Are PascalCase, Everything Else Is camelCase
```swift
// Types (PascalCase)
struct OrderService { }
enum NetworkError { }
protocol DataFetchable { }
typealias UserID = UUID

// Everything else (camelCase)
let userName = "Alice"
var currentOrder: Order?
func processPayment() { }
```

---

## 7. ARC Memory Management

### Rule 7.1: Use `[weak self]` in Closures That Capture Self Cyclically
- A closure that captures `self` strongly and is stored on `self` creates a retain cycle
- Use `[weak self]` to break the cycle; guard against nil self inside the closure

```swift
// BAD - retain cycle: self -> timer -> closure -> self
class CountdownTimer {
    var timer: Timer?
    var count = 10

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { timer in
            self.count -= 1  // strong capture of self
            if self.count == 0 { timer.invalidate() }
        }
    }
}

// GOOD - weak capture breaks the cycle
class CountdownTimer {
    var timer: Timer?
    var count = 10

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] timer in
            guard let self else { timer.invalidate(); return }
            self.count -= 1
            if self.count == 0 { timer.invalidate() }
        }
    }
}
```

### Rule 7.2: Use `unowned` Only When the Captured Object Outlives the Closure
- `unowned` crashes if the captured object is nil when the closure runs
- Use `weak` when in doubt; `unowned` only when you are certain of the lifetime

```swift
// ACCEPTABLE - unowned when lifecycle is guaranteed
// In a delegate pattern where delegate always outlives the child
class DataLoader {
    unowned let delegate: DataLoaderDelegate  // delegate creates DataLoader and outlives it
    init(delegate: DataLoaderDelegate) { self.delegate = delegate }
}

// DEFAULT - use weak for safety
class APIClient {
    func fetch(completion: @escaping (Result<Data, Error>) -> Void) {
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let self else { return }  // self might be nil if view was dismissed
            // process response
        }.resume()
    }
}
```

---

## 8. Codable

### Rule 8.1: Use `Codable` for JSON Serialization - Avoid Manual Parsing
- Implement `Codable` (or `Decodable`/`Encodable`) for JSON models
- Use `CodingKeys` to map snake_case JSON to camelCase Swift properties

```swift
// BAD - manual JSON parsing is fragile and verbose
struct User {
    let id: String
    let firstName: String
}
let user = User(
    id: dict["id"] as! String,
    firstName: dict["first_name"] as! String
)

// GOOD - Codable with CodingKeys for snake_case conversion
struct User: Codable {
    let id: UUID
    let firstName: String
    let email: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case firstName = "first_name"
        case email
        case createdAt = "created_at"
    }
}

// BETTER - use JSONDecoder with keyDecodingStrategy
let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
decoder.dateDecodingStrategy = .iso8601
let user = try decoder.decode(User.self, from: jsonData)
```

---

## 9. Async/Await - Structured Concurrency

### Rule 9.1: Use `async let` for Parallel Independent Operations
- `async let` starts an async task immediately and awaits later
- Use it when multiple independent async operations can run in parallel

```swift
// BAD - sequential: waits for user, then fetches orders
func loadProfile(userID: UUID) async throws -> ProfileData {
    let user = try await userService.fetch(userID)
    let orders = try await orderService.fetchAll(for: userID)
    return ProfileData(user: user, orders: orders)
}

// GOOD - parallel: both fetch simultaneously
func loadProfile(userID: UUID) async throws -> ProfileData {
    async let user = userService.fetch(userID)
    async let orders = orderService.fetchAll(for: userID)
    return try await ProfileData(user: user, orders: orders)
}
```

### Rule 9.2: Use `Task` for Bridging Sync to Async Context
- Use `Task { }` to call async code from a synchronous context
- Use `Task.detached { }` only when the task should NOT inherit the current actor context

```swift
// GOOD - Task in SwiftUI to call async from .onAppear
struct OrderListView: View {
    @State private var orders: [Order] = []

    var body: some View {
        List(orders, id: \.id) { order in
            Text(order.id)
        }
        .task {  // preferred over .onAppear for async work
            await loadOrders()
        }
    }

    private func loadOrders() async {
        do {
            orders = try await orderService.fetchAll()
        } catch {
            print("Failed to load orders: \(error)")
        }
    }
}
```

### Rule 9.3: Mark View and ViewModel Methods with `@MainActor`
- UI updates must happen on the main thread
- Mark view model classes with `@MainActor` to ensure all property updates are on the main thread

```swift
// BAD - updating UI properties from background thread
class OrderViewModel: ObservableObject {
    @Published var orders: [Order] = []

    func load() {
        Task {
            orders = try await service.fetch()  // may run on background thread
        }
    }
}

// GOOD - @MainActor ensures UI updates on main thread
@MainActor
class OrderViewModel: ObservableObject {
    @Published var orders: [Order] = []

    func load() async {
        do {
            orders = try await service.fetch()  // guaranteed on main thread
        } catch {
            // handle error
        }
    }
}
```

---

## 10. Common LLM Mistakes to Avoid

- Force-unwrapping optionals with `!` in non-IBOutlet production code
- Using `class` when `struct` is appropriate for data models
- Missing `[weak self]` in closures stored on `self` (creates retain cycles)
- Using `@State` for business data that should be in a ViewModel
- Using `DispatchQueue.main.async` instead of `@MainActor` in modern Swift code
- Generating completion handler APIs instead of `async throws` for new code
- Not using `guard let` for early returns, leading to deeply nested `if let` chains
- Defining `CodingKeys` when `decoder.keyDecodingStrategy = .convertFromSnakeCase` would suffice
- Calling async functions without `await`, leading to silent data races
- Forgetting `defer` for cleanup in functions with multiple return paths
