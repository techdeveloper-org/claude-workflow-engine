"""
Design Patterns - Reusable patterns for the LangGraph Workflow Engine.

Pattern 1 (original): Memoize Decorator
  - TTL-based cache expiry (per-entry timestamps)
  - Key generation from function arguments (args + kwargs)
  - Thread-safe via threading.Lock
  - LRU eviction when cache exceeds max 100 entries
  - cache_clear() method on the decorated function

Pattern 2: Step Decorators (NEW)
  Composable decorators for LangGraph node functions (state: dict -> dict).
  Eliminates the boilerplate repeated in every step of level3_execution_v2:
  timing, try/catch, metrics recording, logging, timeout enforcement.

    @with_logging("step5")
    @with_metrics("step5_skill_selection")
    @with_timeout(120)
    @with_retry(max_attempts=3)
    def step5_skill_selection(state: dict) -> dict:
        # Pure business logic only - no boilerplate
        ...

Pattern 3: SkillRegistry (NEW)
  Dynamic skill/agent discovery and lookup.  Replaces the hardcoded
  _DEFAULT_DOMAINS list in skill_manager.py with a queryable registry.

    SkillRegistry.register("backend", "python-core", {"tags": ["python"]})
    skills = SkillRegistry.discover("backend.*")
    info = SkillRegistry.get("python-core")

ASCII-only source - cp1252 safe (Windows).
"""

from __future__ import annotations

import fnmatch
import functools
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Cache constants
# ---------------------------------------------------------------------------
_DEFAULT_TTL_SECONDS = 300  # 5 minutes
_DEFAULT_MAX_SIZE = 100  # Max entries before LRU eviction


# ---------------------------------------------------------------------------
# Internal cache entry
# ---------------------------------------------------------------------------
class _CacheEntry:
    """Single entry stored in the memoize cache."""

    __slots__ = ("value", "timestamp", "ttl")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.timestamp: float = time.monotonic()
        self.ttl: float = ttl

    def is_expired(self) -> bool:
        """Return True when the entry has lived past its TTL."""
        if self.ttl <= 0:
            return False  # ttl=0 means never expire
        return (time.monotonic() - self.timestamp) >= self.ttl


# ---------------------------------------------------------------------------
# Key generation helper
# ---------------------------------------------------------------------------
def _make_cache_key(args: tuple, kwargs: dict) -> str:
    """Stable, hashable cache key from positional and keyword arguments.

    Converts args + kwargs to a deterministic JSON string then hashes it
    with MD5 for a compact fixed-length key.  Falls back to repr() for
    types that are not JSON-serialisable.

    Args:
        args:   Positional arguments tuple.
        kwargs: Keyword arguments dict.

    Returns:
        Hex-digest string (32 chars).
    """
    try:
        raw = json.dumps({"args": list(args), "kwargs": kwargs}, sort_keys=True, default=repr)
    except Exception:
        raw = repr((args, sorted(kwargs.items())))
    return hashlib.md5(raw.encode("utf-8", errors="replace")).hexdigest()  # noqa: S324


# ---------------------------------------------------------------------------
# Memoize decorator
# ---------------------------------------------------------------------------
def memoize(
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    max_size: int = _DEFAULT_MAX_SIZE,
) -> Callable[[F], F]:
    """Decorator factory that caches function results with TTL and LRU eviction.

    Features:
    - TTL-based expiry: entries older than ttl_seconds are re-computed.
    - Key generation: stable hash of (args, kwargs).
    - Thread-safe: a per-instance threading.Lock guards all cache mutations.
    - LRU eviction: when cache reaches max_size, the least-recently-used
      entry is removed before inserting the new one.
    - cache_clear(): method injected on the decorated function to flush the
      entire cache manually.

    Args:
        ttl_seconds: How many seconds a cached value is valid.
                     0 or negative means "never expire".
        max_size:    Maximum number of entries before LRU eviction kicks in.
                     Must be >= 1.

    Returns:
        Decorator that wraps the target function.

    Example:
        @memoize(ttl_seconds=3600)
        def detect_framework(project_path: str) -> dict:
            # Expensive file scanning - runs at most once per hour per path
            ...
    """
    if max_size < 1:
        raise ValueError("max_size must be >= 1")

    def decorator(func: F) -> F:
        # OrderedDict preserves insertion order so we can do O(1) LRU moves.
        cache: OrderedDict = OrderedDict()
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_cache_key(args, kwargs)

            with lock:
                entry = cache.get(key)

                # Cache HIT - not expired
                if entry is not None and not entry.is_expired():
                    # Move to end to mark as most-recently-used
                    cache.move_to_end(key)
                    return entry.value

                # Cache MISS or EXPIRED - remove stale entry if present
                if entry is not None:
                    del cache[key]

            # Call original function outside the lock to avoid holding it
            # during potentially long I/O operations.
            result = func(*args, **kwargs)

            with lock:
                # LRU eviction: if at capacity, remove the oldest entry (front)
                while len(cache) >= max_size:
                    cache.popitem(last=False)

                cache[key] = _CacheEntry(value=result, ttl=float(ttl_seconds))

            return result

        def cache_clear() -> None:
            """Clear all cached entries for this function."""
            with lock:
                cache.clear()

        def cache_info() -> dict:
            """Return current cache size and max_size for introspection."""
            with lock:
                return {
                    "size": len(cache),
                    "max_size": max_size,
                    "ttl_seconds": ttl_seconds,
                }

        # Attach helpers directly to the decorated function
        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        wrapper._cache = cache  # type: ignore[attr-defined]
        wrapper._lock = lock  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


# ===========================================================================
# Pattern 2 - Step Decorators for LangGraph nodes
# ===========================================================================

# Type alias used across all four decorators
F = TypeVar("F", bound=Callable[..., Any])  # type: ignore[assignment]


try:
    from loguru import logger as _logger
except ImportError:
    import logging as _logging

    _logger = _logging.getLogger(__name__)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# @with_timeout(seconds)
# ---------------------------------------------------------------------------


def with_timeout(seconds: int) -> Callable[[F], F]:
    """Wrap a LangGraph node function with a per-invocation timeout.

    The node runs in a daemon thread.  If it does not complete within
    *seconds*, the main thread returns the original state unchanged (no
    partial updates) and injects a ``_timeout`` flag so downstream steps
    can detect the condition.

    Windows-compatible: uses threading.Thread, not SIGALRM.

    Args:
        seconds: Maximum allowed wall-clock time for the node.

    Returns:
        Decorator that adds timeout enforcement to any ``(state: dict) -> dict``
        function.

    Example::

        @with_timeout(120)
        def step5_skill_selection(state: dict) -> dict:
            ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            result_holder: Dict[str, Any] = {}
            exc_holder: Dict[str, Any] = {}

            def _target() -> None:
                try:
                    result_holder["value"] = fn(state)
                except Exception as exc:  # noqa: BLE001
                    exc_holder["error"] = exc

            t = threading.Thread(
                target=_target,
                daemon=True,
                name=f"timeout_{fn.__name__}",
            )
            t.start()
            t.join(timeout=seconds)

            if t.is_alive():
                _logger.warning(
                    "[with_timeout] '%s' exceeded %ss - returning state unchanged",
                    fn.__name__,
                    seconds,
                )
                fallback = dict(state)
                fallback["_timeout"] = True
                fallback["_timeout_step"] = fn.__name__
                fallback["_timeout_limit_s"] = seconds
                return fallback

            if "error" in exc_holder:
                raise exc_holder["error"]

            return result_holder.get("value", state)

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @with_metrics(step_name)
# ---------------------------------------------------------------------------


def with_metrics(step_name: str) -> Callable[[F], F]:
    """Record execution time and pass/fail status for a LangGraph node.

    Metrics are attached to the returned state dict under the key
    ``_metrics``, a list that accumulates entries across stacked decorators.
    Each entry is a plain dict so it survives JSON serialisation.

    Args:
        step_name: Human-readable label stored in the metric entry.

    Returns:
        Decorator that adds metrics collection to any node function.

    Example::

        @with_metrics("step5_skill_selection")
        def step5_skill_selection(state: dict) -> dict:
            ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            start = time.perf_counter()
            status = "SUCCESS"
            error_msg: Optional[str] = None
            result: Dict[str, Any] = {}

            try:
                result = fn(state)
                return result
            except Exception as exc:  # noqa: BLE001
                status = "FAILED"
                error_msg = str(exc)
                result = dict(state)
                result["_error"] = error_msg
                raise
            finally:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                entry: Dict[str, Any] = {
                    "step_name": step_name,
                    "status": status,
                    "elapsed_ms": elapsed_ms,
                }
                if error_msg:
                    entry["error"] = error_msg

                # Accumulate metrics in state so they survive across steps
                if isinstance(result, dict):
                    metrics_list = list(result.get("_metrics") or [])
                    metrics_list.append(entry)
                    result["_metrics"] = metrics_list

                _logger.debug("[with_metrics] %s => %s (%sms)", step_name, status, elapsed_ms)

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @with_retry(max_attempts, backoff)
# ---------------------------------------------------------------------------


def with_retry(
    max_attempts: int = 3,
    backoff: float = 1.0,
) -> Callable[[F], F]:
    """Retry a LangGraph node on exception with exponential backoff.

    Attempts: 1 (immediate), 2 (backoff * 1), 3 (backoff * 2), ...
    The last attempt re-raises the exception if it still fails.

    Args:
        max_attempts: Total number of attempts including the first call.
        backoff:      Base delay in seconds.  Delay doubles on each retry.

    Returns:
        Decorator that adds retry logic to any node function.

    Example::

        @with_retry(max_attempts=3, backoff=1.0)
        def step6_skill_validation(state: dict) -> dict:
            ...
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            delay = backoff
            last_exc: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(state)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < max_attempts:
                        _logger.warning(
                            "[with_retry] '%s' attempt %d/%d failed (%s). " "Retrying in %.1fs...",
                            fn.__name__,
                            attempt,
                            max_attempts,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= 2
                    else:
                        _logger.error(
                            "[with_retry] '%s' failed after %d attempt(s): %s",
                            fn.__name__,
                            max_attempts,
                            exc,
                        )

            # last_exc is always set when max_attempts >= 1 and the loop
            # exhausts without a successful return.
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @with_logging(step_name)
# ---------------------------------------------------------------------------


def with_logging(step_name: str) -> Callable[[F], F]:
    """Log start, end, and any error for a LangGraph node.

    Provides consistent log lines without polluting the step function body.
    Compatible with both loguru and stdlib logging.

    Args:
        step_name: Label printed in log lines.

    Returns:
        Decorator that adds structured logging to any node function.

    Example::

        @with_logging("step5")
        def step5_skill_selection(state: dict) -> dict:
            ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            _logger.info("[%s] START", step_name)
            start = time.perf_counter()

            try:
                result = fn(state)
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                _logger.info("[%s] END OK (%sms)", step_name, elapsed_ms)
                return result
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                _logger.error("[%s] END ERROR (%sms): %s", step_name, elapsed_ms, exc)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


# ===========================================================================
# Pattern 3 - SkillRegistry
# ===========================================================================


@dataclass
class SkillInfo:
    """Metadata record for a registered skill or agent.

    Attributes:
        domain:         Domain category (e.g. "backend", "frontend").
        name:           Skill identifier (e.g. "python-core").
        metadata:       Arbitrary key/value metadata dict.
        registered_at:  Unix timestamp of registration.
    """

    domain: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)


class SkillRegistry:
    """Thread-safe registry for dynamic skill and agent discovery.

    This class uses class-level state so all callers share a single registry
    within a process.  All public methods acquire a threading.Lock so the
    registry is safe for concurrent reads and writes.

    Design decisions
    ----------------
    - ``register`` is idempotent: registering the same (domain, name) pair
      again updates metadata instead of raising an error.
    - ``discover`` accepts glob patterns (fnmatch), allowing callers to
      filter by domain, name prefix, or both.
    - ``get`` returns the first registered entry whose ``name`` matches exactly.

    Backward compatibility
    ----------------------
    ``register_defaults()`` seeds the registry with the same eight domains
    that were hardcoded in ``skill_manager._DEFAULT_DOMAINS``.  Existing
    code that iterates ``_DEFAULT_DOMAINS`` can be replaced with::

        domains = SkillRegistry.all_domains_raw()

    This method returns exactly the same list as the old constant.

    Example::

        SkillRegistry.register("backend", "python-core", {"tags": ["python"]})
        SkillRegistry.register("backend", "flask-api", {"tags": ["web"]})

        backend_skills = SkillRegistry.discover("backend")
        info = SkillRegistry.get("python-core")
        print(info.domain, info.name)
    """

    # Class-level registry: {domain: {name: SkillInfo}}
    _registry: Dict[str, Dict[str, SkillInfo]] = {}
    _lock: threading.Lock = threading.Lock()

    # ---------------------------------------------------------------------------
    # Write operations
    # ---------------------------------------------------------------------------

    @classmethod
    def register(
        cls,
        domain: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillInfo:
        """Register a skill under a domain with optional metadata.

        Calling this method a second time with the same (domain, name) pair
        updates the metadata rather than raising an error (idempotent).

        Args:
            domain:   Domain category string (e.g. "backend").
            name:     Unique skill name within the domain (e.g. "python-core").
            metadata: Optional dict with extra attributes (tags, path, version).

        Returns:
            The SkillInfo that was registered or updated.
        """
        info = SkillInfo(domain=domain, name=name, metadata=metadata or {})
        with cls._lock:
            if domain not in cls._registry:
                cls._registry[domain] = {}
            existing = cls._registry[domain].get(name)
            if existing is not None:
                existing.metadata.update(metadata or {})
                _logger.debug("[SkillRegistry] Updated '%s/%s'", domain, name)
                return existing
            cls._registry[domain][name] = info
            _logger.debug("[SkillRegistry] Registered '%s/%s'", domain, name)
        return info

    @classmethod
    def register_defaults(cls) -> None:
        """Seed the registry with the default domain list from skill_manager.

        Preserves backward compatibility: any code that previously relied on
        ``_DEFAULT_DOMAINS`` can call ``SkillRegistry.all_domains_raw()``
        instead and get the same list.

        Domains registered (matches skill_manager._DEFAULT_DOMAINS):
            backend, frontend, devops, data, mobile, security, testing, core
        """
        defaults = [
            "backend",
            "frontend",
            "devops",
            "data",
            "mobile",
            "security",
            "testing",
            "core",
        ]
        for domain in defaults:
            # Register a placeholder so the domain appears in all_domains_raw()
            # even before real skills are added to it.
            cls.register(
                domain,
                f"_domain_{domain}",
                {"type": "domain_placeholder"},
            )
        _logger.debug("[SkillRegistry] Registered %d default domains", len(defaults))

    # ---------------------------------------------------------------------------
    # Read operations
    # ---------------------------------------------------------------------------

    @classmethod
    def discover(cls, pattern: str) -> List[SkillInfo]:
        """Return all SkillInfo entries matching a glob pattern.

        The pattern is matched against the string ``"<domain>/<name>"``.
        Standard fnmatch wildcards apply (``*`` matches any sequence except
        nothing special about ``/``).

        Special shorthand: a bare domain name without ``/`` (e.g. ``"backend"``)
        is automatically expanded to ``"backend/*"``.

        Placeholder entries (registered by ``register_defaults``) are excluded
        from results.

        Args:
            pattern: Glob pattern matched against ``"domain/name"`` strings.
                     Examples: ``"backend"``, ``"backend/*"``, ``"*python*"``.

        Returns:
            Sorted list of matching SkillInfo objects (domain asc, name asc).
        """
        if "/" not in pattern:
            pattern = pattern + "/*"

        results: List[SkillInfo] = []
        with cls._lock:
            for domain, skills in cls._registry.items():
                for name, info in skills.items():
                    if info.metadata.get("type") == "domain_placeholder":
                        continue
                    candidate = f"{domain}/{name}"
                    if fnmatch.fnmatch(candidate, pattern):
                        results.append(info)

        results.sort(key=lambda x: (x.domain, x.name))
        return results

    @classmethod
    def get(cls, name: str) -> Optional[SkillInfo]:
        """Return the first SkillInfo whose name matches exactly.

        Searches all domains in insertion order.  Returns None if no skill
        with that name exists.  Placeholder entries are excluded.

        Args:
            name: Exact skill name to look up (e.g. "python-core").

        Returns:
            Matching SkillInfo or None.
        """
        with cls._lock:
            for _domain, skills in cls._registry.items():
                if name in skills:
                    info = skills[name]
                    if info.metadata.get("type") != "domain_placeholder":
                        return info
        return None

    @classmethod
    def all_domains_raw(cls) -> List[str]:
        """Return a sorted list of all registered domain names.

        This is the drop-in replacement for ``_DEFAULT_DOMAINS`` in
        skill_manager.  After ``register_defaults()`` is called (which happens
        automatically on module import), this method returns the same list.

        Returns:
            Sorted list of domain strings.
        """
        with cls._lock:
            return sorted(cls._registry.keys())

    @classmethod
    def all_domains(cls) -> List[str]:
        """Return sorted domain names that contain at least one real skill.

        Domains that only hold placeholder entries (added by
        ``register_defaults``) are included so that the returned list still
        matches ``_DEFAULT_DOMAINS`` for URL-building purposes.

        Returns:
            Sorted list of domain strings.
        """
        return cls.all_domains_raw()

    @classmethod
    def clear(cls) -> None:
        """Remove all entries from the registry.

        Primarily useful in tests to reset global state between test cases.
        """
        with cls._lock:
            cls._registry.clear()
        _logger.debug("[SkillRegistry] Registry cleared")

    @classmethod
    def size(cls) -> int:
        """Return the total number of registered entries (including placeholders)."""
        with cls._lock:
            return sum(len(skills) for skills in cls._registry.values())


# ---------------------------------------------------------------------------
# Auto-seed the registry with backward-compatible defaults on module import.
# Ensures SkillRegistry.all_domains_raw() always returns the same list that
# _DEFAULT_DOMAINS provided, even before any explicit register() calls.
# ---------------------------------------------------------------------------

SkillRegistry.register_defaults()
