"""Lazy module import factory with graceful degradation.

This module centralises the repeated lazy-import pattern found in 20+ pipeline
files.  Before this module existed each file contained its own variant of:

    def _get_something():
        try:
            from ..module import Class
            return Class
        except Exception:
            return None

The LazyLoader class replaces all of those with a single, cached, thread-safe
implementation.

Design pattern: Factory Method (GoF) - LazyLoader.load() acts as a factory
that creates instances of arbitrary classes on demand, caching the resolved
class between calls to avoid repeated importlib lookups.
"""

import importlib
from typing import Any, Optional


class LazyLoader:
    """Factory for lazy module imports with graceful degradation.

    All resolved classes are cached in a module-level dict so that repeated
    calls with the same module_path + class_name only pay the importlib cost
    once.  A cached value of None means the import previously failed; this
    prevents repeated import attempts for permanently unavailable modules.
    """

    _cache: dict = {}

    @classmethod
    def load(cls, module_path: str, class_name: str, *args: Any, **kwargs: Any) -> Optional[Any]:
        """Lazy-load a class from a dotted module path and optionally instantiate it.

        Args:
            module_path: Dotted module path, e.g.
                         'langgraph_engine.checkpoint_manager'
            class_name:  Name of the class to import, e.g. 'CheckpointManager'
            *args:       Positional constructor arguments.  When provided the
                         method returns an instance rather than the class itself.
            **kwargs:    Keyword constructor arguments.

        Returns:
            An instance of the class when args or kwargs are provided.
            The class object itself when called with no constructor arguments.
            None if the import or instantiation fails.
        """
        cache_key = "%s.%s" % (module_path, class_name)

        if cache_key in cls._cache:
            cached_cls = cls._cache[cache_key]
            if cached_cls is None:
                return None
            try:
                return cached_cls(*args, **kwargs) if (args or kwargs) else cached_cls
            except Exception:
                return None

        try:
            module = importlib.import_module(module_path)
            klass = getattr(module, class_name)
            cls._cache[cache_key] = klass
            return klass(*args, **kwargs) if (args or kwargs) else klass
        except Exception:
            cls._cache[cache_key] = None
            return None

    @classmethod
    def load_function(cls, module_path: str, func_name: str) -> Any:
        """Lazy-load a function from a module path.

        Unlike load(), this method is designed for standalone functions rather
        than classes.  If the import fails a no-op lambda is returned so that
        callers can always call the result without guarding against None.

        Args:
            module_path: Dotted module path.
            func_name:   Name of the function to import.

        Returns:
            The function, or a no-op lambda if the import fails.
        """
        cache_key = "%s.%s" % (module_path, func_name)

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            cls._cache[cache_key] = func
            return func
        except Exception:
            noop = lambda *a, **kw: None  # noqa: E731
            cls._cache[cache_key] = noop
            return noop

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the import cache.

        Intended for use in tests to reset module resolution state between
        test cases.  Should not be called in production code.
        """
        cls._cache.clear()
