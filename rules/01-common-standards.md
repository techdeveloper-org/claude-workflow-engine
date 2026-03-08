---
description: "Level 2.1 - Universal coding standards for all projects"
priority: critical
---

# Common Standards Enforcement (Level 2.1)

**PURPOSE:** Enforce universal coding standards that apply to ALL projects, regardless of tech stack.

---

## 0. Task Type Detection (For Proper Agent Selection)

✅ **Design/UI-UX tasks trigger ui-ux-designer:**
```
Keywords: design, redesign, ui, ux, interface, layout, mockup, wireframe,
styling, theme, color scheme, component design, design system
→ Agent: ui-ux-designer (NOT angular-engineer)
```

✅ **Backend tasks trigger appropriate backend engineer:**
```
Keywords: api, endpoint, database, service, repository
→ Agent: python-backend-engineer, spring-boot-microservices (based on tech stack)
```

✅ **Frontend tasks trigger appropriate frontend engineer:**
```
Keywords: component, state management, hook, styling, accessibility
→ Agent: angular-engineer, swiftui-designer (based on framework)
```

---

## 1. Naming Conventions

- **Variables & functions:** camelCase
  ```javascript
  ✅ const userName = "Alice"
  ✗ const user_name = "Alice"
  ```

- **Classes & types:** PascalCase
  ```java
  ✅ class UserRepository { }
  ✗ class userRepository { }
  ```

- **Constants:** UPPER_SNAKE_CASE
  ```python
  ✅ MAX_RETRIES = 3
  ✗ max_retries = 3
  ```

- **Database tables/columns:** snake_case
  ```sql
  ✅ CREATE TABLE users (user_id, created_at)
  ✗ CREATE TABLE Users (userId, CreatedAt)
  ```

- **API endpoints:** kebab-case plural nouns
  ```
  ✅ GET /api/v1/users
  ✗ GET /api/v1/user or /api/v1/getUsers
  ```

- **Booleans:** prefix with is/has/can/should
  ```python
  ✅ is_active, has_permission, can_delete, should_retry
  ✗ active, permission, delete, retry
  ```

- **Abbreviations:** ONLY universally known (id, url, api, http, etc.)

---

## 2. Error Handling (Universal)

❌ **NEVER swallow exceptions silently**
```python
# ✗ WRONG - Silent failure
try:
    process_data()
except Exception:
    pass

# ✅ CORRECT - Handle or propagate with context
try:
    process_data()
except SpecificError as e:
    logger.error(f"Data processing failed: {e}", exc_info=True)
    raise
```

✅ **Catch specific exception types**
- Avoid generic `Exception` or `Error`
- Always include context in error messages
- Log with full stack trace (`exc_info=True` in Python, `.printStackTrace()` in Java)

✅ **Use appropriate error codes/status**
```
400 Bad Request (invalid input)
401 Unauthorized (authentication failed)
403 Forbidden (no permission)
404 Not Found
500 Internal Server Error (server bug)
```

✅ **NEVER expose internal details to users**
```python
# ✗ WRONG - Exposes DB structure
"Error: Column 'user_id' not found in users table"

# ✅ CORRECT - Generic message, log details internally
"Failed to retrieve user data"  # + log full error
```

---

## 3. Logging Standards

✅ **Structured logging (key-value pairs, not free text)**
```python
# ✗ WRONG
logger.info("User login successful")

# ✅ CORRECT
logger.info("User authentication completed", extra={
    "user_id": user_id,
    "ip_address": request.ip,
    "correlation_id": correlation_id,
    "duration_ms": elapsed_time
})
```

✅ **Include correlation/request ID in ALL log entries**
- Enables end-to-end tracing of a single request
- Use same ID across all services in a microservices system

✅ **Use appropriate log levels**
```
ERROR   - Something failed that the system cannot recover from
WARNING - Something unexpected, but system can continue
INFO    - Important events (startup, user actions)
DEBUG   - Detailed diagnostic info (variable values, flow)
```

❌ **NEVER log sensitive data**
```python
# ✗ WRONG - Exposes credentials
logger.debug(f"Token: {api_token}")
logger.debug(f"Password: {password}")
logger.debug(f"SSN: {social_security_number}")

# ✅ CORRECT - Log without sensitive parts
logger.debug(f"Token: {api_token[:10]}***")
logger.debug(f"Password: ***")
```

---

## 4. Security Basics

❌ **NEVER hardcode secrets, passwords, or API keys**
```python
# ✗ WRONG
API_KEY = "sk-abc123def456"
DB_PASSWORD = "SuperSecret123"

# ✅ CORRECT
API_KEY = os.environ.get("API_KEY")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
```

✅ **Validate ALL external input**
```python
# ✗ WRONG - No validation
user = User.create(email=request.email)

# ✅ CORRECT - Validate before use
if not is_valid_email(request.email):
    raise ValidationError("Invalid email format")
```

✅ **Use parameterized queries for database**
```sql
-- ✗ WRONG - SQL Injection vulnerability
SELECT * FROM users WHERE id = ?

-- ✅ CORRECT - Parameterized/prepared statement
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

✅ **Principle of least privilege**
- Users get minimal permissions needed for their role
- Service accounts access only required data
- APIs expose only necessary endpoints

❌ **NEVER commit secrets to version control**
```bash
# ✗ WRONG - In repo history forever
git add .env
git commit -m "add credentials"

# ✅ CORRECT - Use .gitignore + environment variables
echo ".env" >> .gitignore
```

---

## 5. Code Organization

✅ **Single Responsibility Principle (SRP)**
```python
# ✗ WRONG - UserManager does too much
class UserManager:
    def create_user(self): pass
    def save_to_db(self): pass
    def send_email(self): pass
    def generate_pdf_report(self): pass

# ✅ CORRECT - Separated concerns
class UserService:
    def create_user(self): pass

class UserRepository:
    def save(self): pass

class EmailService:
    def send_welcome_email(self): pass
```

✅ **DRY (Don't Repeat Yourself)**
```python
# ✗ WRONG - Duplicated validation
def create_user(email): validate_email(email)
def update_user(email): validate_email(email)
def subscribe(email): validate_email(email)

# ✅ CORRECT - Reusable function
def _ensure_valid_email(email):
    if not is_valid_email(email):
        raise ValidationError(f"Invalid email: {email}")

@validates_email
def create_user(email): pass

@validates_email
def update_user(email): pass
```

✅ **Separate layers clearly**
```
Controller/Router → validates HTTP request format
Service Layer    → business logic, validation
Repository       → database access, queries
Models           → data structures, entities
```

✅ **Keep functions small and focused**
- Single function = one task
- Easier to test, understand, maintain
- Target: < 20 lines per function

---

## 6. API Design (Universal)

✅ **Use plural nouns for resources**
```
✅ GET /api/v1/users
✅ POST /api/v1/users
✅ GET /api/v1/users/{id}
✗ GET /api/v1/user
✗ GET /api/v1/getUsers
```

✅ **Use standard HTTP methods correctly**
```
GET    - Read/retrieve resource(s) - SAFE, IDEMPOTENT
POST   - Create new resource - NOT idempotent
PUT    - Replace entire resource - IDEMPOTENT
PATCH  - Partial update - IDEMPOTENT
DELETE - Remove resource - IDEMPOTENT
```

✅ **Return appropriate HTTP status codes**
```
200 OK - Request succeeded, response body included
201 Created - Resource created, return new resource
204 No Content - Success, no body
400 Bad Request - Invalid request format/data
401 Unauthorized - Missing/invalid authentication
403 Forbidden - User lacks permission
404 Not Found - Resource doesn't exist
409 Conflict - Constraint violation (duplicate, version mismatch)
500 Internal Server Error - Server bug
```

✅ **Support pagination for list endpoints**
```json
GET /api/v1/users?page=1&pageSize=20

{
  "data": [...20 users...],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalCount": 500,
    "totalPages": 25
  }
}
```

✅ **Version APIs in the URL path**
```
✅ GET /api/v1/users
✅ GET /api/v2/users
✗ GET /api/users (version unclear)
```

✅ **Use consistent response envelope**
```json
// ✅ CONSISTENT format for ALL endpoints
{
  "success": true,
  "data": {...},
  "error": null,
  "timestamp": "2026-03-08T19:07:54Z"
}

{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_EMAIL",
    "message": "User-friendly message"
  },
  "timestamp": "2026-03-08T19:07:54Z"
}
```

---

## 7. Database (Universal)

✅ **snake_case for all table and column names**
```sql
✅ CREATE TABLE user_accounts (user_id, created_at, updated_at)
✗ CREATE TABLE UserAccounts (userId, createdAt, updatedAt)
```

✅ **Database migrations for ALL schema changes**
```bash
# ✗ WRONG - Manual schema change
ALTER TABLE users ADD COLUMN phone_number VARCHAR(20);

# ✅ CORRECT - Use migration framework
migrations/001_add_phone_to_users.sql
```

✅ **Use transactions for multi-step operations**
```python
# ✓ CORRECT - All or nothing
@transactional
def transfer_money(from_account, to_account, amount):
    from_account.debit(amount)
    to_account.credit(amount)
```

---

## 8. Testing Standards

✅ **Unit tests for business logic**
- One test = one behavior
- Test both happy path and error cases
- Use descriptive test names: `test_<function>_<scenario>_<expected_result>`

✅ **Integration tests for external dependencies**
- Database operations
- API calls
- Message queues

---

## 9. Documentation

✅ **Keep code self-documenting**
- Clear function names (`process_payment` not `do_thing`)
- Clear variable names (`user_email` not `ue`)

✅ **Document WHY, not WHAT**
```python
# ✗ WRONG - Obvious from code
x = y * 2  # multiply y by 2

# ✅ CORRECT - Explains reasoning
# Cache timeout doubled for high-traffic scenarios
x = y * 2
```

✅ **Public APIs require docstrings**
```python
def get_user_by_email(email: str) -> User:
    """Fetch a user account by email address.

    Args:
        email: Email address to search for

    Returns:
        User object if found

    Raises:
        UserNotFound: If email doesn't match any user
    """
```

---

## 10. Version Control

✅ **Commit messages follow convention**
```
✅ "fix: Correct null pointer in payment validation"
✅ "feat: Add two-factor authentication"
✅ "docs: Update API documentation for v2"
✗ "fixed stuff"
✗ "changes"
```

✅ **One logical change per commit**
- Don't mix bug fixes with refactoring
- Easier to review, revert, and track history

---

## 11. Performance

✅ **Avoid N+1 query problems**
```python
# ✗ WRONG - Queries in loop
for user_id in user_ids:
    user = User.get(user_id)
    orders = Order.find(user=user)  # N+1 queries!

# ✅ CORRECT - Single query with join
users = User.filter(id__in=user_ids).prefetch_related('orders')
```

✅ **Cache expensive operations**
- Database queries
- API calls
- Computations

✅ **Use indexes for frequently queried columns**

---

## 12. Accessibility & Internationalization

✅ **All error messages are user-friendly**
✅ **No hardcoded strings - use translation keys**
✅ **Dates/times follow ISO 8601 format**
✅ **Support at least one non-English language**

---

**ENFORCEMENT:** This is Level 2.1 - ALWAYS ACTIVE. These rules apply to every code change in this project.
