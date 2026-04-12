# Troubleshooting Guide

**Project:** Claude Workflow Engine
**Version:** 1.15.1
**Last Updated:** 2026-04-04

---

## Failure Modes

### 1. GitHub Token: 401 Unauthorized

**Symptom:**
```
github.GithubException.GithubException: 401 {"message": "Bad credentials"}
```

**Cause:** `GITHUB_TOKEN` is not set, expired, or lacks required scopes.

**Fix:**
- Confirm the token is in `.env`: `grep GITHUB_TOKEN .env`
- Required scopes: `repo`, `issues`, `pull_requests`
- Generate a new token at: https://github.com/settings/tokens
- Test the token:
  ```bash
  curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('login'))"
  ```

---

### 2. LangGraph StateGraph: Missing Key in State

**Symptom:**
```
KeyError: 'step2_impact_analysis'
```

**Cause:** A pipeline node reads a key that was not populated by a previous node
(often because a step was skipped due to hook mode).

**Fix:**
- All state reads should use `.get()` with a fallback:
  ```python
  impact = state.get("step2_impact_analysis", {})
  ```
- If a node unconditionally requires a key, add it to the FlowState defaults in
  `langgraph_engine/state/flow_state.py`.

---

### 3. LangGraph State: Reducer Conflict

**Symptom:**
```
InvalidUpdateError: Cannot apply update -- reducer for key 'messages' expected list, got str
```

**Cause:** A node returns a state key with a type that conflicts with its registered
reducer (e.g., returning a string for a key whose reducer expects `list + list`).

**Fix:**
- Locate the reducer registration in `langgraph_engine/state/reducers.py`.
- Ensure the returning node wraps scalar values in a list when the reducer is
  `operator.add` (list concatenation):
  ```python
  # Wrong
  return {"messages": "hello"}
  # Correct
  return {"messages": ["hello"]}
  ```

---

### 4. Call Graph Builder: AST Parse Error

**Symptom:**
```
[call_graph_builder] AST parse error in src/mcp/some_file.py: invalid syntax (line 42)
```

**Cause:** A Python file in the project has a syntax error, or uses Python 3.10+
syntax (match/case) that the AST parser does not handle.

**Fix:**
- Fix the syntax error in the flagged file.
- The call graph builder skips unparseable files and continues -- the graph will
  be incomplete but not broken.
- Check which files were skipped:
  ```bash
  grep "AST parse error" logs/pipeline_*.log | sort -u
  ```

---

### 5. Stale Call Graph After Multi-Phase Implementation

**Symptom:** Step 11 code review reports no changes despite Step 10 writing files.

**Cause:** Call graph was not refreshed after Step 10 wrote files.

**Fix:** See `docs/runbooks/RUNBOOK_STALE_GRAPH.md` for full diagnosis steps.
Quick fix:
```bash
export FORCE_GRAPH_REBUILD=1
python scripts/3-level-flow.py --task "your task" --start-step 11
```

---

### 6. Jira Integration: ADF Formatting Error

**Symptom:**
```
JiraApiError: 400 Field 'description' cannot be set. It is not on the appropriate screen
```

**Cause:** The Jira project screen does not include the `description` field, or the
ADF (Atlassian Document Format) payload is malformed.

**Fix:**
- Switch to plain-text mode in `jira_mcp_server.py`:
  ```python
  USE_ADF = False  # Toggle in jira_mcp_server.py
  ```
- Or add the `description` field to the Jira project's Create Issue screen.

---

### 7. Windows Encoding Error: UnicodeEncodeError cp1252

**Symptom:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2019' in position 42
```

**Cause:** A Python source file or generated content contains non-ASCII characters.
Windows `cp1252` cannot encode them when writing to files without explicit encoding.

**Fix:**
- All Python files must be ASCII-only (project rule).
- For file writes, always specify `encoding="utf-8"`:
  ```python
  Path("output.txt").write_text(content, encoding="utf-8")
  ```
- Set `PYTHONIOENCODING=utf-8` in your shell profile to fix stdout/stderr.

---

### 8. Pipeline Step Timeout: LangGraph Watchdog

**Symptom:**
```
langgraph.errors.GraphInterrupt: Node 'step7_final_prompt' exceeded timeout (300s)
```

**Cause:** An LLM call at Step 7 (final prompt generation) is taking too long,
usually due to a slow provider or a very large context window.

**Fix:**
- Check which provider is active: `grep "active_provider" logs/pipeline_*.log`
- Switch to a faster provider: `LLM_PROVIDER=claude_cli`
- Reduce context size by trimming the task description or disabling Figma token
  injection for this run: `ENABLE_FIGMA=0`
- Increase the timeout in `langgraph_engine/orchestrator.py`:
  ```python
  step_timeout = 600  # seconds
  ```
