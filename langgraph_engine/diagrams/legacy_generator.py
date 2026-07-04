"""diagrams/legacy_generator.py - Legacy UMLDiagramGenerator class.

Extracted from uml_generators.py. This is the monolithic generator
that was the original implementation before the Strategy pattern refactoring.

Kept for backward compatibility with documentation_manager.py.
Windows-safe: ASCII only.
"""

import ast
import logging
import re
from datetime import datetime
from pathlib import Path

from .ast_analyzer import UMLAstAnalyzer

logger = logging.getLogger(__name__)


def _make_class_info(name, file_path, bases=None, methods=None, attributes=None):
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


class UMLDiagramGenerator:
    """Generate Mermaid/PlantUML syntax from analysis results."""

    def __init__(self, project_root, output_dir=None, call_graph=None):
        import os

        self.project_root = Path(project_root)
        _env = os.environ.get("UML_OUTPUT_DIR", "").strip()
        _dir = _env or output_dir or "uml"
        self.output_dir = Path(_dir) if Path(_dir).is_absolute() else self.project_root / _dir
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
            # call_graph_builder lives at langgraph_engine.call_graph_builder,
            # which is the PARENT of this diagrams/ subpackage -- use '..'.
            # The fallback path handles the case where this module is loaded
            # outside the langgraph_engine package (e.g., via direct file exec).
            try:
                from ..call_graph_builder import build_call_graph
            except ImportError:
                from langgraph_engine.analysis.call_graph_builder import build_call_graph
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
                methods.append(
                    _make_method_info(
                        name=m.get("name", ""),
                        params=m.get("params", []),
                        return_type=m.get("return_type", ""),
                        visibility=m.get("visibility", "+"),
                    )
                )

            # Merge AST-derived attributes
            attributes = attrs_by_name.get(cls_name, [])

            abs_file_path = self.project_root / file_path if file_path else ""
            results.append(
                _make_class_info(
                    name=cls_name,
                    file_path=abs_file_path,
                    bases=bases,
                    methods=methods,
                    attributes=attributes,
                )
            )

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
            caller_name = caller_fqn.split("::")[-1] if "::" in caller_fqn else caller_fqn
            callee_name = callee_fqn.split("::")[-1] if "::" in callee_fqn else callee_fqn
            # Reduce dotted names to leaf
            caller_name = caller_name.split(".")[-1] if "." in caller_name else caller_name
            callee_name = callee_name.split(".")[-1] if "." in callee_name else callee_name

            # Derive absolute file path from caller FQN
            from_file = caller_fqn.split("::")[0] if "::" in caller_fqn else ""
            abs_file = str(self.project_root / from_file) if from_file else ""

            chains.append(
                {
                    "caller": caller_name,
                    "callee": callee_name,
                    "file": abs_file,
                    "caller_fqn": caller_fqn,
                    "callee_fqn": callee_fqn,
                    "line": edge.get("line", 0),
                    "call_type": edge.get("type", "call"),
                }
            )

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
            return 'classDiagram\n    note "No classes found"'

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
                lines.append("        %s%s(%s)%s" % (vis, method["name"], params, ret))

            lines.append("    }")

        # Add inheritance relationships
        for cls in classes:
            for base in cls.get("bases", []):
                if any(c["name"] == base for c in classes):
                    lines.append("    %s <|-- %s" % (base, cls["name"]))

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
                    if any(skip in rel for skip in ["__pycache__", ".venv", "test"]):
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
            lines.append("    %s->>%s: %s()" % (chain["caller"], chain["callee"], chain["callee"]))
            count += 1
            if count >= 30:
                break

        if context:
            enriched = self._llm_enrich("\n".join(lines), "sequence diagram", context)
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
                lines.append("    %s->>%s: %s()" % (caller_p, callee_p, method))
            else:
                key = (caller_p, callee_p, method)
                if key in seen:
                    continue
                seen.add(key)
                lines.append("    %s->>%s: %s()" % (caller_p, callee_p, method))

            count += 1
            if count >= 40:
                break

        if context:
            enriched = self._llm_enrich("\n".join(lines), "sequence diagram", context)
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
            "no markdown fences.\n\n%s\n\n%s" % (function_code[:2000], context[:500])
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
            "no markdown fences.\n\n%s\n\n%s" % (state_info[:2000], context[:500])
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
                srs_content = srs_path.read_text(encoding="utf-8", errors="replace")[:3000]
        if not readme_content:
            readme_path = self.project_root / "README.md"
            if readme_path.is_file():
                readme_content = readme_path.read_text(encoding="utf-8", errors="replace")[:2000]

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
            "- %s (attrs: %s)" % (c["name"], ", ".join(a["name"] for a in c.get("attributes", [])[:5]))
            for c in classes[:15]
        )

        prompt = (
            "Generate a PlantUML object diagram showing example instances "
            "of these classes with realistic field values. Output ONLY "
            "PlantUML syntax (@startuml to @enduml).\n\nClasses:\n%s\n\n%s" % (class_summary, context[:500])
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
                "Dockerfile",
                "docker-compose.yml",
                "docker-compose.yaml",
                "*.k8s.yml",
                "*.k8s.yaml",
                "deployment.yml",
                "Procfile",
                ".github/workflows/*.yml",
            ]
            for pattern in patterns:
                for f in self.project_root.glob(pattern):
                    try:
                        infra_content += "\n--- %s ---\n" % f.name
                        infra_content += f.read_text(encoding="utf-8", errors="replace")[:1000]
                    except OSError:
                        pass

        if not infra_content:
            # Generate based on project structure
            infra_content = "Python project with modules: %s" % ", ".join(
                d.name for d in self.project_root.iterdir() if d.is_dir() and not d.name.startswith(".")
            )

        prompt = (
            "Generate a PlantUML deployment diagram for this project. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s" % infra_content[:3000]
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
            "- %s depends on: %s" % (mod, ", ".join(sorted(deps)[:5])) for mod, deps in sorted(dep_graph.items())[:20]
        )

        prompt = (
            "Generate a PlantUML communication diagram showing how these "
            "modules interact. Output ONLY PlantUML syntax "
            "(@startuml to @enduml).\n\nModules:\n%s\n\n%s" % (module_summary, context[:500])
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
            "- %s: methods=%s, attrs=%s"
            % (
                c["name"],
                ", ".join(m["name"] for m in c.get("methods", [])[:5]),
                ", ".join(a["name"] for a in c.get("attributes", [])[:5]),
            )
            for c in classes[:10]
        )

        prompt = (
            "Generate a PlantUML composite structure diagram showing "
            "internal structure of these classes (ports, parts, connectors). "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s" % (class_summary, context[:500])
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
                    if any(skip in rel for skip in ["__pycache__", ".venv", "test"]):
                        continue
                    chains = self.analyzer.extract_call_chains(py_file)
                    call_chains.extend(chains[:10])
                    if len(call_chains) >= 40:
                        break

        chain_summary = "\n".join("- %s calls %s" % (c["caller"], c["callee"]) for c in call_chains[:20])

        prompt = (
            "Generate a PlantUML interaction overview diagram (activity "
            "diagram with interaction fragments) for these call flows. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s" % (chain_summary, context[:500])
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
            standalone = []  # [(fqn, name, params_str, cyclomatic)]
            node_count = 0

            for fqn, m in call_graph.methods.items():
                if node_count >= MAX_METHODS:
                    break
                name = m.get("name", "")
                params = m.get("params", [])
                params_str = ", ".join(p.split(":")[0].strip() for p in params[:3])
                cyclomatic = m.get("cyclomatic", 1)
                parent_cls = m.get("parent_class")

                if parent_cls:
                    # Extract class name from FQN like "mod.py::ClassName"
                    cls_name = parent_cls.split("::")[-1] if "::" in parent_cls else parent_cls
                    class_methods.setdefault(cls_name, []).append((fqn, name, params_str, cyclomatic))
                else:
                    standalone.append((fqn, name, params_str, cyclomatic))
                node_count += 1

            # Build FQN -> node_id mapping for edges
            def _safe_id(fqn):
                """Convert FQN to valid Mermaid node ID."""
                return fqn.replace("/", "_").replace("\\", "_").replace("::", "__").replace(".", "_").replace("-", "_")

            fqn_to_nid = {}

            # Write class subgraphs
            for cls_name, methods in sorted(class_methods.items()):
                safe_cls = cls_name.replace(".", "_").replace("-", "_")
                lines.append("    subgraph %s_group[%s]" % (safe_cls, cls_name))
                for fqn, mname, params_str, _cx in methods:
                    nid = _safe_id(fqn)
                    fqn_to_nid[fqn] = nid
                    lines.append('        %s["%s(%s)"]' % (nid, mname, params_str))
                lines.append("    end")

            # Write standalone functions
            if standalone:
                lines.append("    subgraph standalone_group[Functions]")
                for fqn, fname, params_str, _cx in standalone:
                    nid = _safe_id(fqn)
                    fqn_to_nid[fqn] = nid
                    lines.append('        %s["%s(%s)"]' % (nid, fname, params_str))
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
                is_entry = not mname.startswith("_") and fqn not in all_callee_fqns
                if is_entry and cyclomatic >= 5:
                    lines.append("    style %s stroke-width:3px,fill:#ff6666" % nid)
                elif is_entry:
                    lines.append("    style %s stroke-width:3px" % nid)
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
            results["package-diagram"] = self.generate_package_diagram(dep_graph)
        except Exception as e:
            logger.debug("package-diagram failed: %s", e)

        try:
            results["component-diagram"] = self.generate_component_diagram(dep_graph)
        except Exception as e:
            logger.debug("component-diagram failed: %s", e)

        try:
            results["call-graph-diagram"] = self.generate_call_graph_diagram(call_graph=cg)
        except Exception as e:
            logger.debug("call-graph-diagram failed: %s", e)

        # ---- Tier 2: AST + LLM hybrid (may fail gracefully) ----
        try:
            results["sequence-diagram"] = self.generate_sequence_diagram(call_chains=cg_chains)
        except Exception as e:
            logger.debug("sequence-diagram failed: %s", e)

        try:
            # Activity diagram: auto-detect main entry point
            entry_code = ""
            for entry_name in ["main", "run", "app", "start", "__main__"]:
                for py_file in self.project_root.rglob("*.py"):
                    rel = str(py_file.relative_to(self.project_root))
                    if any(skip in rel for skip in ["__pycache__", ".venv", "test"]):
                        continue
                    if entry_name in py_file.stem or entry_name == "__main__":
                        try:
                            entry_code = py_file.read_text(encoding="utf-8", errors="replace")[:2000]
                            break
                        except OSError:
                            pass
                if entry_code:
                    break
            results["activity-diagram"] = self.generate_activity_diagram(
                function_code=entry_code, context="Main application entry point flow"
            )
        except Exception as e:
            logger.debug("activity-diagram failed: %s", e)

        try:
            # State diagram: auto-detect from flow_state or state patterns
            state_context = ""
            if cg:
                state_classes = [
                    c.get("name", "")
                    for c in cg.classes.values()
                    if any(kw in c.get("name", "").lower() for kw in ["state", "status", "phase", "mode"])
                ]
                if state_classes:
                    state_context = "State-like classes: %s" % ", ".join(state_classes[:10])
            if not state_context:
                # Check for TypedDict or enum state patterns
                state_context = "Pipeline states from project structure"
            results["state-diagram"] = self.generate_state_diagram(context=state_context)
        except Exception as e:
            logger.debug("state-diagram failed: %s", e)

        # ---- Tier 3: LLM-powered (best-effort) ----
        tier3_items = [
            ("usecase-diagram", lambda: self.generate_usecase_diagram()),
            ("object-diagram", lambda: self.generate_object_diagram(classes)),
            ("deployment-diagram", lambda: self.generate_deployment_diagram()),
            ("communication-diagram", lambda: self.generate_communication_diagram(dep_graph)),
            ("composite-structure-diagram", lambda: self.generate_composite_structure_diagram(classes)),
            ("interaction-overview-diagram", lambda: self.generate_interaction_overview(cg_chains)),
        ]

        for name, method in tier3_items:
            try:
                results[name] = method()
            except Exception as e:
                logger.debug("%s failed: %s", name, e)

        return results

    def save_diagram(self, name, syntax, format="md"):
        """Save diagram to uml/{name}.md with proper markdown wrapper.

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
            "> Auto-generated by Claude Workflow Engine | " "Last updated: %s" % now,
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

    def _get_system_prompt(self, diagram_type):
        # type: (str) -> str
        """Build a system prompt enriched with Domain 46 skill context.

        Reads M1-M6 sections from the corresponding Domain 46 skill via
        skill_context.get_skill_context(). Returns the diagram-type-specific
        base prompt from UML_SYSTEM_PROMPTS._PROMPT_MAP if skill context is
        unavailable (graceful degradation). Never returns an empty string.

        Args:
            diagram_type: One of the 14 UML diagram type slugs. Unknown slugs
                          resolve to the mermaid-syntax-engine-core skill.

        Returns:
            System prompt string. Guaranteed non-empty (baseline fallback).
        """
        import logging as _log

        _logger = _log.getLogger(__name__)

        try:
            from UML_SYSTEM_PROMPTS import _PROMPT_MAP, BASELINE_SYSTEM_PROMPT

            base_prompt = _PROMPT_MAP.get(diagram_type, BASELINE_SYSTEM_PROMPT)
        except ImportError:
            base_prompt = (
                "You are a UML 2.5.1 diagram expert. Generate syntactically "
                "correct UML syntax. Follow OMG UML 2.5 notation."
            )

        _SKILL_MAP = {
            "class": "uml-class-diagram-core",
            "package": "uml-package-diagram-core",
            "component": "uml-component-diagram-core",
            "deployment": "uml-deployment-diagram-core",
            "object": "uml-object-diagram-core",
            "composite": "uml-composite-structure-core",
            "usecase": "uml-use-case-diagram-core",
            "activity": "uml-activity-diagram-core",
            "state": "uml-state-machine-core",
            "interaction": "uml-interaction-overview-core",
            "sequence": "uml-sequence-diagram-core",
            "communication": "uml-communication-diagram-core",
            "timing": "uml-timing-diagram-core",
            "call_graph": "diagram-from-code-core",
            "call_graph_rich": "diagram-layout-algorithms-core",
        }
        skill_name = _SKILL_MAP.get(diagram_type, "mermaid-syntax-engine-core")
        skill_context_text = ""

        try:
            from skill_context import get_skill_context

            skill_context_text = get_skill_context(skill_name)
        except ImportError:
            _logger.debug("skill_context not available; using base prompt only")
        except Exception as exc:
            _logger.debug("skill_context read failed for %s: %s", skill_name, exc)

        if not skill_context_text:
            return base_prompt

        enriched = base_prompt + "\n\n--- DOMAIN 46 SKILL CONTEXT (M1-M6 Foundations) ---\n" + skill_context_text[:4000]
        return enriched

    def generate_timing_diagram(self, process_name=""):
        # type: (str) -> str
        """Generate a UML timing diagram as Mermaid 10.x gantt syntax.

        The four mandatory header lines (gantt, title, dateFormat, axisFormat)
        are hard-coded and never delegated to the LLM. The LLM fills only the
        section/task content. Task IDs are post-processed via
        _sanitize_gantt_sections() to replace invalid characters with underscores.
        Falls back to _build_stub_gantt_sections() on any LLM error.

        Args:
            process_name: Human-readable name of the process being timed.
                          Defaults to "" which renders as "System Process Timeline".

        Returns:
            Mermaid gantt syntax string. Returns a minimal valid stub gantt
            on LLM error. Never raises.
        """
        import logging as _log

        _logger = _log.getLogger(__name__)

        title = process_name.strip() if process_name and process_name.strip() else "System Process Timeline"

        system_prompt = self._get_system_prompt("timing")

        llm_instruction = (
            "Generate ONLY the section blocks for a Mermaid 10.x gantt diagram "
            "for a process named: %s\n\n"
            "Requirements:\n"
            "- Output ONLY section blocks (starting with 'section ...')\n"
            "- Do NOT output gantt, title, dateFormat, or axisFormat lines\n"
            "- Include exactly 3 sections: Initialization, Processing, Completion\n"
            "- Each section must have 2-3 tasks\n"
            "- Task ID: alphanumeric and underscore ONLY (e.g., task_init_A)\n"
            "- Task format: TaskLabel : taskId, YYYY-MM-DD, Nd\n"
            "- Dates starting from 2026-01-01, increment by duration\n"
            "- Duration format: 1d or 2d only\n"
            "- No hyphens in task IDs. Underscores only.\n"
            "- No markdown fences.\n"
        ) % title

        sections_text = None
        try:
            sections_text = _llm_generate_with_system(self, llm_instruction, system_prompt)
        except Exception as exc:
            _logger.debug("LLM timing generation failed: %s", exc)

        if sections_text:
            sections_text = _sanitize_gantt_sections(sections_text)
        else:
            sections_text = _build_stub_gantt_sections()

        header_lines = [
            "gantt",
            "    title %s -- Timing Diagram" % title,
            "    dateFormat  YYYY-MM-DD",
            "    axisFormat  %Y-%m-%d",
        ]
        return "\n".join(header_lines) + "\n" + sections_text

    def generate_uml_from_code(self, source_code, language="python"):
        # type: (str, str) -> str
        """Generate a Mermaid classDiagram from source code via parsing.

        For Python: uses stdlib ast module (Phase 1 priority). Falls back to
        LLM if ast.parse() raises any exception.
        For Java/Kotlin: uses regex pattern extraction (Phase 1 best-effort).
        For TypeScript/JavaScript: uses regex extraction.
        For all other languages: delegates entirely to LLM.

        Maximum 50 classes rendered. System prompt uses _get_system_prompt("class").

        Args:
            source_code: Raw source code string to analyze.
            language: Source language. Supported: "python", "java", "kotlin",
                      "typescript", "javascript". Defaults to "python".

        Returns:
            Mermaid classDiagram syntax string. Returns a minimal stub classDiagram
            on any parse failure. Never raises.
        """
        MAX_CLASSES = 50

        if not source_code or not source_code.strip():
            return 'classDiagram\n    note "No source code provided"'

        lang = language.lower().strip() if language else "python"

        if lang == "python":
            return _parse_python_to_class_diagram(self, source_code, MAX_CLASSES)

        if lang in ("java", "kotlin"):
            return _parse_jvm_to_class_diagram(source_code, lang, MAX_CLASSES)

        if lang in ("typescript", "javascript"):
            return _parse_ts_to_class_diagram(source_code, MAX_CLASSES)

        return _llm_fallback_class_diagram(self, source_code, language)


# ======================================================================
# Kroki Renderer
# ======================================================================

# ======================================================================
# Module-level helpers for the 3 new UMLDiagramGenerator methods
# (must live outside the class; referenced via module-level calls)
# ======================================================================

_GANTT_TASK_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_]")
_GANTT_DEFAULT_START = "2026-01-01"


def _llm_generate_with_system(self, prompt, system_prompt):
    # type: (Any, str, str) -> Optional[str]
    """Call LLM with an explicit system prompt via llm_call.py.

    Attempts to import langgraph_engine.llm_call.llm_call. Falls back to
    self._llm_generate(prompt) if llm_call is unavailable. Returns None on
    any unrecoverable error.

    Args:
        prompt: User-level prompt string passed to the LLM.
        system_prompt: System-level context and instruction string.

    Returns:
        LLM response string, or None on failure.
    """
    import logging as _log

    _logger = _log.getLogger(__name__)
    try:
        from langgraph_engine.llm_call import llm_call

        full_prompt = system_prompt + "\n\n---\n\n" + prompt
        return llm_call(full_prompt, model="fast", timeout=60)
    except ImportError:
        _logger.debug("llm_call not available; falling back to _llm_generate")
        return self._llm_generate(prompt)
    except Exception as exc:
        _logger.debug("LLM call with system prompt failed: %s", exc)
        return None


def _sanitize_gantt_sections(sections_text):
    # type: (str) -> str
    """Post-process LLM gantt sections to enforce valid Mermaid 10.x task IDs.

    Scans each task definition line and replaces any character outside
    [a-zA-Z0-9_] in the task ID field with an underscore. Enforces Nd
    duration format (appends 'd' if unit is missing).

    Args:
        sections_text: Raw LLM-generated section block string.

    Returns:
        Sanitized section string with valid task IDs and duration format.
    """
    task_line_pattern = re.compile(
        r"^(\s+\S[^:]+:\s*)(\w[\w\-\s]*?)\s*," r"\s*([\d]{4}-[\d]{2}-[\d]{2})\s*,\s*(\d+)([a-z]?)\s*$"
    )
    output_lines = []
    for line in sections_text.splitlines():
        match = task_line_pattern.match(line)
        if match:
            label_part = match.group(1)
            task_id_raw = match.group(2).strip()
            date_part = match.group(3)
            duration_num = match.group(4)
            duration_unit = match.group(5) if match.group(5) else "d"

            task_id_clean = _GANTT_TASK_ID_PATTERN.sub("_", task_id_raw)
            if not task_id_clean or task_id_clean[0].isdigit():
                task_id_clean = "task_" + task_id_clean

            output_lines.append(
                "%s%s, %s, %s%s"
                % (
                    label_part,
                    task_id_clean,
                    date_part,
                    duration_num,
                    duration_unit,
                )
            )
        else:
            output_lines.append(line)
    return "\n".join(output_lines)


def _build_stub_gantt_sections():
    # type: () -> str
    """Build a minimal valid Mermaid 10.x gantt section block as fallback.

    Returns:
        Hard-coded section block string with valid task IDs and Nd durations.
    """
    return (
        "    section Initialization\n"
        "        Setup Environment : task_setup_env, %s, 1d\n"
        "        Load Configuration : task_load_config, 2026-01-02, 1d\n"
        "    section Processing\n"
        "        Execute Main Logic : task_execute_main, 2026-01-03, 2d\n"
        "        Validate Results : task_validate_results, 2026-01-05, 1d\n"
        "    section Completion\n"
        "        Write Output : task_write_output, 2026-01-06, 1d\n"
        "        Cleanup Resources : task_cleanup_resources, 2026-01-07, 1d\n"
    ) % _GANTT_DEFAULT_START


def _ast_name_to_str(node):
    # type: (Any) -> str
    """Convert an ast.Name, ast.Attribute, or ast.Subscript node to a string.

    Args:
        node: AST node (ast.Name, ast.Attribute, or ast.Subscript).

    Returns:
        String representation of the node, or "" for unrecognized types.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_name_to_str(node.value)
        return ("%s.%s" % (parent, node.attr)) if parent else node.attr
    if isinstance(node, ast.Subscript):
        return _ast_name_to_str(node.value)
    return ""


def _extract_method_params(func_node):
    # type: (Any) -> str
    """Extract simplified parameter string from an ast.FunctionDef node.

    Skips 'self' and 'cls' parameters. Limits to 4 parameters for readability.

    Args:
        func_node: ast.FunctionDef or ast.AsyncFunctionDef node.

    Returns:
        Comma-separated parameter string (up to 4 params, excluding self/cls).
    """
    args = func_node.args
    param_names = []
    for arg in args.args:
        if arg.arg in ("self", "cls"):
            continue
        param_names.append(arg.arg)
        if len(param_names) >= 4:
            break
    return ", ".join(param_names)


def _extract_return_type(func_node):
    # type: (Any) -> str
    """Extract return type annotation string from an ast.FunctionDef node.

    Args:
        func_node: ast.FunctionDef or ast.AsyncFunctionDef node.

    Returns:
        Return type string derived from the annotation node, or "" if absent.
    """
    if func_node.returns is None:
        return ""
    return _ast_name_to_str(func_node.returns)


def _build_mermaid_class_diagram(classes):
    # type: (List[Dict[str, Any]]) -> str
    """Build Mermaid 10.x classDiagram syntax from a parsed class list.

    Args:
        classes: List of dicts with keys: name (str), bases (list),
                 methods (list of tuples), attributes (list of tuples),
                 stereotype (str, optional).

    Returns:
        Mermaid classDiagram syntax string.
    """
    lines = ["classDiagram"]
    for cls in classes:
        class_name = cls["name"]
        stereotype = cls.get("stereotype", "")
        lines.append("    class %s {" % class_name)
        if stereotype:
            lines.append("        %s" % stereotype)
        for attr_entry in cls.get("attributes", []):
            vis = attr_entry[0]
            a_name = attr_entry[1]
            a_type = attr_entry[2] if len(attr_entry) > 2 else ""
            if a_type:
                lines.append("        %s%s %s" % (vis, a_type, a_name))
            else:
                lines.append("        %s%s" % (vis, a_name))
        for method_entry in cls.get("methods", []):
            vis = method_entry[0]
            m_name = method_entry[1]
            params = method_entry[2] if len(method_entry) > 2 else ""
            ret_type = method_entry[3] if len(method_entry) > 3 else ""
            if ret_type:
                lines.append("        %s%s(%s) %s" % (vis, m_name, params, ret_type))
            else:
                lines.append("        %s%s(%s)" % (vis, m_name, params))
        lines.append("    }")

    class_names = set(cls["name"] for cls in classes)
    for cls in classes:
        for base in cls.get("bases", []):
            if base in class_names:
                lines.append("    %s <|-- %s" % (base, cls["name"]))
    return "\n".join(lines)


def _parse_python_to_class_diagram(self, source_code, max_classes):
    # type: (Any, str, int) -> str
    """Parse Python source with ast module and build Mermaid classDiagram.

    Args:
        source_code: Python source string.
        max_classes: Maximum number of classes to include in the diagram.

    Returns:
        Mermaid classDiagram string.
    """
    import logging as _log

    _logger = _log.getLogger(__name__)
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        _logger.debug("ast.parse SyntaxError: %s -- falling back to LLM", exc)
        return _llm_fallback_class_diagram(self, source_code, "python")
    except Exception as exc:
        _logger.debug("ast.parse failed: %s -- falling back to LLM", exc)
        return _llm_fallback_class_diagram(self, source_code, "python")

    classes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if len(classes) >= max_classes:
            break
        class_name = node.name
        bases = []
        for base in node.bases:
            base_name = _ast_name_to_str(base)
            if base_name and base_name != "object":
                bases.append(base_name)
        methods = []
        attributes = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m_name = item.name
                visibility = "-" if m_name.startswith("__") else ("#" if m_name.startswith("_") else "+")
                params = _extract_method_params(item)
                ret_type = _extract_return_type(item)
                methods.append((visibility, m_name, params, ret_type))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attr_name = target.id
                        vis = "-" if attr_name.startswith("__") else ("#" if attr_name.startswith("_") else "+")
                        attributes.append((vis, attr_name, ""))
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name):
                    attr_name = item.target.id
                    vis = "-" if attr_name.startswith("__") else ("#" if attr_name.startswith("_") else "+")
                    type_str = _ast_name_to_str(item.annotation) if item.annotation else ""
                    attributes.append((vis, attr_name, type_str))
        classes.append(
            {
                "name": class_name,
                "bases": bases,
                "methods": methods[:15],
                "attributes": attributes[:10],
            }
        )

    if not classes:
        return _llm_fallback_class_diagram(self, source_code, "python")
    return _build_mermaid_class_diagram(classes)


def _parse_jvm_to_class_diagram(source_code, language, max_classes):
    # type: (str, str, int) -> str
    """Parse Java or Kotlin source with regex and build Mermaid classDiagram.

    Args:
        source_code: Java or Kotlin source string.
        language: "java" or "kotlin".
        max_classes: Maximum number of classes to render.

    Returns:
        Mermaid classDiagram string.
    """
    class_pattern = re.compile(
        r"(?:public|private|protected|internal)?\s*"
        r"(?:abstract\s+|open\s+|sealed\s+|data\s+)?"
        r"(class|interface|enum|object)\s+(\w+)"
        r"(?:\s*(?:extends|:)\s*([\w,\s<>]+))?"
    )
    method_pattern = re.compile(
        r"(?:public|private|protected|internal|override|fun|def)?\s+"
        r"(?:static\s+|abstract\s+|open\s+|override\s+)?"
        r"(?:[\w<>\[\]]+\s+)?(\w+)\s*\(([^)]{0,200})\)"
    )
    classes = []
    for match in class_pattern.finditer(source_code):
        if len(classes) >= max_classes:
            break
        kind = match.group(1)
        name = match.group(2)
        bases_raw = match.group(3) or ""
        bases = [b.strip().split("<")[0].strip() for b in bases_raw.split(",") if b.strip()]
        stereotype = ""
        if kind == "interface":
            stereotype = "<<interface>>"
        elif kind == "enum":
            stereotype = "<<enumeration>>"
        start_pos = match.end()
        snippet = source_code[start_pos : start_pos + 1000]
        methods = []
        for m_match in method_pattern.finditer(snippet):
            m_name = m_match.group(1)
            if m_name in ("if", "for", "while", "return", "new", "class"):
                continue
            methods.append(("+", m_name, "", ""))
            if len(methods) >= 10:
                break
        classes.append(
            {
                "name": name,
                "bases": bases,
                "methods": methods,
                "attributes": [],
                "stereotype": stereotype,
            }
        )
    if not classes:
        return 'classDiagram\n    note "No classes detected in %s source"' % language
    return _build_mermaid_class_diagram(classes)


def _parse_ts_to_class_diagram(source_code, max_classes):
    # type: (str, int) -> str
    """Parse TypeScript or JavaScript source with regex and build Mermaid classDiagram.

    Args:
        source_code: TypeScript or JavaScript source string.
        max_classes: Maximum number of classes to render.

    Returns:
        Mermaid classDiagram string.
    """
    class_pattern = re.compile(
        r"(?:export\s+)?(?:abstract\s+)?(class|interface)\s+(\w+)"
        r"(?:\s+extends\s+([\w,\s<>]+))?"
        r"(?:\s+implements\s+([\w,\s<>]+))?"
    )
    method_pattern = re.compile(
        r"(?:public|private|protected|static|async|abstract|override)?\s*"
        r"(\w+)\s*\(([^)]{0,200})\)\s*(?::\s*[\w<>\[\]|]+)?\s*[{;]"
    )
    prop_pattern = re.compile(r"(?:public|private|protected|readonly)?\s+" r"(\w+)\s*(?::\s*([\w<>\[\]|]+))?\s*(?:=|;)")
    classes = []
    for match in class_pattern.finditer(source_code):
        if len(classes) >= max_classes:
            break
        kind = match.group(1)
        name = match.group(2)
        extends_raw = match.group(3) or ""
        implements_raw = match.group(4) or ""
        bases = []
        if extends_raw:
            bases.extend([b.strip().split("<")[0].strip() for b in extends_raw.split(",") if b.strip()])
        if implements_raw:
            bases.extend([b.strip().split("<")[0].strip() for b in implements_raw.split(",") if b.strip()])
        stereotype = "<<interface>>" if kind == "interface" else ""
        start_pos = match.end()
        snippet = source_code[start_pos : start_pos + 1200]
        methods = []
        for m_match in method_pattern.finditer(snippet):
            m_name = m_match.group(1)
            if m_name in ("if", "for", "while", "return", "new", "const", "let", "var"):
                continue
            vis = "-" if m_name.startswith("_") else "+"
            methods.append((vis, m_name, "", ""))
            if len(methods) >= 10:
                break
        attributes = []
        for p_match in prop_pattern.finditer(snippet[:500]):
            p_name = p_match.group(1)
            p_type = p_match.group(2) or ""
            if p_name in ("return", "const", "let", "var", "new", "if"):
                continue
            vis = "-" if p_name.startswith("_") else "+"
            attributes.append((vis, p_name, p_type))
            if len(attributes) >= 8:
                break
        classes.append(
            {
                "name": name,
                "bases": bases,
                "methods": methods,
                "attributes": attributes,
                "stereotype": stereotype,
            }
        )
    if not classes:
        return 'classDiagram\n    note "No classes detected in TypeScript source"'
    return _build_mermaid_class_diagram(classes)


def _llm_fallback_class_diagram(self, source_code, language):
    # type: (Any, str, str) -> str
    """Use LLM to generate a classDiagram when AST/regex parsing fails.

    Args:
        source_code: Raw source code string.
        language: Source language identifier (e.g., "python", "java").

    Returns:
        Mermaid classDiagram string, or stub on LLM error.
    """
    system_prompt = self._get_system_prompt("class")
    prompt = (
        "Parse this %s source code and generate a Mermaid 10.x classDiagram. "
        "Extract all classes, their public methods, attributes, and inheritance. "
        "Output ONLY the Mermaid syntax starting with 'classDiagram'. "
        "No markdown fences.\n\n%s"
    ) % (language, source_code[:3000])

    result = _llm_generate_with_system(self, prompt, system_prompt)
    if result:
        result = result.strip()
        if result.startswith("```"):
            result = re.sub(r"^```[a-z]*\n?", "", result).rstrip("`").strip()
        if result.startswith("classDiagram"):
            return result

    return 'classDiagram\n    note "Could not parse %s source"' % language


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
        text = text[len("```mermaid") :].strip()
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
        text = text[len("```plantuml") :].strip()
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
    return '@startuml\nnote "%s: %s" as N1\n@enduml' % (diagram_type, message)


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
