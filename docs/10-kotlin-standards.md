# Kotlin Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Null Safety

### Rule 1.1: Never Use `!!` (Non-Null Assertion) in Production Code
- `!!` throws `NullPointerException` at runtime - it is the same as Java's unchecked dereference
- Use `?.`, `?:`, `let`, or `checkNotNull` with a descriptive message instead

```kotlin
// BAD - crashes with NPE if userRepository.find() returns null
val user = userRepository.find(userId)!!
println(user.name)

// BAD - still crashes, just with a worse message
val user = requireNotNull(userRepository.find(userId))

// GOOD - handle null explicitly
val user = userRepository.find(userId)
    ?: throw UserNotFoundException("User $userId not found")
println(user.name)

// GOOD - safe call with let
userRepository.find(userId)?.let { user ->
    println(user.name)
} ?: logger.warn("User $userId not found")
```

### Rule 1.2: Use `?:` (Elvis) for Null Defaults
- The Elvis operator provides a concise default when a nullable value is null
- Chain Elvis operators for fallback chains instead of nested null checks

```kotlin
// BAD - verbose null check
val displayName: String
if (user.displayName != null) {
    displayName = user.displayName
} else if (user.email != null) {
    displayName = user.email
} else {
    displayName = "Unknown"
}

// GOOD - Elvis chain
val displayName = user.displayName ?: user.email ?: "Unknown"
```

### Rule 1.3: Make Nullability Explicit in Function Signatures
- A function that may not find a result should return `T?` not throw an exception
- A function that requires the result and should throw should be named differently

```kotlin
// GOOD - clear naming and nullability contract
suspend fun findUserById(id: String): User? {   // returns null if not found
    return userRepository.findById(id)
}

suspend fun getUserById(id: String): User {     // throws if not found
    return userRepository.findById(id)
        ?: throw UserNotFoundException(id)
}
```

---

## 2. Coroutines - launch vs async

### Rule 2.1: Use `launch` for Fire-and-Forget, `async` for Results
- `launch` returns a `Job` - use it when you do not need the result
- `async` returns a `Deferred<T>` - use it when you need to `await` a result
- Always call `await()` on `async` - do not ignore the Deferred

```kotlin
// BAD - using async when result is never awaited
scope.async {
    updateAnalytics(event)  // result never used
}

// GOOD - launch for fire-and-forget
scope.launch {
    updateAnalytics(event)
}

// GOOD - async when result is needed
suspend fun loadDashboard(): Dashboard {
    val userDeferred = async { userService.fetchCurrentUser() }
    val ordersDeferred = async { orderService.fetchRecent() }
    val user = userDeferred.await()
    val orders = ordersDeferred.await()
    return Dashboard(user, orders)
}
```

### Rule 2.2: Use `coroutineScope` for Parallel Decomposition
- `coroutineScope` creates a scope that waits for all child coroutines to complete
- Any failure in a child cancels all siblings and propagates to the parent

```kotlin
// GOOD - parallel calls with structured concurrency
suspend fun loadProfileData(userId: String): ProfileData = coroutineScope {
    val user = async { userService.fetch(userId) }
    val orders = async { orderService.fetchForUser(userId) }
    val notifications = async { notificationService.fetchUnread(userId) }
    ProfileData(
        user = user.await(),
        orders = orders.await(),
        notifications = notifications.await()
    )
}
```

### Rule 2.3: Use Flow for Reactive Streams
- `Flow<T>` is Kotlin's cold stream for reactive sequences
- Use `StateFlow` for state (replays latest to new collectors)
- Use `SharedFlow` for events (does not replay)
- Never expose mutable `MutableStateFlow` publicly - expose as `StateFlow`

```kotlin
// BAD - exposing MutableStateFlow publicly
class OrderViewModel : ViewModel() {
    val orders = MutableStateFlow<List<Order>>(emptyList())  // mutable and public
}

// GOOD - private mutable, public immutable
class OrderViewModel : ViewModel() {
    private val _orders = MutableStateFlow<List<Order>>(emptyList())
    val orders: StateFlow<List<Order>> = _orders.asStateFlow()

    private val _events = MutableSharedFlow<OrderEvent>()
    val events: SharedFlow<OrderEvent> = _events.asSharedFlow()

    fun loadOrders() {
        viewModelScope.launch {
            _orders.value = orderRepository.fetchAll()
        }
    }
}
```

---

## 3. Sealed Classes and Interfaces

### Rule 3.1: Use Sealed Classes for Exhaustive State Modeling
- Sealed classes make all subclasses known at compile time - `when` expressions become exhaustive
- Use sealed classes instead of enums when states carry different data
- Always use `when` as an expression (not statement) to get exhaustiveness checking

```kotlin
// BAD - open class hierarchy, when is not exhaustive
open class OrderState
class Pending : OrderState()
class Processing : OrderState()
class Shipped(val trackingNumber: String) : OrderState()

// GOOD - sealed class, when expressions are exhaustive
sealed class OrderState {
    object Pending : OrderState()
    object Processing : OrderState()
    data class Shipped(val trackingNumber: String) : OrderState()
    data class Failed(val reason: String) : OrderState()
}

// Exhaustive when - compiler error if a case is missing
fun statusMessage(state: OrderState): String = when (state) {
    is OrderState.Pending    -> "Your order is being processed"
    is OrderState.Processing -> "Order is being prepared"
    is OrderState.Shipped    -> "Shipped! Tracking: ${state.trackingNumber}"
    is OrderState.Failed     -> "Failed: ${state.reason}"
}
```

### Rule 3.2: Use Sealed Interfaces for UI State with Loading/Error/Success Pattern
- Sealed interfaces allow unrelated classes to implement a bounded type hierarchy
- Common pattern: `UiState` sealed interface for loading, error, and success

```kotlin
sealed interface UiState<out T> {
    object Loading : UiState<Nothing>
    data class Success<T>(val data: T) : UiState<T>
    data class Error(val message: String, val cause: Throwable? = null) : UiState<Nothing>
}

// ViewModel exposes sealed interface
class OrderListViewModel : ViewModel() {
    private val _uiState = MutableStateFlow<UiState<List<Order>>>(UiState.Loading)
    val uiState: StateFlow<UiState<List<Order>>> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            _uiState.value = try {
                UiState.Success(orderRepository.fetchAll())
            } catch (e: Exception) {
                UiState.Error("Failed to load orders", e)
            }
        }
    }
}
```

---

## 4. Data Classes

### Rule 4.1: Use `data class` for Value Objects and DTOs
- `data class` auto-generates `equals`, `hashCode`, `toString`, `copy`, and `componentN` functions
- Use for: API request/response models, domain value objects, DTOs
- Do NOT use `data class` for entities with mutable identity or lifecycle

```kotlin
// GOOD - data class for immutable value object
data class Money(val amount: Long, val currency: String) {
    operator fun plus(other: Money): Money {
        require(currency == other.currency) { "Cannot add different currencies" }
        return copy(amount = amount + other.amount)
    }
}

// GOOD - data class for API response DTO
data class UserResponse(
    val id: String,
    val name: String,
    val email: String,
    val createdAt: Instant
)

// BAD - data class for JPA entity (causes issues with proxy, equals based on id)
@Entity
data class OrderEntity(
    @Id val id: UUID = UUID.randomUUID(),
    var status: String = "PENDING"
)
```

### Rule 4.2: Use `copy()` for Modifying Immutable Data Classes
- `copy()` creates a new instance with specified properties changed
- Do not add `var` properties to data classes unless mutation is truly required

```kotlin
data class OrderItem(val productId: String, val quantity: Int, val price: Money)

// GOOD - copy creates new instance
val original = OrderItem("prod-1", 1, Money(1000, "USD"))
val updated = original.copy(quantity = 2)
// original is unchanged
```

---

## 5. Extension Functions

### Rule 5.1: Use Extension Functions to Add Behavior Without Inheritance
- Extension functions add methods to existing types without modifying them
- Use for: utility functions, type-specific formatting, domain-specific conversions

```kotlin
// GOOD - extension on String for domain logic
fun String.isValidEmail(): Boolean {
    return matches(Regex("^[A-Za-z0-9+_.-]+@(.+)$"))
}

// GOOD - extension on domain type
fun Order.isEditable(): Boolean = status in setOf(OrderStatus.PENDING, OrderStatus.PROCESSING)

// Usage reads naturally
if (email.isValidEmail()) { ... }
if (order.isEditable()) { ... }
```

### Rule 5.2: Do Not Use Extension Functions as a Substitute for Proper Design
- Extension functions on `Any` or very broad types pollute all types
- Do not add extension functions that modify global state or have side effects

```kotlin
// BAD - extension on Any is available everywhere and confusing
fun Any.printType() { println(this::class.simpleName) }

// BAD - extension that has side effects on unrelated type
fun String.saveToDatabase(db: Database) { db.insert(this) }  // wrong abstraction

// GOOD - focused extension on the right receiver type
fun List<Order>.totalAmount(): Money = fold(Money.ZERO) { acc, order -> acc + order.total }
```

---

## 6. Scope Functions - let / run / with / apply / also

### Rule 6.1: Use Scope Functions Appropriately - Match Function to Intent

```kotlin
// let - transform a nullable value or chain operations, result is lambda result
val length = name?.let { it.trim().length } ?: 0

// apply - configure an object, result is the receiver (builder pattern)
val request = HttpRequest().apply {
    url = "https://api.example.com/orders"
    method = "POST"
    headers["Authorization"] = "Bearer $token"
}

// also - perform side effects without changing the value (e.g., logging)
val order = createOrder(items).also { order ->
    logger.info("Created order ${order.id}")
    analyticsService.track("order_created", order.id)
}

// with - operate on an object without it/this confusion, result is lambda result
val summary = with(order) {
    "Order $id: ${items.size} items, total $total"  // this = order
}

// run - like with but as extension function; useful for null-safe operations
val result = connection?.run {
    query("SELECT * FROM orders")  // this = connection
}
```

### Rule 6.2: Do Not Nest Scope Functions More Than Two Levels
- Deeply nested scope functions make code hard to read and debug

```kotlin
// BAD - three levels of scope functions
user?.let { u ->
    u.address?.apply {
        street?.run {
            println("Street: $this")
        }
    }
}

// GOOD - flatten with early returns
val street = user?.address?.street ?: return
println("Street: $street")
```

---

## 7. Android ViewModel and LiveData/StateFlow

### Rule 7.1: Use StateFlow Over LiveData in New Code
- `StateFlow` is Kotlin-native; no need for `LiveData` in new Compose or View-based code
- `LiveData` is lifecycle-aware but requires Android runtime; `StateFlow` works in pure Kotlin

```kotlin
// OLD - LiveData
class UserViewModel : ViewModel() {
    private val _user = MutableLiveData<User?>()
    val user: LiveData<User?> = _user
}

// NEW - StateFlow
class UserViewModel : ViewModel() {
    private val _user = MutableStateFlow<User?>(null)
    val user: StateFlow<User?> = _user.asStateFlow()
}
```

### Rule 7.2: Use `viewModelScope` for Coroutines in ViewModel
- `viewModelScope` is automatically cancelled when the ViewModel is cleared
- Do not create custom `CoroutineScope` in ViewModel - use the provided scope

```kotlin
class OrderViewModel(
    private val repository: OrderRepository
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<List<Order>>>(UiState.Loading)
    val state: StateFlow<UiState<List<Order>>> = _state.asStateFlow()

    init {
        loadOrders()
    }

    fun loadOrders() {
        viewModelScope.launch {  // cancelled automatically when ViewModel is cleared
            _state.value = try {
                UiState.Success(repository.fetchAll())
            } catch (e: CancellationException) {
                throw e  // always re-throw CancellationException
            } catch (e: Exception) {
                UiState.Error(e.localizedMessage ?: "Unknown error")
            }
        }
    }
}
```

---

## 8. Hilt Dependency Injection

### Rule 8.1: Use Hilt Annotations Consistently
- `@HiltViewModel` for ViewModels, `@Inject constructor` for classes Hilt should provide
- Use `@Singleton`, `@ActivityScoped`, `@ViewModelScoped` to control instance lifetime

```kotlin
// GOOD - Hilt ViewModel with injected dependencies
@HiltViewModel
class OrderViewModel @Inject constructor(
    private val orderRepository: OrderRepository,
    private val analyticsService: AnalyticsService
) : ViewModel() { }

// GOOD - Hilt module for interfaces
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    @Singleton
    abstract fun bindOrderRepository(impl: OrderRepositoryImpl): OrderRepository
}
```

---

## 9. Testing with MockK

### Rule 9.1: Use MockK for Kotlin-Idiomatic Mocking
- MockK supports Kotlin features: coroutines, extension functions, top-level functions
- Use `mockk()`, `every { }`, `coEvery { }` for suspend functions, `verify { }`

```kotlin
class OrderServiceTest {
    private val orderRepository: OrderRepository = mockk()
    private val emailService: EmailService = mockk(relaxed = true)  // relaxed: all methods return default values
    private val service = OrderService(orderRepository, emailService)

    @Test
    fun `place order saves order and sends confirmation`() = runTest {
        // Arrange
        val order = Order(id = "ord-1", items = listOf())
        coEvery { orderRepository.save(any()) } returns order

        // Act
        val result = service.placeOrder(order)

        // Assert
        assertEquals(order.id, result.id)
        coVerify { orderRepository.save(order) }
        coVerify { emailService.sendConfirmation(order) }
    }

    @Test
    fun `place order throws when repository fails`() = runTest {
        coEvery { orderRepository.save(any()) } throws DatabaseException("Connection lost")

        assertThrows<OrderProcessingException> {
            service.placeOrder(Order(id = "ord-1", items = listOf()))
        }
    }
}
```

---

## 10. Compose Patterns

### Rule 10.1: Pass State Down, Events Up (Unidirectional Data Flow)
- Composables should receive state as parameters, not hold it internally
- Pass lambda callbacks for events; do not expose ViewModels to deep child composables

```kotlin
// BAD - composable reaches into ViewModel directly
@Composable
fun OrderItem(orderId: String, viewModel: OrderViewModel = hiltViewModel()) {
    val order by viewModel.orders.collectAsState()
    // ...
}

// GOOD - stateless composable receives what it needs
@Composable
fun OrderItem(
    order: Order,
    onSelectOrder: (String) -> Unit,
    onDeleteOrder: (String) -> Unit
) {
    Card(onClick = { onSelectOrder(order.id) }) {
        // display order
    }
}

// Stateful parent passes state and lambdas
@Composable
fun OrderListScreen(viewModel: OrderViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    OrderList(
        orders = (state as? UiState.Success)?.data ?: emptyList(),
        onSelectOrder = viewModel::selectOrder,
        onDeleteOrder = viewModel::deleteOrder
    )
}
```

### Rule 10.2: Use `key()` in Lists to Preserve State Across Recompositions
- Without `key`, Compose reuses composable instances by position
- Use `key(item.id)` so Compose tracks items by identity, not position

```kotlin
// BAD - items tracked by position; reordering causes wrong state
LazyColumn {
    items(orders) { order ->
        OrderItem(order)
    }
}

// GOOD - items tracked by identity
LazyColumn {
    items(orders, key = { it.id }) { order ->
        OrderItem(order)
    }
}
```

---

## 11. Common LLM Mistakes to Avoid

- Using `!!` (non-null assertion) instead of proper null handling
- Forgetting to re-throw `CancellationException` in try/catch blocks in coroutines
- Using `GlobalScope.launch` instead of `viewModelScope` or `lifecycleScope`
- Exposing `MutableStateFlow` or `MutableLiveData` as public properties
- Using `data class` for JPA/Room entities (breaks Hibernate/Room proxy and equals contract)
- Not making the `when` expression exhaustive (missing `else` on sealed class `when`)
- Using `launch` when `async/await` is needed (or vice versa)
- Forgetting to collect Flows in a lifecycle-aware way (`collectAsStateWithLifecycle` not `collectAsState`)
- Writing `if (x != null) x.foo() else null` instead of `x?.foo()`
- Adding `var` to data class properties when `copy()` and immutability would be better
