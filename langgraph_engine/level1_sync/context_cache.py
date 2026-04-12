"""
Context Cache - Cache loaded project context to avoid repeated filesystem scans.

Cache validity rules:
1. Project path must be the same
2. Context files (SRS, README, CLAUDE.md) must be unchanged (mtime + size)
3. Cache must be less than 24 hours old

Cache location: ~/.claude/logs/cache/{key}.json
Cache key     : SHA-256 hash of the absolute project path (first 32 hex chars)

Hit/Miss Rate Logging:
- Session-level counters maintained in-memory via CacheStats singleton
- Stats persisted to ~/.claude/logs/cache/cache_stats.json on save
- Access via ContextCache.get_session_stats() or the module-level CACHE_STATS object

Usage:
    from context_cache import ContextCache
    cache = ContextCache()
    cached = cache.load_cache("/path/to/project")
    if cached is None:
        context_data = load_fresh_context()
        cache.save_cache("/path/to/project", context_data)

    # Check hit/miss stats for the session
    stats = ContextCache.get_session_stats()
    print(stats)  # {"hits": 3, "misses": 1, "hit_rate": 0.75, ...}
"""

import hashlib
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Cache validity window
CACHE_MAX_AGE_HOURS = 24

# Files whose modification time / size are tracked for invalidation
TRACKED_FILE_PATTERNS = [
    "[Ss][Rr][Ss].*",
    "[Rr][Ee][Aa][Dd][Mm][Ee].*",
    "[Cc][Ll][Aa][Uu][Dd][Ee].[Mm][Dd]",
]

# Hash algorithm for cache key generation
# SHA-256 truncated to 32 hex chars - more collision-resistant than MD5
CACHE_KEY_HASH = "sha256"
CACHE_KEY_LENGTH = 32  # chars of hex digest to use


# ============================================================================
# CACHE STATS - session-level hit/miss rate tracking
# ============================================================================


class CacheStats:
    """Thread-safe in-memory cache hit/miss rate tracker.

    One global instance (CACHE_STATS) tracks all cache operations for the
    current process lifetime.  Stats are also appended to a JSON log file
    so they survive across short-lived hook processes.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0
        self._saves: int = 0
        self._invalidations: int = 0
        self._miss_reasons: Dict[str, int] = {}
        self._session_start: str = datetime.now().isoformat()

    # ---- public mutators ----

    def record_hit(self) -> None:
        with self._lock:
            self._hits += 1

    def record_miss(self, reason: str = "unknown") -> None:
        with self._lock:
            self._misses += 1
            self._miss_reasons[reason] = self._miss_reasons.get(reason, 0) + 1

    def record_save(self) -> None:
        with self._lock:
            self._saves += 1

    def record_invalidation(self) -> None:
        with self._lock:
            self._invalidations += 1

    # ---- public accessors ----

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = round(self._hits / total, 4) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "saves": self._saves,
                "invalidations": self._invalidations,
                "total_lookups": total,
                "hit_rate": hit_rate,
                "hit_rate_pct": round(hit_rate * 100, 1),
                "miss_reasons": dict(self._miss_reasons),
                "session_start": self._session_start,
                "snapshot_at": datetime.now().isoformat(),
            }

    def reset(self) -> None:
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._saves = 0
            self._invalidations = 0
            self._miss_reasons = {}
            self._session_start = datetime.now().isoformat()

    def persist(self, stats_file: Path) -> bool:
        """Append current stats snapshot to a JSON-lines stats file.

        Args:
            stats_file: Path to the .json stats log file

        Returns:
            True if written successfully
        """
        try:
            snapshot = self.to_dict()
            # Read existing records
            records: List[Dict] = []
            if stats_file.exists():
                try:
                    records = json.loads(stats_file.read_text(encoding="utf-8"))
                    if not isinstance(records, list):
                        records = []
                except Exception:
                    records = []
            records.append(snapshot)
            # Keep last 100 snapshots
            if len(records) > 100:
                records = records[-100:]
            stats_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            print(
                "[CONTEXT CACHE] WARNING: Stats persist failed: {}".format(exc),
                file=sys.stderr,
            )
            return False


# Module-level singleton - shared across all ContextCache instances
CACHE_STATS = CacheStats()


# ============================================================================
# CONTEXT CACHE
# ============================================================================


class ContextCache:
    """Persistent context cache backed by JSON files on disk.

    One cache entry per project (keyed by SHA-256 hash of project path).
    Cache is invalidated when:
    - Context files change (mtime or size)
    - Cache is older than CACHE_MAX_AGE_HOURS

    Enhancements over v1:
    - SHA-256 key hashing (replaces MD5 - more collision resistant)
    - Session-level hit/miss rate tracking via CacheStats
    - Stats persisted to cache_stats.json alongside cache files
    - Detailed miss reason categorisation for diagnostics
    """

    def __init__(self, cache_base_dir: str = "~/.claude/logs/cache"):
        """
        Args:
            cache_base_dir: Directory where .json cache files are stored.
        """
        self.cache_dir = Path(cache_base_dir).expanduser()
        self._stats_file = self.cache_dir / "cache_stats.json"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(
                "[CONTEXT CACHE] WARNING: Cannot create cache dir: {}".format(exc),
                file=sys.stderr,
            )

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def save_cache(self, project_path: str, context_data: dict) -> bool:
        """Persist context_data for a project.

        Args:
            project_path: Absolute path to project root
            context_data: Context dict from node_context_loader

        Returns:
            True if saved successfully
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        try:
            file_signatures = self._collect_file_signatures(project_path)
            entry = {
                "project_path": str(Path(project_path).resolve()),
                "saved_at": datetime.now().isoformat(),
                "cache_key_algo": CACHE_KEY_HASH,
                "file_signatures": file_signatures,
                "context_data": context_data,
            }
            cache_file.write_text(json.dumps(entry, indent=2), encoding="utf-8")
            CACHE_STATS.record_save()
            print(
                "[CONTEXT CACHE] Saved cache: {} (key={})".format(cache_file.name, key[:8] + "..."),
                file=sys.stderr,
            )
            # Persist stats snapshot after each save so they survive process exit
            CACHE_STATS.persist(self._stats_file)
            return True
        except Exception as exc:
            print(
                "[CONTEXT CACHE] WARNING: Save failed: {}".format(exc),
                file=sys.stderr,
            )
            return False

    def load_cache(self, project_path: str) -> Optional[dict]:
        """Load cached context if valid.

        Validity checks:
        1. Cache file exists
        2. project_path matches
        3. File signatures unchanged (mtime + size for each tracked file)
        4. Cache age < CACHE_MAX_AGE_HOURS

        Hit/miss outcomes are recorded to CACHE_STATS automatically.

        Args:
            project_path: Absolute path to project root

        Returns:
            context_data dict if cache is valid, None otherwise
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        if not cache_file.exists():
            CACHE_STATS.record_miss("no_cache_file")
            print("[CONTEXT CACHE] Miss (no_cache_file): project not in cache", file=sys.stderr)
            return None

        try:
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception as exc:
            CACHE_STATS.record_miss("read_error")
            print(
                "[CONTEXT CACHE] WARNING: Cannot read cache (read_error): {}".format(exc),
                file=sys.stderr,
            )
            return None

        # 1. Project path match
        cached_path = entry.get("project_path", "")
        resolved_path = str(Path(project_path).resolve())
        if cached_path != resolved_path:
            CACHE_STATS.record_miss("path_mismatch")
            print(
                "[CONTEXT CACHE] Miss (path_mismatch): {} != {}".format(cached_path, resolved_path),
                file=sys.stderr,
            )
            return None

        # 2. Age check
        saved_at_str = entry.get("saved_at", "")
        try:
            saved_at = datetime.fromisoformat(saved_at_str)
        except Exception:
            CACHE_STATS.record_miss("invalid_timestamp")
            print("[CONTEXT CACHE] Miss (invalid_timestamp): bad saved_at field", file=sys.stderr)
            return None

        age = datetime.now() - saved_at
        if age > timedelta(hours=CACHE_MAX_AGE_HOURS):
            CACHE_STATS.record_miss("expired")
            print(
                "[CONTEXT CACHE] Miss (expired): {:.1f}h old, limit {}h".format(
                    age.total_seconds() / 3600, CACHE_MAX_AGE_HOURS
                ),
                file=sys.stderr,
            )
            return None

        # 3. File signature check
        cached_sigs = entry.get("file_signatures", {})
        current_sigs = self._collect_file_signatures(project_path)
        if cached_sigs != current_sigs:
            changed = [k for k in current_sigs if current_sigs.get(k) != cached_sigs.get(k)]
            CACHE_STATS.record_miss("files_changed")
            print(
                "[CONTEXT CACHE] Miss (files_changed): {}".format(changed),
                file=sys.stderr,
            )
            return None

        # Cache valid - record hit
        age_hours = age.total_seconds() / 3600
        CACHE_STATS.record_hit()
        stats = CACHE_STATS.to_dict()
        print(
            "[CONTEXT CACHE] Hit: {:.1f}h old cache used "
            "(session hit_rate={:.0f}%, hits={}, misses={})".format(
                age_hours,
                stats["hit_rate_pct"],
                stats["hits"],
                stats["misses"],
            ),
            file=sys.stderr,
        )
        context_data = entry.get("context_data", {})
        context_data["_cache_hit"] = True
        context_data["_cache_age_hours"] = round(age_hours, 2)
        return context_data

    def invalidate(self, project_path: str) -> bool:
        """Remove cache entry for a project.

        Args:
            project_path: Absolute path to project root

        Returns:
            True if cache was removed, False if it didn't exist
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        if not cache_file.exists():
            return False

        try:
            cache_file.unlink()
            CACHE_STATS.record_invalidation()
            print("[CONTEXT CACHE] Invalidated cache for project", file=sys.stderr)
            return True
        except Exception as exc:
            print(
                "[CONTEXT CACHE] WARNING: Invalidation failed: {}".format(exc),
                file=sys.stderr,
            )
            return False

    def cache_info(self, project_path: str) -> Dict[str, Any]:
        """Return metadata about the current cache entry without loading context.

        Returns:
            Dict with keys: exists, age_hours, valid, file_signatures_match, hit_rate_stats
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        if not cache_file.exists():
            return {"exists": False, "hit_rate_stats": CACHE_STATS.to_dict()}

        try:
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            saved_at = datetime.fromisoformat(entry.get("saved_at", ""))
            age = datetime.now() - saved_at
            age_hours = age.total_seconds() / 3600

            current_sigs = self._collect_file_signatures(project_path)
            sigs_match = current_sigs == entry.get("file_signatures", {})

            return {
                "exists": True,
                "age_hours": round(age_hours, 2),
                "valid": age_hours < CACHE_MAX_AGE_HOURS and sigs_match,
                "file_signatures_match": sigs_match,
                "saved_at": entry.get("saved_at"),
                "cache_file": str(cache_file),
                "cache_key_algo": entry.get("cache_key_algo", "md5"),
                "hit_rate_stats": CACHE_STATS.to_dict(),
            }
        except Exception as exc:
            return {"exists": True, "error": str(exc), "hit_rate_stats": CACHE_STATS.to_dict()}

    @staticmethod
    def get_session_stats() -> Dict[str, Any]:
        """Return the current session-level hit/miss statistics.

        Returns:
            Dict with keys: hits, misses, saves, total_lookups, hit_rate,
                            hit_rate_pct, miss_reasons, session_start, snapshot_at
        """
        return CACHE_STATS.to_dict()

    @staticmethod
    def reset_session_stats() -> None:
        """Reset session stats counters (useful in tests)."""
        CACHE_STATS.reset()

    # -------------------------------------------------------------------------
    # PRIVATE HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _cache_key(project_path: str) -> str:
        """Derive a stable cache filename key from project path.

        Uses SHA-256 (first CACHE_KEY_LENGTH hex chars) for better collision
        resistance than MD5.  The truncation keeps filenames short while
        preserving uniqueness for realistic project counts.
        """
        resolved = str(Path(project_path).resolve())
        full_hex = hashlib.sha256(resolved.encode("utf-8")).hexdigest()
        return full_hex[:CACHE_KEY_LENGTH]

    @staticmethod
    def _collect_file_signatures(project_path: str) -> Dict[str, Dict[str, Any]]:
        """Collect mtime + size for each tracked context file.

        Returns:
            Dict mapping filename -> {"mtime": float, "size": int}
        """
        root = Path(project_path)
        signatures: Dict[str, Dict[str, Any]] = {}

        for pattern in TRACKED_FILE_PATTERNS:
            try:
                matches = list(root.glob(pattern))
                for match in matches[:1]:  # Only first match per pattern
                    try:
                        stat = match.stat()
                        signatures[match.name] = {
                            "mtime": round(stat.st_mtime, 2),
                            "size": stat.st_size,
                        }
                    except Exception:
                        pass
            except Exception:
                pass

        return signatures
