"""Resource resolver -- the local-path bridge between claude-workflow-engine
and its sibling claude-global-library.

Implements the ADR-1 3-tier Chain-of-Responsibility resolver documented in
docs/phase-1-architecture/hld.md Section 7.1 and ADR-1:

    1. Local sibling read at rolling disk state (no network, deterministic).
    2. Opt-in GitHub HTTP fallback (default off, ref-pinnable, retried with
       exponential backoff).
    3. Hard-fail with a typed LibrarySetupError naming the expected path and
       the override environment variable.

Callers depend on the ``ResourceResolver`` port; the concrete tiers
(``LocalSiblingAdapter`` / ``GitHubAdapter`` / ``HardFailAdapter``) are
Strategy implementations composed by ``build_default_resolver()``.
"""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENV_LIBRARY_PATH = "CLAUDE_GLOBAL_LIB_PATH"
ENV_ALLOW_GITHUB_FALLBACK = "CLAUDE_ALLOW_GITHUB_FALLBACK"
ENV_SKILL_REPO_URL = "CLAUDE_SKILL_REPO_URL"
ENV_GITHUB_OWNER = "CLAUDE_GITHUB_OWNER"

_SIBLING_DIR_NAME = "claude-global-library"
_DEFAULT_GITHUB_OWNER = "techdeveloper-org"

MAX_RETRIES: int = 4
RETRY_DELAYS: List[float] = [0, 1, 2, 4, 8]
_HTTP_TIMEOUT: int = 15

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_KG_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

_SKILL_FILENAMES = ("SKILL.md", "skill.md")
_AGENT_FILENAME = "agent.md"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LibrarySetupError(Exception):
    """Raised when no resolver tier can resolve a requested resource.

    Carries structured data so the caller can print an actionable message
    without inspecting a traceback.
    """

    def __init__(
        self,
        expected_local_path: Path,
        override_env_var: str = ENV_LIBRARY_PATH,
        detail: Optional[str] = None,
    ):
        self.expected_local_path = expected_local_path
        self.override_env_var = override_env_var
        self.detail = detail
        message = (
            f"claude-global-library not found. Expected sibling at: {expected_local_path}. "
            f"Set {override_env_var} to override, or set {ENV_ALLOW_GITHUB_FALLBACK}=1 "
            f"to allow an opt-in GitHub fallback."
        )
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


# ---------------------------------------------------------------------------
# Resolved resource value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedResource:
    """A resource successfully resolved by some tier of the chain."""

    name: str
    content: str
    source: str  # "local" | "github"
    path_or_url: str


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class ResourceResolver(Protocol):
    """Port consumed by SkillManager, ImportManager, KG readers, and the
    standards adapter. Concrete implementation: ``ChainedResourceResolver``.
    """

    def fetch_skill(self, skill_name: str) -> ResolvedResource: ...

    def fetch_agent(self, agent_name: str) -> ResolvedResource: ...

    def fetch_kg_file(self, relpath: str) -> ResolvedResource: ...


# ---------------------------------------------------------------------------
# Name / path validation (path traversal protection -- HLD Section 10)
# ---------------------------------------------------------------------------


def _validate_resource_name(name: str, kind: str) -> str:
    """Validate a skill/agent name against the safe filesystem-segment charset.

    Raises:
        ValueError: If ``name`` is empty or contains characters outside
            ``^[a-z0-9][a-z0-9-]*$`` (blocks path traversal via crafted names).
    """
    if not name or not _NAME_PATTERN.match(name):
        raise ValueError(f"Invalid {kind} '{name}': must match {_NAME_PATTERN.pattern}")
    return name


def _validate_kg_relpath(relpath: str) -> str:
    """Validate a knowledge-graph relative path segment-by-segment.

    Raises:
        ValueError: If any path segment is empty, ``.``, ``..``, or contains
            characters outside the safe charset (blocks path traversal).
    """
    if not relpath:
        raise ValueError("KG relpath must not be empty")
    segments = relpath.replace("\\", "/").split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError(f"Invalid KG relpath '{relpath}': path traversal segment '{segment}'")
        if not _KG_SEGMENT_PATTERN.match(segment):
            raise ValueError(f"Invalid KG relpath '{relpath}': disallowed characters in segment '{segment}'")
    return relpath


def _assert_within_root(path: Path, root: Path) -> Path:
    """Resolve ``path`` and assert it stays within ``root``.

    Raises:
        ValueError: If the resolved path escapes the library root.
    """
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise ValueError(f"Resolved path {resolved} escapes library root {resolved_root}") from None
    return resolved


# ---------------------------------------------------------------------------
# Sibling-path discovery (shared primitive -- HLD Section 4.2)
# ---------------------------------------------------------------------------

_library_root_cache: Dict[str, Optional[Path]] = {}


def locate_library_root(engine_root: Optional[Path] = None) -> Optional[Path]:
    """Resolve the claude-global-library sibling root, memoized per process.

    Resolution order:
        1. ``CLAUDE_GLOBAL_LIB_PATH`` env var, if set and the directory exists.
        2. ``{engine_root}/../claude-global-library``, if it exists.
        3. ``None`` if neither exists.

    Args:
        engine_root: Root of the claude-workflow-engine checkout. Defaults to
            three parents above this file (``langgraph_engine/library/resolver.py``).

    Returns:
        The resolved library root ``Path``, or ``None`` if no candidate exists.
    """
    override = os.environ.get(ENV_LIBRARY_PATH)
    cache_key = f"{override or ''}::{engine_root or ''}"
    if cache_key in _library_root_cache:
        return _library_root_cache[cache_key]

    if override:
        candidate = Path(override)
        if candidate.is_dir():
            _library_root_cache[cache_key] = candidate
            return candidate
        logger.warning(f"[resolver] {ENV_LIBRARY_PATH}={override} does not exist")

    root = engine_root or Path(__file__).resolve().parent.parent.parent
    default_candidate = root.parent / _SIBLING_DIR_NAME
    if default_candidate.is_dir():
        _library_root_cache[cache_key] = default_candidate
        return default_candidate

    _library_root_cache[cache_key] = None
    return None


def _reset_library_root_cache() -> None:
    """Test-only helper: clear the ``locate_library_root`` memoization cache."""
    _library_root_cache.clear()


# ---------------------------------------------------------------------------
# Tier 1: local sibling adapter
# ---------------------------------------------------------------------------


class LocalSiblingAdapter:
    """Reads skills/agents/kg-files directly from the sibling library at
    rolling disk state. Zero network calls.

    Casing contract: tries ``SKILL.md`` first, then ``skill.md``, for skills.
    Agents always use ``agent.md``.
    """

    def __init__(self, library_root: Path):
        self.library_root = library_root

    def try_fetch_skill(self, skill_name: str) -> Optional[ResolvedResource]:
        _validate_resource_name(skill_name, "skill_name")
        for filename in _SKILL_FILENAMES:
            candidate = self.library_root / "skills" / skill_name / filename
            content = self._read_if_exists(candidate)
            if content is not None:
                return ResolvedResource(name=skill_name, content=content, source="local", path_or_url=str(candidate))
        return None

    def try_fetch_agent(self, agent_name: str) -> Optional[ResolvedResource]:
        _validate_resource_name(agent_name, "agent_name")
        candidate = self.library_root / "agents" / agent_name / _AGENT_FILENAME
        content = self._read_if_exists(candidate)
        if content is not None:
            return ResolvedResource(name=agent_name, content=content, source="local", path_or_url=str(candidate))
        return None

    def try_fetch_kg_file(self, relpath: str) -> Optional[ResolvedResource]:
        _validate_kg_relpath(relpath)
        candidate = self.library_root / relpath
        content = self._read_if_exists(candidate)
        if content is not None:
            return ResolvedResource(name=relpath, content=content, source="local", path_or_url=str(candidate))
        return None

    def _read_if_exists(self, path: Path) -> Optional[str]:
        safe_path = _assert_within_root(path, self.library_root)
        if not safe_path.is_file():
            return None
        try:
            return safe_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(f"[LocalSiblingAdapter] Failed to read {safe_path}: {exc}")
            return None


# ---------------------------------------------------------------------------
# Tier 2: opt-in GitHub adapter
# ---------------------------------------------------------------------------


class GitHubAdapter:
    """Opt-in, pinnable HTTP fallback. Off by default; gated on
    ``CLAUDE_ALLOW_GITHUB_FALLBACK=1`` in ``build_default_resolver()``.

    Retry-with-backoff mirrors SkillManager's existing retry schedule
    (``MAX_RETRIES=4``, ``RETRY_DELAYS=[0,1,2,4,8]`` seconds -- see HLD
    Section 9.1) via the shared module-level constants above, so the two
    call paths always retry on the same numbers. The attempt loop itself is
    a separate, self-contained implementation targeting the library's real
    flat layout (``skills/{name}/SKILL.md``, ``agents/{name}/agent.md``)
    rather than SkillManager's domain-nested candidate-URL builder, which is
    reserved for SkillManager's own (separately scoped, untouched) GitHub tier.
    """

    def __init__(
        self,
        github_raw_base: str,
        timeout: int = _HTTP_TIMEOUT,
        sleep_fn: Any = time.sleep,
    ):
        self.github_raw_base = github_raw_base.rstrip("/")
        self.timeout = timeout
        self._sleep_fn = sleep_fn

    def try_fetch_skill(self, skill_name: str) -> Optional[ResolvedResource]:
        _validate_resource_name(skill_name, "skill_name")
        urls = [f"{self.github_raw_base}/skills/{skill_name}/{fn}" for fn in _SKILL_FILENAMES]
        return self._fetch_first(skill_name, urls)

    def try_fetch_agent(self, agent_name: str) -> Optional[ResolvedResource]:
        _validate_resource_name(agent_name, "agent_name")
        url = f"{self.github_raw_base}/agents/{agent_name}/{_AGENT_FILENAME}"
        return self._fetch_first(agent_name, [url])

    def try_fetch_kg_file(self, relpath: str) -> Optional[ResolvedResource]:
        _validate_kg_relpath(relpath)
        url = f"{self.github_raw_base}/{relpath}"
        return self._fetch_first(relpath, [url])

    def _fetch_first(self, name: str, urls: List[str]) -> Optional[ResolvedResource]:
        for url in urls:
            content = self._retry_download(url)
            if content is not None:
                return ResolvedResource(name=name, content=content, source="github", path_or_url=url)
        return None

    def _retry_download(self, url: str) -> Optional[str]:
        for attempt in range(MAX_RETRIES + 1):
            delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            if delay > 0:
                self._sleep_fn(delay)
            content, status_code = self._attempt(url)
            if content is not None:
                return content
            if status_code == 404:
                return None
        return None

    def _attempt(self, url: str) -> "tuple[Optional[str], int]":
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "claude-workflow-engine-resolver/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                return raw.decode("utf-8", errors="replace"), 200
        except urllib.error.HTTPError as exc:
            return None, exc.code
        except urllib.error.URLError as exc:
            logger.warning(f"[GitHubAdapter] URL error for {url}: {exc.reason}")
            return None, 0
        except OSError as exc:
            logger.warning(f"[GitHubAdapter] Network error for {url}: {exc}")
            return None, 0


# ---------------------------------------------------------------------------
# Tier 3: terminal hard-fail adapter
# ---------------------------------------------------------------------------


class HardFailAdapter:
    """Terminal tier of the chain. Always raises ``LibrarySetupError``."""

    def __init__(self, expected_local_path: Path, override_env_var: str = ENV_LIBRARY_PATH):
        self.expected_local_path = expected_local_path
        self.override_env_var = override_env_var

    def try_fetch_skill(self, skill_name: str) -> Optional[ResolvedResource]:
        raise LibrarySetupError(self.expected_local_path, self.override_env_var, detail=f"skill '{skill_name}'")

    def try_fetch_agent(self, agent_name: str) -> Optional[ResolvedResource]:
        raise LibrarySetupError(self.expected_local_path, self.override_env_var, detail=f"agent '{agent_name}'")

    def try_fetch_kg_file(self, relpath: str) -> Optional[ResolvedResource]:
        raise LibrarySetupError(self.expected_local_path, self.override_env_var, detail=f"kg file '{relpath}'")


# ---------------------------------------------------------------------------
# Chain-of-Responsibility resolver (the ResourceResolver port implementation)
# ---------------------------------------------------------------------------


class ChainedResourceResolver:
    """Chain-of-Responsibility resolver: local sibling -> opt-in GitHub -> hard-fail.

    Implements the ``ResourceResolver`` port (HLD Section 7.1). Tiers are
    tried in order; the first tier that resolves the resource wins. With a
    present local sibling, no network call ever occurs (determinism contract).
    """

    def __init__(self, tiers: List[Any]):
        if not tiers:
            raise ValueError("ChainedResourceResolver requires at least one tier")
        self._tiers = tiers

    def fetch_skill(self, skill_name: str) -> ResolvedResource:
        return self._resolve("try_fetch_skill", skill_name)

    def fetch_agent(self, agent_name: str) -> ResolvedResource:
        return self._resolve("try_fetch_agent", agent_name)

    def fetch_kg_file(self, relpath: str) -> ResolvedResource:
        return self._resolve("try_fetch_kg_file", relpath)

    def _resolve(self, method_name: str, arg: str) -> ResolvedResource:
        for tier in self._tiers:
            result = getattr(tier, method_name)(arg)
            if result is not None:
                return result
        raise LibrarySetupError(Path("<no local-sibling candidate configured>"))


def build_default_resolver(
    engine_root: Optional[Path] = None,
    github_raw_base: Optional[str] = None,
) -> ChainedResourceResolver:
    """Compose the standard ADR-1 3-tier chain from environment configuration.

    Tier 1: ``LocalSiblingAdapter``, included only if the sibling library is found.
    Tier 2: ``GitHubAdapter``, included only if ``CLAUDE_ALLOW_GITHUB_FALLBACK=1``.
    Tier 3: ``HardFailAdapter``, always present (terminal).

    Args:
        engine_root: Root of the claude-workflow-engine checkout, forwarded to
            ``locate_library_root()``.
        github_raw_base: Override for the GitHub raw-content base URL. Defaults
            to ``CLAUDE_SKILL_REPO_URL`` (or the standard raw.githubusercontent.com
            URL for ``CLAUDE_GITHUB_OWNER``).

    Returns:
        A ``ChainedResourceResolver`` ready to use as the ``ResourceResolver`` port.
    """
    root = engine_root or Path(__file__).resolve().parent.parent.parent
    library_root = locate_library_root(root)
    expected_path = library_root or (root.parent / _SIBLING_DIR_NAME)

    tiers: List[Any] = []
    if library_root is not None:
        tiers.append(LocalSiblingAdapter(library_root))

    if os.environ.get(ENV_ALLOW_GITHUB_FALLBACK) == "1":
        owner = os.environ.get(ENV_GITHUB_OWNER, _DEFAULT_GITHUB_OWNER)
        base = github_raw_base or os.environ.get(
            ENV_SKILL_REPO_URL,
            f"https://raw.githubusercontent.com/{owner}/claude-global-library/main",
        )
        tiers.append(GitHubAdapter(base))

    tiers.append(HardFailAdapter(expected_path, ENV_LIBRARY_PATH))
    return ChainedResourceResolver(tiers)
