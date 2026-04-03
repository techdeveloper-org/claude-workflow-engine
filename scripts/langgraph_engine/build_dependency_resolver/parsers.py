# ruff: noqa: F811
"""build_dependency_resolver/parsers.py - Build system dependency parsers.

One parser per build system: Python (pip/pyproject), Maven, Gradle, npm, Go, Cargo.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from .resolver import (  # noqa: E402, F811
    GO_WELL_KNOWN,
    JAVA_WELL_KNOWN,
    NODE_WELL_KNOWN,
    PYTHON_WELL_KNOWN,
    RUST_WELL_KNOWN,
    _classify_dep,
)


def _parse_raw_deps(
    root: Path,
    build_system: str,
    build_files: List[str],
) -> List[Dict]:
    """Dispatch to the appropriate parser for the detected build system."""
    if build_system == "maven":
        return _parse_maven_deps(root, build_files)
    if build_system == "gradle":
        return _parse_gradle_deps(root, build_files)
    if build_system == "npm":
        return _parse_npm_deps(root, build_files)
    if build_system == "go":
        return _parse_go_deps(root, build_files)
    if build_system == "cargo":
        return _parse_cargo_deps(root, build_files)
    if build_system == "python-pyproject":
        return _read_pyproject_deps(root, build_files)
    if build_system in ("python-pip",):
        return _parse_python_deps(root, build_files)
    if build_system in ("python-setup",):
        return _parse_python_deps(root, build_files)
    if build_system == "python-pipenv":
        return _parse_python_deps(root, build_files)
    return []


def _parse_python_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse requirements.txt, setup.py/cfg, Pipfile for Python deps."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file():
            continue
        fname = path.name.lower()

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if fname in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
            for line in content.splitlines():
                parsed = _parse_req_line(line)
                if parsed and parsed["name"] not in seen:
                    seen.add(parsed["name"])
                    deps.append(parsed)

        elif fname == "pipfile":
            # Simple TOML-like parse for [packages] and [dev-packages]
            in_section = False
            for line in content.splitlines():
                stripped = line.strip()
                if re.match(r"^\[(packages|dev-packages)\]", stripped, re.IGNORECASE):
                    in_section = True
                    continue
                if stripped.startswith("[") and not re.match(r"^\[(packages|dev-packages)\]", stripped, re.IGNORECASE):
                    in_section = False
                if in_section and "=" in stripped and not stripped.startswith("#"):
                    name = stripped.split("=")[0].strip().strip('"').strip("'")
                    if name and name not in seen:
                        seen.add(name)
                        deps.append({"name": name, "version": "*", "source": "Pipfile"})

        elif fname in ("setup.py", "setup.cfg"):
            # Rough extraction of install_requires lines
            for line in content.splitlines():
                stripped = line.strip().strip("'\"").strip(",")
                if stripped and not stripped.startswith("#"):
                    parsed = _parse_req_line(stripped)
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

    return deps


def _read_pyproject_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse pyproject.toml using tomllib (3.11+) or tomli or regex fallback."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "pyproject.toml":
            continue

        try:
            # Try tomllib (Python 3.11+)
            import importlib

            tomllib = None
            try:
                tomllib = importlib.import_module("tomllib")
            except ImportError:
                try:
                    tomllib = importlib.import_module("tomli")
                except ImportError:
                    pass

            if tomllib is not None:
                with open(path, "rb") as f:
                    data = tomllib.load(f)

                # PEP 621 dependencies
                project_deps = data.get("project", {}).get("dependencies", [])
                # Poetry dependencies
                poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})

                for dep_str in project_deps:
                    parsed = _parse_req_line(dep_str)
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

                for dep_name in poetry_deps:
                    if dep_name.lower() == "python":
                        continue
                    if dep_name not in seen:
                        seen.add(dep_name)
                        ver = poetry_deps[dep_name]
                        deps.append(
                            {
                                "name": dep_name,
                                "version": ver if isinstance(ver, str) else "*",
                                "source": "pyproject.toml",
                            }
                        )
            else:
                # Regex fallback for Python 3.8/3.9/3.10 without tomli
                content = path.read_text(encoding="utf-8", errors="replace")
                # Match quoted dependency strings under [project] dependencies
                for m in re.finditer(r'"([a-zA-Z0-9_.-]+[^"]*)"', content):
                    parsed = _parse_req_line(m.group(1))
                    if parsed and parsed["name"] not in seen:
                        seen.add(parsed["name"])
                        deps.append(parsed)

        except Exception as exc:
            logger.debug("[BuildDepResolver] pyproject.toml parse error: %s", exc)

    return deps


def _parse_req_line(line: str) -> Optional[Dict]:
    """Parse a single requirements.txt-style dependency line.

    Handles: name, name==1.0, name>=1.0, name[extra], name @ url,
    -r other.txt (skipped), # comments (stripped).
    """
    line = line.strip()
    # Strip inline comments
    if "#" in line:
        line = line[: line.index("#")].strip()
    if not line:
        return None
    # Skip options (-r, -c, --index-url, etc.)
    if line.startswith("-"):
        return None
    # Skip VCS URLs
    if line.startswith(("git+", "hg+", "svn+", "bzr+")):
        return None
    # Strip extras like name[security]
    name_match = re.match(r"^([A-Za-z0-9_.-]+)", line)
    if not name_match:
        return None
    name = name_match.group(1).lower().replace("_", "-")
    # Extract version specifier
    ver_match = re.search(r"([><=!~^]+[\s]*[\w.*]+)", line)
    version = ver_match.group(1).strip() if ver_match else "*"
    return {"name": name, "version": version, "source": "requirements"}


def _parse_maven_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse pom.xml for Maven dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "pom.xml":
            continue
        try:
            tree = ET.parse(str(path))
            root_el = tree.getroot()
            # Strip namespace
            ns_match = re.match(r"\{([^}]+)\}", root_el.tag)
            ns = "{" + ns_match.group(1) + "}" if ns_match else ""

            for dep_el in root_el.iter(f"{ns}dependency"):
                group_id = dep_el.findtext(f"{ns}groupId", "").strip()
                artifact_id = dep_el.findtext(f"{ns}artifactId", "").strip()
                version = dep_el.findtext(f"{ns}version", "*").strip()
                name = f"{group_id}:{artifact_id}" if group_id else artifact_id
                if name and name not in seen:
                    seen.add(name)
                    deps.append(
                        {
                            "name": name,
                            "version": version,
                            "source": "pom.xml",
                            "_group_id": group_id,
                            "_artifact_id": artifact_id,
                        }
                    )
        except Exception as exc:
            logger.debug("[BuildDepResolver] pom.xml parse error: %s", exc)

    return deps


def _parse_gradle_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse build.gradle for Gradle dependencies (best-effort line parsing)."""
    deps: List[Dict] = []
    seen: set = set()

    dep_pattern = re.compile(
        r"""(?:implementation|api|compile|testImplementation|runtimeOnly|compileOnly)\s*['"(]([^'")\s]+)['")]""",
        re.IGNORECASE,
    )

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or "build.gradle" not in path.name:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for m in dep_pattern.finditer(content):
                coord = m.group(1).strip()
                # Maven-style: group:artifact:version
                parts = coord.split(":")
                name = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
                version = parts[2] if len(parts) >= 3 else "*"
                if name not in seen:
                    seen.add(name)
                    deps.append({"name": name, "version": version, "source": "build.gradle"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] build.gradle parse error: %s", exc)

    return deps


def _parse_npm_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse package.json for npm/yarn dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "package.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, version in data.get(section, {}).items():
                    clean_name = name.lower()
                    if clean_name not in seen:
                        seen.add(clean_name)
                        deps.append(
                            {
                                "name": clean_name,
                                "version": version,
                                "source": "package.json",
                            }
                        )
        except Exception as exc:
            logger.debug("[BuildDepResolver] package.json parse error: %s", exc)

    return deps


def _parse_go_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse go.mod for Go module dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    require_pattern = re.compile(r"^\s+([^\s]+)\s+([^\s]+)")

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "go.mod":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            in_require = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("require ("):
                    in_require = True
                    continue
                if in_require and stripped == ")":
                    in_require = False
                    continue
                if in_require:
                    m = require_pattern.match(line)
                    if m:
                        name, version = m.group(1), m.group(2)
                        if name not in seen:
                            seen.add(name)
                            deps.append({"name": name, "version": version, "source": "go.mod"})
                elif stripped.startswith("require ") and not stripped.endswith("("):
                    parts = stripped[len("require ") :].split()
                    if len(parts) >= 2:
                        name, version = parts[0], parts[1]
                        if name not in seen:
                            seen.add(name)
                            deps.append({"name": name, "version": version, "source": "go.mod"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] go.mod parse error: %s", exc)

    return deps


def _parse_cargo_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse Cargo.toml for Rust crate dependencies."""
    deps: List[Dict] = []
    seen: set = set()

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "Cargo.toml":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped in ("[dependencies]", "[dev-dependencies]", "[build-dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("[") and "dependencies" not in stripped:
                    in_deps = False
                if in_deps and "=" in stripped and not stripped.startswith("#"):
                    name = stripped.split("=")[0].strip().strip('"').strip("'")
                    ver_part = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    # Handle table format: { version = "1.0" }
                    ver_match = re.search(r'version\s*=\s*["\']([^"\']+)', ver_part)
                    version = ver_match.group(1) if ver_match else ver_part.strip("{} ")
                    if name and name not in seen:
                        seen.add(name)
                        deps.append({"name": name, "version": version, "source": "Cargo.toml"})
        except Exception as exc:
            logger.debug("[BuildDepResolver] Cargo.toml parse error: %s", exc)

    return deps


# ---------------------------------------------------------------------------
# Private helpers - classification and source lookup
# ---------------------------------------------------------------------------


def _classify_dep(root: Path, dep: Dict, build_system: str) -> str:
    """Classify a dependency as internal/external_known/external_unknown/needs_user_input."""
    name = dep.get("name", "").lower()
    if not name:
        return "external_unknown"

    # Check internal first (local source exists)
    local_path = _find_local_source(root, name)
    if local_path is not None:
        dep["hint_path"] = str(local_path)
        return "internal"

    # Check well-known external sets
    if build_system in ("python-pip", "python-pyproject", "python-setup", "python-pipenv"):
        clean = name.replace("-", "").replace("_", "").lower()
        for known in PYTHON_WELL_KNOWN:
            if clean == known.replace("-", "").replace("_", "").lower():
                return "external_known"

    elif build_system == "maven":
        group = dep.get("_group_id", "").lower()
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "gradle":
        group = name.split(":")[0].lower() if ":" in name else name.lower()
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "npm":
        for known in NODE_WELL_KNOWN:
            if name == known.lower() or name.startswith(f"@{known.lower()}"):
                return "external_known"

    elif build_system == "go":
        for known in GO_WELL_KNOWN:
            if name.startswith(known.lower()):
                return "external_known"
        # Standard library (golang.org/x, etc. already in set; plain std = external_known)
        if "/" not in name:
            return "external_known"

    elif build_system == "cargo":
        for known in RUST_WELL_KNOWN:
            if name == known.lower():
                return "external_known"

    # Short names without path separators are likely external but ambiguous
    if len(name) <= 3 or ("/" not in name and "." not in name and ":" not in name):
        return "external_unknown"

    # Longer unknown names with path-like structure may be internal
    return "needs_user_input"


def _find_local_source(root: Path, dep_name: str) -> Optional[Path]:
    """Try to locate a local source directory for a dependency name."""
    # Normalize: replace hyphens/dots with underscores for directory lookup
    candidates = [
        dep_name,
        dep_name.replace("-", "_"),
        dep_name.replace(".", "_"),
        dep_name.replace("-", ""),
    ]
    # Only look at the package name part (after last slash or colon)
    for sep in ("/", ":", "."):
        if sep in dep_name:
            suffix = dep_name.split(sep)[-1]
            candidates.append(suffix)
            candidates.append(suffix.replace("-", "_"))

    search_dirs = [root, root / "src", root / "lib", root / "packages", root / "modules", root / "vendor", root.parent]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for cand in candidates:
            candidate_path = search_dir / cand
            if candidate_path.is_dir() and _dir_has_code(candidate_path):
                return candidate_path

    return None


def _dir_has_code(path: Path) -> bool:
    """Return True if the directory contains at least one source file."""
    code_extensions = {".py", ".java", ".kt", ".js", ".ts", ".go", ".rs", ".scala"}
    try:
        for child in path.rglob("*"):
            if child.suffix.lower() in code_extensions:
                return True
    except Exception:
        pass
    return False


def _detect_maven_project_group(root: Path) -> Optional[str]:
    """Extract groupId from root pom.xml for internal dep detection."""
    pom = root / "pom.xml"
    if not pom.is_file():
        return None
    try:
        tree = ET.parse(str(pom))
        root_el = tree.getroot()
        ns_match = re.match(r"\{([^}]+)\}", root_el.tag)
        ns = "{" + ns_match.group(1) + "}" if ns_match else ""
        group_el = root_el.find(f"{ns}groupId")
        if group_el is not None:
            return group_el.text.strip()
    except Exception:
        pass
    return None


def _build_question(
    root: Path,
    dep: Dict,
    build_system: str,
    reason: str,
) -> Optional[Dict]:
    """Build an actionable question dict for a dependency that needs user input."""
    name = dep.get("name", "?")
    version = dep.get("version", "*")

    if reason == "needs_input":
        question = (
            f"Is '{name}' (v{version}) an internal package with local source code, "
            f"or an external third-party library?"
        )
        suggestion = (
            f"If internal: provide the local path to '{name}' source relative to "
            f"project root. If external: add '{name}' to your well-known externals list."
        )
        options = [
            "Internal - local path: <provide path>",
            "External third-party library",
            "Skip / not relevant",
        ]
    else:
        question = (
            f"The dependency '{name}' (v{version}) could not be classified. "
            f"Is this a known external library or an internal package?"
        )
        suggestion = f"Search for '{name}' on your package registry. " f"If it is internal, provide a local path."
        options = [
            "External - well-known library",
            "Internal - local path: <provide path>",
            "Unknown / ignore",
        ]

    return {
        "dependency": name,
        "question": question,
        "suggestion": suggestion,
        "options": options,
    }


# ---------------------------------------------------------------------------
# Private helpers - graph merging
# ---------------------------------------------------------------------------


def _merge_sub_graph(main_graph: Any, sub_graph: Any, dep_name: str) -> None:
    """Merge nodes, classes, methods, and edges from sub_graph into main_graph."""
    # Merge nodes dict
    if hasattr(main_graph, "nodes") and hasattr(sub_graph, "nodes"):
        for fqn, node in sub_graph.nodes.items():
            if fqn not in main_graph.nodes:
                main_graph.nodes[fqn] = node

    # Merge classes dict
    if hasattr(main_graph, "classes") and hasattr(sub_graph, "classes"):
        for fqn, cls in sub_graph.classes.items():
            if fqn not in main_graph.classes:
                main_graph.classes[fqn] = cls

    # Merge methods dict
    if hasattr(main_graph, "methods") and hasattr(sub_graph, "methods"):
        for fqn, method in sub_graph.methods.items():
            if fqn not in main_graph.methods:
                main_graph.methods[fqn] = method

    # Merge edges list (avoid duplicates via set of tuples)
    if hasattr(main_graph, "edges") and hasattr(sub_graph, "edges"):
        existing_keys: set = set()
        for edge in main_graph.edges:
            caller = edge.get("caller", "")
            callee = edge.get("callee", "")
            existing_keys.add((caller, callee))

        for edge in sub_graph.edges:
            caller = edge.get("caller", "")
            callee = edge.get("callee", "")
            if (caller, callee) not in existing_keys:
                main_graph.edges.append(edge)
                existing_keys.add((caller, callee))

    # Merge files set
    if hasattr(main_graph, "files") and hasattr(sub_graph, "files"):
        main_graph.files.update(sub_graph.files)

    logger.debug("[BuildDepResolver] Merged sub-graph for '%s' into main graph", dep_name)


# ---------------------------------------------------------------------------
# Private helpers - CallGraphBuilder import (4 strategies)
# ---------------------------------------------------------------------------


def _import_call_graph_builder(root: Path) -> Optional[Any]:
    """Import CallGraphBuilder using 4 fallback strategies.

    1. Relative package import (scripts.langgraph_engine.call_graph_builder)
    2. Sibling module import (call_graph_builder)
    3. sys.path manipulation + import
    4. importlib.util with absolute path
    """
    # Strategy 1: package import
    try:
        from scripts.langgraph_engine.call_graph_builder import CallGraphBuilder

        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 2: sibling import (same directory)
    try:
        from call_graph_builder import CallGraphBuilder

        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 3: sys.path manipulation
    try:
        import sys

        engine_dir = str(Path(__file__).parent)
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        from call_graph_builder import CallGraphBuilder

        return CallGraphBuilder
    except ImportError:
        pass

    # Strategy 4: importlib.util with absolute path
    try:
        import importlib.util

        module_path = Path(__file__).parent / "call_graph_builder.py"
        if not module_path.exists():
            # Try relative to project root
            module_path = root / "scripts" / "langgraph_engine" / "call_graph_builder.py"
        if module_path.exists():
            spec = importlib.util.spec_from_file_location("call_graph_builder", str(module_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "CallGraphBuilder", None)
    except Exception as exc:
        logger.debug("[BuildDepResolver] importlib strategy failed: %s", exc)

    logger.warning("[BuildDepResolver] All 4 CallGraphBuilder import strategies failed")
    return None
