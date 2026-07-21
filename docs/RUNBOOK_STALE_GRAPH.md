# Runbook: Stale Call Graph

**Severity:** Medium
**Component:** call_graph_analyzer.py
**Introduced:** v1.6.1

---

## Symptom

After Step 10 writes implementation files, Step 11 (code review) or a later
multi-phase Step 10 call returns call-graph data that does not reflect the
files just written. Log lines typically show:

```
[call_graph_analyzer] Using cached graph snapshot (step10_pre_change_graph)
```

or the impact review diff shows zero new edges despite known changes.

---

## Root Cause

`call_graph_builder` builds an AST graph once per pipeline run and caches the
result. When Step 10 writes files, the in-memory graph becomes stale. Without
the v1.6.1 guard the analyzer would keep serving the pre-implementation
snapshot for all subsequent steps in the same run.

The `call_graph_stale` flag (set to `True` in FlowState after Step 10 writes)
signals `refresh_call_graph_if_stale()` to rebuild before serving data.

---

## Diagnosis

1. Check whether the flag was set:

   ```
   grep "call_graph_stale" logs/pipeline_<session_id>.log
   ```

   Expected: at least one line containing `call_graph_stale=True` after Step 10.

2. Check whether the refresh ran:

   ```
   grep "Rebuilding call graph" logs/pipeline_<session_id>.log
   ```

   If the first grep finds the flag but the second finds no rebuild, the guard
   function was not called or raised silently.

3. Confirm the project root passed to `refresh_call_graph_if_stale` is correct:

   ```python
   # In call_graph_analyzer.py
   def refresh_call_graph_if_stale(state, project_root):
       if state.get("call_graph_stale"):
           # rebuilds graph from project_root
   ```

   A wrong project root produces an empty graph rather than an error.

---

## Resolution Steps

### Option A — Automatic (standard path)

Ensure `FORCE_GRAPH_REBUILD` is not set to `0` (it defaults to rebuilding on
stale). If someone disabled it for debugging, re-enable:

```bash
unset FORCE_GRAPH_REBUILD
```

Re-run the pipeline from Step 10 onward.

### Option B — Force full rebuild

Set the env var to bypass the stale-flag check entirely and always rebuild:

```bash
export FORCE_GRAPH_REBUILD=1
python scripts/3-level-flow.py --task "your task" --start-step 10
```

### Option C — Manual cache clear

Delete the cached graph pickle (if persistent storage is enabled):

```bash
rm -f .pipeline_cache/call_graph_*.pkl
```

Then re-run the pipeline.

---

## Fallback Priority

`refresh_call_graph_if_stale` resolves the graph through the following chain:

1. Fresh scan (if `call_graph_stale=True`)
2. `state["step10_pre_change_graph"]`
3. `state["step2_impact_analysis"]`
4. `state["pre_analysis_result"]`
5. Fresh scan (nothing cached)

If all five fail, the function returns `call_graph_available=False` without
raising. The pipeline continues without call-graph context.

---

## Prevention

- Never skip Step 10's post-write state update (`call_graph_stale = True`).
- For multi-phase implementations, call `refresh_call_graph_if_stale` at the
  start of each phase, not just once at Step 10 entry.
- Add a test that writes a dummy `.py` file and asserts the graph rebuilds:

  ```python
  state["call_graph_stale"] = True
  result = refresh_call_graph_if_stale(state, project_root)
  assert result.get("call_graph_available") is True
  ```

---

## Escalation

If the stale guard is firing but the rebuilt graph is still wrong (wrong
project root, partial AST parse failures), escalate to the call-graph
maintainer with:

- The `project_root` value logged at rebuild time
- The count of `.py` files found (logged at DEBUG level)
- Any `AST parse error` lines from the session log
