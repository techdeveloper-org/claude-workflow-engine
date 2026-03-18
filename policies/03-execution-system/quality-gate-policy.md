# Quality Gate Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines the 4-gate merge enforcement system that validates code quality before
PR approval in Step 11. All gates must pass (or be explicitly waived) before
the pipeline marks a PR as safe to merge.

---

## Gate Framework

```
[Changed Files]
       |
       v
[Gate 1: SonarQube Scan] --> code smells, bugs, vulnerabilities
       |
       v
[Gate 2: Coverage Check] --> test coverage threshold
       |
       v
[Gate 3: Breaking Change Detection] --> CallGraph diff analysis
       |
       v
[Gate 4: Test Suite] --> all tests pass
       |
       v
[Quality Score: 0.0 - 1.0] --> safe_to_merge decision
```

---

## Gate 1: SonarQube Scan

### Primary Mode: SonarQube API

- Connect to SonarQube server (if configured)
- Run analysis on changed files only
- Check for: bugs, vulnerabilities, code smells, security hotspots

### Fallback Mode: Lightweight Scanner

- If SonarQube not available, use built-in lightweight scanner
- Checks: complexity, duplication, common anti-patterns
- Lower accuracy but always available

### Thresholds

| Metric | Threshold | Severity |
|--------|-----------|----------|
| Bugs | 0 (new) | BLOCKER |
| Vulnerabilities | 0 (new) | BLOCKER |
| Code smells | < 5 (new) | WARNING |
| Duplication | < 3% (new code) | WARNING |
| Complexity | < 15 per method | WARNING |

---

## Gate 2: Coverage Check

### Analysis: `coverage_analyzer.py`

- AST-based coverage analysis (not runtime)
- Identifies untested methods by checking for corresponding test functions
- Risk-prioritizes: public methods > private methods > utilities

### Thresholds

| Project Type | Min Coverage | Target Coverage |
|-------------|--------------|-----------------|
| New project | 60% | 80% |
| Existing project | No regression | Current + 5% |
| Critical path | 80% | 95% |
| Utility code | 40% | 60% |

### Risk-Prioritized Gaps

Report untested methods ordered by risk:
1. Public API methods (highest risk)
2. Methods with many callers (CallGraph data)
3. Methods with complex logic (cyclomatic complexity > 10)
4. Recently modified methods

---

## Gate 3: Breaking Change Detection

### Analysis: `call_graph_analyzer.py`

Uses CallGraph diff (pre-change vs. post-change) from Step 10/11:

| Detection | Action |
|-----------|--------|
| Removed method with callers | BLOCK merge |
| Changed method signature | BLOCK merge (unless callers updated) |
| Orphaned methods (new dead code) | WARNING |
| New circular dependencies | BLOCK merge |
| Renamed without migration | WARNING |

---

## Gate 4: Test Suite

### Validation

- Run project test suite (`pytest`, `mvn test`, `npm test` based on project type)
- All existing tests must pass
- New tests for changed code must exist (from Gate 2)

### Thresholds

| Metric | Threshold |
|--------|-----------|
| Test pass rate | 100% |
| New test requirement | At least 1 test per new public method |
| Flaky test tolerance | 0 (no flaky tests accepted) |

---

## Quality Score Calculation

```
score = (gate1_score * 0.25) + (gate2_score * 0.25) + (gate3_score * 0.30) + (gate4_score * 0.20)

gate_score = 1.0 (pass) | 0.5 (warnings only) | 0.0 (failures)
```

### Decision Matrix

| Score Range | Decision | Action |
|-------------|----------|--------|
| 0.85 - 1.00 | SAFE | Auto-approve merge |
| 0.60 - 0.84 | CAUTION | Merge with warnings, flag for review |
| 0.00 - 0.59 | RISKY | Block merge, require fixes |

---

## Retry Logic

If quality gate fails:
1. Step 11 retries up to **3 times**
2. Each retry can trigger test generation for uncovered methods
3. After 3 failures, mark as RISKY and require manual review

---

## State Fields

| Field | Type | Purpose |
|-------|------|---------|
| `step11_criteria_result` | dict | Per-gate pass/fail details |
| `step11_criteria_score` | float | Overall quality score (0.0-1.0) |
| `step11_review_passed` | bool | Final pass/fail decision |
| `step11_risk_assessment` | str | "safe", "caution", "risky" |

---

## Implementation

- **Orchestrator:** `scripts/langgraph_engine/quality_gate.py`
- **SonarQube:** `scripts/langgraph_engine/sonarqube_scanner.py`
- **Coverage:** `scripts/langgraph_engine/coverage_analyzer.py`
- **Breaking Changes:** `scripts/langgraph_engine/call_graph_analyzer.py`
- **Test Generator:** `scripts/langgraph_engine/test_generator.py`
