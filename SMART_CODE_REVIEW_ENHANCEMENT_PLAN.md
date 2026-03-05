# Smart Code Review Enhancement Plan (GitHub Branch + PR Policy v3.0)

**Document:** Enhancement Design
**Date:** 2026-03-05
**Status:** Ready for Implementation
**Depends On:** github-branch-pr-policy.md, session-summary-generator.py, flow-trace.json

---

## Overview

**Current Behavior (v2.0):**
```
Commit → Create PR → Post generic review comment → Auto-merge ❌
```

**New Behavior (v3.0):**
```
Commit → Create PR → Smart Code Review (Session-Aware + Skill-Aware) → Post Detailed Findings → Auto-merge ✅

Smart Review Process:
1. Load session summary (what was accomplished)
2. Load GitHub issues (requirements/context)
3. Load flow-trace.json (which skills/agents used)
4. Get list of files changed in commit
5. For EACH file:
   a) Determine correct skill/agent from file extension + context
   b) Load skill's best practices
   c) Read the file
   d) Review file against:
      - Skill's patterns (e.g., Spring Boot annotations)
      - Session context (what was supposed to be done)
      - Requirements from issues
      - Tech stack used
   e) Generate findings (✅ passed / ⚠️ warnings / ❌ issues)
6. Post comprehensive review comment on PR
7. Only then auto-merge
```

---

## Data Sources & Mapping

### **Source 1: Session Summary**
**File:** `~/.claude/memory/logs/sessions/{SESSION_ID}/session-summary.json`

```json
{
  "session_id": "SESSION-20260305-115804-VJ0S",
  "duration_minutes": 15,
  "task_description": "Implement Spring Boot REST API with JWT auth",
  "task_type": "API",
  "complexity": 18,
  "tech_stack": ["spring-boot", "java", "postgresql", "docker"],
  "skills_used": ["java-spring-boot-microservices"],
  "agents_used": ["spring-boot-microservices"],
  "files_modified": [
    "src/main/java/com/example/UserController.java",
    "src/main/java/com/example/UserService.java",
    "src/main/resources/application.yml",
    "src/test/java/com/example/UserControllerTest.java"
  ],
  "commits": ["fix: Implement JWT authentication"],
  "github_issues": [42, 43],
  "status": "completed"
}
```

### **Source 2: GitHub Issues**
**From:** `gh issue view {ISSUE_ID} --json title,body,labels`

```json
{
  "number": 42,
  "title": "Implement JWT authentication for REST API",
  "body": "Add JWT token-based auth to /user endpoints\n- Support refresh tokens\n- Validate expiry\n- Return 401 on invalid",
  "labels": ["feature", "security", "priority-high"]
}
```

### **Source 3: Flow-Trace Data**
**File:** `~/.claude/memory/logs/sessions/{SESSION_ID}/flow-trace.json`

```json
{
  "session_id": "SESSION-20260305-115804-VJ0S",
  "skill": "java-spring-boot-microservices",
  "agent": "spring-boot-microservices",
  "tech_stack": ["spring-boot", "java", "postgresql", "docker"],
  "supplementary_skills": ["rdbms-core", "docker"],
  "steps": [
    {
      "step": "Step 3.1 - Task Breakdown",
      "tech_stack": ["spring-boot", "java", "postgresql", "docker"],
      "complexity": 18
    },
    {
      "step": "Step 3.5 - Skill Selection",
      "selected_skill": "java-spring-boot-microservices",
      "selected_agent": "spring-boot-microservices",
      "supplementary": ["rdbms-core", "docker"]
    }
  ]
}
```

### **Source 4: Git Changed Files**
**From:** `git diff --name-only main...current-branch`

```
src/main/java/com/example/UserController.java
src/main/java/com/example/UserService.java
src/main/resources/application.yml
src/test/java/com/example/UserControllerTest.java
```

---

## File-to-Skill Mapping

### **Mapping Table (File Extension → Skill/Agent)**

```python
FILE_TO_SKILL_MAP = {
    # Java Spring Boot
    '.java': {
        'skill': 'java-spring-boot-microservices',
        'context_keywords': ['spring', '@', 'controller', 'service', 'entity', 'repository'],
        'patterns': ['@SpringBootApplication', '@RestController', '@Service', '@Repository']
    },

    # Frontend - Angular/TypeScript
    '.ts': {
        'skill': 'angular-engineer',
        'context_keywords': ['angular', 'component', 'service', 'module', 'rxjs'],
        'patterns': ['@Component', '@Injectable', '@NgModule', 'Observable']
    },
    '.html': {
        'skill': 'ui-ux-designer',
        'context_keywords': ['template', 'form', 'button', 'layout'],
        'patterns': ['*ngIf', '*ngFor', '(click)', '[ngClass]']
    },
    '.scss': {
        'skill': 'css-core',
        'context_keywords': ['style', 'theme', 'color', 'responsive'],
        'patterns': ['$', '@mixin', '@include', 'flex']
    },

    # Python Backend
    '.py': {
        'skill': 'python-backend-engineer',
        'context_keywords': ['flask', 'django', 'fastapi', 'decorator', 'async'],
        'patterns': ['@app.route', '@app.get', '@asyncio', 'def ']
    },

    # Database
    '.sql': {
        'skill': 'rdbms-core',
        'context_keywords': ['select', 'insert', 'create table', 'index'],
        'patterns': ['SELECT', 'INSERT', 'CREATE TABLE']
    },

    # DevOps
    'Dockerfile': {
        'skill': 'docker',
        'context_keywords': ['docker', 'image', 'container'],
        'patterns': ['FROM', 'RUN', 'COPY', 'EXPOSE']
    },
    '.yaml': {
        'skill': 'docker',  # or kubernetes depending on context
        'context_keywords': ['kubernetes', 'service', 'deployment', 'pod'],
        'patterns': ['apiVersion', 'kind', 'metadata', 'spec']
    },

    # Config
    'pom.xml': {
        'skill': 'java-spring-boot-microservices',
        'context_keywords': ['dependency', 'maven', 'plugin'],
        'patterns': ['<dependency>', '<plugin>']
    },
    'package.json': {
        'skill': 'angular-engineer',
        'context_keywords': ['npm', 'typescript', 'angular'],
        'patterns': ['dependencies', 'devDependencies']
    },

    # Tests
    '*Test.java': {
        'skill': 'java-spring-boot-microservices',
        'context_keywords': ['test', 'junit', 'mock', 'assert'],
        'patterns': ['@Test', '@MockBean', 'assertEquals', 'verify']
    },
    '*.test.ts': {
        'skill': 'angular-engineer',
        'context_keywords': ['test', 'jasmine', 'karma', 'spy'],
        'patterns': ['describe', 'it(', 'expect', 'spyOn']
    },
}
```

---

## Review Engine Architecture

### **New Script: `github-smart-pr-reviewer.py`**

```python
class SmartPRReviewer:
    """
    Reviews PR files with skill-aware context before auto-merge.

    Flow:
    1. Load session context (summary + issues + flow-trace)
    2. Get changed files from git
    3. For each file:
       a) Determine correct skill/agent
       b) Review against skill's patterns
       c) Collect findings
    4. Post comprehensive review comment
    5. Return review status (all_passed, warnings_found, critical_issues)
    """

    def __init__(self, session_id, pr_number):
        self.session_id = session_id
        self.pr_number = pr_number
        self.session_summary = None
        self.github_issues = []
        self.flow_trace = None
        self.changed_files = []
        self.findings = {}

    def execute_smart_review(self):
        """Main entry point for smart code review"""
        # Step 1: Load context
        self.load_session_context()

        # Step 2: Get files changed
        self.get_changed_files()

        # Step 3: Review each file
        for file_path in self.changed_files:
            self.review_file(file_path)

        # Step 4: Post findings
        self.post_review_comment()

        # Step 5: Return status
        return self.get_review_status()

    def load_session_context(self):
        """Load session summary, issues, flow-trace"""
        # Load from ~/.claude/memory/logs/sessions/{SESSION_ID}/
        self.session_summary = self._load_json('session-summary.json')
        self.flow_trace = self._load_json('flow-trace.json')
        self.github_issues = self._fetch_github_issues()

    def get_changed_files(self):
        """Get list of files changed in current commit"""
        # Run: git diff --name-only main...HEAD
        self.changed_files = self._run_git_diff()

    def review_file(self, file_path):
        """Review single file with skill context"""
        # Determine skill/agent for this file
        skill = self.determine_skill(file_path)

        # Read file content
        content = self._read_file(file_path)

        # Review against skill patterns
        findings = self._review_against_skill(file_path, content, skill)

        # Store findings
        self.findings[file_path] = {
            'skill': skill,
            'status': findings['status'],  # 'pass', 'warning', 'fail'
            'issues': findings['issues'],
            'suggestions': findings['suggestions']
        }

    def determine_skill(self, file_path):
        """Determine correct skill from file extension + context"""
        # Match file extension from FILE_TO_SKILL_MAP
        # If Java + flow_trace says 'java-spring-boot-microservices' -> use that
        # If Python + session has 'python-backend-engineer' -> use that
        pass

    def _review_against_skill(self, file_path, content, skill):
        """Review file against skill's best practices"""
        # For java-spring-boot-microservices:
        #   - Check for @SpringBootApplication
        #   - Check for service layer
        #   - Check for @Transactional on writes
        #   - Check for proper error handling
        #
        # For angular-engineer:
        #   - Check for component structure
        #   - Check for dependency injection
        #   - Check for observable handling
        #   - Check for change detection
        #
        # For python-backend-engineer:
        #   - Check for proper async/await
        #   - Check for request validation
        #   - Check for error handling
        pass

    def post_review_comment(self):
        """Post comprehensive review on PR"""
        # Build review comment with:
        # - Session context (what was supposed to be done)
        # - Files reviewed (with status icons)
        # - Issues found (per skill pattern)
        # - Suggestions (best practices)
        # - Overall status (ready-to-merge / needs-fix)

        # Post via: gh pr comment {PR} --body "..."
        pass

    def get_review_status(self):
        """Determine if safe to auto-merge"""
        # all_passed: No critical issues, safe to merge
        # warnings: Some warnings, but can merge (with note)
        # critical_issues: Fix required before merge
        pass
```

---

## Review Comment Template

### **Example Review Comment (Posted on PR)**

```markdown
## 🔍 Smart Code Review (Session-Aware + Skill-Aware)

### 📋 Review Context
**Session:** SESSION-20260305-115804-VJ0S
**Task:** Implement Spring Boot REST API with JWT auth (Complexity: 18/25)
**Tech Stack:** spring-boot, java, postgresql, docker
**Skills Used:** java-spring-boot-microservices

**Requirements (from GitHub Issues):**
- [x] Issue #42: Implement JWT authentication for REST API
- [x] Issue #43: Add refresh token support
- [x] Issue #44: Validate token expiry

---

### 📁 Files Reviewed: 4

#### ✅ `src/main/java/com/example/UserController.java`
**Skill Context:** java-spring-boot-microservices
**Status:** PASS ✅

**Findings:**
- ✅ Proper @RestController annotation
- ✅ @RequestMapping correctly configured
- ✅ Uses dependency injection for UserService
- ✅ Returns proper HTTP status codes
- ✅ JWT auth header validation present

**Compliance:** 100% (5/5 Spring Boot patterns verified)

---

#### ⚠️ `src/main/java/com/example/UserService.java`
**Skill Context:** java-spring-boot-microservices
**Status:** PASS with SUGGESTIONS ⚠️

**Findings:**
- ✅ Service layer properly isolated
- ✅ @Transactional on write operations
- ✅ Exception handling present
- ⚠️ Consider adding @Cacheable for token validation
- ⚠️ Suggestion: Use @Validated for input DTOs

**Compliance:** 100% (pattern match, but missing optional optimizations)

---

#### ✅ `src/main/resources/application.yml`
**Skill Context:** java-spring-boot-microservices
**Status:** PASS ✅

**Findings:**
- ✅ JWT secret configured
- ✅ Token expiry properly set
- ✅ Database connection pooling configured
- ✅ Logging levels appropriate

**Compliance:** 100% (4/4 config checks passed)

---

#### ✅ `src/test/java/com/example/UserControllerTest.java`
**Skill Context:** java-spring-boot-microservices
**Status:** PASS ✅

**Findings:**
- ✅ Uses @SpringBootTest
- ✅ MockMvc properly configured
- ✅ JWT token mocking in place
- ✅ Test coverage for auth endpoints
- ✅ Both success and failure cases tested

**Compliance:** 100% (5/5 test patterns verified)

---

### 📊 Overall Review Summary

| Metric | Result |
|--------|--------|
| **Files Reviewed** | 4/4 ✅ |
| **Critical Issues** | 0 ✅ |
| **Warnings** | 1 (non-blocking) |
| **Compliance** | 100% ✅ |
| **Auto-Merge Status** | APPROVED ✅ |

---

### ✅ Ready to Auto-Merge
All files comply with session requirements and skill patterns. Merging now...

_Review auto-generated by Claude Memory System (Smart PR Reviewer v3.0)_
```

---

## Implementation Steps

### **Step 1: Create `github-smart-pr-reviewer.py`**
New file: `scripts/architecture/03-execution-system/09-git-commit/github-smart-pr-reviewer.py`

Functions:
- `load_session_context()` - Load summary + issues + flow-trace
- `get_changed_files()` - Git diff
- `determine_skill()` - File → Skill mapping
- `review_file()` - Single file review
- `_review_against_skill()` - Apply skill patterns
- `post_review_comment()` - Post findings on PR
- `get_review_status()` - Determine auto-merge safety

### **Step 2: Create Skill Review Templates**
New file: `scripts/architecture/03-execution-system/09-git-commit/skill-review-patterns.py`

Contains:
```python
SKILL_PATTERNS = {
    'java-spring-boot-microservices': {
        'required_patterns': [...],
        'optional_patterns': [...],
        'anti_patterns': [...],
        'file_types': ['.java'],
        'checks': [...]
    },
    'angular-engineer': {
        'required_patterns': [...],
        # ...
    },
    # ... 20+ skills
}
```

### **Step 3: Update `github-branch-pr-policy.py`**
Modify the PR merge flow:

**Before:**
```python
create_pr() → post_review_comment() → merge_pr()
```

**After:**
```python
create_pr() → smart_code_review() → post_detailed_findings() → merge_pr()
```

Add function:
```python
def smart_code_review(pr_number):
    """Execute smart PR review before merge"""
    reviewer = SmartPRReviewer(session_id, pr_number)
    status = reviewer.execute_smart_review()

    if status in ['all_passed', 'warnings']:
        return True  # Safe to merge
    else:
        return False  # Don't merge, needs fixes
```

### **Step 4: Update Policy Documentation**
File: `policies/03-execution-system/github-branch-pr-policy.md`

Add section: **"Step 3: Smart Code Review"**
- Explain session-aware review
- Explain skill-aware review
- Show example review comment
- Document review status codes

---

## Review Status Codes

```
✅ PASS (all_passed)
   - All files pass skill pattern checks
   - No warnings found
   - Safe to auto-merge

⚠️ PASS with WARNINGS (warnings)
   - Files pass, but suggestions found
   - Non-blocking issues
   - Can auto-merge with note

❌ NEEDS FIX (critical_issues)
   - Critical pattern violations found
   - DO NOT auto-merge
   - Post comment asking for fixes
```

---

## Context-Aware Review Features

### **1. Task Context**
From session summary:
- What task was being done?
- What was the complexity?
- What tech stack?
- What requirements (GitHub issues)?

### **2. Skill Context**
From flow-trace:
- Which skill was used?
- Which agent was used?
- What patterns should be followed?
- What are the best practices?

### **3. File Context**
From git:
- Which files changed?
- What type of files? (.java, .ts, .py, etc.)
- Which skill should handle them?

### **4. Review Depth**
Based on complexity + skill:
- **Simple tasks:** Quick pattern matching
- **Complex tasks:** Deep review with suggestions
- **Security-sensitive:** Extra checks for auth/crypto

---

## Benefits of Smart Code Review

| Benefit | Impact |
|---------|--------|
| **Context-Aware** | Review respects what was supposed to be done |
| **Skill-Aware** | Review respects best practices for each tech |
| **Automated** | No human review needed before merge |
| **Transparent** | Every finding explained with reasoning |
| **Educational** | Helps understand skill patterns |
| **Safe** | Won't merge if critical issues found |

---

## Example Scenarios

### **Scenario 1: Spring Boot Controller (✅ PASS)**
```
File: UserController.java
Skill: java-spring-boot-microservices
Context: "Implement JWT auth"

Checks:
✅ Has @RestController
✅ Has @RequestMapping
✅ Uses @Autowired for services
✅ Returns ResponseEntity
✅ Has @ExceptionHandler

Result: PASS - Ready to merge
```

### **Scenario 2: Angular Component (⚠️ PASS with WARNINGS)**
```
File: auth.component.ts
Skill: angular-engineer
Context: "Add login form"

Checks:
✅ Has @Component
✅ Implements OnInit
✅ Uses reactive forms
⚠️ Consider using ChangeDetectionStrategy.OnPush
⚠️ Suggestion: Add error handling for observable

Result: PASS with WARNINGS - Can merge, but suggestions noted
```

### **Scenario 3: Python Function (❌ NEEDS FIX)**
```
File: auth_service.py
Skill: python-backend-engineer
Context: "Implement JWT validation"

Checks:
✅ Has function definition
✅ Has error handling
❌ Missing input validation (DTO)
❌ No async/await for crypto operations
❌ Missing docstring

Result: CRITICAL ISSUES - Do NOT merge. Post comment requesting fixes.
```

---

## Testing Plan

### **Test Case 1: Java Spring Boot File Review**
```
Input: UserController.java (Spring Boot file)
Expected: Detects java-spring-boot-microservices skill
          Reviews against Spring patterns
          Posts findings with Spring-specific checks
```

### **Test Case 2: Angular TypeScript File Review**
```
Input: auth.component.ts (Angular file)
Expected: Detects angular-engineer skill
          Reviews against Angular patterns
          Posts findings with Angular-specific checks
```

### **Test Case 3: Mixed Tech Review**
```
Input: 4 files (Java + TS + YAML + SQL)
Expected: Each file reviewed with correct skill
          Comprehensive PR comment with all findings
          Status determines auto-merge decision
```

---

## Future Enhancements

1. **ML-Based Pattern Detection** - Learn patterns from past PRs
2. **Performance Analysis** - Check for N+1 queries, memory leaks
3. **Security Analysis** - Check for OWASP top 10 vulnerabilities
4. **Complexity Analysis** - Functions too long? Methods too complex?
5. **Coverage Analysis** - Test coverage per file
6. **Breaking Changes Detection** - Warn about API changes

---

**Status:** Ready to implement
**Estimated Effort:** 2-3 days
**Complexity:** HIGH (requires deep skill knowledge)
**Impact:** HIGH (automated quality gates)

