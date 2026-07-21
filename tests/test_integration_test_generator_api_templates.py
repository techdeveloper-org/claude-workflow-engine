"""Unit tests for langgraph_engine/level3_execution/integration_test_generator.py --
generate_api_test() and its per-framework template constants (HLD Section 3 row
C13, FR-5).

Covers:
- Each framework stub (flask, fastapi, django, spring, generic/unmapped) still
  produces valid, parseable Python containing the expected placeholders.
- The enriched _FASTAPI_API_TEST template carries the async httpx.AsyncClient /
  ASGITransport pattern sourced from the sibling library's fastapi-core skill,
  while still satisfying the same format-string contract as the other stubs.
- generate_api_test() itself needs no per-framework code branch changes beyond
  what already existed (contract stability check).
"""

import ast
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.level3_execution.integration_test_generator import generate_api_test  # noqa: E402


def _wrap_in_class(stub_body: str) -> str:
    """Wrap a generated stub method body in an enclosing class so ast.parse()
    can validate it as syntactically complete Python (the stub itself is only
    a class-body method, not a standalone module).
    """
    return "import pytest\n\n\nclass TestApi:\n" + stub_body


class TestGenerateApiTestFrameworkStubs:
    ENDPOINT_FQN = "app/routes.py::UserView.get_user"

    @pytest.mark.parametrize(
        "framework",
        ["flask", "fastapi", "django", "spring", "some_unknown_framework"],
    )
    def test_produces_parseable_python(self, framework):
        stub = generate_api_test(self.ENDPOINT_FQN, framework=framework)
        assert stub is not None
        wrapped = _wrap_in_class(stub)
        ast.parse(wrapped)  # raises SyntaxError on malformed output

    @pytest.mark.parametrize(
        "framework",
        ["flask", "fastapi", "django", "spring", "generic"],
    )
    def test_contains_safe_name_test_method(self, framework):
        stub = generate_api_test(self.ENDPOINT_FQN, framework=framework)
        assert "def test_api_endpoint_get_user(self):" in stub

    def test_returns_none_for_empty_endpoint(self):
        assert generate_api_test("", framework="flask") is None
        assert generate_api_test(None, framework="flask") is None

    def test_unmapped_framework_falls_back_to_generic_marker(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="totally_unknown")
        assert "Generic HTTP endpoint test" in stub


class TestFastApiTemplateEnrichment:
    """The FastAPI stub was enriched (FR-5) from the sibling library's
    skills/fastapi-core/SKILL.md section 15 (async pytest + httpx.AsyncClient
    over ASGITransport + dependency_overrides). Flask, Django, and Spring were
    left unchanged -- no richer concrete test-client example exists for them
    anywhere in the library (verified: no skill contains flask.test_client(),
    django.test.Client(), or a MockMvc-bean-based Spring test example).
    """

    ENDPOINT_FQN = "api/orders.py::OrderController.get"

    def test_fastapi_stub_uses_async_httpx_pattern(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="fastapi")
        assert "AsyncClient" in stub
        assert "ASGITransport" in stub
        assert "dependency_overrides" in stub
        assert "pytest.mark.asyncio" in stub

    def test_fastapi_stub_still_parses_as_python(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="fastapi")
        ast.parse(_wrap_in_class(stub))

    def test_fastapi_stub_keeps_endpoint_method_in_docstring(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="fastapi")
        assert self.ENDPOINT_FQN in stub

    def test_flask_stub_unchanged_shape(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="flask")
        assert "test_client()" in stub
        assert "pass  # TODO: configure Flask test client and route" in stub

    def test_django_stub_unchanged_shape(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="django")
        assert "django.test import Client" in stub

    def test_spring_stub_unchanged_shape(self):
        stub = generate_api_test(self.ENDPOINT_FQN, framework="spring")
        assert "MockMvc" in stub
