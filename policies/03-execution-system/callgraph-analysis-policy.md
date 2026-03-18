# CallGraph Analysis Policy

**Version:** 1.0.0
**Priority:** HIGH
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines how the AST-based CallGraph drives intelligent decision-making at 3 critical
pipeline steps (2, 10, 11). The CallGraph provides structural code understanding so
the pipeline knows what could break BEFORE suggesting changes, captures pre-change
state during implementation, and detects breaking changes AFTER changes.

---

## CallGraph Data Source

### Builder: `call_graph_builder.py`

Constructs a full AST-based call graph with class context:

| Metric | Value |
|--------|-------|
| Classes tracked | 578+ |
| Methods tracked | 3,985+ |
| Languages | 4 (Python, Java, TypeScript, Kotlin) |

### Language Support

| Language | Method | Accuracy |
|----------|--------|----------|
| Python | Full AST parsing (`ast.parse()`) | HIGH |
| Java | Regex-based class/method detection | MEDIUM |
| TypeScript | Regex-based class/function detection | MEDIUM |
| Kotlin | Regex-based class/fun detection | MEDIUM |

---

## Step Integration

### Step 2: Plan Execution (Pre-Change Impact Analysis)

**Function:** `analyze_impact_before_change(task_description, affected_files)`

**What it does:**
1. Identifies methods that will be affected by the planned change
2. Traces callers/callees of affected methods (2 levels deep)
3. Calculates risk level based on:
   - Number of affected methods
   - Depth of call chain
   - Whether public API methods are touched
4. Identifies "danger zones" (highly-connected methods)

**Output:**

| Field | Type | Content |
|-------|------|---------|
| `step2_impact_analysis` | dict | risk_level, danger_zones, affected_methods |
| `step2_plan_validated` | bool | Whether plan accounts for all affected areas |

**Risk Levels:**

| Risk | Criteria | Action |
|------|----------|--------|
| LOW | < 5 affected methods, no public API | Proceed normally |
| MEDIUM | 5-15 affected methods OR 1 public API | Add to plan review |
| HIGH | > 15 affected methods OR 3+ public APIs | Mandatory plan review |

---

### Step 10: Implementation (Context Injection)

**Functions:**
- `snapshot_call_graph()` - Captures pre-change state
- `get_implementation_context(files)` - Returns caller/callee context

**What it does:**
1. Takes a snapshot of the current call graph BEFORE any code changes
2. For each file being modified, injects:
   - Direct callers of modified methods
   - Direct callees of modified methods
   - Class hierarchy context
3. Suggests test scope based on affected call paths

**Output:**

| Field | Type | Content |
|-------|------|---------|
| `step10_pre_change_graph` | dict | Full graph snapshot |
| `step10_call_context` | dict | Per-file caller/callee info |
| `step10_suggested_test_scope` | list | Methods that need testing |

---

### Step 11: Code Review (Post-Change Impact Detection)

**Function:** `review_change_impact(pre_graph, post_graph)`

**What it does:**
1. Compares pre-change and post-change call graphs
2. Detects breaking changes:
   - Removed methods that have callers
   - Changed method signatures
   - Orphaned methods (no callers after change)
   - New circular dependencies
3. Generates risk assessment

**Output:**

| Field | Type | Content |
|-------|------|---------|
| `step11_impact_review` | dict | Comparison results |
| `step11_breaking_changes` | list | Detected breaking changes |
| `step11_risk_assessment` | str | "safe", "caution", "risky" |

**Breaking Change Categories:**

| Category | Severity | Example |
|----------|----------|---------|
| Removed public method | CRITICAL | Method deleted but has 5 callers |
| Changed signature | HIGH | Parameter added/removed |
| Orphaned method | MEDIUM | Method has no callers (dead code) |
| New circular dep | HIGH | A->B->C->A cycle introduced |
| Renamed method | MEDIUM | Method renamed without updating callers |

---

## UML Integration

The CallGraph serves as the **single data source** for 13 UML diagram types via
adapters in `uml_generators.py`. This prevents duplicate AST analysis.

| Diagram Type | CallGraph Data Used |
|--------------|-------------------|
| Class diagram | Class hierarchy + methods |
| Sequence diagram | Method call chains |
| Component diagram | Module dependencies |
| Package diagram | Module groupings |
| Activity diagram | Method flow |
| (8 more types) | Various CallGraph views |

---

## Fallback Behavior

| Scenario | Fallback |
|----------|----------|
| CallGraph build fails | Skip impact analysis, proceed with warnings |
| File not in graph | Treat as new file, no impact data |
| Language not supported | Use regex-based detection (lower accuracy) |
| Graph too large (>10K methods) | Sample top 1000 most-connected methods |

---

## Implementation

- **Builder:** `scripts/langgraph_engine/call_graph_builder.py`
- **Analyzer:** `scripts/langgraph_engine/call_graph_analyzer.py`
- **UML Adapter:** `scripts/langgraph_engine/uml_generators.py`
- **Tests:** `tests/test_call_graph_builder.py`, `tests/test_call_graph_analyzer.py`
