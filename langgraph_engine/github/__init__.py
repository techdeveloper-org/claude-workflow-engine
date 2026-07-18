"""github package -- GitHub integration, MCP, routing, facade, and merge validation.

Re-exports all public symbols from sub-modules so callers can use:
    from langgraph_engine.github import GitHubIntegration
    from langgraph_engine.github import GitHubMCP, PYGITHUB_AVAILABLE
    from langgraph_engine.github import GitHubOperationRouter
    from langgraph_engine.github import GitHubFacade, IssueResult, PRResult
    from langgraph_engine.github import check_merge_conflicts_bulletproof
"""

from .facade import BranchResult, GitHubFacade, IssueResult, MergeResult, PRResult, PushResult  # noqa: F401
from .integration import GitHubIntegration  # noqa: F401
from .merge_validation import (  # noqa: F401
    check_merge_conflicts_bulletproof,
    detect_git_conflict_markers,
    detect_project_type_for_validation,
    test_merge_locally,
    validate_project_after_merge,
)
from .operation_router import GitHubOperationRouter  # noqa: F401

try:
    from .mcp import PYGITHUB_AVAILABLE, GitHubMCP  # noqa: F401
except ImportError:
    PYGITHUB_AVAILABLE = False  # noqa: F841
