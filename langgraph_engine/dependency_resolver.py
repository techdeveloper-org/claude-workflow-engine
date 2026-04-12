"""
Dependency Resolver - Recursive skill dependency resolution with circular detection.

Provides:
1. parse_skill_metadata()    - Extract dependencies and version requirements from skill content
2. resolve_dependencies()    - Recursive resolution with visited-set cycle detection
3. detect_circular()         - Dedicated cycle detector using DFS with path tracking
4. build_dependency_graph()  - Build adjacency map from a set of skill names

All functions are pure (no I/O). Callers are responsible for loading skill content
via SkillAgentLoader before passing it here.

Dependency metadata is expected inside skill markdown under a "## Dependencies" or
"## Skill Dependencies" section formatted as YAML-like bullet list:
    ## Dependencies
    - skill: python-backend-engineer
      version: ">=1.0.0"
    - skill: rdbms-core
      version: "*"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

# Regex patterns for extracting dependency blocks from skill markdown
_DEP_SECTION_PATTERN = re.compile(
    r"##\s+(?:Skill\s+)?Dependencies\s*\n(.*?)(?=\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_DEP_ITEM_PATTERN = re.compile(
    r"-\s+skill:\s*([^\n]+)",
    re.IGNORECASE,
)
_VERSION_ITEM_PATTERN = re.compile(
    r"version:\s*[\"']?([^\n\"']+)[\"']?",
    re.IGNORECASE,
)
_MANDATORY_SECTION_PATTERN = re.compile(
    r"##\s+(?:Skill\s+)?Dependencies.*?###\s+Mandatory\s*\n(.*?)(?=###|\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_OPTIONAL_SECTION_PATTERN = re.compile(
    r"##\s+(?:Skill\s+)?Dependencies.*?###\s+Optional\s*\n(.*?)(?=###|\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def parse_skill_metadata(skill_content: str, skill_name: str = "<unknown>") -> Dict[str, Any]:
    """Extract dependency metadata from a skill markdown definition.

    Parses the "## Dependencies" section of a skill.md / SKILL.md file and returns
    structured metadata including mandatory and optional dependencies.

    Args:
        skill_content: Full text content of the skill markdown file.
        skill_name: Name of the skill (for logging only).

    Returns:
        Dict with:
            name (str)                - skill_name passed in
            mandatory (List[Dict])    - mandatory dependencies [{name, version_req}]
            optional (List[Dict])     - optional dependencies [{name, version_req}]
            all_deps (List[str])      - flat list of all dependency names (mandatory only)
            raw_section (str)         - raw matched dependencies section (for debugging)

    Example:
        >>> content = "## Dependencies\\n- skill: rdbms-core\\n  version: >=1.0.0"
        >>> meta = parse_skill_metadata(content, "my-skill")
        >>> meta["mandatory"][0]["name"]
        'rdbms-core'
    """
    result: Dict[str, Any] = {
        "name": skill_name,
        "mandatory": [],
        "optional": [],
        "all_deps": [],
        "raw_section": "",
    }

    if not skill_content:
        logger.debug(f"[DependencyResolver] Empty content for skill '{skill_name}'")
        return result

    # Try to find mandatory/optional sub-sections first (structured format)
    mandatory_match = _MANDATORY_SECTION_PATTERN.search(skill_content)
    optional_match = _OPTIONAL_SECTION_PATTERN.search(skill_content)

    if mandatory_match or optional_match:
        # Structured format with ### Mandatory / ### Optional
        if mandatory_match:
            mandatory_text = mandatory_match.group(1)
            result["mandatory"] = _extract_dep_list(mandatory_text)
            result["raw_section"] += f"[Mandatory]\n{mandatory_text}\n"

        if optional_match:
            optional_text = optional_match.group(1)
            result["optional"] = _extract_dep_list(optional_text)
            result["raw_section"] += f"[Optional]\n{optional_text}\n"
    else:
        # Flat format: all deps under ## Dependencies are treated as mandatory
        dep_match = _DEP_SECTION_PATTERN.search(skill_content)
        if dep_match:
            section_text = dep_match.group(1)
            result["raw_section"] = section_text
            result["mandatory"] = _extract_dep_list(section_text)

    # Build flat all_deps list from mandatory dependencies only
    result["all_deps"] = [d["name"] for d in result["mandatory"]]

    logger.debug(
        f"[DependencyResolver] '{skill_name}': "
        f"{len(result['mandatory'])} mandatory, {len(result['optional'])} optional deps"
    )
    return result


def _extract_dep_list(text: str) -> List[Dict[str, str]]:
    """Extract dependency name+version pairs from a markdown list block."""
    deps: List[Dict[str, str]] = []
    # Split on bullet points and parse name/version
    lines = text.splitlines()
    current_dep: Optional[Dict[str, str]] = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            # Could be a skill entry or a plain name
            skill_match = re.match(r"^-\s+skill:\s*(.+)", stripped, re.IGNORECASE)
            plain_match = re.match(r"^-\s+([a-zA-Z][a-zA-Z0-9_-]+)\s*$", stripped)

            if skill_match:
                if current_dep:
                    deps.append(current_dep)
                current_dep = {"name": skill_match.group(1).strip(), "version_req": "*"}
            elif plain_match:
                if current_dep:
                    deps.append(current_dep)
                current_dep = {"name": plain_match.group(1).strip(), "version_req": "*"}
        elif stripped.startswith("version:") and current_dep is not None:
            ver_match = re.match(r"version:\s*[\"']?([^\n\"']+)[\"']?", stripped, re.IGNORECASE)
            if ver_match:
                current_dep["version_req"] = ver_match.group(1).strip()

    if current_dep:
        deps.append(current_dep)

    return deps


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


def detect_circular(
    dependency_graph: Dict[str, List[str]],
) -> List[List[str]]:
    """Detect all circular dependency cycles using iterative DFS.

    Args:
        dependency_graph: Adjacency map {skill_name: [dep1, dep2, ...]}

    Returns:
        List of cycles, where each cycle is a list of skill names forming the loop.
        Empty list if no circular dependencies found.

    Example:
        >>> graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        >>> detect_circular(graph)
        [['a', 'b', 'c', 'a']]
    """
    cycles: List[List[str]] = []
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    def _dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in dependency_graph.get(node, []):
            if neighbor not in visited:
                _dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found a cycle - reconstruct it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                # Deduplicate (same cycle may be detected from multiple start points)
                cycle_key = frozenset(cycle)
                if not any(frozenset(c) == cycle_key for c in cycles):
                    cycles.append(cycle)
                    logger.warning(f"[DependencyResolver] Circular dependency detected: " f"{' -> '.join(cycle)}")

        path.pop()
        rec_stack.discard(node)

    for skill in list(dependency_graph.keys()):
        if skill not in visited:
            _dfs(skill, [])

    if not cycles:
        logger.debug("[DependencyResolver] No circular dependencies detected")

    return cycles


# ---------------------------------------------------------------------------
# Recursive dependency resolution
# ---------------------------------------------------------------------------


def resolve_dependencies(
    root_skill: str,
    skill_contents: Dict[str, str],
    max_depth: int = 10,
) -> Dict[str, Any]:
    """Recursively resolve all dependencies for a root skill.

    Uses an iterative BFS approach with a visited set to avoid re-processing
    skills and to detect cycles gracefully.

    Args:
        root_skill: Name of the skill to resolve dependencies for.
        skill_contents: Map of {skill_name: skill_markdown_content}. Must include
            at minimum the root_skill's content. Missing dependencies that are not
            in this map will be reported as unresolvable.
        max_depth: Maximum recursion depth to prevent runaway resolution.

    Returns:
        Dict with:
            resolved (List[str])       - ordered list of all skills to load (topological)
            unresolvable (List[str])   - skills whose content was not in skill_contents
            circular (List[List[str]]) - any detected circular dependency cycles
            dependency_graph (Dict)    - full adjacency map built during resolution
            metadata (Dict[str, Dict]) - parsed metadata per skill
            success (bool)             - True if resolution completed without critical errors
            error (Optional[str])      - Error message if resolution failed

    Example:
        >>> contents = {"my-skill": "## Dependencies\\n- skill: rdbms-core",
        ...             "rdbms-core": "# rdbms-core"}
        >>> result = resolve_dependencies("my-skill", contents)
        >>> result["resolved"]
        ['rdbms-core', 'my-skill']
    """
    logger.info(f"[DependencyResolver] Resolving dependencies for '{root_skill}'")

    resolved_order: List[str] = []
    unresolvable: List[str] = []
    dependency_graph: Dict[str, List[str]] = {}
    metadata: Dict[str, Dict] = {}

    # BFS queue: (skill_name, depth, parent)
    queue: List[Tuple[str, int, Optional[str]]] = [(root_skill, 0, None)]
    visited: Set[str] = set()

    while queue:
        skill_name, depth, parent = queue.pop(0)

        if skill_name in visited:
            continue

        if depth > max_depth:
            logger.warning(
                f"[DependencyResolver] Max depth {max_depth} exceeded at '{skill_name}' "
                f"(parent: {parent}). Stopping recursion."
            )
            unresolvable.append(skill_name)
            continue

        visited.add(skill_name)
        content = skill_contents.get(skill_name)

        if content is None:
            logger.warning(
                f"[DependencyResolver] Skill '{skill_name}' not found in skill_contents " f"(required by '{parent}')"
            )
            unresolvable.append(skill_name)
            dependency_graph[skill_name] = []
            continue

        # Parse metadata for this skill
        meta = parse_skill_metadata(content, skill_name)
        metadata[skill_name] = meta

        # Build dependency graph entry
        dep_names = meta["all_deps"]
        dependency_graph[skill_name] = dep_names

        logger.debug(f"[DependencyResolver] '{skill_name}' (depth={depth}): " f"deps={dep_names}")

        # Enqueue dependencies before current skill (for topological ordering)
        for dep_name in dep_names:
            if dep_name not in visited:
                queue.insert(0, (dep_name, depth + 1, skill_name))

        # Add to resolved order AFTER processing deps (post-order = topo sort)
        resolved_order.append(skill_name)

    # Reorder resolved list for topological order (deps before dependents)
    # Build proper topological sort from the dependency graph
    topo_sorted = _topological_sort(dependency_graph, root_skill)
    if topo_sorted:
        resolved_order = topo_sorted

    # Detect any cycles in the full graph
    circular = detect_circular(dependency_graph)

    success = len(unresolvable) == 0 and len(circular) == 0

    logger.info(
        f"[DependencyResolver] Resolution complete for '{root_skill}': "
        f"{len(resolved_order)} resolved, {len(unresolvable)} unresolvable, "
        f"{len(circular)} cycles, success={success}"
    )

    return {
        "resolved": resolved_order,
        "unresolvable": unresolvable,
        "circular": circular,
        "dependency_graph": dependency_graph,
        "metadata": metadata,
        "success": success,
        "error": None if success else _build_error_summary(unresolvable, circular),
    }


def _topological_sort(
    graph: Dict[str, List[str]],
    root: str,
) -> List[str]:
    """Kahn's algorithm for topological sort on a subgraph reachable from root.

    The graph is a dependency graph where graph[A] = [B, C] means A depends on
    B and C. In topological order, B and C must appear BEFORE A.

    We compute in-degree as "how many skills DEPEND ON this node" (i.e., reverse
    in-degree), then process nodes with no dependents first (leaf dependencies
    that nothing in the set depends on).

    Alternatively: nodes with zero OUT-degree (no deps they need) go first.
    """
    # Collect all reachable nodes
    reachable: Set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        for neighbor in graph.get(node, []):
            stack.append(neighbor)

    # Build "dependency count" - how many unresolved deps each node still needs.
    # Nodes with dep_count=0 are leaf deps (no dependencies) and go first.
    dep_count: Dict[str, int] = {}
    for node in reachable:
        # Count only deps that are within the reachable set
        deps_in_set = [n for n in graph.get(node, []) if n in reachable]
        dep_count[node] = len(deps_in_set)

    # Start with nodes that have no dependencies (leaf skills)
    queue: List[str] = sorted([n for n in reachable if dep_count[n] == 0])
    sorted_result: List[str] = []

    # Build reverse map: who depends on node X?
    dependents: Dict[str, List[str]] = {n: [] for n in reachable}
    for node in reachable:
        for dep in graph.get(node, []):
            if dep in reachable:
                dependents[dep].append(node)

    while queue:
        node = queue.pop(0)
        sorted_result.append(node)
        # Decrement dep_count for all skills that depend on this node
        for dependent in sorted(dependents.get(node, [])):
            dep_count[dependent] -= 1
            if dep_count[dependent] == 0:
                queue.append(dependent)

    # If we couldn't sort all (cycle present), return what we have
    return sorted_result


def _build_error_summary(
    unresolvable: List[str],
    circular: List[List[str]],
) -> str:
    """Build human-readable error summary from resolution failures."""
    parts: List[str] = []
    if unresolvable:
        parts.append(f"Unresolvable skills: {', '.join(unresolvable)}")
    if circular:
        cycle_strs = [" -> ".join(c) for c in circular]
        parts.append(f"Circular dependencies: {'; '.join(cycle_strs)}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Dependency graph building
# ---------------------------------------------------------------------------


def build_dependency_graph(
    skill_names: List[str],
    skill_contents: Dict[str, str],
) -> Dict[str, List[str]]:
    """Build a full adjacency map for a collection of skills.

    Unlike resolve_dependencies (which starts from a root), this function
    processes ALL provided skills and extracts their direct dependencies.

    Args:
        skill_names: List of skill names to include in the graph.
        skill_contents: Map of {skill_name: skill_markdown_content}.

    Returns:
        Adjacency map {skill_name: [dependency1, dependency2, ...]}
        Skills with no dependencies map to an empty list.
        Skills whose content is missing map to an empty list with a warning.

    Example:
        >>> skills = ["a", "b", "c"]
        >>> contents = {"a": "## Dependencies\\n- skill: b", "b": "", "c": ""}
        >>> build_dependency_graph(skills, contents)
        {'a': ['b'], 'b': [], 'c': []}
    """
    graph: Dict[str, List[str]] = {}

    for skill_name in skill_names:
        content = skill_contents.get(skill_name)
        if content is None:
            logger.warning(
                f"[DependencyResolver] build_dependency_graph: " f"No content for '{skill_name}', treating as leaf node"
            )
            graph[skill_name] = []
            continue

        meta = parse_skill_metadata(content, skill_name)
        graph[skill_name] = meta["all_deps"]

    logger.info(
        f"[DependencyResolver] Built dependency graph: {len(graph)} skills, "
        f"{sum(len(v) for v in graph.values())} total edges"
    )
    return graph
