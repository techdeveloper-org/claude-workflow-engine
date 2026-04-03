# Refactoring Execution Plan
# Claude Workflow Engine - Modular Sub-Package Decomposition
# Version: 1.0  |  Date: 2026-04-03  |  Status: APPROVED FOR EXECUTION

---

## 0. CONSTRAINTS (NON-NEGOTIABLE)

| Constraint | Enforcement |
|------------|-------------|
| Backward compatibility | Every moved symbol re-exported from original module via shim |
| ASCII-only Python | No Unicode chars in any .py file (cp1252-safe, Windows) |
| Tests green after each phase | pytest tests/ passes before next phase begins |
| No feature changes | Pure structural refactoring only |
| No new pip dependencies | Only stdlib + already-installed packages |
| Lazy imports maintained | No new import-time side effects |
| FlowState / StepKeys / NodeResult signatures | Unchanged in all phases |

---

## 1. CURRENT FILE INVENTORY (Phase A targets)

| ID | File | Lines | Why It Matters |
|----|------|-------|----------------|
| A1 | scripts/langgraph_engine/subgraphs/level3_execution.py | 2,608 | 15 monolithic step functions (step0-step14) + 2 routers + merge node |
| A2 | scripts/langgraph_engine/subgraphs/level3_execution_v2.py | 2,261 | 323-line _run_step() + 16 thin wrappers + orchestration_pre_analysis_node + infra getters |
| A3 | scripts/pre-tool-enforcer.py | 2,059 | 13 policy-check functions + 4 loader functions + main() |
| A4 | scripts/post-tool-tracker.py | 1,709 | 6 policy branches + progress tracking + github integration + main() |
| A5 | scripts/github_issue_manager.py | 1,703 | GitHub CRUD + branch management + session integration + utility functions |

---

## 2. AGENT ASSIGNMENTS

| Agent | Responsibilities |
|-------|-----------------|
| solution-architect | Produces this plan; reviews output at each phase gate |
| python-backend-engineer | All file creation, code movement, import shim writing |
| qa-testing-agent | Runs pytest tests/ after each phase; verifies import shims work; checks no test regressions |

---

## 3. PHASE SEQUENCING AND DEPENDENCY MAP

```
Phase A (sequential - each item depends on prior for imports)
  A1 (level3_execution.py split) MUST complete before A2
  A2 (level3_execution_v2.py refactor) MUST complete before QA-A gate
  A3, A4, A5 can run in parallel after A1+A2 complete

QA Gate A: pytest tests/ must pass before Phase B begins

Phase B (parallel groups within B)
  B1, B2, B3 can run in parallel (independent files)
  B4 (level1_sync.py) can run in parallel with B1/B2/B3
  B5 (call_graph_builder.py) can run in parallel with B1/B2/B3/B4
  B6, B7, B8 can run in parallel after all of B1-B5 complete

QA Gate B: pytest tests/ must pass before Phase C begins

Phase C (sequential)
  C1 (shared helpers) MUST complete before C2
  C2 (policy framework) MUST complete before C3
  C3 (__init__ shims) MUST complete before C4
  C4 (import updates) last step

QA Gate C (Final): pytest tests/ must pass; plan is complete
```

---

## 4. PHASE A - TIER 1 CRITICAL REFACTORING

### A1: level3_execution.py -> level3_execution/steps/ package

**Current state:** Monolithic file, 2,608 lines. Functions step0 through step14, 2 route functions, 1 merge node, 1 shared helper (call_execution_script).

**Target structure:**

```
scripts/langgraph_engine/subgraphs/level3_execution/
  __init__.py                  <- backward-compat re-export shim (ALL symbols)
  helpers.py                   <- call_execution_script() + shared constants
  steps/
    __init__.py                <- re-exports all step* symbols
    step0_task_analysis.py     <- step0_task_analysis()
    step1_plan_decision.py     <- step1_plan_mode_decision()
    step2_plan_execution.py    <- step2_plan_execution()
    step3_task_breakdown.py    <- step3_task_breakdown_validation()
    step4_toon_refinement.py   <- step4_toon_refinement()
    step5_skill_selection.py   <- step5_skill_agent_selection()
    step6_skill_download.py    <- step6_skill_validation_download()
    step7_prompt_generation.py <- step7_final_prompt_generation()
    step8_github_issue.py      <- step8_github_issue_creation()
    step9_branch_creation.py   <- step9_branch_creation()
    step10_implementation.py   <- step10_implementation_execution()
    step11_pr_review.py        <- step11_pull_request_review()
    step12_issue_closure.py    <- step12_issue_closure()
    step13_documentation.py    <- step13_project_documentation_update()
    step14_summary.py          <- step14_final_summary_generation()
  routing.py                   <- route_after_step1_plan_decision()
                                  route_after_step11_review()
                                  level3_merge_node()
```

**IMPORTANT:** The directory scripts/langgraph_engine/level3_execution/ already exists (separate package). The new sub-package must be placed at scripts/langgraph_engine/subgraphs/level3_execution/ (under subgraphs/, not at engine root). The original file becomes a shim.

**Exact functions to extract per file:**

| Target File | Function(s) | Approx Lines in Source |
|-------------|-------------|------------------------|
| helpers.py | call_execution_script() + module-level imports (_LEVEL3_SKILLS_DIR, _LEVEL3_AGENTS_DIR, _LANGGRAPH_AVAILABLE) | 1-131 |
| step0_task_analysis.py | step0_task_analysis() | 143-245 |
| step1_plan_decision.py | step1_plan_mode_decision() | 251-389 |
| step2_plan_execution.py | step2_plan_execution() | 390-541 |
| step3_task_breakdown.py | step3_task_breakdown_validation() | 542-595 |
| step4_toon_refinement.py | step4_toon_refinement() | 596-681 |
| step5_skill_selection.py | step5_skill_agent_selection() | 682-1012 |
| step6_skill_download.py | step6_skill_validation_download() | 1013-1277 |
| step7_prompt_generation.py | step7_final_prompt_generation() | 1278-1598 |
| step8_github_issue.py | step8_github_issue_creation() | 1599-1742 |
| step9_branch_creation.py | step9_branch_creation() | 1743-1804 |
| step10_implementation.py | step10_implementation_execution() | 1805-1999 |
| step11_pr_review.py | step11_pull_request_review() | 2000-2118 |
| step12_issue_closure.py | step12_issue_closure() | 2119-2208 |
| step13_documentation.py | step13_project_documentation_update() | 2209-2286 |
| step14_summary.py | step14_final_summary_generation() | 2287-2439 |
| routing.py | route_after_step1_plan_decision(), route_after_step11_review(), level3_merge_node() | 2440-2608 |

**Imports each step file needs:**
- `from pathlib import Path`
- `import json, sys, os` (as needed per function)
- `from loguru import logger` (if present in function body)
- `from ..flow_state import FlowState`  (relative from subgraphs/level3_execution/)
- `from .helpers import call_execution_script`
- Cross-step imports (step5 imports step6 helper, etc.) -> resolved by importing from .helpers or sibling steps

**Shim content for original scripts/langgraph_engine/subgraphs/level3_execution.py:**

```python
# BACKWARD-COMPAT SHIM - DO NOT EDIT DIRECTLY
# All symbols now live in subgraphs/level3_execution/ package.
# This file re-exports everything so existing imports keep working.
from .level3_execution.helpers import call_execution_script  # noqa: F401
from .level3_execution.steps import (  # noqa: F401
    step0_task_analysis,
    step1_plan_mode_decision,
    step2_plan_execution,
    step3_task_breakdown_validation,
    step4_toon_refinement,
    step5_skill_agent_selection,
    step6_skill_validation_download,
    step7_final_prompt_generation,
    step8_github_issue_creation,
    step9_branch_creation,
    step10_implementation_execution,
    step11_pull_request_review,
    step12_issue_closure,
    step13_project_documentation_update,
    step14_final_summary_generation,
)
from .level3_execution.routing import (  # noqa: F401
    route_after_step1_plan_decision,
    route_after_step11_review,
    level3_merge_node,
)
```

**Relative import adjustments inside each step file:**
- Original: `from ..flow_state import FlowState`
- In subgraphs/level3_execution/steps/stepN.py: `from ...flow_state import FlowState`
- Original: `from ..level3_execution.documentation_manager import ...`
- In subgraphs/level3_execution/steps/step0.py: `from ...level3_execution.documentation_manager import ...`

**QA check for A1:** After A1, run:
```bash
python -c "from scripts.langgraph_engine.subgraphs.level3_execution import step0_task_analysis, step14_final_summary_generation, route_after_step1_plan_decision"
pytest tests/test_level3_execution_v2.py tests/test_level3_remaining_steps.py -x
```

---

### A2: level3_execution_v2.py -> core/infrastructure.py + StepNodeFactory

**Current state:** 2,261 lines. Contains:
- 4 lazy infrastructure getters (_get_checkpoint_manager, _get_metrics_collector, _get_error_logger, _get_backup_manager)
- _get_infra() with session cache (_infra_cache)
- _write_step_log() helper
- _pipeline_start_times module dict
- _RAG_ELIGIBLE_STEPS constant
- _run_step() function (323 lines, lines 319-641) - the core dispatcher
- 16 step wrapper node functions (step0_0_project_context_node through step14_final_summary_node)
- orchestration_pre_analysis_node()
- route_to_plan_or_breakdown() and route_pre_analysis()
- build_level3_v2_subgraph() graph builder

**Target structure:**

```
scripts/langgraph_engine/core/infrastructure.py    <- NEW FILE
  _get_checkpoint_manager()
  _get_metrics_collector()
  _get_error_logger()
  _get_backup_manager()
  _get_infra()
  _infra_cache dict
  _pipeline_start_times dict

scripts/langgraph_engine/subgraphs/level3_execution_v2.py  <- REDUCED (~300 lines)
  All imports (kept)
  _write_step_log() (kept here - level3-specific)
  _RAG_ELIGIBLE_STEPS constant
  _run_step() (reduced by extracting infra calls to use core.infrastructure)
  StepNodeFactory class (NEW - wraps all 16 step node functions)
  orchestration_pre_analysis_node()
  route_to_plan_or_breakdown()
  route_pre_analysis()
  build_level3_v2_subgraph()
```

**StepNodeFactory class design:**

```python
class StepNodeFactory:
    """Factory that creates thin LangGraph node wrappers around step functions."""

    @staticmethod
    def make(step_number, step_label, step_fn, fallback=None):
        """Return a callable node function for the given step."""
        def node(state):
            return _run_step(step_number, step_label, step_fn, state,
                             fallback_result=fallback)
        node.__name__ = f"step{step_number:02d}_{step_label.lower().replace(' ', '_')}_node"
        return node
```

The 16 individual stepN_..._node functions are REPLACED by factory calls:

```python
step0_task_analysis_node       = StepNodeFactory.make(0, "STEP 0", step0_task_analysis)
step1_plan_mode_decision_node  = StepNodeFactory.make(1, "STEP 1", step1_plan_mode_decision)
# ... etc for steps 0-14
```

**core/infrastructure.py imports:**
```python
from pathlib import Path
from typing import Any, Dict
```
No circular deps - infrastructure.py does NOT import FlowState.

**level3_execution_v2.py shim after refactor:**
The file is reduced but remains at the same path. It now imports from core.infrastructure:
```python
from ..core.infrastructure import _get_infra, _pipeline_start_times
```

**QA check for A2:**
```bash
pytest tests/test_level3_execution_v2.py -x
python -c "from scripts.langgraph_engine.subgraphs.level3_execution_v2 import orchestration_pre_analysis_node, build_level3_v2_subgraph"
```

---

### A3: pre-tool-enforcer.py -> pre_tool_enforcer/ plugin directory

**Current state:** 2,059 lines. 13 check functions, 4 loaders, 1 main().

**Target structure:**

```
scripts/pre_tool_enforcer/
  __init__.py          <- PolicyRegistry + run_all_checks() entry
  core.py              <- main() entry point (~150 lines)
  registry.py          <- PolicyRegistry class
  policies/
    __init__.py
    checkpoint.py      <- check_checkpoint_pending()
    task_breakdown.py  <- check_task_breakdown_pending()
    skill_selection.py <- check_skill_selection_pending()
    level1_sync.py     <- check_level1_sync_complete()
    level2_standards.py <- check_level2_standards_complete()
    context_read.py    <- check_context_read_complete()
    bash_commands.py   <- check_bash()
    python_unicode.py  <- check_python_unicode()
    write_edit.py      <- check_write_edit()
    grep_opt.py        <- check_grep()
    read_opt.py        <- check_read()
    failure_kb.py      <- check_failure_kb_hints() + _load_failure_kb()
    skill_context.py   <- check_dynamic_skill_context()
  loaders.py           <- _load_flow_trace_context() + _load_failure_kb()
                          + get_current_session_id() + _load_raw_flow_trace()
```

**PolicyRegistry class design:**

```python
class PolicyRegistry:
    """Ordered list of policy check callables. Each returns (blocked: bool, msg: str)."""

    def __init__(self):
        self._checks = []  # List of (name, callable)

    def register(self, name, fn):
        self._checks.append((name, fn))

    def run_all(self, tool_name, tool_input, session_id=None):
        """Run all checks in order. Return first block result or (False, '')."""
        for name, check in self._checks:
            try:
                blocked, msg = check(tool_name, tool_input)
                if blocked:
                    return True, msg
            except Exception:
                pass  # Fail-open: never block on check errors
        return False, ''
```

**Original file scripts/pre-tool-enforcer.py becomes a shim:**

```python
# BACKWARD-COMPAT SHIM
# Pre-tool enforcement logic moved to scripts/pre_tool_enforcer/
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pre_tool_enforcer.core import main
if __name__ == '__main__':
    main()
```

**NOTE:** pre-tool-enforcer.py is invoked directly as a script by Claude Code hooks. The shim must preserve script execution behavior. The original `if __name__ == '__main__': main()` pattern is maintained.

**Import changes in each policy file:**
Each policies/*.py file imports loaders from:
```python
from ..loaders import _load_flow_trace_context, get_current_session_id
```
Constants like `BLOCKED_WHILE_CHECKPOINT_PENDING` move to `pre_tool_enforcer/__init__.py`.

**QA check for A3:**
```bash
pytest tests/test_pre_tool_enforcer.py -x
python scripts/pre-tool-enforcer.py  # should execute without error (hook mode test)
```

---

### A4: post-tool-tracker.py -> post_tool_tracker/ package

**Current state:** 1,709 lines. Contains progress tracking, 6 policy enforcement functions, GitHub integration, main().

**Target structure:**

```
scripts/post_tool_tracker/
  __init__.py            <- package init, re-exports main entry symbols
  core.py                <- main() (~200 lines)
  progress_tracker.py    <- PROGRESS_DELTA dict
                            _get_session_id_from_progress()
                            _clear_session_flags()
                            progress update logic (from main() body)
  github_integration.py  <- _get_github_issue_manager()
                            close_github_issues_on_completion()
  loaders.py             <- _load_flow_trace_context()
                            _load_raw_flow_trace() (if present)
  policies/
    __init__.py
    uncommitted_push.py  <- check_uncommitted_before_push() (~lines 691-730)
    post_merge_update.py <- run_post_merge_version_update() (~lines 733-784)
    task_tracking.py     <- task-update frequency warning logic
    phase_complexity.py  <- phase-complexity enforcement logic
    task_breakdown_clear.py <- Level 3.1 flag-clearing logic
    skill_selection_clear.py <- Level 3.5 flag-clearing logic
```

**Original scripts/post-tool-tracker.py becomes a shim:**

```python
# BACKWARD-COMPAT SHIM
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_tool_tracker.core import main
if __name__ == '__main__':
    main()
```

**QA check for A4:**
```bash
pytest tests/test_post_tool_tracker.py -x
```

---

### A5: github_issue_manager.py -> github_operations/ package

**Current state:** 1,703 lines. GitHub CRUD, branch management, session utilities, labeling.

**Target structure:**

```
scripts/github_operations/
  __init__.py                <- re-exports all public symbols
  client.py                  <- is_gh_available() + GH_TIMEOUT + MAX_OPS_PER_SESSION
                                _run_gh_cmd() (if extracted inline)
  session_integration.py     <- _get_session_id() + _get_current_session_id()
                                _get_mapping_file() + _load_issues_mapping()
                                _save_issues_mapping() + _get_ops_count()
                                _increment_ops_count()
  issue_manager.py           <- create_github_issue() (line 483)
                                close_github_issue() (line 1020)
                                _build_close_comment() (line 801)
                                extract_task_id_from_response() (line 221)
  branch_manager.py          <- create_issue_branch() (line 1420)
                                get_session_branch() (line 1610)
                                is_on_issue_branch() (line 1679)
  labels.py                  <- _build_issue_labels() (line 1290)
```

**Original scripts/github_issue_manager.py becomes a shim:**

```python
# BACKWARD-COMPAT SHIM
from github_operations.client import is_gh_available, GH_TIMEOUT, MAX_OPS_PER_SESSION  # noqa
from github_operations.session_integration import (  # noqa
    _get_session_id, _load_issues_mapping, _save_issues_mapping,
    _get_ops_count, _increment_ops_count,
)
from github_operations.issue_manager import (  # noqa
    create_github_issue, close_github_issue,
    extract_task_id_from_response,
)
from github_operations.branch_manager import (  # noqa
    create_issue_branch, get_session_branch, is_on_issue_branch,
)
from github_operations.labels import _build_issue_labels  # noqa
```

**QA check for A5:**
```bash
pytest tests/test_github_mcp_phase1.py tests/test_mcp_and_github_integration.py -x
python -c "import sys; sys.path.insert(0,'scripts'); import github_issue_manager; print(github_issue_manager.is_gh_available.__module__)"
```

---

### QA Gate A (MANDATORY before Phase B)

**Assigned to:** qa-testing-agent

**Checks:**
```
[ ] pytest tests/ -x  -> zero failures
[ ] python -c "from scripts.langgraph_engine.subgraphs.level3_execution import step0_task_analysis"
[ ] python -c "from scripts.langgraph_engine.subgraphs.level3_execution_v2 import orchestration_pre_analysis_node"
[ ] python -c "import sys; sys.path.insert(0,'scripts'); import pre_tool_enforcer; import post_tool_tracker_mod; import github_issue_manager"
[ ] No new import-time side effects (check with CLAUDE_WORKFLOW_RUNNING=1)
[ ] All shim files re-export every previously-exported symbol
[ ] ASCII-only: grep -rn '[^\x00-\x7F]' scripts/pre_tool_enforcer/ scripts/post_tool_tracker/ scripts/github_operations/
```

**Failure response:** Any test failure -> re-invoke python-backend-engineer with exact failing test + fix instruction. Do NOT proceed to Phase B on failure.

---

## 5. PHASE B - TIER 2 HIGH-PRIORITY REFACTORING

### B1: sonarqube_scanner.py (1,639 lines) -> sonarqube/ package (already partially done)

**Current state:** scripts/langgraph_engine/level3_execution/sonarqube_scanner.py. The sonarqube/ sub-package already exists at scripts/langgraph_engine/level3_execution/sonarqube/ with api_client.py, lightweight_scanner.py, result_aggregator.py, auto_fixer.py.

**Action:** sonarqube_scanner.py is a legacy entry point. Review what it exports that is NOT already in the sonarqube/ package and move those functions. Convert sonarqube_scanner.py to a shim that imports from the sub-package.

**Target:**
```
scripts/langgraph_engine/level3_execution/sonarqube_scanner.py  <- SHIM
  from .sonarqube.api_client import SonarQubeClient             # noqa
  from .sonarqube.lightweight_scanner import LightweightScanner  # noqa
  from .sonarqube.result_aggregator import SonarResultAggregator # noqa
  from .sonarqube.auto_fixer import SonarAutoFixer               # noqa
  # Re-export any standalone functions still in scanner
```

**QA check for B1:**
```bash
pytest tests/test_level3_robustness.py -x
python -c "from scripts.langgraph_engine.level3_execution.sonarqube_scanner import SonarQubeClient"
```

---

### B2: uml_generators.py (1,585 lines) -> diagrams/ package (already partially done)

**Current state:** scripts/langgraph_engine/uml_generators.py is documented as a compat shim -> diagrams/DiagramFactory. Verify it is truly a shim. If it still contains inline logic, extract to diagrams/.

**Action:**
1. Read uml_generators.py to confirm shim vs inline logic.
2. If shim: no action needed (already done in v1.9).
3. If inline logic remains: extract to diagrams/uml_generator_legacy.py and update shim.

**QA check for B2:**
```bash
pytest tests/test_uml_generators.py -x
```

---

### B3: diagrams/drawio_converter.py (1,507 lines) -> diagrams/drawio/ sub-package

**Current state:** One large file. Likely contains multiple DrawIO shape/layout generators.

**Action:** Read the file, identify class boundaries, split into:
```
scripts/langgraph_engine/diagrams/drawio/
  __init__.py           <- re-exports all public classes
  converter_base.py     <- base DrawIOConverter class + XML utilities
  shapes.py             <- shape factory functions
  layout.py             <- layout algorithms
  exporters.py          <- file export / URL generation
```
Original diagrams/drawio_converter.py becomes shim.

**QA check for B3:**
```bash
pytest -x -k "drawio"
```

---

### B4: level1_sync.py (1,478 lines) -> level1_sync/ package (already partially done)

**Current state:** scripts/langgraph_engine/subgraphs/level1_sync.py. The level1_sync/ package already exists at scripts/langgraph_engine/level1_sync/.

**Action:** The sub-package exists but the subgraph file may still be monolithic. Identify which node functions (node_session_loader, node_complexity_calculation, node_context_loader, node_toon_compression, level1_merge_node, cleanup_level1_memory) are NOT yet in the package and move them.

**Target:**
```
scripts/langgraph_engine/level1_sync/
  __init__.py                      <- re-exports all node functions
  nodes/
    __init__.py
    session_loader.py              <- node_session_loader()
    complexity_calculator.py       <- node_complexity_calculation()
    context_loader.py              <- node_context_loader() + helpers
    toon_compressor.py             <- node_toon_compression() + _verify_toon_integrity() + _decompress_toon()
    merge_cleanup.py               <- level1_merge_node() + cleanup_level1_memory()
  helpers.py                       <- _load_architecture_script() + _stream_file_head() + _read_file_with_timeout()
```

Original scripts/langgraph_engine/subgraphs/level1_sync.py becomes shim:
```python
# BACKWARD-COMPAT SHIM
from ..level1_sync.nodes import (  # noqa
    node_session_loader, node_complexity_calculation,
    node_context_loader, node_toon_compression,
    level1_merge_node, cleanup_level1_memory,
)
```

**QA check for B4:**
```bash
pytest tests/test_level1_sync.py tests/test_level1_sync_nodes.py -x
```

---

### B5: call_graph_builder.py (1,447 lines) -> parsers/ package (already partially done)

**Current state:** scripts/langgraph_engine/call_graph_builder.py. Documented as a compat shim -> parsers/. Verify.

**Action:**
1. Read the file to confirm shim vs inline logic.
2. If shim: confirm all 4 parser classes are in parsers/ (ParserRegistry + Python/Java/TS/Kotlin parsers).
3. If inline: extract CallGraph, CallGraphBuilder, _CallGraphVisitor, _RegexVisitor to parsers/call_graph.py. Move build_call_graph, get_call_graph_metrics, get_impact_analysis to parsers/__init__.py or parsers/api.py.

**QA check for B5:**
```bash
pytest tests/test_call_graph_builder.py -x
```

---

### B6: stop-notifier.py (1,382 lines) -> stop_notifier/ package

**Current state:** scripts/stop-notifier.py. Invoked by Stop hook.

**Action:** Read the file and identify function groups. Typical split:
```
scripts/stop_notifier/
  __init__.py
  core.py              <- main() entry point
  session_summary.py   <- session summary generation functions
  voice_notify.py      <- TTS / voice notification functions
  git_commit.py        <- auto-commit logic (if present)
  report_writer.py     <- report file writing logic
```

Original scripts/stop-notifier.py becomes shim:
```python
# BACKWARD-COMPAT SHIM
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stop_notifier.core import main
if __name__ == '__main__':
    main()
```

**QA check for B6:**
```bash
pytest tests/test_stop_notifier.py -x
```

---

### B7: github_pr_workflow.py (1,333 lines) -> github_operations/pr/ sub-package

**Current state:** scripts/langgraph_engine/github_pr_workflow.py. PR creation, merge, code review orchestration.

**Action:**
```
scripts/langgraph_engine/github_pr_workflow/
  __init__.py         <- re-exports
  pr_creator.py       <- PR creation functions
  pr_merger.py        <- merge logic
  review_handler.py   <- code review integration
  pr_workflow.py      <- end-to-end workflow orchestration
```

Original scripts/langgraph_engine/github_pr_workflow.py becomes shim.

**QA check for B7:**
```bash
pytest tests/test_step11_code_review.py tests/test_bulletproof_merge_detection.py -x
```

---

### B8: build_dependency_resolver.py (1,176 lines) -> build/ sub-package

**Current state:** scripts/langgraph_engine/build_dependency_resolver.py.

**Action:** Read file for class/function structure. Typical split:
```
scripts/langgraph_engine/build/
  __init__.py
  dependency_resolver.py  <- main resolver class
  language_detectors.py   <- per-language build file detection
  graph_builder.py        <- dependency graph construction
  conflict_detector.py    <- conflict detection logic
```

Original file becomes shim.

**QA check for B8:**
```bash
pytest -x -k "build_dependency or dependency_resolver"
```

---

### QA Gate B (MANDATORY before Phase C)

**Assigned to:** qa-testing-agent

```
[ ] pytest tests/ -x  -> zero failures
[ ] python -c "import scripts.langgraph_engine.uml_generators"  (shim import works)
[ ] python -c "import scripts.langgraph_engine.call_graph_builder"  (shim works)
[ ] python -c "from scripts.langgraph_engine.subgraphs.level1_sync import node_session_loader"
[ ] ASCII-only check on all new files
[ ] No import-time side effects introduced
```

---

## 6. PHASE C - CROSS-CUTTING: SHARED HELPERS AND DEDUPLICATION

### C1: Create scripts/helpers/ with shared utilities

**Purpose:** Extract functions duplicated between pre-tool-enforcer, post-tool-tracker, and github_issue_manager.

**Observed duplications:**
- `_load_flow_trace_context()` exists in BOTH pre-tool-enforcer.py and post-tool-tracker.py with nearly identical logic
- Session ID resolution logic appears in 3+ files
- `_load_failure_kb()` is in pre-tool-enforcer but referenced by post-tool-tracker

**Target:**
```
scripts/helpers/
  __init__.py
  session_resolver.py   <- get_current_session_id() shared implementation
                           read_session_file() utility
  flow_trace_reader.py  <- _load_flow_trace_context() shared implementation
                           _load_raw_flow_trace() shared implementation
  flag_manager.py       <- _clear_session_flags() + flag path resolution
```

**How to update callers:**
- pre_tool_enforcer/loaders.py: replace local _load_flow_trace_context with `from helpers.flow_trace_reader import _load_flow_trace_context`
- post_tool_tracker/loaders.py: same
- Keep local wrappers with same name for backward compat if needed

---

### C2: Create scripts/policy_framework/ with shared policy infrastructure

**Purpose:** The PolicyRegistry pattern developed in A3 (pre_tool_enforcer) can serve as a shared base for post_tool_tracker policies too.

**Target:**
```
scripts/policy_framework/
  __init__.py
  registry.py     <- PolicyRegistry (moved from pre_tool_enforcer/registry.py)
  base_policy.py  <- BasePolicy abstract class (optional, for future typed policies)
  result.py       <- PolicyResult named tuple (blocked: bool, message: str, severity: str)
```

**Update callers:**
- pre_tool_enforcer/registry.py: import from policy_framework instead
- post_tool_tracker/core.py: use PolicyRegistry from policy_framework

---

### C3: __init__.py backward-compatible re-exports audit

**Purpose:** Verify every original module's public API is fully re-exported through shims.

**Checklist per shim file:**
```
[ ] scripts/langgraph_engine/subgraphs/level3_execution.py
    - All 15 step* functions exported
    - call_execution_script exported
    - 3 routing/merge functions exported

[ ] scripts/langgraph_engine/subgraphs/level3_execution_v2.py
    - orchestration_pre_analysis_node exported
    - route_pre_analysis exported
    - build_level3_v2_subgraph exported
    - StepNodeFactory exported (new)

[ ] scripts/pre-tool-enforcer.py
    - main() accessible as script (not just import)

[ ] scripts/post-tool-tracker.py
    - main() accessible as script

[ ] scripts/github_issue_manager.py
    - create_github_issue, close_github_issue exported
    - is_gh_available, extract_task_id_from_response exported
    - create_issue_branch, get_session_branch, is_on_issue_branch exported
    - _build_issue_labels exported (used internally)

[ ] scripts/langgraph_engine/call_graph_builder.py
    - build_call_graph, get_call_graph_metrics, get_impact_analysis
    - CallGraph, CallGraphBuilder classes

[ ] scripts/langgraph_engine/uml_generators.py
    - DiagramFactory + all 13 generator classes
```

---

### C4: Update all imports across codebase

**Purpose:** After C1-C3, update callers that import directly from the original large files to import from the new sub-packages. This is for correctness; shims ensure it is not strictly required for tests to pass, but direct imports are preferred for clarity.

**Files to audit for import updates:**
```bash
grep -rn "from .level3_execution import\|from ..level3_execution import" scripts/langgraph_engine/
grep -rn "import github_issue_manager" scripts/
grep -rn "from .level1_sync import" scripts/langgraph_engine/subgraphs/
```

**Key import locations to update:**
- scripts/langgraph_engine/subgraphs/level3_execution_v2.py line 71-90: imports from .level3_execution -> update to from .level3_execution.steps import ...
- scripts/langgraph_engine/level3_steps8to12_jira.py (if imports from level3_execution)
- scripts/langgraph_engine/orchestrator.py (imports subgraph builders)
- tests/ files: do NOT change test imports - they test the public API which must still work via shims

---

### QA Gate C (FINAL - MANDATORY)

**Assigned to:** qa-testing-agent

**Full verification checklist:**
```
[ ] TASK COMPLETION:    All 18 target files have been refactored with shims in place
[ ] CODE INTEGRITY:     python -m py_compile on all new files (no syntax errors)
[ ] TESTS EXIST:        New test stubs exist for StepNodeFactory, PolicyRegistry (if not covered by existing tests)
[ ] TESTS PASS:         pytest tests/ -x  -> zero failures
[ ] RECENT CHANGES:     git diff --stat reviewed; no unintended modifications
[ ] LINT/FORMAT:        No trailing whitespace, no mixed indent in new files
[ ] CONTRACT MATCH:     All shim files export exactly the same symbols as documented in C3 checklist
[ ] ASCII-ONLY:         grep -rPn '[^\x00-\x7F]' scripts/pre_tool_enforcer/ scripts/post_tool_tracker/ scripts/github_operations/ scripts/stop_notifier/ scripts/helpers/ scripts/policy_framework/
[ ] IMPORT VERIFY:      python -c "from scripts.langgraph_engine.subgraphs.level3_execution import step0_task_analysis, step14_final_summary_generation"
[ ] HOOK VERIFY:        echo '{}' | python scripts/pre-tool-enforcer.py  (no crash, exits 0)
[ ] HOOK VERIFY:        echo '{}' | python scripts/post-tool-tracker.py  (no crash, exits 0)
```

---

## 7. ERROR HANDLING STRATEGY

### Per-step failure classification

| Failure Type | Response |
|--------------|----------|
| Import error in new module | Rollback: restore original file from git, re-invoke python-backend-engineer with exact error |
| Test regression | Halt phase. Fix the specific failing test before proceeding. Never skip tests |
| Shim missing symbol | Add the missing re-export to the shim immediately (not deferred) |
| Circular import introduced | Restructure: move shared dependency to helpers/ to break cycle |
| ASCII violation in new file | Fix immediately: replace any non-ASCII chars with ASCII equivalents |

### Rollback scope per phase

| Phase | Rollback Scope |
|-------|----------------|
| A1 fails | Delete subgraphs/level3_execution/ directory; restore level3_execution.py from git |
| A2 fails | Delete core/infrastructure.py; restore level3_execution_v2.py from git |
| A3 fails | Delete pre_tool_enforcer/; restore pre-tool-enforcer.py from git |
| A4 fails | Delete post_tool_tracker/; restore post-tool-tracker.py from git |
| A5 fails | Delete github_operations/; restore github_issue_manager.py from git |
| Phase B item fails | Delete new sub-package; restore original file from git |
| Phase C fails | Revert C4 import updates; keep shims from A/B (still backward compat) |

### Retry policy
- Transient tool errors (file not found, subprocess timeout): retry once
- Logic errors (wrong function extracted, wrong imports): fix and re-run, no retry limit
- After 3 failed attempts on the same step: escalate to user with diagnosis

---

## 8. LOGGING AND OBSERVABILITY

### Workflow correlation ID
Each phase execution logs with prefix: `[REFACTOR-A1]`, `[REFACTOR-A2]` etc.

### Per-agent handoff log entry format
```
AGENT HANDOFF:
  Step:     {phase-item}
  Agent:    python-backend-engineer
  Files created: {list with line counts}
  Files modified: {list with +/- line counts}
  Status:   COMPLETE | FAILED
  QA result: PASS | FAIL (details)
```

### What to log at each gate
- QA Gate A: full pytest output (truncated to failures only if passing)
- QA Gate B: full pytest output
- QA Gate C: full verification checklist with PASS/FAIL per item

---

## 9. EXECUTION ORDER SUMMARY

```
Sequential block 1:
  [python-backend-engineer] A1: level3_execution.py split
  [python-backend-engineer] A2: level3_execution_v2.py refactor
  [qa-testing-agent] Verify A1+A2

Parallel block 1 (after A1+A2 pass QA):
  [python-backend-engineer] A3: pre-tool-enforcer split
  [python-backend-engineer] A4: post-tool-tracker split
  [python-backend-engineer] A5: github_issue_manager split

[qa-testing-agent] QA Gate A (after A3+A4+A5 all complete)

Parallel block 2 (after QA Gate A):
  [python-backend-engineer] B1: sonarqube_scanner shim
  [python-backend-engineer] B2: uml_generators verify/shim
  [python-backend-engineer] B3: drawio_converter split
  [python-backend-engineer] B4: level1_sync package completion
  [python-backend-engineer] B5: call_graph_builder verify/shim

Sequential block 2 (after B1-B5 complete):
  [python-backend-engineer] B6: stop-notifier split
  [python-backend-engineer] B7: github_pr_workflow split
  [python-backend-engineer] B8: build_dependency_resolver split

[qa-testing-agent] QA Gate B (after B6+B7+B8 complete)

Sequential block 3 (after QA Gate B):
  [python-backend-engineer] C1: shared helpers/
  [python-backend-engineer] C2: policy_framework/
  [python-backend-engineer] C3: shim audit
  [python-backend-engineer] C4: import updates

[qa-testing-agent] QA Gate C (FINAL)
```

---

## 10. FILE COUNT SUMMARY

| Phase | New Files Created | Original Files Shimmed | Net Change |
|-------|-------------------|------------------------|------------|
| A1 | 18 (16 steps + helpers.py + routing.py) + 1 __init__ + 1 steps/__init__ | 1 (level3_execution.py) | +20 |
| A2 | 1 (core/infrastructure.py) | level3_execution_v2.py reduced | +1 |
| A3 | ~16 (core + registry + loaders + 13 policies + __init__s) | 1 (pre-tool-enforcer.py) | +15 |
| A4 | ~9 (core + progress + github + loaders + 5 policies + __init__s) | 1 (post-tool-tracker.py) | +8 |
| A5 | 6 (client + session + issue_manager + branch + labels + __init__) | 1 (github_issue_manager.py) | +5 |
| B1-B8 | ~25 total across 8 files | 8 files shimmed | +17 |
| C1-C4 | ~7 (helpers + policy_framework + __init__s) | 0 | +7 |
| **TOTAL** | **~72** | **12 files shimmed** | **~73** |

---

## 11. RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Relative import depth breaks (../../ vs ../) | HIGH | HIGH | Test each new file with python -m py_compile immediately after creation |
| Hook scripts fail (pre-tool, post-tool executed as scripts) | MEDIUM | HIGH | Test with echo '{}' pipe after every hook refactor |
| Windows path sep in new imports | LOW | HIGH | Use Path() or forward slashes in all new code |
| Circular import from helpers/ | MEDIUM | MEDIUM | helpers/ must import ONLY stdlib; no imports from scripts/langgraph_engine/ |
| Test isolation broken by module-level state (_infra_cache, _gh_available) | MEDIUM | MEDIUM | Move module-level caches into class-level in refactored versions |
| level3_execution package name collision with level3_execution/ dir | HIGH | HIGH | The new dir goes under subgraphs/level3_execution/, NOT at engine root |

---

## 12. PYTHON-BACKEND-ENGINEER INSTRUCTION TEMPLATE

For each phase item, the orchestrator issues this instruction format to python-backend-engineer:

```
TASK:       Refactor {file} as described in docs/refactoring-plan.md section {A1/A2/...}
INPUT:      Current file at {absolute_path} (read it first)
            Refactoring-plan at /...claude-workflow-engine/docs/refactoring-plan.md
OUTPUT:     New package directory at {target_path}
            Shim file replacing the original at {original_path}
MUST NOT:   Change any function signatures, behavior, or logic
MUST NOT:   Add new pip dependencies
MUST NOT:   Use Unicode characters in .py files
MUST NOT:   Change any test files
VERIFY:     After creation, run: python -m py_compile {each_new_file}
            Then: python -c "from {original_import_path} import {key_symbols}"
```

---

*Plan produced by: orchestrator-agent / solution-architect*
*Based on: analysis of 5 Phase A files (reading lines 1-300 each + function grep)*
*Next action: Execute Phase A starting with A1 (level3_execution.py split)*
