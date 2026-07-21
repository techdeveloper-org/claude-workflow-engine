# 🚀 PARALLEL TASK EXECUTION WITH PARALLEL SUBAGENTS POLICY

**VERSION:** 1.0.0
**STATUS:** 🟢 ACTIVE
**PRIORITY:** 🔴 CRITICAL (STEP 7 in Execution Flow)
**TYPE:** Execution Automation
**LOCATION:** `~/.claude/memory/03-execution-system/parallel-execution-policy.md`

---

## 📋 TABLE OF CONTENTS

1. [Overview](#-overview)
2. [When to Use Parallel Execution](#-when-to-use-parallel-execution)
3. [Parallel Execution Strategy](#-parallel-execution-strategy)
4. [Temporary Skill/Agent Creation](#-temporary-skillagent-creation)
5. [Result Merging Strategy](#-result-merging-strategy)
6. [Lifecycle Management](#-lifecycle-management)
7. [Execution Flow Integration](#-execution-flow-integration)
8. [Implementation Scripts](#-implementation-scripts)
9. [Examples](#-examples)

---

## 🎯 OVERVIEW

**PURPOSE:**
Maximize execution efficiency by running independent tasks in parallel using multiple subagents, creating temporary skills/agents as needed, and intelligently merging results.

**KEY BENEFITS:**
- ⚡ **10x Faster Execution** - Run independent tasks simultaneously
- 🤖 **Auto Parallelization** - Automatically detect parallelizable tasks
- 🔧 **Dynamic Skills/Agents** - Create temporary tools on-the-fly
- 🔄 **Smart Merging** - Intelligently combine results
- 🗑️ **Auto Cleanup** - Remove unused temporary resources

**PHILOSOPHY:**
```
Sequential Execution:  Task1 → Task2 → Task3 → Task4  (Takes 4x time)
Parallel Execution:    [Task1, Task2, Task3, Task4]   (Takes 1x time!)
```

---

## 🔍 WHEN TO USE PARALLEL EXECUTION

### ✅ Use Parallel Execution When:

| Scenario | Example | Benefit |
|----------|---------|---------|
| **Multiple Independent Services** | Creating auth-service, user-service, product-service | 3x faster |
| **Multiple File Operations** | Reading 5 service configs | 5x faster |
| **Multi-Repository Operations** | Cloning 3 repos, pushing to 4 repos | 4x faster |
| **Parallel Testing** | Running unit tests across 5 services | 5x faster |
| **Parallel Builds** | Building 3 microservices | 3x faster |
| **Research Tasks** | Searching 4 different patterns | 4x faster |
| **Independent Endpoints** | Creating 6 REST endpoints | 6x faster |
| **Configuration Updates** | Updating configs in 5 services | 5x faster |

### ❌ Don't Use Parallel Execution When:

| Scenario | Reason |
|----------|--------|
| Tasks have dependencies | Task B needs output from Task A |
| Sequential database migrations | Order matters |
| Git operations on same repo | Conflicts possible |
| Single file editing | No parallelization possible |
| Resource-intensive operations | May overload system |

---

## 🚀 PARALLEL EXECUTION STRATEGY

### Phase 1: Task Analysis

```python
# Auto-detect parallel opportunities
def analyze_tasks_for_parallelization(tasks):
    """
    Analyze task list and identify which can run in parallel.

    Returns:
        parallel_groups: List of task groups that can run in parallel
        sequential_tasks: Tasks that must run sequentially
    """

    # Build dependency graph
    dependency_graph = build_dependency_graph(tasks)

    # Group tasks by dependencies
    parallel_groups = []
    current_group = []

    for task in tasks:
        if not has_dependencies(task, current_group):
            current_group.append(task)
        else:
            if current_group:
                parallel_groups.append(current_group)
            current_group = [task]

    if current_group:
        parallel_groups.append(current_group)

    return parallel_groups
```

### Phase 2: Parallel Execution

```bash
#!/bin/bash
# parallel-task-executor.sh

# Execute tasks in parallel using multiple subagents

execute_parallel_tasks() {
    local tasks=("$@")
    local pids=()
    local task_ids=()

    echo "🚀 Launching ${#tasks[@]} tasks in parallel..."

    # Launch all tasks in background
    for task in "${tasks[@]}"; do
        # Extract task details
        task_id=$(echo "$task" | jq -r '.id')
        task_type=$(echo "$task" | jq -r '.type')
        task_prompt=$(echo "$task" | jq -r '.prompt')

        # Select appropriate subagent
        subagent_type=$(select_subagent "$task_type")

        # Launch in background
        python ~/.claude/memory/scripts/parallel-executor.py \
            --task-id "$task_id" \
            --subagent "$subagent_type" \
            --prompt "$task_prompt" \
            --background &

        local pid=$!
        pids+=($pid)
        task_ids+=($task_id)

        echo "  ✅ Launched Task $task_id (PID: $pid, Agent: $subagent_type)"
    done

    echo ""
    echo "⏳ Waiting for all tasks to complete..."

    # Wait for all to complete
    local failed=0
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local task_id=${task_ids[$i]}

        wait $pid
        local exit_code=$?

        if [ $exit_code -eq 0 ]; then
            echo "  ✅ Task $task_id completed successfully"
        else
            echo "  ❌ Task $task_id failed (exit code: $exit_code)"
            ((failed++))
        fi
    done

    echo ""
    if [ $failed -eq 0 ]; then
        echo "✅ All ${#tasks[@]} tasks completed successfully!"
        return 0
    else
        echo "❌ $failed tasks failed out of ${#tasks[@]}"
        return 1
    fi
}
```

### Phase 3: Result Collection

```python
# collect-parallel-results.py

def collect_parallel_results(task_ids):
    """
    Collect results from all parallel tasks.

    Returns:
        results: Dict mapping task_id to result
    """
    results = {}

    for task_id in task_ids:
        result_file = f"~/.claude/memory/temp/parallel-results/{task_id}.json"

        if os.path.exists(result_file):
            with open(result_file, 'r') as f:
                results[task_id] = json.load(f)
        else:
            results[task_id] = {"status": "failed", "error": "No result file"}

    return results
```

---

## 🔧 TEMPORARY SKILL/AGENT CREATION

### When to Create Temporary Skills/Agents

**CREATE TEMPORARY when:**
- ✅ Task requires specialized knowledge not in existing skills
- ✅ One-time operation with unique requirements
- ✅ Domain-specific task (e.g., "migrate legacy API to GraphQL")
- ✅ Experimental/prototype work
- ✅ Complex multi-step operation that needs orchestration

**USE EXISTING when:**
- ❌ Task matches existing skill capabilities
- ❌ Standard operations (CRUD, deployments, testing)
- ❌ Common patterns already handled

### Temporary Skill/Agent Registry

**Location:** `~/.claude/memory/temp/temp-skills-registry.json`

```json
{
    "temporary_skills": [
        {
            "name": "graphql-migration-expert",
            "created": "2026-02-16T10:30:00",
            "created_by": "parallel-executor",
            "usage_count": 1,
            "last_used": "2026-02-16T10:30:00",
            "status": "active",
            "keep_reason": null,
            "delete_reason": null
        }
    ],
    "temporary_agents": [
        {
            "name": "legacy-api-migrator",
            "created": "2026-02-16T10:35:00",
            "created_by": "parallel-executor",
            "usage_count": 1,
            "last_used": "2026-02-16T10:35:00",
            "status": "active",
            "keep_reason": null,
            "delete_reason": null
        }
    ]
}
```

### Creation Script

```python
# temp-skill-agent-creator.py

def create_temporary_skill(name, description, capabilities):
    """
    Create a temporary skill for specialized task.

    Args:
        name: Skill name (e.g., "graphql-migration-expert")
        description: What the skill does
        capabilities: List of capabilities

    Returns:
        skill_path: Path to created skill
    """

    # Generate skill definition
    skill_def = {
        "name": name,
        "description": description,
        "capabilities": capabilities,
        "temporary": True,
        "created": datetime.now().isoformat(),
        "usage_count": 0
    }

    # Create skill directory
    skill_dir = f"~/.claude/skills/temp/{name}"
    os.makedirs(skill_dir, exist_ok=True)

    # Write skill.md
    skill_file = f"{skill_dir}/skill.md"
    with open(skill_file, 'w') as f:
        f.write(generate_skill_markdown(skill_def))

    # Register in temp registry
    register_temp_skill(name, skill_def)

    print(f"✅ Created temporary skill: {name}")
    print(f"📁 Location: {skill_dir}")

    return skill_dir


def create_temporary_agent(name, description, tools):
    """
    Create a temporary agent for specialized execution.

    Args:
        name: Agent name (e.g., "legacy-api-migrator")
        description: What the agent does
        tools: List of tools the agent can use

    Returns:
        agent_config: Agent configuration
    """

    # Generate agent definition
    agent_def = {
        "name": name,
        "description": description,
        "tools": tools,
        "temporary": True,
        "created": datetime.now().isoformat(),
        "usage_count": 0
    }

    # Register in temp registry
    register_temp_agent(name, agent_def)

    print(f"✅ Created temporary agent: {name}")

    return agent_def
```

### Keep or Delete Decision

```python
# temp-resource-manager.py

def decide_keep_or_delete(resource_name, resource_type):
    """
    Decide whether to keep or delete a temporary resource.

    Decision Criteria:
        KEEP if:
        - Used 3+ times
        - Used in last 7 days
        - Marked as useful by user
        - Solves common problem

        DELETE if:
        - One-time use only
        - Not used in 30+ days
        - Redundant with existing skill/agent
        - Task completed and no future need

    Returns:
        decision: "keep" or "delete"
        reason: Explanation for decision
    """

    registry = load_temp_registry()
    resource = registry.get(resource_type, {}).get(resource_name)

    if not resource:
        return "delete", "Resource not found"

    # Check usage
    usage_count = resource.get("usage_count", 0)
    last_used = datetime.fromisoformat(resource.get("last_used"))
    days_since_last_use = (datetime.now() - last_used).days

    # Decision logic
    if usage_count >= 3:
        return "keep", f"Used {usage_count} times - shows value"

    if days_since_last_use <= 7:
        return "keep", "Recently used - might be needed again"

    if resource.get("user_marked_useful"):
        return "keep", "User marked as useful"

    if days_since_last_use >= 30:
        return "delete", f"Not used in {days_since_last_use} days"

    if usage_count == 1 and days_since_last_use >= 7:
        return "delete", "One-time use, no recent activity"

    # Check for redundancy
    if is_redundant_with_existing(resource_name, resource_type):
        return "delete", "Redundant with existing skill/agent"

    # Default: keep for now
    return "keep", "Pending further usage data"


def cleanup_temp_resources():
    """
    Cleanup temporary resources based on keep/delete decisions.
    """

    registry = load_temp_registry()

    deleted_count = 0
    kept_count = 0

    # Check temporary skills
    for skill_name in registry.get("temporary_skills", []):
        decision, reason = decide_keep_or_delete(skill_name, "skill")

        if decision == "delete":
            delete_temp_skill(skill_name)
            print(f"🗑️ Deleted temp skill: {skill_name} - {reason}")
            deleted_count += 1
        else:
            print(f"✅ Keeping temp skill: {skill_name} - {reason}")
            kept_count += 1

    # Check temporary agents
    for agent_name in registry.get("temporary_agents", []):
        decision, reason = decide_keep_or_delete(agent_name, "agent")

        if decision == "delete":
            delete_temp_agent(agent_name)
            print(f"🗑️ Deleted temp agent: {agent_name} - {reason}")
            deleted_count += 1
        else:
            print(f"✅ Keeping temp agent: {agent_name} - {reason}")
            kept_count += 1

    print(f"\n📊 Cleanup Summary: Kept {kept_count}, Deleted {deleted_count}")
```

---

## 🔄 RESULT MERGING STRATEGY

### Merge Scenarios

| Scenario | Merge Strategy |
|----------|----------------|
| **Multiple Service Creations** | Aggregate status, combine file lists |
| **Multiple File Reads** | Concatenate contents, index by file |
| **Multiple Search Results** | Deduplicate, rank by relevance |
| **Multiple Test Results** | Aggregate pass/fail, combine coverage |
| **Multiple Build Results** | Check all succeeded, combine artifacts |
| **Multiple Deployments** | Verify all deployed, aggregate endpoints |

### Merge Implementation

```python
# result-merger.py

def merge_parallel_results(results, merge_strategy):
    """
    Merge results from parallel executions.

    Args:
        results: Dict mapping task_id to result
        merge_strategy: How to merge results

    Returns:
        merged_result: Combined result
    """

    if merge_strategy == "service_creation":
        return merge_service_creation_results(results)

    elif merge_strategy == "file_read":
        return merge_file_read_results(results)

    elif merge_strategy == "search":
        return merge_search_results(results)

    elif merge_strategy == "test":
        return merge_test_results(results)

    elif merge_strategy == "build":
        return merge_build_results(results)

    elif merge_strategy == "deployment":
        return merge_deployment_results(results)

    else:
        # Default: simple aggregation
        return {
            "status": "completed",
            "task_count": len(results),
            "results": results
        }


def merge_service_creation_results(results):
    """
    Merge results from creating multiple services.
    """

    all_succeeded = all(r.get("status") == "success" for r in results.values())

    created_services = []
    created_files = []
    errors = []

    for task_id, result in results.items():
        if result.get("status") == "success":
            created_services.append(result.get("service_name"))
            created_files.extend(result.get("files", []))
        else:
            errors.append({
                "task_id": task_id,
                "error": result.get("error")
            })

    return {
        "status": "success" if all_succeeded else "partial",
        "created_services": created_services,
        "created_files": created_files,
        "total_files": len(created_files),
        "errors": errors if errors else None
    }


def merge_test_results(results):
    """
    Merge results from running tests across multiple services.
    """

    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    test_details = []

    for task_id, result in results.items():
        service_tests = result.get("test_count", 0)
        service_passed = result.get("passed", 0)
        service_failed = result.get("failed", 0)

        total_tests += service_tests
        passed_tests += service_passed
        failed_tests += service_failed

        test_details.append({
            "service": result.get("service_name"),
            "tests": service_tests,
            "passed": service_passed,
            "failed": service_failed
        })

    all_passed = failed_tests == 0

    return {
        "status": "success" if all_passed else "failed",
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "pass_rate": f"{(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%",
        "details": test_details
    }
```

---

## 🔄 LIFECYCLE MANAGEMENT

### Complete Lifecycle Flow

```
1. ANALYSIS
   ↓
   Detect parallelizable tasks
   Group by dependencies

2. SKILL/AGENT CHECK
   ↓
   Check existing skills/agents
   Create temporary if needed

3. PARALLEL LAUNCH
   ↓
   Launch all tasks in parallel
   Monitor progress

4. RESULT COLLECTION
   ↓
   Collect all results
   Check for failures

5. RESULT MERGING
   ↓
   Merge results intelligently
   Generate summary

6. CLEANUP DECISION
   ↓
   Evaluate temp resources
   Keep useful, delete unused

7. FINAL REPORT
   ↓
   Show merged results
   Show time savings
```

### Lifecycle Manager

```python
# parallel-lifecycle-manager.py

class ParallelExecutionLifecycle:
    def __init__(self, tasks):
        self.tasks = tasks
        self.parallel_groups = []
        self.temp_resources = []
        self.results = {}

    def run(self):
        """
        Execute complete parallel execution lifecycle.
        """

        print("🚀 PARALLEL EXECUTION LIFECYCLE STARTED")
        print("=" * 80)

        # Phase 1: Analysis
        print("\n📊 Phase 1: Task Analysis")
        self.parallel_groups = self.analyze_tasks()
        print(f"   ✅ Identified {len(self.parallel_groups)} parallel groups")

        # Phase 2: Resource Check
        print("\n🔍 Phase 2: Skill/Agent Check")
        self.check_and_create_resources()

        # Phase 3: Parallel Execution
        print("\n⚡ Phase 3: Parallel Execution")
        start_time = time.time()
        self.execute_parallel()
        execution_time = time.time() - start_time

        # Phase 4: Result Collection
        print("\n📥 Phase 4: Result Collection")
        self.collect_results()

        # Phase 5: Result Merging
        print("\n🔄 Phase 5: Result Merging")
        merged_result = self.merge_results()

        # Phase 6: Cleanup Decision
        print("\n🗑️ Phase 6: Cleanup Decision")
        self.cleanup_temp_resources()

        # Phase 7: Final Report
        print("\n📋 Phase 7: Final Report")
        self.generate_report(merged_result, execution_time)

        print("=" * 80)
        print("✅ PARALLEL EXECUTION LIFECYCLE COMPLETED")

        return merged_result

    def analyze_tasks(self):
        """Analyze tasks for parallelization opportunities."""
        from parallel_task_analyzer import analyze_tasks_for_parallelization
        return analyze_tasks_for_parallelization(self.tasks)

    def check_and_create_resources(self):
        """Check for existing skills/agents, create temporary if needed."""
        for group in self.parallel_groups:
            for task in group:
                required_skill = task.get("required_skill")

                if required_skill and not skill_exists(required_skill):
                    # Create temporary skill
                    temp_skill = create_temporary_skill(
                        name=required_skill,
                        description=task.get("skill_description"),
                        capabilities=task.get("skill_capabilities")
                    )
                    self.temp_resources.append(("skill", required_skill))
                    print(f"   ✅ Created temp skill: {required_skill}")

    def execute_parallel(self):
        """Execute tasks in parallel."""
        for group in self.parallel_groups:
            execute_parallel_tasks(group)

    def collect_results(self):
        """Collect results from all parallel executions."""
        task_ids = [task["id"] for group in self.parallel_groups for task in group]
        self.results = collect_parallel_results(task_ids)
        print(f"   ✅ Collected {len(self.results)} results")

    def merge_results(self):
        """Merge results intelligently."""
        merge_strategy = determine_merge_strategy(self.tasks)
        merged = merge_parallel_results(self.results, merge_strategy)
        print(f"   ✅ Merged results using strategy: {merge_strategy}")
        return merged

    def cleanup_temp_resources(self):
        """Cleanup temporary resources."""
        for resource_type, resource_name in self.temp_resources:
            decision, reason = decide_keep_or_delete(resource_name, resource_type)

            if decision == "delete":
                if resource_type == "skill":
                    delete_temp_skill(resource_name)
                else:
                    delete_temp_agent(resource_name)
                print(f"   🗑️ Deleted temp {resource_type}: {resource_name} - {reason}")
            else:
                print(f"   ✅ Keeping temp {resource_type}: {resource_name} - {reason}")

    def generate_report(self, merged_result, execution_time):
        """Generate final execution report."""
        task_count = len([task for group in self.parallel_groups for task in group])
        sequential_time_estimate = task_count * 60  # Assume 60s per task
        time_saved = sequential_time_estimate - execution_time

        print(f"""
╔════════════════════════════════════════════════════════════════════════════╗
║                      PARALLEL EXECUTION REPORT                             ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Tasks Executed:          {task_count:>3}                                            ║
║ Parallel Groups:         {len(self.parallel_groups):>3}                                            ║
║ Execution Time:          {execution_time:.1f}s                                       ║
║ Sequential Estimate:     {sequential_time_estimate:.1f}s                                       ║
║ Time Saved:              {time_saved:.1f}s ({(time_saved/sequential_time_estimate*100):.0f}%)                               ║
║ Temp Resources Created:  {len(self.temp_resources):>3}                                            ║
║ Temp Resources Kept:     {sum(1 for r in self.temp_resources if decide_keep_or_delete(r[1], r[0])[0] == "keep"):>3}                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
        """)
```

---

## 🔗 EXECUTION FLOW INTEGRATION

### Updated Execution Flow (with Parallel Execution)

```
STEP 0: Prompt Generation (MANDATORY)
   ↓
STEP 1: Task Breakdown (MANDATORY)
   ↓
STEP 2: Auto Plan Mode (MANDATORY)
   ↓
STEP 3: Context Check
   ↓
STEP 4: Model Selection
   ↓
STEP 5: Skill/Agent Selection
   ↓
STEP 6: Tool Optimization
   ↓
**STEP 7: PARALLEL EXECUTION ANALYSIS** (NEW!)
   ↓
   → Analyze tasks for parallelization
   → If parallelizable: Launch parallel execution
   → If sequential: Continue normal flow
   ↓
STEP 8: Execute Tasks (Parallel or Sequential)
   ↓
STEP 9: Result Merging (if parallel)
   ↓
STEP 10: Cleanup Temp Resources
   ↓
STEP 11: Session Save
   ↓
STEP 12: Git Auto-Commit
```

### Integration Script

```python
# integrate-parallel-execution.py

def integrate_parallel_execution_into_flow(tasks, prompt):
    """
    Integrate parallel execution into existing execution flow.

    This runs AFTER:
    - Task breakdown (STEP 1)
    - Model selection (STEP 4)
    - Skill/agent selection (STEP 5)

    This runs BEFORE:
    - Task execution (STEP 8)
    """

    print("🔍 STEP 7: Analyzing for parallel execution opportunities...")

    # Analyze tasks
    parallel_groups = analyze_tasks_for_parallelization(tasks)

    if len(parallel_groups) > 1 or len(parallel_groups[0]) > 1:
        # Parallel execution possible
        total_tasks = sum(len(group) for group in parallel_groups)
        print(f"✅ Found {total_tasks} tasks in {len(parallel_groups)} parallel groups")
        print(f"⚡ Estimated speedup: {total_tasks / len(parallel_groups):.1f}x")

        # Run parallel lifecycle
        lifecycle = ParallelExecutionLifecycle(tasks)
        result = lifecycle.run()

        return result, "parallel"

    else:
        # No parallelization possible
        print("ℹ️ No parallel execution opportunities found")
        print("   Proceeding with sequential execution")

        return None, "sequential"
```

---

## 📜 IMPLEMENTATION SCRIPTS

### Main Parallel Executor

**Location:** `~/.claude/memory/scripts/parallel-executor.py`

```python
#!/usr/bin/env python3
"""
Parallel Task Executor
Executes multiple tasks in parallel using subagents
"""

import sys
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

def execute_task_with_subagent(task_id, subagent_type, prompt, background=False):
    """Execute a single task using a subagent."""

    # Prepare task execution
    task_start = datetime.now()

    print(f"🚀 Launching Task {task_id} with {subagent_type} agent...")

    # Build subagent command
    cmd = [
        "claude",
        "task",
        f"--subagent={subagent_type}",
        f"--prompt={prompt}"
    ]

    if background:
        cmd.append("--background")

    try:
        # Execute
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        task_end = datetime.now()
        duration = (task_end - task_start).total_seconds()

        # Save result
        result_data = {
            "task_id": task_id,
            "subagent": subagent_type,
            "status": "success" if result.returncode == 0 else "failed",
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "duration": duration,
            "start_time": task_start.isoformat(),
            "end_time": task_end.isoformat()
        }

        # Save to file
        result_file = Path.home() / ".claude/memory/temp/parallel-results" / f"{task_id}.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)

        with open(result_file, 'w') as f:
            json.dump(result_data, f, indent=2)

        if result.returncode == 0:
            print(f"✅ Task {task_id} completed in {duration:.1f}s")
        else:
            print(f"❌ Task {task_id} failed after {duration:.1f}s")

        return result.returncode

    except subprocess.TimeoutExpired:
        print(f"⏱️ Task {task_id} timed out after 10 minutes")
        return 1

    except Exception as e:
        print(f"❌ Task {task_id} error: {str(e)}")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Execute task with subagent")
    parser.add_argument("--task-id", required=True, help="Task ID")
    parser.add_argument("--subagent", required=True, help="Subagent type")
    parser.add_argument("--prompt", required=True, help="Task prompt")
    parser.add_argument("--background", action="store_true", help="Run in background")

    args = parser.parse_args()

    exit_code = execute_task_with_subagent(
        args.task_id,
        args.subagent,
        args.prompt,
        args.background
    )

    sys.exit(exit_code)
```

### Parallel Task Analyzer

**Location:** `~/.claude/memory/scripts/parallel-task-analyzer.py`

```python
#!/usr/bin/env python3
"""
Parallel Task Analyzer
Analyzes tasks and identifies parallelization opportunities
"""

import json
from typing import List, Dict, Tuple

def build_dependency_graph(tasks: List[Dict]) -> Dict:
    """Build dependency graph from tasks."""
    graph = {}

    for task in tasks:
        task_id = task['id']
        dependencies = task.get('blockedBy', [])
        graph[task_id] = dependencies

    return graph


def has_dependencies(task: Dict, current_group: List[Dict]) -> bool:
    """Check if task has dependencies on tasks in current group."""
    task_deps = set(task.get('blockedBy', []))
    group_ids = set(t['id'] for t in current_group)

    return bool(task_deps & group_ids)


def analyze_tasks_for_parallelization(tasks: List[Dict]) -> List[List[Dict]]:
    """
    Analyze tasks and group them for parallel execution.

    Returns:
        List of task groups, where each group can run in parallel
    """

    if not tasks:
        return []

    # Sort tasks by dependencies (topological sort)
    sorted_tasks = topological_sort(tasks)

    # Group tasks by wave (tasks with no dependencies on each other)
    parallel_groups = []
    current_group = []
    completed_tasks = set()

    for task in sorted_tasks:
        task_deps = set(task.get('blockedBy', []))

        # Can this task run with current group?
        if task_deps.issubset(completed_tasks):
            # Check if it depends on any task in current group
            current_group_ids = set(t['id'] for t in current_group)

            if not task_deps & current_group_ids:
                # No dependency on current group - can run in parallel
                current_group.append(task)
            else:
                # Depends on current group - start new group
                if current_group:
                    parallel_groups.append(current_group)
                    completed_tasks.update(t['id'] for t in current_group)
                current_group = [task]
        else:
            # Dependencies not met - shouldn't happen after topological sort
            # Start new group
            if current_group:
                parallel_groups.append(current_group)
                completed_tasks.update(t['id'] for t in current_group)
            current_group = [task]

    # Add last group
    if current_group:
        parallel_groups.append(current_group)

    return parallel_groups


def topological_sort(tasks: List[Dict]) -> List[Dict]:
    """Topologically sort tasks by dependencies."""
    graph = build_dependency_graph(tasks)
    task_map = {t['id']: t for t in tasks}

    visited = set()
    result = []

    def visit(task_id):
        if task_id in visited:
            return

        visited.add(task_id)

        # Visit dependencies first
        for dep in graph.get(task_id, []):
            visit(dep)

        result.append(task_map[task_id])

    for task in tasks:
        visit(task['id'])

    return result


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Analyze tasks for parallelization")
    parser.add_argument("--tasks-file", required=True, help="JSON file with tasks")

    args = parser.parse_args()

    # Load tasks
    with open(args.tasks_file, 'r') as f:
        tasks = json.load(f)

    # Analyze
    parallel_groups = analyze_tasks_for_parallelization(tasks)

    # Output
    print(f"📊 Parallel Analysis Results:")
    print(f"   Total tasks: {len(tasks)}")
    print(f"   Parallel groups: {len(parallel_groups)}")
    print(f"   Estimated speedup: {len(tasks) / len(parallel_groups):.1f}x")
    print()

    for i, group in enumerate(parallel_groups, 1):
        print(f"Group {i} ({len(group)} tasks in parallel):")
        for task in group:
            print(f"  - Task {task['id']}: {task.get('subject', 'No subject')}")
        print()
```

---

## 📚 EXAMPLES

### Example 1: Creating Multiple Microservices

**Scenario:** Create auth-service, user-service, and product-service in parallel

```bash
# Without Parallel Execution (Sequential)
# Time: 3 services × 5 minutes = 15 minutes

Task 1: Create auth-service   (5 min)
   ↓
Task 2: Create user-service   (5 min)
   ↓
Task 3: Create product-service (5 min)

Total: 15 minutes
```

```bash
# With Parallel Execution
# Time: ~5 minutes (all in parallel)

[Task 1: auth-service, Task 2: user-service, Task 3: product-service]

Total: 5 minutes (3x speedup!)
```

**Implementation:**

```python
# Tasks definition
tasks = [
    {
        "id": "task-1",
        "type": "service_creation",
        "subject": "Create auth-service",
        "prompt": "Create Spring Boot auth-service with JWT authentication",
        "blockedBy": [],
        "required_skill": "java-spring-boot-microservices"
    },
    {
        "id": "task-2",
        "type": "service_creation",
        "subject": "Create user-service",
        "prompt": "Create Spring Boot user-service with user management",
        "blockedBy": [],
        "required_skill": "java-spring-boot-microservices"
    },
    {
        "id": "task-3",
        "type": "service_creation",
        "subject": "Create product-service",
        "prompt": "Create Spring Boot product-service with product catalog",
        "blockedBy": [],
        "required_skill": "java-spring-boot-microservices"
    }
]

# Execute in parallel
lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Output:
# ✅ Created 3 services in parallel
# ⚡ Time: 5.2 minutes (vs 15 minutes sequential)
# 📊 Speedup: 2.9x
```

### Example 2: Running Tests Across Multiple Services

**Scenario:** Run tests in 5 microservices simultaneously

```bash
# Without Parallel Execution
# Time: 5 services × 2 minutes = 10 minutes

# With Parallel Execution
# Time: ~2 minutes (all in parallel)
# Speedup: 5x
```

**Implementation:**

```python
tasks = [
    {
        "id": f"test-{service}",
        "type": "testing",
        "subject": f"Run tests in {service}",
        "prompt": f"cd backend/{service} && mvn test",
        "blockedBy": []
    }
    for service in ["auth-service", "user-service", "product-service",
                    "order-service", "notification-service"]
]

# Execute
lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Merged result:
# {
#   "status": "success",
#   "total_tests": 147,
#   "passed": 147,
#   "failed": 0,
#   "pass_rate": "100%",
#   "execution_time": "2.1 minutes"
# }
```

### Example 3: Creating Temporary Skill for GraphQL Migration

**Scenario:** Migrate 3 REST services to GraphQL (requires specialized knowledge)

```python
# Step 1: Detect need for temporary skill
task = {
    "type": "migration",
    "subject": "Migrate REST APIs to GraphQL",
    "required_skill": "graphql-migration-expert"  # Doesn't exist!
}

# Step 2: Auto-create temporary skill
print("🔍 Required skill 'graphql-migration-expert' not found")
print("✅ Creating temporary skill...")

create_temporary_skill(
    name="graphql-migration-expert",
    description="Expert in migrating REST APIs to GraphQL",
    capabilities=[
        "Analyze REST endpoints and create GraphQL schema",
        "Generate resolvers from REST controllers",
        "Handle authentication in GraphQL context",
        "Optimize GraphQL queries",
        "Add GraphQL subscriptions"
    ]
)

# Step 3: Use temporary skill for all 3 services in parallel
tasks = [
    {
        "id": f"migrate-{service}",
        "type": "migration",
        "subject": f"Migrate {service} to GraphQL",
        "prompt": f"Migrate {service} REST API to GraphQL",
        "required_skill": "graphql-migration-expert",
        "blockedBy": []
    }
    for service in ["user-service", "product-service", "order-service"]
]

lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Step 4: Decide keep or delete
# After execution:
# - Usage count: 3 times
# - Last used: Just now
# - User feedback: None yet

decision, reason = decide_keep_or_delete("graphql-migration-expert", "skill")
# Decision: "keep" (used 3 times - shows value)

print(f"✅ Keeping temp skill: graphql-migration-expert - {reason}")
```

### Example 4: Multi-Repository Git Operations

**Scenario:** Push changes to 4 microservice repositories simultaneously

```python
tasks = [
    {
        "id": f"git-push-{service}",
        "type": "git_operation",
        "subject": f"Push changes to {service}",
        "prompt": f"cd backend/{service} && git add . && git commit -m 'Update dependencies' && git push",
        "blockedBy": []
    }
    for service in ["auth-service", "user-service", "product-service", "order-service"]
]

# Execute in parallel
lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Merged result:
# {
#   "status": "success",
#   "pushed_repos": 4,
#   "total_commits": 4,
#   "execution_time": "3.2s"
# }
# vs Sequential: 12.8s (4x speedup)
```

### Example 5: Temporary Agent for Complex Orchestration

**Scenario:** Deploy 5 services to Kubernetes with health checks (needs orchestration)

```python
# Step 1: Create temporary orchestrator agent
create_temporary_agent(
    name="k8s-deployment-orchestrator",
    description="Orchestrates complex Kubernetes deployments with health checks",
    tools=["Bash", "Read", "Write", "Grep"]
)

# Step 2: Define parallel deployment tasks
tasks = [
    {
        "id": f"deploy-{service}",
        "type": "deployment",
        "subject": f"Deploy {service} to K8s",
        "prompt": f"Deploy {service} to Kubernetes and verify health",
        "required_agent": "k8s-deployment-orchestrator",
        "blockedBy": []
    }
    for service in ["auth-service", "user-service", "product-service",
                    "order-service", "notification-service"]
]

# Step 3: Execute
lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Step 4: Cleanup decision
# - Usage count: 1 time
# - Last used: Just now
# - Task type: Deployment (common operation)
# - Days since last use: 0

decision, reason = decide_keep_or_delete("k8s-deployment-orchestrator", "agent")
# Decision: "keep" (Recently used - might be needed again)

print(f"✅ Keeping temp agent: k8s-deployment-orchestrator - {reason}")

# After 30 days with no use:
# Decision: "delete" (Not used in 30 days)
```

### Example 6: Intelligent Result Merging

**Scenario:** Search for configuration files across 5 services

```python
# Execute parallel searches
tasks = [
    {
        "id": f"search-config-{service}",
        "type": "search",
        "subject": f"Search for config in {service}",
        "prompt": f"Find all application.yml files in {service}",
        "blockedBy": []
    }
    for service in ["auth-service", "user-service", "product-service",
                    "order-service", "notification-service"]
]

lifecycle = ParallelExecutionLifecycle(tasks)
result = lifecycle.run()

# Merged result with deduplication and ranking:
# {
#   "status": "success",
#   "total_files_found": 12,
#   "unique_files": 8,
#   "duplicates_removed": 4,
#   "files_by_service": {
#     "auth-service": ["application.yml", "application-prod.yml"],
#     "user-service": ["application.yml", "application-dev.yml"],
#     ...
#   },
#   "execution_time": "1.2s"
# }
```

---

## 🎯 ENFORCEMENT RULES

### Mandatory Application

**I MUST apply parallel execution when:**

1. ✅ **3+ independent tasks** detected
2. ✅ **No blocking dependencies** between tasks
3. ✅ **Same task type** (e.g., all service creation, all tests)
4. ✅ **Estimated time savings >50%**

### Automatic Detection

**Script:** `~/.claude/memory/scripts/auto-parallel-detector.py`

```python
def should_use_parallel_execution(tasks):
    """
    Automatically detect if parallel execution should be used.

    Returns:
        (should_use: bool, reason: str, estimated_speedup: float)
    """

    # Check task count
    if len(tasks) < 3:
        return False, "Less than 3 tasks", 1.0

    # Analyze dependencies
    parallel_groups = analyze_tasks_for_parallelization(tasks)

    if len(parallel_groups) == 1:
        return False, "All tasks have dependencies", 1.0

    # Calculate speedup
    estimated_speedup = len(tasks) / len(parallel_groups)

    if estimated_speedup < 1.5:
        return False, f"Speedup too low: {estimated_speedup:.1f}x", estimated_speedup

    # Check if same task type (works better in parallel)
    task_types = set(t.get('type') for t in tasks)

    if len(task_types) == 1:
        # Homogeneous tasks - excellent for parallel
        return True, f"Homogeneous tasks, speedup: {estimated_speedup:.1f}x", estimated_speedup

    # Mixed task types - still good if speedup is significant
    if estimated_speedup >= 2.0:
        return True, f"Significant speedup: {estimated_speedup:.1f}x", estimated_speedup

    return False, "Mixed tasks with low speedup", estimated_speedup
```

### Integration with Task Breakdown

**After STEP 1 (Task Breakdown), automatically check for parallel opportunities:**

```python
# In automatic-task-breakdown-policy.md execution

# After creating all tasks
tasks = load_all_tasks()

# Check for parallel execution
should_parallel, reason, speedup = should_use_parallel_execution(tasks)

if should_parallel:
    print(f"⚡ PARALLEL EXECUTION RECOMMENDED")
    print(f"   Reason: {reason}")
    print(f"   Estimated speedup: {speedup:.1f}x")
    print(f"   Proceeding with parallel execution...")

    # Execute in parallel
    lifecycle = ParallelExecutionLifecycle(tasks)
    result = lifecycle.run()
else:
    print(f"ℹ️ Sequential execution recommended")
    print(f"   Reason: {reason}")
    # Continue with normal flow
```

---

## 📊 MONITORING & METRICS

### Metrics to Track

| Metric | Description |
|--------|-------------|
| **Parallel Execution Rate** | % of tasks executed in parallel |
| **Average Speedup** | Average time saved by parallelization |
| **Temp Resources Created** | Number of temporary skills/agents created |
| **Temp Resources Kept** | % of temp resources kept vs deleted |
| **Merge Success Rate** | % of parallel executions with successful merges |
| **Failure Rate** | % of parallel tasks that failed |

### Dashboard

**Location:** `~/.claude/memory/logs/parallel-execution-stats.json`

```json
{
    "total_parallel_executions": 47,
    "total_tasks_parallelized": 183,
    "average_speedup": 3.2,
    "total_time_saved_minutes": 342,
    "temp_skills_created": 12,
    "temp_skills_kept": 5,
    "temp_agents_created": 8,
    "temp_agents_kept": 3,
    "merge_success_rate": 0.96,
    "failure_rate": 0.04
}
```

---

## 🔧 CONFIGURATION

### Parallel Execution Config

**Location:** `~/.claude/memory/config/parallel-execution-config.json`

```json
{
    "enabled": true,
    "min_tasks_for_parallel": 3,
    "min_speedup_threshold": 1.5,
    "max_parallel_tasks": 10,
    "task_timeout_seconds": 600,
    "auto_create_temp_resources": true,
    "auto_cleanup_temp_resources": true,
    "temp_resource_retention_days": 30,
    "merge_strategies": {
        "service_creation": "aggregate_status",
        "testing": "aggregate_results",
        "file_read": "concatenate",
        "search": "deduplicate_rank",
        "deployment": "verify_all"
    },
    "monitoring": {
        "enabled": true,
        "log_file": "~/.claude/memory/logs/parallel-execution.log",
        "stats_file": "~/.claude/memory/logs/parallel-execution-stats.json"
    }
}
```

---

## 🚨 ERROR HANDLING

### Failure Scenarios

| Failure | Handling Strategy |
|---------|------------------|
| **Single Task Fails** | Continue others, report at end |
| **All Tasks Fail** | Abort, report all errors |
| **Timeout** | Kill task, mark as failed |
| **Temp Resource Creation Fails** | Fall back to existing skills/agents |
| **Result Merge Fails** | Return individual results |

### Retry Strategy

```python
def execute_with_retry(task, max_retries=3):
    """Execute task with automatic retry on failure."""

    for attempt in range(1, max_retries + 1):
        try:
            result = execute_task(task)

            if result.get('status') == 'success':
                return result

            print(f"⚠️ Task {task['id']} failed, attempt {attempt}/{max_retries}")

        except Exception as e:
            print(f"❌ Task {task['id']} error: {str(e)}")

            if attempt == max_retries:
                raise

        time.sleep(2 ** attempt)  # Exponential backoff

    return {"status": "failed", "error": "Max retries exceeded"}
```

---

## 📖 REFERENCES

### Related Policies

- **automatic-task-breakdown-policy.md** - Creates tasks for parallelization
- **auto-skill-agent-selection-policy.md** - Selects skills/agents (can trigger temp creation)
- **intelligent-model-selection-policy.md** - Selects model for parallel tasks
- **task-progress-tracking-policy.md** - Tracks progress of parallel tasks

### Related Scripts

- `parallel-executor.py` - Main parallel execution engine
- `parallel-task-analyzer.py` - Analyzes parallelization opportunities
- `parallel-lifecycle-manager.py` - Manages complete lifecycle
- `temp-skill-agent-creator.py` - Creates temporary resources
- `temp-resource-manager.py` - Manages temporary resource lifecycle
- `result-merger.py` - Merges results from parallel executions

---

## 📝 CHANGELOG

- **v1.0.0** (2026-02-16): Initial release
  - Parallel task execution with subagents
  - Temporary skill/agent creation
  - Intelligent result merging
  - Automatic cleanup
  - Complete lifecycle management

---

## ✅ SUCCESS CRITERIA

**This policy is successful when:**

1. ✅ Tasks are automatically analyzed for parallelization
2. ✅ Independent tasks execute in parallel (3x+ speedup)
3. ✅ Temporary skills/agents are created when needed
4. ✅ Results are intelligently merged
5. ✅ Temporary resources are cleaned up appropriately
6. ✅ Overall execution time reduced by 50%+
7. ✅ Zero increase in failure rate

---

**VERSION:** 1.0.0
**STATUS:** 🟢 ACTIVE (MANDATORY)
**LAST UPDATED:** 2026-02-16
**MAINTAINER:** Claude Memory System
**LOCATION:** `~/.claude/memory/03-execution-system/parallel-execution-policy.md`
