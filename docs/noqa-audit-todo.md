# noqa Audit — TODO List

**Master Issue:** [#217](../../issues/217)
**Goal:** Remove all `# ruff: noqa: F821` file-level suppressors from the codebase.

---

## Why This Matters

Four production bugs were found during the v1.16.x cleanup sprint — all hidden by `# ruff: noqa: F821` file-level suppressors.
See [CONTRIBUTING.md](../CONTRIBUTING.md) and the [Known Issues section in README](../README.md#known-issues--cleanup-history) for full history.

---

## Task List

### Task 1 — hooks/stop_notifier (30 real errors)
**Issue:** [#212](../../issues/212) | **Difficulty:** Medium | **Files:** 4

| File | Errors | Fix |
|------|--------|-----|
| `hooks/stop_notifier/core.py` | 17 | Add 10 missing names to `from .helpers import ...` |
| `hooks/stop_notifier/post_impl.py` | 4 | Add `import subprocess` at top |
| `hooks/stop_notifier/voice.py` | 9 | Add `MEMORY_BASE`, `VOICE_ENABLED`, `VOICE_SCRIPT` to `from .helpers import ...` |
| `hooks/stop_notifier/helpers.py` | 0 | Remove suppressor only |

Missing symbols (all defined in `helpers.py`):
- `core.py` needs: `SESSION_START_FLAG_PID`, `SESSION_START_FLAG`, `TASK_COMPLETE_FLAG_PID`, `TASK_COMPLETE_FLAG`, `WORK_DONE_FLAG_PID`, `WORK_DONE_FLAG`, `FLAG_DIR`, `MEMORY_BASE`, `_get_session_issues_file`, `emit_hook_execution`
- `voice.py` needs: `MEMORY_BASE`, `VOICE_ENABLED`, `VOICE_SCRIPT`

Verify:
```bash
python -m ruff check hooks/stop_notifier/ --select F821 --ignore-noqa
```

---

### Task 2 — level3_execution/nodes (17 real errors)
**Issue:** [#213](../../issues/213) | **Difficulty:** Medium | **Files:** 5

| File | Errors | Fix |
|------|--------|-----|
| `level3_execution/nodes/pre_nodes.py` | 1 | Import `_run_step` from `subgraph.py:226` |
| `level3_execution/nodes/step_wrappers_5to9.py` | 5 | Import `_run_step`, `get_infra`, `step8_`, `step9_` |
| `level3_execution/nodes/step_wrappers_12_14.py` | 11 | Import `_run_step`, `get_infra`, `step12_`, `step13_`, `step14_` |
| `level3_execution/nodes/orchestration.py` | 0 | Remove suppressor only |
| `level3_execution/nodes/step_wrappers_0to4.py` | 0 | Remove suppressor only |

Known symbol locations:
- `_run_step` → `langgraph_engine/level3_execution/subgraph.py:226`
- `get_infra` → `langgraph_engine/core/infrastructure.py:82`
- `step8_`, `step9_`, `step12_`, `step13_`, `step14_` → locate with:
  ```bash
  grep -rn "^def step8_\|^def step9_\|^def step12_\|^def step13_\|^def step14_" langgraph_engine/
  ```
  If not found → same class of defect as #211 (need to locate or reimplement).

Verify:
```bash
python -m ruff check langgraph_engine/level3_execution/nodes/ --select F821 --ignore-noqa
```

---

### Task 3 — diagrams/drawio/converter.py (~80 errors, 57 unique names)
**Issue:** [#214](../../issues/214) | **Difficulty:** Easy (import fix) | **Files:** 2

| File | Errors | Fix |
|------|--------|-----|
| `langgraph_engine/diagrams/drawio/converter.py` | ~80 | Add all 56 `S_*` constants + `logger` to imports |
| `langgraph_engine/diagrams/drawio/xml_helpers.py` | 0 | Remove suppressor only |

Current import in `converter.py`:
```python
from .xml_helpers import _edge, _edge_points, _esc, _IDGen, _vertex, _vertex_child, _wrap_mxfile
```

Missing: all `S_*` style constants (56 names, all starting with `S_`) defined in `xml_helpers.py` starting at line 66.
Also missing: `logger` — add standard try/except loguru fallback.

All 56 missing S_* names:
```
S_ABST_HDR, S_ACT_ACTION, S_ACT_ARROW, S_ACT_DIAMOND, S_ACT_FINAL, S_ACT_FORK,
S_ACT_INIT, S_AGGREGATE, S_ASSOCIATE, S_CLASS_DIV, S_CLASS_HDR, S_CLASS_ROW,
S_COMM_MSG, S_COMM_OBJ, S_COMPOSE, S_COMP_BOX, S_COMP_DEP, S_COMP_PROV,
S_CS_CLASS, S_CS_PART, S_CS_PORT, S_DEPEND, S_DEP_COMP, S_DEP_CONN,
S_DEP_DEVICE, S_DEP_NODE, S_IFACE_HDR, S_INHERIT, S_IO_ARROW, S_IO_DECISION,
S_IO_FINAL, S_IO_INIT, S_IO_REF, S_LIFELINE, S_MSG_ASYNC, S_MSG_RETURN,
S_MSG_SYNC, S_OBJ_DIV, S_OBJ_HDR, S_OBJ_LINK, S_OBJ_ROW, S_PKG_BOX,
S_PKG_IMPORT, S_REALIZE, S_ST_ARROW, S_ST_BOX, S_ST_COMP, S_ST_FINAL,
S_ST_INIT, S_ST_SELF, S_UC_ACTOR, S_UC_ASSOC, S_UC_CASE, S_UC_EXTEND,
S_UC_INCL, S_UC_SYSTEM
```

Verify:
```bash
python -m ruff check langgraph_engine/diagrams/drawio/ --select F821 --ignore-noqa
pytest tests/test_uml_generators.py -v
```

---

### Task 4 — scripts/github_pr_workflow (12 errors, 1 false positive)
**Issue:** [#215](../../issues/215) | **Difficulty:** Easy | **Files:** 3

| File | Errors | Fix |
|------|--------|-----|
| `scripts/github_pr_workflow/commit_push.py` | 2 | Add `GH_TIMEOUT` to `from .git_ops import` |
| `scripts/github_pr_workflow/review.py` | 6 real + 1 false positive | Add 3 names to `from .git_ops import`; inline noqa for `SESSION_STATE_FILE` |
| `scripts/github_pr_workflow/versioning.py` | 4 | Add 3 names to `from .git_ops import` |

All missing symbols are in `scripts/github_pr_workflow/git_ops.py`:

| Symbol | Type | Location |
|--------|------|----------|
| `GH_TIMEOUT` | Constant | `git_ops.py:47` |
| `MEMORY_BASE` | Constant | `git_ops.py:46` |
| `_get_session_id` | Function | `git_ops.py:86` |
| `_save_issues_mapping` | Function | `git_ops.py:115` |
| `_load_session_summary` | Function | `git_ops.py:130` |

For `SESSION_STATE_FILE` in `review.py` (lines 291-292): this is defined via try/except block (ruff false positive). Use targeted inline suppressor:
```python
if SESSION_STATE_FILE.exists():  # noqa: F821
    with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:  # noqa: F821
```

Verify:
```bash
python -m ruff check scripts/github_pr_workflow/ --select F821 --ignore-noqa
```

---

### Task 5 — Remove suppressors from 5 clean files (TRIVIAL — good first issue)
**Issue:** [#216](../../issues/216) | **Difficulty:** Trivial | **Files:** 5

All 5 files have **zero actual F821 errors**. Just delete the `# ruff: noqa: F821` line from each.

| File | Action |
|------|--------|
| `langgraph_engine/build_dependency_resolver/parsers.py` | Delete line 1: `# ruff: noqa: F821` |
| `hooks/stop_notifier/helpers.py` | Delete line with `# ruff: noqa: F821` |
| `langgraph_engine/level3_execution/nodes/orchestration.py` | Delete line 1: `# ruff: noqa: F821` |
| `langgraph_engine/level3_execution/nodes/step_wrappers_0to4.py` | Delete line 1: `# ruff: noqa: F821` |
| `scripts/helpers/session_resolver.py` | Delete line with `# ruff: noqa: F821` |

Verify:
```bash
python -m ruff check \
  langgraph_engine/build_dependency_resolver/parsers.py \
  hooks/stop_notifier/helpers.py \
  langgraph_engine/level3_execution/nodes/orchestration.py \
  langgraph_engine/level3_execution/nodes/step_wrappers_0to4.py \
  scripts/helpers/session_resolver.py \
  --select F821
# Expected: All checks passed!
```

---

## Final Verification (run after all 5 tasks are done)

```bash
# Zero F821 errors across entire repo
python -m ruff check langgraph_engine/ hooks/ scripts/ --select F821 --ignore-noqa

# No remaining file-level suppressors
grep -r "ruff: noqa: F821" --include="*.py" -l

# Full test suite still green
pytest tests/
```

**Expected after all tasks complete:**
- Zero F821 errors
- Zero file-level suppressors
- 793/793 tests pass (or more)

---

## Recommended Order

1. **Task 5** first (trivial, builds confidence, closes #216)
2. **Task 3** second (easy import fix, closes #214)
3. **Task 4** third (easy import fix, closes #215)
4. **Task 1** fourth (medium, requires reading helpers.py carefully, closes #212)
5. **Task 2** last (medium + investigation needed for step impl functions, closes #213)
