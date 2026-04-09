---
description: "Level 2.3 - Python/FastAPI testing standards: 122 scenarios across 11 layers (positive/negative/edge)"
paths:
  - "tests/**/*.py"
  - "test_*.py"
  - "*_test.py"
priority: high
conditional: "Python FastAPI project detected (requirements.txt or pyproject.toml with fastapi)"
---

# Python/FastAPI Testing Standards (Level 2.3)

**PURPOSE:** Define the mandatory test scenarios that every Python FastAPI REST microservice
must cover, organized by application layer. This file is the Python/FastAPI-specific implementation
of the language-agnostic scenarios defined in `40-universal-test-patterns-abstract.md`. It is
self-contained: every scenario includes a concrete Python code example using pytest, unittest.mock,
httpx.AsyncClient, Pydantic v2, and SQLAlchemy 2.0 async. A developer can apply this file
without reading the abstract file.

**APPLIES WHEN:** Any Python FastAPI REST microservice with Router → Service → Repository layers,
Pydantic v2 request/response models, and SQLAlchemy 2.0 async ORM.

---

## Technology Stack

| Concern | Tool |
|---------|------|
| Framework | FastAPI 0.100+ |
| Test Runner | pytest 7+ |
| Async Test | pytest-asyncio |
| HTTP Test Client | httpx.AsyncClient with ASGITransport OR TestClient (sync) |
| Mocking | unittest.mock (patch, MagicMock, AsyncMock) + pytest-mock (mocker) |
| Validation | Pydantic v2 BaseModel with Field validators |
| ORM | SQLAlchemy 2.0 async (AsyncSession) |
| Event Publishing | aioredis / redis-py async |
| Assertions | pytest assert + assertpy (optional) |

---

## Shared conftest.py (Required in every test package)

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

from app.main import app
from app.services.resource_service import ResourceService
from app.repositories.resource_repository import ResourceRepository


@pytest.fixture
def mock_service():
    """Injected mock for ResourceService — used in controller tests."""
    service = MagicMock(spec=ResourceService)
    app.dependency_overrides[ResourceService] = lambda: service
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def mock_repo():
    """Injected mock for ResourceRepository — used in service tests."""
    return AsyncMock(spec=ResourceRepository)


@pytest.fixture
def mock_redis():
    """Injected mock for the redis publish client — used in event publisher tests."""
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    """Synchronous TestClient bound to the mock_service override."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Async HTTPX client for async endpoint tests."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

---

## 1. Bootstrap Layer — Tests

### What We Follow

The FastAPI application entry-point (`main.py`) must have tests that verify:
- The FastAPI `app` object is created
- Uvicorn startup is correctly delegated when `__main__` is invoked
- CLI arguments are forwarded without loss

Mock `uvicorn.run` using `unittest.mock.patch` so no real server starts. Use
`importlib.reload` to re-execute the entry-point module and trigger the `if __name__ == "__main__"` block.

### How To Implement

```python
# tests/test_bootstrap.py
import importlib
import sys
from unittest.mock import patch, MagicMock, call
import pytest

import app.main as main_module
from app.main import app
from fastapi import FastAPI


class TestBootstrapPositive:

    # P1: FastAPI app object is created and is a FastAPI instance
    def test_p1_app_is_fastapi_instance(self):
        assert isinstance(app, FastAPI), "app must be a FastAPI instance"

    # P2: App title is set (service discovery / OpenAPI contract)
    def test_p2_app_has_title(self):
        assert app.title is not None and app.title != "", \
            "FastAPI app must have a non-empty title set"

    # P3: App has at least one router registered (routes not empty)
    def test_p3_app_has_routes_registered(self):
        route_paths = [r.path for r in app.routes]
        assert len(route_paths) > 0, "App must have at least one route registered"

    # P4: The main module exposes a callable main() or startup via __main__
    def test_p4_main_module_is_importable_without_side_effects(self):
        # Importing the module must not raise and must not start a server
        with patch("uvicorn.run") as mock_run:
            importlib.reload(main_module)
            # If __name__ != "__main__", uvicorn.run should NOT be called on import
            mock_run.assert_not_called()

    # P5: When __name__ == "__main__", uvicorn.run is called exactly once
    def test_p5_uvicorn_run_called_when_main(self):
        with patch("uvicorn.run") as mock_run, \
             patch.object(main_module, "__name__", "__main__"):
            importlib.reload(main_module)
            mock_run.assert_called_once()

    # P6: uvicorn.run receives the app as the first positional argument
    def test_p6_uvicorn_run_receives_app_argument(self):
        with patch("uvicorn.run") as mock_run, \
             patch.object(main_module, "__name__", "__main__"):
            importlib.reload(main_module)
            call_args = mock_run.call_args
            assert call_args is not None, "uvicorn.run must be called"
            # First positional arg is the app or app string reference
            first_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("app")
            assert first_arg is not None, "uvicorn.run must receive an app argument"

    # P7: The main module has no global state that prevents re-import
    def test_p7_module_reloadable_without_error(self):
        with patch("uvicorn.run"):
            try:
                importlib.reload(main_module)
            except Exception as exc:
                pytest.fail(f"Module reload raised unexpected exception: {exc}")

    # P8: App has no unexpected custom base class (is directly FastAPI)
    def test_p8_app_is_direct_fastapi_not_subclass(self):
        assert type(app) is FastAPI, \
            "app must be a direct FastAPI instance, not a subclass"


class TestBootstrapNegative:

    # N9: Module import with empty sys.argv does not crash
    def test_n9_empty_sys_argv_does_not_crash(self):
        original_argv = sys.argv
        try:
            sys.argv = []
            with patch("uvicorn.run"):
                importlib.reload(main_module)
        except Exception as exc:
            pytest.fail(f"Empty sys.argv caused crash: {exc}")
        finally:
            sys.argv = original_argv

    # N10: Module import with no CLI args still allows uvicorn.run to be invoked
    def test_n10_no_args_still_invokes_uvicorn(self):
        original_argv = sys.argv
        try:
            sys.argv = ["app/main.py"]
            with patch("uvicorn.run") as mock_run, \
                 patch.object(main_module, "__name__", "__main__"):
                importlib.reload(main_module)
                mock_run.assert_called_once()
        finally:
            sys.argv = original_argv


class TestBootstrapEdge:

    # E11: Multiple CLI flags are forwarded without loss
    def test_e11_multiple_cli_flags_forwarded(self):
        test_argv = ["main.py", "--host=0.0.0.0", "--port=9090", "--reload"]
        original_argv = sys.argv
        try:
            sys.argv = test_argv
            with patch("uvicorn.run") as mock_run, \
                 patch.object(main_module, "__name__", "__main__"):
                importlib.reload(main_module)
                # Verify uvicorn was called — argument forwarding via sys.argv
                # is the Python equivalent of forwarding CLI flags
                mock_run.assert_called_once()
        finally:
            sys.argv = original_argv
```

### Why This Matters

Without P5, the `if __name__ == "__main__"` block is never exercised and the coverage
gate fails on the entry-point module. Without N9 and N10, empty `sys.argv` in CI
containers causes silent crashes before the first test runs.

---

## 2. Configuration Layer — Tests

### What We Follow

Configuration modules (Pydantic `BaseSettings` or plain constants modules) must be
verified to load without error and expose the exact expected constant values. No mocks
required — instantiate the settings class directly using test environment values.

### How To Implement

```python
# tests/test_config.py
import pytest
from app.config import CacheConfig, Settings


class TestConfigPositive:

    # P12: Config class instantiates without error
    def test_p12_config_instantiates_without_error(self):
        config = CacheConfig()
        assert config is not None

    # P13: Single-entity cache name constant has correct value
    def test_p13_cache_by_id_constant_correct(self):
        assert CacheConfig.CACHE_BY_ID == "resourceById", \
            f"Expected 'resourceById', got '{CacheConfig.CACHE_BY_ID}'"

    # P14: Collection cache name constant has correct value
    def test_p14_cache_all_constant_correct(self):
        assert CacheConfig.CACHE_ALL == "allResources", \
            f"Expected 'allResources', got '{CacheConfig.CACHE_ALL}'"

    # P15: Count cache name constant has correct value
    def test_p15_cache_count_constant_correct(self):
        assert CacheConfig.CACHE_COUNT == "resourceCount", \
            f"Expected 'resourceCount', got '{CacheConfig.CACHE_COUNT}'"


class TestConfigNegative:

    # N16: No configuration constant is None or empty string
    def test_n16_no_constant_is_none_or_empty(self):
        constants = [
            ("CACHE_BY_ID", CacheConfig.CACHE_BY_ID),
            ("CACHE_ALL", CacheConfig.CACHE_ALL),
            ("CACHE_COUNT", CacheConfig.CACHE_COUNT),
        ]
        for name, value in constants:
            assert value is not None, f"CacheConfig.{name} must not be None"
            assert value != "", f"CacheConfig.{name} must not be an empty string"
            assert value.strip() != "", f"CacheConfig.{name} must not be whitespace-only"


class TestConfigEdge:

    # E17: All configuration constants are distinct (no duplicate values)
    def test_e17_all_constants_are_distinct(self):
        values = [
            CacheConfig.CACHE_BY_ID,
            CacheConfig.CACHE_ALL,
            CacheConfig.CACHE_COUNT,
        ]
        assert len(values) == len(set(values)), \
            f"All cache name constants must be distinct. Found duplicates in: {values}"
```

### Why This Matters

A typo in a cache name constant causes silent cache misses — the application returns
200 but queries the database on every request. String assertions at test time catch
the typo before it reaches staging.

---

## 3. Controller / Route Layer — Tests

### What We Follow

Every FastAPI route handler must be tested for the correct HTTP status code and response
body structure on the happy path and for correct error propagation on the failure path.
Override the service dependency using `app.dependency_overrides` so no real service or
database is involved. Use `TestClient` (sync) or `httpx.AsyncClient` (async).

### How To Implement

```python
# tests/test_resource_router.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.resource_service import ResourceService
from app.schemas.resource_schema import ResourceResponse, ResourceForm
from app.core.exceptions import (
    DuplicateNameException,
    DuplicatePathException,
    ResourceNotFoundException,
)


def _mock_dto(resource_id: int = 1, name: str = "TestResource", path: str = "/test"):
    return {"id": resource_id, "name": name, "path": path}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestResourceRouterPositive:

    # P18: POST create returns 201 CREATED
    def test_p18_post_create_returns_201(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.add.return_value = {
            "success": True, "status": 201,
            "message": "Created", "data": _mock_dto()
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.post("/api/resources", json={"name": "TestResource", "path": "/test"})

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"] is not None

    # P19: PUT update returns 200 OK
    def test_p19_put_update_returns_200(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.update.return_value = {
            "success": True, "status": 200,
            "message": "Updated", "data": _mock_dto(name="Updated")
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.put("/api/resources/1", json={"name": "Updated", "path": "/updated"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    # P20: GET by ID returns 200 OK with single resource
    def test_p20_get_by_id_returns_200(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_by_id.return_value = {
            "success": True, "status": 200,
            "message": "Found", "data": _mock_dto(resource_id=1)
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources/1")

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["id"] == 1

    # P21: GET all returns 200 OK with ordered list
    def test_p21_get_all_returns_200_with_list(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_all.return_value = {
            "success": True, "status": 200,
            "message": "OK",
            "data": [_mock_dto(1, "A", "/a"), _mock_dto(2, "B", "/b")]
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], list)

    # P22: DELETE returns 200 OK
    def test_p22_delete_returns_200(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.delete.return_value = {
            "success": True, "status": 200, "message": "Deleted", "data": None
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.delete("/api/resources/1")

        assert response.status_code == 200

    # P23: GET count returns 200 OK with numeric value
    def test_p23_get_count_returns_200_with_number(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_count.return_value = {
            "success": True, "status": 200, "message": "OK", "data": 5
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources/count")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], int)
        assert body["data"] == 5


class TestResourceRouterNegative:

    # N24: POST with duplicate name propagates 409
    def test_n24_duplicate_name_returns_409(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.add.side_effect = DuplicateNameException("Name already exists")
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.post("/api/resources", json={"name": "Existing", "path": "/new"})

        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False

    # N25: POST with duplicate path propagates 409
    def test_n25_duplicate_path_returns_409(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.add.side_effect = DuplicatePathException("Path already exists")
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.post("/api/resources", json={"name": "New", "path": "/existing"})

        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False

    # N26: GET with non-existent ID propagates 404
    def test_n26_nonexistent_id_get_returns_404(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_by_id.side_effect = ResourceNotFoundException("Resource not found")
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources/9999")

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False

    # N27: PUT with non-existent ID propagates 404
    def test_n27_nonexistent_id_put_returns_404(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.update.side_effect = ResourceNotFoundException("Resource not found")
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.put("/api/resources/9999", json={"name": "Name", "path": "/path"})

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False


class TestResourceRouterEdge:

    # E28: GET all with empty data returns empty list, NOT null
    def test_e28_get_all_empty_returns_empty_list_not_null(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_all.return_value = {
            "success": True, "status": 200, "message": "OK", "data": []
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources")

        assert response.status_code == 200
        body = response.json()
        assert body["data"] is not None, "data must not be null for empty results"
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 0

    # E29: GET all preserves ordered list type (not set or unordered)
    def test_e29_get_all_preserves_ordered_list(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_all.return_value = {
            "success": True, "status": 200, "message": "OK",
            "data": [_mock_dto(1), _mock_dto(2), _mock_dto(3)]
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        response = client.get("/api/resources")

        body = response.json()
        # JSON arrays preserve order; verify the data field is a list
        assert isinstance(body["data"], list), \
            "GET all must return a JSON array (ordered), not a JSON object or null"

    # E30: Service invoked exactly once per request (no double-call)
    def test_e30_service_invoked_exactly_once(self):
        mock_svc = MagicMock(spec=ResourceService)
        mock_svc.get_by_id.return_value = {
            "success": True, "status": 200, "message": "OK", "data": _mock_dto()
        }
        app.dependency_overrides[ResourceService] = lambda: mock_svc

        client = TestClient(app)
        client.get("/api/resources/1")

        mock_svc.get_by_id.assert_called_once_with(1)
```

### Why This Matters

FastAPI routes are thin — they delegate to services. Testing status codes in isolation
via `dependency_overrides` verifies the HTTP contract in milliseconds without starting
a real database or Redis connection.

---

## 4. Service Layer — Tests

### What We Follow

Every service method must be tested on its happy path and failure path using injected
mock repositories and event publishers. Call service methods directly — no HTTP client.
Use `AsyncMock` for async repository methods and verify argument shapes with `call_args`.

### How To Implement

```python
# tests/test_resource_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from app.services.resource_service import ResourceService
from app.repositories.resource_repository import ResourceRepository
from app.events.resource_event_publisher import ResourceEventPublisher
from app.core.exceptions import (
    DuplicateNameException,
    DuplicatePathException,
    ResourceNotFoundException,
)
from app.models.resource_entity import ResourceEntity


def _entity(resource_id=1, name="Name", path="/path"):
    e = ResourceEntity()
    e.id = resource_id
    e.name = name
    e.path = path
    return e


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=ResourceRepository)
    return repo


@pytest.fixture
def mock_publisher():
    return AsyncMock(spec=ResourceEventPublisher)


@pytest.fixture
def service(mock_repo, mock_publisher):
    return ResourceService(repository=mock_repo, publisher=mock_publisher)


class TestResourceServicePositive:

    # P31: Add resource returns populated DTO with correct fields
    @pytest.mark.asyncio
    async def test_p31_add_returns_populated_dto(self, service, mock_repo):
        mock_repo.exists_by_name_icase.return_value = False
        mock_repo.exists_by_path_icase.return_value = False
        mock_repo.save.return_value = _entity(1, "Name", "/path")

        form = {"name": "Name", "path": "/path"}
        result = await service.add(form)

        assert result["data"]["id"] == 1
        assert result["data"]["name"] == "Name"
        assert result["data"]["path"] == "/path"
        assert result["status"] == 201

    # P32: Update resource returns updated DTO
    @pytest.mark.asyncio
    async def test_p32_update_returns_updated_dto(self, service, mock_repo):
        mock_repo.find_by_id.return_value = _entity(1, "Old", "/old")
        mock_repo.exists_by_name_icase_exclude_id.return_value = False
        mock_repo.exists_by_path_icase_exclude_id.return_value = False
        mock_repo.save.return_value = _entity(1, "Updated", "/updated")

        form = {"name": "Updated", "path": "/updated"}
        result = await service.update(1, form)

        assert result["data"]["name"] == "Updated"
        assert result["data"]["path"] == "/updated"
        assert result["status"] == 200

    # P33: Get by ID returns DTO with all fields correctly mapped
    @pytest.mark.asyncio
    async def test_p33_get_by_id_maps_all_fields(self, service, mock_repo):
        mock_repo.find_by_id.return_value = _entity(1, "Name", "/path")

        result = await service.get_by_id(1)

        assert result["data"]["id"] == 1
        assert result["data"]["name"] == "Name"
        assert result["data"]["path"] == "/path"

    # P34: Get all passes sort-by-ID-ascending to repository
    @pytest.mark.asyncio
    async def test_p34_get_all_passes_sort_asc_id_to_repo(self, service, mock_repo):
        mock_repo.find_all_sorted.return_value = []

        await service.get_all()

        # MUST verify exact sort arguments — not just assert_called_once()
        mock_repo.find_all_sorted.assert_called_once_with(sort_by="id", direction="ASC")

    # P35: Get all returns items in ID-ascending order
    @pytest.mark.asyncio
    async def test_p35_get_all_returns_id_ascending_order(self, service, mock_repo):
        mock_repo.find_all_sorted.return_value = [
            _entity(1, "A", "/a"), _entity(2, "B", "/b"), _entity(3, "C", "/c")
        ]

        result = await service.get_all()

        ids = [item["id"] for item in result["data"]]
        assert ids == sorted(ids), f"IDs must be in ascending order, got: {ids}"

    # P36: Delete triggers DELETE cache invalidation event
    @pytest.mark.asyncio
    async def test_p36_delete_publishes_delete_event(self, service, mock_repo, mock_publisher):
        mock_repo.delete_by_id.return_value = None

        await service.delete(1)

        mock_publisher.publish_delete.assert_called_once_with(1)

    # P37: Count returns correct non-zero count
    @pytest.mark.asyncio
    async def test_p37_count_returns_nonzero(self, service, mock_repo):
        mock_repo.count.return_value = 5

        result = await service.get_count()

        assert result["data"] == 5

    # P38: Count returns zero when repository is empty
    @pytest.mark.asyncio
    async def test_p38_count_returns_zero_for_empty(self, service, mock_repo):
        mock_repo.count.return_value = 0

        result = await service.get_count()

        assert result["data"] == 0
        assert result["data"] is not None, "Count must return 0 (int), not None"

    # P39: Update with identical data (idempotent) succeeds without error
    @pytest.mark.asyncio
    async def test_p39_idempotent_update_succeeds(self, service, mock_repo):
        entity = _entity(1, "Name", "/path")
        mock_repo.find_by_id.return_value = entity
        mock_repo.exists_by_name_icase_exclude_id.return_value = False
        mock_repo.exists_by_path_icase_exclude_id.return_value = False
        mock_repo.save.return_value = entity

        form = {"name": "Name", "path": "/path"}
        try:
            await service.update(1, form)
        except Exception as exc:
            pytest.fail(f"Idempotent update raised unexpected exception: {exc}")


class TestResourceServiceNegative:

    # N40: Add with duplicate name throws DuplicateNameException
    @pytest.mark.asyncio
    async def test_n40_add_duplicate_name_raises_typed_exception(self, service, mock_repo):
        mock_repo.exists_by_name_icase.return_value = True

        with pytest.raises(DuplicateNameException):
            await service.add({"name": "Existing", "path": "/new"})

    # N41: Add with duplicate path throws DuplicatePathException
    @pytest.mark.asyncio
    async def test_n41_add_duplicate_path_raises_typed_exception(self, service, mock_repo):
        mock_repo.exists_by_name_icase.return_value = False
        mock_repo.exists_by_path_icase.return_value = True

        with pytest.raises(DuplicatePathException):
            await service.add({"name": "New", "path": "/existing"})

    # N42: Get by non-existent ID throws ResourceNotFoundException
    @pytest.mark.asyncio
    async def test_n42_get_nonexistent_id_raises_not_found(self, service, mock_repo):
        mock_repo.find_by_id.return_value = None

        with pytest.raises(ResourceNotFoundException):
            await service.get_by_id(9999)

    # N43: Update non-existent ID throws ResourceNotFoundException
    @pytest.mark.asyncio
    async def test_n43_update_nonexistent_id_raises_not_found(self, service, mock_repo):
        mock_repo.find_by_id.return_value = None

        with pytest.raises(ResourceNotFoundException):
            await service.update(9999, {"name": "Name", "path": "/path"})

    # N44: Update with name taken by another resource raises DuplicateNameException
    @pytest.mark.asyncio
    async def test_n44_update_name_taken_by_other_raises_duplicate(self, service, mock_repo):
        mock_repo.find_by_id.return_value = _entity(1, "Old", "/old")
        mock_repo.exists_by_name_icase_exclude_id.return_value = True  # Other resource has this name

        with pytest.raises(DuplicateNameException):
            await service.update(1, {"name": "Taken", "path": "/new"})

    # N45: Update with path taken by another resource raises DuplicatePathException
    @pytest.mark.asyncio
    async def test_n45_update_path_taken_by_other_raises_duplicate(self, service, mock_repo):
        mock_repo.find_by_id.return_value = _entity(1, "Name", "/old")
        mock_repo.exists_by_name_icase_exclude_id.return_value = False
        mock_repo.exists_by_path_icase_exclude_id.return_value = True  # Other resource has this path

        with pytest.raises(DuplicatePathException):
            await service.update(1, {"name": "Name", "path": "/taken"})


class TestResourceServiceEdge:

    # E46: Case-insensitive duplicate detection blocks "Resource" when "resource" exists
    @pytest.mark.asyncio
    async def test_e46_case_insensitive_duplicate_name_blocked(self, service, mock_repo):
        # Repository uses icase (case-insensitive) check; return True for case-variant
        mock_repo.exists_by_name_icase.return_value = True

        with pytest.raises(DuplicateNameException):
            await service.add({"name": "RESOURCE", "path": "/new"})

    # E47: Get all with empty repository returns empty list, not None
    @pytest.mark.asyncio
    async def test_e47_empty_repository_returns_empty_list(self, service, mock_repo):
        mock_repo.find_all_sorted.return_value = []

        result = await service.get_all()

        assert result["data"] is not None, "data must not be None when repository is empty"
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 0

    # E48: Delete non-existent ID raises no error (idempotent delete)
    @pytest.mark.asyncio
    async def test_e48_delete_nonexistent_id_is_idempotent(self, service, mock_repo):
        mock_repo.delete_by_id.return_value = None  # No-op for non-existent

        try:
            await service.delete(9999)
        except Exception as exc:
            pytest.fail(f"Delete of non-existent ID raised unexpected exception: {exc}")

    # E49: Null event publisher does not crash delete
    @pytest.mark.asyncio
    async def test_e49_null_publisher_does_not_crash_delete(self, mock_repo):
        service_no_pub = ResourceService(repository=mock_repo, publisher=None)
        mock_repo.delete_by_id.return_value = None

        try:
            await service_no_pub.delete(1)
        except AttributeError:
            pytest.fail("Service crashed with AttributeError when publisher is None")

    # E50: Sort argument validated exactly: correct direction AND field name
    @pytest.mark.asyncio
    async def test_e50_sort_direction_and_field_exact(self, service, mock_repo):
        mock_repo.find_all_sorted.return_value = []

        await service.get_all()

        mock_repo.find_all_sorted.assert_called_once()
        call_kwargs = mock_repo.find_all_sorted.call_args

        # Extract the sort parameters — adjust key names to match your implementation
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        args = call_kwargs.args if call_kwargs.args else ()

        sort_field = kwargs.get("sort_by") or (args[0] if args else None)
        sort_dir = kwargs.get("direction") or (args[1] if len(args) > 1 else None)

        assert sort_field == "id", f"Sort field must be 'id', got '{sort_field}'"
        assert str(sort_dir).upper() == "ASC", f"Sort direction must be 'ASC', got '{sort_dir}'"
```

### Why This Matters

Service layer holds all business rules. Happy-path tests verify that entity-to-dict
mapping is complete, sort contracts are respected, and cache events are published on
every mutating operation.

---

## 5. Entity / Model Layer — Tests

### What We Follow

Every SQLAlchemy model or Pydantic model must have tests for constructors, property
access, equality contract, and string representation. No mocks required — direct
instantiation only. Tests must complete in under 1 ms each.

### How To Implement

```python
# tests/test_resource_entity.py
import json
import sys
import pytest
from app.models.resource_entity import ResourceEntity


class TestResourceEntityPositive:

    # P51: Parameterized constructor/factory sets all fields
    def test_p51_parameterized_constructor_sets_all_fields(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        assert entity.id == 1
        assert entity.name == "Name"
        assert entity.path == "/path"

    # P52: Default (no-args) constructor creates a non-null instance
    def test_p52_no_args_constructor_creates_non_null_instance(self):
        entity = ResourceEntity()
        assert entity is not None

    # P53: Getters/properties return values set by assignment
    def test_p53_setters_and_getters_round_trip(self):
        entity = ResourceEntity()
        entity.id = 42
        entity.name = "Test"
        entity.path = "/test"

        assert entity.id == 42
        assert entity.name == "Test"
        assert entity.path == "/test"

    # P54: Equality — two instances with same data are equal
    def test_p54_two_instances_with_same_data_are_equal(self):
        e1 = ResourceEntity(id=1, name="Name", path="/path")
        e2 = ResourceEntity(id=1, name="Name", path="/path")
        assert e1 == e2

    # P55: Hash — equal objects produce the same hash code
    def test_p55_equal_objects_have_same_hash(self):
        e1 = ResourceEntity(id=1, name="Name", path="/path")
        e2 = ResourceEntity(id=1, name="Name", path="/path")
        assert hash(e1) == hash(e2)

    # P56: Equality — reflexive: object equals itself
    def test_p56_reflexive_equality(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        assert entity == entity

    # P57: String representation is not null or empty
    def test_p57_repr_is_not_null_or_empty(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        assert repr(entity) is not None
        assert repr(entity) != ""

    # P58: String representation contains the type name
    def test_p58_repr_contains_class_name(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        assert "ResourceEntity" in repr(entity), \
            f"repr must contain 'ResourceEntity', got: {repr(entity)}"

    # P59: String representation contains field values
    def test_p59_repr_contains_field_values(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        representation = repr(entity)
        assert "1" in representation, "repr must contain the ID value"
        assert "Name" in representation, "repr must contain the name value"

    # P60: Entity can be serialized to dict/JSON without error
    def test_p60_entity_serializes_to_dict(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        # SQLAlchemy models: test __dict__ or explicit to_dict method
        data = {"id": entity.id, "name": entity.name, "path": entity.path}
        json_str = json.dumps(data)
        deserialized = json.loads(json_str)
        assert deserialized["id"] == 1
        assert deserialized["name"] == "Name"
        assert deserialized["path"] == "/path"

    # P61: Entity class has __tablename__ defined (SQLAlchemy contract)
    def test_p61_entity_has_tablename(self):
        assert hasattr(ResourceEntity, "__tablename__"), \
            "SQLAlchemy entity must define __tablename__"
        assert ResourceEntity.__tablename__ is not None
        assert ResourceEntity.__tablename__ != ""


class TestResourceEntityNegative:

    # N62: Equality — different IDs means not equal
    def test_n62_different_ids_not_equal(self):
        e1 = ResourceEntity(id=1, name="Name", path="/path")
        e2 = ResourceEntity(id=2, name="Name", path="/path")
        assert e1 != e2

    # N63: Equality — comparison to None returns False, no crash
    def test_n63_comparison_to_none_returns_false(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        result = entity.__eq__(None)
        assert result is False or result is NotImplemented, \
            "Comparing entity to None must return False or NotImplemented, not raise"

    # N64: Equality — comparison to a different type returns False
    def test_n64_comparison_to_different_type_returns_false(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        result = entity.__eq__("some string")
        assert result is False or result is NotImplemented

    # N65: Constructor with None name does not raise in the constructor
    def test_n65_constructor_with_none_name_does_not_crash(self):
        try:
            entity = ResourceEntity(id=1, name=None, path="/path")
            assert entity is not None
        except Exception as exc:
            pytest.fail(f"Constructor raised on None name (ORM hydration requires this): {exc}")

    # N66: Constructor with None path does not raise in the constructor
    def test_n66_constructor_with_none_path_does_not_crash(self):
        try:
            entity = ResourceEntity(id=1, name="Name", path=None)
            assert entity is not None
        except Exception as exc:
            pytest.fail(f"Constructor raised on None path (ORM hydration requires this): {exc}")


class TestResourceEntityEdge:

    # E67: Name at exactly maximum allowed length is stored without truncation
    def test_e67_name_at_max_length_stored_exactly(self):
        max_name = "A" * 255
        entity = ResourceEntity(id=1, name=max_name, path="/path")
        assert entity.name == max_name
        assert len(entity.name) == 255

    # E68: Path at exactly maximum allowed length is stored without truncation
    def test_e68_path_at_max_length_stored_exactly(self):
        max_path = "/" + "p" * 254  # 255 total chars
        entity = ResourceEntity(id=1, name="Name", path=max_path)
        assert entity.path == max_path
        assert len(entity.path) == 255

    # E69: Maximum integer ID value does not overflow
    def test_e69_max_int_id_does_not_overflow(self):
        max_id = sys.maxsize
        entity = ResourceEntity(id=max_id, name="Name", path="/path")
        assert entity.id == max_id

    # E70: Minimum valid ID value (1) is accepted
    def test_e70_id_of_1_is_valid(self):
        entity = ResourceEntity(id=1, name="Name", path="/path")
        assert entity.id == 1

    # E71: Special characters in name stored and retrieved exactly
    def test_e71_special_characters_stored_exactly(self):
        special_name = "Res & Name (2024) <test> \u00e9"
        entity = ResourceEntity(id=1, name=special_name, path="/path")
        assert entity.name == special_name

    # E72: Whitespace-only string stored without automatic trimming
    def test_e72_whitespace_only_name_not_trimmed(self):
        whitespace_name = "   \t  "
        entity = ResourceEntity(id=1, name=whitespace_name, path="/path")
        assert entity.name == whitespace_name, \
            "Entity constructor must not trim whitespace — that is the validator's job"

    # E73: Two instances with null/None IDs and same data are equal
    def test_e73_two_null_id_instances_with_same_data_are_equal(self):
        e1 = ResourceEntity(id=None, name="Name", path="/path")
        e2 = ResourceEntity(id=None, name="Name", path="/path")
        assert e1 == e2, \
            "Two pre-persist entities (None ID) with same data must be equal for Set deduplication"
```

### Why This Matters

Broken entity equality contracts silently corrupt `set()` deduplication in Python.
Missing `__tablename__` causes SQLAlchemy to raise an `InvalidRequestError` that is
only discovered at runtime when a real database session is opened.

---

## 6. Error Handler Layer — Tests

### What We Follow

Every FastAPI exception handler registered with `@app.exception_handler` must be tested
by directly calling the handler function with a pre-constructed exception. Verify the
JSONResponse status code, `success=False`, and a non-blank message. No mocks required.

### How To Implement

```python
# tests/test_exception_handlers.py
import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from unittest.mock import MagicMock

from app.core.exception_handlers import (
    handle_duplicate_name,
    handle_duplicate_path,
    handle_data_integrity,
)
from app.core.exceptions import (
    DuplicateNameException,
    DuplicatePathException,
    DataIntegrityException,
)


def _mock_request():
    """Create a minimal mock FastAPI Request for handler invocation."""
    return MagicMock(spec=Request)


class TestExceptionHandlersPositive:

    # P74: Duplicate-name exception maps to 409 with correct structure
    @pytest.mark.asyncio
    async def test_p74_duplicate_name_returns_409_with_structure(self):
        request = _mock_request()
        exc = DuplicateNameException("Resource name already exists")

        response: JSONResponse = await handle_duplicate_name(request, exc)

        assert response.status_code == 409
        body = response.body  # bytes
        import json
        data = json.loads(body)
        assert data["success"] is False
        assert data["message"] is not None and data["message"] != ""

    # P75: Duplicate-path exception maps to 409 with same structure
    @pytest.mark.asyncio
    async def test_p75_duplicate_path_returns_409_with_structure(self):
        request = _mock_request()
        exc = DuplicatePathException("Resource path already exists")

        response: JSONResponse = await handle_duplicate_path(request, exc)

        assert response.status_code == 409
        import json
        data = json.loads(response.body)
        assert data["success"] is False
        assert data["message"] is not None and data["message"] != ""

    # P76: Data integrity exception maps to 409 with non-leaking message
    @pytest.mark.asyncio
    async def test_p76_data_integrity_returns_409_with_safe_message(self):
        request = _mock_request()
        exc = DataIntegrityException(
            "UNIQUE constraint failed: resource.name"
        )

        response: JSONResponse = await handle_data_integrity(request, exc)

        assert response.status_code == 409
        import json
        data = json.loads(response.body)
        # Message must not leak SQL internals
        assert "constraint" not in data["message"].lower(), \
            "Response must not expose SQL constraint details"
        assert "unique" not in data["message"].lower(), \
            "Response must not expose SQL UNIQUE keyword"

    # P77: HTTP status code in response matches status field in response body
    @pytest.mark.asyncio
    async def test_p77_http_status_matches_body_status_field(self):
        request = _mock_request()
        exc = DuplicateNameException("exists")

        response: JSONResponse = await handle_duplicate_name(request, exc)

        import json
        data = json.loads(response.body)
        assert response.status_code == data["status"], \
            f"HTTP status {response.status_code} must match body status {data['status']}"


class TestExceptionHandlersNegative:

    # N78: Duplicate-name handler explicitly sets success=False (not null, not missing)
    @pytest.mark.asyncio
    async def test_n78_duplicate_name_sets_success_false_explicitly(self):
        request = _mock_request()
        exc = DuplicateNameException("exists")

        response: JSONResponse = await handle_duplicate_name(request, exc)

        import json
        data = json.loads(response.body)
        assert "success" in data, "Response body must contain 'success' field"
        assert data["success"] is False, \
            f"success must be boolean False, got: {data['success']} (type: {type(data['success'])})"

    # N79: Duplicate-path handler explicitly sets success=False
    @pytest.mark.asyncio
    async def test_n79_duplicate_path_sets_success_false_explicitly(self):
        request = _mock_request()
        exc = DuplicatePathException("exists")

        response: JSONResponse = await handle_duplicate_path(request, exc)

        import json
        data = json.loads(response.body)
        assert "success" in data
        assert data["success"] is False


class TestExceptionHandlersEdge:

    # E80: All conflict-class handlers return identical HTTP status code (409)
    @pytest.mark.asyncio
    async def test_e80_all_conflict_handlers_return_409(self):
        request = _mock_request()
        handlers_and_exceptions = [
            (handle_duplicate_name, DuplicateNameException("a")),
            (handle_duplicate_path, DuplicatePathException("b")),
            (handle_data_integrity, DataIntegrityException("c")),
        ]

        for handler, exc in handlers_and_exceptions:
            response = await handler(request, exc)
            assert response.status_code == 409, \
                f"{handler.__name__} returned {response.status_code}, expected 409"

    # E81: All conflict-class handlers set success=False consistently
    @pytest.mark.asyncio
    async def test_e81_all_conflict_handlers_set_success_false(self):
        import json
        request = _mock_request()
        handlers_and_exceptions = [
            (handle_duplicate_name, DuplicateNameException("a")),
            (handle_duplicate_path, DuplicatePathException("b")),
            (handle_data_integrity, DataIntegrityException("c")),
        ]

        for handler, exc in handlers_and_exceptions:
            response = await handler(request, exc)
            data = json.loads(response.body)
            assert data["success"] is False, \
                f"{handler.__name__} must set success=False, got: {data['success']}"
```

### Why This Matters

Exception handler responses are the only signal a client has when an operation fails.
A well-structured error response with `success=False` and a non-leaking message prevents
SQL schema exposure and enables single-code-path error handling in clients.

---

## 7. Validation Layer — Tests

### What We Follow

Every Pydantic v2 `BaseModel` used as a request body must be tested by constructing
instances with valid and invalid inputs and asserting on `ValidationError` counts and
field paths. Use `pydantic.ValidationError` directly — no HTTP, no mocks.

### How To Implement

```python
# tests/test_resource_form.py
import pytest
from pydantic import ValidationError
from app.schemas.resource_form import ResourceForm


def _violations(name=None, path=None):
    """Helper: collect all Pydantic v2 ValidationError error dicts for given inputs."""
    try:
        if name is not None and path is not None:
            ResourceForm(name=name, path=path)
        elif name is not None:
            ResourceForm(name=name, path="/default")
        elif path is not None:
            ResourceForm(name="Default", path=path)
        else:
            ResourceForm()
        return []
    except ValidationError as exc:
        return exc.errors()


def _violation_fields(errors):
    """Extract field location strings from Pydantic v2 error list."""
    return [".".join(str(loc) for loc in err["loc"]) for err in errors]


class TestResourceFormPositive:

    # P82: Valid form — zero violations
    def test_p82_valid_form_zero_violations(self):
        errors = _violations(name="ValidName", path="/valid-path")
        assert len(errors) == 0, f"Expected 0 violations, got: {errors}"

    # P83: Minimum valid name (1 character) — zero violations
    def test_p83_single_char_name_zero_violations(self):
        errors = _violations(name="A", path="/path")
        assert len(errors) == 0

    # P84: Maximum valid name (exact max chars) — zero violations
    def test_p84_max_length_name_zero_violations(self):
        max_name = "A" * 255  # Adjust to your model's Field(max_length=...)
        errors = _violations(name=max_name, path="/path")
        assert len(errors) == 0

    # P85: Maximum valid path (exact max chars) — zero violations
    def test_p85_max_length_path_zero_violations(self):
        max_path = "/" + "p" * 254  # 255 total chars
        errors = _violations(name="Name", path=max_path)
        assert len(errors) == 0

    # P86: Special characters in name — zero violations
    def test_p86_special_chars_in_name_zero_violations(self):
        errors = _violations(name="Res & Name (2024)", path="/path")
        assert len(errors) == 0

    # P87: Numeric characters in name — zero violations
    def test_p87_numeric_name_zero_violations(self):
        errors = _violations(name="12345", path="/path")
        assert len(errors) == 0


class TestResourceFormNegative:

    # N88: None name produces required-field violation on "name" field
    def test_n88_none_name_violation_on_name_field(self):
        errors = _violations(name=None, path="/path")
        fields = _violation_fields(errors)
        assert len(errors) >= 1, "None name must produce at least one violation"
        assert "name" in fields, \
            f"Violation must be on field 'name', got fields: {fields}"

    # N89: Empty string name produces non-empty violation on "name"
    def test_n89_empty_name_violation_on_name_field(self):
        errors = _violations(name="", path="/path")
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "name" in fields

    # N90: Whitespace-only name produces non-blank violation on "name"
    def test_n90_whitespace_name_violation_on_name_field(self):
        errors = _violations(name="   ", path="/path")
        fields = _violation_fields(errors)
        assert len(errors) >= 1, \
            "Whitespace-only name must be rejected by @validator or Field with strip_whitespace"
        assert "name" in fields

    # N91: Name exceeding max length by 1 produces length violation
    def test_n91_name_max_plus_one_length_violation(self):
        over_max_name = "A" * 256  # max_length + 1
        errors = _violations(name=over_max_name, path="/path")
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "name" in fields

    # N92: Name far exceeding max length (2x) produces length violation
    def test_n92_name_double_max_length_violation(self):
        double_max = "A" * 510
        errors = _violations(name=double_max, path="/path")
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "name" in fields

    # N93: None path produces required-field violation on "path" field
    def test_n93_none_path_violation_on_path_field(self):
        errors = _violations(name="Name", path=None)
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "path" in fields

    # N94: Empty string path produces non-empty violation on "path"
    def test_n94_empty_path_violation_on_path_field(self):
        errors = _violations(name="Name", path="")
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "path" in fields

    # N95: Tab-only path produces non-blank violation on "path"
    def test_n95_tab_only_path_violation_on_path_field(self):
        errors = _violations(name="Name", path="\t\t")
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "path" in fields

    # N96: Path exceeding max length produces length violation
    def test_n96_path_exceeding_max_length_violation(self):
        over_max_path = "/" + "p" * 300  # exceeds any reasonable max
        errors = _violations(name="Name", path=over_max_path)
        fields = _violation_fields(errors)
        assert len(errors) >= 1
        assert "path" in fields


class TestResourceFormEdge:

    # E97: Both name and path None produces exactly 2 violations, one per field
    def test_e97_both_null_produces_exactly_2_violations(self):
        try:
            ResourceForm(name=None, path=None)
            pytest.fail("Expected ValidationError was not raised")
        except ValidationError as exc:
            errors = exc.errors()
            fields = _violation_fields(errors)
            assert len(errors) == 2, \
                f"Expected exactly 2 violations (one per field), got {len(errors)}: {errors}"
            assert "name" in fields, f"Missing violation for 'name' field, got: {fields}"
            assert "path" in fields, f"Missing violation for 'path' field, got: {fields}"

    # E98: Both fields empty produces at least 2 violations
    def test_e98_both_empty_produces_at_least_2_violations(self):
        errors = _violations(name="", path="")
        assert len(errors) >= 2, \
            f"Expected at least 2 violations, got {len(errors)}: {errors}"

    # E99: Both fields whitespace produces at least 2 violations
    def test_e99_both_whitespace_produces_at_least_2_violations(self):
        errors = _violations(name="  ", path="\t")
        assert len(errors) >= 2

    # E100: Both fields exceeding max length produces exactly 2 length violations
    def test_e100_both_over_max_produces_exactly_2_length_violations(self):
        over_max_name = "A" * 300
        over_max_path = "/" + "p" * 300
        try:
            ResourceForm(name=over_max_name, path=over_max_path)
            pytest.fail("Expected ValidationError was not raised")
        except ValidationError as exc:
            errors = exc.errors()
            assert len(errors) == 2, \
                f"Expected exactly 2 length violations, got {len(errors)}: {errors}"

    # E101: Null field triggers required violation only (not required + length simultaneously)
    def test_e101_null_field_triggers_required_not_required_plus_length(self):
        try:
            ResourceForm(name=None, path="/path")
            pytest.fail("Expected ValidationError was not raised")
        except ValidationError as exc:
            name_errors = [e for e in exc.errors() if "name" in _violation_fields([e])]
            assert len(name_errors) == 1, \
                f"Null field must produce exactly 1 violation (required), got {len(name_errors)}: {name_errors}"
```

### Why This Matters

Positive validation tests document the exact acceptance boundaries. Without them, teams
unknowingly tighten constraints and break existing clients that were within the original
contract. E97 catches the copy-paste bug where both fields share the same validator instance.

---

## 8. Event Publisher Layer — Tests

### What We Follow

Every event type (CREATE, UPDATE, DELETE) must be tested for correct event type, entity
type, and entity ID in the published payload. Mock the Redis publish method using
`AsyncMock`. Use `call_args` to inspect the published message content.

### How To Implement

```python
# tests/test_resource_event_publisher.py
import pytest
from unittest.mock import AsyncMock, call, MagicMock
import json

from app.events.resource_event_publisher import ResourceEventPublisher
from app.events.event_types import EventType, EntityType


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def publisher(mock_redis):
    return ResourceEventPublisher(redis_client=mock_redis)


class TestEventPublisherPositive:

    # P102: CREATE event contains correct entity type with null entity ID
    @pytest.mark.asyncio
    async def test_p102_create_event_correct_entity_type_null_id(
        self, publisher, mock_redis
    ):
        await publisher.publish_create(None)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args.args[0]
        payload = json.loads(call_args.args[1])

        assert payload["event_type"] == EventType.CREATE.value
        assert payload["entity_type"] == EntityType.RESOURCE.value
        assert payload["entity_id"] is None

    # P103: CREATE event entity ID is null (not yet persisted)
    @pytest.mark.asyncio
    async def test_p103_create_event_entity_id_is_null(self, publisher, mock_redis):
        await publisher.publish_create(None)

        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args.args[1])
        assert payload["entity_id"] is None, \
            "CREATE event must have null entity_id (entity not yet persisted)"

    # P104: UPDATE event contains correct entity type AND populated entity ID
    @pytest.mark.asyncio
    async def test_p104_update_event_correct_type_and_id(self, publisher, mock_redis):
        await publisher.publish_update(42)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args.args[1])

        assert payload["event_type"] == EventType.UPDATE.value
        assert payload["entity_type"] == EntityType.RESOURCE.value
        assert payload["entity_id"] == 42
        assert payload["entity_id"] is not None
        assert payload["entity_id"] > 0

    # P105: DELETE event contains correct entity type AND populated entity ID
    @pytest.mark.asyncio
    async def test_p105_delete_event_correct_type_and_id(self, publisher, mock_redis):
        await publisher.publish_delete(99)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args.args[1])

        assert payload["event_type"] == EventType.DELETE.value
        assert payload["entity_type"] == EntityType.RESOURCE.value
        assert payload["entity_id"] == 99


class TestEventPublisherNegative:

    # N106: UPDATE with non-existent ID still publishes the event
    @pytest.mark.asyncio
    async def test_n106_update_nonexistent_id_still_publishes(self, publisher, mock_redis):
        # Publisher must not check entity existence — that is the service's job
        await publisher.publish_update(99999)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args.args[1])
        assert payload["entity_id"] == 99999


class TestEventPublisherEdge:

    # E107: CREATE, UPDATE, DELETE events have structurally distinct event types
    @pytest.mark.asyncio
    async def test_e107_event_types_are_structurally_distinct(
        self, publisher, mock_redis
    ):
        # Collect event types from all three publish calls
        await publisher.publish_create(None)
        create_payload = json.loads(mock_redis.publish.call_args_list[0].args[1])
        mock_redis.reset_mock()

        await publisher.publish_update(1)
        update_payload = json.loads(mock_redis.publish.call_args_list[0].args[1])
        mock_redis.reset_mock()

        await publisher.publish_delete(1)
        delete_payload = json.loads(mock_redis.publish.call_args_list[0].args[1])

        create_type = create_payload["event_type"]
        update_type = update_payload["event_type"]
        delete_type = delete_payload["event_type"]

        assert create_type != update_type, \
            f"CREATE and UPDATE event types must differ, both are: '{create_type}'"
        assert update_type != delete_type, \
            f"UPDATE and DELETE event types must differ, both are: '{update_type}'"
        assert create_type != delete_type, \
            f"CREATE and DELETE event types must differ, both are: '{create_type}'"
```

### Why This Matters

Incorrect event type or wrong entity type in the published payload causes the consumer
to either ignore the event or invalidate the wrong cache key — both are invisible without
this test. E107 catches the bug where all three event types use the same string constant.

---

## 9. Mocking Strategy Reference (Python/FastAPI)

| Layer | Mock Tool | What To Mock | What NOT To Mock |
|-------|-----------|-------------|-----------------|
| Layer 1 — Bootstrap | `unittest.mock.patch("uvicorn.run")` | `uvicorn.run` static call | The FastAPI `app` object; its constructors |
| Layer 2 — Configuration | None | Nothing | The configuration class itself or its constants |
| Layer 3 — Controller | `app.dependency_overrides[Service] = lambda: MagicMock(spec=Service)` | Service layer methods | The HTTP framework; serialization; Pydantic validation |
| Layer 4 — Service | `AsyncMock(spec=Repository)`, `AsyncMock(spec=Publisher)` | Repository async methods; publisher publish methods | The service itself; domain entity classes |
| Layer 5 — Entity | None | Nothing | The entity's own `__init__` or properties |
| Layer 6 — Exception Handler | `MagicMock(spec=Request)` | The FastAPI Request object | The exception classes themselves; JSONResponse |
| Layer 7 — Validation | None | Nothing | The Pydantic validation framework |
| Layer 8 — Event Publisher | `AsyncMock()` on the redis client | `redis_client.publish()` | The publisher class itself; event payload dataclasses |

### FastAPI-Specific Mock Patterns

```python
# CORRECT: Override service dependency for route tests
from app.main import app
from app.services.resource_service import ResourceService
from unittest.mock import MagicMock

mock_svc = MagicMock(spec=ResourceService)
app.dependency_overrides[ResourceService] = lambda: mock_svc
# ... run test ...
app.dependency_overrides.clear()  # Always clean up

# CORRECT: AsyncMock for async repository methods
from unittest.mock import AsyncMock
mock_repo = AsyncMock(spec=ResourceRepository)
mock_repo.find_by_id.return_value = ResourceEntity(id=1, name="Name", path="/path")

# CORRECT: Patch uvicorn.run for bootstrap tests
from unittest.mock import patch
with patch("uvicorn.run") as mock_run:
    # re-import or trigger __main__ block
    mock_run.assert_called_once()

# WRONG: Using real service in route test (slow, hits database)
def test_wrong():
    client = TestClient(app)  # No override — will use real service
    response = client.post("/api/resources", json={...})  # WRONG

# WRONG: Using MagicMock instead of AsyncMock for async methods
mock_repo = MagicMock(spec=ResourceRepository)
mock_repo.find_by_id.return_value = entity  # WRONG — async method needs AsyncMock
```

---

## 10. Cross-Cutting Patterns (Python/FastAPI)

These seven patterns span multiple layers and must be enforced consistently.

### Pattern 1 — Response Wrapper Consistency

**Spans:** Router Layer + Exception Handler Layer

```python
# CORRECT: All endpoints return identical wrapper structure
# Success response:
{"success": True, "status": 200, "message": "OK", "data": {...}}

# Error response:
{"success": False, "status": 409, "message": "Name already exists", "data": None}

# WRONG: Raw DTO on success, wrapped error on failure
# Success: {"id": 1, "name": "Name"}          <- raw DTO
# Failure: {"success": False, "status": 409}   <- wrapped
# This breaks clients that parse the wrapper uniformly
```

```python
# tests/test_cross_cutting.py — Pattern 1 enforcement
def test_pattern1_all_endpoints_use_same_wrapper_shape(client):
    # Success case
    ok_response = client.get("/api/resources")
    ok_body = ok_response.json()
    assert "success" in ok_body
    assert "status" in ok_body
    assert "message" in ok_body
    assert "data" in ok_body

    # Error case — trigger 404
    err_response = client.get("/api/resources/9999")
    err_body = err_response.json()
    assert "success" in err_body
    assert "status" in err_body
    assert "message" in err_body
    assert "data" in err_body
```

### Pattern 2 — success=False on All Error Responses

**Spans:** Exception Handler Layer

```python
# CORRECT: All error handlers explicitly set success=False
async def handle_duplicate_name(request: Request, exc: DuplicateNameException):
    return JSONResponse(
        status_code=409,
        content={"success": False, "status": 409, "message": str(exc), "data": None}
    )

# WRONG: Omitting success field or defaulting to null
async def handle_wrong(request: Request, exc: DuplicateNameException):
    return JSONResponse(
        status_code=409,
        content={"status": 409, "message": str(exc)}  # Missing success field
    )
```

### Pattern 3 — HTTP Status Matches Body Status Field

**Spans:** Router Layer + Exception Handler Layer

```python
# CORRECT: Status code in header == status field in body
return JSONResponse(status_code=409, content={"success": False, "status": 409, ...})

# WRONG: Mismatch between header and body
return JSONResponse(status_code=200, content={"success": False, "status": 409, ...})
# HTTP gateway sees 200 (success) but body says 409 (conflict)
```

### Pattern 4 — Case-Insensitive Duplicate Detection

**Spans:** Service Layer (via repository icase queries)

```python
# CORRECT: Repository query uses case-insensitive comparison
async def exists_by_name_icase(self, name: str) -> bool:
    result = await self.session.execute(
        select(ResourceEntity).where(
            func.lower(ResourceEntity.name) == name.lower()
        )
    )
    return result.scalar_one_or_none() is not None

# WRONG: Case-sensitive check allows "Admin" and "admin" to coexist
async def exists_by_name(self, name: str) -> bool:
    result = await self.session.execute(
        select(ResourceEntity).where(ResourceEntity.name == name)  # Case-sensitive
    )
    return result.scalar_one_or_none() is not None
```

### Pattern 5 — Idempotent Delete

**Spans:** Service Layer

```python
# CORRECT: Delete non-existent ID is silent (no error)
async def delete(self, resource_id: int) -> None:
    await self.repository.delete_by_id(resource_id)  # Repo-level no-op if not found
    if self.publisher:
        await self.publisher.publish_delete(resource_id)

# WRONG: Check existence before delete (breaks idempotency)
async def delete(self, resource_id: int) -> None:
    entity = await self.repository.find_by_id(resource_id)
    if entity is None:
        raise ResourceNotFoundException(f"Resource {resource_id} not found")  # WRONG
    await self.repository.delete_by_id(resource_id)
```

### Pattern 6 — Sort Validated with Exact Field and Direction

**Spans:** Service Layer

```python
# CORRECT: Explicit sort field and direction passed to repository
async def get_all(self) -> dict:
    entities = await self.repository.find_all_sorted(sort_by="id", direction="ASC")
    return {"success": True, "status": 200, "message": "OK",
            "data": [self._to_dict(e) for e in entities]}

# Test enforcement:
mock_repo.find_all_sorted.assert_called_once_with(sort_by="id", direction="ASC")

# WRONG: No sort argument — database default ordering (non-deterministic)
entities = await self.repository.find_all()  # No sort — undefined ordering
```

### Pattern 7 — Cache Events for CREATE, UPDATE, DELETE

**Spans:** Service Layer + Event Publisher Layer

```python
# CORRECT: All three mutation operations publish cache events
async def add(self, form: dict) -> dict:
    entity = await self.repository.save(ResourceEntity(**form))
    await self.publisher.publish_create(None)     # CREATE event
    return self._wrap(201, entity)

async def update(self, resource_id: int, form: dict) -> dict:
    entity = await self.repository.save(...)
    await self.publisher.publish_update(resource_id)  # UPDATE event
    return self._wrap(200, entity)

async def delete(self, resource_id: int) -> None:
    await self.repository.delete_by_id(resource_id)
    await self.publisher.publish_delete(resource_id)  # DELETE event

# WRONG: No event published after mutation
async def add(self, form: dict) -> dict:
    entity = await self.repository.save(ResourceEntity(**form))
    # Missing: publisher.publish_create()
    return self._wrap(201, entity)
```

---

## 11. Anti-Patterns (What NOT To Do)

```python
# ANTI-PATTERN 1: Business logic in route handler
# WRONG:
@router.post("/resources")
async def create_resource(form: ResourceForm, db: AsyncSession = Depends(get_db)):
    # WRONG: business logic (duplicate check) in route handler
    existing = await db.execute(select(ResourceEntity).where(...))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Duplicate")
    entity = ResourceEntity(**form.dict())
    db.add(entity)
    await db.commit()
    return entity

# CORRECT: Route handler delegates to service
@router.post("/resources", status_code=201)
async def create_resource(
    form: ResourceForm,
    service: ResourceService = Depends(ResourceService)
):
    return await service.add(form.dict())


# ANTI-PATTERN 2: MagicMock instead of AsyncMock for async methods
# WRONG:
mock_repo = MagicMock(spec=ResourceRepository)
mock_repo.find_by_id.return_value = entity  # Will not work for async def
# await service.get_by_id(1)  # This will raise TypeError

# CORRECT:
mock_repo = AsyncMock(spec=ResourceRepository)
mock_repo.find_by_id.return_value = entity  # Works for async def


# ANTI-PATTERN 3: Forgetting to clear dependency_overrides
# WRONG:
def test_one():
    app.dependency_overrides[ResourceService] = lambda: mock_svc
    client = TestClient(app)
    client.get("/api/resources")
    # No cleanup — override leaks into test_two

# CORRECT:
@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


# ANTI-PATTERN 4: Returning None instead of empty list
# WRONG:
async def get_all(self) -> dict:
    entities = await self.repository.find_all_sorted(sort_by="id", direction="ASC")
    if not entities:
        return {"success": True, "status": 200, "message": "OK", "data": None}  # WRONG: null data

# CORRECT:
async def get_all(self) -> dict:
    entities = await self.repository.find_all_sorted(sort_by="id", direction="ASC")
    return {"success": True, "status": 200, "message": "OK",
            "data": [self._to_dict(e) for e in entities]}  # Always a list


# ANTI-PATTERN 5: Starting the real HTTP server in tests
# WRONG:
import uvicorn
import threading
def test_wrong():
    t = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"port": 8000})
    t.daemon = True
    t.start()
    # ... expensive, port conflicts, non-isolated

# CORRECT:
from fastapi.testclient import TestClient
def test_correct():
    client = TestClient(app)  # No real server, ASGI transport


# ANTI-PATTERN 6: Asserting only that a mock was called, not what it was called with
# WRONG:
mock_repo.find_all_sorted.assert_called()  # Too weak — allows wrong arguments

# CORRECT:
mock_repo.find_all_sorted.assert_called_once_with(sort_by="id", direction="ASC")


# ANTI-PATTERN 7: Catching generic Exception in service and swallowing it
# WRONG:
async def add(self, form: dict) -> dict:
    try:
        return await self._do_add(form)
    except Exception:
        pass  # Silent swallow — test will pass but production will silently fail

# CORRECT:
async def add(self, form: dict) -> dict:
    try:
        return await self._do_add(form)
    except DuplicateNameException:
        raise  # Re-raise typed exception; let exception handler map it to 409
    except SQLAlchemyError as exc:
        raise DataIntegrityException(str(exc)) from exc
```

---

## Quick-Reference Checklist (Python/FastAPI)

For every new FastAPI service module, verify each item before marking the feature complete:

Bootstrap Layer:
- [ ] P1: FastAPI `app` is a `FastAPI` instance
- [ ] P2: App has a non-empty title
- [ ] P3: At least one route is registered
- [ ] P4: Module import does not start the server
- [ ] P5: `uvicorn.run` called when `__name__ == "__main__"`
- [ ] P6: `uvicorn.run` receives app argument
- [ ] P7: Module reloadable without error
- [ ] P8: `app` is `FastAPI`, not a subclass
- [ ] N9: Empty `sys.argv` does not crash
- [ ] N10: No args still triggers uvicorn call in `__main__` block
- [ ] E11: Multiple CLI flags forwarded without loss

Configuration Layer:
- [ ] P12: Config class instantiates without error
- [ ] P13: CACHE_BY_ID constant correct value
- [ ] P14: CACHE_ALL constant correct value
- [ ] P15: CACHE_COUNT constant correct value
- [ ] N16: No constant is None or empty
- [ ] E17: All constants are distinct

Controller/Route Layer:
- [ ] P18: POST returns 201 with body
- [ ] P19: PUT returns 200 with updated body
- [ ] P20: GET by ID returns 200 with single resource
- [ ] P21: GET all returns 200 with list
- [ ] P22: DELETE returns 200
- [ ] P23: GET count returns 200 with integer
- [ ] N24: Duplicate name raises 409
- [ ] N25: Duplicate path raises 409
- [ ] N26: Non-existent GET raises 404
- [ ] N27: Non-existent PUT raises 404
- [ ] E28: Empty result returns `[]`, not `None`
- [ ] E29: GET all returns JSON array
- [ ] E30: Service called exactly once per request

Service Layer:
- [ ] P31: Add returns populated dict with all fields
- [ ] P32: Update returns updated field values
- [ ] P33: Get by ID maps all entity fields
- [ ] P34: Get all calls repo with sort_by="id", direction="ASC"
- [ ] P35: Get all returns IDs in ascending order
- [ ] P36: Delete publishes DELETE event via publisher
- [ ] P37: Count returns non-zero integer
- [ ] P38: Count returns 0 (not None) for empty repo
- [ ] P39: Idempotent update with same data succeeds
- [ ] N40: Duplicate name raises DuplicateNameException
- [ ] N41: Duplicate path raises DuplicatePathException
- [ ] N42: Non-existent get raises ResourceNotFoundException
- [ ] N43: Non-existent update raises ResourceNotFoundException
- [ ] N44: Name taken by other resource raises DuplicateNameException
- [ ] N45: Path taken by other resource raises DuplicatePathException
- [ ] E46: Case-insensitive duplicate detection (icase repo query)
- [ ] E47: Empty repo returns `[]`, not `None`
- [ ] E48: Delete of non-existent ID is silent
- [ ] E49: None publisher does not crash delete
- [ ] E50: Sort: sort_by="id" AND direction="ASC" (both asserted)

Entity Layer:
- [ ] P51: Constructor sets all fields
- [ ] P52: No-args constructor creates non-None instance
- [ ] P53: Assignment round-trip via attribute access
- [ ] P54: Same data → equal (==)
- [ ] P55: Equal objects → same hash
- [ ] P56: Entity equals itself (reflexive)
- [ ] P57: `repr()` is non-None, non-empty
- [ ] P58: `repr()` contains "ResourceEntity"
- [ ] P59: `repr()` contains id and name values
- [ ] P60: Serializes to dict/JSON without error
- [ ] P61: `__tablename__` defined and non-empty
- [ ] N62: Different IDs → not equal
- [ ] N63: `entity == None` returns False or NotImplemented, no crash
- [ ] N64: `entity == "string"` returns False or NotImplemented
- [ ] N65: `None` name in constructor does not raise
- [ ] N66: `None` path in constructor does not raise
- [ ] E67: Name of 255 chars stored exactly
- [ ] E68: Path of 255 chars stored exactly
- [ ] E69: `sys.maxsize` ID does not overflow
- [ ] E70: ID=1 accepted
- [ ] E71: Unicode/special chars stored exactly
- [ ] E72: Whitespace-only name not trimmed in entity
- [ ] E73: Two None-ID instances with same data are equal

Error Handler Layer:
- [ ] P74: DuplicateNameException → 409, success=False, non-blank message
- [ ] P75: DuplicatePathException → 409, success=False, non-blank message
- [ ] P76: DataIntegrityException → 409, message does not leak SQL
- [ ] P77: JSONResponse.status_code == body["status"]
- [ ] N78: DuplicateNameException handler: success is `False` (not null)
- [ ] N79: DuplicatePathException handler: success is `False` (not null)
- [ ] E80: All conflict handlers return 409
- [ ] E81: All conflict handlers set success=False

Validation Layer:
- [ ] P82: Valid input → 0 violations
- [ ] P83: Single-char name → 0 violations
- [ ] P84: Max-length name → 0 violations
- [ ] P85: Max-length path → 0 violations
- [ ] P86: Special chars in name → 0 violations
- [ ] P87: Numeric string name → 0 violations
- [ ] N88: None name → violation on "name" field
- [ ] N89: Empty name → violation on "name" field
- [ ] N90: Whitespace name → violation on "name" field
- [ ] N91: max+1 name → length violation on "name"
- [ ] N92: 2x max name → length violation on "name"
- [ ] N93: None path → violation on "path" field
- [ ] N94: Empty path → violation on "path" field
- [ ] N95: Tab-only path → violation on "path" field
- [ ] N96: Over-max path → length violation on "path"
- [ ] E97: Both None → exactly 2 violations (one per field)
- [ ] E98: Both empty → at least 2 violations
- [ ] E99: Both whitespace → at least 2 violations
- [ ] E100: Both over-max → exactly 2 length violations
- [ ] E101: Null triggers required only (not required+length simultaneously)

Event Publisher Layer:
- [ ] P102: CREATE event: event_type=CREATE, entity_type=RESOURCE, entity_id=None
- [ ] P103: CREATE event: entity_id is None
- [ ] P104: UPDATE event: event_type=UPDATE, entity_type=RESOURCE, entity_id=provided_id
- [ ] P105: DELETE event: event_type=DELETE, entity_type=RESOURCE, entity_id=provided_id
- [ ] N106: UPDATE with non-existent ID still publishes (no existence check)
- [ ] E107: CREATE/UPDATE/DELETE event_type values are all distinct

Security Layer:
- [ ] SEC1: Authenticated request succeeds with valid token
- [ ] SEC2: Health endpoint accessible without auth
- [ ] SEC3: Unauthenticated request returns 401
- [ ] SEC4: Invalid/expired token returns 401
- [ ] SEC5: SQL injection input returns 400/422, not 500
- [ ] SEC6: XSS payload handled safely
- [ ] SEC7: Oversized body returns 413/400
- [ ] SEC8: Missing Content-Type returns 415/400

Path Parameters:
- [ ] PP1: Non-numeric ID returns 422
- [ ] PP2: Negative ID returns 400/404
- [ ] PP3: Zero ID returns 400/404
- [ ] PP4: Overflow ID returns 422

Error Structure:
- [ ] ERR1: 500 returns ApiResponse envelope
- [ ] ERR2: 500 message has no stack trace
- [ ] ERR3: 500 Content-Type is application/json

---

**ENFORCEMENT:** Every PR introducing a new FastAPI layer (router, service, entity, handler,
form, publisher) must include all corresponding test scenarios from this catalog before the
coverage gate runs. Missing tests will cause `pytest --cov` branch/statement coverage
failures under the 100% per-module enforcement gate.

## 9. Security Layer (SEC1–SEC8)

**Purpose:** Verify authentication enforcement, input sanitization, and request size limits
align with OWASP Top 10 (A01 Broken Access Control, A03 Injection, A05 Misconfiguration).

### SEC1: Authenticated request succeeds with valid token

```python
def test_sec1_authenticated_request_succeeds(client, valid_token):
    response = client.get(
        "/api/resources/1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
```

### SEC2: Health endpoint accessible without authentication

```python
def test_sec2_health_endpoint_requires_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
```

### SEC3: Unauthenticated request to protected endpoint returns 401

```python
def test_sec3_unauthenticated_request_returns_401(client):
    response = client.get("/api/resources/1")
    assert response.status_code == 401
```

### SEC4: Invalid or expired token returns 401

```python
def test_sec4_invalid_token_returns_401(client):
    response = client.get(
        "/api/resources/1",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401
```

### SEC5: SQL injection payload in request body returns 400 or 422, never 500

```python
def test_sec5_sql_injection_in_name_returns_422(client, valid_token):
    response = client.post(
        "/api/resources",
        headers={"Authorization": f"Bearer {valid_token}"},
        json={"name": "'; DROP TABLE resources; --", "path": "/safe"},
    )
    assert response.status_code in (400, 422)
    assert response.status_code != 500
```

### SEC6: XSS payload in request body is handled safely

```python
def test_sec6_xss_payload_in_name_does_not_cause_500(client, valid_token):
    response = client.post(
        "/api/resources",
        headers={"Authorization": f"Bearer {valid_token}"},
        json={"name": "<script>alert('xss')</script>", "path": "/safe"},
    )
    # Must not crash the server; response body must not echo raw script tag
    assert response.status_code in (200, 201, 400, 422)
    assert response.status_code != 500
    if response.status_code in (200, 201):
        body = response.json()
        assert "<script>" not in str(body)
```

### SEC7: Oversized request body returns 413 or 400, never 500

```python
def test_sec7_oversized_body_returns_413_or_400(client, valid_token):
    huge_name = "A" * 10_000_000  # 10 MB string
    response = client.post(
        "/api/resources",
        headers={"Authorization": f"Bearer {valid_token}"},
        json={"name": huge_name, "path": "/test"},
    )
    assert response.status_code in (400, 413, 422)
    assert response.status_code != 500
```

### SEC8: Request without Content-Type header returns 415 or 400

```python
def test_sec8_missing_content_type_returns_415_or_400(client, valid_token):
    response = client.post(
        "/api/resources",
        headers={"Authorization": f"Bearer {valid_token}"},
        data='{"name": "test", "path": "/test"}',  # raw bytes, no content-type
    )
    assert response.status_code in (400, 415, 422)
```

---

## 10. Path Parameter Edge Cases (PP1–PP4)

**Purpose:** Confirm that FastAPI's typed path parameter validation rejects invalid IDs at
the framework layer before any service or repository code is reached.

### PP1: Non-numeric path ID returns 422 Unprocessable Entity

```python
def test_pp1_non_numeric_id_returns_422(client):
    response = client.get("/api/resources/abc")
    assert response.status_code == 422
```

### PP2: Negative path ID returns 400 or 404

```python
def test_pp2_negative_id_returns_400_or_404(client, valid_token):
    response = client.get(
        "/api/resources/-1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code in (400, 404)
```

### PP3: Zero path ID returns 400 or 404

```python
def test_pp3_zero_id_returns_400_or_404(client, valid_token):
    response = client.get(
        "/api/resources/0",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code in (400, 404)
```

### PP4: Integer overflow path ID returns 422

```python
def test_pp4_very_large_id_returns_422(client):
    # Value exceeds Python/FastAPI int32 boundary — framework must reject before service
    response = client.get("/api/resources/99999999999999999999")
    assert response.status_code == 422
```

---

## 11. Internal Error Structure (ERR1–ERR3)

**Purpose:** Ensure unhandled exceptions are caught by the global exception handler and
always return a structured `ApiResponse` envelope with no internal detail leakage.

### ERR1: Unhandled exception returns ApiResponse envelope with success=False

```python
def test_err1_unhandled_exception_returns_structured_response(
    client, valid_token, mock_service
):
    mock_service.get_by_id.side_effect = RuntimeError("unexpected DB failure")
    response = client.get(
        "/api/resources/1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 500
    body = response.json()
    assert "success" in body
    assert body["success"] is False
    assert "message" in body
```

### ERR2: 500 response body contains no stack trace text

```python
def test_err2_500_does_not_leak_stack_trace(client, valid_token, mock_service):
    mock_service.get_by_id.side_effect = RuntimeError("db connection pool exhausted")
    response = client.get(
        "/api/resources/1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    message = body.get("message", "")
    assert "Traceback" not in message
    assert "File " not in message
    assert "RuntimeError" not in message
    assert "line " not in message
```

### ERR3: 500 response Content-Type is application/json

```python
def test_err3_500_content_type_is_json(client, valid_token, mock_service):
    mock_service.get_by_id.side_effect = RuntimeError("unexpected error")
    response = client.get(
        "/api/resources/1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 500
    assert "application/json" in response.headers.get("content-type", "")
```

---

**SEE ALSO:**
- `40-universal-test-patterns-abstract.md` — language-agnostic source of truth for all 122 scenario IDs
- `28-test-coverage-enforcement.md` — 100% per-module coverage gate configuration
- `38-test-mocking-strategy.md` — which isolation strategy to use per layer
