"""
Diagrams package - Modular UML diagram generators (Strategy + Factory patterns).
Also includes DrawioConverter for generating editable .drawio files.

Each concrete generator lives in its own module and self-registers with
DiagramFactory at import time via a deferred _register() call.

Usage:
    from langgraph_engine.diagrams import DiagramFactory

    gen = DiagramFactory.create("class")
    markup = gen.generate(analysis_data)

    # Or bulk generation:
    results = DiagramFactory.generate_all(analysis_data)
"""

import logging

logger = logging.getLogger(__name__)


class DiagramFactory:
    """Registry and factory for UML diagram generators.

    Concrete generators self-register at import time.  Callers use
    DiagramFactory.create(diagram_type) to get the right generator.
    """

    _registry = {}  # type: dict

    @classmethod
    def register(cls, diagram_type, generator_class):
        # type: (str, type) -> None
        """Register a generator class for a diagram type."""
        cls._registry[diagram_type] = generator_class
        logger.debug("DiagramFactory: registered '%s'", diagram_type)

    @classmethod
    def create(cls, diagram_type):
        """Create and return a generator instance for diagram_type.

        Raises KeyError if the type is not registered.
        """
        if diagram_type not in cls._registry:
            raise KeyError("Unknown diagram type '%s'. Available: %s" % (diagram_type, sorted(cls._registry.keys())))
        return cls._registry[diagram_type]()

    @classmethod
    def available_types(cls):
        # type: () -> list
        """Return sorted list of registered diagram type names."""
        return sorted(cls._registry.keys())

    @classmethod
    def generate_all(cls, analysis_data, format="mermaid"):
        # type: (dict, str) -> dict
        """Generate all registered diagram types.

        Returns dict mapping diagram_type -> markup string.
        Failures per diagram are caught and logged; other diagrams continue.
        """
        results = {}
        for dtype, gen_cls in cls._registry.items():
            try:
                gen = gen_cls()
                results[dtype] = gen.generate(analysis_data, format=format)
            except Exception as e:
                logger.warning("DiagramFactory.generate_all: '%s' failed: %s", dtype, e)
                results[dtype] = ""
        return results


# ------------------------------------------------------------------
# Import all concrete generators so they self-register.
# Import errors are caught individually to avoid blocking the whole
# package when a single module has a dependency problem.
# ------------------------------------------------------------------


def _import_generators():
    """Import all generator modules so they call _register()."""
    _modules = [
        ".class_diagram",
        ".sequence_diagram",
        ".activity_diagram",
        ".state_diagram",
        ".component_diagram",
        ".package_diagram",
        ".usecase_diagram",
        ".object_diagram",
        ".deployment_diagram",
        ".communication_diagram",
        ".composite_diagram",
        ".interaction_diagram",
    ]
    for mod in _modules:
        try:
            import importlib

            importlib.import_module(mod, package=__name__)
        except Exception as e:
            logger.debug("diagrams: could not import %s: %s", mod, e)


_import_generators()

# DrawioConverter is importable directly:
#   from langgraph_engine.diagrams.drawio_converter import DrawioConverter
