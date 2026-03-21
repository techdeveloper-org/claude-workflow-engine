"""
UML AST Analyzer - Python AST analysis for structural UML diagrams.

Extracted from uml_generators.py (UMLAstAnalyzer class + data helpers).
"""

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ======================================================================
# Data helpers (plain dicts, no dataclass dependency)
# ======================================================================

def make_class_info(name, file_path, bases=None, methods=None, attributes=None):
    """Create a ClassInfo dict."""
    return {
        "name": name,
        "file_path": str(file_path),
        "module": str(Path(file_path).stem),
        "bases": bases or [],
        "methods": methods or [],
        "attributes": attributes or [],
    }


def make_method_info(name, params=None, return_type="", visibility="+"):
    """Create a MethodInfo dict."""
    return {
        "name": name,
        "params": params or [],
        "return_type": return_type,
        "visibility": visibility,
    }


def make_attr_info(name, type_hint="", visibility="+"):
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
                        make_method_info(item.name, params, ret, vis)
                    )

                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes.append(
                                make_attr_info(target.id, "", "+")
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
                            make_attr_info(item.target.id, hint, "+")
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
                                        make_attr_info(attr_name, "", vis)
                                    )

            classes.append(
                make_class_info(
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
            from ..call_graph_builder import _CallGraphVisitor
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
                    caller_name = (
                        caller_fqn.split("::")[-1]
                        if "::" in caller_fqn else caller_fqn
                    )
                    callee_name = (
                        callee_raw.split("::")[-1]
                        if "::" in callee_raw else callee_raw
                    )
                    callee_name = (
                        callee_name.split(".")[-1]
                        if "." in callee_name else callee_name
                    )

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
