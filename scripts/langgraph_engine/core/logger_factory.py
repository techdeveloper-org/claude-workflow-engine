"""Centralised logger factory for consistent logging across all pipeline modules.

Before this module existed, 25+ files each contained the same boilerplate:

    try:
        from loguru import logger
    except ImportError:
        import logging
        logger = logging.getLogger(__name__)

get_logger() replaces that pattern.  When loguru is installed it returns the
shared loguru logger (which is already a module-level singleton).  When loguru
is unavailable it returns a stdlib logging.Logger scoped to the caller's
module name, mirroring the behaviour that the original boilerplate provided.

Design note: loguru uses a single global logger object; multiple callers that
call get_logger() without a name argument all receive the same loguru instance.
For stdlib fallback, a named Logger is returned so that each module has its own
logging namespace and can be filtered independently.
"""

import logging
from typing import Any, Optional


def get_logger(name: Optional[str] = None) -> Any:
    """Return a logger instance using loguru when available, stdlib otherwise.

    Args:
        name: Module name used for the stdlib fallback logger.  When None the
              function attempts to determine the caller's __name__ via the
              call stack.  Explicit values are always preferred.

    Returns:
        A loguru Logger when loguru is installed, or a stdlib logging.Logger.
    """
    try:
        from loguru import logger as _loguru_logger
        return _loguru_logger
    except ImportError:
        pass

    # Loguru not available - fall back to stdlib.
    if name is None:
        import inspect
        frame = inspect.currentframe()
        caller_name = __name__
        if frame is not None and frame.f_back is not None:
            caller_name = frame.f_back.f_globals.get("__name__", __name__)
        name = caller_name

    return logging.getLogger(name)
