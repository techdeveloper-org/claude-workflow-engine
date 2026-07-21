---
description: "Level 2.1 - Security standards (Authentication, Encryption, Secrets)"
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
  - "src/**/*.py"
  - "src/**/*.java"
  - "scripts/**/*.py"
  - "config/**/*.yml"
priority: critical
---

# Security Standards (Level 2.1)

**PURPOSE:** Enforce security best practices across all layers: authentication, encryption, secrets management, and data protection.

---

## 1. Authentication & Authorization

✅ **JWT Token Management (Stateless):**

```typescript
// ✅ CORRECT - JWT handling
interface JwtPayload {
  sub: string;           // User ID
  email: string;
  role: 'admin' | 'user';
  iat: number;           // Issued at
  exp: number;           // Expiration
}

// Frontend: Store in memory (or secure httpOnly cookie from backend)
const token = localStorage.getItem('authToken');  // For SPA
// Or: Let backend set httpOnly cookie (preferred)

// API request
const headers = {
  'Authorization': `Bearer ${token}`
};

// Backend: Verify JWT
import jwt from 'jsonwebtoken';

const verifyToken = (token: string): JwtPayload => {
  try {
    return jwt.verify(token, process.env.JWT_SECRET!) as JwtPayload;
  } catch (error) {
    throw new Error('Invalid token');
  }
};
```

✅ **Password hashing (never store plaintext):**

```python
# ✅ CORRECT - Python with bcrypt
from werkzeug.security import generate_password_hash, check_password_hash

# Creating account
hashed = generate_password_hash(plaintext_password, method='pbkdf2:sha256')
user.password = hashed

# Verifying login
if check_password_hash(user.password, provided_password):
    # Password matches
    token = create_jwt(user.id)
```

```java
// ✅ CORRECT - Java with BCrypt
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
String hashed = encoder.encode(plaintext_password);

// Verify
if (encoder.matches(plaintext_password, user.getPassword())) {
    // Password matches
}
```

✅ **Role-based access control (RBAC):**

```typescript
// ✅ CORRECT - Check authorization before action
interface AuthContext {
  user: User | null;
  token: string | null;
  isAdmin: () => boolean;
  hasPermission: (permission: string) => boolean;
}

// Route protection
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isAdmin } = useAuth();

  if (!user) {
    return <Navigate to="/login" />;
  }

  if (!isAdmin()) {
    return <Navigate to="/unauthorized" />;
  }

  return <>{children}</>;
};

// API endpoint protection
app.post('/admin/users', authenticate, requireRole('admin'), (req, res) => {
  // Only admins can reach here
});
```

---

## 2. Secrets Management

❌ **NEVER hardcode secrets:**

```python
# ✗ WRONG - Secrets exposed!
DATABASE_PASSWORD = "SuperSecret123"
API_KEY = "sk-abc123def456"
JWT_SECRET = "my-secret-key"
AWS_SECRET_ACCESS_KEY = "awsSecretKey123"
```

✅ **Use environment variables:**

```python
# .env (in .gitignore)
DATABASE_PASSWORD=SuperSecret123
API_KEY=sk-abc123def456
JWT_SECRET=my-secret-key
AWS_SECRET_ACCESS_KEY=awsSecretKey123

# Code
import os
db_password = os.getenv('DATABASE_PASSWORD')
api_key = os.getenv('API_KEY')
jwt_secret = os.getenv('JWT_SECRET')
```

✅ **Use secret management tools:**

```yaml
# AWS Secrets Manager example
secret_name: "prod/api/secrets"
secrets:
  - key: DATABASE_PASSWORD
    value: "actual-encrypted-password"
  - key: API_KEY
    value: "actual-api-key"
  - key: JWT_SECRET
    value: "actual-jwt-secret"

# Application retrieves at runtime
import boto3
client = boto3.client('secretsmanager')
secret = client.get_secret_value(SecretId='prod/api/secrets')
```

✅ **Version control setup:**

```bash
# .gitignore - MANDATORY
.env
.env.local
.env.*.local
secrets.json
credentials.json
private_key.pem
*.key
*.pem
```

```bash
# Git pre-commit hook to prevent accidental commits
#!/bin/bash
if git diff --cached | grep -E '(password|secret|api_key|DATABASE_PASSWORD)'; then
  echo "ERROR: Potential secrets detected in staged changes!"
  echo "Make sure these are in .gitignore and .env files"
  exit 1
fi
```

---

## 3. SQL Injection Prevention

❌ **NEVER concatenate queries:**

```sql
-- ✗ WRONG - SQL Injection vulnerability!
SELECT * FROM users WHERE email = '" + userEmail + "'"

-- Input: ' OR '1'='1
-- Resulting query: SELECT * FROM users WHERE email = '' OR '1'='1'
-- This returns ALL users!
```

✅ **Use parameterized queries:**

```python
# ✅ CORRECT - Python with parameterized query
cursor.execute("SELECT * FROM users WHERE email = %s", (user_email,))

# ✅ CORRECT - ORM (SQLAlchemy)
user = User.query.filter_by(email=user_email).first()

# ✅ CORRECT - Java with prepared statement
PreparedStatement stmt = connection.prepareStatement(
    "SELECT * FROM users WHERE email = ?"
);
stmt.setString(1, userEmail);
ResultSet rs = stmt.executeQuery();
```

---

## 4. XSS (Cross-Site Scripting) Prevention

❌ **NEVER render untrusted HTML:**

```typescript
// ✗ WRONG - User input rendered as HTML
const UserProfile = ({ bio }: { bio: string }) => (
  <div dangerouslySetInnerHTML={{ __html: bio }} />
);

// If bio = "<img src=x onerror='alert(\"hacked\")'>"
// Script will execute!
```

✅ **Sanitize user input:**

```typescript
// ✅ CORRECT - Use DOMPurify
import DOMPurify from 'dompurify';

const UserProfile = ({ bio }: { bio: string }) => {
  const cleanHtml = DOMPurify.sanitize(bio, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'p', 'a'],
    ALLOWED_ATTR: ['href', 'title']
  });

  return <div dangerouslySetInnerHTML={{ __html: cleanHtml }} />;
};
```

✅ **React auto-escapes by default:**

```typescript
// ✅ CORRECT - React escapes variables
const UserProfile = ({ bio }: { bio: string }) => (
  <div>{bio}</div>  // Auto-escaped, safe!
);

// If bio = "<img src=x onerror='alert()'>"
// Renders as literal text: "<img src=x onerror='alert()'>"
```

---

## 5. CORS (Cross-Origin Resource Sharing)

✅ **Restrict CORS to known domains:**

```python
# ✅ CORRECT - Flask with restricted CORS
from flask_cors import CORS

CORS(app, resources={
    r"/api/*": {
        "origins": ["https://example.com", "https://app.example.com"],
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "max_age": 3600
    }
})
```

```java
// ✅ CORRECT - Spring Boot CORS config
@Configuration
public class CorsConfig {
    @Bean
    public WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                    .allowedOrigins("https://example.com")
                    .allowedMethods("GET", "POST", "PUT", "DELETE")
                    .allowedHeaders("Content-Type", "Authorization")
                    .maxAge(3600);
            }
        };
    }
}
```

❌ **NEVER allow all origins:**

```python
# ✗ WRONG - Opens to any domain
CORS(app)  # Default: allow all origins
```

---

## 6. CSRF (Cross-Site Request Forgery) Protection

✅ **Use CSRF tokens:**

```html
<!-- ✅ CORRECT - Hidden CSRF token in form -->
<form method="POST" action="/api/users">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input type="text" name="username">
  <button type="submit">Create</button>
</form>
```

```python
# ✅ CORRECT - Server-side CSRF validation
@app.route('/api/users', methods=['POST'])
def create_user():
    csrf_token = request.form.get('csrf_token')
    if not csrf.validate_token(csrf_token):
        return {"error": "Invalid CSRF token"}, 403
    # Process request
```

---

## 7. Rate Limiting

✅ **Implement rate limiting for API endpoints:**

```python
# ✅ CORRECT - Flask-Limiter
from flask_limiter import Limiter

limiter = Limiter(
    app=app,
    key_func=lambda: request.remote_addr
)

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    # Max 5 login attempts per minute per IP
    pass

@app.route('/api/users', methods=['GET'])
@limiter.limit("100 per hour")
def get_users():
    # Max 100 requests per hour
    pass
```

```java
// ✅ CORRECT - Spring Boot with Bucket4j
@RestController
@RequestMapping("/api")
public class ApiController {

    private final Bandwidth limit = Bandwidth.classic(100, Refill.intervally(100, Duration.ofHours(1)));
    private final Bucket bucket = Bucket4j.builder()
        .addLimit(limit)
        .build();

    @GetMapping("/users")
    public ResponseEntity<?> getUsers() {
        if (!bucket.tryConsume(1)) {
            return ResponseEntity.status(429).body("Rate limit exceeded");
        }
        // Process request
    }
}
```

---

## 8. Data Encryption

✅ **Encrypt sensitive data at rest:**

```python
# ✅ CORRECT - AES encryption for sensitive fields
from cryptography.fernet import Fernet

class User:
    def __init__(self):
        self.encryption_key = os.getenv('ENCRYPTION_KEY')
        self.cipher = Fernet(self.encryption_key)

    def encrypt_ssn(self, ssn: str) -> str:
        return self.cipher.encrypt(ssn.encode()).decode()

    def decrypt_ssn(self, encrypted_ssn: str) -> str:
        return self.cipher.decrypt(encrypted_ssn.encode()).decode()

# Usage
user = User()
encrypted_ssn = user.encrypt_ssn("123-45-6789")
# Store encrypted_ssn in database

# Retrieve and decrypt
decrypted_ssn = user.decrypt_ssn(encrypted_ssn)
```

✅ **Use HTTPS everywhere:**

```python
# ✅ CORRECT - Force HTTPS
@app.before_request
def enforce_https():
    if not request.is_secure and not app.debug:
        return redirect(
            request.url.replace('http://', 'https://', 1),
            code=301
        )
```

---

## 9. Input Validation

✅ **Validate all external input:**

```python
# ✅ CORRECT - Input validation before processing
from pydantic import BaseModel, EmailStr, validator

class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    age: int

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain uppercase letter')
        return v

    @validator('age')
    def age_valid(cls, v):
        if v < 18:
            raise ValueError('Must be 18 or older')
        return v

# Automatic validation on request
@app.post('/users')
def create_user(request: UserCreateRequest):
    # request is already validated
    pass
```

---

## 10. Logging Sensitive Data

❌ **NEVER log sensitive information:**

```python
# ✗ WRONG - Exposes credentials!
logger.debug(f"User login: email={email}, password={password}")
logger.debug(f"API request: token={api_token}, ssn={ssn}")
logger.debug(f"Database: {connection_string}")
```

✅ **Log safely:**

```python
# ✅ CORRECT - Log without sensitive data
logger.info(f"User login attempt: email={email}")
logger.debug(f"API request to endpoint: {endpoint}")
logger.debug(f"Database query executed")

# If you must log sensitive data, mask it
def mask_token(token: str) -> str:
    return token[:10] + "***" + token[-4:]

logger.debug(f"Token: {mask_token(api_token)}")
```

---

## 11. Dependency Security

✅ **Keep dependencies updated:**

```bash
# Check for vulnerabilities
npm audit
pip check
cargo audit

# Update to latest safe versions
npm update
pip install --upgrade package-name
```

✅ **Use lock files:**

```bash
# Commit lock files to version control
package-lock.json    # npm
poetry.lock         # Python poetry
Gemfile.lock        # Ruby
```

---

## 12. Security Headers

✅ **Set security headers in responses:**

```python
# ✅ CORRECT - Flask with security headers
from flask import Flask

app = Flask(__name__)

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

```java
// ✅ CORRECT - Spring Boot security headers
@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .headers()
            .contentSecurityPolicy("default-src 'self'")
            .and()
            .frameOptions().deny()
            .and()
            .xssProtection();
        return http.build();
    }
}
```

---

## 13. Access Logging & Monitoring

✅ **Log all security-relevant events:**

```python
# ✅ CORRECT - Log authentication events
logger.info(
    "User login successful",
    extra={
        "user_id": user.id,
        "ip_address": request.remote_addr,
        "user_agent": request.user_agent,
        "timestamp": datetime.utcnow().isoformat()
    }
)

logger.warning(
    "Failed login attempt",
    extra={
        "email": email,
        "ip_address": request.remote_addr,
        "attempts": failed_count
    }
)

logger.error(
    "Unauthorized access attempt",
    extra={
        "user_id": user_id,
        "resource": resource_path,
        "method": request.method
    }
)
```

---

## 14. API Security

✅ **API Key management:**

```python
# ✅ CORRECT - API key validation
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or not validate_api_key(api_key):
            return {"error": "Invalid API key"}, 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/data')
@require_api_key
def get_data():
    # Only requests with valid API key reach here
    pass
```

✅ **API versioning for security updates:**

```
/api/v1/users      <- Deprecated, plan sunset
/api/v2/users      <- Current, with security fixes
/api/v3/users      <- Beta, testing security enhancements
```

---

**ENFORCEMENT:** Security standards are CRITICAL. All violations must be addressed immediately. Never bypass security checks for convenience.
