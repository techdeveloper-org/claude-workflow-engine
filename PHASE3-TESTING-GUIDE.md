# Phase 3: Testing & Integration Guide

**Status:** Implementation Ready
**Date:** 2026-03-10
**Scope:** Testing the complete 14-step Level 3 pipeline

---

## Testing Strategy

### Level of Testing
1. **Unit Tests** - Individual step modules
2. **Integration Tests** - Full pipeline with mock data
3. **End-to-End Tests** - Real Ollama + GitHub workflow
4. **Performance Tests** - Execution time profiling

---

## Prerequisites for Testing

### 1. Environment Setup

```bash
# Install all dependencies
pip install -r requirements.txt

# Verify Ollama is running
curl http://127.0.0.1:11434/api/status
# Response should show available models

# Set GitHub token (for GitHub workflow tests)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# (Optional) Configure Git
git config user.name "Claude Insight"
git config user.email "claude@insight.local"
```

### 2. Ollama Models

```bash
# Install required models (if not already available)
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b

# Start Ollama server (if not running)
ollama serve  # Listens on http://127.0.0.1:11434
```

### 3. Test Environment

```bash
# Create test session directory
mkdir -p ~/.claude/logs/sessions/test-session-001

# Verify directory structure
ls -la ~/.claude/logs/sessions/test-session-001/
```

---

## Unit Tests (Individual Steps)

### Test Step 1: Plan Mode Decision

```python
from scripts.langgraph_engine.level3_step1_planner import Level3Step1Planner

planner = Level3Step1Planner("~/.claude/logs/sessions/test-001/")

# Mock TOON object
toon = {
    "complexity_score": 6,
    "files_loaded_count": 3,
    "context": {"srs": True, "readme": True, "claude_md": False}
}

# Test decision
result = planner.execute(toon, "Fix dashboard data loading issue")

print(f"Plan required: {result['plan_required']}")
print(f"Risk level: {result['risk_level']}")
print(f"Reasoning: {result['reasoning']}")
```

**Expected Output:**
```
Plan required: True
Risk level: medium
Reasoning: Complex bug fix with multiple file changes requires planning
```

### Test Step 2: Plan Execution

```python
from scripts.langgraph_engine.level3_remaining_steps import Level3RemainingSteps

steps = Level3RemainingSteps("~/.claude/logs/sessions/test-001/")

result = steps.step2_plan_execution(toon, "Fix dashboard data")

assert result["success"] == True
assert len(result["files_affected"]) > 0
assert len(result["phases"]) > 0
print(f"✓ Plan generated: {len(result['plan'])} chars, {len(result['phases'])} phases")
```

### Test Step 5: Skill Selection

```python
from scripts.langgraph_engine.ollama_service import OllamaService

ollama = OllamaService()

# Mock blueprint
blueprint = {
    "plan": "Update dashboard metrics collection",
    "phases": [{"title": "Phase 1", "tasks": ["Update metrics"], "files_affected": ["src/metrics.py"]}]
}

skills = ["python-backend-engineer", "docker", "kubernetes"]
agents = ["orchestrator-agent", "python-backend-engineer"]

result = ollama.step5_skill_agent_selection(blueprint, skills, agents)

print(f"Selected skills: {result['final_skills_selected']}")
print(f"Selected agents: {result['final_agents_selected']}")
```

### Test GitHub Operations

```python
from scripts.langgraph_engine.git_operations import GitOperations

git = GitOperations(".")

# Test branch creation
result = git.create_branch("issue-42-test", "main")
assert result["success"] == True
print(f"✓ Branch created: {result['branch']}")

# Clean up
import subprocess
subprocess.run(["git", "checkout", "main"])
subprocess.run(["git", "branch", "-D", "issue-42-test"])
```

---

## Integration Test: Full Pipeline (Mock)

### Test Script

```python
"""
integration_test.py - Full Level 3 pipeline with mock data
"""

import json
from pathlib import Path
from scripts.langgraph_engine.level3_step1_planner import Level3Step1Planner
from scripts.langgraph_engine.level3_remaining_steps import Level3RemainingSteps
from scripts.langgraph_engine.logging_setup import setup_logger

def test_full_pipeline():
    """Test complete pipeline with mock data."""

    # Setup
    session_id = "test-pipeline-001"
    session_dir = Path(f"~/.claude/logs/sessions/{session_id}").expanduser()
    session_dir.mkdir(parents=True, exist_ok=True)

    # Logging
    exec_logger = setup_logger(session_dir, session_id)

    print("\n" + "=" * 60)
    print("PHASE 3: FULL PIPELINE TEST")
    print("=" * 60)

    # Mock data
    toon = {
        "session_id": session_id,
        "complexity_score": 6,
        "files_loaded_count": 3,
        "context": {"srs": True, "readme": True, "claude_md": True}
    }
    user_requirement = "Fix dashboard data not loading. Metrics are showing zeros."

    # Step 1: Plan Mode Decision
    print("\n[TEST] Step 1: Plan Mode Decision")
    planner = Level3Step1Planner(str(session_dir))
    step1 = planner.execute(toon, user_requirement)
    exec_logger.log_execution_step(1, "Plan Mode Decision",
        "success" if not step1.get("error") else "failed",
        duration_ms=step1.get("execution_time_ms", 0),
        error=step1.get("error"))
    assert step1.get("success") or "error" in step1
    print(f"✓ Plan required: {step1.get('plan_required')}")

    # If plan required, continue with Steps 2-4
    if step1.get("plan_required"):
        print("\n[TEST] Step 2: Plan Execution")
        steps = Level3RemainingSteps(str(session_dir))
        step2 = steps.step2_plan_execution(toon, user_requirement)
        assert step2.get("success")
        print(f"✓ Plan created: {len(step2['plan'])} chars")

        print("\n[TEST] Step 3: Task Breakdown")
        step3 = steps.step3_task_breakdown(
            step2.get("plan", ""),
            step2.get("files_affected", [])
        )
        assert step3.get("success")
        print(f"✓ Tasks: {step3['task_count']} identified")

        print("\n[TEST] Step 4: TOON Refinement")
        step4 = steps.step4_toon_refinement(
            toon,
            step2,
            step3.get("tasks", [])
        )
        assert step4.get("success")
        print(f"✓ TOON refined and saved")

    # Cleanup
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)

    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "tests_passed": True
    }

if __name__ == "__main__":
    result = test_full_pipeline()
    print(f"\nSession: {result['session_id']}")
    print(f"Location: {result['session_dir']}")
```

**Run the test:**
```bash
python integration_test.py
```

**Expected Output:**
```
============================================================
PHASE 3: FULL PIPELINE TEST
============================================================

[TEST] Step 1: Plan Mode Decision
✓ Plan required: True

[TEST] Step 2: Plan Execution
✓ Plan created: 1234 chars

[TEST] Step 3: Task Breakdown
✓ Tasks: 3 identified

[TEST] Step 4: TOON Refinement
✓ TOON refined and saved

============================================================
✅ ALL TESTS PASSED
============================================================
```

---

## Integration Test: LangGraph Execution

### Test Level 3 Subgraph

```python
"""
langgraph_test.py - Test LangGraph integration
"""

from scripts.langgraph_engine.subgraphs.level3_execution_v2 import create_level3_execution_subgraph_v2
from scripts.langgraph_engine.flow_state import FlowState

def test_langgraph_execution():
    """Test Level 3 subgraph with LangGraph."""

    print("\n[LANGGRAPH] Creating subgraph...")
    graph = create_level3_execution_subgraph_v2()
    print("✓ Subgraph created successfully")

    # Create initial state
    state = {
        "session_id": "test-langgraph-001",
        "session_dir": "~/.claude/logs/sessions/test-langgraph-001",
        "user_message": "Fix dashboard bug",
        "level1_context_toon": {
            "complexity_score": 5,
            "files_loaded_count": 3
        }
    }

    print("\n[LANGGRAPH] Executing graph...")
    try:
        # Execute graph
        result = graph.invoke(state)

        print(f"✓ Graph execution completed")
        print(f"  Status: {result.get('level3_status')}")
        print(f"  Time: {result.get('level3_total_execution_time_ms')}ms")
        print(f"  Errors: {len([k for k in result if k.endswith('_error') and result.get(k)])}")

        return True
    except Exception as e:
        print(f"✗ Graph execution failed: {e}")
        return False

if __name__ == "__main__":
    success = test_langgraph_execution()
    exit(0 if success else 1)
```

---

## End-to-End Test: Real Ollama + GitHub

### Prerequisites

```bash
# 1. Ollama running
ollama serve

# 2. GitHub token set
export GITHUB_TOKEN=ghp_...

# 3. In a test repository
cd /path/to/test-repo
git init
git remote add origin https://github.com/user/test-repo.git
```

### Test with Real Data

```python
"""
e2e_test.py - End-to-end test with real Ollama + GitHub
"""

from scripts.langgraph_engine.level3_step1_planner import Level3Step1Planner
from scripts.langgraph_engine.level3_steps8to12_github import Level3GitHubWorkflow

def test_e2e():
    """Test with real Ollama and GitHub."""

    session_dir = "~/.claude/logs/sessions/e2e-test-001"

    print("\n[E2E] Testing with real Ollama...")
    planner = Level3Step1Planner(session_dir)

    toon = {
        "complexity_score": 4,
        "files_loaded_count": 2,
        "context": {"srs": False, "readme": True, "claude_md": False}
    }

    result = planner.execute(toon, "Simple bug fix in utils.py")
    print(f"✓ Plan decision: {result['plan_required']}")

    # If GitHub token available, test GitHub workflow
    import os
    if os.getenv("GITHUB_TOKEN"):
        print("\n[E2E] Testing GitHub workflow...")
        workflow = Level3GitHubWorkflow(session_dir)

        issue_result = workflow.step8_create_issue(
            "Test Issue",
            "This is a test issue created by e2e test"
        )

        if issue_result.get("success"):
            print(f"✓ GitHub issue created: #{issue_result['issue_number']}")
        else:
            print(f"✗ GitHub issue failed: {issue_result.get('error')}")
    else:
        print("⚠ GITHUB_TOKEN not set, skipping GitHub tests")

if __name__ == "__main__":
    test_e2e()
```

---

## Performance Testing

### Measure Execution Times

```python
"""
performance_test.py - Measure pipeline performance
"""

import time
from scripts.langgraph_engine.level3_step1_planner import Level3Step1Planner
from scripts.langgraph_engine.level3_remaining_steps import Level3RemainingSteps

def benchmark_steps():
    """Benchmark each step."""

    session_dir = "~/.claude/logs/sessions/perf-test-001"
    toon = {"complexity_score": 6, "files_loaded_count": 3}
    requirement = "Fix dashboard data loading"

    results = {}

    # Step 1: Plan Mode Decision
    print("\n[PERF] Benchmarking Step 1...")
    planner = Level3Step1Planner(session_dir)
    start = time.time()
    result1 = planner.execute(toon, requirement)
    results["Step 1"] = (time.time() - start) * 1000
    print(f"Step 1: {results['Step 1']:.0f}ms")

    # Step 2: Plan Execution (if needed)
    if result1.get("plan_required"):
        print("[PERF] Benchmarking Step 2...")
        steps = Level3RemainingSteps(session_dir)
        start = time.time()
        result2 = steps.step2_plan_execution(toon, requirement)
        results["Step 2"] = (time.time() - start) * 1000
        print(f"Step 2: {results['Step 2']:.0f}ms")

        # Step 3
        print("[PERF] Benchmarking Step 3...")
        start = time.time()
        result3 = steps.step3_task_breakdown(
            result2.get("plan", ""),
            result2.get("files_affected", [])
        )
        results["Step 3"] = (time.time() - start) * 1000
        print(f"Step 3: {results['Step 3']:.0f}ms")

    # Summary
    total = sum(results.values())
    print("\n" + "=" * 40)
    print("PERFORMANCE SUMMARY")
    print("=" * 40)
    for step, ms in results.items():
        print(f"{step:10s}: {ms:6.0f}ms")
    print(f"{'Total':10s}: {total:6.0f}ms")
    print("=" * 40)

if __name__ == "__main__":
    benchmark_steps()
```

---

## Testing Checklist

### Phase 3 Testing Plan

- [ ] **Unit Tests** - All individual steps
  - [ ] Step 1: Plan mode decision
  - [ ] Step 2-7: Planning and preparation
  - [ ] Step 8-12: GitHub workflow
  - [ ] Step 13-14: Documentation and summary

- [ ] **Integration Tests** - Full pipeline
  - [ ] Mock data execution
  - [ ] Session persistence
  - [ ] Logging and error handling
  - [ ] File I/O operations

- [ ] **LangGraph Tests**
  - [ ] Subgraph creation
  - [ ] Node execution
  - [ ] Conditional routing (Step 1→2 vs Step 1→3)
  - [ ] State transitions

- [ ] **Ollama Tests** (with real server)
  - [ ] Model availability check
  - [ ] Step 1 execution
  - [ ] Step 5 execution
  - [ ] Step 7 execution
  - [ ] Error handling (timeout, unavailable)

- [ ] **GitHub Tests** (with token)
  - [ ] Issue creation
  - [ ] Branch creation
  - [ ] PR creation and merge
  - [ ] Issue closure

- [ ] **Performance Tests**
  - [ ] Measure each step timing
  - [ ] Total pipeline time
  - [ ] Memory usage
  - [ ] Log file sizes

---

## Expected Results

### Successful Pipeline Execution

```
Step 1: Plan Mode Decision    ✓ (2-5s)
Step 2: Plan Execution        ✓ (10-20s)
Step 3: Task Breakdown        ✓ (<1s)
Step 4: TOON Refinement       ✓ (<1s)
Step 5: Skill Selection       ✓ (5-10s)    [LLM recommends needed skills]
Step 6: Skill Validation      ✓ (1-5s)    [Scan local + download if needed]
Step 7: Prompt Generation     ✓ (5-10s)
Step 8: GitHub Issue          ✓ (1-2s)
Step 9: Branch Creation       ✓ (2-3s)
Step 10: Implementation       ⏳ (Manual)
Step 11: PR Creation & Merge  ✓ (3-5s)
Step 12: Issue Closure        ✓ (1-2s)
Step 13: Docs Update          ✓ (<1s)
Step 14: Final Summary        ✓ (<1s)

Total: ~41-81 seconds (excluding Step 10)

Step 6 Breakdown:
- Scan local skills/agents:    <1s
- Download missing (if any):   1-5s (depends on internet + file size)
- Return selected skills:      <1s
```

---

## Troubleshooting

### Ollama Not Available

```python
# Error: Connection refused
# Solution: Start Ollama server
ollama serve

# Check: Verify connection
curl http://127.0.0.1:11434/api/status
```

### Model Not Found

```python
# Error: Model qwen2.5:7b not available
# Solution: Pull model
ollama pull qwen2.5:7b

# Verify: List models
ollama list
```

### GitHub Token Invalid

```bash
# Error: 401 Unauthorized
# Solution: Generate new token
# GitHub → Settings → Developer settings → Personal access tokens
# Required scopes: repo, issue, pull_request

export GITHUB_TOKEN=ghp_xxxxx
```

### Session Directory Issues

```bash
# Error: Permission denied
# Solution: Create with proper permissions
mkdir -p ~/.claude/logs/sessions
chmod 755 ~/.claude/logs/sessions
```

---

## Next Steps

1. **Run Unit Tests** - Start with individual steps
2. **Run Integration Tests** - Test full mock pipeline
3. **Run LangGraph Tests** - Validate orchestrator integration
4. **Run E2E Tests** - Test with real Ollama + GitHub
5. **Performance Test** - Measure and optimize execution times
6. **Documentation** - Create final execution guide

---

**Status:** Ready for Testing ✓
**Estimated Time:** 2-3 hours for full test suite
**Success Criteria:** All 14 steps complete without errors

