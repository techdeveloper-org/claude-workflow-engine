# 🛡️ Anti-Hallucination Enforcement Policy

**VERSION:** 1.0.0
**CREATED:** 2026-02-16
**PRIORITY:** 🔴 CRITICAL - Integrated with STEP 0
**STATUS:** 🟢 ACTIVE

---

## 📋 POLICY OVERVIEW

**MANDATORY RULES to prevent hallucinations and ensure accuracy:**

1. **🧠 THINK FIRST** - Always use thinking phase before responding
2. **🔍 FIND BEFORE ANSWER** - Search/read relevant information first
3. **✅ VERIFY EVERYTHING** - Answer based on found information only
4. **⏸️ GIVE TIME TO THINK** - Don't rush, use reasoning steps

---

## 🚨 THE PROBLEM: Hallucination Sources

### **Common Hallucination Causes:**

1. **Assumption-Based Answers**
   - ❌ Assuming file structure without checking
   - ❌ Guessing API patterns
   - ❌ Making up configuration syntax
   - ❌ Inventing method names

2. **Rushing to Answer**
   - ❌ Skipping information gathering
   - ❌ No verification step
   - ❌ Not reading existing code
   - ❌ Not checking documentation

3. **Memory Limitations**
   - ❌ Relying on training data (outdated)
   - ❌ Not checking current codebase
   - ❌ Assuming patterns that don't exist
   - ❌ Using deprecated approaches

4. **Incomplete Context**
   - ❌ Not understanding full requirements
   - ❌ Missing edge cases
   - ❌ Incomplete information gathering
   - ❌ Partial codebase understanding

---

## ✅ THE SOLUTION: Mandatory 3-Phase Process

### **PHASE 1: THINKING (🧠 Mandatory)**

```
BEFORE doing anything, I MUST:

1. Understand the Question
   - What is user asking?
   - What is the core intent?
   - What are the sub-questions?

2. Identify Required Information
   - What do I need to know?
   - Where can I find it?
   - What examples exist?

3. Plan the Search
   - Which files to read?
   - Which patterns to search?
   - Which docs to check?

4. Consider Unknowns
   - What am I uncertain about?
   - What could go wrong?
   - What edge cases exist?

OUTPUT: Thinking summary visible to user
```

**Example:**
```
User: "Create a product API with CRUD operations"

🧠 THINKING:
  Intent: User wants a REST API for Product entity with Create, Read, Update, Delete

  Sub-questions:
  - What's the project structure?
  - What patterns are used in existing services?
  - What's the package naming convention?
  - How are responses structured?
  - How is validation done?

  Information needed:
  - Similar CRUD implementations
  - Project base package structure
  - Response DTO pattern
  - Validation pattern
  - Database configuration pattern

  Where to find:
  - user-service (has CRUD for User entity)
  - auth-service (has request/response patterns)
  - java-project-structure.md (package structure)
  - api-design-standards.md (API patterns)

  Uncertainties:
  - Does product-service directory already exist?
  - What fields should Product entity have?
  - What validation rules apply?
```

---

### **PHASE 2: INFORMATION GATHERING (🔍 Mandatory)**

```
I MUST search/read BEFORE answering:

1. Search Codebase
   ✅ Find similar implementations
   ✅ Search for pattern examples
   ✅ Locate relevant files

2. Read Files
   ✅ Read existing similar code
   ✅ Extract actual patterns used
   ✅ Note naming conventions

3. Check Documentation
   ✅ Read architecture docs
   ✅ Check standards documents
   ✅ Review configuration guides

4. Verify Structure
   ✅ Check directory structure
   ✅ Verify file paths exist
   ✅ Confirm dependencies

OUTPUT: What information was found and verified
```

**Example:**
```
🔍 SEARCHING FOR INFORMATION...

1. Searching for CRUD implementations...
   ✅ Found: user-service/controller/UserController.java
   ✅ Found: user-service/services/UserService.java
   ✅ Found: user-service/entity/User.java

2. Reading UserController.java...
   ✅ Pattern found: ApiResponseDto<T> for responses
   ✅ Pattern found: @Valid for request validation
   ✅ Pattern found: Form classes for requests
   ✅ Endpoints: POST /create, GET /{id}, GET /list, PUT /update, DELETE /{id}

3. Reading java-project-structure.md...
   ✅ Package structure: com.example-project.{project}.{service}
   ✅ Packages: controller, services, services.impl, entity, repository, dto, form

4. Checking project structure...
   ✅ Base path exists: sample-project/backend/
   ✅ Services found: auth-service, user-service
   ⚠️ product-service NOT found (will need to create)

5. Reading api-design-standards.md...
   ✅ Response format: ApiResponseDto<T> with success, message, data
   ✅ Error handling: ValidationException, NotFoundException
   ✅ Status codes: 200 OK, 201 Created, 400 Bad Request, 404 Not Found

INFORMATION GATHERING COMPLETE ✅
All examples verified and patterns extracted from actual code.
```

---

### **PHASE 3: VERIFICATION & ANSWER (✅ Mandatory)**

```
BEFORE generating final answer, I MUST verify:

1. Examples Verification
   ✅ All file paths actually exist
   ✅ All patterns extracted from real code
   ✅ All configurations found in actual files

2. Pattern Validation
   ✅ Patterns match current codebase
   ✅ Not using deprecated approaches
   ✅ Consistent with documentation

3. Assumption Check
   ❌ No assumptions made
   ❌ No guessed file locations
   ❌ No invented patterns
   ❌ No made-up configurations

4. Uncertainty Flagging
   ⚠️ Mark anything uncertain
   ⚠️ Flag missing information
   ⚠️ Note where user input needed

OUTPUT: Answer based ONLY on verified information
```

**Example:**
```
✅ VERIFICATION COMPLETE

Based on verified information:

1. Response Pattern (from UserController.java):
   ✅ Verified: ApiResponseDto<T>
   ✅ Location: user-service/dto/ApiResponseDto.java
   ✅ Usage confirmed in 15 endpoints

2. Package Structure (from actual codebase):
   ✅ Verified: com.example-project.sample-project.userservice
   ✅ Packages exist: controller, services, entity, repository, dto, form
   ✅ Pattern confirmed in user-service and auth-service

3. Validation Pattern (from UserForm.java):
   ✅ Verified: Form extends ValidationMessageConstants
   ✅ Location: user-service/form/UserForm.java
   ✅ Annotations: @NotBlank, @Email, @Pattern

⚠️ UNCERTAINTIES:
- Product entity fields not specified by user
- Will need user input for: field names, types, validations

PROCEEDING with structured prompt based on verified patterns...
```

---

## 🎯 INTEGRATION WITH PROMPT GENERATION

### **Updated Prompt Generation Flow:**

```
User Message
    ↓
🧠 PHASE 1: THINKING (Output visible)
    ↓
🔍 PHASE 2: INFORMATION GATHERING (Output visible)
    ↓
✅ PHASE 3: VERIFICATION (Output visible)
    ↓
📄 Generate Structured Prompt (Based on verified info)
    ↓
Continue to Step 1 (Context Check)
```

### **Mandatory Outputs to User:**

```markdown
## 🧠 Understanding Your Request

**Intent:** [What user wants to achieve]
**Key Questions:** [Sub-questions identified]
**Information Needed:** [What needs to be found]

---

## 🔍 Gathering Information

**Searching for:** [What to search]
**Found:** [List of files/patterns found]
**Reading:** [Files being read]
**Extracted:** [Patterns extracted]

---

## ✅ Verification

**Examples Verified:** ✅/❌
**Patterns Matched:** ✅/❌
**Assumptions Made:** [List any assumptions]
**Uncertainties:** [List anything unclear]

---

## 📄 Structured Prompt Generated

[Full structured prompt based on verified information]
```

---

## 🔧 IMPLEMENTATION RULES

### **For Claude Code:**

**MUST DO:**
```python
# 1. Show thinking
print("🧠 THINKING:")
print(f"  Understanding: {intent}")
print(f"  Need to find: {information_needed}")

# 2. Search first, then read
files = Glob(pattern="**/*Controller.java")
for file in files[:3]:
    content = Read(file)
    patterns = extract_patterns(content)

# 3. Verify before using
for example in examples:
    if not verify_exists(example):
        flag_uncertainty(example)

# 4. Generate based on verified info only
structured_prompt = generate_from_verified_info(verified_patterns)
```

**MUST NOT DO:**
```python
# ❌ NEVER assume file locations
path = "backend/product-service/..."  # Without checking it exists

# ❌ NEVER guess patterns
response = "ApiResponse"  # Without reading actual code

# ❌ NEVER rush to answer
return answer  # Without searching/reading first

# ❌ NEVER hide uncertainties
# If unsure, MUST flag it explicitly
```

---

## 📊 ANTI-HALLUCINATION CHECKLIST

**Before generating ANY answer, verify:**

- [ ] 🧠 Did I think about what's needed?
- [ ] 🧠 Did I break down into sub-questions?
- [ ] 🧠 Did I identify information sources?

- [ ] 🔍 Did I search for similar code?
- [ ] 🔍 Did I read existing implementations?
- [ ] 🔍 Did I check documentation?
- [ ] 🔍 Did I verify project structure?

- [ ] ✅ Are all examples from actual code?
- [ ] ✅ Are all file paths verified?
- [ ] ✅ Are all patterns confirmed?
- [ ] ✅ Did I flag uncertainties?

- [ ] 📄 Is answer based ONLY on verified info?
- [ ] 📄 Are all assumptions clearly marked?
- [ ] 📄 Is user informed of any gaps?

**If ANY checkbox is unchecked → STOP and complete it!**

---

## 🎯 EXAMPLES: Before vs After

### **Example 1: CRUD API Request**

**❌ BEFORE (Hallucination Risk):**
```
User: "Create product API"

Claude: "I'll create a Product API with these files:
- ProductController.java
- ProductService.java
- Product.java

Using standard CRUD endpoints..."
```
**Problem:** Assumed structure, didn't verify patterns, no search done!

**✅ AFTER (Anti-Hallucination):**
```
User: "Create product API"

Claude:
🧠 THINKING:
  Need to understand: Project structure, existing patterns, naming conventions
  Will search: Similar CRUD implementations, package structure, response patterns

🔍 SEARCHING:
  ✅ Found UserController.java - reading patterns...
  ✅ Pattern extracted: ApiResponseDto<T> for responses
  ✅ Pattern extracted: Form classes for validation
  ✅ Verified package structure: com.example-project.{project}.{service}

✅ VERIFICATION:
  ✅ All patterns from actual user-service code
  ✅ Response pattern confirmed in 15 endpoints
  ⚠️ Product entity fields not specified - will need user input

📄 STRUCTURED PROMPT:
  Based on verified patterns from user-service...
  [Detailed prompt with actual examples]
```

---

### **Example 2: JWT Authentication**

**❌ BEFORE (Hallucination Risk):**
```
User: "Add JWT to product service"

Claude: "I'll add JWT authentication using standard Spring Security..."
```
**Problem:** No verification of existing JWT implementation!

**✅ AFTER (Anti-Hallucination):**
```
User: "Add JWT to product service"

Claude:
🧠 THINKING:
  Check if JWT already implemented in other services
  Find existing JWT utilities, filters, configurations

🔍 SEARCHING:
  ✅ Found auth-service with JWT implementation
  ✅ Reading JwtUtil.java...
  ✅ Reading JwtAuthenticationFilter.java...
  ✅ Reading SecurityConfig.java...
  ✅ Pattern extracted: jjwt library with HS512 algorithm

✅ VERIFICATION:
  ✅ JWT secret stored in Secret Manager (verified)
  ✅ Existing filter implementation in auth-service
  ✅ Can reuse JwtUtil methods

📄 STRUCTURED PROMPT:
  Will use EXACT pattern from auth-service...
  [Detailed prompt with verified examples]
```

---

## 🔄 CONTINUOUS LEARNING

### **Feedback Loop:**
```
Execute Task
    ↓
Was information accurate? ✅/❌
    ↓
If ❌: Update search patterns
    ↓
If ✅: Reinforce successful patterns
```

### **Pattern Database Update:**
```
Successful verification
    ↓
Add pattern to verified_patterns.json
    ↓
Future searches prioritize verified patterns
```

---

## 📈 SUCCESS METRICS

### **Hallucination Reduction:**
- ✅ 0% made-up file paths
- ✅ 0% assumed patterns
- ✅ 0% invented configurations
- ✅ 100% verified examples

### **Quality Improvement:**
- ✅ Faster execution (no backtracking)
- ✅ Higher accuracy (based on actual code)
- ✅ Better consistency (using real patterns)
- ✅ User confidence (transparent process)

---

## 🚨 ENFORCEMENT

**This policy is MANDATORY and BLOCKING:**

- ❌ Cannot skip thinking phase
- ❌ Cannot skip information gathering
- ❌ Cannot skip verification
- ❌ Cannot proceed with assumptions

**Violations will cause:**
- 🔴 Answer quality degradation
- 🔴 User trust loss
- 🔴 Rework required
- 🔴 Time wasted

---

**VERSION:** 1.0.0
**CREATED:** 2026-02-16
**LOCATION:** `~/.claude/memory/anti-hallucination-enforcement.md`
**INTEGRATED WITH:** prompt-generation-policy.md (Step 0)
