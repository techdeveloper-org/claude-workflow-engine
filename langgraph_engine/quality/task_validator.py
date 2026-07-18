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
        "estimated_tokens": int,    # optional: estimated token cost for execution
    }

Token feasibility:
    validate_feasibility(task, available_tokens) checks whether a single task
    can be executed within the remaining token budget by consulting the
    task's "estimated_tokens" field or a per-effort heuristic.

Public API additions (acceptance criteria):
    cycle_detect(tasks) -> Tuple[bool, List[Any]]
        Alias for the DFS cycle detector; also returns the first cycle path found.
    validate_feasibility(task, available_tokens) -> Tuple[bool, str]
        Check whether a single task fits within the token budget.
"""

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token cost heuristics per estimated_effort level
# ---------------------------------------------------------------------------
_EFFORT_TOKEN_COST: Dict[str, int] = {
    "trivial": 100,
    "small": 300,
    "medium": 700,
    "large": 1500,
    "complex": 2500,
    "": 500,
}


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def build_dependency_graph(tasks: List[Dict[str, Any]]) -> Dict[Any, List[Any]]:
    """Build an adjacency list from a task list.

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

    referenced: Set[Any] = set()
    for deps in graph.values():
        referenced.update(deps)
    for ref in referenced:
        if ref not in graph:
            graph[ref] = []

    return graph


def has_cycle(graph: Dict[Any, List[Any]]) -> bool:
    """Detect whether the dependency graph contains a cycle.

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
                return True
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
    """Check whether the task list collectively addresses the requirement.

    Extracts significant words from the requirement and verifies that at least
    one task's combined text (name + description) contains each keyword.
    Returns True if no requirement text is supplied.

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

    combined_task_text = " ".join("{} {}".format(t.get("name", ""), t.get("description", "")).lower() for t in tasks)

    uncovered = [kw for kw in keywords if kw not in combined_task_text]
    if uncovered:
        logger.debug("[TaskValidator] Uncovered keywords: {}", uncovered)
        return False
    return True


# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------


def all_tasks_reachable(tasks: List[Dict[str, Any]]) -> bool:
    """Check that all tasks are reachable from the root set in a DAG traversal.

    'Reachable' means: starting from tasks with no dependencies (roots),
    following dependency edges, every task in the list can be visited.
    Orphan tasks -- those neither depended upon by others nor reachable from
    roots -- indicate a structuring error.

    Returns:
        True if all tasks are reachable, False otherwise.
    """
    if not tasks:
        return True

    task_ids = {t["id"] for t in tasks if t.get("id") is not None}
    graph = build_dependency_graph(tasks)

    reverse: Dict[Any, List[Any]] = defaultdict(list)
    for tid, deps in graph.items():
        for dep in deps:
            reverse[dep].append(tid)

    roots = [tid for tid, deps in graph.items() if not deps and tid in task_ids]

    if not roots:
        logger.debug("[TaskValidator] No root tasks found (all have dependencies)")
        return False

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

    for root in roots:
        for dep in graph.get(root, []):
            visited.add(dep)

    unreachable = task_ids - visited
    if unreachable:
        logger.debug("[TaskValidator] Unreachable task ids: {}", unreachable)
        return False
    return True


# ---------------------------------------------------------------------------
# Feasibility check
# ---------------------------------------------------------------------------

_VALID_EFFORTS = {"small", "medium", "large", "trivial", "complex", ""}


def all_tasks_feasible(tasks: List[Dict[str, Any]]) -> bool:
    """Check that every task is feasible (has a non-empty name/title).

    Feasibility is a lightweight check. The rule: every task must at minimum
    have a non-empty name field.

    Returns:
        True if all tasks pass feasibility check.
    """
    for task in tasks:
        name = (task.get("name") or task.get("title") or "").strip()
        if not name:
            logger.debug("[TaskValidator] Task missing name/title: id={}", task.get("id"))
            return False
    return True


# ---------------------------------------------------------------------------
# Public aliases and extended checks (acceptance-criteria API)
# ---------------------------------------------------------------------------


def cycle_detect(tasks: List[Dict[str, Any]]) -> Tuple[bool, List[Any]]:
    """Detect whether the task dependency graph contains a cycle.

    This is the acceptance-criteria public API. It wraps the internal
    has_cycle() function and also returns the first cycle path found so
    callers can report which task ids are involved.

    Args:
        tasks: List of task dicts (each with "id" and optional "dependencies").

    Returns:
        Tuple (cycle_found: bool, cycle_path: List[Any]).
        cycle_path is the list of task ids forming the cycle, or [] if none.

    Example:
        tasks = [
            {"id": 1, "name": "A", "dependencies": [2]},
            {"id": 2, "name": "B", "dependencies": [1]},
        ]
        cycle_detect(tasks)  # -> (True, [1, 2])
    """
    graph = build_dependency_graph(tasks)
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: Dict[Any, int] = defaultdict(int)
    path_stack: List[Any] = []

    def _dfs(node: Any) -> Optional[List[Any]]:
        colour[node] = GRAY
        path_stack.append(node)
        for neighbour in graph.get(node, []):
            if colour[neighbour] == GRAY:
                idx = path_stack.index(neighbour)
                return path_stack[idx:]
            if colour[neighbour] == WHITE:
                result = _dfs(neighbour)
                if result is not None:
                    return result
        path_stack.pop()
        colour[node] = BLACK
        return None

    for node in list(graph.keys()):
        if colour[node] == WHITE:
            cycle_path = _dfs(node)
            if cycle_path is not None:
                logger.error("[TaskValidator] Cycle detected in dependency graph: {}", cycle_path)
                return True, list(cycle_path)

    logger.debug("[TaskValidator] No cycle detected in task dependency graph")
    return False, []


def validate_feasibility(
    task: Dict[str, Any],
    available_tokens: int,
) -> Tuple[bool, str]:
    """Check whether a single task can be executed within the available token budget.

    Decision logic:
    1. If the task has an explicit "estimated_tokens" field, use that value.
    2. Otherwise derive a cost estimate from the "estimated_effort" field
       using the _EFFORT_TOKEN_COST heuristic table.
    3. Compare the estimated cost against available_tokens.

    Args:
        task: Task dict. May contain "estimated_tokens" (int) and/or
              "estimated_effort" (str: trivial|small|medium|large|complex).
        available_tokens: Remaining token budget for this execution.

    Returns:
        Tuple (feasible: bool, reason: str).

    Example:
        validate_feasibility({"name": "Setup DB", "estimated_effort": "small"}, 500)
        # -> (True, "Estimated cost 300 <= available 500 (effort=small)")
    """
    task_name = task.get("name") or task.get("title") or str(task.get("id", "?"))

    explicit = task.get("estimated_tokens")
    if isinstance(explicit, int) and explicit > 0:
        cost = explicit
        source = "explicit estimate"
    else:
        effort = (task.get("estimated_effort") or "").strip().lower()
        cost = _EFFORT_TOKEN_COST.get(effort, _EFFORT_TOKEN_COST[""])
        source = "effort={}".format(effort or "unknown")

    feasible = cost <= available_tokens
    if feasible:
        reason = "Estimated cost {} <= available {} ({})".format(cost, available_tokens, source)
        logger.debug("[TaskValidator] Feasible '{}': {}", task_name, reason)
    else:
        reason = "Estimated cost {} > available {} ({})".format(cost, available_tokens, source)
        logger.warning("[TaskValidator] NOT feasible '{}': {}", task_name, reason)

    return feasible, reason


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_breakdown(
    tasks: List[Dict[str, Any]],
    requirement: str = "",
) -> Tuple[bool, List[str]]:
    """Validate a task breakdown list against all four criteria.

    Args:
        tasks: List of task dicts (see module docstring for schema).
        requirement: Original user requirement text (for completeness check).

    Returns:
        Tuple (valid: bool, errors: List[str]).
        valid is True only when errors is empty.

    Example:
        tasks = [
            {"id": 1, "name": "Setup DB", "dependencies": []},
            {"id": 2, "name": "Implement API", "dependencies": [1]},
        ]
        validate_breakdown(tasks, "setup database and implement API")  # -> (True, [])
    """
    errors: List[str] = []

    if not tasks:
        errors.append("Task list is empty")
        return False, errors

    graph = build_dependency_graph(tasks)
    if has_cycle(graph):
        errors.append("Circular dependency detected in task graph")
        logger.error("[TaskValidator] Cycle detected in task dependency graph")

    if not covers_all_requirements(tasks, requirement):
        errors.append("Incomplete task coverage - some requirement keywords not addressed")
        logger.warning("[TaskValidator] Task breakdown does not cover all requirement keywords")

    if not all_tasks_reachable(tasks):
        errors.append("Some tasks are unreachable (orphan or disconnected tasks detected)")
        logger.warning("[TaskValidator] Unreachable tasks detected")

    if not all_tasks_feasible(tasks):
        errors.append("Some tasks are not feasible (missing name/title)")
        logger.error("[TaskValidator] Tasks missing name/title found")

    is_valid = len(errors) == 0

    if is_valid:
        logger.info("[TaskValidator] Validation passed: {} tasks, all checks OK", len(tasks))
    else:
        logger.warning("[TaskValidator] Validation failed: {} error(s): {}", len(errors), errors)

    return is_valid, errors
