"""
UML Diagram Generator - Auto-generates 12 UML diagram types from codebase analysis.

Tier 1 (AST-based, no LLM): Class, Package, Component
Tier 2 (AST + LLM hybrid): Sequence, Activity, State
Tier 3 (LLM-powered): Use Case, Object, Deployment, Communication,
                       Composite Structure, Interaction Overview

Rendering:
- Mermaid syntax for GitHub-native rendering (Tier 1 + 2)
- PlantUML syntax for remaining types (Tier 3)
- Kroki.io free API for PlantUML -> SVG rendering
"""

import os
import ast
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Data classes (plain dicts for simplicity, no dataclass dep)
# ======================================================================

def _make_class_info(
    name, file_path, bases=None, methods=None, attributes=None
):
    """Create a ClassInfo dict."""
    return {
        "name": name,
        "file_path": str(file_path),
        "module": str(Path(file_path).stem),
        "bases": bases or [],
        "methods": methods or [],
        "attributes": attributes or [],
    }


def _make_method_info(name, params=None, return_type="", visibility="+"):
    """Create a MethodInfo dict."""
    return {
        "name": name,
        "params": params or [],
        "return_type": return_type,
        "visibility": visibility,
    }


def _make_attr_info(name, type_hint="", visibility="+"):
    """Create an AttributeInfo dict."""
    return {
        "name": name,
        "type_hint": type_hint,
        "visibility": visibility,
    }


# ======================================================================
# AST Analyzer
# ======================================================================

class UMLAstAnalyzer:
    """Python AST analysis for structural UML diagrams."""

    def __init__(self, project_root):
        self.project_root = Path(project_root)

    def extract_classes(self, file_path):
        """Extract class info from a single Python file.

        Returns list of ClassInfo dicts.
        """
        file_path = Path(file_path)
        classes = []
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError) as e:
            logger.debug("Cannot parse %s: %s", file_path, e)
            return classes

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.dump(base))

            methods = []
            attributes = []

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    vis = "-" if item.name.startswith("_") else "+"
                    if item.name.startswith("__") and item.name.endswith("__"):
                        vis = "+"  # dunder methods are public interface

                    params = []
                    for arg in item.args.args:
                        if arg.arg != "self":
                            params.append(arg.arg)

                    ret = ""
                    if item.returns:
                        try:
                            ret = ast.dump(item.returns)
                        except Exception:
                            pass

                    methods.append(
                        _make_method_info(item.name, params, ret, vis)
                    )

                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes.append(
                                _make_attr_info(target.id, "", "+")
                            )

                elif isinstance(item, ast.AnnAssign) and item.target:
                    if isinstance(item.target, ast.Name):
                        hint = ""
                        if item.annotation:
                            try:
                                hint = ast.dump(item.annotation)
                            except Exception:
                                pass
                        attributes.append(
                            _make_attr_info(item.target.id, hint, "+")
                        )

            # Also scan __init__ for self.attr assignments
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name == "__init__"):
                    for stmt in ast.walk(item):
                        if (isinstance(stmt, ast.Assign)
                                and len(stmt.targets) == 1):
                            target = stmt.targets[0]
                            if (isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "self"):
                                attr_name = target.attr
                                vis = "-" if attr_name.startswith("_") else "+"
                                # Avoid duplicates
                                existing = [
                                    a["name"] for a in attributes
                                ]
                                if attr_name not in existing:
                                    attributes.append(
                                        _make_attr_info(attr_name, "", vis)
                                    )

            classes.append(
                _make_class_info(
                    node.name, file_path, bases, methods, attributes
                )
            )

        return classes

    def extract_all_classes(self, directory=None):
        """Recursively extract classes from all .py files."""
        root = Path(directory) if directory else self.project_root
        all_classes = []

        for py_file in root.rglob("*.py"):
            # Skip test files, __pycache__, venv
            rel = str(py_file.relative_to(root))
            if any(skip in rel for skip in [
                "__pycache__", ".venv", "venv", "node_modules"
            ]):
                continue
            all_classes.extend(self.extract_classes(py_file))

        return all_classes

    def extract_imports(self, file_path):
        """Extract import statements from a Python file.

        Returns dict with 'imports' and 'from_imports' lists.
        """
        file_path = Path(file_path)
        result = {"imports": [], "from_imports": [], "file": str(file_path)}
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError):
            return result

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    result["from_imports"].append(
                        {"module": module, "name": alias.name}
                    )

        return result

    def build_dependency_graph(self, directory=None):
        """Build module-level dependency map.

        Returns dict: {module_name: set_of_imported_modules}
        """
        root = Path(directory) if directory else self.project_root
        graph = {}

        for py_file in root.rglob("*.py"):
            rel = str(py_file.relative_to(root))
            if any(skip in rel for skip in [
                "__pycache__", ".venv", "venv", "node_modules"
            ]):
                continue

            module_name = py_file.stem
            imports = self.extract_imports(py_file)
            deps = set()

            for imp in imports["imports"]:
                deps.add(imp.split(".")[0])
            for fi in imports["from_imports"]:
                if fi["module"]:
                    deps.add(fi["module"].split(".")[0])

            # Filter to only project-internal deps
            graph[module_name] = deps

        return graph

    def extract_call_chains(self, file_path, entry_func=None):
        """Extract static call chains from a file with class context.

        Uses CallGraphBuilder's AST NodeVisitor to maintain class->method
        hierarchy instead of flat ast.walk() which loses class context.

        Returns list of call chain dicts:
        [{caller, callee, file, caller_fqn, callee_fqn, line, call_type}]
        """
        file_path = Path(file_path)

        # Try new call graph builder (maintains class context)
        try:
            from .call_graph_builder import _CallGraphVisitor
        except ImportError:
            try:
                from call_graph_builder import _CallGraphVisitor
            except ImportError:
                _CallGraphVisitor = None

        if _CallGraphVisitor is not None:
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(file_path))

                try:
                    rel_path = str(file_path.relative_to(self.project_root))
                except ValueError:
                    rel_path = file_path.name
                rel_path = rel_path.replace("\\", "/")

                visitor = _CallGraphVisitor(str(file_path), rel_path)
                visitor.visit(tree)

                chains = []
                for edge in visitor.edges:
                    if edge["type"] == "inheritance":
                        continue

                    caller_fqn = edge["from"]
                    callee_raw = edge["to"]

                    # Extract simple names for backward compatibility
                    caller_name = caller_fqn.split("::")[-1] if "::" in caller_fqn else caller_fqn
                    callee_name = callee_raw.split("::")[-1] if "::" in callee_raw else callee_raw
                    callee_name = callee_name.split(".")[-1] if "." in callee_name else callee_name

                    if entry_func and not caller_name.endswith(entry_func):
                        continue

                    chains.append({
                        "caller": caller_name,
                        "callee": callee_name,
                        "file": str(file_path),
                        "caller_fqn": caller_fqn,
                        "callee_fqn": callee_raw,
                        "line": edge.get("line", 0),
                        "call_type": edge.get("type", "call"),
                    })

                return chains
            except Exception:
                pass  # Fall through to legacy

        # Legacy fallback (no class context)
        chains = []
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError):
            return chains

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            caller = node.name
            if entry_func and caller != entry_func:
                continue

            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = ""
                    if isinstance(child.func, ast.Name):
                        callee = child.func.id
                    elif isinstance(child.func, ast.Attribute):
                        callee = child.func.attr
                    if callee:
                        chains.append({
                            "caller": caller,
                            "callee": callee,
                            "file": str(file_path),
                        })

        return chains


# ======================================================================
# Diagram Generator
# ======================================================================

class UMLDiagramGenerator:
    """Generate Mermaid/PlantUML syntax from analysis results."""

    def __init__(self, project_root, output_dir="docs/uml", call_graph=None):
        self.project_root = Path(project_root)
        self.output_dir = self.project_root / output_dir
        self.analyzer = UMLAstAnalyzer(project_root)
        self._call_graph = call_graph  # pre-built CallGraph or None (lazy)

    # ------------------------------------------------------------------
    # CallGraph integration helpers
    # ------------------------------------------------------------------

    def _get_call_graph(self):
        """Return stored CallGraph or lazily build one.

        Returns CallGraph instance or None if building fails.
        """
        if self._call_graph is not None:
            return self._call_graph
        try:
            try:
                from .call_graph_builder import build_call_graph
            except ImportError:
                from call_graph_builder import build_call_graph
            cg = build_call_graph(str(self.project_root))
            self._call_graph = cg
            return cg
        except Exception as e:
            logger.debug("CallGraph build failed: %s", e)
            return None

    def _classes_from_call_graph(self, cg):
        """Adapt CallGraph class/method data into _make_class_info format.

        Uses analyzer.extract_classes() per file for attributes (AST-derived)
        and merges with CallGraph method data for richer method info.

        Returns list of ClassInfo dicts or None if cg has no classes.
        """
        if cg is None:
            return None

        # Build file -> list of class FQNs for attribute extraction
        file_to_classes = {}
        for fqn, cls_node in cg.classes.items():
            fp = cls_node.get("file", "")
            if fp not in file_to_classes:
                file_to_classes[fp] = []
            file_to_classes[fp].append(fqn)

        # Extract attributes per file via the existing AST analyzer
        # Map: class_name -> attributes list
        attrs_by_name = {}
        for rel_path in file_to_classes:
            abs_path = self.project_root / rel_path
            try:
                ast_classes = self.analyzer.extract_classes(abs_path)
                for ac in ast_classes:
                    attrs_by_name[ac["name"]] = ac.get("attributes", [])
            except Exception:
                pass

        results = []
        for fqn, cls_node in cg.classes.items():
            cls_name = cls_node.get("name", "")
            file_path = cls_node.get("file", "")
            bases = cls_node.get("bases", [])

            # Collect methods for this class from cg.methods
            methods = []
            for method_fqn in cls_node.get("methods", []):
                m = cg.methods.get(method_fqn)
                if m is None:
                    continue
                methods.append(_make_method_info(
                    name=m.get("name", ""),
                    params=m.get("params", []),
                    return_type=m.get("return_type", ""),
                    visibility=m.get("visibility", "+"),
                ))

            # Merge AST-derived attributes
            attributes = attrs_by_name.get(cls_name, [])

            abs_file_path = (
                self.project_root / file_path if file_path else ""
            )
            results.append(_make_class_info(
                name=cls_name,
                file_path=abs_file_path,
                bases=bases,
                methods=methods,
                attributes=attributes,
            ))

        return results if results else None

    def _dep_graph_from_call_graph(self, cg):
        """Enrich analyzer dependency graph with cross-file CallGraph edges.

        Starts with the existing AST-based dep graph and adds edges from
        CallGraph where the caller file differs from the callee file.

        Returns dep_graph dict: {module_name: set_of_deps}
        """
        # Always start with AST-based graph as the base
        dep_graph = self.analyzer.build_dependency_graph()

        if cg is None:
            return dep_graph

        # Add cross-file edges from CallGraph
        for edge in cg.get_edges():
            if edge.get("type") == "inheritance":
                continue
            from_fqn = edge.get("from", "")
            to_fqn = edge.get("to", "")
            if not from_fqn or not to_fqn:
                continue

            # FQN format: "rel/path.py::ClassName.method"
            from_file = from_fqn.split("::")[0] if "::" in from_fqn else ""
            to_file = to_fqn.split("::")[0] if "::" in to_fqn else ""

            # Only enrich with cross-file edges
            if not from_file or not to_file or from_file == to_file:
                continue

            from_module = Path(from_file).stem
            to_module = Path(to_file).stem

            if from_module not in dep_graph:
                dep_graph[from_module] = set()
            dep_graph[from_module].add(to_module)

        return dep_graph

    def _call_chains_from_call_graph(self, cg):
        """Convert CallGraph edges to call_chains format.

        Filters out inheritance edges and returns:
        [{caller, callee, file, caller_fqn, callee_fqn, line, call_type}]

        Returns list or None if cg has no usable edges.
        """
        if cg is None:
            return None

        chains = []
        for edge in cg.get_edges():
            if edge.get("type") == "inheritance":
                continue

            caller_fqn = edge.get("from", "")
            callee_fqn = edge.get("to", "")
            if not caller_fqn:
                continue

            # Extract simple names for backward compatibility
            caller_name = (
                caller_fqn.split("::")[-1]
                if "::" in caller_fqn else caller_fqn
            )
            callee_name = (
                callee_fqn.split("::")[-1]
                if "::" in callee_fqn else callee_fqn
            )
            # Reduce dotted names to leaf
            caller_name = (
                caller_name.split(".")[-1]
                if "." in caller_name else caller_name
            )
            callee_name = (
                callee_name.split(".")[-1]
                if "." in callee_name else callee_name
            )

            # Derive absolute file path from caller FQN
            from_file = caller_fqn.split("::")[0] if "::" in caller_fqn else ""
            abs_file = (
                str(self.project_root / from_file) if from_file else ""
            )

            chains.append({
                "caller": caller_name,
                "callee": callee_name,
                "file": abs_file,
                "caller_fqn": caller_fqn,
                "callee_fqn": callee_fqn,
                "line": edge.get("line", 0),
                "call_type": edge.get("type", "call"),
            })

        return chains if chains else None

    # ------------------------------------------------------------------
    # Tier 1: AST-based (no LLM)
    # ------------------------------------------------------------------

    def generate_class_diagram(self, classes=None, scope="all"):
        """Generate Mermaid classDiagram from Python AST analysis.

        Args:
            classes: Pre-extracted class list, or None to auto-extract.
            scope: "all" for full project, or a directory/file path.
        """
        if classes is None:
            if scope == "all":
                # Try CallGraph first; fall back to AST analyzer
                cg = self._get_call_graph()
                classes = self._classes_from_call_graph(cg)
                if not classes:
                    classes = self.analyzer.extract_all_classes()
            else:
                scope_path = Path(scope)
                if scope_path.is_file():
                    classes = self.analyzer.extract_classes(scope_path)
                else:
                    classes = self.analyzer.extract_all_classes(scope_path)

        if not classes:
            return "classDiagram\n    note \"No classes found\""

        lines = ["classDiagram"]

        for cls in classes:
            lines.append("    class %s {" % cls["name"])

            for attr in cls.get("attributes", [])[:10]:
                vis = attr.get("visibility", "+")
                hint = attr.get("type_hint", "")
                type_str = ""
                if hint:
                    # Simplify AST dump to readable type
                    type_str = _simplify_type(hint)
                    type_str = ": %s" % type_str if type_str else ""
                lines.append("        %s%s%s" % (vis, attr["name"], type_str))

            for method in cls.get("methods", [])[:15]:
                vis = method.get("visibility", "+")
                params = ", ".join(method.get("params", [])[:4])
                ret = ""
                if method.get("return_type"):
                    ret = " %s" % _simplify_type(method["return_type"])
                lines.append(
                    "        %s%s(%s)%s" % (vis, method["name"], params, ret)
                )

            lines.append("    }")

        # Add inheritance relationships
        for cls in classes:
            for base in cls.get("bases", []):
                if any(c["name"] == base for c in classes):
                    lines.append(
                        "    %s <|-- %s" % (base, cls["name"])
                    )

        return "\n".join(lines)

    def generate_package_diagram(self, dep_graph=None):
        """Generate Mermaid flowchart from module dependencies."""
        if dep_graph is None:
            cg = self._get_call_graph()
            dep_graph = self._dep_graph_from_call_graph(cg)

        if not dep_graph:
            return "flowchart LR\n    note[No modules found]"

        # Group modules by directory
        lines = ["flowchart LR"]

        # Collect all known project modules
        project_modules = set(dep_graph.keys())

        for module, deps in sorted(dep_graph.items()):
            for dep in sorted(deps):
                # Only show internal dependencies
                if dep in project_modules:
                    lines.append("    %s --> %s" % (module, dep))

        # Add isolated modules (no deps shown)
        connected = set()
        for module, deps in dep_graph.items():
            internal_deps = deps & project_modules
            if internal_deps:
                connected.add(module)
                connected.update(internal_deps)

        for module in sorted(project_modules - connected):
            lines.append("    %s" % module)

        return "\n".join(lines)

    def generate_component_diagram(self, dep_graph=None):
        """Generate Mermaid flowchart representing components."""
        if dep_graph is None:
            cg = self._get_call_graph()
            dep_graph = self._dep_graph_from_call_graph(cg)

        if not dep_graph:
            return "flowchart TB\n    note[No components found]"

        lines = ["flowchart TB"]

        # Group by top-level directories
        groups = {}
        for module in dep_graph:
            # Try to find the file to determine its directory
            for py_file in self.project_root.rglob("%s.py" % module):
                try:
                    rel = py_file.relative_to(self.project_root)
                    parts = rel.parts
                    group = parts[0] if len(parts) > 1 else "root"
                    if group not in groups:
                        groups[group] = []
                    groups[group].append(module)
                except ValueError:
                    pass
                break

        for group, modules in sorted(groups.items()):
            safe_group = group.replace("-", "_").replace(".", "_")
            lines.append("    subgraph %s[%s]" % (safe_group, group))
            for mod in sorted(set(modules)):
                lines.append("        %s[%s]" % (mod, mod))
            lines.append("    end")

        # Add cross-group dependencies
        project_modules = set(dep_graph.keys())
        for module, deps in dep_graph.items():
            for dep in deps:
                if dep in project_modules and dep != module:
                    lines.append("    %s --> %s" % (module, dep))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tier 2: AST + LLM hybrid
    # ------------------------------------------------------------------

    def generate_sequence_diagram(self, call_chains=None, context=""):
        """Generate Mermaid sequenceDiagram from call chains.

        When CallGraph is available, uses class-aware participants:
        - Class names become participants (not raw function names)
        - Method calls show Class.method() notation
        - Call paths are followed for proper sequencing
        """
        if call_chains is None:
            # Try CallGraph first; fall back to per-file extraction
            cg = self._get_call_graph()
            call_chains = self._call_chains_from_call_graph(cg)
            if not call_chains:
                call_chains = []
                for py_file in self.project_root.rglob("*.py"):
                    rel = str(py_file.relative_to(self.project_root))
                    if any(skip in rel for skip in [
                        "__pycache__", ".venv", "test"
                    ]):
                        continue
                    chains = self.analyzer.extract_call_chains(py_file)
                    call_chains.extend(chains[:20])
                    if len(call_chains) >= 80:
                        break

        if not call_chains:
            return "sequenceDiagram\n    Note over System: No call chains found"

        # Build class-aware participant mapping from FQN data
        # If call_chains have caller_fqn/callee_fqn, use class context
        has_fqn = any(c.get("caller_fqn") for c in call_chains)

        if has_fqn:
            return self._sequence_from_fqn_chains(call_chains, context)

        # Legacy path: flat caller/callee names
        lines = ["sequenceDiagram"]
        seen = set()
        count = 0
        for chain in call_chains:
            key = (chain["caller"], chain["callee"])
            if key in seen or chain["caller"] == chain["callee"]:
                continue
            seen.add(key)
            lines.append(
                "    %s->>%s: %s()" % (
                    chain["caller"], chain["callee"], chain["callee"]
                )
            )
            count += 1
            if count >= 30:
                break

        if context:
            enriched = self._llm_enrich(
                "\n".join(lines), "sequence diagram", context
            )
            if enriched:
                return enriched

        return "\n".join(lines)

    def _sequence_from_fqn_chains(self, call_chains, context=""):
        """Build class-aware sequence diagram from FQN call chains.

        Uses caller_fqn/callee_fqn to extract class participants and
        show method calls with proper Class.method() notation.
        """
        lines = ["sequenceDiagram"]

        # Extract participant classes/modules from FQNs
        # FQN format: "path/file.py::ClassName.method" or "path/file.py::func"
        participants = {}  # display_name -> order (for stable participant decl)
        order = 0

        def _participant_name(fqn):
            """Extract class name or module name as participant."""
            if "::" not in fqn:
                return fqn
            after = fqn.split("::")[-1]  # "ClassName.method" or "func"
            if "." in after:
                return after.split(".")[0]  # ClassName
            # Standalone function -> use module name
            before = fqn.split("::")[0]  # "path/file.py"
            return Path(before).stem  # "file"

        def _method_name(fqn):
            """Extract method/function name from FQN."""
            if "::" not in fqn:
                return fqn
            after = fqn.split("::")[-1]
            if "." in after:
                return after.split(".")[-1]
            return after

        # Pre-scan to register participants in call order
        for chain in call_chains:
            caller_fqn = chain.get("caller_fqn", "")
            callee_fqn = chain.get("callee_fqn", "")
            if not caller_fqn:
                continue
            cp = _participant_name(caller_fqn)
            if cp and cp not in participants:
                participants[cp] = order
                order += 1
            ep = _participant_name(callee_fqn)
            if ep and ep not in participants:
                participants[ep] = order
                order += 1

        # Declare participants in order
        for name in sorted(participants, key=lambda k: participants[k]):
            # Sanitize for Mermaid (no special chars)
            safe = name.replace("-", "_").replace(".", "_")
            if safe != name:
                lines.append("    participant %s as %s" % (safe, name))
            else:
                lines.append("    participant %s" % safe)

        # Add call arrows with method names
        seen = set()
        count = 0
        for chain in call_chains:
            caller_fqn = chain.get("caller_fqn", "")
            callee_fqn = chain.get("callee_fqn", "")
            if not caller_fqn or not callee_fqn:
                continue

            caller_p = _participant_name(caller_fqn).replace("-", "_").replace(".", "_")
            callee_p = _participant_name(callee_fqn).replace("-", "_").replace(".", "_")
            method = _method_name(callee_fqn)

            if caller_p == callee_p:
                # Self-call within same class
                key = (caller_p, method, "self")
                if key in seen:
                    continue
                seen.add(key)
                lines.append(
                    "    %s->>%s: %s()" % (caller_p, callee_p, method)
                )
            else:
                key = (caller_p, callee_p, method)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(
                    "    %s->>%s: %s()" % (caller_p, callee_p, method)
                )

            count += 1
            if count >= 40:
                break

        if context:
            enriched = self._llm_enrich(
                "\n".join(lines), "sequence diagram", context
            )
            if enriched:
                return enriched

        return "\n".join(lines)

    def generate_activity_diagram(self, function_code="", context=""):
        """Generate Mermaid flowchart TD from function logic."""
        if not function_code and not context:
            return "flowchart TD\n    Start([Start]) --> End([End])"

        prompt = (
            "Generate a Mermaid flowchart TD (activity diagram) for "
            "the following code/context. Output ONLY the Mermaid syntax, "
            "no markdown fences.\n\n%s\n\n%s"
            % (function_code[:2000], context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_mermaid(result)

        # Fallback: basic structure
        return "flowchart TD\n    Start([Start]) --> Process[Process] --> End([End])"

    def generate_state_diagram(self, state_info="", context=""):
        """Generate Mermaid stateDiagram-v2."""
        if not state_info and not context:
            return "stateDiagram-v2\n    [*] --> Idle\n    Idle --> [*]"

        prompt = (
            "Generate a Mermaid stateDiagram-v2 for the following "
            "system/context. Output ONLY the Mermaid syntax, "
            "no markdown fences.\n\n%s\n\n%s"
            % (state_info[:2000], context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_mermaid(result)

        return "stateDiagram-v2\n    [*] --> Idle\n    Idle --> [*]"

    # ------------------------------------------------------------------
    # Tier 3: LLM-powered
    # ------------------------------------------------------------------

    def generate_usecase_diagram(self, srs_content="", readme_content=""):
        """Generate PlantUML use case diagram from requirements docs."""
        if not srs_content:
            srs_path = self.project_root / "SRS.md"
            if srs_path.is_file():
                srs_content = srs_path.read_text(
                    encoding="utf-8", errors="replace"
                )[:3000]
        if not readme_content:
            readme_path = self.project_root / "README.md"
            if readme_path.is_file():
                readme_content = readme_path.read_text(
                    encoding="utf-8", errors="replace"
                )[:2000]

        content = srs_content or readme_content
        if not content:
            return _plantuml_stub("usecase", "No requirements docs found")

        prompt = (
            "Generate a PlantUML use case diagram from these requirements. "
            "Output ONLY PlantUML syntax starting with @startuml and ending "
            "with @enduml. Keep it concise (max 15 use cases).\n\n%s" % content
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("usecase", "LLM generation unavailable")

    def generate_object_diagram(self, classes=None, context=""):
        """Generate PlantUML object diagram showing class instances."""
        if classes is None:
            cg = self._get_call_graph()
            classes = self._classes_from_call_graph(cg)
            if not classes:
                classes = self.analyzer.extract_all_classes()

        class_summary = "\n".join(
            "- %s (attrs: %s)" % (
                c["name"],
                ", ".join(a["name"] for a in c.get("attributes", [])[:5])
            )
            for c in classes[:15]
        )

        prompt = (
            "Generate a PlantUML object diagram showing example instances "
            "of these classes with realistic field values. Output ONLY "
            "PlantUML syntax (@startuml to @enduml).\n\nClasses:\n%s\n\n%s"
            % (class_summary, context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("object", "LLM generation unavailable")

    def generate_deployment_diagram(self, infra_files=None):
        """Generate PlantUML deployment diagram from infrastructure files."""
        infra_content = ""
        if infra_files is None:
            # Auto-detect infrastructure files
            patterns = [
                "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                "*.k8s.yml", "*.k8s.yaml", "deployment.yml",
                "Procfile", ".github/workflows/*.yml",
            ]
            for pattern in patterns:
                for f in self.project_root.glob(pattern):
                    try:
                        infra_content += "\n--- %s ---\n" % f.name
                        infra_content += f.read_text(
                            encoding="utf-8", errors="replace"
                        )[:1000]
                    except OSError:
                        pass

        if not infra_content:
            # Generate based on project structure
            infra_content = "Python project with modules: %s" % ", ".join(
                d.name for d in self.project_root.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )

        prompt = (
            "Generate a PlantUML deployment diagram for this project. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s"
            % infra_content[:3000]
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("deployment", "LLM generation unavailable")

    def generate_communication_diagram(self, dep_graph=None, context=""):
        """Generate PlantUML communication diagram."""
        if dep_graph is None:
            cg = self._get_call_graph()
            dep_graph = self._dep_graph_from_call_graph(cg)

        module_summary = "\n".join(
            "- %s depends on: %s" % (mod, ", ".join(sorted(deps)[:5]))
            for mod, deps in sorted(dep_graph.items())[:20]
        )

        prompt = (
            "Generate a PlantUML communication diagram showing how these "
            "modules interact. Output ONLY PlantUML syntax "
            "(@startuml to @enduml).\n\nModules:\n%s\n\n%s"
            % (module_summary, context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("communication", "LLM generation unavailable")

    def generate_composite_structure_diagram(self, classes=None, context=""):
        """Generate PlantUML composite structure diagram."""
        if classes is None:
            cg = self._get_call_graph()
            classes = self._classes_from_call_graph(cg)
            if not classes:
                classes = self.analyzer.extract_all_classes()

        class_summary = "\n".join(
            "- %s: methods=%s, attrs=%s" % (
                c["name"],
                ", ".join(m["name"] for m in c.get("methods", [])[:5]),
                ", ".join(a["name"] for a in c.get("attributes", [])[:5]),
            )
            for c in classes[:10]
        )

        prompt = (
            "Generate a PlantUML composite structure diagram showing "
            "internal structure of these classes (ports, parts, connectors). "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s"
            % (class_summary, context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("composite", "LLM generation unavailable")

    def generate_interaction_overview(self, call_chains=None, context=""):
        """Generate PlantUML interaction overview diagram."""
        if call_chains is None:
            # Try CallGraph first; fall back to per-file extraction
            cg = self._get_call_graph()
            call_chains = self._call_chains_from_call_graph(cg)
            if not call_chains:
                call_chains = []
                for py_file in self.project_root.rglob("*.py"):
                    rel = str(py_file.relative_to(self.project_root))
                    if any(skip in rel for skip in [
                        "__pycache__", ".venv", "test"
                    ]):
                        continue
                    chains = self.analyzer.extract_call_chains(py_file)
                    call_chains.extend(chains[:10])
                    if len(call_chains) >= 40:
                        break

        chain_summary = "\n".join(
            "- %s calls %s" % (c["caller"], c["callee"])
            for c in call_chains[:20]
        )

        prompt = (
            "Generate a PlantUML interaction overview diagram (activity "
            "diagram with interaction fragments) for these call flows. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s"
            % (chain_summary, context[:500])
        )

        result = self._llm_generate(prompt)
        if result:
            return _clean_plantuml(result)

        return _plantuml_stub("interaction", "LLM generation unavailable")

    def generate_call_graph_diagram(self, call_graph=None):
        """Generate a Mermaid flowchart showing the method-level call graph.

        Tier 1 diagram: AST-based, no LLM required.
        Shows classes as subgraphs, methods as nodes, call edges between them.
        Entry points get bold borders, high-complexity methods get red fill.

        Args:
            call_graph: Optional pre-built CallGraph object. If None, builds
                one via _get_call_graph() lazy builder.

        Returns:
            str: Mermaid flowchart syntax string.
        """
        MAX_METHODS = 40
        MAX_EDGES = 60

        # Resolve CallGraph
        if call_graph is None:
            call_graph = self._get_call_graph()

        if call_graph is None:
            return "flowchart LR\n    note[Call graph not available]"

        try:
            lines = ["flowchart LR"]

            # Group methods by parent class from CallGraph.methods dict
            class_methods = {}  # class_name -> [(fqn, name, params_str, cyclomatic)]
            standalone = []     # [(fqn, name, params_str, cyclomatic)]
            node_count = 0

            for fqn, m in call_graph.methods.items():
                if node_count >= MAX_METHODS:
                    break
                name = m.get("name", "")
                params = m.get("params", [])
                params_str = ", ".join(
                    p.split(":")[0].strip() for p in params[:3]
                )
                cyclomatic = m.get("cyclomatic", 1)
                parent_cls = m.get("parent_class")

                if parent_cls:
                    # Extract class name from FQN like "mod.py::ClassName"
                    cls_name = parent_cls.split("::")[-1] if "::" in parent_cls else parent_cls
                    class_methods.setdefault(cls_name, []).append(
                        (fqn, name, params_str, cyclomatic)
                    )
                else:
                    standalone.append((fqn, name, params_str, cyclomatic))
                node_count += 1

            # Build FQN -> node_id mapping for edges
            def _safe_id(fqn):
                """Convert FQN to valid Mermaid node ID."""
                return fqn.replace("/", "_").replace("\\", "_").replace(
                    "::", "__").replace(".", "_").replace("-", "_")

            fqn_to_nid = {}

            # Write class subgraphs
            for cls_name, methods in sorted(class_methods.items()):
                safe_cls = cls_name.replace(".", "_").replace("-", "_")
                lines.append(
                    "    subgraph %s_group[%s]" % (safe_cls, cls_name)
                )
                for fqn, mname, params_str, _cx in methods:
                    nid = _safe_id(fqn)
                    fqn_to_nid[fqn] = nid
                    lines.append(
                        '        %s["%s(%s)"]' % (nid, mname, params_str)
                    )
                lines.append("    end")

            # Write standalone functions
            if standalone:
                lines.append("    subgraph standalone_group[Functions]")
                for fqn, fname, params_str, _cx in standalone:
                    nid = _safe_id(fqn)
                    fqn_to_nid[fqn] = nid
                    lines.append(
                        '        %s["%s(%s)"]' % (nid, fname, params_str)
                    )
                lines.append("    end")

            # Collect callee FQNs for entry point detection
            all_callee_fqns = set()
            edges = call_graph.get_edges()

            # Write call edges
            edge_count = 0
            for edge in edges:
                if edge_count >= MAX_EDGES:
                    break
                if edge.get("type") == "inheritance":
                    continue
                from_fqn = edge.get("from", "")
                to_fqn = edge.get("to", "")
                all_callee_fqns.add(to_fqn)

                from_nid = fqn_to_nid.get(from_fqn)
                to_nid = fqn_to_nid.get(to_fqn)
                if from_nid and to_nid and from_nid != to_nid:
                    lines.append("    %s --> %s" % (from_nid, to_nid))
                    edge_count += 1

            # Style: entry points (bold border) and high-complexity (red fill)
            all_method_data = []
            for cls_name, methods in class_methods.items():
                all_method_data.extend(methods)
            all_method_data.extend(standalone)

            for fqn, mname, _p, cyclomatic in all_method_data:
                nid = fqn_to_nid.get(fqn)
                if not nid:
                    continue
                is_entry = (
                    not mname.startswith("_") and fqn not in all_callee_fqns
                )
                if is_entry and cyclomatic >= 5:
                    lines.append(
                        "    style %s stroke-width:3px,fill:#ff6666" % nid
                    )
                elif is_entry:
                    lines.append(
                        "    style %s stroke-width:3px" % nid
                    )
                elif cyclomatic >= 5:
                    lines.append("    style %s fill:#ff6666" % nid)

            return "\n".join(lines)

        except Exception as e:
            logger.warning("Call graph diagram generation failed: %s", e)
            return "flowchart LR\n    note[Call graph not available]"

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def generate_all(self, scope="project"):
        """Generate all 13 diagram types.

        Calls _get_call_graph() once upfront so all individual methods share
        the same CallGraph instance without redundant builds.

        Tier 1 (AST-based, always): class, package, component, call-graph
        Tier 2 (AST + LLM): sequence, activity, state
        Tier 3 (LLM-powered): usecase, object, deployment, communication,
                               composite-structure, interaction-overview

        Returns dict: {diagram_name: syntax_string}
        """
        results = {}

        # Build CallGraph once upfront; cache in self._call_graph so that
        # all generate_* calls below reuse it via _get_call_graph().
        cg = self._get_call_graph()

        # Derive shared data sources from CallGraph or AST analyzer
        classes = []
        dep_graph = {}
        cg_chains = None

        try:
            # Classes: prefer CallGraph, fall back to AST
            cg_classes = self._classes_from_call_graph(cg)
            classes = cg_classes if cg_classes else self.analyzer.extract_all_classes()

            # Dep graph: enriched from CallGraph (already falls back internally)
            dep_graph = self._dep_graph_from_call_graph(cg)

            # Call chains: prefer CallGraph
            cg_chains = self._call_chains_from_call_graph(cg)
        except Exception as e:
            logger.warning("Shared data source build failed: %s", e)

        # ---- Tier 1: AST-based (always generate) ----
        try:
            results["class-diagram"] = self.generate_class_diagram(classes)
        except Exception as e:
            logger.debug("class-diagram failed: %s", e)

        try:
            results["package-diagram"] = self.generate_package_diagram(
                dep_graph
            )
        except Exception as e:
            logger.debug("package-diagram failed: %s", e)

        try:
            results["component-diagram"] = self.generate_component_diagram(
                dep_graph
            )
        except Exception as e:
            logger.debug("component-diagram failed: %s", e)

        try:
            results["call-graph-diagram"] = self.generate_call_graph_diagram(
                call_graph=cg
            )
        except Exception as e:
            logger.debug("call-graph-diagram failed: %s", e)

        # ---- Tier 2: AST + LLM hybrid (may fail gracefully) ----
        try:
            results["sequence-diagram"] = self.generate_sequence_diagram(
                call_chains=cg_chains
            )
        except Exception as e:
            logger.debug("sequence-diagram failed: %s", e)

        try:
            # Activity diagram: auto-detect main entry point
            entry_code = ""
            for entry_name in ["main", "run", "app", "start", "__main__"]:
                for py_file in self.project_root.rglob("*.py"):
                    rel = str(py_file.relative_to(self.project_root))
                    if any(skip in rel for skip in [
                        "__pycache__", ".venv", "test"
                    ]):
                        continue
                    if entry_name in py_file.stem or entry_name == "__main__":
                        try:
                            entry_code = py_file.read_text(
                                encoding="utf-8", errors="replace"
                            )[:2000]
                            break
                        except OSError:
                            pass
                if entry_code:
                    break
            results["activity-diagram"] = self.generate_activity_diagram(
                function_code=entry_code,
                context="Main application entry point flow"
            )
        except Exception as e:
            logger.debug("activity-diagram failed: %s", e)

        try:
            # State diagram: auto-detect from flow_state or state patterns
            state_context = ""
            if cg:
                state_classes = [
                    c.get("name", "") for c in cg.classes.values()
                    if any(kw in c.get("name", "").lower()
                           for kw in ["state", "status", "phase", "mode"])
                ]
                if state_classes:
                    state_context = "State-like classes: %s" % ", ".join(
                        state_classes[:10]
                    )
            if not state_context:
                # Check for TypedDict or enum state patterns
                state_context = "Pipeline states from project structure"
            results["state-diagram"] = self.generate_state_diagram(
                context=state_context
            )
        except Exception as e:
            logger.debug("state-diagram failed: %s", e)

        # ---- Tier 3: LLM-powered (best-effort) ----
        tier3_items = [
            ("usecase-diagram",
             lambda: self.generate_usecase_diagram()),
            ("object-diagram",
             lambda: self.generate_object_diagram(classes)),
            ("deployment-diagram",
             lambda: self.generate_deployment_diagram()),
            ("communication-diagram",
             lambda: self.generate_communication_diagram(dep_graph)),
            ("composite-structure-diagram",
             lambda: self.generate_composite_structure_diagram(classes)),
            ("interaction-overview-diagram",
             lambda: self.generate_interaction_overview(cg_chains)),
        ]

        for name, method in tier3_items:
            try:
                results[name] = method()
            except Exception as e:
                logger.debug("%s failed: %s", name, e)

        return results

    def save_diagram(self, name, syntax, format="md"):
        """Save diagram to docs/uml/{name}.md with proper markdown wrapper.

        Returns the output file path.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().strftime("%Y-%m-%d")
        title = name.replace("-", " ").title()

        # Determine if Mermaid or PlantUML
        is_plantuml = syntax.strip().startswith("@startuml")
        lang = "plantuml" if is_plantuml else "mermaid"

        content_lines = [
            "# %s" % title,
            "",
            "> Auto-generated by Claude Workflow Engine | "
            "Last updated: %s" % now,
            "",
        ]

        content_lines.append("```%s" % lang)
        content_lines.append(syntax)
        content_lines.append("```")
        content_lines.append("")
        content_lines.append("## Notes")
        content_lines.append("")
        content_lines.append("- Generated from: %s" % str(self.project_root))
        content_lines.append("- Scope: Full project")
        content_lines.append("")

        out_path = self.output_dir / ("%s.md" % name)
        out_path.write_text("\n".join(content_lines), encoding="utf-8")

        logger.info("Saved diagram: %s", out_path)
        return str(out_path)

    # ------------------------------------------------------------------
    # LLM helpers (lazy import)
    # ------------------------------------------------------------------

    def _llm_generate(self, prompt):
        """Call LLM via llm_call.py (lazy import, graceful fallback)."""
        try:
            from langgraph_engine.llm_call import llm_call
            result = llm_call(prompt, model="fast", timeout=60)
            return result
        except ImportError:
            logger.debug("llm_call not available, skipping LLM generation")
            return None
        except Exception as e:
            logger.debug("LLM call failed: %s", e)
            return None

    def _llm_enrich(self, diagram_syntax, diagram_type, context):
        """Use LLM to enrich an AST-generated diagram."""
        prompt = (
            "Improve this %s Mermaid diagram by adding better labels "
            "and notes. Output ONLY the improved Mermaid syntax, "
            "no markdown fences.\n\nCurrent diagram:\n%s\n\nContext:\n%s"
            % (diagram_type, diagram_syntax, context[:1000])
        )
        return self._llm_generate(prompt)


# ======================================================================
# Kroki Renderer
# ======================================================================

class KrokiRenderer:
    """Render PlantUML/Mermaid via Kroki.io free API."""

    KROKI_URL = "https://kroki.io"

    def render(self, diagram_text, diagram_type="plantuml",
               output_format="svg"):
        """Render diagram via Kroki.io API.

        Args:
            diagram_text: PlantUML or Mermaid source text.
            diagram_type: "plantuml", "mermaid", etc.
            output_format: "svg", "png", etc.

        Returns bytes or None on failure.
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests not available for Kroki rendering")
            return None

        url = "%s/%s/%s" % (self.KROKI_URL, diagram_type, output_format)

        try:
            resp = requests.post(
                url,
                data=diagram_text.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.content
            logger.warning(
                "Kroki API returned %d: %s",
                resp.status_code, resp.text[:200]
            )
            return None
        except Exception as e:
            logger.warning("Kroki rendering failed: %s", e)
            return None

    def render_to_file(self, diagram_text, output_path,
                       diagram_type="plantuml", output_format="svg"):
        """Render and save to file. Returns path or None."""
        data = self.render(diagram_text, diagram_type, output_format)
        if data is None:
            return None

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return str(output_path)


# ======================================================================
# Utility functions
# ======================================================================

def _simplify_type(ast_dump):
    """Convert AST dump string to readable type name."""
    if not ast_dump:
        return ""
    # Handle common patterns from ast.dump()
    s = ast_dump
    # Name(id='str') -> str
    if "Name(id='" in s:
        start = s.find("id='") + 4
        end = s.find("'", start)
        if end > start:
            return s[start:end]
    # Constant(value=...) -> skip
    if "Constant" in s:
        return ""
    # Subscript patterns -> simplify
    if len(s) > 30:
        return ""
    return ""


def _clean_mermaid(text):
    """Clean LLM output to extract Mermaid syntax."""
    if not text:
        return ""
    # Remove markdown fences if present
    text = text.strip()
    if text.startswith("```mermaid"):
        text = text[len("```mermaid"):].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _clean_plantuml(text):
    """Clean LLM output to extract PlantUML syntax."""
    if not text:
        return ""
    text = text.strip()
    # Remove markdown fences
    if text.startswith("```plantuml"):
        text = text[len("```plantuml"):].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    # Ensure @startuml/@enduml wrapper
    if not text.startswith("@startuml"):
        text = "@startuml\n" + text
    if not text.endswith("@enduml"):
        text = text + "\n@enduml"
    return text


def _plantuml_stub(diagram_type, message):
    """Generate a PlantUML stub with a note."""
    return (
        "@startuml\nnote \"%s: %s\" as N1\n@enduml"
        % (diagram_type, message)
    )


# ======================================================================
# Backward-compatibility shim
# ======================================================================
# The diagram generation logic above has been refactored into the
# diagrams/ subpackage (Strategy + Factory patterns).  This file is
# kept as the legacy entry point so that existing callers that import
# UMLDiagramGenerator or the module-level helpers directly continue to
# work without any changes.
#
# New code should use the diagrams package instead:
#
#   from langgraph_engine.diagrams import DiagramFactory
#   gen = DiagramFactory.create("class")
#   markup = gen.generate(analysis_data)
#
# The concrete generator modules are:
#   diagrams/class_diagram.py       -> ClassDiagramGenerator
#   diagrams/sequence_diagram.py    -> SequenceDiagramGenerator
#   diagrams/activity_diagram.py    -> ActivityDiagramGenerator
#   diagrams/state_diagram.py       -> StateDiagramGenerator
#   diagrams/component_diagram.py   -> ComponentDiagramGenerator
#   diagrams/package_diagram.py     -> PackageDiagramGenerator
#   diagrams/usecase_diagram.py     -> UsecaseDiagramGenerator
#   diagrams/object_diagram.py      -> ObjectDiagramGenerator
#   diagrams/deployment_diagram.py  -> DeploymentDiagramGenerator
#   diagrams/communication_diagram.py -> CommunicationDiagramGenerator
#   diagrams/composite_diagram.py   -> CompositeDiagramGenerator
#   diagrams/interaction_diagram.py -> InteractionDiagramGenerator
# ======================================================================
