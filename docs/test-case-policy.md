# Test Case Policy (ALWAYS ACTIVE)

## System-Level Requirement

This is a **permanent rule** that defines mandatory vs optional testing approaches.

---

## Testing Categories

### 1. Mandatory Testing (ALWAYS DO)

**Development Testing**
- Code must compile/run without errors
- Basic functionality must work
- No syntax errors, no crashes

**Manual Testing**
- Test the implemented feature manually
- Verify expected behavior works
- Check edge cases if obvious

**Status**: MANDATORY - Cannot skip

---

### 2. Optional Testing (ASK USER)

**Unit Tests**
- Individual function/component tests
- Test cases for each method
- Mock dependencies

**Integration Tests**
- Test multiple components together
- API endpoint tests
- Database integration tests

**E2E Tests**
- Full user flow tests
- Browser automation tests
- End-to-end scenarios

**Status**: OPTIONAL - Always ask user preference

---

## When to Ask About Optional Tests

### Triggers for Asking

Ask user about test cases when ANY of these conditions are met:

1. **Phase/Task Completion**
   - Phase wrapping up
   - Feature implementation done
   - Before final commit

2. **New Feature Added**
   - REST API endpoints created
   - New components/services built
   - Business logic implemented

3. **During Planning**
   - In planning mode
   - Breaking down large tasks
   - Designing implementation approach

### How to Ask

Use `AskUserQuestion` tool with this format:

```
Question: "Unit/Integration tests likhein ya skip karein?"
Header: "Test Cases"
Options:
1. "Write all tests now" - Unit + Integration tests complete karo
2. "Skip for now, add later" (Recommended) - Focus on development, tests baad mein
3. "Only critical tests" - Sirf important test cases likho
```

**Default Recommendation**: Option 2 (Skip for now) - Because:
- Development aur manual testing enough for initial work
- Tests can be added incrementally later
- Saves significant time (30-50% faster delivery)
- User can request tests anytime: "ab tests likh do"

---

## Test Phase Execution

### If User Chooses: "Write all tests now"

```
Phase N: Implementation ✅
  ↓
Phase N+1: Test Cases
├─ Unit tests
├─ Integration tests
└─ E2E tests (if applicable)
  ↓
Auto-commit + push ✅
```

### If User Chooses: "Skip for now"

```
Phase N: Implementation ✅
  ↓
Auto-commit + push ✅
  ↓
(Tests skipped - can add later)
```

User can request later:
```
User: "Ab tests likh do for authentication"
Claude: Creates test phase + implements tests
```

### If User Chooses: "Only critical tests"

```
Phase N: Implementation ✅
  ↓
Mini Test Phase:
- Critical path unit tests (5-10 tests)
- Main integration test (1-2 tests)
  ↓
Auto-commit + push ✅
```

---

## Integration with Phased Execution

### Large Task Breakdown

**Before Policy:**
```
Phase 1: Backend API
Phase 2: Frontend UI
Phase 3: Unit Tests     ← Time consuming
Phase 4: Integration Tests  ← Time consuming
Phase 5: E2E Tests      ← Time consuming
```

**After Policy (User chooses skip):**
```
Phase 1: Backend API
Phase 2: Frontend UI
(Tests skipped - 40-50% time saved!)

User can request tests anytime later.
```

**After Policy (User chooses critical only):**
```
Phase 1: Backend API + Critical Tests
Phase 2: Frontend UI + Critical Tests
(30% time saved vs full test suite!)
```

---

## Test Coverage Guidelines

### When Tests ARE Recommended

Strong recommendation to write tests (but still ask):

1. **Critical Business Logic**
   - Payment processing
   - Authentication/Authorization
   - Data validation/sanitization

2. **Complex Algorithms**
   - Custom calculations
   - Data transformations
   - Edge case handling

3. **Public APIs**
   - External-facing endpoints
   - Third-party integrations
   - SDK/library code

### When Tests Can Be Skipped

Safe to skip (user preference):

1. **Prototypes/POCs**
2. **Internal tools**
3. **Simple CRUD operations**
4. **UI components** (manual testing sufficient)
5. **Configuration files**
6. **Experimental features**

---

## Example Conversations

### Example 1: API Development

```
User: "Build user authentication API"

Claude: [Plans phases]
Phase 1: Auth endpoints + JWT setup
Phase 2: Database integration

[Before execution, asks:]
"Unit/Integration tests likhein ya skip karein?

1. Write all tests now (Full test coverage)
2. Skip for now, add later (Recommended - Focus on dev)
3. Only critical tests (Auth validation tests only)"

User: "Skip for now"
Claude: [Executes Phase 1 & 2, skips test phase]
```

### Example 2: During Planning

```
User: "Build complete e-commerce system"

Claude: [Enters planning mode]
"Large task detected. Breaking into phases:

Phase 1: Product catalog API
Phase 2: Shopping cart backend
Phase 3: Frontend UI
Phase 4: Tests (Optional - your choice)

Unit/Integration tests likhein ya skip karein?
[Options...]"

User: "Only critical tests"
Claude: [Plans critical tests per phase, skips exhaustive testing]
```

### Example 3: User Requests Tests Later

```
[After implementation complete]

User: "Ab authentication ke tests likh do"

Claude: "Starting test implementation...

Creating test suite:
- Unit tests for auth functions
- Integration tests for API endpoints
- Mock data setup

[Implements tests]
✅ Tests complete + committed"
```

---

## Time Savings Analysis

### Typical Feature Implementation

**With Full Tests (Traditional):**
- Development: 40% time
- Manual testing: 10% time
- Unit tests: 20% time
- Integration tests: 20% time
- E2E tests: 10% time
Total: 100% time

**With Policy (Skip tests):**
- Development: 80% time
- Manual testing: 20% time
- Tests: Deferred
Total: 50% faster delivery!

**With Policy (Critical only):**
- Development: 70% time
- Manual testing: 15% time
- Critical tests: 15% time
Total: 30% faster delivery!

---

## Priority

**SYSTEM-LEVEL**: This policy activates during:
1. Planning phase (when breaking down tasks)
2. Phase completion (before final commit)
3. Feature implementation (after core work done)

Runs AFTER:
- context-management-core
- model-selection-core
- task-planning-intelligence
- phased-execution-intelligence

Runs BEFORE:
- git-auto-commit-policy (ask before committing with tests)

---

## Safety Guarantees

Even when tests are skipped:

1. **Code Quality**: Still write clean, testable code
2. **Manual Verification**: Always test manually
3. **Documentation**: Document expected behavior
4. **Incremental Addition**: Tests can be added anytime later
5. **No Technical Debt**: User makes informed choice

---

## Exception Cases

**Force Tests (Don't Ask) When:**
- User explicitly says "with tests" in initial request
- Critical security feature (auth, payments, etc.) AND user hasn't said to skip
- Production deployment imminent AND no tests exist

**Never Ask When:**
- User already said "no tests" for this session
- Tiny changes (1-2 line fixes)
- Configuration-only changes
- Documentation updates

---

## Status

**ACTIVE**: This policy is permanent and applies to all sessions.
**Version**: 1.0.0
**Last Updated**: 2026-01-23 (Initial creation - Optional test cases with user preference)

---

## Quick Reference

```
Development → ✅ Mandatory
Manual Testing → ✅ Mandatory
Unit Tests → ❓ Ask user (recommend skip)
Integration Tests → ❓ Ask user (recommend skip)
E2E Tests → ❓ Ask user (recommend skip)
```

**Default stance**: Skip tests initially, add incrementally when needed.
**User flexibility**: Can request tests anytime: "ab tests likh do"
**Time savings**: 30-50% faster delivery without sacrificing quality
