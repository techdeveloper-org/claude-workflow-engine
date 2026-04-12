# 🎯 Prompt Generation & Structuring Policy

**VERSION:** 1.0.0
**CREATED:** 2026-02-16
**PRIORITY:** 🔴 CRITICAL - STEP 0 (Before all other policies)
**STATUS:** 🟢 ACTIVE

---

## 📋 POLICY OVERVIEW

**MANDATORY FIRST STEP:**
Before executing ANY task, Claude MUST convert the user's natural language input into a structured system prompt with:
- ✅ Clear Input/Output definitions
- ✅ Conditions & validations
- ✅ Examples from existing projects
- ✅ Architecture alignment
- ✅ Success criteria

---

## 🚨 EXECUTION ORDER

```
User Natural Language Input
        ↓
🔴 STEP 0: PROMPT GENERATION (THIS POLICY - MANDATORY)
        ↓
    🧠 THINKING PHASE (Mandatory - Anti-Hallucination)
        ↓
    🔍 INFORMATION GATHERING (Mandatory - Find Before Answer)
        ↓
    Structured System Prompt Generated
        ↓
    ✅ VERIFICATION (Answer based on found info only)
        ↓
🟢 Step 1: Context Check
🟢 Step 2: Model Selection
🟢 Step 3: Task/Phase Analysis
... (rest of the pipeline)
```

---

## 🎯 PROMPT STRUCTURING TEMPLATE

### **Input Format:**
```yaml
task_type: "[API/Feature/Fix/Refactor/Migration/etc]"
user_request: "[Original natural language request]"
project_context:
  project_name: "[e.g., sample-project]"
  service_name: "[e.g., user-service, product-service]"
  technology_stack: "[Spring Boot 3.2.0, PostgreSQL, etc]"
  existing_patterns: "[List from codebase]"

structured_input:
  entities:
    - name: "[Entity name]"
      fields: "[Field definitions]"
      validations: "[Validation rules]"

  endpoints:
    - method: "[GET/POST/PUT/DELETE]"
      path: "[/api/v1/...]"
      request: "[Request structure]"
      response: "[Response structure]"

  business_rules:
    - rule: "[Business logic]"
      condition: "[When to apply]"
      validation: "[How to validate]"

  dependencies:
    - service: "[Other services]"
      reason: "[Why needed]"

constraints:
  - "[Constraint 1]"
  - "[Constraint 2]"

conditions:
  pre_conditions:
    - condition: "[Must be true before starting]"
      validation: "[How to check]"
      example: "[From existing code]"

  post_conditions:
    - condition: "[Must be true after completion]"
      validation: "[How to verify]"
      test: "[How to test]"

expected_output:
  files_created:
    - path: "[Full path]"
      type: "[Entity/Controller/Service/etc]"
      purpose: "[Why needed]"

  files_modified:
    - path: "[Full path]"
      changes: "[What will change]"
      reason: "[Why changing]"

  configurations:
    - location: "[Config server path]"
      changes: "[What config added/modified]"

success_criteria:
  - "[Criterion 1: Builds successfully]"
  - "[Criterion 2: Tests pass]"
  - "[Criterion 3: API works as expected]"

examples_from_codebase:
  similar_implementations:
    - service: "[Service name]"
      file: "[Path to example]"
      pattern: "[What pattern to follow]"

  reference_code:
    - description: "[What this shows]"
      location: "[Where to find it]"
      usage: "[How to apply it]"
```

---

## 🛡️ ANTI-HALLUCINATION PRINCIPLES (MANDATORY)

**CRITICAL: Follow these rules to prevent hallucinations:**

### **Rule 1: THINK FIRST (Mandatory Thinking Phase)**
```
BEFORE doing anything:
1. 🧠 Understand what user is asking
2. 🧠 Break down into sub-questions
3. 🧠 Identify what information is needed
4. 🧠 Plan where to find that information
5. 🧠 Consider edge cases and unknowns

DO NOT rush to answer!
```

### **Rule 2: FIND RELEVANT INFORMATION FIRST (Mandatory Search Phase)**
```
NEVER answer based on assumptions!

ALWAYS search/read first:
1. 🔍 Search codebase for similar implementations
2. 🔍 Read existing files to understand patterns
3. 🔍 Check documentation files
4. 🔍 Find configuration examples
5. 🔍 Locate architecture standards

ONLY after finding information → Structure the prompt
```

### **Rule 3: ANSWER BASED ON FOUND INFORMATION ONLY**
```
When generating structured prompt:
✅ USE: Information from files you read
✅ USE: Examples from codebase you found
✅ USE: Patterns from documentation you checked

❌ AVOID: Assumptions about code structure
❌ AVOID: Guessing file locations
❌ AVOID: Making up API patterns
❌ AVOID: Inventing configuration syntax

IF information not found → Mark as "NEEDS_RESEARCH"
```

### **Rule 4: VERIFICATION STEP (Mandatory)**
```
Before finalizing structured prompt:
✅ Verify all examples actually exist in codebase
✅ Verify file paths are correct
✅ Verify patterns match existing code
✅ Verify assumptions against documentation

If anything is uncertain → Flag it in the prompt
```

---

## 🔍 PROMPT GENERATION PROCESS (UPDATED WITH ANTI-HALLUCINATION)

### **Phase 0: THINKING (NEW - MANDATORY)**
```python
# THINK: What does user want?
thinking = {
    "user_intent": "What is the user trying to achieve?",
    "core_question": "What is the main question?",
    "sub_questions": [
        "What entity/feature is involved?",
        "What operations are needed?",
        "What technology stack?",
        "What are the constraints?"
    ],
    "information_needed": [
        "Existing similar implementations",
        "Project structure",
        "Naming conventions",
        "Architecture patterns",
        "Configuration patterns"
    ],
    "where_to_find": {
        "implementations": "Search in existing services",
        "structure": "Read project directories",
        "conventions": "Check documentation",
        "patterns": "Read similar files",
        "config": "Check config server"
    }
}

# OUTPUT thinking to user
print("🧠 THINKING:")
print(f"  Intent: {thinking['user_intent']}")
print(f"  Information needed: {thinking['information_needed']}")
print(f"  Will search in: {thinking['where_to_find']}")
```

### **Phase 1: INFORMATION GATHERING (NEW - MANDATORY)**
```python
# SEARCH: Find relevant information FIRST
information_gathered = {}

# 1. Search for similar implementations
print("🔍 Searching for similar implementations...")
similar_files = search_codebase(
    pattern="CRUD API",
    file_types=["*.java"],
    services=["user-service", "auth-service", "product-service"]
)
information_gathered["similar_implementations"] = similar_files

# 2. Read existing files to understand patterns
print("📖 Reading existing files...")
for file in similar_files[:3]:  # Read top 3 matches
    content = read_file(file)
    patterns = extract_patterns(content)
    information_gathered["patterns"] = patterns

# 3. Check documentation
print("📚 Checking documentation...")
docs = [
    "java-project-structure.md",
    "api-design-standards.md",
    "spring-cloud-config.md"
]
for doc in docs:
    doc_content = read_file(doc)
    information_gathered["documentation"] = doc_content

# 4. Verify project structure
print("🔍 Verifying project structure...")
project_structure = scan_directory("sample-project/backend/")
information_gathered["project_structure"] = project_structure

# 5. Check configuration examples
print("⚙️ Checking configuration examples...")
config_examples = find_configs("configurations/sample-project/")
information_gathered["config_examples"] = config_examples

# OUTPUT what was found
print(f"✅ Found {len(similar_files)} similar implementations")
print(f"✅ Extracted {len(patterns)} patterns")
print(f"✅ Read {len(docs)} documentation files")
print(f"✅ Verified project structure")
```

### **Phase 2: VERIFICATION (NEW - MANDATORY)**
```python
# VERIFY: Check all information is accurate
verification = {
    "examples_exist": True,
    "paths_correct": True,
    "patterns_match": True,
    "assumptions": []
}

# Verify examples
for example in information_gathered["similar_implementations"]:
    if not file_exists(example):
        verification["examples_exist"] = False
        verification["assumptions"].append(f"Example not found: {example}")

# Verify paths
for path in information_gathered["project_structure"]:
    if not directory_exists(path):
        verification["paths_correct"] = False
        verification["assumptions"].append(f"Path not found: {path}")

# Flag uncertainties
if verification["assumptions"]:
    print("⚠️ UNCERTAINTIES FOUND:")
    for assumption in verification["assumptions"]:
        print(f"  - {assumption}")
    print("  These will be marked in the prompt for user confirmation")

# OUTPUT verification status
print("✅ VERIFICATION COMPLETE")
print(f"  Examples verified: {verification['examples_exist']}")
print(f"  Paths verified: {verification['paths_correct']}")
```

### **Phase 3: STRUCTURED PROMPT GENERATION (Based on verified info only)**

### **1. Analyze User Input**
```python
# Parse natural language
user_message = "Create a product API with CRUD operations"

# Extract key information
task_type = "API Creation"
entities = ["Product"]
operations = ["Create", "Read", "Update", "Delete"]
technology = "Spring Boot" (from context)
project = "sample-project" (from context)
```

### **2. Search for Similar Examples**
```python
# Find similar patterns in codebase
examples = search_codebase(
    pattern="CRUD API",
    technology="Spring Boot",
    services=["user-service", "auth-service"]
)

# Extract architecture patterns
architecture = {
    "package_structure": extract_from(examples),
    "naming_conventions": extract_from(examples),
    "response_format": "ApiResponseDto<T>",
    "validation_pattern": "Form extends ValidationMessageConstants"
}
```

### **3. Define Conditions**
```python
# Pre-conditions (Must be true before starting)
pre_conditions = [
    "Database entity must be defined",
    "Config server configuration must exist",
    "Dependencies must be in pom.xml"
]

# Post-conditions (Must be true after completion)
post_conditions = [
    "All CRUD endpoints must work",
    "Validation must be applied",
    "Responses must use ApiResponseDto",
    "Tests must pass"
]
```

### **4. Structure Input/Output**
```python
# Input structure
input_structure = {
    "entity": "Product",
    "fields": [
        {"name": "id", "type": "Long", "validation": "NotNull"},
        {"name": "name", "type": "String", "validation": "NotBlank"},
        {"name": "price", "type": "BigDecimal", "validation": "Positive"}
    ],
    "operations": ["create", "read", "update", "delete"]
}

# Output structure
output_structure = {
    "files": [
        "entity/Product.java",
        "repository/ProductRepository.java",
        "services/ProductService.java",
        "services/impl/ProductServiceImpl.java",
        "controller/ProductController.java",
        "dto/ProductDto.java",
        "form/ProductForm.java"
    ],
    "configurations": [
        "configurations/sample-project/services/product-service.yml"
    ]
}
```

### **5. Validate Against Architecture**
```python
# Check alignment with standards
validations = {
    "package_structure": check_against("java-project-structure.md"),
    "api_design": check_against("api-design-standards.md"),
    "error_handling": check_against("error-handling-standards.md"),
    "security": check_against("security-best-practices.md"),
    "database": check_against("database-standards.md")
}
```

### **6. Generate Structured Prompt**
```python
structured_prompt = generate_prompt(
    task_type=task_type,
    input_structure=input_structure,
    output_structure=output_structure,
    conditions={"pre": pre_conditions, "post": post_conditions},
    examples=examples,
    validations=validations,
    architecture=architecture
)
```

---

## 📚 KNOWLEDGE SOURCES FOR EXAMPLES

### **1. Existing Projects:**
```
example-workspace/
├── sample-project/
│   └── backend/
│       ├── auth-service/          # Auth patterns, JWT, security
│       ├── user-service/          # User CRUD, validation
│       └── product-service/       # Product operations
│
└── example-project/
    └── backend/
        ├── example-project-gateway/           # Gateway patterns
        ├── example-project-eureka/            # Service discovery
        ├── example-project-config-server/     # Config patterns
        └── example-project-secret-manager/    # Secret management
```

### **2. Architecture Documentation:**
```
~/.claude/memory/docs/
├── java-project-structure.md      # Package structure, naming
├── api-design-standards.md        # REST API patterns
├── error-handling-standards.md    # Exception handling
├── security-best-practices.md     # Security patterns
├── database-standards.md          # DB patterns
├── spring-cloud-config.md         # Config server usage
└── secret-management.md           # Secret patterns
```

### **3. Code Examples Database:**
```
# Build from existing code
examples_db = {
    "CRUD_API": {
        "user-service": "com.example-project.userservice.controller.UserController",
        "pattern": "Controller → Service → Repository",
        "response": "ApiResponseDto<T>"
    },
    "Authentication": {
        "auth-service": "com.example-project.authservice.controller.AuthController",
        "pattern": "JWT token generation",
        "security": "Spring Security configuration"
    },
    "Validation": {
        "pattern": "Form extends ValidationMessageConstants",
        "location": "*.form.*.java"
    }
}
```

---

## 🎯 EXAMPLE TRANSFORMATIONS

### **Example 1: Simple Request**

**User Input:**
> "Create a product API"

**Structured Prompt:**
```yaml
task_type: "REST API Creation"
user_request: "Create a product API"
project_context:
  project_name: "sample-project"
  service_name: "product-service"
  technology_stack:
    - "Spring Boot 3.2.0"
    - "PostgreSQL"
    - "Spring Cloud Config"
    - "Eureka Discovery"
  base_package: "com.example-project.sample-project.productservice"

structured_input:
  entity:
    name: "Product"
    table_name: "products"
    fields_inferred:
      - {name: "id", type: "Long", pk: true}
      - {name: "name", type: "String", required: true}
      - {name: "description", type: "String"}
      - {name: "price", type: "BigDecimal", required: true}
      - {name: "createdAt", type: "LocalDateTime", auto: true}
      - {name: "updatedAt", type: "LocalDateTime", auto: true}

  endpoints_required:
    - {method: "POST", path: "/api/v1/products", operation: "create"}
    - {method: "GET", path: "/api/v1/products/{id}", operation: "getById"}
    - {method: "GET", path: "/api/v1/products", operation: "getAll"}
    - {method: "PUT", path: "/api/v1/products/{id}", operation: "update"}
    - {method: "DELETE", path: "/api/v1/products/{id}", operation: "delete"}

conditions:
  pre_conditions:
    - condition: "Database must be configured"
      validation: "Check application.yml has datasource"
      example: "user-service/application.yml"

    - condition: "Base package structure must exist"
      validation: "Check com.example-project.sample-project.productservice exists"
      example: "user-service package structure"

    - condition: "Dependencies must be available"
      validation: "spring-boot-starter-data-jpa, postgresql in pom.xml"
      example: "user-service/pom.xml"

  post_conditions:
    - condition: "All endpoints return ApiResponseDto<T>"
      validation: "Response wrapping check"
      test: "Call each endpoint, verify structure"

    - condition: "Validation must work"
      validation: "Invalid data returns 400"
      test: "Send empty product name, expect validation error"

    - condition: "Database operations must be transactional"
      validation: "@Transactional on service methods"
      test: "Check service impl has annotations"

expected_output:
  files_created:
    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/entity/Product.java"
      type: "JPA Entity"
      purpose: "Database mapping"
      example: "user-service/entity/User.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/repository/ProductRepository.java"
      type: "JPA Repository"
      purpose: "Database operations"
      example: "user-service/repository/UserRepository.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/services/ProductService.java"
      type: "Service Interface"
      purpose: "Business logic contract"
      example: "user-service/services/UserService.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/services/impl/ProductServiceImpl.java"
      type: "Service Implementation"
      purpose: "Business logic"
      example: "user-service/services/impl/UserServiceImpl.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/controller/ProductController.java"
      type: "REST Controller"
      purpose: "API endpoints"
      example: "user-service/controller/UserController.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/dto/ProductDto.java"
      type: "Response DTO"
      purpose: "API response"
      example: "user-service/dto/UserDto.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/form/ProductForm.java"
      type: "Request Form"
      purpose: "API request validation"
      example: "user-service/form/UserForm.java"

  files_modified:
    - path: "backend/product-service/pom.xml"
      changes: "Add dependencies if missing"
      reason: "Ensure JPA, PostgreSQL available"

  configurations:
    - location: "example-project/backend/example-project-config-server/configurations/sample-project/services/product-service.yml"
      changes:
        - "Database configuration"
        - "JPA settings"
        - "Eureka registration"
      template: "user-service.yml"

success_criteria:
  - "✅ mvn clean install succeeds"
  - "✅ Service registers with Eureka"
  - "✅ All CRUD endpoints work"
  - "✅ Validation errors return proper messages"
  - "✅ Database transactions work"
  - "✅ Responses follow ApiResponseDto<T> pattern"

examples_from_codebase:
  similar_implementations:
    - service: "user-service"
      file: "controller/UserController.java"
      pattern: "CRUD operations with ApiResponseDto"
      location: "sample-project/backend/user-service/"

  reference_code:
    - description: "Entity with JPA annotations"
      location: "user-service/entity/User.java"
      usage: "Copy structure, modify fields"

    - description: "Repository pattern"
      location: "user-service/repository/UserRepository.java"
      usage: "Interface extending JpaRepository"

    - description: "Service implementation"
      location: "user-service/services/impl/UserServiceImpl.java"
      usage: "Package-private class, @Transactional"

    - description: "Controller with validation"
      location: "user-service/controller/UserController.java"
      usage: "REST endpoints, @Valid, ApiResponseDto"

    - description: "Form validation"
      location: "user-service/form/UserForm.java"
      usage: "Extends ValidationMessageConstants"

architecture_compliance:
  package_structure: "✅ Follows java-project-structure.md"
  api_design: "✅ Follows api-design-standards.md"
  error_handling: "✅ Follows error-handling-standards.md"
  security: "✅ Follows security-best-practices.md"
  database: "✅ Follows database-standards.md"
```

---

### **Example 2: Complex Request**

**User Input:**
> "Add authentication with JWT to product service, users should login and access products based on roles"

**Structured Prompt:**
```yaml
task_type: "Security Enhancement - JWT Authentication & Authorization"
user_request: "Add authentication with JWT to product service, users should login and access products based on roles"
project_context:
  project_name: "sample-project"
  affected_services:
    - "auth-service" (JWT generation)
    - "product-service" (JWT validation, role-based access)
  technology_stack:
    - "Spring Boot 3.2.0"
    - "Spring Security 6"
    - "JWT (jjwt)"
    - "PostgreSQL"

structured_input:
  authentication_flow:
    - step: "User sends credentials to auth-service"
      endpoint: "POST /api/v1/auth/login"
      request: {username: "string", password: "string"}
      response: {token: "jwt_string", expiresIn: "number"}

    - step: "User sends JWT to product-service"
      header: "Authorization: Bearer {token}"
      validation: "Gateway validates JWT"
      extraction: "Extract user details and roles"

  authorization_rules:
    - resource: "GET /api/v1/products"
      allowed_roles: ["USER", "ADMIN"]

    - resource: "POST /api/v1/products"
      allowed_roles: ["ADMIN"]

    - resource: "PUT /api/v1/products/{id}"
      allowed_roles: ["ADMIN"]

    - resource: "DELETE /api/v1/products/{id}"
      allowed_roles: ["ADMIN"]

  jwt_structure:
    payload:
      - sub: "User ID"
      - username: "Username"
      - roles: ["Array of roles"]
      - iat: "Issued at"
      - exp: "Expiration"

    secret: "Stored in Secret Manager"
    expiration: "24 hours"

conditions:
  pre_conditions:
    - condition: "auth-service must exist and be functional"
      validation: "Check auth-service can generate JWT"
      example: "auth-service/controller/AuthController.java"

    - condition: "Secret Manager must have JWT secret"
      validation: "Check secret exists for project"
      command: "Call Secret Manager API"

    - condition: "Gateway must be configured for routing"
      validation: "Check gateway routes to product-service"
      example: "example-project-gateway/application.yml"

    - condition: "User roles must be defined"
      validation: "Check Role enum/entity exists"
      example: "auth-service/entity/Role.java"

  post_conditions:
    - condition: "Unauthorized requests must return 401"
      validation: "Call endpoint without token"
      test: "curl /api/v1/products (expect 401)"

    - condition: "Invalid token must return 403"
      validation: "Call with expired/invalid token"
      test: "curl -H 'Authorization: Bearer invalid' (expect 403)"

    - condition: "Valid token with wrong role must return 403"
      validation: "USER role tries to create product"
      test: "POST /api/v1/products with USER token (expect 403)"

    - condition: "Valid token with correct role must work"
      validation: "ADMIN can create product"
      test: "POST /api/v1/products with ADMIN token (expect 201)"

expected_output:
  files_created:
    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/security/JwtAuthenticationFilter.java"
      type: "Security Filter"
      purpose: "Validate JWT on each request"
      example: "auth-service/security/JwtAuthenticationFilter.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/security/SecurityConfig.java"
      type: "Security Configuration"
      purpose: "Configure Spring Security"
      example: "auth-service/security/SecurityConfig.java"

    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/security/JwtUtil.java"
      type: "Utility Class"
      purpose: "JWT parsing and validation"
      example: "auth-service/security/JwtUtil.java"

  files_modified:
    - path: "backend/product-service/src/main/java/com/example-project/sample-project/productservice/controller/ProductController.java"
      changes:
        - "Add @PreAuthorize annotations"
        - "Add role-based access control"
      example: "hasRole('ADMIN') for create/update/delete"

    - path: "backend/product-service/pom.xml"
      changes:
        - "Add spring-boot-starter-security"
        - "Add jjwt dependencies"
      reason: "Enable Spring Security and JWT"

  configurations:
    - location: "example-project/backend/example-project-config-server/configurations/sample-project/services/product-service.yml"
      changes:
        - "jwt.secret: ${secret-manager.jwt.secret}"
        - "jwt.expiration: 86400000"
        - "security.enabled: true"

    - location: "Secret Manager"
      changes:
        - "Add jwt.secret for sample-project project"
      command: "POST /api/v1/secrets/project/sample-project"

success_criteria:
  - "✅ Unauthenticated requests return 401"
  - "✅ Invalid tokens return 403"
  - "✅ USER role can GET products"
  - "✅ USER role cannot POST/PUT/DELETE products"
  - "✅ ADMIN role can perform all operations"
  - "✅ JWT validation works across all endpoints"
  - "✅ Token expiration is enforced"

examples_from_codebase:
  similar_implementations:
    - service: "auth-service"
      file: "security/SecurityConfig.java"
      pattern: "Spring Security configuration with JWT"
      location: "sample-project/backend/auth-service/"

    - service: "auth-service"
      file: "security/JwtAuthenticationFilter.java"
      pattern: "Filter for JWT validation"
      usage: "Copy and adapt for product-service"

    - service: "auth-service"
      file: "security/JwtUtil.java"
      pattern: "JWT generation and parsing"
      usage: "Use validation methods only (not generation)"

  reference_code:
    - description: "JWT Filter implementation"
      location: "auth-service/security/JwtAuthenticationFilter.java"
      usage: "Extract token, validate, set security context"

    - description: "Security configuration"
      location: "auth-service/security/SecurityConfig.java"
      usage: "Configure filter chain, CORS, CSRF"

    - description: "Role-based authorization"
      location: "auth-service/controller/AdminController.java"
      usage: "@PreAuthorize('hasRole(\"ADMIN\")')"

architecture_compliance:
  security: "✅ Follows security-best-practices.md"
  jwt_pattern: "✅ Consistent with auth-service implementation"
  config_management: "✅ Secrets in Secret Manager"
  error_handling: "✅ Proper 401/403 responses"
```

---

## 🔧 IMPLEMENTATION SCRIPT

**File:** `~/.claude/memory/prompt-generator.py`

```python
#!/usr/bin/env python3
"""
Prompt Generation & Structuring Script
Converts natural language to structured prompts
"""

import yaml
import json
from typing import Dict, List, Any
from pathlib import Path

class PromptGenerator:
    def __init__(self):
        self.workspace = Path("C:/Users/techd/Documents/example-workspace")
        self.docs = Path("C:/Users/techd/.claude/memory/docs")
        self.examples_db = self.load_examples()

    def load_examples(self) -> Dict:
        """Load examples from existing codebase"""
        examples = {
            "CRUD_API": [],
            "Authentication": [],
            "Authorization": [],
            "Validation": [],
            "Configuration": []
        }
        # Scan workspace for patterns
        # Build examples database
        return examples

    def analyze_request(self, user_message: str) -> Dict:
        """Analyze natural language request"""
        analysis = {
            "task_type": self.detect_task_type(user_message),
            "entities": self.extract_entities(user_message),
            "operations": self.extract_operations(user_message),
            "keywords": self.extract_keywords(user_message)
        }
        return analysis

    def detect_task_type(self, message: str) -> str:
        """Detect what kind of task this is"""
        keywords_map = {
            "API Creation": ["create api", "add api", "new api", "crud"],
            "Authentication": ["auth", "login", "jwt", "token"],
            "Authorization": ["role", "permission", "access control"],
            "Database": ["database", "table", "migration", "schema"],
            "Configuration": ["config", "configure", "setup"],
            "Bug Fix": ["fix", "bug", "error", "issue"],
            "Refactoring": ["refactor", "improve", "optimize", "clean"]
        }

        message_lower = message.lower()
        for task_type, keywords in keywords_map.items():
            if any(kw in message_lower for kw in keywords):
                return task_type

        return "General Task"

    def extract_entities(self, message: str) -> List[str]:
        """Extract entity names from message"""
        # Simple extraction - can be enhanced
        common_entities = ["user", "product", "order", "category", "role", "permission"]
        found = [e for e in common_entities if e in message.lower()]
        return found

    def extract_operations(self, message: str) -> List[str]:
        """Extract operations from message"""
        operations = []
        if "create" in message.lower() or "add" in message.lower():
            operations.append("create")
        if "read" in message.lower() or "get" in message.lower() or "fetch" in message.lower():
            operations.append("read")
        if "update" in message.lower() or "edit" in message.lower():
            operations.append("update")
        if "delete" in message.lower() or "remove" in message.lower():
            operations.append("delete")
        if "crud" in message.lower():
            operations = ["create", "read", "update", "delete"]
        return operations

    def find_similar_examples(self, task_type: str, entities: List[str]) -> List[Dict]:
        """Find similar implementations in codebase"""
        examples = []

        # Search in existing services
        for service_dir in self.workspace.glob("*/backend/*-service"):
            # Look for similar patterns
            # Add to examples
            pass

        return examples

    def define_conditions(self, task_type: str, analysis: Dict) -> Dict:
        """Define pre and post conditions"""
        conditions = {
            "pre_conditions": [],
            "post_conditions": []
        }

        # Based on task type, add relevant conditions
        if task_type == "API Creation":
            conditions["pre_conditions"].extend([
                {
                    "condition": "Database must be configured",
                    "validation": "Check application.yml",
                    "example": "user-service/application.yml"
                },
                {
                    "condition": "Base package must exist",
                    "validation": "Check package structure",
                    "example": "java-project-structure.md"
                }
            ])

            conditions["post_conditions"].extend([
                {
                    "condition": "All endpoints must work",
                    "validation": "Test each endpoint",
                    "test": "curl requests"
                },
                {
                    "condition": "Responses must use ApiResponseDto",
                    "validation": "Check response structure",
                    "test": "Verify JSON structure"
                }
            ])

        return conditions

    def structure_input_output(self, analysis: Dict) -> Dict:
        """Structure input and expected output"""
        structure = {
            "input": {},
            "output": {
                "files_created": [],
                "files_modified": [],
                "configurations": []
            }
        }

        # Based on analysis, define structure
        # ...

        return structure

    def validate_architecture_alignment(self, structured_prompt: Dict) -> List[str]:
        """Validate against architecture standards"""
        violations = []

        # Check against various standards
        standards = [
            "java-project-structure.md",
            "api-design-standards.md",
            "error-handling-standards.md",
            "security-best-practices.md"
        ]

        for standard in standards:
            # Validate against standard
            # Add violations if found
            pass

        return violations

    def generate(self, user_message: str) -> Dict:
        """Main method: Generate structured prompt from natural language"""

        # Step 1: Analyze request
        analysis = self.analyze_request(user_message)

        # Step 2: Find similar examples
        examples = self.find_similar_examples(
            analysis["task_type"],
            analysis["entities"]
        )

        # Step 3: Define conditions
        conditions = self.define_conditions(
            analysis["task_type"],
            analysis
        )

        # Step 4: Structure input/output
        io_structure = self.structure_input_output(analysis)

        # Step 5: Generate structured prompt
        structured_prompt = {
            "task_type": analysis["task_type"],
            "user_request": user_message,
            "project_context": {
                "project_name": "sample-project",  # From context
                "service_name": self.infer_service(analysis),
                "technology_stack": self.get_tech_stack()
            },
            "structured_input": io_structure["input"],
            "conditions": conditions,
            "expected_output": io_structure["output"],
            "examples_from_codebase": examples,
            "success_criteria": self.define_success_criteria(analysis)
        }

        # Step 6: Validate architecture alignment
        violations = self.validate_architecture_alignment(structured_prompt)
        if violations:
            structured_prompt["architecture_violations"] = violations

        return structured_prompt

    def infer_service(self, analysis: Dict) -> str:
        """Infer which service this applies to"""
        entity_service_map = {
            "user": "user-service",
            "auth": "auth-service",
            "product": "product-service",
            "order": "order-service"
        }

        for entity in analysis["entities"]:
            if entity in entity_service_map:
                return entity_service_map[entity]

        return "unknown-service"

    def get_tech_stack(self) -> List[str]:
        """Get technology stack"""
        return [
            "Spring Boot 3.2.0",
            "Spring Cloud 2023.0.0",
            "PostgreSQL 15",
            "Redis 7",
            "Eureka Discovery",
            "Config Server",
            "Gateway"
        ]

    def define_success_criteria(self, analysis: Dict) -> List[str]:
        """Define success criteria"""
        criteria = [
            "✅ Code builds successfully (mvn clean install)",
            "✅ Service starts without errors",
            "✅ Registers with Eureka"
        ]

        if analysis["task_type"] == "API Creation":
            criteria.extend([
                "✅ All endpoints respond correctly",
                "✅ Validation works as expected",
                "✅ Responses follow ApiResponseDto pattern"
            ])

        return criteria


def main():
    """CLI interface"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python prompt-generator.py 'user message'")
        sys.exit(1)

    user_message = " ".join(sys.argv[1:])

    generator = PromptGenerator()
    structured_prompt = generator.generate(user_message)

    # Output as YAML
    print(yaml.dump(structured_prompt, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()
```

---

## 🚀 USAGE

### **Method 1: Automatic (Preferred)**
```python
# Claude automatically runs this before executing
python ~/.claude/memory/prompt-generator.py "Create product API with CRUD"

# Output: Structured prompt in YAML
# Claude uses this structured prompt for execution
```

### **Method 2: Manual Validation**
```python
# User can manually check what Claude understood
python ~/.claude/memory/prompt-generator.py "Add JWT authentication to product service"

# Review structured output
# Confirm with Claude before execution
```

---

## 📋 INTEGRATION WITH EXECUTION FLOW

```
User Natural Language Input
        ↓
🔴 prompt-generator.py (THIS POLICY)
        ↓
    Structured Prompt Generated
        ↓
    Show to User (Optional - for complex tasks)
        ↓
    User Confirms or Adjusts
        ↓
🟢 context-monitor.py (Context Check)
🟢 model-selection-enforcer.py (Model Selection)
🟢 task-phase-enforcer.py (Task/Phase Analysis)
        ↓
    ... (rest of pipeline)
```

---

## ✅ SUCCESS METRICS

### **Prompt Quality:**
- ✅ Clear input/output structure
- ✅ All conditions defined
- ✅ Examples from codebase included
- ✅ Architecture alignment validated
- ✅ Success criteria measurable

### **Execution Efficiency:**
- ✅ Reduced ambiguity
- ✅ Fewer clarification questions
- ✅ Faster implementation
- ✅ Better code quality
- ✅ Fewer mistakes

---

## 🔄 CONTINUOUS IMPROVEMENT

**Learning Loop:**
```
Execute Task → Collect Results → Analyze Success → Update Examples DB
```

**Feedback Integration:**
```
User Feedback → Adjust Prompt Generation → Improve Templates → Better Results
```

---

**VERSION:** 1.0.0
**CREATED:** 2026-02-16
**LOCATION:** `~/.claude/memory/prompt-generation-policy.md`
**SCRIPT:** `~/.claude/memory/prompt-generator.py`
