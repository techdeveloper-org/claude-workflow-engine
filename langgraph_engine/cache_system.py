"""
Enhanced Cache System - Multi-tier persistent caching for the 3-level pipeline.

Three cache tiers with different TTLs:
1. LLM Response Cache      - 1 hour  TTL  (claude_cli / anthropic responses)
2. File Analysis Cache     - 24 hour TTL  (codebase scan results, grep output)
3. Skill Definitions Cache - 7 day   TTL  (SKILL.md / agent.md content)

All tiers share the same JSON-backed storage format and a common
thread-safe in-memory lookup layer to minimise disk reads on hot paths.

Cache key derivation:
- LLM responses:   MD5(model + sorted(messages))
- File analysis:   MD5(file_path + mtime + size)
- Skill defs:      MD5(skill_name + file mtime + size)

Cache location: ~/.claude/logs/cache/<tier>/<hex_key>.json

Usage::

    from cache_system import get_pipeline_cache
    cache = get_pipeline_cache()

    # LLM response
    key = cache.llm.make_key("claude-haiku-4-5", [{"role": "user", "content": "..."}])
    hit = cache.llm.get(key)
    if hit is None:
        response = llm_call(...)
        cache.llm.set(key, response)

    # File analysis
    key = cache.file_analysis.make_file_key("/path/to/file.py")
    result = cache.file_analysis.get(key)

    # Skill definition
    key = cache.skill_defs.make_skill_key("python-backend-engineer")
    content = cache.skill_defs.get(key)
"""

import hashlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTL constants (seconds)
# ---------------------------------------------------------------------------

_LLM_TTL_SECONDS: int = 3600  # 1 hour
_FILE_ANALYSIS_TTL_SECONDS: int = 86400  # 24 hours
_SKILL_DEFS_TTL_SECONDS: int = 604800  # 7 days

# In-memory layer max entries per tier (evict oldest when full)
_MEMORY_MAX_ENTRIES: int = int(os.environ.get("CACHE_MEM_MAX", "512"))

# Base directory for on-disk cache
_DEFAULT_CACHE_BASE: str = os.environ.get("CACHE_BASE_DIR", "~/.claude/logs/cache")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _md5_str(data: str) -> str:
    """Return hex MD5 of *data* (UTF-8 encoded)."""
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def _now_ts() -> float:
    """Return current Unix timestamp."""
    return time.time()


# ---------------------------------------------------------------------------
# In-memory LRU-like layer
# ---------------------------------------------------------------------------


class _MemoryLayer:
    """Thread-safe in-memory dict with TTL and max-size eviction."""

    def __init__(self, max_entries: int = _MEMORY_MAX_ENTRIES):
        self._store: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry)
        self._lock = threading.RLock()
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if _now_ts() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict the entry with the smallest expiry (soonest to expire)
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[key] = (value, _now_ts() + ttl_seconds)

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def stats(self) -> Dict[str, int]:
        with self._lock:
            now = _now_ts()
            live = sum(1 for _, exp in self._store.values() if exp > now)
            return {
                "total_entries": len(self._store),
                "live_entries": live,
                "max_entries": self._max_entries,
            }


# ---------------------------------------------------------------------------
# Disk-backed cache tier
# ---------------------------------------------------------------------------


class CacheTier:
    """Single cache tier: in-memory layer backed by JSON files on disk.

    Args:
        name: Human label ("llm", "file_analysis", "skill_defs").
        ttl_seconds: Time-to-live for cache entries.
        cache_base_dir: Root directory; a sub-directory named *name* is created.
    """

    def __init__(
        self,
        name: str,
        ttl_seconds: int,
        cache_base_dir: str = _DEFAULT_CACHE_BASE,
    ):
        self.name = name
        self.ttl_seconds = ttl_seconds
        self._mem = _MemoryLayer()
        self._disk_dir = Path(cache_base_dir).expanduser() / name
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._lock = threading.RLock()

        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("[Cache:{}] Cannot create disk dir: {}".format(name, exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or None."""
        # 1. Check in-memory layer first
        value = self._mem.get(key)
        if value is not None:
            self._hits += 1
            logger.debug("[Cache:{}] MEM hit for key {}...".format(self.name, key[:8]))
            return value

        # 2. Fall through to disk
        disk_value = self._load_from_disk(key)
        if disk_value is not None:
            # Warm up memory layer
            self._mem.set(key, disk_value, self.ttl_seconds)
            self._hits += 1
            logger.debug("[Cache:{}] DISK hit for key {}...".format(self.name, key[:8]))
            return disk_value

        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* with the tier's TTL."""
        self._mem.set(key, value, self.ttl_seconds)
        self._save_to_disk(key, value)
        self._sets += 1
        logger.debug("[Cache:{}] SET key {}...".format(self.name, key[:8]))

    def invalidate(self, key: str) -> bool:
        """Remove entry from both memory and disk."""
        mem_removed = self._mem.invalidate(key)
        disk_removed = self._delete_from_disk(key)
        return mem_removed or disk_removed

    def clear_expired(self) -> int:
        """Remove expired disk entries; returns count removed."""
        removed = 0
        try:
            now_dt = datetime.utcnow()
            for f in list(self._disk_dir.glob("*.json")):
                try:
                    entry = json.loads(f.read_text(encoding="utf-8"))
                    saved_at = datetime.fromisoformat(entry.get("saved_at", "1970-01-01"))
                    age_s = (now_dt - saved_at).total_seconds()
                    if age_s > self.ttl_seconds:
                        f.unlink(missing_ok=True)
                        removed += 1
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("[Cache:{}] clear_expired error: {}".format(self.name, exc))
        return removed

    def hit_rate(self) -> float:
        """Return cache hit rate (0.0-1.0) since process start."""
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def stats(self) -> Dict[str, Any]:
        """Return cache tier statistics."""
        return {
            "name": self.name,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "hit_rate": round(self.hit_rate(), 4),
            "memory": self._mem.stats(),
        }

    # ------------------------------------------------------------------
    # Key derivation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_llm_key(model: str, messages: list) -> str:
        """Derive a cache key for an LLM request."""
        # Sort messages so that same content in different order hits cache
        canonical = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return _md5_str(canonical)

    @staticmethod
    def make_file_key(file_path: str) -> str:
        """Derive a cache key based on file path + mtime + size."""
        p = Path(file_path)
        try:
            stat = p.stat()
            data = "{}:{}:{}".format(str(p.resolve()), stat.st_mtime, stat.st_size)
        except Exception:
            data = str(file_path)
        return _md5_str(data)

    @staticmethod
    def make_skill_key(skill_name: str, skill_path: Optional[str] = None) -> str:
        """Derive a cache key for a skill definition."""
        if skill_path:
            p = Path(skill_path)
            try:
                stat = p.stat()
                data = "skill:{}:{}:{}".format(skill_name, stat.st_mtime, stat.st_size)
            except Exception:
                data = "skill:{}".format(skill_name)
        else:
            data = "skill:{}".format(skill_name)
        return _md5_str(data)

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _disk_path(self, key: str) -> Path:
        return self._disk_dir / "{}.json".format(key)

    def _save_to_disk(self, key: str, value: Any) -> None:
        try:
            entry = {
                "key": key,
                "saved_at": datetime.utcnow().isoformat(),
                "ttl_seconds": self.ttl_seconds,
                "value": value,
            }
            self._disk_path(key).write_text(
                json.dumps(entry, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[Cache:{}] Disk save failed: {}".format(self.name, exc))

    def _load_from_disk(self, key: str) -> Optional[Any]:
        p = self._disk_path(key)
        if not p.exists():
            return None
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
            saved_at = datetime.fromisoformat(entry.get("saved_at", "1970-01-01"))
            age_s = (datetime.utcnow() - saved_at).total_seconds()
            if age_s > self.ttl_seconds:
                p.unlink(missing_ok=True)
                return None
            return entry.get("value")
        except Exception as exc:
            logger.warning("[Cache:{}] Disk load failed: {}".format(self.name, exc))
            return None

    def _delete_from_disk(self, key: str) -> bool:
        p = self._disk_path(key)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
                return True
            except Exception:
                pass
        return False


# ---------------------------------------------------------------------------
# Multi-tier cache facade
# ---------------------------------------------------------------------------


class PipelineCache:
    """Facade exposing all three cache tiers as named attributes.

    Attributes:
        llm           - LLM response cache (1 hour TTL)
        file_analysis - File analysis / scan cache (24 hour TTL)
        skill_defs    - Skill/agent definition cache (7 day TTL)

    Usage::

        cache = PipelineCache()
        key = cache.llm.make_llm_key("claude-sonnet-4-6", messages)
        hit = cache.llm.get(key)
    """

    def __init__(self, cache_base_dir: str = _DEFAULT_CACHE_BASE):
        self.llm = CacheTier(
            name="llm",
            ttl_seconds=_LLM_TTL_SECONDS,
            cache_base_dir=cache_base_dir,
        )
        self.file_analysis = CacheTier(
            name="file_analysis",
            ttl_seconds=_FILE_ANALYSIS_TTL_SECONDS,
            cache_base_dir=cache_base_dir,
        )
        self.skill_defs = CacheTier(
            name="skill_defs",
            ttl_seconds=_SKILL_DEFS_TTL_SECONDS,
            cache_base_dir=cache_base_dir,
        )

    # ------------------------------------------------------------------

    def all_stats(self) -> Dict[str, Any]:
        """Return stats for all three tiers."""
        return {
            "llm": self.llm.stats(),
            "file_analysis": self.file_analysis.stats(),
            "skill_defs": self.skill_defs.stats(),
        }

    def clear_all_expired(self) -> Dict[str, int]:
        """Remove expired entries from all tiers; return counts."""
        return {
            "llm": self.llm.clear_expired(),
            "file_analysis": self.file_analysis.clear_expired(),
            "skill_defs": self.skill_defs.clear_expired(),
        }

    def hit_rates(self) -> Dict[str, float]:
        """Return hit rate (0-1) for each tier."""
        return {
            "llm": self.llm.hit_rate(),
            "file_analysis": self.file_analysis.hit_rate(),
            "skill_defs": self.skill_defs.hit_rate(),
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_pipeline_cache: Optional[PipelineCache] = None
_singleton_lock = threading.Lock()


def get_pipeline_cache(cache_base_dir: str = _DEFAULT_CACHE_BASE) -> PipelineCache:
    """Return the global PipelineCache singleton (thread-safe lazy init)."""
    global _pipeline_cache
    if _pipeline_cache is None:
        with _singleton_lock:
            if _pipeline_cache is None:
                _pipeline_cache = PipelineCache(cache_base_dir=cache_base_dir)
    return _pipeline_cache


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def cached_llm_call(
    model: str,
    messages: list,
    call_fn: Any,  # Callable[[str, list], Any]
    cache: Optional[PipelineCache] = None,
) -> Any:
    """Wrap an LLM call with cache lookup and storage.

    Args:
        model: Model identifier string.
        messages: List of message dicts (role/content).
        call_fn: Callable(model, messages) -> response_dict.
        cache: PipelineCache instance (uses singleton if None).

    Returns:
        Cached or fresh response dict.
    """
    if cache is None:
        cache = get_pipeline_cache()

    key = cache.llm.make_llm_key(model, messages)
    hit = cache.llm.get(key)
    if hit is not None:
        logger.info("[cached_llm_call] Cache HIT for model={} (key={}...)".format(model, key[:8]))
        return hit

    logger.info("[cached_llm_call] Cache MISS for model={} - calling LLM".format(model))
    response = call_fn(model, messages)
    cache.llm.set(key, response)
    return response


def cached_file_read(
    file_path: str,
    read_fn: Any,  # Callable[[str], str]
    cache: Optional[PipelineCache] = None,
) -> str:
    """Wrap a file read with file-analysis cache.

    Args:
        file_path: Absolute or relative path to file.
        read_fn: Callable(file_path) -> str content.
        cache: PipelineCache instance (uses singleton if None).

    Returns:
        File contents (possibly from cache).
    """
    if cache is None:
        cache = get_pipeline_cache()

    key = cache.file_analysis.make_file_key(file_path)
    hit = cache.file_analysis.get(key)
    if hit is not None:
        logger.debug("[cached_file_read] Cache HIT: {}".format(file_path))
        return hit

    content = read_fn(file_path)
    cache.file_analysis.set(key, content)
    return content


def cached_skill_load(
    skill_name: str,
    skill_path: str,
    load_fn: Any,  # Callable[[str], str]
    cache: Optional[PipelineCache] = None,
) -> str:
    """Wrap a skill definition load with the skill-definitions cache.

    Args:
        skill_name: Skill identifier.
        skill_path: Path to SKILL.md / skill.md.
        load_fn: Callable(skill_path) -> str content.
        cache: PipelineCache instance (uses singleton if None).

    Returns:
        Skill definition content (possibly from cache).
    """
    if cache is None:
        cache = get_pipeline_cache()

    key = cache.skill_defs.make_skill_key(skill_name, skill_path)
    hit = cache.skill_defs.get(key)
    if hit is not None:
        logger.debug("[cached_skill_load] Cache HIT: {}".format(skill_name))
        return hit

    content = load_fn(skill_path)
    if content:
        cache.skill_defs.set(key, content)
    return content or ""
