"""
Level 2 SubGraph - Standards System with Conditional Java Routing

Level 2 loads coding standards and patterns:
1. Common standards (applies to all projects)
2. Java/Spring standards (only if is_java_project=True)

Uses conditional routing to avoid loading unnecessary Java standards
for non-Java projects (saves ~1-2 seconds and context tokens).
"""

from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


# ============================================================================
# STANDARDS DETECTION
# ============================================================================


def detect_project_type(state: FlowState) -> None:
    """Detect project type (Java, Python, Node.js, etc.).

    Sets state["is_java_project"] based on presence of:
    - pom.xml (Maven)
    - build.gradle (Gradle)
    - .java files

    Modifies state in-place.
    """
    try:
        project_root = Path(state.get("project_root", "."))

        # Check for Java project indicators
        has_pom = (project_root / "pom.xml").exists()
        has_gradle = (project_root / "build.gradle").exists()
        has_gradle_kts = (project_root / "build.gradle.kts").exists()
        java_files = list(project_root.glob("**/*.java"))[:5]  # Check first 5

        is_java = has_pom or has_gradle or has_gradle_kts or bool(java_files)
        state["is_java_project"] = is_java

    except Exception:
        state["is_java_project"] = False


# ============================================================================
# STANDARDS NODES
# ============================================================================


def node_common_standards(state: FlowState) -> FlowState:
    """Load common standards that apply to all projects.

    Loads:
    - Code quality standards
    - Documentation standards
    - Git commit standards
    - File naming conventions
    - Import patterns

    Args:
        state: FlowState

    Returns:
        Updated state with standards_loaded, standards_count
    """
    try:
        detect_project_type(state)

        # Common standards (hardcoded - would load from policies/ in production)
        common_standards = [
            "code-quality",
            "documentation",
            "git-commits",
            "file-naming",
            "imports",
            "error-handling",
            "logging",
            "testing",
            "performance",
            "security",
            "accessibility",
            "internationalization",
            "backwards-compatibility",
            "api-versioning",
            "deprecation",
        ]

        state["standards_loaded"] = True
        state["standards_count"] = len(common_standards)
        state.setdefault("pipeline", []).append({
            "node": "node_common_standards",
            "standards_loaded": len(common_standards),
        })

        return state

    except Exception as e:
        state["standards_loaded"] = False
        state["standards_error"] = str(e)
        return state


def node_java_standards(state: FlowState) -> FlowState:
    """Load Java/Spring standards (only for Java projects).

    Loads:
    - Spring Boot patterns
    - Java language standards
    - Maven/Gradle build standards
    - Java testing frameworks
    - Microservices patterns

    Args:
        state: FlowState

    Returns:
        Updated state with java_standards_loaded, spring_boot_patterns
    """
    try:
        java_standards = [
            "spring-boot",
            "spring-mvc",
            "spring-security",
            "spring-data",
            "junit",
            "mockito",
            "maven-conventions",
            "gradle-conventions",
            "microservices",
            "java-naming",
            "java-concurrency",
            "dependency-injection",
            "aspect-oriented",
        ]

        state["java_standards_loaded"] = True
        state["spring_boot_patterns"] = {
            "annotations": [
                "@SpringBootApplication",
                "@Service",
                "@Repository",
                "@RestController",
                "@Bean",
                "@Configuration",
            ],
            "standards_count": len(java_standards),
            "patterns": [
                "dependency-injection",
                "service-layer",
                "repository-pattern",
                "controller-pattern",
                "exception-handling",
            ],
        }

        state.setdefault("pipeline", []).append({
            "node": "node_java_standards",
            "java_standards_loaded": len(java_standards),
        })

        return state

    except Exception as e:
        state["java_standards_loaded"] = False
        state["java_standards_error"] = str(e)
        return state


# ============================================================================
# ROUTING
# ============================================================================


def route_java_standards(state: FlowState) -> str:
    """Route based on is_java_project flag.

    Args:
        state: FlowState

    Returns:
        "java_standards_node" if Java project, "merge" otherwise
    """
    if state.get("is_java_project"):
        return "java_standards_node"
    return "merge"


# ============================================================================
# MERGE NODE
# ============================================================================


def level2_merge_node(state: FlowState) -> FlowState:
    """Merge standards loading results.

    Determines overall Level 2 status:
    - Common standards loaded: OK
    - Java standards also loaded (for Java projects): OK
    - Any error: FAILED

    Args:
        state: FlowState

    Returns:
        Updated state with level2_status
    """
    if state.get("standards_loaded"):
        state["level2_status"] = "OK"
    else:
        state["level2_status"] = "FAILED"
        if "errors" not in state:
            state["errors"] = []
        state["errors"].append("Level 2: Standards loading failed")

    # Count total standards loaded
    total = state.get("standards_count", 0)
    if state.get("java_standards_loaded"):
        total += len(state.get("spring_boot_patterns", {}).get("patterns", []))

    state["standards_count"] = total

    return state


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level2_subgraph():
    """Create Level 2 subgraph with conditional Java routing.

    Returns:
        Compiled StateGraph for Level 2
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add nodes
    graph.add_node("common_standards", node_common_standards)
    graph.add_node("java_standards", node_java_standards)
    graph.add_node("merge", level2_merge_node)

    # Common standards run first
    graph.add_edge(START, "common_standards")

    # Conditional routing: Java standards only for Java projects
    graph.add_conditional_edges(
        "common_standards",
        route_java_standards,
        {
            "java_standards_node": "java_standards",
            "merge": "merge",
        },
    )

    # Java standards (if taken) leads to merge
    graph.add_edge("java_standards", "merge")

    graph.add_edge("merge", END)

    return graph.compile()
