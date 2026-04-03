"""Backward-compat shim for drawio_converter.py.

All DrawIO logic has been refactored into the drawio/ sub-package.
This file re-exports all public symbols so existing imports keep working.
"""

from .drawio import (  # noqa: F401
    DrawioConverter,
    _edge,
    _edge_points,
    _encode_drawio_url,
    _esc,
    _IDGen,
    _vertex,
    _vertex_child,
    _wrap_mxfile,
    get_shareable_url,
)
