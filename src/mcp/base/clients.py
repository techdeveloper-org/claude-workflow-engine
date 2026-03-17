"""
MCP Lazy Clients - Singleton Pattern for shared resource initialization.

Design Patterns:
  - Singleton:      Each client type has exactly one instance
  - Lazy Init:      Resources loaded on first access, not import time
  - Template Method: Subclasses implement _initialize() and _health_check()

Replaces duplicated lazy-init patterns across 5+ MCP servers:
  - GitPython Repo: git_mcp_server, github_mcp_server
  - PyGithub client: github_mcp_server
  - Qdrant client: vector_db_mcp_server
  - Embedding model: vector_db_mcp_server
  - LLM module: llm_mcp_server

Windows-Safe: ASCII only (cp1252 compatible)
"""

import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class LazyClient(ABC):
    """Abstract base for lazily-initialized singleton clients.

    Thread-safe lazy initialization using double-checked locking.
    Subclasses must implement _initialize() to create the underlying resource.

    Usage:
        class MyClient(LazyClient):
            def _initialize(self):
                return SomeExpensiveConnection()

        client = MyClient.instance()
        resource = client.get()  # calls _initialize() on first access
    """

    _instances = {}
    _lock = threading.Lock()

    def __init__(self):
        self._client = None
        self._available = False
        self._error = None
        self._init_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "LazyClient":
        """Get or create the singleton instance for this client type."""
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = cls()
        return cls._instances[cls]

    def get(self) -> Any:
        """Get the underlying client, initializing on first call.

        Returns None if initialization failed.
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
        """Get the underlying client or raise RuntimeError."""
        client = self.get()
        if client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} not available: {self._error or 'initialization failed'}"
            )
        return client

    @property
    def available(self) -> bool:
        """Check if client is available (triggers initialization)."""
        if self._client is None and not self._error:
            self.get()
        return self._available

    @property
    def error(self) -> Optional[str]:
        """Get last initialization error message."""
        return self._error

    def reset(self) -> None:
        """Reset client state (for testing or reconnection)."""
        with self._init_lock:
            self._client = None
            self._available = False
            self._error = None

    @abstractmethod
    def _initialize(self) -> Any:
        """Create and return the underlying resource.

        Subclasses implement this to perform expensive initialization.
        Return None if the resource is unavailable.
        Raise an exception to indicate an error.
        """

    def health_check(self) -> dict:
        """Run a health check on this client.

        Returns dict with 'available', 'status', and optional details.
        Override _health_check() for custom checks.
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
        """Override for custom health check logic. Return extra dict fields."""
        return None

    @classmethod
    def reset_all(cls):
        """Reset all singleton instances (for testing)."""
        with cls._lock:
            for instance in cls._instances.values():
                instance.reset()
            cls._instances.clear()


# ---------------------------------------------------------------------------
# Concrete Client Implementations
# ---------------------------------------------------------------------------

class GitRepoClient(LazyClient):
    """Lazy GitPython Repo client.

    Usage:
        repo = GitRepoClient.instance().get()
        # or
        repo = GitRepoClient.for_path("/path/to/repo")
    """

    _repo_path = "."

    @classmethod
    def for_path(cls, repo_path: str = ".") -> Any:
        """Get a Repo object for the given path."""
        try:
            from git import Repo
            return Repo(repo_path)
        except ImportError:
            raise RuntimeError(
                "GitPython not installed. Install with: pip install GitPython"
            )

    def _initialize(self) -> Any:
        try:
            from git import Repo
            return Repo(self._repo_path)
        except ImportError:
            raise RuntimeError(
                "GitPython not installed. Install with: pip install GitPython"
            )

    def _health_check(self) -> Optional[dict]:
        if self._client:
            return {
                "branch": str(self._client.active_branch),
                "is_dirty": self._client.is_dirty(),
            }
        return None


class GitHubApiClient(LazyClient):
    """Lazy PyGithub client with token resolution.

    Token sources (checked in order):
    1. GITHUB_TOKEN environment variable
    2. gh CLI keyring (one-time subprocess)
    """

    def _initialize(self) -> Any:
        try:
            from github import Github
        except ImportError:
            raise RuntimeError(
                "PyGithub not installed. Install with: pip install PyGithub"
            )

        token = self._resolve_token()
        if not token:
            raise RuntimeError(
                "No GitHub token. Set GITHUB_TOKEN env var or login with: gh auth login"
            )

        return Github(token)

    @staticmethod
    def _resolve_token() -> Optional[str]:
        """Resolve GitHub token from environment or gh CLI."""
        token = os.getenv("GITHUB_TOKEN")
        if token:
            return token

        try:
            import subprocess
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        return None

    def get_repo(self, repo_path: str = "."):
        """Get PyGithub repo object from local git remote URL."""
        client = self.get_or_raise()
        owner, name = self._parse_remote(repo_path)
        if not owner or not name:
            raise RuntimeError(f"Cannot detect GitHub repo from: {repo_path}")
        return client.get_repo(f"{owner}/{name}")

    @staticmethod
    def _parse_remote(repo_path: str = ".") -> tuple:
        """Parse owner/repo from git remote URL."""
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
            return parts[0], parts[1]
        except Exception:
            return None, None


class QdrantManager(LazyClient):
    """Lazy Qdrant client with collection auto-creation.

    Uses local persistent mode (no external server needed).
    """

    COLLECTIONS = {
        "tool_calls": {"size": 384, "distance": "Cosine"},
        "sessions": {"size": 384, "distance": "Cosine"},
        "flow_traces": {"size": 384, "distance": "Cosine"},
        "node_decisions": {"size": 384, "distance": "Cosine"},
    }

    DB_PATH = Path.home() / ".claude" / "memory" / "vector_db"

    def _initialize(self) -> Any:
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance

        self.DB_PATH.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(self.DB_PATH))

        # Ensure collections exist
        existing = {c.name for c in client.get_collections().collections}
        for name, config in self.COLLECTIONS.items():
            if name not in existing:
                dist = getattr(
                    Distance, config["distance"].upper(), Distance.COSINE
                )
                client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=config["size"], distance=dist
                    ),
                )

        return client

    def _health_check(self) -> Optional[dict]:
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
    """Lazy sentence-transformers embedding model.

    Model: all-MiniLM-L6-v2 (384-dimensional output)
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def _initialize(self) -> Any:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(self.MODEL_NAME)

    def embed(self, text: str) -> list:
        """Generate embedding vector for text. Returns list of floats."""
        model = self.get_or_raise()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _health_check(self) -> Optional[dict]:
        return {
            "model": self.MODEL_NAME,
            "dimension": self.DIMENSION,
        }
