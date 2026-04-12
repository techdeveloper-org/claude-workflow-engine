"""Backward-compat shim for uml_generators.py.

All diagram generation logic has been refactored into the diagrams/ package.
This file re-exports all public symbols so existing imports keep working.

Windows-safe: ASCII only, no Unicode characters.
"""

from .diagrams import DiagramFactory  # noqa: F401
from .diagrams.ast_analyzer import UMLAstAnalyzer  # noqa: F401
from .diagrams.kroki_renderer import KrokiRenderer  # noqa: F401
from .diagrams.legacy_generator import UMLDiagramGenerator  # noqa: F401
from .diagrams.legacy_generator import (  # noqa: F401
    _clean_mermaid,
    _clean_plantuml,
    _make_attr_info,
    _make_class_info,
    _make_method_info,
    _plantuml_stub,
    _simplify_type,
)
