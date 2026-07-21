# Flask Framework Standards

> Auto-loaded by Level 2 Standards System
> Layered on top of the language-level Python standards (`docs/02-backend-standards.md`) — this file covers Flask-specific idioms only.

---

## 1. Application Factory Pattern

### Rule 1.1: Never Create the Flask App at Module Import Time
- A module-level `app = Flask(__name__)` makes the app a global singleton — impossible to create multiple instances for testing with different configs
- Use an application factory function so tests can spin up isolated instances

```python
# BAD - global app instance, hard to test with different configs
app = Flask(__name__)
app.config.from_object(ProdConfig)
db.init_app(app)

# GOOD - factory function, callable with any config per test/run
def create_app(config_object=ProdConfig):
    app = Flask(__name__)
    app.config.from_object(config_object)
    db.init_app(app)
    register_blueprints(app)
    register_error_handlers(app)
    return app
```

### Rule 1.2: Initialize Extensions Outside the Factory, Bind Inside It
- Instantiate `SQLAlchemy()`, `Migrate()`, etc. at module level without an app, then call `.init_app(app)` inside the factory
- This is the deferred-initialization pattern Flask extensions are designed around

```python
# extensions.py - instantiated without an app
db = SQLAlchemy()
migrate = Migrate()

# app.py - bound to a specific app instance inside the factory
def create_app(config_object=ProdConfig):
    app = Flask(__name__)
    app.config.from_object(config_object)
    db.init_app(app)
    migrate.init_app(app, db)
    return app
```

---

## 2. Blueprints

### Rule 2.1: Organize Routes into Blueprints by Feature, Not by HTTP Verb
- One blueprint per feature/domain area (`users`, `orders`), not one per verb

```python
# BAD - single monolithic routes.py with everything
@app.route('/users', methods=['GET'])
def list_users(): ...

@app.route('/orders', methods=['GET'])
def list_orders(): ...

# GOOD - feature-scoped blueprints
# users/routes.py
users_bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

@users_bp.route('/', methods=['GET'])
def list_users(): ...

# app.py
app.register_blueprint(users_bp)
```

### Rule 2.2: Never Import `current_app` or Extensions at Blueprint Module Level
- Blueprint modules are imported before any app exists — importing `current_app` and using it at import time raises `RuntimeError: Working outside of application context`
- Only access `current_app`, `g`, `session`, or `request` inside request-handling functions

```python
# BAD - accessed at import time, outside any request/app context
from flask import current_app
DEBUG_MODE = current_app.config['DEBUG']  # RuntimeError

# GOOD - accessed inside the view function, where a context exists
@users_bp.route('/')
def list_users():
    debug_mode = current_app.config['DEBUG']
    ...
```

---

## 3. Request Validation

### Rule 3.1: Validate Request Bodies with Marshmallow/Pydantic Schemas, Not Manual `request.json.get()` Chains
- Manual dict access scatters validation logic across every route and silently accepts malformed input

```python
# BAD - manual validation, easy to forget a field
@users_bp.route('/', methods=['POST'])
def create_user():
    email = request.json.get('email')
    password = request.json.get('password')
    if not email:
        return {"error": "email required"}, 400
    # password length never checked...

# GOOD - schema validates everything before the handler runs
class UserCreateSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))

@users_bp.route('/', methods=['POST'])
def create_user():
    data = UserCreateSchema().load(request.json)  # raises ValidationError on bad input
    user = user_service.create(**data)
    return jsonify(user), 201
```

---

## 4. Error Handling

### Rule 4.1: Register Error Handlers Centrally, Never `try/except` Per Route for the Same Error Type
- A single `@app.errorhandler` covers every route, keeping error response format consistent

```python
# BAD - repeated in every route
@users_bp.route('/<int:id>')
def get_user(id):
    try:
        user = user_service.get(id)
    except UserNotFoundError:
        return {"error": "not found"}, 404

# GOOD - registered once, applies everywhere
@app.errorhandler(UserNotFoundError)
def handle_not_found(error):
    return jsonify({"success": False, "error": str(error)}), 404

@users_bp.route('/<int:id>')
def get_user(id):
    user = user_service.get(id)  # raises UserNotFoundError, handled globally
    return jsonify(user)
```

### Rule 4.2: Use `abort()` with a Custom Exception, Not Bare Return Tuples, for Non-2xx Responses Inside Business Logic
- Keeps error signaling consistent whether the failure happens in a route or three layers down in a service

```python
# BAD - service layer returns a tuple that only makes sense in a route
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return None, 404  # what does the caller do with this?
    return user, 200

# GOOD - service layer raises, route/error-handler decides the HTTP response
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        raise UserNotFoundError(user_id)
    return user
```

---

## 5. Database Sessions (Flask-SQLAlchemy)

### Rule 5.1: Never Manually Manage `db.session` Lifecycle in Routes
- Flask-SQLAlchemy already scopes and tears down the session per request via `teardown_appcontext`
- Manually calling `db.session.remove()` or creating a new session per route fights the framework

```python
# BAD - fighting the framework's session scoping
@users_bp.route('/', methods=['POST'])
def create_user():
    session = db.create_scoped_session()
    session.add(User(...))
    session.commit()
    session.close()

# GOOD - use the app-scoped session, let Flask-SQLAlchemy manage its lifecycle
@users_bp.route('/', methods=['POST'])
def create_user():
    user = User(email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user), 201
```

### Rule 5.2: Use Flask-Migrate for All Schema Changes
- Never hand-edit the database schema; always generate and review a migration

```bash
# GOOD
flask db migrate -m "add phone_number to users"
flask db upgrade
```

---

## 6. Configuration

### Rule 6.1: Use `Config` Classes Per Environment, Never Hardcoded Values in `app.config[...]`
- One base `Config` class, subclassed per environment (`DevConfig`, `TestConfig`, `ProdConfig`), values sourced from environment variables

```python
# GOOD
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProdConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
```

---

## 7. Testing

### Rule 7.1: Use the Factory Pattern to Build a Test Client Per Test, Never a Module-Level Client
- Reuse of a single global test client across tests leaks state (sessions, `g`) between them

```python
# GOOD - pytest fixture builds a fresh app + client per test
@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

def test_create_user_returns_201(client):
    response = client.post('/api/v1/users/', json={"email": "a@b.com", "password": "secret123"})
    assert response.status_code == 201
```

---

## 8. Common LLM Mistakes to Avoid

- Creating `app = Flask(__name__)` at module level instead of inside an application factory
- Accessing `current_app`, `g`, or `request` at import time, outside a request or app context
- Manually managing `db.session` lifecycle instead of relying on Flask-SQLAlchemy's per-request scoping
- Returning `(data, status_code)` tuples from service-layer functions instead of raising exceptions
- Validating request bodies with manual `request.json.get()` chains instead of a schema
- Hardcoding config values (`SECRET_KEY`, database URLs) instead of sourcing from environment-specific `Config` classes
- Sharing a single global test client across tests instead of a fresh one per test via a fixture
- Editing the database schema by hand instead of generating a Flask-Migrate migration
