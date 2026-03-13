"""
Context Cache - Cache loaded project context to avoid repeated filesystem scans.

Cache validity rules:
1. Project path must be the same
2. Context files (SRS, README, CLAUDE.md) must be unchanged (mtime + size)
3. Cache must be less than 24 hours old

Cache location: ~/.claude/logs/cache/{key}.json
Cache key     : MD5 hash of the absolute project path

Usage:
    from context_cache import ContextCache
    cache = ContextCache()
    cached = cache.load_cache("/path/to/project")
    if cached is None:
        context_data = load_fresh_context()
        cache.save_cache("/path/to/project", context_data)
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List


# Cache validity window
CACHE_MAX_AGE_HOURS = 24

# Files whose modification time / size are tracked for invalidation
TRACKED_FILE_PATTERNS = [
    "[Ss][Rr][Ss].*",
    "[Rr][Ee][Aa][Dd][Mm][Ee].*",
    "[Cc][Ll][Aa][Uu][Dd][Ee].[Mm][Dd]",
]


class ContextCache:
    """Persistent context cache backed by JSON files on disk.

    One cache entry per project (keyed by hash of project path).
    Cache is invalidated when:
    - Context files change (mtime or size)
    - Cache is older than CACHE_MAX_AGE_HOURS
    """

    def __init__(self, cache_base_dir: str = "~/.claude/logs/cache"):
        """
        Args:
            cache_base_dir: Directory where .json cache files are stored.
        """
        self.cache_dir = Path(cache_base_dir).expanduser()
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print("[CONTEXT CACHE] WARNING: Cannot create cache dir: {}".format(exc), file=sys.stderr)

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
                "file_signatures": file_signatures,
                "context_data": context_data,
            }
            cache_file.write_text(json.dumps(entry, indent=2), encoding="utf-8")
            print("[CONTEXT CACHE] Saved cache: {}".format(cache_file.name), file=sys.stderr)
            return True
        except Exception as exc:
            print("[CONTEXT CACHE] WARNING: Save failed: {}".format(exc), file=sys.stderr)
            return False

    def load_cache(self, project_path: str) -> Optional[dict]:
        """Load cached context if valid.

        Validity checks:
        1. Cache file exists
        2. project_path matches
        3. File signatures unchanged (mtime + size for each tracked file)
        4. Cache age < CACHE_MAX_AGE_HOURS

        Args:
            project_path: Absolute path to project root

        Returns:
            context_data dict if cache is valid, None otherwise
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        if not cache_file.exists():
            print("[CONTEXT CACHE] Miss: no cache file for project", file=sys.stderr)
            return None

        try:
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print("[CONTEXT CACHE] WARNING: Cannot read cache: {}".format(exc), file=sys.stderr)
            return None

        # 1. Project path match
        cached_path = entry.get("project_path", "")
        resolved_path = str(Path(project_path).resolve())
        if cached_path != resolved_path:
            print(
                "[CONTEXT CACHE] Miss: path mismatch ({} != {})".format(cached_path, resolved_path),
                file=sys.stderr,
            )
            return None

        # 2. Age check
        saved_at_str = entry.get("saved_at", "")
        try:
            saved_at = datetime.fromisoformat(saved_at_str)
        except Exception:
            print("[CONTEXT CACHE] Miss: invalid saved_at timestamp", file=sys.stderr)
            return None

        age = datetime.now() - saved_at
        if age > timedelta(hours=CACHE_MAX_AGE_HOURS):
            print(
                "[CONTEXT CACHE] Miss: cache expired ({:.1f}h old, limit {}h)".format(
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
            print(
                "[CONTEXT CACHE] Miss: files changed: {}".format(changed),
                file=sys.stderr,
            )
            return None

        # Cache valid
        age_hours = age.total_seconds() / 3600
        print(
            "[CONTEXT CACHE] Hit: {:.1f}h old cache used".format(age_hours),
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
            print("[CONTEXT CACHE] Invalidated cache for project", file=sys.stderr)
            return True
        except Exception as exc:
            print("[CONTEXT CACHE] WARNING: Invalidation failed: {}".format(exc), file=sys.stderr)
            return False

    def cache_info(self, project_path: str) -> Dict[str, Any]:
        """Return metadata about the current cache entry without loading context.

        Returns:
            Dict with keys: exists, age_hours, valid, file_signatures_match
        """
        key = self._cache_key(project_path)
        cache_file = self.cache_dir / (key + ".json")

        if not cache_file.exists():
            return {"exists": False}

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
            }
        except Exception as exc:
            return {"exists": True, "error": str(exc)}

    # -------------------------------------------------------------------------
    # PRIVATE HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _cache_key(project_path: str) -> str:
        """Derive a stable cache filename key from project path."""
        resolved = str(Path(project_path).resolve())
        return hashlib.md5(resolved.encode("utf-8")).hexdigest()

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
