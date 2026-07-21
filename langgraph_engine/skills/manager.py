"""
Skill Manager - Enhanced skill lifecycle management with retry, caching, and versioning.

Responsibilities:
1. Download skills from GitHub with exponential-backoff retry (max 4 attempts)
2. Cache downloaded skills in-memory and on disk for reuse
3. Validate downloaded skills using dependency_resolver and version_selector
4. Orchestrate full skill provisioning: discover -> download -> validate -> cache

Retry strategy:
    Attempt 1: immediate
    Attempt 2: 1s delay
    Attempt 3: 2s delay
    Attempt 4: 4s delay
    Attempt 5: 8s delay (max 4 retries = 5 total attempts)

Cache strategy:
    - In-memory dict is checked first (fastest)
    - Disk cache at ~/.claude/skills/<domain>/<skill_name>/ is checked second
    - After successful download, skill is stored in both caches
    - Cache hit is returned immediately without network calls

All public methods return structured result dicts for consistent error handling.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_skills_dir

    _SKILLS_ROOT_DEFAULT = get_skills_dir()
except ImportError:
    _SKILLS_ROOT_DEFAULT = Path.home() / ".claude" / "skills"

from langgraph_engine.dependency_resolver import (
    build_dependency_graph,
    detect_circular,
    parse_skill_metadata,
    resolve_dependencies,
)
from langgraph_engine.library.resolver import LocalSiblingAdapter, locate_library_root
from langgraph_engine.patterns import SkillRegistry
from langgraph_engine.version_selector import handle_deprecated, validate_version_set

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RETRY_DELAYS: List[float] = [0, 1, 2, 4, 8]
MAX_RETRIES: int = 4

_GITHUB_OWNER = os.environ.get("CLAUDE_GITHUB_OWNER", "techdeveloper-org")
_GITHUB_RAW_BASE = os.environ.get(
    "CLAUDE_SKILL_REPO_URL",
    "https://raw.githubusercontent.com/{}/claude-global-library/main".format(_GITHUB_OWNER),
)

_DEFAULT_DOMAINS: List[str] = [
    "backend",
    "frontend",
    "devops",
    "database",
    "testing",
    "security",
    "mobile",
    "ai",
]

_HTTP_TIMEOUT: int = 15


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------


class SkillManager:
    """Manages skill lifecycle: download, cache, validate, and version selection.

    Usage:
        manager = SkillManager()
        result = manager.provision_skill("python-backend-engineer")
        if result["success"]:
            content = result["content"]
        else:
            print(result["error"])
    """

    def __init__(
        self,
        skills_root: Optional[Path] = None,
        github_raw_base: str = _GITHUB_RAW_BASE,
        local_library_root: Optional[Path] = None,
    ):
        """Initialize SkillManager.

        Args:
            skills_root: Root directory for skill storage. Defaults to ~/.claude/skills/
            github_raw_base: Base URL for GitHub raw content downloads.
            local_library_root: Root of the sibling claude-global-library checkout,
                used for the local-sibling resolver tier (ADR-1). Defaults to the
                result of ``locate_library_root()``; pass explicitly to override
                or to inject a test double.
        """
        self.skills_root = skills_root or _SKILLS_ROOT_DEFAULT
        self.github_raw_base = github_raw_base.rstrip("/")
        self._cache: Dict[str, Dict[str, Any]] = {}

        library_root = local_library_root if local_library_root is not None else locate_library_root()
        self._local_adapter: Optional[LocalSiblingAdapter] = (
            LocalSiblingAdapter(library_root) if library_root is not None else None
        )
        if self._local_adapter is None:
            logger.info("[SkillManager] No local sibling library found; skills served from disk cache / GitHub only.")

        logger.info(
            "[SkillManager] Initialized: skills_root={}, cache_size={}".format(self.skills_root, len(self._cache))
        )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def provision_skill(
        self,
        skill_name: str,
        version_req: str = "*",
        force_download: bool = False,
    ) -> Dict[str, Any]:
        """Provision a skill: load from cache or download with retry.

        This is the primary entry point for skill acquisition. It checks
        in-memory cache, then disk cache, then downloads from GitHub with
        exponential-backoff retry.

        Args:
            skill_name: Skill name to provision (e.g., "python-backend-engineer").
            version_req: Version requirement specifier (e.g., ">=1.0.0", "*").
            force_download: Skip cache and always download fresh copy.

        Returns:
            Dict with success (bool), skill_name (str), content (Optional[str]),
            version (Optional[str]), source (str), attempts (int),
            deprecated (bool), deprecation_info (Dict), error (Optional[str])
        """
        logger.info("[SkillManager] Provisioning skill '{}' (req: {})".format(skill_name, version_req))

        if not force_download:
            cached = self._get_from_memory_cache(skill_name)
            if cached:
                logger.info("[SkillManager] Memory cache hit for '{}'".format(skill_name))
                return self._build_result(
                    skill_name=skill_name,
                    content=cached["content"],
                    source="memory_cache",
                    attempts=0,
                    version=cached.get("version"),
                    metadata=cached.get("metadata"),
                )

        if not force_download:
            local_content, local_path = self._try_local_tier(skill_name)
            if local_content is not None:
                logger.info("[SkillManager] Local sibling hit for '{}' ({})".format(skill_name, local_path))
                self._store_in_memory_cache(skill_name, local_content)
                return self._build_result(
                    skill_name=skill_name,
                    content=local_content,
                    source="local",
                    attempts=0,
                )

        if not force_download:
            disk_content = self._load_from_disk(skill_name)
            if disk_content:
                logger.info("[SkillManager] Disk cache hit for '{}'".format(skill_name))
                self._store_in_memory_cache(skill_name, disk_content)
                return self._build_result(
                    skill_name=skill_name,
                    content=disk_content,
                    source="disk_cache",
                    attempts=0,
                )

        download_result = self._download_with_retry(skill_name)

        if not download_result["success"]:
            disk_fallback = self._load_from_disk(skill_name)
            if disk_fallback:
                logger.warning("[SkillManager] Download failed for '{}', falling back to disk cache".format(skill_name))
                return self._build_result(
                    skill_name=skill_name,
                    content=disk_fallback,
                    source="disk_cache",
                    attempts=download_result["attempts"],
                    error="Download failed - serving cached version",
                )

            return {
                "success": False,
                "skill_name": skill_name,
                "content": None,
                "version": None,
                "source": "failed",
                "attempts": download_result["attempts"],
                "deprecated": False,
                "deprecation_info": {},
                "error": download_result["error"],
            }

        content = download_result["content"]
        dep_info = handle_deprecated(skill_name, content)
        self._store_in_memory_cache(skill_name, content)
        self._save_to_disk(skill_name, content)

        return self._build_result(
            skill_name=skill_name,
            content=content,
            source="download",
            attempts=download_result["attempts"],
            deprecated=dep_info["is_deprecated"],
            deprecation_info=dep_info,
        )

    def provision_skills_batch(
        self,
        skill_names: List[str],
        version_requirements: Optional[Dict[str, str]] = None,
        resolve_deps: bool = True,
    ) -> Dict[str, Any]:
        """Provision multiple skills, optionally resolving dependencies.

        Args:
            skill_names: List of skill names to provision.
            version_requirements: Optional {skill_name: version_req} map.
            resolve_deps: If True, recursively resolve and provision dependencies.

        Returns:
            Dict with provisioned (Dict), all_success (bool), failed (List),
            dependency_order (List), circular_deps (List)
        """
        version_requirements = version_requirements or {}
        provisioned: Dict[str, Dict] = {}
        failed: List[str] = []
        all_skill_names = list(skill_names)

        dependency_order: List[str] = skill_names[:]
        circular_deps: List[List[str]] = []

        if resolve_deps and skill_names:
            dep_result = self._resolve_all_dependencies(skill_names)
            dependency_order = dep_result.get("resolved", skill_names)
            circular_deps = dep_result.get("circular", [])
            for name in dependency_order:
                if name not in all_skill_names:
                    all_skill_names.append(name)

        for skill_name in dependency_order:
            req = version_requirements.get(skill_name, "*")
            result = self.provision_skill(skill_name, version_req=req)
            provisioned[skill_name] = result
            if not result["success"]:
                failed.append(skill_name)

        all_success = len(failed) == 0

        logger.info(
            "[SkillManager] Batch provisioning: {} total, {} failed, circular={}".format(
                len(provisioned), len(failed), len(circular_deps)
            )
        )

        return {
            "provisioned": provisioned,
            "all_success": all_success,
            "failed": failed,
            "dependency_order": dependency_order,
            "circular_deps": circular_deps,
        }

    def validate_skill_set(
        self,
        skill_names: List[str],
    ) -> Dict[str, Any]:
        """Validate a set of skills for conflicts and version compatibility.

        Args:
            skill_names: Names of skills to validate together.

        Returns:
            Dict with valid (bool), conflicts (List), circular_deps (List),
            deprecation_warnings (List), report (str)
        """
        skill_contents: Dict[str, str] = {}
        deprecation_warnings: List[Dict] = []

        for skill_name in skill_names:
            content = self._load_from_disk(skill_name) or self._get_from_memory_cache(skill_name, "content")
            if content:
                skill_contents[skill_name] = content
                dep_info = handle_deprecated(skill_name, content)
                if dep_info["is_deprecated"]:
                    deprecation_warnings.append(dep_info)

        dep_graph = build_dependency_graph(skill_names, skill_contents)
        circular_deps = detect_circular(dep_graph)

        version_reqs: Dict[str, Dict[str, str]] = {}
        installed_versions: Dict[str, str] = {}

        for skill_name, content in skill_contents.items():
            meta = parse_skill_metadata(content, skill_name)
            version_reqs[skill_name] = {d["name"]: d["version_req"] for d in meta["mandatory"]}
            installed_versions[skill_name] = self._extract_version(content) or "0.0.0"

        version_result = validate_version_set(installed_versions, version_reqs)

        valid = len(circular_deps) == 0 and version_result["valid"] and len(deprecation_warnings) == 0

        report_parts = [version_result["report"]]
        if circular_deps:
            report_parts.append("{} circular dependency cycle(s) detected".format(len(circular_deps)))
        if deprecation_warnings:
            report_parts.append(
                "{} deprecated skill(s): {}".format(
                    len(deprecation_warnings),
                    ", ".join(w["message"] for w in deprecation_warnings),
                )
            )

        return {
            "valid": valid,
            "conflicts": version_result["violations"],
            "circular_deps": circular_deps,
            "deprecation_warnings": deprecation_warnings,
            "report": " | ".join(report_parts),
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return statistics about the current cache state.

        Returns:
            Dict with memory_entries, disk_entries, skills_root
        """
        return {
            "memory_entries": len(self._cache),
            "disk_entries": self._count_disk_cache_entries(),
            "skills_root": str(self.skills_root),
        }

    def clear_memory_cache(self) -> None:
        """Clear the in-memory skill cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info("[SkillManager] Cleared in-memory cache ({} entries)".format(count))

    # -----------------------------------------------------------------------
    # Download with retry
    # -----------------------------------------------------------------------

    def _download_with_retry(self, skill_name: str) -> Dict[str, Any]:
        """Download a skill from GitHub with exponential backoff retry.

        Retry schedule: attempt 1 immediate, then 1s, 2s, 4s, 8s delays.
        Max 4 retries (5 total attempts).

        Args:
            skill_name: Skill to download.

        Returns:
            Dict with success (bool), content (str|None), attempts (int), error (str|None)
        """
        urls = self._build_candidate_urls(skill_name)
        last_error: str = "No candidate URLs found for '{}'".format(skill_name)
        attempts = 0

        for url in urls:
            for attempt in range(MAX_RETRIES + 1):
                attempts += 1
                delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else _RETRY_DELAYS[-1]

                if delay > 0:
                    logger.info(
                        "[SkillManager] Retry {}/{} for '{}' (delay={}s)".format(
                            attempt, MAX_RETRIES, skill_name, delay
                        )
                    )
                    time.sleep(delay)

                result = self._attempt_download(url)

                if result["success"]:
                    logger.info(
                        "[SkillManager] Downloaded '{}' from {} (attempt {}/{})".format(
                            skill_name, url, attempt + 1, MAX_RETRIES + 1
                        )
                    )
                    return {
                        "success": True,
                        "content": result["content"],
                        "attempts": attempts,
                        "error": None,
                        "url": url,
                    }

                last_error = result["error"]
                error_code = result.get("status_code", 0)

                if error_code == 404:
                    logger.debug("[SkillManager] 404 for '{}' at {}, trying next URL candidate".format(skill_name, url))
                    break

                logger.warning(
                    "[SkillManager] Download attempt {} failed for '{}': {}".format(attempt + 1, skill_name, last_error)
                )

        logger.error(
            "[SkillManager] All download attempts failed for '{}' ({} total attempts). Last error: {}".format(
                skill_name, attempts, last_error
            )
        )
        return {
            "success": False,
            "content": None,
            "attempts": attempts,
            "error": "Download failed after {} attempt(s): {}".format(attempts, last_error),
        }

    def _attempt_download(self, url: str) -> Dict[str, Any]:
        """Make a single HTTP GET request to download skill content.

        Args:
            url: Full URL to request.

        Returns:
            Dict with success (bool), content (str|None), error (str|None), status_code (int)
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "claude-workflow-engine-skill-manager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as response:
                raw = response.read()
                content = raw.decode("utf-8", errors="replace")
                return {"success": True, "content": content, "error": None, "status_code": 200}

        except urllib.error.HTTPError as exc:
            return {
                "success": False,
                "content": None,
                "error": "HTTP {}: {}".format(exc.code, exc.reason),
                "status_code": exc.code,
            }
        except urllib.error.URLError as exc:
            return {
                "success": False,
                "content": None,
                "error": "URL error: {}".format(exc.reason),
                "status_code": 0,
            }
        except OSError as exc:
            return {
                "success": False,
                "content": None,
                "error": "Network error: {}".format(exc),
                "status_code": 0,
            }

    def _build_candidate_urls(self, skill_name: str) -> List[str]:
        """Build list of candidate GitHub raw URLs for a skill.

        Tries multiple domain directories and both SKILL.md and skill.md filenames.

        Args:
            skill_name: Skill name to look up.

        Returns:
            Ordered list of candidate URLs to try.
        """
        urls: List[str] = []
        filenames = ["skill.md", "SKILL.md"]
        domains = SkillRegistry.all_domains_raw() or _DEFAULT_DOMAINS

        for domain in domains:
            for filename in filenames:
                url = "{}/skills/{}/{}/{}".format(self.github_raw_base, domain, skill_name, filename)
                urls.append(url)

        for filename in filenames:
            url = "{}/skills/{}/{}".format(self.github_raw_base, skill_name, filename)
            urls.append(url)

        return urls

    # -----------------------------------------------------------------------
    # Local sibling resolver tier (ADR-1)
    # -----------------------------------------------------------------------

    def _try_local_tier(self, skill_name: str) -> "tuple[Optional[str], Optional[str]]":
        """Probe the local-sibling resolver tier for a skill.

        Never raises: an invalid skill name or an absent local library is
        treated as a soft miss so the existing disk-cache / GitHub-download
        pipeline continues unchanged when the sibling library is unavailable.

        Args:
            skill_name: Skill to look up in the sibling library.

        Returns:
            Tuple of (content, source_path) on a hit, or (None, None) on a miss.
        """
        if self._local_adapter is None:
            return None, None
        try:
            resource = self._local_adapter.try_fetch_skill(skill_name)
        except ValueError as exc:
            logger.warning("[SkillManager] Invalid skill name for local tier '{}': {}".format(skill_name, exc))
            return None, None
        if resource is None:
            return None, None
        return resource.content, resource.path_or_url

    # -----------------------------------------------------------------------
    # Cache management
    # -----------------------------------------------------------------------

    def _get_from_memory_cache(
        self,
        skill_name: str,
        field: Optional[str] = None,
    ) -> Optional[Any]:
        """Retrieve a skill (or specific field) from in-memory cache.

        Args:
            skill_name: Skill to look up.
            field: If given, return only that field from the cache entry.

        Returns:
            Cache entry dict, specific field value, or None if not cached.
        """
        key = self._cache_key(skill_name)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if field:
            return entry.get(field)
        return entry

    def _store_in_memory_cache(self, skill_name: str, content: str) -> None:
        """Store skill content in in-memory cache with metadata."""
        key = self._cache_key(skill_name)
        meta = parse_skill_metadata(content, skill_name)
        version = self._extract_version(content)

        self._cache[key] = {
            "skill_name": skill_name,
            "content": content,
            "metadata": meta,
            "version": version,
            "timestamp": time.time(),
        }
        logger.debug("[SkillManager] Stored '{}' in memory cache (key={}...)".format(skill_name, key[:8]))

    def _load_from_disk(self, skill_name: str) -> Optional[str]:
        """Load skill content from disk cache.

        Searches all domain subdirectories and both filename conventions.

        Args:
            skill_name: Skill name to search for.

        Returns:
            Skill markdown content string, or None if not found on disk.
        """
        if not self.skills_root.exists():
            return None

        search_patterns = [
            "*/{}/skill.md".format(skill_name),
            "*/{}/SKILL.md".format(skill_name),
            "{}/skill.md".format(skill_name),
            "{}/SKILL.md".format(skill_name),
        ]

        for pattern in search_patterns:
            matches = list(self.skills_root.glob(pattern))
            if matches:
                try:
                    content = matches[0].read_text(encoding="utf-8")
                    logger.debug("[SkillManager] Loaded '{}' from disk: {}".format(skill_name, matches[0]))
                    return content
                except OSError as exc:
                    logger.warning("[SkillManager] Failed to read '{}': {}".format(matches[0], exc))

        return None

    def _save_to_disk(self, skill_name: str, content: str) -> bool:
        """Save skill content to disk cache.

        Saves to ~/.claude/skills/downloaded/<skill_name>/skill.md so the skill
        can be found by future disk cache lookups.

        Args:
            skill_name: Skill name (used as directory name).
            content: Skill markdown content to save.

        Returns:
            True if saved successfully, False on error.
        """
        skill_dir = self.skills_root / "downloaded" / skill_name
        skill_file = skill_dir / "skill.md"

        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file.write_text(content, encoding="utf-8")
            logger.debug("[SkillManager] Saved '{}' to disk: {}".format(skill_name, skill_file))
            return True
        except OSError as exc:
            logger.warning("[SkillManager] Failed to save '{}' to disk: {}".format(skill_name, exc))
            return False

    def _count_disk_cache_entries(self) -> int:
        """Count skill definitions currently on disk."""
        if not self.skills_root.exists():
            return 0
        patterns = ["*/*/skill.md", "*/*/SKILL.md", "*/skill.md", "*/SKILL.md"]
        found: set = set()
        for pattern in patterns:
            for p in self.skills_root.glob(pattern):
                found.add(p.parent)
        return len(found)

    # -----------------------------------------------------------------------
    # Dependency resolution
    # -----------------------------------------------------------------------

    def _resolve_all_dependencies(
        self,
        skill_names: List[str],
    ) -> Dict[str, Any]:
        """Resolve dependencies for a list of root skills.

        Collects all skill contents from disk/memory cache, then uses
        dependency_resolver to build the full dependency graph.

        Args:
            skill_names: Root skill names to resolve from.

        Returns:
            Dict with resolved (List[str]), unresolvable (List[str]), circular (List[List])
        """
        skill_contents: Dict[str, str] = {}

        for skill_name in skill_names:
            content = self._load_from_disk(skill_name)
            if content:
                skill_contents[skill_name] = content

        all_resolved: List[str] = []
        all_unresolvable: List[str] = []
        all_circular: List[List[str]] = []

        for root_skill in skill_names:
            if root_skill not in skill_contents:
                all_unresolvable.append(root_skill)
                continue

            result = resolve_dependencies(root_skill, skill_contents)
            for skill in result["resolved"]:
                if skill not in all_resolved:
                    all_resolved.append(skill)
            for skill in result["unresolvable"]:
                if skill not in all_unresolvable:
                    all_unresolvable.append(skill)
            for cycle in result["circular"]:
                if cycle not in all_circular:
                    all_circular.append(cycle)

        return {
            "resolved": all_resolved,
            "unresolvable": all_unresolvable,
            "circular": all_circular,
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _cache_key(skill_name: str) -> str:
        """Generate a stable cache key from a skill name."""
        return hashlib.md5(skill_name.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_version(skill_content: str) -> Optional[str]:
        """Extract version string from skill markdown content.

        Looks for patterns like:
            **Version:** 1.2.3
            version: 1.2.3
            # skill-name v1.2.3

        Returns:
            Version string or None if not found.
        """
        patterns = [
            r"\*\*Version\*\*:\s*([0-9][^\s\n]*)",
            r"^version:\s*([0-9][^\s\n]*)",
            r"v(\d+\.\d+(?:\.\d+)?)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, skill_content, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _build_result(
        self,
        skill_name: str,
        content: Optional[str],
        source: str,
        attempts: int,
        version: Optional[str] = None,
        metadata: Optional[Dict] = None,
        deprecated: bool = False,
        deprecation_info: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a standardized provision result dict."""
        if version is None and content:
            version = self._extract_version(content)
        if metadata is None and content:
            metadata = parse_skill_metadata(content, skill_name)
        if deprecation_info is None and content:
            dep_result = handle_deprecated(skill_name, content)
            deprecated = dep_result["is_deprecated"]
            deprecation_info = dep_result

        return {
            "success": content is not None,
            "skill_name": skill_name,
            "content": content,
            "version": version,
            "source": source,
            "attempts": attempts,
            "deprecated": deprecated,
            "deprecation_info": deprecation_info or {},
            "metadata": metadata or {},
            "error": error,
        }


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def get_skill_manager(
    skills_root: Optional[Path] = None,
) -> SkillManager:
    """Factory function to obtain a SkillManager instance.

    Args:
        skills_root: Optional override for skills storage root.

    Returns:
        SkillManager instance ready to use.

    Usage:
        manager = get_skill_manager()
        result = manager.provision_skill("python-backend-engineer")
    """
    return SkillManager(skills_root=skills_root)
