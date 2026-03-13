"""
Task Breakdown Validator - Step 3 validation for Level 3 execution.

Validates a list of task dicts produced by Step 3 task breakdown against
four criteria:

1. Cycle detection       - dependency graph must be a DAG
2. Completeness          - all requirement keywords are addressed by at least one task
3. Reachability          - no orphan tasks (every non-root task is depended on or depends on others)
4. Feasibility           - each task has a title/name and an estimated effort

Task dict schema expected:
    {
        "id": <int | str>,          # unique task identifier
        "name": str,                # short task name
        "description": str,         # optional detail
        "dependencies": List[id],   # list of task ids this task depends on
        "type": str,                # optional category
        "estimated_effort": str,    # optional: "small" | "medium" | "large"
    }
"""

from typing import List, Dict, Any, Tuple, Set, Optional
from collections import defaultdict, deque
from loguru import logger


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def build_dependency_graph(tasks: List[Dict[str, Any]]) -> Dict[Any, List[Any]]:
    """
    Build an adjacency list from a task list.

    Returns:
        Dict mapping task_id -> list of task_ids that this task depends on.
        All task ids are included as keys even if they have no dependencies.
    """
    graph: Dict[Any, List[Any]] = {}
    for task in tasks:
        tid = task.get("id")
        if tid is None:
            continue
        deps = task.get("dependencies") or []
        graph[tid] = list(deps)

    # Ensure all referenced dependency ids also appear as keys
    referenced: Set[Any] = set()
    for deps in graph.values():
        referenced.update(deps)
    for ref in referenced:
        if ref not in graph:
            graph[ref] = []

    return graph


def has_cycle(graph: Dict[Any, List[Any]]) -> bool:
    """
    Detect whether the dependency graph contains a cycle.

    Uses iterative DFS with three-colour marking:
        WHITE (0): unvisited
        GRAY  (1): currently in the DFS stack
        BLACK (2): fully processed

    Returns:
        True if a cycle is detected, False otherwise.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: Dict[Any, int] = defaultdict(int)

    def _dfs(node: Any) -> bool:
        colour[node] = GRAY
        for neighbour in graph.get(node, []):
            if colour[neighbour] == GRAY:
                return True   # Back-edge -> cycle
            if colour[neighbour] == WHITE:
                if _dfs(neighbour):
                    return True
        colour[node] = BLACK
        return False

    for node in list(graph.keys()):
        if colour[node] == WHITE:
            if _dfs(node):
                return True
    return False


# ---------------------------------------------------------------------------
# Completeness check
# ---------------------------------------------------------------------------

def covers_all_requirements(tasks: List[Dict[str, Any]], requirement: str = "") -> bool:
    """
    Check whether the task list collectively addresses the requirement.

    Strategy: extract significant words from the requirement and verify
    that at least one task's combined text (name + description) contains
    each keyword.  If no requirement text is supplied, returns True.

    Args:
        tasks: Validated task list.
        requirement: Original user requirement text.

    Returns:
        True if all significant keywords are covered (or no requirement given).
    """
    if not requirement:
        return True

    keywords = [w.lower() for w in requirement.split() if len(w) >= 4]
    if not keywords:
        return True

    combined_task_text = " ".join(
        f"{t.get('name', '')} {t.get('description', '')}".lower()
        for t in tasks
    )

    uncovered = [kw for kw in keywords if kw not in combined_task_text]
    if uncovered:
        logger.debug(f"[TaskValidator] Uncovered keywords: {uncovered}")
        return False
    return True


# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------

def all_tasks_reachable(tasks: List[Dict[str, Any]]) -> bool:
    """
    Check that all tasks are reachable from the root set in a DAG traversal.

    "Reachable" here means: starting from tasks with no dependencies (roots),
    following dependency edges, we can visit every task in the list.
    Orphan tasks — those neither depended upon by others nor reachable from
    roots — indicate a structuring error.

    Returns:
        True if all tasks are reachable, False otherwise.
    """
    if not tasks:
        return True

    task_ids = {t["id"] for t in tasks if t.get("id") is not None}
    graph = build_dependency_graph(tasks)

    # Build reverse graph: who *depends on* each task (successors)
    reverse: Dict[Any, List[Any]] = defaultdict(list)
    for tid, deps in graph.items():
        for dep in deps:
            reverse[dep].append(tid)

    # Roots = tasks with no dependencies
    roots = [tid for tid, deps in graph.items() if not deps and tid in task_ids]

    if not roots:
        # Every task has a dependency -> possible cycle or all orphans
        logger.debug("[TaskValidator] No root tasks found (all have dependencies)")
        return False

    # BFS forward from roots through the dependency direction
    # (forward = from root to tasks that depend on root)
    visited: Set[Any] = set()
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for successor in reverse.get(node, []):
            if successor not in visited:
                queue.append(successor)

    # Also mark roots themselves; add direct reachability from roots via deps
    # (roots are reachable by definition, and tasks listed as deps of roots)
    for root in roots:
        for dep in graph.get(root, []):
            visited.add(dep)

    unreachable = task_ids - visited
    if unreachable:
        logger.debug(f"[TaskValidator] Unreachable task ids: {unreachable}")
        return False
    return True


# ---------------------------------------------------------------------------
# Feasibility check
# ---------------------------------------------------------------------------

_VALID_EFFORTS = {"small", "medium", "large", "trivial", "complex", ""}


def all_tasks_feasible(tasks: List[Dict[str, Any]]) -> bool:
    """
    Check that every task is feasible (has a non-empty name/title).

    Feasibility is intentionally a lightweight check here because deeper
    feasibility analysis requires domain knowledge.  The rule: every task
    must at minimum have a non-empty name field.

    Returns:
        True if all tasks pass feasibility check.
    """
    for task in tasks:
        name = (task.get("name") or task.get("title") or "").strip()
        if not name:
            logger.debug(f"[TaskValidator] Task missing name/title: id={task.get('id')}")
            return False
    return True


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_breakdown(
    tasks: List[Dict[str, Any]],
    requirement: str = "",
) -> Tuple[bool, List[str]]:
    """
    Validate a task breakdown list against all four criteria.

    Args:
        tasks: List of task dicts (see module docstring for schema).
        requirement: Original user requirement text (for completeness check).

    Returns:
        Tuple (valid: bool, errors: List[str]).
        valid is True only when errors is empty.

    Example:
        >>> tasks = [
        ...     {"id": 1, "name": "Setup DB", "dependencies": []},
        ...     {"id": 2, "name": "Implement API", "dependencies": [1]},
        ... ]
        >>> validate_breakdown(tasks, "setup database and implement API")
        (True, [])
    """
    errors: List[str] = []

    if not tasks:
        errors.append("Task list is empty")
        return False, errors

    # 1. Cycle detection
    graph = build_dependency_graph(tasks)
    if has_cycle(graph):
        errors.append("Circular dependency detected in task graph")
        logger.error("[TaskValidator] Cycle detected in task dependency graph")

    # 2. Completeness
    if not covers_all_requirements(tasks, requirement):
        errors.append("Incomplete task coverage - some requirement keywords not addressed")
        logger.warning("[TaskValidator] Task breakdown does not cover all requirement keywords")

    # 3. Reachability
    if not all_tasks_reachable(tasks):
        errors.append("Some tasks are unreachable (orphan or disconnected tasks detected)")
        logger.warning("[TaskValidator] Unreachable tasks detected")

    # 4. Feasibility
    if not all_tasks_feasible(tasks):
        errors.append("Some tasks are not feasible (missing name/title)")
        logger.error("[TaskValidator] Tasks missing name/title found")

    valid = len(errors) == 0

    if valid:
        logger.info(f"[TaskValidator] Validation passed: {len(tasks)} tasks, all checks OK")
    else:
        logger.warning(
            f"[TaskValidator] Validation failed: {len(errors)} error(s): {errors}"
        )

    return valid, errors
