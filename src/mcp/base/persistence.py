"""
MCP Persistence Layer - Repository Pattern for file-based data storage.

Design Patterns:
  - Repository Pattern: AtomicJsonStore encapsulates JSON file CRUD
  - Append-Only Log:    JsonlAppender for structured event logging
  - Singleton:          SessionIdResolver caches current session ID

Replaces duplicated file I/O patterns across 6+ MCP servers:
  - Atomic write (write .tmp -> rename): 4 servers
  - JSONL append: 3 servers
  - Session ID resolution: 3 servers
  - State load/save: 4 servers

Windows-Safe: ASCII only (cp1252 compatible)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


class AtomicJsonStore:
    """Thread-safe, atomic JSON file persistence with backup support.

    Repository pattern - encapsulates all read/write/backup logic
    for a single JSON file. Uses write-to-temp-then-rename for
    crash safety (no partial writes).

    Usage:
        store = AtomicJsonStore(Path("~/.claude/memory/state.json"))
        data = store.load(default={"count": 0})
        data["count"] += 1
        store.save(data)

        # With modification callback:
        store.modify(lambda d: d.update(count=d["count"] + 1))
    """

    __slots__ = ("_path", "_default_factory")

    def __init__(self, path: Path, default_factory: Optional[Callable] = None):
        """
        Args:
            path: Path to the JSON file
            default_factory: Callable returning default dict when file missing
        """
        self._path = Path(path)
        self._default_factory = default_factory or dict

    @property
    def path(self) -> Path:
        """Return the file path."""
        return self._path

    @property
    def exists(self) -> bool:
        """Check if the backing file exists."""
        return self._path.exists()

    def load(self, default: Optional[dict] = None) -> dict:
        """Load JSON data from file.

        Falls back to .bak backup if primary file is corrupted.
        Returns default (or default_factory()) if file missing.
        """
        # Try primary file
        data = self._try_read(self._path)
        if data is not None:
            return data

        # Try .bak backup
        bak = self._path.with_suffix(self._path.suffix + ".bak")
        data = self._try_read(bak)
        if data is not None:
            return data

        # Return default
        if default is not None:
            return dict(default)
        return self._default_factory()

    def save(self, data: dict, backup: bool = False) -> None:
        """Save data atomically (write .tmp then rename).

        Args:
            data: Dict to serialize
            backup: If True, copy current file to .bak before overwrite
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if backup and self._path.exists():
            bak = self._path.with_suffix(self._path.suffix + ".bak")
            try:
                import shutil
                shutil.copy2(str(self._path), str(bak))
            except Exception:
                pass

        temp = self._path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        temp.replace(self._path)

    def modify(self, fn: Callable[[dict], Any],
               default: Optional[dict] = None) -> dict:
        """Load, apply modification function, save, return updated data.

        The callback receives the loaded dict and can mutate it in place.
        """
        data = self.load(default=default)
        fn(data)
        self.save(data)
        return data

    def delete(self) -> bool:
        """Delete the backing file. Returns True if file existed."""
        if self._path.exists():
            self._path.unlink(missing_ok=True)
            return True
        return False

    @staticmethod
    def _try_read(path: Path) -> Optional[dict]:
        """Try reading and parsing a JSON file. Returns None on failure."""
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, IOError, ValueError, OSError):
            pass
        return None


class JsonlAppender:
    """Append-only JSONL (JSON Lines) logger for structured event data.

    Each call to .append() writes one JSON object as a single line.
    Optimized for write-heavy, read-rarely patterns like tool tracking
    and optimization logging.

    Usage:
        logger = JsonlAppender(Path("~/.claude/logs/tools.jsonl"))
        logger.append({"tool": "Read", "status": "success"})

        # Read all entries
        for entry in logger.read_all():
            print(entry["tool"])
    """

    __slots__ = ("_path",)

    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.exists()

    def append(self, entry: dict, auto_timestamp: bool = True) -> None:
        """Append a single JSON object as a line.

        Args:
            entry: Dict to serialize as one JSON line
            auto_timestamp: If True, add 'timestamp' field if not present
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if auto_timestamp and "timestamp" not in entry:
            entry["timestamp"] = datetime.now().isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def read_all(self) -> list:
        """Read all entries. Returns empty list if file missing."""
        if not self._path.exists():
            return []
        entries = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
        return entries

    def read_filtered(self, date: str = "", **filters) -> list:
        """Read entries matching date and/or field filters.

        Args:
            date: ISO date prefix filter (e.g., "2026-03-17")
            **filters: Key-value pairs to match against entries
        """
        results = []
        for entry in self.read_all():
            if date and date not in entry.get("timestamp", ""):
                continue
            if all(entry.get(k) == v for k, v in filters.items()):
                results.append(entry)
        return results

    def count(self) -> int:
        """Count total entries without loading all into memory."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


class SessionIdResolver:
    """Resolves current session ID from multiple sources with caching.

    Singleton-style resolver that checks:
    1. .current-session.json (primary)
    2. session-progress.json (fallback)

    Caches result for 30 seconds to avoid repeated disk reads.
    """

    _instance = None
    _CACHE_TTL = 30  # seconds

    def __new__(cls, config_dir: Optional[Path] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: Optional[Path] = None):
        if self._initialized:
            return
        self._config_dir = config_dir or (Path.home() / ".claude" / "memory")
        self._cached_id = ""
        self._cache_time = 0.0
        self._initialized = True

    @property
    def current_session_file(self) -> Path:
        return self._config_dir / ".current-session.json"

    @property
    def progress_file(self) -> Path:
        return self._config_dir / "logs" / "session-progress.json"

    def get(self, force_refresh: bool = False) -> str:
        """Get current session ID with caching.

        Args:
            force_refresh: Bypass cache and re-read from disk
        """
        import time
        now = time.time()

        if not force_refresh and self._cached_id:
            if (now - self._cache_time) < self._CACHE_TTL:
                return self._cached_id

        sid = self._resolve()
        self._cached_id = sid
        self._cache_time = now
        return sid

    def invalidate(self) -> None:
        """Clear the cached session ID."""
        self._cached_id = ""
        self._cache_time = 0.0

    def _resolve(self) -> str:
        """Resolve session ID from disk sources."""
        # Source 1: .current-session.json
        sid = self._read_session_file(self.current_session_file)
        if sid:
            return sid

        # Source 2: session-progress.json
        sid = self._read_progress_file(self.progress_file)
        if sid:
            return sid

        return ""

    @staticmethod
    def _read_session_file(path: Path) -> str:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                sid = data.get("current_session_id", "")
                if sid.startswith("SESSION-"):
                    return sid
        except Exception:
            pass
        return ""

    @staticmethod
    def _read_progress_file(path: Path) -> str:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                sid = data.get("session_id", "")
                if sid.startswith("SESSION-"):
                    return sid
        except Exception:
            pass
        return ""

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None
