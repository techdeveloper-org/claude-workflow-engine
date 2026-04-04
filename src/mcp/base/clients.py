"""
MCP Lazy Clients - Singleton Pattern for shared resource initialization.

Design Patterns:
  - Singleton:      Each client type has exactly one instance via ``instance()``
  - Lazy Init:      Resources loaded on first ``get()`` call, not at import time
  - Template Method: Subclasses implement ``_initialize()`` and ``_health_check()``

Replaces duplicated lazy-init patterns across 5+ MCP servers:
  - GitPython Repo: ``git_mcp_server``, ``github_mcp_server``
  - PyGithub client: ``github_mcp_server``
  - Qdrant client: ``vector_db_mcp_server``
  - Embedding model: ``vector_db_mcp_server``

Windows-Safe: ASCII only (cp1252 compatible)
"""

import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional, Tuple


class LazyClient(ABC):
    """Abstract base for lazily-initialized singleton clients.

    Thread-safe lazy initialization using double-checked locking pattern.
    Each concrete subclass gets its own singleton instance, managed via
    a class-level registry.

    Subclasses must implement ``_initialize()`` to create the underlying
    resource. Optionally override ``_health_check()`` for custom health
    monitoring.

    Class Attributes:
        _instances: Shared registry mapping subclass types to their singletons.
        _lock: Global lock for singleton creation (per-instance locks used
            for initialization to avoid blocking unrelated clients).

    Example::

        class MyClient(LazyClient):
            def _initialize(self):
                return SomeExpensiveConnection()

        client = MyClient.instance()
        resource = client.get()  # calls _initialize() on first access
    """

    _instances = {}
    _lock = threading.Lock()

    def __init__(self):
        """Initialize client state. Called once per singleton."""
        self._client = None
        self._available = False
        self._error = None
        self._init_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "LazyClient":
        """Get or create the singleton instance for this client type.

        Uses double-checked locking for thread safety without contention
        on subsequent calls.

        Returns:
            The singleton instance of the concrete subclass.
        """
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = cls()
        return cls._instances[cls]

    def get(self) -> Any:
        """Get the underlying client, initializing on first call.

        Thread-safe: uses a per-instance lock so different client types
        can initialize concurrently without blocking each other.

        Returns:
            The initialized client object, or None if initialization failed.
        """
        if self._client is not None:
            return self._client

        with self._init_lock:
            if self._client is not None:
                return self._client

            try:
                self._client = self._initialize()
                self._available = self._client is not None
            except Exception as e:
                self._error = str(e)
                self._available = False
                self._client = None

        return self._client

    def get_or_raise(self) -> Any:
        """Get the underlying client or raise ``RuntimeError``.

        Convenience method for call sites that cannot handle ``None``.

        Returns:
            The initialized client object.

        Raises:
            RuntimeError: If the client is not available (initialization failed
                or dependency missing).
        """
        client = self.get()
        if client is None:
            raise RuntimeError(f"{self.__class__.__name__} not available: " f"{self._error or 'initialization failed'}")
        return client

    @property
    def available(self) -> bool:
        """Check if the client is available.

        Note: This triggers initialization on first access as a side effect.
        If you only want to check without initializing, test
        ``self._client is not None`` directly.

        Returns:
            True if the client initialized successfully.
        """
        if self._client is None and not self._error:
            self.get()
        return self._available

    @property
    def error(self) -> Optional[str]:
        """Last initialization error message, or None if no error occurred."""
        return self._error

    def reset(self) -> None:
        """Reset client state for testing or reconnection.

        Clears the cached client, error, and availability flag.
        Next ``get()`` call will re-initialize.
        """
        with self._init_lock:
            self._client = None
            self._available = False
            self._error = None

    @abstractmethod
    def _initialize(self) -> Any:
        """Create and return the underlying resource.

        Subclasses implement this to perform expensive initialization
        (network connections, model loading, etc.).

        Returns:
            The initialized resource, or None if unavailable.

        Raises:
            Exception: Any exception is caught by ``get()`` and stored in ``error``.
        """

    def health_check(self) -> dict:
        """Run a health check on this client.

        Returns a dict with ``client``, ``available``, ``status``, and any
        additional fields from ``_health_check()``.

        Returns:
            Health status dictionary.
        """
        base = {
            "client": self.__class__.__name__,
            "available": self.available,
            "status": "healthy" if self.available else "unavailable",
        }
        if self._error:
            base["error"] = self._error

        if self._available:
            try:
                extra = self._health_check()
                if extra:
                    base.update(extra)
            except Exception as e:
                base["status"] = "degraded"
                base["health_error"] = str(e)[:100]

        return base

    def _health_check(self) -> Optional[dict]:
        """Override for custom health check logic.

        Called by ``health_check()`` only when the client is available.

        Returns:
            Dict of additional health fields to merge, or None.
        """
        return None

    @classmethod
    def reset_all(cls) -> None:
        """Reset all singleton instances across all subclasses.

        Primarily for testing. Clears the shared ``_instances`` registry
        and resets each client's internal state.
        """
        with cls._lock:
            for inst in cls._instances.values():
                inst.reset()
            cls._instances.clear()


# ---------------------------------------------------------------------------
# Concrete Client Implementations
# ---------------------------------------------------------------------------


class GitRepoClient(LazyClient):
    """Lazy GitPython ``Repo`` client for git operations.

    Provides two access patterns:

    - ``GitRepoClient.instance().get()`` -- singleton for the default repo
    - ``GitRepoClient.for_path(path)`` -- factory for a specific repo path

    The ``for_path()`` classmethod creates a fresh ``Repo`` each time
    (not a singleton), suitable for tools that operate on different repos.

    Example::

        # Singleton (default repo)
        repo = GitRepoClient.instance().get()

        # Specific path (not cached)
        repo = GitRepoClient.for_path("/path/to/repo")
    """

    _repo_path = "."

    @classmethod
    def for_path(cls, repo_path: str = ".") -> Any:
        """Create a ``Repo`` object for the given path.

        This is NOT a singleton -- each call creates a fresh ``Repo``.
        Use this for tools that need to operate on different repositories.

        Args:
            repo_path: Filesystem path to the git repository root.

        Returns:
            A ``git.Repo`` instance.

        Raises:
            RuntimeError: If GitPython is not installed.
        """
        try:
            from git import Repo

            return Repo(repo_path)
        except ImportError:
            raise RuntimeError("GitPython not installed. Install with: pip install GitPython")

    def _initialize(self) -> Any:
        """Initialize the default git repo at ``_repo_path``.

        Returns:
            A ``git.Repo`` instance for the default path.

        Raises:
            RuntimeError: If GitPython is not installed.
        """
        try:
            from git import Repo

            return Repo(self._repo_path)
        except ImportError:
            raise RuntimeError("GitPython not installed. Install with: pip install GitPython")

    def _health_check(self) -> Optional[dict]:
        """Check git repo health (branch name and dirty state).

        Returns:
            Dict with ``branch`` and ``is_dirty`` fields, or None.
        """
        if self._client:
            return {
                "branch": str(self._client.active_branch),
                "is_dirty": self._client.is_dirty(),
            }
        return None


class GitHubApiClient(LazyClient):
    """Lazy PyGithub client with automatic token resolution.

    Token sources are checked in order:

    1. ``GITHUB_TOKEN`` environment variable
    2. ``gh`` CLI keyring via ``gh auth token`` subprocess (one-time, cached)

    Example::

        client = GitHubApiClient.instance()
        repo = client.get_repo(".")  # auto-detects owner/repo from git remote
    """

    def _initialize(self) -> Any:
        """Initialize the PyGithub client with resolved token.

        Returns:
            A ``github.Github`` instance.

        Raises:
            RuntimeError: If PyGithub is not installed or no token is available.
        """
        try:
            from github import Github
        except ImportError:
            raise RuntimeError("PyGithub not installed. Install with: pip install PyGithub")

        token = self._resolve_token()
        if not token:
            raise RuntimeError("No GitHub token. Set GITHUB_TOKEN env var or " "login with: gh auth login")

        return Github(token)

    @staticmethod
    def _resolve_token() -> Optional[str]:
        """Resolve GitHub token from environment or ``gh`` CLI.

        Checks ``GITHUB_TOKEN`` env var first, then falls back to
        ``gh auth token`` subprocess call with 5-second timeout.

        Returns:
            Token string, or None if no source provides one.
        """
        token = os.getenv("GITHUB_TOKEN")
        if token:
            return token

        try:
            import subprocess

            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, OSError):
            pass

        return None

    def get_repo(self, repo_path: str = "."):
        """Get a PyGithub repo object from a local git remote URL.

        Parses the origin remote URL to determine ``owner/repo``,
        then fetches the corresponding GitHub repo object.

        Args:
            repo_path: Local filesystem path to the git repository.

        Returns:
            A ``github.Repository`` object.

        Raises:
            RuntimeError: If the GitHub client is not available or the
                repo cannot be detected from the git remote.
        """
        client = self.get_or_raise()
        owner, name = self._parse_remote(repo_path)
        if not owner or not name:
            raise RuntimeError(f"Cannot detect GitHub repo from: {repo_path}")
        return client.get_repo(f"{owner}/{name}")

    @staticmethod
    def _parse_remote(repo_path: str = ".") -> Tuple[Optional[str], Optional[str]]:
        """Parse ``owner/repo`` from git remote origin URL.

        Handles both SSH (``git@github.com:owner/repo.git``) and
        HTTPS (``https://github.com/owner/repo.git``) URL formats.

        Args:
            repo_path: Path to local git repository.

        Returns:
            Tuple of ``(owner, repo_name)`` or ``(None, None)`` on failure.
        """
        try:
            from git import Repo

            repo = Repo(repo_path)
            url = repo.remotes.origin.url
            if "github.com" not in url:
                return None, None
            if url.startswith("git@"):
                parts = url.split(":")[-1].replace(".git", "").split("/")
            else:
                parts = url.rstrip("/").replace(".git", "").split("/")[-2:]
            if len(parts) >= 2:
                return parts[0], parts[1]
            return None, None
        except (ImportError, IndexError, AttributeError):
            return None, None


class QdrantManager(LazyClient):
    """Lazy Qdrant vector database client with collection auto-creation.

    Uses Qdrant in local persistent mode (no external server needed).
    On first initialization, ensures all required collections exist
    with the correct vector configuration.

    Class Attributes:
        COLLECTIONS: Registry of collection names with their vector
            size and distance metric configuration.
        DB_PATH: Filesystem path for Qdrant local storage.
            Evaluated lazily inside ``_initialize()`` to respect
            test environment overrides.
    """

    COLLECTIONS = {
        "tool_calls": {"size": 384, "distance": "Cosine"},
        "sessions": {"size": 384, "distance": "Cosine"},
        "flow_traces": {"size": 384, "distance": "Cosine"},
        "node_decisions": {"size": 384, "distance": "Cosine"},
    }

    @classmethod
    def _get_db_path(cls) -> Path:
        """Resolve the database path lazily (not at import time).

        Returns:
            Path to the Qdrant local storage directory.
        """
        return Path.home() / ".claude" / "memory" / "vector_db"

    def _initialize(self) -> Any:
        """Initialize Qdrant client and ensure all collections exist.

        Creates the storage directory if needed and bootstraps any
        missing collections from the ``COLLECTIONS`` registry.

        Returns:
            A ``QdrantClient`` instance in local persistent mode.

        Raises:
            ImportError: If ``qdrant_client`` is not installed.
        """
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        db_path = self._get_db_path()
        db_path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(db_path))

        # Ensure collections exist
        existing = {c.name for c in client.get_collections().collections}
        for name, config in self.COLLECTIONS.items():
            if name not in existing:
                dist = getattr(Distance, config["distance"].upper(), Distance.COSINE)
                client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=config["size"], distance=dist),
                )

        return client

    def _health_check(self) -> Optional[dict]:
        """Check health of all registered collections.

        Returns:
            Dict with collection statuses and point counts.
        """
        if not self._client:
            return None
        collections = {}
        for name in self.COLLECTIONS:
            try:
                info = self._client.get_collection(name)
                collections[name] = {
                    "status": str(info.status),
                    "points": info.points_count or 0,
                }
            except Exception:
                collections[name] = {"status": "ERROR"}
        return {"collections": collections}


class EmbeddingManager(LazyClient):
    """Lazy sentence-transformers embedding model manager.

    Loads the ``all-MiniLM-L6-v2`` model on first ``embed()`` call.
    Produces 384-dimensional normalized embeddings suitable for
    cosine similarity search in Qdrant.

    Class Attributes:
        MODEL_NAME: Name of the sentence-transformers model to load.
        DIMENSION: Output embedding vector dimension.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def _initialize(self) -> Any:
        """Load the sentence-transformers model.

        Returns:
            A ``SentenceTransformer`` model instance.

        Raises:
            ImportError: If ``sentence_transformers`` is not installed.
        """
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.MODEL_NAME)

    def embed(self, text: str) -> List[float]:
        """Generate a normalized embedding vector for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats (384-dimensional embedding vector).

        Raises:
            RuntimeError: If the embedding model is not available.
        """
        model = self.get_or_raise()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _health_check(self) -> Optional[dict]:
        """Report model name and output dimension.

        Returns:
            Dict with ``model`` and ``dimension`` fields.
        """
        return {
            "model": self.MODEL_NAME,
            "dimension": self.DIMENSION,
        }
