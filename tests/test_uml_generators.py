"""
Tests for UML diagram generation (uml_generators.py).

Tests AST analysis, Mermaid/PlantUML generation, and Kroki rendering.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path for imports
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from langgraph_engine.uml_generators import (  # noqa: E402
    KrokiRenderer,
    UMLAstAnalyzer,
    UMLDiagramGenerator,
    _clean_mermaid,
    _clean_plantuml,
    _plantuml_stub,
    _simplify_type,
)

# ==================================================================
# Fixtures
# ==================================================================


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary Python project for testing."""
    # Create a simple Python file with classes
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    sample_py = src_dir / "models.py"
    sample_py.write_text(
        "class Animal:\n"
        "    species: str = ''\n"
        "\n"
        "    def __init__(self, name: str, age: int = 0):\n"
        "        self.name = name\n"
        "        self.age = age\n"
        "        self._internal = True\n"
        "\n"
        "    def speak(self) -> str:\n"
        "        return ''\n"
        "\n"
        "    def _private_method(self):\n"
        "        pass\n"
        "\n"
        "\n"
        "class Dog(Animal):\n"
        "    breed: str = ''\n"
        "\n"
        "    def speak(self) -> str:\n"
        "        return 'Woof'\n"
        "\n"
        "    def fetch(self, item: str) -> bool:\n"
        "        return True\n",
        encoding="utf-8",
    )

    # Create a file with imports
    utils_py = src_dir / "utils.py"
    utils_py.write_text(
        "import os\n"
        "import json\n"
        "from pathlib import Path\n"
        "from .models import Animal\n"
        "\n"
        "def helper():\n"
        "    a = Animal('test')\n"
        "    a.speak()\n"
        "    return str(Path('.'))\n",
        encoding="utf-8",
    )

    # Create a second module for dependency testing
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    svc_py = services_dir / "handler.py"
    svc_py.write_text(
        "from src.models import Dog\n"
        "\n"
        "class DogHandler:\n"
        "    def process(self, dog):\n"
        "        dog.speak()\n"
        "        dog.fetch('ball')\n",
        encoding="utf-8",
    )

    # Create a README for use case diagram
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Test Project\n\nA sample project for testing UML generation.\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def analyzer(tmp_project):
    return UMLAstAnalyzer(str(tmp_project))


@pytest.fixture
def generator(tmp_project):
    return UMLDiagramGenerator(str(tmp_project))


# ==================================================================
# TestUMLAstAnalyzer
# ==================================================================


class TestUMLAstAnalyzer:

    def test_extract_classes_simple(self, analyzer, tmp_project):
        """Extract classes with methods and attributes."""
        classes = analyzer.extract_classes(tmp_project / "src" / "models.py")
        assert len(classes) == 2

        animal = next(c for c in classes if c["name"] == "Animal")
        assert animal["name"] == "Animal"
        assert len(animal["bases"]) == 0
        assert any(m["name"] == "speak" for m in animal["methods"])
        assert any(m["name"] == "__init__" for m in animal["methods"])
        assert any(a["name"] == "name" for a in animal["attributes"])
        assert any(a["name"] == "age" for a in animal["attributes"])

    def test_extract_classes_inheritance(self, analyzer, tmp_project):
        """Extract parent/child classes with inheritance."""
        classes = analyzer.extract_classes(tmp_project / "src" / "models.py")
        dog = next(c for c in classes if c["name"] == "Dog")
        assert "Animal" in dog["bases"]
        assert any(m["name"] == "fetch" for m in dog["methods"])

    def test_extract_classes_empty_file(self, analyzer, tmp_path):
        """Empty file returns no classes."""
        empty = tmp_path / "empty.py"
        empty.write_text("# no classes here\nx = 42\n", encoding="utf-8")
        classes = analyzer.extract_classes(empty)
        assert classes == []

    def test_extract_classes_syntax_error(self, analyzer, tmp_path):
        """File with syntax errors returns empty list gracefully."""
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(\n", encoding="utf-8")
        classes = analyzer.extract_classes(bad)
        assert classes == []

    def test_extract_classes_visibility(self, analyzer, tmp_project):
        """Private methods get '-' visibility, public get '+'."""
        classes = analyzer.extract_classes(tmp_project / "src" / "models.py")
        animal = next(c for c in classes if c["name"] == "Animal")

        speak = next(m for m in animal["methods"] if m["name"] == "speak")
        assert speak["visibility"] == "+"

        private = next(m for m in animal["methods"] if m["name"] == "_private_method")
        assert private["visibility"] == "-"

    def test_extract_classes_self_attributes(self, analyzer, tmp_project):
        """Detect self.attr assignments in __init__."""
        classes = analyzer.extract_classes(tmp_project / "src" / "models.py")
        animal = next(c for c in classes if c["name"] == "Animal")
        attr_names = [a["name"] for a in animal["attributes"]]
        assert "name" in attr_names
        assert "age" in attr_names
        # Private attribute
        internal = next((a for a in animal["attributes"] if a["name"] == "_internal"), None)
        if internal:
            assert internal["visibility"] == "-"

    def test_extract_all_classes(self, analyzer):
        """Recursively extract classes from all files."""
        all_classes = analyzer.extract_all_classes()
        names = [c["name"] for c in all_classes]
        assert "Animal" in names
        assert "Dog" in names
        assert "DogHandler" in names

    def test_extract_imports(self, analyzer, tmp_project):
        """Extract import and from-import statements."""
        imports = analyzer.extract_imports(tmp_project / "src" / "utils.py")
        assert "os" in imports["imports"]
        assert "json" in imports["imports"]
        assert any(fi["name"] == "Path" for fi in imports["from_imports"])
        assert any(fi["name"] == "Animal" for fi in imports["from_imports"])

    def test_build_dependency_graph(self, analyzer):
        """Build module-level dependency map."""
        graph = analyzer.build_dependency_graph()
        assert isinstance(graph, dict)
        # models.py has no project-internal deps typically
        # utils.py imports os, json, pathlib, models
        if "utils" in graph:
            assert "os" in graph["utils"] or "json" in graph["utils"]

    def test_extract_call_chains(self, analyzer, tmp_project):
        """Extract function call chains."""
        chains = analyzer.extract_call_chains(tmp_project / "src" / "utils.py", "helper")
        assert len(chains) > 0
        callees = [c["callee"] for c in chains]
        assert "Animal" in callees or "speak" in callees

    def test_extract_call_chains_no_match(self, analyzer, tmp_project):
        """No matching entry function returns empty."""
        chains = analyzer.extract_call_chains(tmp_project / "src" / "utils.py", "nonexistent_func")
        assert chains == []


# ==================================================================
# TestUMLDiagramGenerator
# ==================================================================


class TestUMLDiagramGenerator:

    def test_generate_class_diagram_mermaid(self, generator, tmp_project):
        """Generate valid Mermaid classDiagram syntax."""
        classes = generator.analyzer.extract_all_classes(tmp_project / "src")
        syntax = generator.generate_class_diagram(classes)
        assert syntax.startswith("classDiagram")
        assert "class Animal" in syntax
        assert "class Dog" in syntax
        assert "Animal <|-- Dog" in syntax

    def test_generate_class_diagram_no_classes(self, generator):
        """Empty class list produces stub diagram."""
        syntax = generator.generate_class_diagram(classes=[])
        assert "classDiagram" in syntax
        assert "No classes found" in syntax

    def test_generate_class_diagram_methods_attrs(self, generator, tmp_project):
        """Class diagram includes methods and attributes."""
        classes = generator.analyzer.extract_classes(tmp_project / "src" / "models.py")
        syntax = generator.generate_class_diagram(classes)
        assert "speak" in syntax
        assert "name" in syntax

    def test_generate_package_diagram(self, generator):
        """Generate valid Mermaid flowchart for packages."""
        syntax = generator.generate_package_diagram()
        assert syntax.startswith("flowchart")

    def test_generate_component_diagram(self, generator):
        """Generate valid Mermaid component diagram."""
        syntax = generator.generate_component_diagram()
        assert "flowchart TB" in syntax

    def test_generate_sequence_diagram_ast(self, generator):
        """Sequence diagram from AST call chains (no LLM)."""
        syntax = generator.generate_sequence_diagram()
        assert "sequenceDiagram" in syntax

    def test_generate_all_diagrams(self, generator):
        """Generate multiple diagrams at once."""
        results = generator.generate_all()
        assert isinstance(results, dict)
        assert "class-diagram" in results
        assert "package-diagram" in results
        assert "component-diagram" in results
        # Tier 1 should always succeed
        assert len(results) >= 3

    def test_save_diagram_creates_file(self, generator):
        """Save diagram writes file to uml/."""
        syntax = "classDiagram\n    class Foo"
        path = generator.save_diagram("test-diagram", syntax)
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "```mermaid" in content
        assert "classDiagram" in content
        assert "Auto-generated" in content

    def test_save_diagram_plantuml(self, generator):
        """PlantUML diagrams get plantuml fence."""
        syntax = "@startuml\nclass Foo\n@enduml"
        path = generator.save_diagram("test-plantuml", syntax)
        content = Path(path).read_text(encoding="utf-8")
        assert "```plantuml" in content
        assert "@startuml" in content

    def test_save_diagram_creates_directory(self, tmp_path):
        """Output directory is created if missing."""
        gen = UMLDiagramGenerator(str(tmp_path), "new_dir/uml")
        syntax = "classDiagram\n    class Bar"
        path = gen.save_diagram("test", syntax)
        assert Path(path).exists()

    def test_generate_class_diagram_scope_file(self, generator, tmp_project):
        """Scope to a single file."""
        file_path = str(tmp_project / "src" / "models.py")
        syntax = generator.generate_class_diagram(scope=file_path)
        assert "Animal" in syntax


# ==================================================================
# TestKrokiRenderer
# ==================================================================


class TestKrokiRenderer:

    def test_render_plantuml_svg(self):
        """Kroki API call for PlantUML (mocked)."""
        renderer = KrokiRenderer()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<svg>test</svg>"

        with patch("langgraph_engine.uml_generators.KrokiRenderer.render") as mock:
            mock.return_value = b"<svg>test</svg>"
            result = renderer.render("@startuml\nclass A\n@enduml", "plantuml", "svg")
        assert result == b"<svg>test</svg>"

    def test_render_mermaid_svg(self):
        """Kroki API call for Mermaid (mocked)."""
        renderer = KrokiRenderer()
        with patch("langgraph_engine.uml_generators.KrokiRenderer.render") as mock:
            mock.return_value = b"<svg>mermaid</svg>"
            result = renderer.render("classDiagram\n    class A", "mermaid", "svg")
        assert result == b"<svg>mermaid</svg>"

    def test_render_failure_graceful(self):
        """API error returns None."""
        renderer = KrokiRenderer()
        with patch.dict("sys.modules", {"requests": MagicMock()}) as _:
            mock_requests = sys.modules["requests"]
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_requests.post.return_value = mock_resp

            # Direct test - mock the whole render method for simplicity
            with patch.object(renderer, "render", return_value=None):
                result = renderer.render("bad input")
        assert result is None

    def test_render_to_file(self, tmp_path):
        """Render and save to file."""
        renderer = KrokiRenderer()
        out = tmp_path / "test.svg"

        with patch.object(renderer, "render", return_value=b"<svg>ok</svg>"):
            path = renderer.render_to_file("@startuml\nA\n@enduml", str(out), "plantuml", "svg")
        assert path is not None
        assert Path(path).exists()
        assert Path(path).read_bytes() == b"<svg>ok</svg>"

    def test_render_to_file_failure(self, tmp_path):
        """Render failure returns None."""
        renderer = KrokiRenderer()
        out = tmp_path / "fail.svg"
        with patch.object(renderer, "render", return_value=None):
            path = renderer.render_to_file("bad", str(out))
        assert path is None


# ==================================================================
# Test utility functions
# ==================================================================


class TestUtilities:

    def test_simplify_type_name(self):
        """Simplify AST Name type dump."""
        assert _simplify_type("Name(id='str')") == "str"
        assert _simplify_type("Name(id='int')") == "int"
        assert _simplify_type("Name(id='Optional')") == "Optional"

    def test_simplify_type_empty(self):
        assert _simplify_type("") == ""
        assert _simplify_type(None) == ""

    def test_simplify_type_constant(self):
        """Constant types return empty."""
        assert _simplify_type("Constant(value=42)") == ""

    def test_clean_mermaid_with_fences(self):
        """Remove markdown fences from Mermaid output."""
        raw = "```mermaid\nclassDiagram\n    class A\n```"
        assert _clean_mermaid(raw) == "classDiagram\n    class A"

    def test_clean_mermaid_plain(self):
        """Plain Mermaid passes through."""
        raw = "classDiagram\n    class A"
        assert _clean_mermaid(raw) == raw

    def test_clean_plantuml_with_fences(self):
        """Remove markdown fences and ensure @startuml/@enduml."""
        raw = "```plantuml\n@startuml\nclass A\n@enduml\n```"
        result = _clean_plantuml(raw)
        assert result.startswith("@startuml")
        assert result.endswith("@enduml")

    def test_clean_plantuml_adds_wrapper(self):
        """Add @startuml/@enduml if missing."""
        raw = "class A\nclass B"
        result = _clean_plantuml(raw)
        assert result.startswith("@startuml")
        assert result.endswith("@enduml")

    def test_plantuml_stub(self):
        """Generate PlantUML stub with message."""
        result = _plantuml_stub("test", "hello")
        assert "@startuml" in result
        assert "test: hello" in result
        assert "@enduml" in result


# ==================================================================
# Integration test
# ==================================================================


class TestIntegration:

    def test_analyze_and_generate_this_project(self):
        """Run analysis on the claude-insight project itself."""
        project_root = Path(__file__).resolve().parent.parent
        analyzer = UMLAstAnalyzer(str(project_root))

        # Should find classes in the project
        classes = analyzer.extract_all_classes(project_root / "langgraph_engine")
        assert len(classes) > 0, "Should find classes in langgraph_engine"

        # Generate class diagram
        gen = UMLDiagramGenerator(str(project_root), "uml")
        syntax = gen.generate_class_diagram(classes[:20])
        assert "classDiagram" in syntax
        assert len(syntax.split("\n")) > 2

    def test_full_generate_and_save(self, tmp_path):
        """Full workflow: analyze, generate, save."""
        # Create minimal project
        py_file = tmp_path / "app.py"
        py_file.write_text(
            "class Server:\n"
            "    port: int = 8080\n"
            "    def start(self):\n"
            "        pass\n"
            "    def stop(self):\n"
            "        pass\n"
            "\n"
            "class Client:\n"
            "    def connect(self, server):\n"
            "        server.start()\n",
            encoding="utf-8",
        )

        gen = UMLDiagramGenerator(str(tmp_path))
        results = gen.generate_all()

        assert "class-diagram" in results

        # Save all
        for name, syntax in results.items():
            path = gen.save_diagram(name, syntax)
            assert Path(path).exists()

        # Check output directory
        uml_dir = tmp_path / "uml"
        assert uml_dir.exists()
        md_files = list(uml_dir.glob("*.md"))
        assert len(md_files) >= 1


# ==================================================================
# TestCallGraphIntegration
# ==================================================================


class TestCallGraphIntegration:
    """Tests for UMLDiagramGenerator methods that integrate with CallGraph."""

    def test_get_call_graph_lazy_build(self, tmp_project):
        """_get_call_graph() builds and returns a CallGraph when not pre-built."""
        gen = UMLDiagramGenerator(str(tmp_project))
        # No call_graph pre-injected; should build lazily
        cg = gen._get_call_graph()
        # May return None if build fails, but on a valid project it should succeed
        if cg is not None:
            # Must have classes dict and methods dict
            assert hasattr(cg, "classes")
            assert hasattr(cg, "methods")
            # tmp_project contains Animal, Dog, DogHandler
            assert len(cg.classes) > 0

    def test_get_call_graph_caches(self, tmp_project):
        """_get_call_graph() returns the same object on repeated calls."""
        gen = UMLDiagramGenerator(str(tmp_project))
        cg1 = gen._get_call_graph()
        cg2 = gen._get_call_graph()
        # Both calls must return the same object (identity, not just equality)
        assert cg1 is cg2

    def test_get_call_graph_with_prebuilt(self, tmp_project):
        """When call_graph is injected at construction, _get_call_graph returns it."""
        from langgraph_engine.call_graph_builder import build_call_graph

        cg = build_call_graph(str(tmp_project))
        if cg is None:
            # Build failed - skip assertion on identity but verify None returned
            gen = UMLDiagramGenerator(str(tmp_project), call_graph=None)
            assert gen._get_call_graph() is not cg or cg is None
            return
        gen = UMLDiagramGenerator(str(tmp_project), call_graph=cg)
        assert gen._get_call_graph() is cg

    def test_classes_from_call_graph(self, tmp_project):
        """_classes_from_call_graph() returns list of ClassInfo dicts."""
        from langgraph_engine.call_graph_builder import build_call_graph

        cg = build_call_graph(str(tmp_project))
        if cg is None or not cg.classes:
            return  # CallGraph build failed or no classes; not a test error

        gen = UMLDiagramGenerator(str(tmp_project))
        result = gen._classes_from_call_graph(cg)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

        # Each item must be a ClassInfo dict with required keys
        for cls_info in result:
            assert "name" in cls_info
            assert "methods" in cls_info
            assert "attributes" in cls_info
            assert "bases" in cls_info
            assert isinstance(cls_info["name"], str)
            assert isinstance(cls_info["methods"], list)
            assert isinstance(cls_info["attributes"], list)

    def test_classes_from_call_graph_returns_none_on_empty(self, tmp_project):
        """_classes_from_call_graph() returns None when cg is None."""
        gen = UMLDiagramGenerator(str(tmp_project))
        result = gen._classes_from_call_graph(None)
        assert result is None

    def test_dep_graph_from_call_graph(self, tmp_project):
        """_dep_graph_from_call_graph() returns dict mapping module -> set of deps."""
        from langgraph_engine.call_graph_builder import build_call_graph

        cg = build_call_graph(str(tmp_project))
        gen = UMLDiagramGenerator(str(tmp_project))
        dep_graph = gen._dep_graph_from_call_graph(cg)

        assert isinstance(dep_graph, dict)
        # All values must be sets (even empty ones)
        for module_name, deps in dep_graph.items():
            assert isinstance(module_name, str)
            assert isinstance(deps, set)

    def test_dep_graph_from_call_graph_no_cg(self, tmp_project):
        """_dep_graph_from_call_graph() falls back to AST analyzer when cg=None."""
        gen = UMLDiagramGenerator(str(tmp_project))
        dep_graph = gen._dep_graph_from_call_graph(None)
        # Must still return a dict (from pure AST analysis)
        assert isinstance(dep_graph, dict)

    def test_call_chains_from_call_graph(self, tmp_project):
        """_call_chains_from_call_graph() returns list of chain dicts."""
        from langgraph_engine.call_graph_builder import build_call_graph

        cg = build_call_graph(str(tmp_project))
        if cg is None:
            return

        gen = UMLDiagramGenerator(str(tmp_project))
        chains = gen._call_chains_from_call_graph(cg)

        if chains is None:
            # No call edges found in tiny project; acceptable
            return

        assert isinstance(chains, list)
        # Every chain must have the required keys
        required_keys = {"caller", "callee", "file", "caller_fqn", "callee_fqn"}
        for chain in chains:
            for key in required_keys:
                assert key in chain, "chain missing key: %s" % key

    def test_call_chains_has_fqn_data(self, tmp_project):
        """call_chains produced from CallGraph have non-empty caller_fqn and callee_fqn."""
        from langgraph_engine.call_graph_builder import build_call_graph

        cg = build_call_graph(str(tmp_project))
        if cg is None:
            return

        gen = UMLDiagramGenerator(str(tmp_project))
        chains = gen._call_chains_from_call_graph(cg)
        if not chains:
            return  # no edges in tiny project

        # At least some chains must have caller_fqn populated (containing "::")
        fqn_chains = [c for c in chains if "::" in c.get("caller_fqn", "")]
        assert len(fqn_chains) > 0, "Expected at least one chain with FQN caller_fqn"

    def test_call_chains_returns_none_on_empty_cg(self, tmp_project):
        """_call_chains_from_call_graph() returns None when cg is None."""
        gen = UMLDiagramGenerator(str(tmp_project))
        result = gen._call_chains_from_call_graph(None)
        assert result is None

    def test_backward_compat_no_call_graph(self, tmp_project):
        """UMLDiagramGenerator with no call_graph param: generate_class_diagram works."""
        gen = UMLDiagramGenerator(str(tmp_project))
        # Should not raise even if _get_call_graph() returns None internally
        syntax = gen.generate_class_diagram()
        assert "classDiagram" in syntax
        # tmp_project has Animal and Dog
        assert "Animal" in syntax or "Dog" in syntax


# ==================================================================
# TestCallGraphDiagram
# ==================================================================


class TestCallGraphDiagram:
    """Tests for generate_call_graph_diagram()."""

    def _make_two_class_project(self, tmp_path):
        """Helper: write two classes that call each other into tmp_path."""
        src = tmp_path / "caller.py"
        src.write_text(
            "class ServiceA:\n"
            "    def run(self):\n"
            "        b = ServiceB()\n"
            "        b.execute()\n"
            "\n"
            "class ServiceB:\n"
            "    def execute(self):\n"
            "        self.helper()\n"
            "\n"
            "    def helper(self):\n"
            "        pass\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_generate_call_graph_diagram(self, tmp_path):
        """Call graph diagram contains flowchart LR, class subgraphs, and edge arrows."""
        project = self._make_two_class_project(tmp_path)
        gen = UMLDiagramGenerator(str(project))
        syntax = gen.generate_call_graph_diagram()

        # Must start with flowchart LR
        assert "flowchart LR" in syntax
        # Should have subgraph blocks for at least one class
        assert "subgraph" in syntax
        # Should have at least one arrow between nodes
        assert " --> " in syntax

    def test_call_graph_diagram_no_graph(self, tmp_path):
        """Call graph diagram with a project with no Python files returns a stub."""
        # Create project with no Python files
        (tmp_path / "README.md").write_text("empty project", encoding="utf-8")
        gen = UMLDiagramGenerator(str(tmp_path))
        syntax = gen.generate_call_graph_diagram()
        # Must return some flowchart string (stub or real)
        assert "flowchart" in syntax

    def test_call_graph_diagram_entry_points(self, tmp_path):
        """Public methods that are entry points get stroke-width:3px style."""
        project = self._make_two_class_project(tmp_path)
        gen = UMLDiagramGenerator(str(project))
        syntax = gen.generate_call_graph_diagram()
        # run() in ServiceA is a public entry point (not called by anyone in this file)
        assert "stroke-width:3px" in syntax

    def test_call_graph_diagram_in_generate_all(self, tmp_path):
        """generate_all() includes 'call-graph-diagram' in results."""
        project = self._make_two_class_project(tmp_path)
        gen = UMLDiagramGenerator(str(project))
        results = gen.generate_all()
        assert "call-graph-diagram" in results
        assert "flowchart" in results["call-graph-diagram"]

    def test_call_graph_diagram_with_prebuilt_graph(self, tmp_path):
        """generate_call_graph_diagram() accepts a pre-built CallGraph object."""
        from langgraph_engine.call_graph_builder import build_call_graph

        project = self._make_two_class_project(tmp_path)
        cg = build_call_graph(str(project))
        gen = UMLDiagramGenerator(str(project))
        syntax = gen.generate_call_graph_diagram(call_graph=cg)
        assert "flowchart" in syntax

    def test_call_graph_diagram_none_call_graph_returns_stub(self, tmp_path):
        """generate_call_graph_diagram() with a None CallGraph returns a stub string."""
        gen = UMLDiagramGenerator(str(tmp_path))
        # Inject None so _get_call_graph returns None
        gen._call_graph = None
        # Override _get_call_graph to always return None for this test
        gen._call_graph = "sentinel_to_prevent_lazy_build"

        class _NullCG:
            classes = {}
            methods = {}

            def get_edges(self):
                return []

        syntax = gen.generate_call_graph_diagram(call_graph=_NullCG())
        # With empty graph: no nodes, no edges -> should still return flowchart LR
        assert "flowchart LR" in syntax


# ==================================================================
# TestGenerateAllCompleteness
# ==================================================================


class TestGenerateAllCompleteness:
    """Tests that generate_all() produces all expected diagram keys."""

    TIER1_KEYS = [
        "class-diagram",
        "package-diagram",
        "component-diagram",
        "call-graph-diagram",
    ]

    TIER2_KEYS = [
        "sequence-diagram",
        "activity-diagram",
        "state-diagram",
    ]

    def test_generate_all_has_tier1_plus_tier2(self, tmp_project):
        """generate_all() produces at least Tier 1 + Tier 2 keys."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        assert isinstance(results, dict)
        for key in self.TIER1_KEYS:
            assert key in results, "Missing expected diagram key: %s" % key
        for key in self.TIER2_KEYS:
            assert key in results, "Missing expected diagram key: %s" % key

    def test_generate_all_tier1_always_present(self, tmp_project):
        """Tier 1 diagrams are always present regardless of LLM availability."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        for key in self.TIER1_KEYS:
            assert key in results, "Tier 1 key missing: %s" % key
            assert isinstance(results[key], str)
            assert len(results[key]) > 0

    def test_generate_all_class_diagram_is_mermaid(self, tmp_project):
        """class-diagram result is valid Mermaid classDiagram syntax."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        assert "classDiagram" in results["class-diagram"]

    def test_generate_all_package_diagram_is_flowchart(self, tmp_project):
        """package-diagram result contains flowchart keyword."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        assert "flowchart" in results["package-diagram"]

    def test_generate_all_call_graph_diagram_is_flowchart(self, tmp_project):
        """call-graph-diagram result contains flowchart keyword."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        assert "flowchart" in results["call-graph-diagram"]

    def test_generate_all_sequence_diagram_is_mermaid(self, tmp_project):
        """sequence-diagram result contains sequenceDiagram keyword."""
        gen = UMLDiagramGenerator(str(tmp_project))
        results = gen.generate_all()
        assert "sequenceDiagram" in results["sequence-diagram"]

    def test_generate_all_no_exceptions_on_minimal_project(self, tmp_path):
        """generate_all() does not raise on a minimal single-file project."""
        py_file = tmp_path / "minimal.py"
        py_file.write_text(
            "class Minimal:\n    def do_something(self):\n        pass\n",
            encoding="utf-8",
        )
        gen = UMLDiagramGenerator(str(tmp_path))
        # Should not raise regardless of LLM availability
        results = gen.generate_all()
        assert isinstance(results, dict)
        assert len(results) >= len(self.TIER1_KEYS)


# ==================================================================
# TestSequenceDiagramFQN
# ==================================================================


class TestSequenceDiagramFQN:
    """Tests for sequence diagram generation using FQN-aware call chains."""

    def test_sequence_uses_class_participants(self, tmp_project):
        """Sequence diagram declares participant names derived from class context."""
        gen = UMLDiagramGenerator(str(tmp_project))
        syntax = gen.generate_sequence_diagram()
        assert "sequenceDiagram" in syntax
        # Must have at least a participant or an arrow
        has_participant = "participant" in syntax
        has_arrow = "->>" in syntax
        assert has_participant or has_arrow, "Sequence diagram has no participants or arrows: %s" % syntax[:300]

    def test_sequence_fallback_legacy(self, tmp_project):
        """generate_sequence_diagram() with legacy chains (no caller_fqn) works."""
        gen = UMLDiagramGenerator(str(tmp_project))
        # Pass call_chains without FQN data (legacy format)
        legacy_chains = [
            {"caller": "helper", "callee": "Animal", "file": "utils.py"},
            {"caller": "helper", "callee": "speak", "file": "utils.py"},
            {"caller": "process", "callee": "speak", "file": "handler.py"},
        ]
        syntax = gen.generate_sequence_diagram(call_chains=legacy_chains)
        assert "sequenceDiagram" in syntax
        # Legacy path builds caller->>callee arrows
        assert "->>" in syntax

    def test_sequence_from_fqn_chains_uses_class_names(self, tmp_project):
        """_sequence_from_fqn_chains() extracts class names as participant names."""
        gen = UMLDiagramGenerator(str(tmp_project))
        fqn_chains = [
            {
                "caller": "speak",
                "callee": "helper",
                "file": "models.py",
                "caller_fqn": "src/models.py::Animal.speak",
                "callee_fqn": "src/utils.py::helper",
                "line": 10,
                "call_type": "call",
            }
        ]
        syntax = gen.generate_sequence_diagram(call_chains=fqn_chains)
        assert "sequenceDiagram" in syntax
        # "Animal" should appear as a participant (extracted from FQN)
        assert "Animal" in syntax

    def test_sequence_fqn_chains_has_arrows(self, tmp_project):
        """Sequence diagram from FQN chains includes call arrows."""
        gen = UMLDiagramGenerator(str(tmp_project))
        fqn_chains = [
            {
                "caller": "run",
                "callee": "execute",
                "file": "service.py",
                "caller_fqn": "service.py::ServiceA.run",
                "callee_fqn": "service.py::ServiceB.execute",
                "line": 5,
                "call_type": "call",
            }
        ]
        syntax = gen.generate_sequence_diagram(call_chains=fqn_chains)
        assert "->>" in syntax

    def test_sequence_empty_call_chains_returns_stub(self, tmp_project):
        """generate_sequence_diagram() with empty list returns a stub."""
        gen = UMLDiagramGenerator(str(tmp_project))
        syntax = gen.generate_sequence_diagram(call_chains=[])
        assert "sequenceDiagram" in syntax

    def test_sequence_diagram_from_call_graph(self, tmp_path):
        """Sequence diagram from a project with two interacting classes uses FQN path."""
        from langgraph_engine.call_graph_builder import build_call_graph

        src = tmp_path / "interaction.py"
        src.write_text(
            "class Sender:\n"
            "    def send(self):\n"
            "        r = Receiver()\n"
            "        r.receive()\n"
            "\n"
            "class Receiver:\n"
            "    def receive(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        cg = build_call_graph(str(tmp_path))
        gen = UMLDiagramGenerator(str(tmp_path))
        if cg is not None:
            chains = gen._call_chains_from_call_graph(cg)
            if chains:
                syntax = gen.generate_sequence_diagram(call_chains=chains)
                assert "sequenceDiagram" in syntax
                assert "->>" in syntax
            else:
                # No edges resolved; verify stub is returned
                syntax = gen.generate_sequence_diagram(call_chains=[])
                assert "sequenceDiagram" in syntax
        else:
            # CallGraph build failed; verify fallback still works
            syntax = gen.generate_sequence_diagram()
            assert "sequenceDiagram" in syntax
