# ruff: noqa: F811
"""build_dependency_resolver/parsers.py - Build system dependency parsers.

One parser per build system: Python (pip/pyproject), Maven, Gradle, npm, Go, Cargo.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import functools
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from .registries import (  # noqa: E402
    GO_WELL_KNOWN,
    JAVA_WELL_KNOWN,
    NODE_WELL_KNOWN,
    NODE_WELL_KNOWN_NORMALIZED,
    PYTHON_WELL_KNOWN_NORMALIZED,
    RUST_WELL_KNOWN_NORMALIZED,
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
                # Regex fallback for Python 3.8/3.9/3.10 without tomli.
                # Scope-limited (D9): only extract deps from the [project]
                # dependencies array; stop at the next bare [section] header.
                content = path.read_text(encoding="utf-8", errors="replace")
                in_project_section = False
                in_deps_array = False
                for line in content.splitlines():
                    stripped = line.strip()
                    # Detect [project] section header
                    if re.match(r"^\[project\]\s*$", stripped):
                        in_project_section = True
                        continue
                    # Any new bare [section] ends [project] scope
                    if stripped.startswith("[") and not stripped.startswith("[["):
                        in_project_section = False
                        in_deps_array = False
                        continue
                    if not in_project_section:
                        continue
                    # Detect dependencies = [ array start inside [project]
                    if re.match(r"^dependencies\s*=\s*\[", stripped):
                        in_deps_array = True
                        # May have first dep on same line after [
                        rest = re.split(r"\[", stripped, maxsplit=1)[1]
                        for m in re.finditer(r'"([^"]+)"', rest):
                            val = m.group(1)
                            # D9 guards: skip :: (extras), :// (URLs), bare whitespace
                            if "::" in val or "://" in val or not val.strip():
                                continue
                            parsed = _parse_req_line(val)
                            if parsed and parsed["name"] not in seen:
                                seen.add(parsed["name"])
                                deps.append(parsed)
                        if "]" in rest:
                            in_deps_array = False
                        continue
                    if in_deps_array:
                        if "]" in stripped:
                            in_deps_array = False
                        for m in re.finditer(r'"([^"]+)"', stripped):
                            val = m.group(1)
                            if "::" in val or "://" in val or not val.strip():
                                continue
                            parsed = _parse_req_line(val)
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
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
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


_GRADLE_SCOPES = (
    "implementation",
    "api",
    "compile",
    "testImplementation",
    "runtimeOnly",
    "compileOnly",
    "annotationProcessor",
    "kapt",
    "testRuntimeOnly",
)


def _parse_gradle_deps(root: Path, build_files: List[str]) -> List[Dict]:
    """Parse build.gradle / build.gradle.kts for Gradle dependencies.

    Supports three declaration styles (D11):
      1. String literal:  implementation 'group:artifact:1.0'
      2. Map-style:       implementation group: 'g', name: 'a', version: '1.0'
      3. Version catalog: implementation libs.some.alias
    """
    deps: List[Dict] = []
    seen: set = set()

    scope_alts = "|".join(re.escape(s) for s in _GRADLE_SCOPES)

    # Style 1: quoted coordinate string
    dep_pattern = re.compile(
        r"""(?:%s)\s*['"(]([^'")\s]+)['")]""" % scope_alts,
        re.IGNORECASE,
    )
    # Style 2: map-style  group: 'x', name: 'y', version: 'z'
    map_pattern = re.compile(
        r"""(?:%s)\s+group\s*:\s*['"]([^'"]+)['"]\s*,\s*name\s*:\s*['"]([^'"]+)['"]\s*(?:,\s*version\s*:\s*['"]([^'"]+)['"])?"""
        % scope_alts,
        re.IGNORECASE,
    )
    # Style 3: version catalog alias  libs.<alias>
    libs_pattern = re.compile(
        r"""(?:%s)\s+libs\.([A-Za-z0-9_.]+)""" % scope_alts,
        re.IGNORECASE,
    )

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or "build.gradle" not in path.name:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")

            # Style 1
            for m in dep_pattern.finditer(content):
                coord = m.group(1).strip()
                parts = coord.split(":")
                name = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
                version = parts[2] if len(parts) >= 3 else "*"
                if name not in seen:
                    seen.add(name)
                    deps.append({"name": name, "version": version, "source": "build.gradle"})

            # Style 2
            for m in map_pattern.finditer(content):
                group, artifact = m.group(1).strip(), m.group(2).strip()
                version = (m.group(3) or "*").strip()
                name = "%s:%s" % (group, artifact)
                if name not in seen:
                    seen.add(name)
                    deps.append({"name": name, "version": version, "source": "build.gradle"})

            # Style 3 (catalog alias -- no version available at parse time)
            for m in libs_pattern.finditer(content):
                alias = m.group(1).strip()
                name = "libs.%s" % alias
                if name not in seen:
                    seen.add(name)
                    deps.append({"name": name, "version": "*", "source": "build.gradle(catalog)"})

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
    """Parse Cargo.toml for Rust crate dependencies.

    Prefers tomllib/tomli structured parse (D10) for correctness;
    falls back to line-by-line text parse when neither is available.
    """
    deps: List[Dict] = []
    seen: set = set()

    # Try to import a TOML parser once
    import importlib as _importlib

    _toml = None
    for _mod in ("tomllib", "tomli"):
        try:
            _toml = _importlib.import_module(_mod)
            break
        except ImportError:
            pass

    _dep_sections = ("dependencies", "dev-dependencies", "build-dependencies")

    for bf in build_files:
        path = Path(bf)
        if not path.is_file() or path.name != "Cargo.toml":
            continue
        try:
            if _toml is not None:
                # Structured parse (D10)
                with open(path, "rb") as f:
                    data = _toml.load(f)
                for section in _dep_sections:
                    section_data = data.get(section, {})
                    if not isinstance(section_data, dict):
                        continue
                    for name, spec in section_data.items():
                        if not name or name in seen:
                            continue
                        seen.add(name)
                        if isinstance(spec, str):
                            version = spec
                        elif isinstance(spec, dict):
                            version = spec.get("version", "*") or "*"
                        else:
                            version = "*"
                        deps.append({"name": name, "version": version, "source": "Cargo.toml"})
            else:
                # Line-by-line fallback
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


@functools.lru_cache(maxsize=512)
def _network_classify(name: str, build_system: str) -> Optional[str]:
    """Optional PyPI / crates.io / npmjs network lookup for unknown deps (D16).

    Returns "external_known" if the package exists on the public registry,
    None otherwise (network unavailable, package not found, or lookup disabled).

    Controlled by env var BDR_NETWORK_CLASSIFY=1 (default: disabled).
    Results are cached via lru_cache to avoid redundant HTTP calls.
    """
    if not name or len(name) > 200:
        return None
    if not (
        build_system in ("python-pip", "python-pyproject", "python-setup", "python-pipenv")
        or build_system == "cargo"
        or build_system == "npm"
    ):
        return None
    try:
        import urllib.request

        if build_system in ("python-pip", "python-pyproject", "python-setup", "python-pipenv"):
            url = "https://pypi.org/pypi/%s/json" % name
        elif build_system == "cargo":
            url = "https://crates.io/api/v1/crates/%s" % name
        elif build_system == "npm":
            url = "https://registry.npmjs.org/%s/latest" % name
        else:
            return None

        req = urllib.request.Request(url, headers={"User-Agent": "claude-workflow-engine/bdr"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return "external_known"
    except Exception:
        pass
    return None


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

    # Check well-known external sets (O(1) normalized set lookups -- D12)
    if build_system in ("python-pip", "python-pyproject", "python-setup", "python-pipenv"):
        clean = name.replace("-", "").replace("_", "").lower()
        if clean in PYTHON_WELL_KNOWN_NORMALIZED:
            return "external_known"

    elif build_system == "maven":
        group = dep.get("_group_id", "").lower()
        # Prefix check still requires iteration (no normalized form for prefix match)
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "gradle":
        group = name.split(":")[0].lower() if ":" in name else name.lower()
        for known in JAVA_WELL_KNOWN:
            if group.startswith(known.lower()):
                return "external_known"

    elif build_system == "npm":
        # O(1) exact match; prefix "@scope/" still needs linear scan
        if name in NODE_WELL_KNOWN_NORMALIZED:
            return "external_known"
        for known in NODE_WELL_KNOWN:
            if name.startswith("@" + known.lower()):
                return "external_known"

    elif build_system == "go":
        # Prefix check requires iteration; plain stdlib names are O(1) branch
        for known in GO_WELL_KNOWN:
            if name.startswith(known.lower()):
                return "external_known"
        # Standard library (golang.org/x, etc. already in set; plain std = external_known)
        if "/" not in name:
            return "external_known"

    elif build_system == "cargo":
        clean = name.replace("-", "").replace("_", "").lower()
        if clean in RUST_WELL_KNOWN_NORMALIZED:
            return "external_known"

    # Short names without path separators are likely external but ambiguous
    if len(name) <= 3 or ("/" not in name and "." not in name and ":" not in name):
        # D16: optional network lookup to confirm before returning unknown
        if os.environ.get("BDR_NETWORK_CLASSIFY") == "1":
            net = _network_classify(name, build_system)
            if net is not None:
                return net
        return "external_unknown"

    # Longer unknown names with path-like structure may be internal
    # D16: try network lookup before giving up
    if os.environ.get("BDR_NETWORK_CLASSIFY") == "1":
        net = _network_classify(name, build_system)
        if net is not None:
            return net
    return "needs_user_input"


def _find_local_source(root: Path, dep_name: str) -> Optional[Path]:
    """Try to locate a local source directory for a dependency name.

    Search is restricted to subtrees of ``root`` by default.
    Set env var BDR_ALLOW_PARENT_SEARCH=1 to also search root.parent
    (not recommended -- can cause false positives and slow scans).
    """
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

    search_dirs = [root, root / "src", root / "lib", root / "packages", root / "modules", root / "vendor"]

    # Parent search gated behind env var to prevent accidental filesystem crawling
    if os.environ.get("BDR_ALLOW_PARENT_SEARCH") == "1":
        search_dirs.append(root.parent)

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for cand in candidates:
            candidate_path = search_dir / cand
            # Symlink guard: resolve to real path and ensure it stays under root
            if candidate_path.is_dir():
                try:
                    real = candidate_path.resolve()
                    root_real = root.resolve()
                    # Accept path only if it is under the project root (or parent if allowed)
                    if not str(real).startswith(str(root_real)):
                        if os.environ.get("BDR_ALLOW_PARENT_SEARCH") != "1":
                            logger.debug(
                                "[BuildDepResolver] _find_local_source: skipping symlink outside root: %s",
                                candidate_path,
                            )
                            continue
                except Exception:
                    continue
                if _dir_has_code(candidate_path):
                    return candidate_path

    return None


def _dir_has_code_uncached(path_str: str) -> bool:
    """Bounded BFS implementation for _dir_has_code. Called via lru_cache wrapper."""
    import collections

    code_extensions = {".py", ".java", ".kt", ".js", ".ts", ".go", ".rs", ".scala"}
    max_depth = 4
    max_files_scanned = 1000
    files_scanned = 0

    # BFS queue items: (directory_path, current_depth)
    queue = collections.deque([(Path(path_str), 0)])

    try:
        while queue:
            current_dir, depth = queue.popleft()
            if depth > max_depth:
                continue
            try:
                for child in current_dir.iterdir():
                    files_scanned += 1
                    if files_scanned > max_files_scanned:
                        return False
                    if child.is_file() and child.suffix.lower() in code_extensions:
                        return True
                    if child.is_dir() and not child.is_symlink():
                        queue.append((child, depth + 1))
            except PermissionError:
                continue
    except Exception:
        pass
    return False


@functools.lru_cache(maxsize=1024)
def _dir_has_code(path: Path) -> bool:
    """Return True if the directory contains at least one source file.

    Uses bounded BFS (max_depth=4, max_files=1000) to avoid hanging on
    deep or symlinked directory trees. Results are memoized via lru_cache.
    """
    return _dir_has_code_uncached(str(path))


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


def _rewrite_subgraph_fqns(sub_graph: Any, prefix: str) -> None:
    """Namespace all FQNs in sub_graph with ``prefix`` to prevent collisions.

    Rewrites keys in nodes, classes, methods dicts and from/to/caller/callee
    fields in each edge. The prefix used is ``dep::<dep_name>::``.

    This is a mutating operation -- call before merging into main_graph.
    """
    dep_prefix = prefix + "::"

    def _prefixed(fqn: str) -> str:
        if fqn and not fqn.startswith("dep::"):
            return dep_prefix + fqn
        return fqn

    # Rewrite nodes
    if hasattr(sub_graph, "nodes") and isinstance(sub_graph.nodes, dict):
        original_keys = list(sub_graph.nodes.keys())
        for key in original_keys:
            new_key = _prefixed(key)
            if new_key != key:
                sub_graph.nodes[new_key] = sub_graph.nodes.pop(key)

    # Rewrite classes
    if hasattr(sub_graph, "classes") and isinstance(sub_graph.classes, dict):
        original_keys = list(sub_graph.classes.keys())
        for key in original_keys:
            new_key = _prefixed(key)
            if new_key != key:
                sub_graph.classes[new_key] = sub_graph.classes.pop(key)

    # Rewrite methods
    if hasattr(sub_graph, "methods") and isinstance(sub_graph.methods, dict):
        original_keys = list(sub_graph.methods.keys())
        for key in original_keys:
            new_key = _prefixed(key)
            if new_key != key:
                sub_graph.methods[new_key] = sub_graph.methods.pop(key)

    # Rewrite edge endpoint fields (support both caller/callee and from/to schemas)
    if hasattr(sub_graph, "edges") and isinstance(sub_graph.edges, list):
        for edge in sub_graph.edges:
            for field in ("caller", "callee", "from", "to"):
                if field in edge and edge[field]:
                    edge[field] = _prefixed(edge[field])


def _merge_sub_graph(main_graph: Any, sub_graph: Any, dep_name: str) -> None:
    """Merge nodes, classes, methods, and edges from sub_graph into main_graph.

    Applies FQN namespacing (D3) before merging to prevent collisions with
    main graph entries. Uses canonical edge dedup key (from, to, type) that
    supports both caller/callee and from/to edge schemas (D2).

    Invariant: main graph FQNs must NOT start with 'dep::' (they are owned
    by the main project). Sub-graph FQNs are rewritten to 'dep::<name>::'.
    """
    # D3: namespace sub-graph FQNs before merging
    _rewrite_subgraph_fqns(sub_graph, "dep::" + dep_name)

    # Invariant check: main graph should not contain dep:: entries already
    if hasattr(main_graph, "nodes") and isinstance(main_graph.nodes, dict):
        dep_nodes = [k for k in main_graph.nodes if k.startswith("dep::")]
        if dep_nodes:
            logger.debug(
                "[BuildDepResolver] main_graph already has %d dep:: nodes before merge",
                len(dep_nodes),
            )

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

    # Merge edges list (D2: canonical dedup key uses from/to/type to support
    # both caller/callee schema and from/to schema sub-graphs)
    if hasattr(main_graph, "edges") and hasattr(sub_graph, "edges"):
        existing_keys: set = set()
        for edge in main_graph.edges:
            src = edge.get("from", edge.get("caller", ""))
            dst = edge.get("to", edge.get("callee", ""))
            etype = edge.get("type", "call")
            existing_keys.add((src, dst, etype))

        for edge in sub_graph.edges:
            src = edge.get("from", edge.get("caller", ""))
            dst = edge.get("to", edge.get("callee", ""))
            etype = edge.get("type", "call")
            if (src, dst, etype) not in existing_keys:
                main_graph.edges.append(edge)
                existing_keys.add((src, dst, etype))

    # Merge files set
    if hasattr(main_graph, "files") and hasattr(sub_graph, "files"):
        main_graph.files.update(sub_graph.files)

    logger.debug("[BuildDepResolver] Merged sub-graph for '%s' into main graph", dep_name)


# ---------------------------------------------------------------------------
# Private helpers - CallGraphBuilder import (4 strategies)
# ---------------------------------------------------------------------------


def _import_call_graph_builder(root: Path) -> Optional[Any]:
    """Import CallGraphBuilder from the canonical package location.

    Single strategy: langgraph_engine.call_graph_builder package import.
    sys.path manipulation and importlib.util hacks removed (D14) --
    they mask import errors and can silently load stale .pyc files.
    """
    try:
        from langgraph_engine.call_graph_builder import CallGraphBuilder

        return CallGraphBuilder
    except ImportError as exc:
        logger.warning("[BuildDepResolver] CallGraphBuilder import failed: %s", exc)
        return None
