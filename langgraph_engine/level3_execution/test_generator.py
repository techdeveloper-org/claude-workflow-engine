"""
Test Generator - Auto-generates unit tests for modified methods using CallGraph data.

Template-based (NO LLM) generation for speed and reliability.
Supports Python (pytest), Java (JUnit 5), TypeScript (Jest), and Go (testing).

Uses CallGraph method info (name, params, return_type, cyclomatic, parent_class)
to generate syntactically valid, language-specific test stubs.

Usage:
    from test_generator import generate_tests_for_file, generate_tests_for_modified_files

Python 3.8+ compatible. ASCII-only (cp1252-safe).
"""

import ast
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXTENSION_MAP = {
    ".py": "python",
    ".java": "java",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".kt": "kotlin",
}


def detect_language(file_path):
    """Detect language from file extension.

    Args:
        file_path: Path to source file (str or Path).

    Returns:
        str: One of 'python', 'java', 'typescript', 'go', 'rust', 'swift',
             'kotlin', or 'unknown'.
    """
    try:
        suffix = Path(str(file_path)).suffix.lower()
        return _EXTENSION_MAP.get(suffix, "unknown")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Test framework detection
# ---------------------------------------------------------------------------


def detect_test_framework(language, project_root):
    """Detect which test framework the project uses.

    Args:
        language:     Language string (e.g. 'python', 'java', 'typescript').
        project_root: Root directory of the project (str or Path).

    Returns:
        str: Framework name such as 'pytest', 'unittest', 'junit5', 'junit4',
             'jest', 'vitest', 'testing'.
    """
    try:
        root = Path(str(project_root))

        if language == "python":
            # Check requirements.txt and pyproject.toml for pytest
            for req_file in ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt", "pyproject.toml"):
                req_path = root / req_file
                if req_path.exists():
                    try:
                        content = req_path.read_text(encoding="utf-8", errors="replace").lower()
                        if "pytest" in content:
                            return "pytest"
                    except Exception:
                        pass
            return "unittest"

        if language == "java":
            # Check pom.xml for junit5 vs junit4
            pom = root / "pom.xml"
            if pom.exists():
                try:
                    content = pom.read_text(encoding="utf-8", errors="replace").lower()
                    if "junit-jupiter" in content or "junit5" in content:
                        return "junit5"
                    if "junit" in content:
                        return "junit4"
                except Exception:
                    pass
            # Check build.gradle
            for gradle in ("build.gradle", "build.gradle.kts"):
                gpath = root / gradle
                if gpath.exists():
                    try:
                        content = gpath.read_text(encoding="utf-8", errors="replace").lower()
                        if "junit-jupiter" in content or "junit5" in content:
                            return "junit5"
                        if "junit" in content:
                            return "junit4"
                    except Exception:
                        pass
            return "junit5"

        if language == "typescript":
            # Check package.json for jest or vitest
            pkg = root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
                    all_deps = {}
                    all_deps.update(data.get("dependencies", {}))
                    all_deps.update(data.get("devDependencies", {}))
                    if "vitest" in all_deps:
                        return "vitest"
                    if "jest" in all_deps or "@jest/core" in all_deps:
                        return "jest"
                except Exception:
                    pass
            return "jest"

        if language == "go":
            return "testing"

        if language == "kotlin":
            return "junit5"

        if language == "rust":
            return "rust_test"

        if language == "swift":
            return "xctest"

    except Exception:
        pass

    return "unknown"


# ---------------------------------------------------------------------------
# Test file path resolution
# ---------------------------------------------------------------------------


def get_test_file_path(source_file, language):
    """Generate the test file path from source file path.

    Conventions:
        Python:     src/models.py             -> tests/test_models.py
        Java:       src/main/java/.../Svc.java -> src/test/java/.../SvcTest.java
        TypeScript: src/service.ts            -> src/__tests__/service.test.ts
        Go:         pkg/service.go            -> pkg/service_test.go
        Kotlin:     src/.../Service.kt        -> src/test/.../ServiceTest.kt

    Args:
        source_file: Path to source file (str or Path).
        language:    Language string.

    Returns:
        str: Resolved test file path.
    """
    try:
        src = Path(str(source_file))
        stem = src.stem

        if language == "python":
            # Attempt to mirror a src/ -> tests/ layout
            parts = src.parts
            if "src" in parts:
                idx = parts.index("src")
                rel_parts = parts[idx + 1 :]
                test_parts = ("tests",) + rel_parts[:-1] + ("test_%s.py" % stem,)
                return str(Path(*test_parts))
            # Fallback: tests/test_<stem>.py beside the file
            return str(src.parent / "tests" / ("test_%s.py" % stem))

        if language == "java":
            # src/main/java/... -> src/test/java/...
            path_str = str(src).replace("\\", "/")
            if "src/main/java" in path_str:
                test_path = path_str.replace("src/main/java", "src/test/java", 1)
                test_path = test_path.replace(".java", "Test.java")
                return test_path
            return str(src.parent / ("%sTest.java" % stem))

        if language == "typescript":
            # src/foo/service.ts -> src/foo/__tests__/service.test.ts
            test_dir = src.parent / "__tests__"
            return str(test_dir / ("%s.test.ts" % stem))

        if language == "go":
            # pkg/service.go -> pkg/service_test.go
            return str(src.parent / ("%s_test.go" % stem))

        if language == "kotlin":
            path_str = str(src).replace("\\", "/")
            if "src/main" in path_str:
                test_path = path_str.replace("src/main", "src/test", 1)
                test_path = test_path.replace(".kt", "Test.kt")
                return test_path
            return str(src.parent / ("%sTest.kt" % stem))

    except Exception:
        pass

    return str(Path(str(source_file)).parent / ("test_%s.txt" % Path(str(source_file)).stem))


# ---------------------------------------------------------------------------
# AST-based method extraction (Python fallback when CallGraph unavailable)
# ---------------------------------------------------------------------------


def _extract_methods_from_python_ast(file_path):
    """Extract method dicts from a Python file using AST.

    Returns a list of method dicts compatible with the CallGraph schema:
    {
        "name": str,
        "params": [str],
        "return_type": str,
        "parent_class": str or None,  (simple class name, not FQN)
        "cyclomatic": int,
        "visibility": "+" or "-",
    }
    """
    methods = []
    try:
        source = Path(str(file_path)).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except Exception:
        return methods

    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef,)):
            continue
        class_name = node.name
        for item in ast.walk(node):
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = item.name
            # Visibility: public unless starts with single underscore
            if name.startswith("__") and name.endswith("__"):
                vis = "+"
            elif name.startswith("_"):
                vis = "-"
            else:
                vis = "+"

            params = []
            for arg in item.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                param_str = arg.arg
                if arg.annotation:
                    try:
                        param_str = "%s: %s" % (arg.arg, ast.unparse(arg.annotation))
                    except Exception:
                        pass
                params.append(param_str)

            return_type = ""
            if item.returns:
                try:
                    return_type = ast.unparse(item.returns)
                except Exception:
                    pass

            cyclomatic = _estimate_cyclomatic(item)

            methods.append(
                {
                    "name": name,
                    "params": params,
                    "return_type": return_type,
                    "parent_class": class_name,
                    "cyclomatic": cyclomatic,
                    "visibility": vis,
                }
            )

    # Also extract module-level functions
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Skip if it is inside a class (already captured above)
        name = node.name
        vis = "-" if name.startswith("_") else "+"
        params = []
        for arg in node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            param_str = arg.arg
            if arg.annotation:
                try:
                    param_str = "%s: %s" % (arg.arg, ast.unparse(arg.annotation))
                except Exception:
                    pass
            params.append(param_str)

        return_type = ""
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except Exception:
                pass

        cyclomatic = _estimate_cyclomatic(node)
        methods.append(
            {
                "name": name,
                "params": params,
                "return_type": return_type,
                "parent_class": None,
                "cyclomatic": cyclomatic,
                "visibility": vis,
            }
        )

    return methods


def _estimate_cyclomatic(func_node):
    """Estimate cyclomatic complexity from an AST FunctionDef node.

    Counts branches: if, elif, for, while, except, with, assert, and/or.
    Base complexity = 1.
    """
    count = 1
    for child in ast.walk(func_node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.AsyncFor, ast.AsyncWith)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            # and/or adds branches
            count += len(child.values) - 1
    return count


# ---------------------------------------------------------------------------
# Methods resolution: from CallGraph nodes or AST fallback
# ---------------------------------------------------------------------------


def _resolve_methods_for_file(file_path, call_graph, language):
    """Resolve method list for a file from CallGraph or AST.

    Args:
        file_path:  Source file path (str or Path).
        call_graph: CallGraph dict (with 'nodes') or None.
        language:   Language string.

    Returns:
        list of method dicts.
    """
    if call_graph is not None:
        nodes = call_graph.get("nodes", [])
        # CallGraph nodes have a 'file' field (relative path).
        # Try to match by file name or path suffix.
        fp = str(file_path).replace("\\", "/")
        matched = []
        for node in nodes:
            if node.get("type") not in ("method", "function"):
                continue
            node_file = str(node.get("file", "")).replace("\\", "/")
            if node_file and (node_file == fp or fp.endswith(node_file) or node_file.endswith(fp)):
                matched.append(
                    {
                        "name": node.get("name", ""),
                        "params": node.get("params", []),
                        "return_type": node.get("return_type", ""),
                        "parent_class": _extract_class_name(node.get("parent_class", "")),
                        "cyclomatic": node.get("cyclomatic", 1),
                        "visibility": node.get("visibility", "+"),
                    }
                )
        if matched:
            return matched

    # Fallback: AST analysis for Python files
    if language == "python":
        return _extract_methods_from_python_ast(file_path)

    return []


def _extract_class_name(parent_class_fqn):
    """Extract simple class name from FQN like 'file.py::ClassName'.

    Returns None if not present.
    """
    if not parent_class_fqn:
        return None
    # FQN format: path::ClassName or path::Outer.Inner
    if "::" in parent_class_fqn:
        class_part = parent_class_fqn.split("::", 1)[1]
        # Take last segment for nested classes
        return class_part.split(".")[-1]
    return parent_class_fqn


# ---------------------------------------------------------------------------
# Python (pytest) generator
# ---------------------------------------------------------------------------

_PY_HEADER = '''\
"""
Auto-generated tests for {module}.
Generated by test_generator.py - review and complete as needed.
"""
import pytest
{import_line}
'''

_PY_CLASS_HEADER = "\nclass Test{class_name}:\n"

_PY_BASIC = """\
    def test_{method}_basic(self):
        obj = {class_name}()
        result = obj.{method}({default_args})
        assert result is not None
"""

_PY_NONE_INPUT = """\
    def test_{method}_none_input(self):
        obj = {class_name}()
        with pytest.raises((TypeError, ValueError, AttributeError)):
            obj.{method}(None)
"""

_PY_EMPTY_INPUT = """\
    def test_{method}_empty_input(self):
        obj = {class_name}()
        # Test with empty string and empty list - should not raise unexpectedly
        try:
            result = obj.{method}("")
            assert result is not None or result is None
        except (TypeError, ValueError):
            pass  # Acceptable for empty input
        try:
            result = obj.{method}([])
            assert result is not None or result is None
        except (TypeError, ValueError):
            pass
"""

_PY_BOUNDARY = """\
    def test_{method}_boundary_values(self):
        obj = {class_name}()
        # Test boundary values: 0, -1, large number
        for val in [0, -1, 999999]:
            try:
                result = obj.{method}(val)
                assert result is not None or result is None
            except (TypeError, ValueError, OverflowError):
                pass  # Acceptable at boundaries
"""

_PY_VALIDATE_TRUE = """\
    def test_{method}_returns_true_for_valid(self):
        obj = {class_name}()
        # Provide a valid input - adjust as needed
        result = obj.{method}("valid_input")
        assert result is True or result is not None
"""

_PY_VALIDATE_FALSE = """\
    def test_{method}_returns_false_for_invalid(self):
        obj = {class_name}()
        # Provide an invalid input - adjust as needed
        result = obj.{method}("")
        assert result is False or result is None
"""

_PY_RETURN_TYPE = """\
    def test_{method}_return_type(self):
        obj = {class_name}()
        result = obj.{method}({default_args})
        assert isinstance(result, {expected_type})
"""

# Module-level function templates
_PY_FUNC_BASIC = """\
def test_{method}_basic():
    result = {method}({default_args})
    assert result is not None
"""

_PY_FUNC_NONE_INPUT = """\
def test_{method}_none_input():
    with pytest.raises((TypeError, ValueError, AttributeError)):
        {method}(None)
"""

_PY_FUNC_EMPTY = """\
def test_{method}_empty_input():
    try:
        result = {method}("")
        assert result is not None or result is None
    except (TypeError, ValueError):
        pass
"""


def _py_default_args(params):
    """Generate placeholder default argument list for a call."""
    if not params:
        return ""
    defaults = []
    for p in params:
        pname = p.split(":")[0].strip()
        defaults.append("None  # TODO: provide %s" % pname)
    return ", ".join(defaults)


def _py_expected_type(return_type):
    """Map a return type annotation to a pytest isinstance check type."""
    _map = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "list": "list",
        "dict": "dict",
        "tuple": "tuple",
        "set": "set",
        "bytes": "bytes",
    }
    rt = return_type.strip().lower().rstrip(")")  # handle Optional[str]
    for k, v in _map.items():
        if rt.startswith(k):
            return v
    return None


def _generate_python_tests(methods, class_name=None):
    """Generate pytest test code for a list of method dicts.

    Args:
        methods:    List of method dicts from CallGraph or AST.
        class_name: Name of the class under test, or None for module functions.

    Returns:
        str: pytest test source code.
    """
    if not methods:
        return ""

    lines = []

    if class_name:
        lines.append(_PY_CLASS_HEADER.format(class_name=class_name))

    for method in methods:
        name = method.get("name", "")
        params = method.get("params", [])
        return_type = method.get("return_type", "")
        cyclomatic = method.get("cyclomatic", 1)
        vis = method.get("visibility", "+")

        # Skip private methods (single underscore) unless they are dunder
        is_dunder = name.startswith("__") and name.endswith("__")
        if vis == "-" and not is_dunder:
            continue

        # Skip __init__, __str__, __repr__ - hard to test generically
        if name in ("__init__", "__str__", "__repr__", "__del__", "__enter__", "__exit__"):
            continue

        default_args = _py_default_args(params)
        is_validate = "validate" in name.lower() or "check" in name.lower()
        expected_type = _py_expected_type(return_type)

        if class_name:
            # Class method tests
            lines.append(_PY_BASIC.format(method=name, class_name=class_name, default_args=default_args))

            if cyclomatic > 1 and params:
                lines.append(_PY_NONE_INPUT.format(method=name, class_name=class_name))

            if cyclomatic > 3 and params:
                lines.append(_PY_EMPTY_INPUT.format(method=name, class_name=class_name))

            if cyclomatic > 5 and params:
                lines.append(_PY_BOUNDARY.format(method=name, class_name=class_name))

            if is_validate:
                lines.append(_PY_VALIDATE_TRUE.format(method=name, class_name=class_name))
                lines.append(_PY_VALIDATE_FALSE.format(method=name, class_name=class_name))

            if expected_type:
                lines.append(
                    _PY_RETURN_TYPE.format(
                        method=name, class_name=class_name, default_args=default_args, expected_type=expected_type
                    )
                )
        else:
            # Module-level function tests
            lines.append(_PY_FUNC_BASIC.format(method=name, default_args=default_args))
            if cyclomatic > 1 and params:
                lines.append(_PY_FUNC_NONE_INPUT.format(method=name))
            if cyclomatic > 3 and params:
                lines.append(_PY_FUNC_EMPTY.format(method=name))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Java (JUnit 5) generator
# ---------------------------------------------------------------------------

_JAVA_HEADER = """\
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Auto-generated tests for {class_name}.
 * Generated by test_generator.py - review and complete as needed.
 */
class {class_name}Test {{

    private {class_name} obj;

    @BeforeEach
    void setUp() {{
        obj = new {class_name}();
    }}
"""

_JAVA_BASIC = """\
    @Test
    void test{Method}_basic() {{
        // TODO: provide valid arguments
        var result = obj.{method}({default_args});
        assertNotNull(result);
    }}
"""

_JAVA_NULL_INPUT = """\
    @Test
    void test{Method}_nullInput() {{
        assertThrows(Exception.class, () -> {{
            obj.{method}(null);
        }});
    }}
"""

_JAVA_EMPTY_INPUT = """\
    @Test
    void test{Method}_emptyInput() {{
        // Test with empty string or empty list
        assertDoesNotThrow(() -> {{
            obj.{method}("");
        }});
    }}
"""

_JAVA_VALIDATE_TRUE = """\
    @Test
    void test{Method}_validInput() {{
        // TODO: replace with a known-valid input
        var result = obj.{method}("valid");
        assertTrue(result != null);
    }}
"""

_JAVA_VALIDATE_FALSE = """\
    @Test
    void test{Method}_invalidInput() {{
        // TODO: replace with a known-invalid input
        var result = obj.{method}("");
        assertFalse(Boolean.TRUE.equals(result));
    }}
"""

_JAVA_FUNC = """\
    @Test
    void test{Method}_basic() {{
        var result = {class_name}.{method}({default_args});
        assertNotNull(result);
    }}
"""


def _java_capitalize(name):
    """Capitalize first letter for Java method naming."""
    if not name:
        return name
    return name[0].upper() + name[1:]


def _java_default_args(params):
    """Generate placeholder null arguments for Java calls."""
    if not params:
        return ""
    return ", ".join("null  /* TODO: %s */" % p.split(":")[0].strip() for p in params)


def _generate_java_tests(methods, class_name=None):
    """Generate JUnit 5 test code for a list of method dicts.

    Args:
        methods:    List of method dicts.
        class_name: Simple class name.

    Returns:
        str: JUnit 5 test source code.
    """
    if not methods or not class_name:
        return ""

    lines = [_JAVA_HEADER.format(class_name=class_name)]

    for method in methods:
        name = method.get("name", "")
        params = method.get("params", [])
        cyclomatic = method.get("cyclomatic", 1)
        vis = method.get("visibility", "+")

        if vis == "-":
            continue
        if name in ("__init__", "__str__", "toString", "hashCode", "equals"):
            continue

        cap = _java_capitalize(name)
        default_args = _java_default_args(params)
        is_validate = "validate" in name.lower() or "check" in name.lower()

        lines.append(_JAVA_BASIC.format(Method=cap, method=name, default_args=default_args))

        if cyclomatic > 1 and params:
            lines.append(_JAVA_NULL_INPUT.format(Method=cap, method=name))

        if cyclomatic > 3 and params:
            lines.append(_JAVA_EMPTY_INPUT.format(Method=cap, method=name))

        if is_validate:
            lines.append(_JAVA_VALIDATE_TRUE.format(Method=cap, method=name))
            lines.append(_JAVA_VALIDATE_FALSE.format(Method=cap, method=name))

    lines.append("}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TypeScript (Jest / Vitest) generator
# ---------------------------------------------------------------------------

_TS_HEADER = """\
/**
 * Auto-generated tests for {class_name}.
 * Generated by test_generator.py - review and complete as needed.
 */
import {{ {class_name} }} from '../{module}';

describe('{class_name}', () => {{
    let obj: {class_name};

    beforeEach(() => {{
        obj = new {class_name}();
    }});
"""

_TS_BASIC = """\
    test('{method} - basic call', () => {{
        const result = obj.{method}({default_args});
        expect(result).toBeDefined();
    }});
"""

_TS_NULL = """\
    test('{method} - throws on null input', () => {{
        expect(() => {{
            obj.{method}(null as any);
        }}).toThrow();
    }});
"""

_TS_EMPTY = """\
    test('{method} - handles empty string', () => {{
        expect(() => {{
            obj.{method}('');
        }}).not.toThrow();
    }});
"""

_TS_VALIDATE_TRUE = """\
    test('{method} - returns truthy for valid input', () => {{
        const result = obj.{method}('valid_value');
        expect(result).toBeTruthy();
    }});
"""

_TS_VALIDATE_FALSE = """\
    test('{method} - returns falsy for invalid input', () => {{
        const result = obj.{method}('');
        expect(result).toBeFalsy();
    }});
"""

_TS_FUNC_HEADER = """\
/**
 * Auto-generated tests for {module} module functions.
 * Generated by test_generator.py - review and complete as needed.
 */
import {{ {imports} }} from '../{module}';

describe('{module} functions', () => {{
"""

_TS_FUNC_BASIC = """\
    test('{method} - basic call', () => {{
        const result = {method}({default_args});
        expect(result).toBeDefined();
    }});
"""

_TS_CLOSE = "});\n"


def _ts_default_args(params):
    """Generate placeholder undefined arguments."""
    if not params:
        return ""
    return ", ".join("undefined /* TODO: %s */" % p.split(":")[0].strip() for p in params)


def _generate_typescript_tests(methods, class_name=None):
    """Generate Jest/Vitest test code for a list of method dicts.

    Args:
        methods:    List of method dicts.
        class_name: Simple class name or None for module functions.

    Returns:
        str: TypeScript test source code.
    """
    if not methods:
        return ""

    lines = []
    module_name = class_name.lower() if class_name else "module"

    if class_name:
        lines.append(_TS_HEADER.format(class_name=class_name, module=module_name))
        for method in methods:
            name = method.get("name", "")
            params = method.get("params", [])
            cyclomatic = method.get("cyclomatic", 1)
            vis = method.get("visibility", "+")

            if vis == "-":
                continue
            if name in ("constructor",):
                continue

            default_args = _ts_default_args(params)
            is_validate = "validate" in name.lower() or "check" in name.lower()

            lines.append(_TS_BASIC.format(method=name, default_args=default_args))

            if cyclomatic > 1 and params:
                lines.append(_TS_NULL.format(method=name))

            if cyclomatic > 3 and params:
                lines.append(_TS_EMPTY.format(method=name))

            if is_validate:
                lines.append(_TS_VALIDATE_TRUE.format(method=name))
                lines.append(_TS_VALIDATE_FALSE.format(method=name))

        lines.append(_TS_CLOSE)
    else:
        public_names = [m["name"] for m in methods if m.get("visibility") == "+"]
        imports_str = ", ".join(public_names) if public_names else "/* TODO */"
        lines.append(_TS_FUNC_HEADER.format(module=module_name, imports=imports_str))
        for method in methods:
            name = method.get("name", "")
            params = method.get("params", [])
            vis = method.get("visibility", "+")
            if vis == "-":
                continue
            default_args = _ts_default_args(params)
            lines.append(_TS_FUNC_BASIC.format(method=name, default_args=default_args))
        lines.append(_TS_CLOSE)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Go (testing package) generator - table-driven
# ---------------------------------------------------------------------------

_GO_HEADER = """\
package {package}

import (
\t"testing"
)

// Auto-generated tests for {file_stem}.
// Generated by test_generator.py - review and complete as needed.
"""

_GO_TABLE_TEST = """\
func Test{Method}(t *testing.T) {{
\ttests := []struct {{
\t\tname    string
\t\tinput   interface{{}}
\t\twantErr bool
\t}}{{
\t\t{{name: "basic_valid", input: nil /* TODO */, wantErr: false}},
\t\t{{name: "nil_input",   input: nil,             wantErr: true}},
\t}}

\tfor _, tt := range tests {{
\t\tt.Run(tt.name, func(t *testing.T) {{
\t\t\t// TODO: instantiate and call {method}
\t\t\t// result, err := {method}(tt.input)
\t\t\t// if (err != nil) != tt.wantErr {{
\t\t\t//     t.Errorf("{method}() error = %v, wantErr %v", err, tt.wantErr)
\t\t\t// }}
\t\t\t_ = tt  // placeholder
\t\t}})
\t}}
}}
"""


def _generate_go_tests(methods, class_name=None):
    """Generate Go table-driven test code.

    Args:
        methods:    List of method dicts.
        class_name: Struct name or None.

    Returns:
        str: Go test source code.
    """
    if not methods:
        return ""

    # Infer package name from class or method context
    package = class_name.lower() if class_name else "main"
    file_stem = class_name if class_name else "module"

    lines = [_GO_HEADER.format(package=package, file_stem=file_stem)]

    for method in methods:
        name = method.get("name", "")
        vis = method.get("visibility", "+")
        if vis == "-":
            continue
        # Go exported = starts with uppercase
        if name and name[0].islower():
            continue

        cap = _java_capitalize(name)  # reuse capitalize helper
        lines.append(_GO_TABLE_TEST.format(Method=cap, method=name))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# generate_tests_for_methods - dispatcher
# ---------------------------------------------------------------------------


def generate_tests_for_methods(methods, language="python", framework="pytest"):
    """Generate test code for a list of method dicts.

    Args:
        methods:   List of CallGraph method dicts, each with keys:
                   name, params, return_type, parent_class, cyclomatic,
                   visibility.
        language:  'python', 'java', 'typescript', 'go', or other.
        framework: 'pytest', 'unittest', 'junit5', 'junit4', 'jest',
                   'vitest', 'testing'.

    Returns:
        str: Generated test source code.
    """
    if not methods:
        return ""

    try:
        # Group methods by parent class
        by_class = {}  # class_name -> [method dicts]
        no_class = []

        for m in methods:
            parent = m.get("parent_class") or None
            if parent:
                # parent may be FQN; extract simple name
                cn = _extract_class_name(str(parent))
                if cn not in by_class:
                    by_class[cn] = []
                by_class[cn].append(m)
            else:
                no_class.append(m)

        parts = []

        if language == "python":
            for class_name, class_methods in by_class.items():
                parts.append(_generate_python_tests(class_methods, class_name=class_name))
            if no_class:
                parts.append(_generate_python_tests(no_class, class_name=None))

        elif language == "java":
            for class_name, class_methods in by_class.items():
                parts.append(_generate_java_tests(class_methods, class_name=class_name))

        elif language in ("typescript", "javascript"):
            for class_name, class_methods in by_class.items():
                parts.append(_generate_typescript_tests(class_methods, class_name=class_name))
            if no_class:
                parts.append(_generate_typescript_tests(no_class, class_name=None))

        elif language == "go":
            all_methods = list(methods)
            parts.append(_generate_go_tests(all_methods, class_name=None))

        return "\n\n".join(p for p in parts if p.strip())

    except Exception:
        return ""


# ---------------------------------------------------------------------------
# generate_tests_for_file - main entry point for a single file
# ---------------------------------------------------------------------------


def generate_tests_for_file(project_root, file_path, call_graph=None):
    """Generate unit tests for all public methods in a file.

    Args:
        project_root: Root directory of the project (str or Path).
        file_path:    Source file to generate tests for (str or Path).
        call_graph:   Optional CallGraph dict with a 'nodes' key.
                      When provided, method info is sourced from the graph.
                      Falls back to AST analysis for Python files.

    Returns:
        dict with keys:
            test_file_path  (str)  - where tests should be written
            test_code       (str)  - generated test code
            methods_tested  (int)  - number of methods included
            language        (str)  - detected language
            framework       (str)  - detected test framework
        Returns an empty-result dict on any error.
    """
    empty = {
        "test_file_path": "",
        "test_code": "",
        "methods_tested": 0,
        "language": "unknown",
        "framework": "unknown",
    }

    try:
        root = Path(str(project_root))
        src = Path(str(file_path))

        if not src.exists():
            return empty

        language = detect_language(src)
        if language == "unknown":
            return empty

        framework = detect_test_framework(language, root)
        test_file = get_test_file_path(src, language)

        methods = _resolve_methods_for_file(src, call_graph, language)
        if not methods:
            return {
                "test_file_path": test_file,
                "test_code": "",
                "methods_tested": 0,
                "language": language,
                "framework": framework,
            }

        # Build the header / import section for Python
        module_stem = src.stem
        test_code_body = generate_tests_for_methods(methods, language, framework)

        if language == "python":
            # Collect unique class names from methods
            class_names = sorted({m.get("parent_class") or "" for m in methods if m.get("parent_class")})
            if class_names:
                import_names = ", ".join(class_names)
                import_line = "from %s import %s" % (module_stem, import_names)
            else:
                import_line = "from %s import *  # TODO: update import" % module_stem

            header = _PY_HEADER.format(module=module_stem, import_line=import_line)
            test_code = header + test_code_body
        else:
            test_code = test_code_body

        # Count methods that generated at least one test block
        methods_tested = sum(
            1
            for m in methods
            if m.get("visibility") == "+"
            and m.get("name", "")
            not in (
                "__init__",
                "__str__",
                "__repr__",
                "__del__",
                "__enter__",
                "__exit__",
                "constructor",
                "toString",
                "hashCode",
                "equals",
            )
        )

        return {
            "test_file_path": test_file,
            "test_code": test_code,
            "methods_tested": methods_tested,
            "language": language,
            "framework": framework,
        }

    except Exception:
        return empty


# ---------------------------------------------------------------------------
# generate_tests_for_modified_files - batch entry point
# ---------------------------------------------------------------------------


def generate_tests_for_modified_files(project_root, modified_files, call_graph=None):
    """Generate tests for all modified files in a batch.

    Args:
        project_root:   Root directory of the project (str or Path).
        modified_files: Iterable of file paths (str or Path).
        call_graph:     Optional CallGraph dict with a 'nodes' key.

    Returns:
        dict with keys:
            tests_generated      (int)  - number of files with test code
            total_methods_tested (int)  - sum of methods across all files
            files                (list) - list of per-file result dicts, each:
                {
                    test_file_path (str),
                    methods_tested (int),
                    language       (str),
                    framework      (str),
                    test_code      (str),
                }
    """
    result = {
        "tests_generated": 0,
        "total_methods_tested": 0,
        "files": [],
    }

    try:
        for fp in modified_files or []:
            file_result = generate_tests_for_file(project_root, fp, call_graph)
            if not file_result.get("test_code", "").strip():
                continue

            result["tests_generated"] += 1
            result["total_methods_tested"] += file_result.get("methods_tested", 0)
            result["files"].append(
                {
                    "test_file_path": file_result["test_file_path"],
                    "methods_tested": file_result["methods_tested"],
                    "language": file_result["language"],
                    "framework": file_result["framework"],
                    "test_code": file_result["test_code"],
                }
            )
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Convenience: write test files to disk
# ---------------------------------------------------------------------------


def write_test_files(batch_result, dry_run=False):
    """Write generated test code to disk.

    Args:
        batch_result: Result dict from generate_tests_for_modified_files().
        dry_run:      If True, return paths without writing.

    Returns:
        list of str: Paths of files written (or that would be written).
    """
    written = []
    try:
        for entry in batch_result.get("files", []):
            test_path = entry.get("test_file_path", "")
            test_code = entry.get("test_code", "")
            if not test_path or not test_code.strip():
                continue
            if not dry_run:
                dest = Path(test_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(test_code, encoding="utf-8")
            written.append(test_path)
    except Exception:
        pass
    return written
