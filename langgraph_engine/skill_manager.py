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
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from utils.path_resolver import get_skills_dir

    _SKILLS_ROOT_DEFAULT = get_skills_dir()
except ImportError:
    _SKILLS_ROOT_DEFAULT = Path.home() / ".claude" / "skills"

from .dependency_resolver import build_dependency_graph, detect_circular, parse_skill_metadata, resolve_dependencies
from .patterns import SkillRegistry
from .version_selector import handle_deprecated, validate_version_set

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Retry configuration - exponential backoff delays (seconds)
_RETRY_DELAYS: List[float] = [0, 1, 2, 4, 8]  # Index = attempt number (0-based)
MAX_RETRIES: int = 4  # Max number of retries after initial attempt = 5 total attempts

# GitHub raw base URL for skill downloads (configurable via env var)
_GITHUB_OWNER = os.environ.get("CLAUDE_GITHUB_OWNER", "techdeveloper-org")
_GITHUB_RAW_BASE = os.environ.get(
    "CLAUDE_SKILL_REPO_URL", f"https://raw.githubusercontent.com/{_GITHUB_OWNER}/claude-global-library/main"
)

# Default domains - hardcoded fallback for backward compatibility.
# New code should call SkillRegistry.all_domains_raw() at call time (not import time).
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

# Timeout for HTTP requests in seconds
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
    ):
        """Initialize SkillManager.

        Args:
            skills_root: Root directory for skill storage. Defaults to ~/.claude/skills/
            github_raw_base: Base URL for GitHub raw content downloads.
        """
        self.skills_root = skills_root or _SKILLS_ROOT_DEFAULT
        self.github_raw_base = github_raw_base.rstrip("/")

        # In-memory cache: {cache_key: {"content": str, "metadata": dict, "timestamp": float}}
        self._cache: Dict[str, Dict[str, Any]] = {}

        logger.info(f"[SkillManager] Initialized: skills_root={self.skills_root}, " f"cache_size={len(self._cache)}")

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

        This is the primary entry point for skill acquisition. It:
        1. Checks in-memory cache
        2. Checks disk cache (existing skill files)
        3. Downloads from GitHub with exponential-backoff retry
        4. Validates the downloaded skill
        5. Caches on success

        Args:
            skill_name: Skill name to provision (e.g., "python-backend-engineer").
            version_req: Version requirement specifier (e.g., ">=1.0.0", "*").
            force_download: Skip cache and always download fresh copy.

        Returns:
            Dict with:
                success (bool)           - True if skill is ready to use
                skill_name (str)         - Name of the skill
                content (Optional[str])  - Full skill markdown content
                version (Optional[str])  - Version of the skill (if detectable)
                source (str)             - "memory_cache" | "disk_cache" | "download" | "failed"
                attempts (int)           - Number of download attempts made
                deprecated (bool)        - True if skill is deprecated
                deprecation_info (Dict)  - Deprecation details if deprecated
                error (Optional[str])    - Error message if success=False
        """
        logger.info(f"[SkillManager] Provisioning skill '{skill_name}' (req: {version_req})")

        # 1. Check in-memory cache
        if not force_download:
            cached = self._get_from_memory_cache(skill_name)
            if cached:
                logger.info(f"[SkillManager] Memory cache hit for '{skill_name}'")
                return self._build_result(
                    skill_name=skill_name,
                    content=cached["content"],
                    source="memory_cache",
                    attempts=0,
                    version=cached.get("version"),
                    metadata=cached.get("metadata"),
                )

        # 2. Check disk cache
        if not force_download:
            disk_content = self._load_from_disk(skill_name)
            if disk_content:
                logger.info(f"[SkillManager] Disk cache hit for '{skill_name}'")
                self._store_in_memory_cache(skill_name, disk_content)
                return self._build_result(
                    skill_name=skill_name,
                    content=disk_content,
                    source="disk_cache",
                    attempts=0,
                )

        # 3. Download with retry
        download_result = self._download_with_retry(skill_name)

        if not download_result["success"]:
            # 4. If download completely failed, try disk cache as last resort
            disk_fallback = self._load_from_disk(skill_name)
            if disk_fallback:
                logger.warning(f"[SkillManager] Download failed for '{skill_name}', " f"falling back to disk cache")
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

        # 5. Check for deprecation
        dep_info = handle_deprecated(skill_name, content)

        # 6. Cache the downloaded skill
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
            Dict with:
                provisioned (Dict[str, Dict])  - {skill_name: provision_result}
                all_success (bool)             - True if all skills provisioned OK
                failed (List[str])             - Skills that failed to provision
                dependency_order (List[str])   - Topological order of skills
                circular_deps (List[List])     - Any circular dependencies detected
        """
        version_requirements = version_requirements or {}
        provisioned: Dict[str, Dict] = {}
        failed: List[str] = []
        all_skill_names = list(skill_names)

        # Resolve dependencies if requested
        dependency_order: List[str] = skill_names[:]
        circular_deps: List[List[str]] = []

        if resolve_deps and skill_names:
            dep_result = self._resolve_all_dependencies(skill_names)
            dependency_order = dep_result.get("resolved", skill_names)
            circular_deps = dep_result.get("circular", [])
            # Add any newly discovered dep names to provision
            for name in dependency_order:
                if name not in all_skill_names:
                    all_skill_names.append(name)

        # Provision in dependency order (deps first)
        for skill_name in dependency_order:
            req = version_requirements.get(skill_name, "*")
            result = self.provision_skill(skill_name, version_req=req)
            provisioned[skill_name] = result
            if not result["success"]:
                failed.append(skill_name)

        all_success = len(failed) == 0

        logger.info(
            f"[SkillManager] Batch provisioning: {len(provisioned)} total, "
            f"{len(failed)} failed, circular={len(circular_deps)}"
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
            Dict with:
                valid (bool)                - True if all skills can coexist
                conflicts (List[Dict])      - Version conflicts found
                circular_deps (List[List])  - Circular dependency cycles
                deprecation_warnings (List) - Deprecated skills in the set
                report (str)                - Summary report
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

        # Check circular dependencies
        dep_graph = build_dependency_graph(skill_names, skill_contents)
        circular_deps = detect_circular(dep_graph)

        # Build version requirements from skill metadata
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
            report_parts.append(f"{len(circular_deps)} circular dependency cycle(s) detected")
        if deprecation_warnings:
            report_parts.append(
                f"{len(deprecation_warnings)} deprecated skill(s): "
                + ", ".join(w["message"] for w in deprecation_warnings)
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
            Dict with memory_entries, disk_entries, total_size_kb
        """
        memory_entries = len(self._cache)
        disk_entries = self._count_disk_cache_entries()

        return {
            "memory_entries": memory_entries,
            "disk_entries": disk_entries,
            "skills_root": str(self.skills_root),
        }

    def clear_memory_cache(self) -> None:
        """Clear the in-memory skill cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"[SkillManager] Cleared in-memory cache ({count} entries)")

    # -----------------------------------------------------------------------
    # Download with retry
    # -----------------------------------------------------------------------

    def _download_with_retry(self, skill_name: str) -> Dict[str, Any]:
        """Download a skill from GitHub with exponential backoff retry.

        Retry schedule:
            Attempt 1: immediate
            Attempt 2: 1s delay
            Attempt 3: 2s delay
            Attempt 4: 4s delay
            Attempt 5: 8s delay
        Max 4 retries (5 total attempts).

        Args:
            skill_name: Skill to download.

        Returns:
            Dict with success (bool), content (str|None), attempts (int), error (str|None)
        """
        urls = self._build_candidate_urls(skill_name)
        last_error: str = f"No candidate URLs found for '{skill_name}'"
        attempts = 0

        for url in urls:
            for attempt in range(MAX_RETRIES + 1):
                attempts += 1
                delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else _RETRY_DELAYS[-1]

                if delay > 0:
                    logger.info(f"[SkillManager] Retry {attempt}/{MAX_RETRIES} for '{skill_name}' " f"(delay={delay}s)")
                    time.sleep(delay)

                result = self._attempt_download(url)

                if result["success"]:
                    logger.info(
                        f"[SkillManager] Downloaded '{skill_name}' from {url} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES + 1})"
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

                # Do not retry on 404 (skill doesn't exist at this URL)
                if error_code == 404:
                    logger.debug(f"[SkillManager] 404 for '{skill_name}' at {url}, " f"trying next URL candidate")
                    break  # Try next URL candidate

                logger.warning(
                    f"[SkillManager] Download attempt {attempt + 1} failed for '{skill_name}': " f"{last_error}"
                )

        logger.error(
            f"[SkillManager] All download attempts failed for '{skill_name}' "
            f"({attempts} total attempts). Last error: {last_error}"
        )
        return {
            "success": False,
            "content": None,
            "attempts": attempts,
            "error": f"Download failed after {attempts} attempt(s): {last_error}",
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
                headers={"User-Agent": "claude-insight-skill-manager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as response:
                raw = response.read()
                content = raw.decode("utf-8", errors="replace")
                return {"success": True, "content": content, "error": None, "status_code": 200}

        except urllib.error.HTTPError as exc:
            return {
                "success": False,
                "content": None,
                "error": f"HTTP {exc.code}: {exc.reason}",
                "status_code": exc.code,
            }
        except urllib.error.URLError as exc:
            return {
                "success": False,
                "content": None,
                "error": f"URL error: {exc.reason}",
                "status_code": 0,
            }
        except OSError as exc:
            return {
                "success": False,
                "content": None,
                "error": f"Network error: {exc}",
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

        # Use SkillRegistry for dynamic domain discovery.
        # Falls back to the module-level _DEFAULT_DOMAINS if registry is empty,
        # which preserves the original behaviour when no extra domains are added.
        domains = SkillRegistry.all_domains_raw() or _DEFAULT_DOMAINS

        for domain in domains:
            for filename in filenames:
                url = f"{self.github_raw_base}/skills/{domain}/{skill_name}/{filename}"
                urls.append(url)

        # Also try a flat (no domain) path
        for filename in filenames:
            url = f"{self.github_raw_base}/skills/{skill_name}/{filename}"
            urls.append(url)

        return urls

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
        logger.debug(f"[SkillManager] Stored '{skill_name}' in memory cache (key={key[:8]}...)")

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

        # Search domain subdirectories
        search_patterns = [
            f"*/{skill_name}/skill.md",
            f"*/{skill_name}/SKILL.md",
            f"{skill_name}/skill.md",
            f"{skill_name}/SKILL.md",
        ]

        for pattern in search_patterns:
            matches = list(self.skills_root.glob(pattern))
            if matches:
                try:
                    content = matches[0].read_text(encoding="utf-8")
                    logger.debug(f"[SkillManager] Loaded '{skill_name}' from disk: {matches[0]}")
                    return content
                except OSError as exc:
                    logger.warning(f"[SkillManager] Failed to read '{matches[0]}': {exc}")

        return None

    def _save_to_disk(self, skill_name: str, content: str) -> bool:
        """Save skill content to disk cache.

        Saves to ~/.claude/skills/downloaded/<skill_name>/skill.md
        This allows the skill to be found by future disk cache lookups.

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
            logger.debug(f"[SkillManager] Saved '{skill_name}' to disk: {skill_file}")
            return True
        except OSError as exc:
            logger.warning(f"[SkillManager] Failed to save '{skill_name}' to disk: {exc}")
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
        # Load all available skill contents for dependency graph
        skill_contents: Dict[str, str] = {}

        # First pass: load the requested skills
        for skill_name in skill_names:
            content = self._load_from_disk(skill_name)
            if content:
                skill_contents[skill_name] = content

        # Second pass: iteratively load dependencies
        # (simplified - in production would recursively discover)
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
        import re

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
