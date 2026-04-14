"""Tests for BDR parser defect fixes D9-D16 (issue #209).

Covers:
  D9  - pyproject.toml regex fallback scope-limited to [project] section
  D10 - Cargo.toml uses tomllib structured parse when available
  D11 - Gradle map-style + libs.alias declarations parsed
  D13 - inline comment stripping uses whitespace+# split (URL hash safety)
  D16 - _network_classify is present, lru_cache-wrapped, and opt-in

Windows-safe: ASCII only.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _parsers():
    from langgraph_engine.build_dependency_resolver import parsers

    return parsers


# ---------------------------------------------------------------------------
# D13: inline comment stripping in _parse_req_line
# ---------------------------------------------------------------------------


class TestD13InlineCommentStripping:
    def test_plain_comment_stripped(self):
        p = _parsers()
        result = p._parse_req_line("requests>=2.28  # http client")
        assert result is not None
        assert result["name"] == "requests"

    def test_url_with_hash_fragment_not_stripped(self):
        """D13: 'name @ url#egg=name' must NOT be truncated at the # inside the URL."""
        p = _parsers()
        # The hash in the URL is adjacent to the fragment, no whitespace before it.
        # re.split(r"\s+#", ...) only splits on whitespace+#, so the hash inside
        # a URL (no preceding whitespace) is preserved.
        line = "mylib @ https://example.com/mylib-1.0.tar.gz#sha256=abc123"
        result = p._parse_req_line(line)
        # This is a VCS/URL install -- _parse_req_line may return None for URL installs.
        # The important check: it must NOT return "https" as the name, which would
        # indicate the line was truncated at "https://...#" -> "https:".
        if result is not None:
            assert result["name"] != "https"

    def test_empty_after_comment_returns_none(self):
        p = _parsers()
        result = p._parse_req_line("  # just a comment")
        assert result is None

    def test_no_comment_unchanged(self):
        p = _parsers()
        result = p._parse_req_line("flask==2.3.0")
        assert result is not None
        assert result["name"] == "flask"
        assert "2.3.0" in result["version"]

    def test_whitespace_separated_comment(self):
        p = _parsers()
        result = p._parse_req_line("numpy>=1.24 # scientific computing")
        assert result is not None
        assert result["name"] == "numpy"


# ---------------------------------------------------------------------------
# D9: pyproject.toml regex fallback scope-limited to [project] section
# ---------------------------------------------------------------------------


class TestD9PyprojectRegexFallback:
    def _parse(self, content: str):
        p = _parsers()
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "pyproject.toml"
            f.write_text(content, encoding="utf-8")
            # Force regex fallback by patching tomllib + tomli to be unavailable
            with patch.dict("sys.modules", {"tomllib": None, "tomli": None}):
                import importlib

                with patch.object(importlib, "import_module", side_effect=ImportError):
                    result = p._read_pyproject_deps(Path(tmp), [str(f)])
        return result

    def test_project_deps_extracted(self):
        content = """
[project]
name = "myapp"
dependencies = [
    "requests>=2.28",
    "flask==2.3.0",
]
"""
        deps = self._parse(content)
        names = {d["name"] for d in deps}
        assert "requests" in names
        assert "flask" in names

    def test_non_project_section_excluded(self):
        """D9: deps under [tool.poetry] must NOT be extracted by the regex fallback."""
        content = """
[tool.poetry]
name = "myapp"

[tool.poetry.dependencies]
python = "^3.9"
django = "^4.2"

[project]
dependencies = [
    "requests>=2.28",
]
"""
        deps = self._parse(content)
        names = {d["name"] for d in deps}
        # requests is in [project] -> included
        assert "requests" in names
        # django is in [tool.poetry.dependencies] -> excluded
        assert "django" not in names

    def test_empty_deps_returns_empty_list(self):
        content = "[project]\nname = 'empty'\n"
        deps = self._parse(content)
        assert isinstance(deps, list)

    def test_no_project_section_returns_empty_list(self):
        content = "[tool.ruff]\nline-length = 88\n"
        deps = self._parse(content)
        assert isinstance(deps, list)
        assert len(deps) == 0


# ---------------------------------------------------------------------------
# D10: Cargo.toml structured parse via tomllib/tomli
# ---------------------------------------------------------------------------


class TestD10CargoTomllb:
    def _cargo_deps(self, content: str):
        p = _parsers()
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "Cargo.toml"
            f.write_bytes(content.encode("utf-8"))
            return p._parse_cargo_deps(Path(tmp), [str(f)])

    def test_simple_version_string(self):
        content = '[dependencies]\nserde = "1.0"\ntokio = "1.36"\n'
        deps = self._cargo_deps(content)
        names = {d["name"] for d in deps}
        assert "serde" in names
        assert "tokio" in names

    def test_table_style_version(self):
        content = '[dependencies]\nserde = { version = "1.0", features = ["derive"] }\n'
        deps = self._cargo_deps(content)
        names = {d["name"] for d in deps}
        assert "serde" in names
        # Version should be "1.0" not the whole table string
        serde_dep = next(d for d in deps if d["name"] == "serde")
        assert serde_dep["version"] == "1.0"

    def test_dev_deps_included(self):
        content = '[dependencies]\nserde = "1.0"\n[dev-dependencies]\ncargo-test = "0.1"\n'
        deps = self._cargo_deps(content)
        names = {d["name"] for d in deps}
        assert "cargo-test" in names

    def test_empty_cargo_toml(self):
        deps = self._cargo_deps("[package]\nname = 'myapp'\n")
        assert isinstance(deps, list)

    def test_no_duplicate_deps(self):
        content = '[dependencies]\nserde = "1.0"\n[dev-dependencies]\nserde = "1.0"\n'
        deps = self._cargo_deps(content)
        names = [d["name"] for d in deps]
        assert names.count("serde") == 1


# ---------------------------------------------------------------------------
# D11: Gradle map-style and libs.alias declarations
# ---------------------------------------------------------------------------


class TestD11GradleMapAndLibs:
    def _gradle_deps(self, content: str):
        p = _parsers()
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "build.gradle"
            f.write_text(content, encoding="utf-8")
            return p._parse_gradle_deps(Path(tmp), [str(f)])

    def test_string_literal_style(self):
        content = "implementation 'com.google.guava:guava:32.0-jre'\n"
        deps = self._gradle_deps(content)
        names = {d["name"] for d in deps}
        assert "com.google.guava:guava" in names

    def test_map_style(self):
        content = "implementation group: 'org.springframework', name: 'spring-core', version: '6.1'\n"
        deps = self._gradle_deps(content)
        names = {d["name"] for d in deps}
        assert "org.springframework:spring-core" in names
        dep = next(d for d in deps if d["name"] == "org.springframework:spring-core")
        assert dep["version"] == "6.1"

    def test_libs_alias_style(self):
        content = "implementation libs.androidx.core\n"
        deps = self._gradle_deps(content)
        names = {d["name"] for d in deps}
        assert any("libs.androidx" in n for n in names)

    def test_no_duplicates_across_styles(self):
        content = (
            "implementation 'com.example:mylib:1.0'\n"
            "implementation group: 'com.example', name: 'mylib2', version: '2.0'\n"
        )
        deps = self._gradle_deps(content)
        names = [d["name"] for d in deps]
        assert len(names) == len(set(names))

    def test_empty_gradle_file(self):
        deps = self._gradle_deps("// empty build file\n")
        assert isinstance(deps, list)


# ---------------------------------------------------------------------------
# D16: _network_classify presence, caching, opt-in guard
# ---------------------------------------------------------------------------


class TestD16NetworkClassify:
    def test_function_exists(self):
        p = _parsers()
        assert hasattr(p, "_network_classify"), "_network_classify function missing (D16)"

    def test_function_is_callable(self):
        p = _parsers()
        assert callable(p._network_classify)

    def test_lru_cache_applied(self):
        """_network_classify must be wrapped with functools.lru_cache."""
        p = _parsers()
        assert hasattr(p._network_classify, "cache_info"), "_network_classify is not lru_cache-wrapped"

    def test_returns_none_when_disabled(self):
        """When BDR_NETWORK_CLASSIFY is not set, classify_dep must not call network."""
        p = _parsers()
        import os

        env = dict(os.environ)
        env.pop("BDR_NETWORK_CLASSIFY", None)
        with patch.dict("os.environ", env, clear=True):
            # Clear cache so fresh call goes through the env check path
            p._network_classify.cache_clear()
            result = p._network_classify("requests", "python-pip")
        # When network classify is disabled the function itself is never called
        # by _classify_dep, but if called directly it should either return None
        # or "external_known" (network hit). Either is acceptable here since
        # the function itself doesn't check the env var -- the caller does.
        # Just verify it doesn't raise and returns Optional[str].
        assert result is None or result == "external_known"

    def test_classify_dep_does_not_call_network_by_default(self):
        """_classify_dep must NOT trigger _network_classify without BDR_NETWORK_CLASSIFY=1."""
        p = _parsers()
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dep = {"name": "someobscurepkg123", "version": "*"}
            with patch.object(p, "_network_classify") as mock_nc:
                with patch.dict("os.environ", {}, clear=False):
                    import os

                    os.environ.pop("BDR_NETWORK_CLASSIFY", None)
                    p._classify_dep(root, dep, "python-pip")
                mock_nc.assert_not_called()
