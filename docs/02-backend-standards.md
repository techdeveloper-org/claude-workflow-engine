---
description: "Level 2.1 - Backend development standards (Python, Flask, microservices)"
paths:
  - "src/**/*.py"
  - "scripts/**/*.py"
  - "tests/**/*.py"
priority: high
---

# Backend Standards (Level 2.1 - Python/Flask)

**PURPOSE:** Enforce Python backend development standards for consistency, reliability, and maintainability.

---

## 1. Project Structure & Organization

✅ **Organize code by feature/service, not by type:**

```python
# ✅ CORRECT - Feature-based organization
src/
├── auth/
│   ├── __init__.py
│   ├── routes.py
│   ├── services.py
│   ├── models.py
│   └── schemas.py
├── users/
│   ├── __init__.py
│   ├── routes.py
│   ├── services.py
│   └── models.py
└── shared/
    ├── __init__.py
    ├── exceptions.py
    └── utils.py

# ✗ WRONG - Type-based organization (anti-pattern)
src/
├── routes/
│   ├── auth.py
│   └── users.py
├── services/
│   ├── auth_service.py
│   └── user_service.py
└── models/
    ├── user_model.py
    └── auth_model.py
```

✅ **Separate concerns clearly:**
```python
# routes.py    - HTTP request/response handling
# services.py  - Business logic
# models.py    - Database entities
# schemas.py   - Data validation (Pydantic/Marshmallow)
# exceptions.py - Custom error classes
```

---

## 2. Service Layer Pattern

✅ **Services contain business logic, never in routes:**

```python
# ✅ CORRECT
# routes.py
@auth_bp.route('/login', methods=['POST'])
def login():
    form = LoginForm.from_request(request)
    token = auth_service.authenticate(form.email, form.password)
    return api_response({"token": token})

# services.py
class AuthService:
    def authenticate(self, email: str, password: str) -> str:
        """Validate credentials and return JWT token."""
        user = self.user_repo.find_by_email(email)
        if not user or not user.verify_password(password):
            raise InvalidCredentialsError()
        return self.jwt_service.create_token(user.id)

# ✗ WRONG - Logic in route
@auth_bp.route('/login', methods=['POST'])
def login():
    email = request.json.get('email')
    password = request.json.get('password')

    # ✗ Business logic here!
    user = User.query.filter_by(email=email).first()
    if not user or not user.verify_password(password):
        return {"error": "Invalid credentials"}, 401

    token = jwt.encode({"user_id": user.id}, SECRET_KEY)
    return {"token": token}
```

✅ **Use dependency injection for services:**

```python
# ✗ WRONG - Global service (hard to test)
user_service = UserService()

@users_bp.route('/<int:user_id>')
def get_user(user_id):
    return user_service.get_by_id(user_id)

# ✅ CORRECT - Injected service (easy to test)
@users_bp.route('/<int:user_id>')
def get_user(user_id, user_service: UserService = Depends(get_user_service)):
    return user_service.get_by_id(user_id)
```

---

## 3. Database Access Layer

✅ **Use Repository pattern for data access:**

```python
# ✓ CORRECT
class UserRepository:
    """Data access for User entity."""

    def find_by_id(self, user_id: int) -> User:
        return User.query.get(user_id)

    def find_by_email(self, email: str) -> Optional[User]:
        return User.query.filter_by(email=email).first()

    def find_all_active(self, page: int = 1, page_size: int = 20):
        return User.query.filter_by(is_active=True)\
            .paginate(page=page, per_page=page_size)

    def create(self, user_data: Dict) -> User:
        user = User(**user_data)
        db.session.add(user)
        db.session.commit()
        return user

# Service uses repository
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: int) -> UserResponseDto:
        user = self.repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return self._map_to_dto(user)
```

❌ **NEVER query directly in service/route:**

```python
# ✗ WRONG - Direct database query in service
class UserService:
    def get_user(self, user_id: int):
        user = User.query.get(user_id)  # ✗ Direct query
        return user
```

---

## 4. API Response Format

✅ **All APIs return consistent response structure:**

```python
# ✅ CORRECT format for ALL endpoints
{
    "success": true,
    "data": {...},
    "error": null,
    "timestamp": "2026-03-08T19:26:00Z"
}

{
    "success": false,
    "data": null,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Email is required"
    },
    "timestamp": "2026-03-08T19:26:00Z"
}

# Helper function
def api_response(data=None, message: str = None, status_code: int = 200):
    """Wrap response in standard format."""
    response = {
        "success": 200 <= status_code < 400,
        "data": data,
        "error": None if 200 <= status_code < 400 else {
            "code": "ERROR",
            "message": message or "An error occurred"
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    return response, status_code
```

---

## 5. Input Validation

✅ **Validate at API boundary using schemas:**

```python
from pydantic import BaseModel, EmailStr, Field

# ✅ CORRECT - Pydantic schema
class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)

    class Config:
        example = {
            "email": "user@example.com",
            "password": "SecurePass123!",
            "first_name": "John",
            "last_name": "Doe"
        }

# ✅ In route
@users_bp.route('/', methods=['POST'])
def create_user(schema: UserCreateSchema):
    """Pydantic automatically validates request."""
    user = user_service.create(schema.dict())
    return api_response(user, status_code=201)

# ✗ WRONG - Manual validation
@users_bp.route('/', methods=['POST'])
def create_user():
    data = request.json
    if not data.get('email'):
        return {"error": "Email required"}, 400
    if len(data.get('password', '')) < 8:
        return {"error": "Password too short"}, 400
    # ... more manual checks
```

---

## 6. Error Handling

✅ **Use custom exception classes:**

```python
# ✅ CORRECT - Custom exceptions
class ApplicationError(Exception):
    """Base exception for all app errors."""
    def __init__(self, message: str, code: str = "ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)

class NotFoundError(ApplicationError):
    def __init__(self, entity: str, entity_id):
        super().__init__(f"{entity} not found: {entity_id}", "NOT_FOUND")

class ValidationError(ApplicationError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")

# ✅ Global error handler
@app.errorhandler(NotFoundError)
def handle_not_found(error):
    return api_response(
        message=error.message,
        status_code=404
    )

@app.errorhandler(ValidationError)
def handle_validation(error):
    return api_response(
        message=error.message,
        status_code=400
    )

# ✗ WRONG - Generic exception handling
try:
    user = User.query.get(user_id)
except Exception as e:
    return {"error": "Server error"}, 500  # Silent failure!
```

---

## 7. Configuration Management

✅ **Use environment variables for configuration:**

```python
import os
from dataclasses import dataclass

@dataclass
class Config:
    """Application configuration."""
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    DATABASE_URL = os.getenv('DATABASE_URL')
    SECRET_KEY = os.getenv('SECRET_KEY')
    JWT_EXPIRATION = int(os.getenv('JWT_EXPIRATION', '3600'))
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

    # Validate critical configs
    def __post_init__(self):
        if not self.SECRET_KEY and not self.DEBUG:
            raise ValueError("SECRET_KEY required in production")
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")

# ✗ WRONG - Hardcoded config
SECRET_KEY = "super-secret-key-123"
DATABASE_URL = "postgresql://user:pass@localhost/mydb"
API_KEY = "sk-abc123def456"  # ✗ Exposed in code!
```

---

## 8. Logging Standards

✅ **Structured logging with context:**

```python
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ✅ CORRECT - Structured logs
def create_user(user_data: dict):
    try:
        user = user_service.create(user_data)
        logger.info(
            "User created successfully",
            extra={
                "user_id": user.id,
                "email": user.email,
                "created_at": user.created_at.isoformat(),
                "duration_ms": elapsed_time
            }
        )
        return api_response(user)
    except ValidationError as e:
        logger.warning(
            "User creation validation failed",
            extra={
                "error": str(e),
                "provided_email": user_data.get('email')
            }
        )
        return api_response(message=str(e), status_code=400)
    except Exception as e:
        logger.error(
            "User creation failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True  # Include stack trace
        )
        return api_response(message="Internal server error", status_code=500)

# ✗ WRONG - Free-text logging
logger.info("user created")  # No context!
logger.debug(f"Password: {password}")  # ✗ Sensitive data!
```

---

## 9. Database Migrations

✅ **Use Alembic/Flask-Migrate for ALL schema changes:**

```bash
# ✅ CORRECT - Create migration
flask db migrate -m "Add phone_number column to users"
flask db upgrade

# ✗ WRONG - Manual SQL
ALTER TABLE users ADD COLUMN phone_number VARCHAR(20);
```

✅ **Migrations in version control:**

```
migrations/
├── versions/
│   ├── 001_initial_schema.py
│   ├── 002_add_phone_to_users.py
│   └── 003_create_orders_table.py
└── env.py
```

---

## 10. Testing Standards

✅ **Unit tests for business logic:**

```python
import pytest

class TestUserService:
    """Tests for UserService."""

    def test_get_user_by_id_success(self, user_service, user_factory):
        """Test successful user retrieval."""
        user = user_factory.create()
        result = user_service.get_by_id(user.id)
        assert result.id == user.id
        assert result.email == user.email

    def test_get_user_not_found(self, user_service):
        """Test user not found error."""
        with pytest.raises(UserNotFoundError):
            user_service.get_by_id(9999)

    def test_create_user_duplicate_email(self, user_service, user_factory):
        """Test duplicate email validation."""
        user_factory.create(email="test@example.com")
        with pytest.raises(DuplicateEmailError):
            user_service.create({
                "email": "test@example.com",
                "password": "SecurePass123!"
            })

# ✗ WRONG - No negative test cases
def test_user_creation():
    """Test that users can be created."""
    user = user_service.create({...})
    assert user.id is not None  # Not enough!
```

---

## 11. Security Best Practices

❌ **NEVER hardcode secrets:**
```python
# ✗ WRONG - Exposed!
SECRET_KEY = "my-secret-key-123"
DB_PASSWORD = "SuperSecret123"
API_KEY = "sk-abc123def456"
```

✅ **Use environment variables:**
```python
# ✅ CORRECT
SECRET_KEY = os.getenv('SECRET_KEY')
DB_PASSWORD = os.getenv('DB_PASSWORD')
API_KEY = os.getenv('API_KEY')
```

✅ **Hash passwords properly:**
```python
# ✅ CORRECT - Use bcrypt
from werkzeug.security import generate_password_hash, check_password_hash

user.password = generate_password_hash(plaintext_password)
if check_password_hash(user.password, provided_password):
    # Password matches
```

✅ **Validate ALL input:**
```python
# ✅ CORRECT - Validate before use
email = request.json.get('email', '').lower().strip()
if not is_valid_email(email):
    raise ValidationError("Invalid email format")
```

---

## 12. Performance Considerations

✅ **Use lazy loading and pagination:**

```python
# ✗ WRONG - N+1 query problem
users = User.query.all()
for user in users:
    print(user.orders)  # New query for each user!

# ✅ CORRECT - Use eager loading
users = User.query.options(joinedload(User.orders)).all()

# ✅ CORRECT - Use pagination
page = request.args.get('page', 1, type=int)
users = User.query.paginate(page=page, per_page=20)
```

✅ **Cache expensive operations:**

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_countries():
    """Cache list of countries."""
    return Country.query.all()

# Or use Redis for distributed caching
@cache.cached(timeout=3600, key_prefix='countries')
def get_countries():
    return Country.query.all()
```

---

## 13. Type Hints

✅ **Use type hints for clarity:**

```python
# ✅ CORRECT - Type hints
def create_user(email: str, password: str) -> User:
    """Create a new user account."""
    ...

def get_users(page: int = 1, per_page: int = 20) -> List[UserDto]:
    """Retrieve paginated users."""
    ...

# ✗ WRONG - No type hints
def create_user(email, password):
    # What types? What's returned?
    ...
```

---

## 14. Dependency Management

✅ **Use requirements.txt with pinned versions:**

```txt
# requirements.txt
Flask==2.3.2
Flask-SQLAlchemy==3.0.5
python-dotenv==1.0.0
pydantic==2.0.0
pytest==7.4.0
```

✅ **Separate dev and prod dependencies:**

```bash
# requirements.txt - Production
Flask==2.3.2
Flask-SQLAlchemy==3.0.5
gunicorn==21.2.0

# requirements-dev.txt - Development
-r requirements.txt
pytest==7.4.0
pytest-cov==4.1.0
black==23.7.0
```

---

## 15. Code Quality

✅ **Follow PEP 8 style guide:**
- 4 spaces per indentation level
- Maximum line length: 100 characters
- 2 blank lines between classes
- 1 blank line between methods

✅ **Use linting tools:**
```bash
# Check code style
flake8 src/
black --check src/
pylint src/

# Auto-fix
black src/
```

✅ **Document public APIs:**
```python
def transfer_funds(from_account: Account, to_account: Account, amount: Decimal) -> Transaction:
    """Transfer funds between accounts.

    Args:
        from_account: Source account
        to_account: Destination account
        amount: Amount to transfer

    Returns:
        Created transaction record

    Raises:
        InsufficientFundsError: If from_account lacks funds
        ValidationError: If amount is negative or zero
    """
```

---

**ENFORCEMENT:** These standards apply to all Python backend code in this project. Violations caught during code review or pre-commit hooks.
