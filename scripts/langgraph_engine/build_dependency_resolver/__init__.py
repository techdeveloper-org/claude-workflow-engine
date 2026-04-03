"""Build dependency resolver package.
Refactored from monolithic build_dependency_resolver.py.
All symbols re-exported for backward compatibility.
"""

from .parsers import (  # noqa: F401
    _parse_cargo_deps,
    _parse_go_deps,
    _parse_gradle_deps,
    _parse_maven_deps,
    _parse_npm_deps,
    _parse_python_deps,
    _parse_raw_deps,
    _parse_req_line,
    _read_pyproject_deps,
)
from .resolver import (  # noqa: F401
    detect_build_system,
    enhance_call_graph,
    get_unresolved_questions,
    parse_dependencies,
    resolve_and_enhance,
    resolve_internal_deps,
)
