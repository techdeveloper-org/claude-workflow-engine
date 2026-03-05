# Smart Code Review Flow (Visual Diagrams)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      COMMIT CREATED                             │
│              (All files modified in git)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CREATE PR ON GITHUB                          │
│            (stop-notifier.py calls github_pr_workflow)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  NEW: SMART CODE REVIEW STARTS     │
          │  (github-smart-pr-reviewer.py)     │
          └────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌─────────────┐ ┌──────────────┐ ┌─────────────┐
   │Load Session │ │Load GitHub   │ │Load Flow    │
   │ Summary     │ │  Issues      │ │ Trace       │
   └─────────────┘ └──────────────┘ └─────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  GET CHANGED FILES FROM GIT        │
          │  (git diff --name-only)            │
          │  Returns: [file1.java, file2.ts,   │
          │           file3.yml, ...]          │
          └────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  FOR EACH FILE IN CHANGED LIST     │
          └────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                                 │
    ┌─────▼──────┐               ┌────────▼────────┐
    │ file1.java │               │ file2.ts        │
    │ (4 files)  │     ...       │                 │
    └─────┬──────┘               └────────┬────────┘
          │                               │
          ▼                               ▼
    ┌──────────────────┐           ┌──────────────────┐
    │DETERMINE SKILL   │           │DETERMINE SKILL   │
    │ .java → spring   │           │ .ts → angular    │
    │ -boot            │           │ -engineer        │
    └──────────────────┘           └──────────────────┘
          │                               │
          ▼                               ▼
    ┌──────────────────┐           ┌──────────────────┐
    │LOAD SKILL        │           │LOAD SKILL        │
    │PATTERNS          │           │PATTERNS          │
    │(from            │           │(from             │
    │ skill-review-    │           │ skill-review-    │
    │patterns.py)      │           │patterns.py)      │
    └──────────────────┘           └──────────────────┘
          │                               │
          ▼                               ▼
    ┌──────────────────┐           ┌──────────────────┐
    │READ FILE CODE    │           │READ FILE CODE    │
    │ UserController   │           │auth.component    │
    │ .java            │           │.ts               │
    └──────────────────┘           └──────────────────┘
          │                               │
          ▼                               ▼
    ┌──────────────────┐           ┌──────────────────┐
    │REVIEW AGAINST    │           │REVIEW AGAINST    │
    │SKILL PATTERNS    │           │SKILL PATTERNS    │
    │✅ @Controller    │           │✅ @Component     │
    │✅ @Service       │           │✅ OnInit         │
    │✅ @Transactional │           │✅ reactive forms │
    │⚠️ Missing cache  │           │⚠️ error handling │
    └──────────────────┘           └──────────────────┘
          │                               │
          └────────────────┬──────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  COLLECT ALL FINDINGS              │
          │  {                                 │
          │    "file1.java": {                 │
          │      "skill": "spring-boot",       │
          │      "status": "pass",             │
          │      "issues": [...],              │
          │      "suggestions": [...]          │
          │    },                              │
          │    "file2.ts": {                   │
          │      "skill": "angular",           │
          │      "status": "pass_with_warnings"│
          │      ...                           │
          │    }                               │
          │  }                                 │
          └────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  BUILD REVIEW COMMENT              │
          │  (with skill context + findings)   │
          │                                    │
          │  ## 🔍 Smart Code Review          │
          │  - Session context                │
          │  - File-by-file findings          │
          │  - Skill patterns matched         │
          │  - Overall status                 │
          └────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  POST COMMENT ON PR                │
          │  (gh pr comment {PR} --body "...")│
          └────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  CHECK REVIEW STATUS               │
          │                                    │
          │  if all_passed or warnings:        │
          │    → Continue to auto-merge ✅     │
          │  else:                             │
          │    → Stop, post needs-fix msg ❌   │
          └────────────────────────────────────┘
                           │
          ┌────────────────┴───────────────────┐
          │                                    │
     ✅ SAFE TO MERGE                    ❌ STOP
          │                                    │
          ▼                                    ▼
    ┌──────────────┐            ┌──────────────────────┐
    │AUTO-MERGE PR │            │POST: "Please fix     │
    │(gh pr merge) │            │ critical issues:"    │
    │              │            │ - Issue 1            │
    │Merged! ✅    │            │ - Issue 2            │
    └──────────────┘            │                      │
                                │DO NOT MERGE         │
                                └──────────────────────┘
```

---

## Data Flow Diagram

```
SESSION CONTEXT                 GITHUB CONTEXT              GIT CONTEXT
┌──────────────────┐           ┌──────────────────┐        ┌──────────────┐
│session-summary   │           │Issues #42, #43   │        │Changed files:│
│.json             │           │                  │        │  file1.java  │
├──────────────────┤           ├──────────────────┤        │  file2.ts    │
│task: "Impl JWT"  │           │"Add JWT auth"    │        │  file3.yml   │
│complexity: 18    │           │"Validate token"  │        │  test.java   │
│tech_stack:       │           │"RefreshToken"    │        └──────────────┘
│  - spring-boot   │           └──────────────────┘               │
│  - java          │                  │                           │
│  - postgresql    │                  │                           │
│skills_used:      │                  │                           │
│  - java-spring   │                  │                           │
│    -boot         │                  │                           │
└──────────────────┘                  │                           │
         │                             │                          │
         └─────────────────────────────┼──────────────────────────┘
                                       │
                                       ▼
                         ┌──────────────────────────┐
                         │ SMART CODE REVIEWER      │
                         │ (github-smart-pr-        │
                         │  reviewer.py)            │
                         │                          │
                         │ Inputs:                  │
                         │ - Session summary        │
                         │ - GitHub issues          │
                         │ - Changed files list     │
                         │ - Flow-trace data        │
                         └──────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
            ┌───────▼────────┐  ┌─────▼───────┐  ┌──────▼──────┐
            │ SKILL MAPPING  │  │ PATTERN     │  │FINDINGS     │
            │                │  │ MATCHING    │  │             │
            │file.java       │  │             │  │✅ PASS      │
            │  → spring-boot │  │java:        │  │⚠️ WARNINGS  │
            │                │  │  @Controller│  │❌ CRITICAL  │
            │file.ts         │  │  @Service   │  │             │
            │  → angular     │  │  @Transact. │  │             │
            │                │  │             │  │             │
            │file.yml        │  │angular:     │  │             │
            │  → docker      │  │  @Component │  │             │
            │                │  │  OnInit     │  │             │
            └────────────────┘  │  reactive   │  └─────────────┘
                                │             │
                                └─────────────┘
                                       │
                                       ▼
                         ┌──────────────────────────┐
                         │  BUILD REVIEW COMMENT    │
                         │                          │
                         │ ## 🔍 Smart Code Review │
                         │ ### 📋 Context          │
                         │ - Task: Impl JWT        │
                         │ - Skills: spring-boot   │
                         │ ### 📁 Files Reviewed   │
                         │ ✅ UserController.java │
                         │ ⚠️  UserService.java    │
                         │ ✅ application.yml      │
                         │ ### 📊 Summary          │
                         │ Status: Ready to merge  │
                         └──────────────────────────┘
                                       │
                                       ▼
                         ┌──────────────────────────┐
                         │ POST ON PR + AUTO-MERGE  │
                         │ (if status OK)           │
                         └──────────────────────────┘
```

---

## File Review Process (Per File)

```
┌───────────────────────────────────────────┐
│    REVIEW SINGLE FILE: UserController.java│
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│ STEP 1: DETERMINE SKILL                   │
│                                           │
│ Input: "UserController.java"              │
│ - Extension: .java ✅                     │
│ - Context from session: spring-boot ✅    │
│ - Flow-trace skill: java-spring-boot ✅   │
│                                           │
│ Result: java-spring-boot-microservices    │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│ STEP 2: LOAD SKILL PATTERNS               │
│                                           │
│ From skill-review-patterns.py:            │
│ Required patterns:                        │
│   - @SpringBootApplication                │
│   - @RestController                       │
│   - @RequestMapping                       │
│   - Dependency injection (@Autowired)     │
│   - Error handling                        │
│                                           │
│ Optional patterns:                        │
│   - @Cacheable for performance            │
│   - @Validated for input validation       │
│   - OpenAPI @Operation annotations        │
│                                           │
│ Anti-patterns (avoid):                    │
│   - Direct database access in controller  │
│   - Throwing RuntimeException             │
│   - Logic in controller (should be svc)   │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│ STEP 3: READ FILE CODE                    │
│                                           │
│ @RestController                           │
│ @RequestMapping("/api/users")             │
│ public class UserController {             │
│     @Autowired                            │
│     private UserService userService;      │
│                                           │
│     @PostMapping("/login")                │
│     public ResponseEntity<?> login(       │
│         @RequestBody LoginRequest req) {  │
│         try {                             │
│             User user = userService      │
│                 .authenticate(req);       │
│             String token = userService   │
│                 .generateToken(user);     │
│             return ResponseEntity        │
│                 .ok(new LoginResponse(   │
│                     token));              │
│         } catch (AuthException e) {       │
│             return ResponseEntity        │
│                 .status(401)              │
│                 .body(error);             │
│         }                                 │
│     }                                     │
│ }                                         │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│ STEP 4: VERIFY PATTERNS (Checklist)       │
│                                           │
│ ✅ Has @RestController                   │
│    Found: "@RestController"               │
│                                           │
│ ✅ Has @RequestMapping                   │
│    Found: "@RequestMapping("/api/users")"│
│                                           │
│ ✅ Uses @Autowired for DI                │
│    Found: "@Autowired UserService"       │
│                                           │
│ ✅ Returns ResponseEntity                │
│    Found: "ResponseEntity.ok(...)"        │
│                                           │
│ ✅ Error handling present                │
│    Found: "catch (AuthException e)"      │
│    Found: ".status(401)"                  │
│                                           │
│ ⚠️  Optional: @Validated missing         │
│    (not required, but suggested)          │
│                                           │
│ ✅ No direct DB access                   │
│    Uses UserService (good!)               │
│                                           │
│ ✅ No anti-patterns found                │
│    OK: Uses service layer properly        │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│ STEP 5: GENERATE FINDINGS                 │
│                                           │
│ {                                         │
│   "file": "UserController.java",          │
│   "skill": "java-spring-boot",            │
│   "status": "PASS",                       │
│   "compliance": "5/5 patterns verified",  │
│   "issues": [],                           │
│   "suggestions": [                        │
│     "Consider @Validated for DTO         │
│      validation",                         │
│     "@ExceptionHandler for global        │
│      error handling"                      │
│   ]                                       │
│ }                                         │
└───────────┬───────────────────────────────┘
            │
            ▼
   ┌────────────────────┐
   │ ADD TO FINDINGS    │
   │ COLLECTION         │
   └────────────────────┘
```

---

## Review Comment Example

```
┌──────────────────────────────────────────────────────┐
│      PR #15: Implement JWT Auth for REST API         │
└──────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════╗
║   🔍 Smart Code Review (Session-Aware Context)      ║
╚══════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────┐
│ 📋 REVIEW CONTEXT                                   │
├──────────────────────────────────────────────────────┤
│ Session: SESSION-20260305-115804-VJ0S              │
│ Task: Implement Spring Boot REST API with JWT auth │
│ Complexity: 18/25 (Moderate)                        │
│ Tech Stack: spring-boot, java, postgresql, docker  │
│ Skills Used: java-spring-boot-microservices        │
│                                                     │
│ Requirements (GitHub Issues):                       │
│ ✅ Issue #42: Implement JWT authentication         │
│ ✅ Issue #43: Add refresh token support            │
│ ✅ Issue #44: Validate token expiry               │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 📁 FILES REVIEWED: 4                                │
├──────────────────────────────────────────────────────┤
│
│ ✅ PASS: UserController.java
│ Skill Context: java-spring-boot-microservices
│ ├─ ✅ Proper @RestController annotation
│ ├─ ✅ @RequestMapping correctly configured
│ ├─ ✅ Uses dependency injection for UserService
│ ├─ ✅ Returns ResponseEntity with proper status
│ └─ ✅ Error handling with @ExceptionHandler
│ Compliance: 100% (5/5 patterns verified)
│
│ ⚠️  PASS with SUGGESTIONS: UserService.java
│ Skill Context: java-spring-boot-microservices
│ ├─ ✅ Service layer properly isolated
│ ├─ ✅ @Transactional on write operations
│ ├─ ✅ Exception handling present
│ ├─ ⚠️  Consider @Cacheable for token validation
│ └─ ⚠️  Suggestion: Add @Validated for input DTOs
│ Compliance: 100% (core patterns, optional improvements)
│
│ ✅ PASS: application.yml
│ Skill Context: java-spring-boot-microservices
│ ├─ ✅ JWT secret configured correctly
│ ├─ ✅ Token expiry properly set
│ ├─ ✅ Database connection pooling configured
│ └─ ✅ Logging levels appropriate
│ Compliance: 100% (4/4 config checks)
│
│ ✅ PASS: UserControllerTest.java
│ Skill Context: java-spring-boot-microservices
│ ├─ ✅ Uses @SpringBootTest for integration testing
│ ├─ ✅ MockMvc properly configured
│ ├─ ✅ JWT token mocking in place
│ ├─ ✅ Test coverage for auth endpoints
│ └─ ✅ Both success and failure cases tested
│ Compliance: 100% (5/5 test patterns verified)
│
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 📊 SUMMARY                                          │
├──────────────────────────────────────────────────────┤
│ Total Files: 4                                      │
│ Critical Issues: 0 ✅                               │
│ Warnings: 1 (non-blocking) ⚠️                       │
│ Pattern Compliance: 100% ✅                         │
│ Requirements Met: 100% ✅                           │
│                                                     │
│ AUTO-MERGE STATUS: ✅ APPROVED                     │
│ Ready to merge immediately!                        │
└──────────────────────────────────────────────────────┘

_Auto-generated by Smart PR Reviewer v3.0_
_Timestamp: 2026-03-05 11:45:23 UTC_
```

---

## Decision Tree: Auto-Merge or Not?

```
                    REVIEW COMPLETE
                           │
                           ▼
            ┌──────────────────────────┐
            │ CHECK: Critical Issues?  │
            └──────────┬───────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
        YES                        NO
          │                         │
          ▼                         ▼
    ┌─────────────────┐    ┌────────────────┐
    │ ❌ DO NOT MERGE │    │ Any warnings?  │
    │                 │    └────────────────┘
    │ Post comment:   │           │
    │ "Critical       │    ┌──────┴──────┐
    │  issues found   │    │             │
    │  - Issue 1      │   YES           NO
    │  - Issue 2      │    │             │
    │                 │    ▼             ▼
    │ Please fix and  │ ┌──────────┐  ┌─────────┐
    │ request review  │ │⚠️ MERGE │ │✅ MERGE │
    │ again"          │ │WITH NOTE│ │APPROVED │
    │                 │ │         │ │         │
    └─────────────────┘ │"Warnings│ │Auto-    │
                        │found:   │ │merge in │
                        │- Item 1 │ │progress │
                        │- Item 2 │ │         │
                        │         │ └─────────┘
                        │Still OK │
                        │to merge"│
                        └─────────┘
```

---

**This flow ensures QUALITY + AUTOMATION + CONTEXT-AWARENESS! 🚀**

