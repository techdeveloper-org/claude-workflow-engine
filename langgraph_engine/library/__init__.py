"""library package -- local-path bridge to the sibling claude-global-library.

Re-exports the resolver port and its adapters so callers can use:
    from langgraph_engine.library import build_default_resolver, LibrarySetupError
"""

from .resolver import (  # noqa: F401
    ChainedResourceResolver,
    GitHubAdapter,
    HardFailAdapter,
    LibrarySetupError,
    LocalSiblingAdapter,
    ResolvedResource,
    ResourceResolver,
    build_default_resolver,
    locate_library_root,
)
