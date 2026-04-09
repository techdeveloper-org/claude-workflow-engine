---
description: "Level 2.3 - Go testing standards: 122 scenarios across 8 layers + security/path/error-structure extensions (positive/negative/edge)"
paths:
  - "**/*_test.go"
priority: high
conditional: "Go project detected (go.mod present)"
---

# Testing Standards — Go (Level 2.3)

**PURPOSE:** Define the mandatory test scenarios for every Go REST service layer. This file
is the Go implementation of the universal patterns defined in `40-universal-test-patterns-abstract.md`.
Every scenario ID (P1–P105, N9–N106, E11–E107, SEC1–SEC8, PP1–PP4, ERR1–ERR3) maps 1:1 to the abstract catalog.
Missing any scenario causes a gap in observable contract coverage.

**APPLIES WHEN:** Go REST service with standard library HTTP handlers or any Go HTTP framework
(chi, gorilla/mux, gin). The patterns apply to any Handler → Service → Repository layered
architecture backed by a relational or document database and an event/cache publisher.

---

## Technology Stack

- Language: Go 1.21+
- HTTP: `net/http` stdlib (primary); chi / gorilla/mux / gin as alternatives where noted
- Test runner: `testing` stdlib
- Mocking: `github.com/stretchr/testify/mock` (primary); `github.com/golang/mock/gomock` (secondary)
- HTTP recording: `net/http/httptest`
- Assertions: `github.com/stretchr/testify/assert` + `github.com/stretchr/testify/require`
- Validation: `github.com/go-playground/validator/v10`
- ORM: GORM (primary); sqlx (secondary)
- Cache events: `github.com/redis/go-redis/v9`

---

## Mock Interface Reference

All tests in this file assume the following interface and mock types are defined in a
`mocks/` package or alongside the production code:

```go
// mocks/mock_resource_service.go
package mocks

import (
    "context"
    "github.com/stretchr/testify/mock"
)

// ResourceService is the interface under test at the handler layer.
type ResourceService interface {
    Add(ctx context.Context, form ResourceForm) (*ResourceDTO, error)
    Update(ctx context.Context, id int64, form ResourceForm) (*ResourceDTO, error)
    GetByID(ctx context.Context, id int64) (*ResourceDTO, error)
    GetAll(ctx context.Context) ([]ResourceDTO, error)
    Delete(ctx context.Context, id int64) error
    GetCount(ctx context.Context) (int64, error)
}

// MockResourceService satisfies ResourceService using testify/mock.
type MockResourceService struct {
    mock.Mock
}

func (m *MockResourceService) Add(ctx context.Context, form ResourceForm) (*ResourceDTO, error) {
    args := m.Called(ctx, form)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*ResourceDTO), args.Error(1)
}

func (m *MockResourceService) Update(ctx context.Context, id int64, form ResourceForm) (*ResourceDTO, error) {
    args := m.Called(ctx, id, form)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*ResourceDTO), args.Error(1)
}

func (m *MockResourceService) GetByID(ctx context.Context, id int64) (*ResourceDTO, error) {
    args := m.Called(ctx, id)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*ResourceDTO), args.Error(1)
}

func (m *MockResourceService) GetAll(ctx context.Context) ([]ResourceDTO, error) {
    args := m.Called(ctx)
    return args.Get(0).([]ResourceDTO), args.Error(1)
}

func (m *MockResourceService) Delete(ctx context.Context, id int64) error {
    args := m.Called(ctx, id)
    return args.Error(0)
}

func (m *MockResourceService) GetCount(ctx context.Context) (int64, error) {
    args := m.Called(ctx)
    return args.Get(0).(int64), args.Error(1)
}

// ResourceRepository is the interface mocked at the service layer.
type ResourceRepository interface {
    Save(ctx context.Context, entity *ResourceEntity) (*ResourceEntity, error)
    FindByID(ctx context.Context, id int64) (*ResourceEntity, error)
    FindAll(ctx context.Context, opts QueryOptions) ([]ResourceEntity, error)
    DeleteByID(ctx context.Context, id int64) error
    Count(ctx context.Context) (int64, error)
    ExistsByNameILike(ctx context.Context, name string) (bool, error)
    ExistsByPathILike(ctx context.Context, path string) (bool, error)
    ExistsByNameILikeAndIDNot(ctx context.Context, name string, id int64) (bool, error)
    ExistsByPathILikeAndIDNot(ctx context.Context, path string, id int64) (bool, error)
}

// MockResourceRepository satisfies ResourceRepository.
type MockResourceRepository struct {
    mock.Mock
}

func (m *MockResourceRepository) Save(ctx context.Context, entity *ResourceEntity) (*ResourceEntity, error) {
    args := m.Called(ctx, entity)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*ResourceEntity), args.Error(1)
}

func (m *MockResourceRepository) FindByID(ctx context.Context, id int64) (*ResourceEntity, error) {
    args := m.Called(ctx, id)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*ResourceEntity), args.Error(1)
}

func (m *MockResourceRepository) FindAll(ctx context.Context, opts QueryOptions) ([]ResourceEntity, error) {
    args := m.Called(ctx, opts)
    return args.Get(0).([]ResourceEntity), args.Error(1)
}

func (m *MockResourceRepository) DeleteByID(ctx context.Context, id int64) error {
    return m.Called(ctx, id).Error(0)
}

func (m *MockResourceRepository) Count(ctx context.Context) (int64, error) {
    args := m.Called(ctx)
    return args.Get(0).(int64), args.Error(1)
}

func (m *MockResourceRepository) ExistsByNameILike(ctx context.Context, name string) (bool, error) {
    args := m.Called(ctx, name)
    return args.Bool(0), args.Error(1)
}

func (m *MockResourceRepository) ExistsByPathILike(ctx context.Context, path string) (bool, error) {
    args := m.Called(ctx, path)
    return args.Bool(0), args.Error(1)
}

func (m *MockResourceRepository) ExistsByNameILikeAndIDNot(ctx context.Context, name string, id int64) (bool, error) {
    args := m.Called(ctx, name, id)
    return args.Bool(0), args.Error(1)
}

func (m *MockResourceRepository) ExistsByPathILikeAndIDNot(ctx context.Context, path string, id int64) (bool, error) {
    args := m.Called(ctx, path, id)
    return args.Bool(0), args.Error(1)
}

// CachePublisher is the interface mocked at the service layer.
type CachePublisher interface {
    PublishCreate(ctx context.Context, entityID int64) error
    PublishUpdate(ctx context.Context, entityID int64) error
    PublishDelete(ctx context.Context, entityID int64) error
}

// MockCachePublisher satisfies CachePublisher.
type MockCachePublisher struct {
    mock.Mock
}

func (m *MockCachePublisher) PublishCreate(ctx context.Context, entityID int64) error {
    return m.Called(ctx, entityID).Error(0)
}

func (m *MockCachePublisher) PublishUpdate(ctx context.Context, entityID int64) error {
    return m.Called(ctx, entityID).Error(0)
}

func (m *MockCachePublisher) PublishDelete(ctx context.Context, entityID int64) error {
    return m.Called(ctx, entityID).Error(0)
}
```

---

## Helper Functions

```go
// testhelpers/helpers.go
package testhelpers

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"

    "github.com/go-playground/validator/v10"
    "github.com/stretchr/testify/require"
)

// NewJSONRequest creates a POST/PUT/PATCH request with a JSON body.
func NewJSONRequest(t *testing.T, method, path, body string) *http.Request {
    t.Helper()
    req := httptest.NewRequest(method, path, strings.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    return req
}

// DecodeBody decodes the recorder body into v.
func DecodeBody[T any](t *testing.T, rec *httptest.ResponseRecorder) T {
    t.Helper()
    var v T
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&v))
    return v
}

// ContainsFieldError returns true if the validator.ValidationErrors slice
// has an entry for the given field and tag.
func ContainsFieldError(errs validator.ValidationErrors, field, tag string) bool {
    for _, e := range errs {
        if e.Field() == field && e.Tag() == tag {
            return true
        }
    }
    return false
}
```

---

## Domain Types Reference

```go
// types.go  (shared across test files)
package resource

import "time"

// ResourceEntity is the persistence model.
type ResourceEntity struct {
    ID        int64     `json:"id"         gorm:"primaryKey;autoIncrement"`
    Name      string    `json:"name"       gorm:"uniqueIndex;not null"`
    Path      string    `json:"path"       gorm:"uniqueIndex;not null"`
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
}

// ResourceDTO is the API-facing data transfer object.
type ResourceDTO struct {
    ID   int64  `json:"id"`
    Name string `json:"name"`
    Path string `json:"path"`
}

// ResourceForm is the inbound create/update payload.
type ResourceForm struct {
    Name string `json:"name" validate:"required,min=1,max=50"`
    Path string `json:"path" validate:"required,min=1,max=50"`
}

// QueryOptions carries sort and filter parameters to the repository.
type QueryOptions struct {
    SortField string
    SortDir   string
}

// ApiResponse is the standard response envelope.
type ApiResponse[T any] struct {
    Success bool   `json:"success"`
    Status  int    `json:"status"`
    Message string `json:"message"`
    Data    T      `json:"data,omitempty"`
}

// CacheEvent is the Redis-published payload.
type CacheEvent struct {
    EventType  string `json:"event_type"`  // "CREATE" | "UPDATE" | "DELETE"
    EntityType string `json:"entity_type"` // e.g. "RESOURCE"
    EntityID   int64  `json:"entity_id"`
}

// Sentinel errors
var (
    ErrDuplicateResource = errors.New("duplicate resource")
    ErrDuplicatePath     = errors.New("duplicate path")
    ErrNotFound          = errors.New("resource not found")
)
```

---

## 1. Bootstrap Layer (P1–P8, N9–N10, E11)

Go apps have a `func main()` entry-point, `http.ListenAndServe()` (or framework equivalent),
router registration, and middleware chaining.

### What We Follow

Test that the server constructor wires up all required middleware, that `main()` correctly
delegates to the listener function, and that the server tolerates null/empty argument states.
Use a function-variable indirection (`listenAndServe var`) to intercept the real listener
without binding a port.

### How To Implement

```go
// bootstrap_test.go
package main_test

import (
    "net/http"
    "os"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

// P1: Server creates correctly with all required middleware registered.
func TestNewServer_HasRequiredMiddleware(t *testing.T) {
    srv := NewServer(Config{Port: 8080})
    assert.NotNil(t, srv, "server must not be nil")
    assert.NotNil(t, srv.Router, "router must be registered")
    assert.NotNil(t, srv.Middleware, "middleware chain must be initialised")
}

// P2: Router registers the /api/v1/resources path.
func TestNewServer_RegistersResourceRoute(t *testing.T) {
    srv := NewServer(Config{Port: 8080})
    routes := srv.Routes()
    assert.Contains(t, routes, "/api/v1/resources",
        "resource route must be registered on startup")
}

// P3: Logging middleware is present in the chain.
func TestNewServer_LoggingMiddlewarePresent(t *testing.T) {
    srv := NewServer(Config{Port: 8080})
    assert.True(t, srv.HasMiddleware("logging"),
        "logging middleware must be present")
}

// P4: Recovery (panic) middleware is present.
func TestNewServer_RecoveryMiddlewarePresent(t *testing.T) {
    srv := NewServer(Config{Port: 8080})
    assert.True(t, srv.HasMiddleware("recovery"),
        "recovery middleware must be present")
}

// P5: main() delegates to listenAndServe with the configured address.
// Override the function variable to avoid actually binding a port.
func TestMain_DelegatesToListenAndServe(t *testing.T) {
    var capturedAddr string
    original := listenAndServe
    listenAndServe = func(addr string, handler http.Handler) error {
        capturedAddr = addr
        return nil
    }
    defer func() { listenAndServe = original }()

    main()

    assert.Equal(t, ":8080", capturedAddr,
        "main() must delegate to :8080 by default")
}

// P6: main() forwards the configured handler (not nil).
func TestMain_ForwardsNonNilHandler(t *testing.T) {
    var capturedHandler http.Handler
    original := listenAndServe
    listenAndServe = func(addr string, handler http.Handler) error {
        capturedHandler = handler
        return nil
    }
    defer func() { listenAndServe = original }()

    main()

    assert.NotNil(t, capturedHandler,
        "main() must pass a non-nil handler to the listener")
}

// P7: PORT env var overrides the default listen address.
func TestMain_RespectsPortEnvVar(t *testing.T) {
    t.Setenv("PORT", "9090")

    var capturedAddr string
    original := listenAndServe
    listenAndServe = func(addr string, handler http.Handler) error {
        capturedAddr = addr
        return nil
    }
    defer func() { listenAndServe = original }()

    main()

    assert.Equal(t, ":9090", capturedAddr)
}

// P8: Server with full config (port + timeout) creates without error.
func TestNewServer_FullConfig_NoError(t *testing.T) {
    cfg := Config{Port: 8080, ReadTimeout: 30, WriteTimeout: 30}
    srv := NewServer(cfg)
    assert.NotNil(t, srv)
}

// N9: Server starts with missing optional env var — no panic, no error.
func TestNewServer_MissingOptionalEnvVar_NoError(t *testing.T) {
    os.Unsetenv("OPTIONAL_FEATURE_FLAG")
    srv := NewServer(Config{Port: 8080})
    assert.NotNil(t, srv,
        "missing optional env var must not prevent server construction")
}

// N10: main() with listenAndServe returning an error does not panic.
func TestMain_ListenerError_DoesNotPanic(t *testing.T) {
    original := listenAndServe
    listenAndServe = func(addr string, handler http.Handler) error {
        return errors.New("bind: address already in use")
    }
    defer func() { listenAndServe = original }()

    assert.NotPanics(t, func() { main() })
}

// E11: All middleware names in the chain are distinct — no duplicates.
func TestNewServer_AllMiddlewareNamesDistinct(t *testing.T) {
    srv := NewServer(Config{Port: 8080})
    names := srv.MiddlewareNames()
    seen := make(map[string]bool)
    for _, n := range names {
        assert.False(t, seen[n], "middleware %q registered more than once", n)
        seen[n] = true
    }
}
```

### Why This Matters
Go `main()` and the listener setup cannot be tested once a real port is bound.
Function-variable indirection is the idiomatic Go pattern for making entry-point code
testable without starting a real server process.

---

## 2. Configuration Layer (P12–P15, N16, E17)

### What We Follow

Constants must hold the exact string values the rest of the system expects, because they
drive cache key lookups and topic routing. Test each constant individually.

### How To Implement

```go
// config_test.go
package config_test

import (
    "testing"

    "github.com/stretchr/testify/assert"
)

// P12: Config struct initialises without error.
func TestCacheConfig_Instantiates(t *testing.T) {
    cfg := NewCacheConfig()
    assert.NotNil(t, cfg)
}

// P13: CacheByID constant holds the expected value.
func TestCacheByIDConstant(t *testing.T) {
    assert.Equal(t, "entityById", CacheByID,
        "CacheByID must equal 'entityById'")
}

// P14: CacheAll constant holds the expected value.
func TestCacheAllConstant(t *testing.T) {
    assert.Equal(t, "allEntities", CacheAll,
        "CacheAll must equal 'allEntities'")
}

// P15: CacheCount constant holds the expected value.
func TestCacheCountConstant(t *testing.T) {
    assert.Equal(t, "entityCount", CacheCount,
        "CacheCount must equal 'entityCount'")
}

// N16: No cache constant returns an empty string.
func TestCacheConstants_NoneEmpty(t *testing.T) {
    assert.NotEmpty(t, CacheByID,  "CacheByID must not be empty")
    assert.NotEmpty(t, CacheAll,   "CacheAll must not be empty")
    assert.NotEmpty(t, CacheCount, "CacheCount must not be empty")
}

// E17: All cache constants are distinct — a typo that reuses a value is caught.
func TestAllCacheConstants_AreDistinct(t *testing.T) {
    constants := map[string]bool{
        CacheByID:  true,
        CacheAll:   true,
        CacheCount: true,
    }
    assert.Len(t, constants, 3,
        "all cache constants must be unique strings; duplicate would reduce map size")
}
```

### Why This Matters
Incorrect cache constant names cause silent cache misses at runtime — the application
compiles and runs but returns stale data on every request. String assertion catches typos
before they reach staging.

---

## 3. Handler Layer (P18–P23, N24–N27, E28–E30)

### What We Follow

Use `httptest.NewRequest` and `httptest.NewRecorder` to exercise HTTP handlers without
starting a real server. Inject mock services via constructor or dependency injection.
Assert HTTP status code and response body envelope fields.

### How To Implement

```go
// handler_test.go
package handler_test

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/require"
)

// P18: POST /resources returns 201 Created with populated DTO.
func TestCreateResource_Returns201(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Add", mock.Anything, mock.AnythingOfType("ResourceForm")).
        Return(&ResourceDTO{ID: 1, Name: "Test", Path: "/test"}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"Test","path":"/test"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    assert.Equal(t, http.StatusCreated, rec.Code)
    var body ApiResponse[ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.True(t, body.Success)
    assert.Equal(t, int64(1), body.Data.ID)
    mockSvc.AssertExpectations(t)
}

// P19: PUT /resources/{id} returns 200 OK with updated DTO.
func TestUpdateResource_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Update", mock.Anything, int64(1), mock.AnythingOfType("ResourceForm")).
        Return(&ResourceDTO{ID: 1, Name: "Updated", Path: "/updated"}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPut, "/api/v1/resources/1",
        strings.NewReader(`{"name":"Updated","path":"/updated"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    // Simulate chi/gorilla route variable extraction:
    h.Update(rec, withRouteVar(req, "id", "1"))

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.True(t, body.Success)
    assert.Equal(t, "Updated", body.Data.Name)
}

// P20: GET /resources/{id} returns 200 OK with DTO.
func TestGetResourceByID_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetByID", mock.Anything, int64(1)).
        Return(&ResourceDTO{ID: 1, Name: "Name", Path: "/path"}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/1", nil)
    rec := httptest.NewRecorder()

    h.GetByID(rec, withRouteVar(req, "id", "1"))

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.Equal(t, int64(1), body.Data.ID)
}

// P21: GET /resources returns 200 OK with slice of DTOs.
func TestGetAllResources_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetAll", mock.Anything).
        Return([]ResourceDTO{{ID: 1, Name: "A"}, {ID: 2, Name: "B"}}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
    rec := httptest.NewRecorder()

    h.GetAll(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[[]ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.Len(t, body.Data, 2)
}

// P22: DELETE /resources/{id} returns 200 OK.
func TestDeleteResource_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Delete", mock.Anything, int64(1)).Return(nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodDelete, "/api/v1/resources/1", nil)
    rec := httptest.NewRecorder()

    h.Delete(rec, withRouteVar(req, "id", "1"))

    assert.Equal(t, http.StatusOK, rec.Code)
}

// P23: GET /resources/count returns 200 OK with count value.
func TestGetResourceCount_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetCount", mock.Anything).Return(int64(7), nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/count", nil)
    rec := httptest.NewRecorder()

    h.GetCount(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[int64]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.Equal(t, int64(7), body.Data)
}

// N24: POST with duplicate name returns 409 Conflict.
func TestCreateResource_DuplicateName_Returns409(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Add", mock.Anything, mock.Anything).
        Return(nil, ErrDuplicateResource)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"Dup","path":"/dup"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    assert.Equal(t, http.StatusConflict, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
    assert.NotEmpty(t, body.Message)
}

// N25: POST with duplicate path returns 409 Conflict.
func TestCreateResource_DuplicatePath_Returns409(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Add", mock.Anything, mock.Anything).
        Return(nil, ErrDuplicatePath)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"New","path":"/dup"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    assert.Equal(t, http.StatusConflict, rec.Code)
}

// N26: GET /resources/{id} with non-existent ID returns 404 Not Found.
func TestGetResourceByID_NotFound_Returns404(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetByID", mock.Anything, int64(999)).
        Return(nil, ErrNotFound)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/999", nil)
    rec := httptest.NewRecorder()

    h.GetByID(rec, withRouteVar(req, "id", "999"))

    assert.Equal(t, http.StatusNotFound, rec.Code)
}

// N27: POST with invalid JSON body returns 400 Bad Request.
func TestCreateResource_MalformedJSON_Returns400(t *testing.T) {
    mockSvc := new(MockResourceService)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{invalid`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    assert.Equal(t, http.StatusBadRequest, rec.Code)
    mockSvc.AssertNotCalled(t, "Add")
}

// E28: GET /resources when empty returns empty slice, not null.
func TestGetAllResources_Empty_ReturnsEmptySlice(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetAll", mock.Anything).Return([]ResourceDTO{}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
    rec := httptest.NewRecorder()

    h.GetAll(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[[]ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.NotNil(t, body.Data, "empty result must be [] not null")
    assert.Empty(t, body.Data)
}

// E29: GET /resources/count when zero returns 0, not null.
func TestGetResourceCount_Zero_Returns0(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetCount", mock.Anything).Return(int64(0), nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/count", nil)
    rec := httptest.NewRecorder()

    h.GetCount(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
    var body ApiResponse[int64]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.Equal(t, int64(0), body.Data)
}

// E30: Response Content-Type is application/json on all endpoints.
func TestCreateResource_ResponseContentType_JSON(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Add", mock.Anything, mock.Anything).
        Return(&ResourceDTO{ID: 1, Name: "X", Path: "/x"}, nil)

    h := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"X","path":"/x"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    assert.Contains(t, rec.Header().Get("Content-Type"), "application/json")
}
```

### Why This Matters
Handler tests verify the HTTP contract — status codes, body structure, and Content-Type —
in milliseconds without booting a real server. Every client depends on this contract.

---

## 4. Service Layer (P31–P39, N40–N45, E46–E50)

### What We Follow

Mock the repository and publisher interfaces. Assert that the correct repository methods
are called with the correct arguments. Verify that sentinel errors are returned unchanged
so the handler layer can map them to HTTP status codes.

### How To Implement

```go
// service_test.go
package service_test

import (
    "context"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/require"
)

// P31: Add — valid form saves entity and returns populated DTO.
func TestAdd_ValidResource_ReturnsDTO(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)

    repo.On("ExistsByNameILike", mock.Anything, "Test").Return(false, nil)
    repo.On("ExistsByPathILike", mock.Anything, "/test").Return(false, nil)
    repo.On("Save", mock.Anything, mock.AnythingOfType("*ResourceEntity")).
        Return(&ResourceEntity{ID: 1, Name: "Test", Path: "/test"}, nil)
    pub.On("PublishCreate", mock.Anything, int64(1)).Return(nil)

    svc := NewResourceService(repo, pub)
    dto, err := svc.Add(context.Background(), ResourceForm{Name: "Test", Path: "/test"})

    require.NoError(t, err)
    assert.Equal(t, int64(1), dto.ID)
    assert.Equal(t, "Test", dto.Name)
    repo.AssertCalled(t, "Save", mock.Anything, mock.Anything)
    pub.AssertCalled(t, "PublishCreate", mock.Anything, int64(1))
}

// P32: Update — valid form updates entity and returns updated DTO.
func TestUpdate_ValidForm_ReturnsUpdatedDTO(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)

    existing := &ResourceEntity{ID: 1, Name: "Old", Path: "/old"}
    updated  := &ResourceEntity{ID: 1, Name: "New", Path: "/new"}

    repo.On("FindByID", mock.Anything, int64(1)).Return(existing, nil)
    repo.On("ExistsByNameILikeAndIDNot", mock.Anything, "New", int64(1)).Return(false, nil)
    repo.On("ExistsByPathILikeAndIDNot", mock.Anything, "/new", int64(1)).Return(false, nil)
    repo.On("Save", mock.Anything, mock.Anything).Return(updated, nil)
    pub.On("PublishUpdate", mock.Anything, int64(1)).Return(nil)

    svc := NewResourceService(repo, pub)
    dto, err := svc.Update(context.Background(), 1, ResourceForm{Name: "New", Path: "/new"})

    require.NoError(t, err)
    assert.Equal(t, "New", dto.Name)
    pub.AssertCalled(t, "PublishUpdate", mock.Anything, int64(1))
}

// P33: GetByID — existing ID returns DTO with all fields mapped.
func TestGetByID_Exists_ReturnsMappedDTO(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindByID", mock.Anything, int64(1)).
        Return(&ResourceEntity{ID: 1, Name: "Name", Path: "/path"}, nil)

    svc := NewResourceService(repo, nil)
    dto, err := svc.GetByID(context.Background(), 1)

    require.NoError(t, err)
    assert.Equal(t, int64(1), dto.ID)
    assert.Equal(t, "Name", dto.Name)
    assert.Equal(t, "/path", dto.Path)
}

// P34: GetAll — calls repository with Sort by ID ASC.
func TestGetAll_CallsRepositoryWithSortByIDAsc(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindAll", mock.Anything, mock.MatchedBy(func(opts QueryOptions) bool {
        return opts.SortField == "id" && opts.SortDir == "asc"
    })).Return([]ResourceEntity{}, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.GetAll(context.Background())

    require.NoError(t, err)
    repo.AssertExpectations(t)
}

// P35: GetAll — returns DTOs with correct field mapping.
func TestGetAll_ReturnsMappedDTOs(t *testing.T) {
    repo := new(MockResourceRepository)
    entities := []ResourceEntity{
        {ID: 1, Name: "A", Path: "/a"},
        {ID: 2, Name: "B", Path: "/b"},
    }
    repo.On("FindAll", mock.Anything, mock.Anything).Return(entities, nil)

    svc := NewResourceService(repo, nil)
    dtos, err := svc.GetAll(context.Background())

    require.NoError(t, err)
    require.Len(t, dtos, 2)
    assert.Equal(t, int64(1), dtos[0].ID)
    assert.Equal(t, int64(2), dtos[1].ID)
}

// P36: Delete — publishes DELETE cache event with correct ID.
func TestDelete_PublishesDeleteEvent(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)
    repo.On("DeleteByID", mock.Anything, int64(1)).Return(nil)
    pub.On("PublishDelete", mock.Anything, int64(1)).Return(nil)

    svc := NewResourceService(repo, pub)
    err := svc.Delete(context.Background(), 1)

    require.NoError(t, err)
    pub.AssertCalled(t, "PublishDelete", mock.Anything, int64(1))
}

// P37: GetCount — returns the repository count value.
func TestGetCount_ReturnsRepositoryCount(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("Count", mock.Anything).Return(int64(5), nil)

    svc := NewResourceService(repo, nil)
    count, err := svc.GetCount(context.Background())

    require.NoError(t, err)
    assert.Equal(t, int64(5), count)
}

// P38: GetCount — returns 0 when repository is empty.
func TestGetCount_EmptyRepository_ReturnsZero(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("Count", mock.Anything).Return(int64(0), nil)

    svc := NewResourceService(repo, nil)
    count, err := svc.GetCount(context.Background())

    require.NoError(t, err)
    assert.Equal(t, int64(0), count)
}

// P39: Update with identical data — succeeds without error (idempotent field check).
func TestUpdate_IdenticalData_NoError(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)
    entity := &ResourceEntity{ID: 1, Name: "Same", Path: "/same"}

    repo.On("FindByID", mock.Anything, int64(1)).Return(entity, nil)
    repo.On("ExistsByNameILikeAndIDNot", mock.Anything, "Same", int64(1)).Return(false, nil)
    repo.On("ExistsByPathILikeAndIDNot", mock.Anything, "/same", int64(1)).Return(false, nil)
    repo.On("Save", mock.Anything, mock.Anything).Return(entity, nil)
    pub.On("PublishUpdate", mock.Anything, mock.Anything).Return(nil)

    svc := NewResourceService(repo, pub)
    _, err := svc.Update(context.Background(), 1, ResourceForm{Name: "Same", Path: "/same"})
    assert.NoError(t, err)
}

// N40: Add with duplicate name returns ErrDuplicateResource without saving.
func TestAdd_DuplicateName_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("ExistsByNameILike", mock.Anything, "Dup").Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Add(context.Background(), ResourceForm{Name: "Dup", Path: "/new"})

    assert.ErrorIs(t, err, ErrDuplicateResource)
    repo.AssertNotCalled(t, "Save")
}

// N41: Add with duplicate path returns ErrDuplicatePath without saving.
func TestAdd_DuplicatePath_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("ExistsByNameILike", mock.Anything, "New").Return(false, nil)
    repo.On("ExistsByPathILike", mock.Anything, "/dup").Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Add(context.Background(), ResourceForm{Name: "New", Path: "/dup"})

    assert.ErrorIs(t, err, ErrDuplicatePath)
    repo.AssertNotCalled(t, "Save")
}

// N42: GetByID with unknown ID returns ErrNotFound.
func TestGetByID_NotFound_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindByID", mock.Anything, int64(999)).Return(nil, ErrNotFound)

    svc := NewResourceService(repo, nil)
    _, err := svc.GetByID(context.Background(), 999)

    assert.ErrorIs(t, err, ErrNotFound)
}

// N43: Update on non-existent ID returns ErrNotFound.
func TestUpdate_NotFound_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindByID", mock.Anything, int64(999)).Return(nil, ErrNotFound)

    svc := NewResourceService(repo, nil)
    _, err := svc.Update(context.Background(), 999, ResourceForm{Name: "X", Path: "/x"})

    assert.ErrorIs(t, err, ErrNotFound)
}

// N44: Update with duplicate name on a different resource returns ErrDuplicateResource.
func TestUpdate_DuplicateNameOnOther_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    existing := &ResourceEntity{ID: 1, Name: "Old", Path: "/old"}
    repo.On("FindByID", mock.Anything, int64(1)).Return(existing, nil)
    repo.On("ExistsByNameILikeAndIDNot", mock.Anything, "Taken", int64(1)).Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Update(context.Background(), 1, ResourceForm{Name: "Taken", Path: "/new"})

    assert.ErrorIs(t, err, ErrDuplicateResource)
    repo.AssertNotCalled(t, "Save")
}

// N45: Update with duplicate path on a different resource returns ErrDuplicateResource.
func TestUpdate_DuplicatePathOnOther_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    existing := &ResourceEntity{ID: 1, Name: "Name", Path: "/old"}
    repo.On("FindByID", mock.Anything, int64(1)).Return(existing, nil)
    repo.On("ExistsByNameILikeAndIDNot", mock.Anything, "Name", int64(1)).Return(false, nil)
    repo.On("ExistsByPathILikeAndIDNot", mock.Anything, "/taken", int64(1)).Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Update(context.Background(), 1, ResourceForm{Name: "Name", Path: "/taken"})

    assert.ErrorIs(t, err, ErrDuplicateResource)
    repo.AssertNotCalled(t, "Save")
}

// N45B: Repository error on Save propagates to caller.
func TestAdd_RepositoryError_Propagates(t *testing.T) {
    repo := new(MockResourceRepository)
    repoErr := errors.New("db connection failed")

    repo.On("ExistsByNameILike", mock.Anything, "X").Return(false, nil)
    repo.On("ExistsByPathILike", mock.Anything, "/x").Return(false, nil)
    repo.On("Save", mock.Anything, mock.Anything).Return(nil, repoErr)

    svc := NewResourceService(repo, nil)
    _, err := svc.Add(context.Background(), ResourceForm{Name: "X", Path: "/x"})

    assert.Error(t, err)
    assert.ErrorContains(t, err, "db connection failed")
}

// E46: Case-insensitive duplicate check — uppercase name triggers ErrDuplicateResource.
func TestAdd_CaseInsensitiveDuplicate_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("ExistsByNameILike", mock.Anything, "RESOURCE").Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Add(context.Background(), ResourceForm{Name: "RESOURCE", Path: "/new"})

    assert.ErrorIs(t, err, ErrDuplicateResource)
}

// E47: Case-insensitive duplicate check — mixed-case path triggers ErrDuplicatePath.
func TestAdd_CaseInsensitivePathDuplicate_ReturnsError(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("ExistsByNameILike", mock.Anything, "New").Return(false, nil)
    repo.On("ExistsByPathILike", mock.Anything, "/PATH").Return(true, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.Add(context.Background(), ResourceForm{Name: "New", Path: "/PATH"})

    assert.ErrorIs(t, err, ErrDuplicatePath)
}

// E48: Delete on non-existent ID is idempotent — no error returned.
func TestDelete_NonExistentID_NoError(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)
    repo.On("DeleteByID", mock.Anything, int64(999)).Return(nil)
    pub.On("PublishDelete", mock.Anything, int64(999)).Return(nil)

    svc := NewResourceService(repo, pub)
    err := svc.Delete(context.Background(), 999)

    assert.NoError(t, err)
}

// E49: GetAll on single-item repository returns a slice of length 1.
func TestGetAll_SingleItem_ReturnsOneElementSlice(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindAll", mock.Anything, mock.Anything).
        Return([]ResourceEntity{{ID: 1, Name: "Only", Path: "/only"}}, nil)

    svc := NewResourceService(repo, nil)
    dtos, err := svc.GetAll(context.Background())

    require.NoError(t, err)
    assert.Len(t, dtos, 1)
}

// E50: GetAll sort option — SortField "id", SortDir "asc" verified via MatchedBy.
func TestGetAll_SortOptions_Verified(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindAll", mock.Anything, mock.MatchedBy(func(opts QueryOptions) bool {
        return opts.SortField == "id" && opts.SortDir == "asc"
    })).Return([]ResourceEntity{}, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.GetAll(context.Background())

    require.NoError(t, err)
    repo.AssertExpectations(t)
}
```

### Why This Matters
Service tests verify the business contract in isolation. The duplicate-check order,
case-insensitivity behaviour, and event publishing must all be explicit — the handler
layer relies on these sentinel errors to produce the correct HTTP status.

---

## 5. Entity/Model Layer (P51–P61, N62–N66, E67–E73)

### What We Follow

Go structs are value types. Test construction, field access, value equality, JSON
serialisation round-trip, and boundary values using direct struct initialisation —
no mocks required at this layer.

### How To Implement

```go
// entity_test.go
package resource_test

import (
    "encoding/json"
    "math"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

// P51: Struct literal sets all fields correctly.
func TestResourceEntity_FieldsSetCorrectly(t *testing.T) {
    e := ResourceEntity{ID: 1, Name: "Name", Path: "/path"}
    assert.Equal(t, int64(1), e.ID)
    assert.Equal(t, "Name", e.Name)
    assert.Equal(t, "/path", e.Path)
}

// P52: Zero-value struct is non-nil (Go always returns addressable zero value).
func TestResourceEntity_ZeroValue_IsUsable(t *testing.T) {
    var e ResourceEntity
    // Zero value must not cause a nil-pointer panic when accessed.
    assert.Equal(t, int64(0), e.ID)
    assert.Equal(t, "", e.Name)
}

// P53: Mutating fields via pointer reflects change.
func TestResourceEntity_FieldMutation(t *testing.T) {
    e := &ResourceEntity{}
    e.ID = 42
    e.Name = "Test"
    e.Path = "/test"
    assert.Equal(t, int64(42), e.ID)
    assert.Equal(t, "Test", e.Name)
    assert.Equal(t, "/test", e.Path)
}

// P54: Two structs with identical values are equal (reflect.DeepEqual via testify).
func TestResourceEntity_EqualWhenSameData(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    e2 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    assert.Equal(t, e1, e2)
}

// P55: Struct used as map key — same data produces same hash (via comparable).
func TestResourceEntity_AsMapKey(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    e2 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    m := map[ResourceEntity]bool{e1: true}
    assert.True(t, m[e2], "identical struct must match as map key")
}

// P56: DTO maps all entity fields.
func TestResourceDTO_MapsAllEntityFields(t *testing.T) {
    entity := ResourceEntity{ID: 1, Name: "Name", Path: "/path"}
    dto    := ResourceDTO{ID: entity.ID, Name: entity.Name, Path: entity.Path}
    assert.Equal(t, entity.ID, dto.ID)
    assert.Equal(t, entity.Name, dto.Name)
    assert.Equal(t, entity.Path, dto.Path)
}

// P57: JSON marshal of ResourceDTO produces expected keys.
func TestResourceDTO_JSONMarshal_HasExpectedKeys(t *testing.T) {
    dto  := ResourceDTO{ID: 1, Name: "Name", Path: "/path"}
    data, err := json.Marshal(dto)
    require.NoError(t, err)
    assert.Contains(t, string(data), `"id"`)
    assert.Contains(t, string(data), `"name"`)
    assert.Contains(t, string(data), `"path"`)
}

// P58: JSON unmarshal of ResourceDTO round-trips without loss.
func TestResourceDTO_JSONRoundTrip(t *testing.T) {
    original := ResourceDTO{ID: 1, Name: "Test", Path: "/test"}
    data, err := json.Marshal(original)
    require.NoError(t, err)
    var decoded ResourceDTO
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, original, decoded)
}

// P59: ResourceForm JSON round-trip preserves all fields.
func TestResourceForm_JSONRoundTrip(t *testing.T) {
    original := ResourceForm{Name: "MyName", Path: "/mypath"}
    data, err := json.Marshal(original)
    require.NoError(t, err)
    var decoded ResourceForm
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, original, decoded)
}

// P60: CacheEvent JSON round-trip preserves all fields.
func TestCacheEvent_JSONRoundTrip(t *testing.T) {
    original := CacheEvent{EventType: "CREATE", EntityType: "RESOURCE", EntityID: 1}
    data, err := json.Marshal(original)
    require.NoError(t, err)
    var decoded CacheEvent
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, original, decoded)
}

// P61: ApiResponse JSON round-trip preserves all envelope fields.
func TestApiResponse_JSONRoundTrip(t *testing.T) {
    original := ApiResponse[ResourceDTO]{
        Success: true,
        Status:  200,
        Message: "ok",
        Data:    ResourceDTO{ID: 1, Name: "A", Path: "/a"},
    }
    data, err := json.Marshal(original)
    require.NoError(t, err)
    var decoded ApiResponse[ResourceDTO]
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, original, decoded)
}

// N62: Structs with different IDs are not equal.
func TestResourceEntity_NotEqualWhenDifferentID(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    e2 := ResourceEntity{ID: 2, Name: "N", Path: "/p"}
    assert.NotEqual(t, e1, e2)
}

// N63: Structs with different names are not equal.
func TestResourceEntity_NotEqualWhenDifferentName(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "A", Path: "/p"}
    e2 := ResourceEntity{ID: 1, Name: "B", Path: "/p"}
    assert.NotEqual(t, e1, e2)
}

// N64: Structs with different paths are not equal.
func TestResourceEntity_NotEqualWhenDifferentPath(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "N", Path: "/a"}
    e2 := ResourceEntity{ID: 1, Name: "N", Path: "/b"}
    assert.NotEqual(t, e1, e2)
}

// N65: Empty string fields are distinct from whitespace-only fields.
func TestResourceEntity_EmptyVsWhitespace_NotEqual(t *testing.T) {
    e1 := ResourceEntity{ID: 1, Name: "", Path: "/p"}
    e2 := ResourceEntity{ID: 1, Name: " ", Path: "/p"}
    assert.NotEqual(t, e1, e2)
}

// N66: ResourceDTO with zero ID is valid Go zero-value (no panic).
func TestResourceDTO_ZeroID_NoNilDeref(t *testing.T) {
    dto := ResourceDTO{}
    assert.Equal(t, int64(0), dto.ID)
    assert.Equal(t, "", dto.Name)
}

// E67: Single-character name is a valid field value.
func TestResourceEntity_SingleCharName_Valid(t *testing.T) {
    e := ResourceEntity{ID: 1, Name: "A", Path: "/p"}
    assert.Equal(t, "A", e.Name)
}

// E68: Exactly 50-character name stores correctly.
func TestResourceEntity_MaxLengthName_Stores(t *testing.T) {
    maxName := strings.Repeat("A", 50)
    e := ResourceEntity{ID: 1, Name: maxName, Path: "/p"}
    assert.Equal(t, 50, len(e.Name))
}

// E69: math.MaxInt64 as ID stores without overflow.
func TestResourceEntity_MaxInt64ID_Stores(t *testing.T) {
    e := ResourceEntity{ID: math.MaxInt64}
    assert.Equal(t, int64(math.MaxInt64), e.ID)
}

// E70: Negative ID stores without panic.
func TestResourceEntity_NegativeID_Stores(t *testing.T) {
    e := ResourceEntity{ID: -1}
    assert.Equal(t, int64(-1), e.ID)
}

// E71: Name with special characters stores and round-trips via JSON.
func TestResourceEntity_SpecialCharName_JSONRoundTrip(t *testing.T) {
    name := "Res & Name (2024) <test>"
    e := ResourceEntity{ID: 1, Name: name, Path: "/p"}
    data, err := json.Marshal(e)
    require.NoError(t, err)
    var decoded ResourceEntity
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, name, decoded.Name)
}

// E72: Path with unicode characters stores and round-trips via JSON.
func TestResourceEntity_UnicodePathName_JSONRoundTrip(t *testing.T) {
    path := "/path/भारत"
    e := ResourceEntity{ID: 1, Name: "N", Path: path}
    data, err := json.Marshal(e)
    require.NoError(t, err)
    var decoded ResourceEntity
    require.NoError(t, json.Unmarshal(data, &decoded))
    assert.Equal(t, path, decoded.Path)
}

// E73: ApiResponse with nil data encodes as omitted field, not "data":null.
func TestApiResponse_NilData_OmittedInJSON(t *testing.T) {
    resp := ApiResponse[*ResourceDTO]{Success: false, Status: 409, Message: "conflict"}
    data, err := json.Marshal(resp)
    require.NoError(t, err)
    // omitempty on Data means null pointer should produce no "data" key.
    assert.NotContains(t, string(data), `"data":null`)
}
```

### Why This Matters
Go struct equality and JSON serialisation are the foundation of every handler response
and cache event payload. A mismatched JSON tag (`json:"id"` vs `json:"Id"`) silently
produces empty fields on the client side with no compile error.

---

## 6. Error Handler Layer (P74–P77, N78–N79, E80–E81)

### What We Follow

The error handler maps domain sentinel errors to HTTP status codes and wraps the response
in the standard `ApiResponse` envelope. Test each error mapping independently using
`httptest.NewRecorder`.

### How To Implement

```go
// error_handler_test.go
package handler_test

import (
    "encoding/json"
    "net/http/httptest"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

// P74: ErrDuplicateResource → 409 Conflict with success=false.
func TestErrorHandler_DuplicateResource_Returns409(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, ErrDuplicateResource)

    assert.Equal(t, http.StatusConflict, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
    assert.NotEmpty(t, body.Message)
}

// P75: ErrDuplicatePath → 409 Conflict with success=false.
func TestErrorHandler_DuplicatePath_Returns409(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, ErrDuplicatePath)

    assert.Equal(t, http.StatusConflict, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
}

// P76: ErrNotFound → 404 Not Found with success=false.
func TestErrorHandler_NotFound_Returns404(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, ErrNotFound)

    assert.Equal(t, http.StatusNotFound, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
}

// P77: HTTP status in recorder matches body status field.
func TestErrorHandler_StatusMatchesBody(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, ErrNotFound)

    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.Equal(t, rec.Code, body.Status,
        "HTTP status code must match body.status field")
}

// N78: Unknown error → 500 Internal Server Error.
func TestErrorHandler_UnknownError_Returns500(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, errors.New("some unexpected error"))

    assert.Equal(t, http.StatusInternalServerError, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
}

// N79: 500 response does not contain stack trace or internal error text.
func TestErrorHandler_InternalError_NoStackTrace(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, errors.New("internal db panic details"))

    bodyStr := rec.Body.String()
    assert.NotContains(t, bodyStr, "goroutine",
        "stack trace must not leak into HTTP response")
    assert.NotContains(t, bodyStr, "internal db panic details",
        "raw error message must not leak into HTTP response")
}

// E80: Error response body always has non-empty message.
func TestErrorHandler_AllErrors_NonEmptyMessage(t *testing.T) {
    h := NewErrorHandler()
    errs := []error{ErrDuplicateResource, ErrDuplicatePath, ErrNotFound, errors.New("generic")}

    for _, e := range errs {
        rec := httptest.NewRecorder()
        h.Handle(rec, e)

        var body ApiResponse[any]
        require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
        assert.NotEmpty(t, body.Message, "error %v must produce non-empty message", e)
    }
}

// E81: Error response Content-Type is application/json.
func TestErrorHandler_ResponseContentType_JSON(t *testing.T) {
    h   := NewErrorHandler()
    rec := httptest.NewRecorder()

    h.Handle(rec, ErrNotFound)

    assert.Contains(t, rec.Header().Get("Content-Type"), "application/json")
}
```

### Why This Matters
If the error handler leaks internal error strings or stack traces to clients it becomes
an information-disclosure vulnerability. If HTTP status does not match body status the
client receives contradictory signals and cannot distinguish success from failure.

---

## 7. Validation Layer (P82–P87, N88–N96, E97–E101)

### What We Follow

Use `go-playground/validator/v10` directly — no HTTP layer involved. Compile the validator
once per test file or use `sync.Once`. Test positive, negative, and edge cases using
table-driven tests, which is the idiomatic Go pattern.

### How To Implement

```go
// validation_test.go
package resource_test

import (
    "strings"
    "testing"

    "github.com/go-playground/validator/v10"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

var validate = validator.New()

// P82: Valid form — no validation errors.
func TestValidate_ValidForm_NoErrors(t *testing.T) {
    form := ResourceForm{Name: "Valid", Path: "/valid"}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// P83: Minimum valid name (1 character) passes.
func TestValidate_SingleCharName_NoErrors(t *testing.T) {
    form := ResourceForm{Name: "A", Path: "/path"}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// P84: Maximum valid name (50 characters) passes.
func TestValidate_MaxLengthName_NoErrors(t *testing.T) {
    form := ResourceForm{Name: strings.Repeat("A", 50), Path: "/path"}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// P85: Maximum valid path (50 characters) passes.
func TestValidate_MaxLengthPath_NoErrors(t *testing.T) {
    form := ResourceForm{Name: "Name", Path: strings.Repeat("p", 50)}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// P86: Name with special characters passes.
func TestValidate_SpecialCharsInName_NoErrors(t *testing.T) {
    form := ResourceForm{Name: "Res & Name (2024)", Path: "/path"}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// P87: Name with digits passes.
func TestValidate_DigitsInName_NoErrors(t *testing.T) {
    form := ResourceForm{Name: "Resource123", Path: "/path"}
    err  := validate.Struct(form)
    assert.NoError(t, err)
}

// Table-driven negative validation tests (N88–N96).
func TestValidate_NegativeScenarios(t *testing.T) {
    tests := []struct {
        id       string
        form     ResourceForm
        field    string
        tag      string
    }{
        // N88: Empty name — required violation.
        {"N88", ResourceForm{Name: "", Path: "/path"}, "Name", "required"},
        // N89: Name too long (51 chars) — max violation.
        {"N89", ResourceForm{Name: strings.Repeat("A", 51), Path: "/path"}, "Name", "max"},
        // N90: Empty path — required violation.
        {"N90", ResourceForm{Name: "Name", Path: ""}, "Path", "required"},
        // N91: Path too long (51 chars) — max violation.
        {"N91", ResourceForm{Name: "Name", Path: strings.Repeat("p", 51)}, "Path", "max"},
        // N92: Both name and path empty — both required violations.
        // (handled by E97 below for count; this verifies Name field specifically)
        {"N92", ResourceForm{Name: "", Path: "/p"}, "Name", "required"},
        // N93: Whitespace-only name — required violation (validator trims).
        {"N93", ResourceForm{Name: "   ", Path: "/path"}, "Name", "required"},
        // N94: Single-space path — required violation.
        {"N94", ResourceForm{Name: "Name", Path: " "}, "Path", "required"},
        // N95: Name of exactly 51 chars — one over max.
        {"N95", ResourceForm{Name: strings.Repeat("X", 51), Path: "/p"}, "Name", "max"},
        // N96: Path of exactly 51 chars — one over max.
        {"N96", ResourceForm{Name: "Name", Path: strings.Repeat("p", 51)}, "Path", "max"},
    }

    for _, tt := range tests {
        tt := tt // capture loop variable
        t.Run(tt.id, func(t *testing.T) {
            err := validate.Struct(tt.form)
            require.Error(t, err)
            var valErrs validator.ValidationErrors
            require.ErrorAs(t, err, &valErrs)
            assert.True(t,
                containsFieldError(valErrs, tt.field, tt.tag),
                "%s: expected field=%s tag=%s in %v", tt.id, tt.field, tt.tag, valErrs,
            )
        })
    }
}

// E97: Both fields empty returns exactly 2 validation errors.
func TestValidate_BothEmpty_TwoErrors(t *testing.T) {
    form := ResourceForm{Name: "", Path: ""}
    err  := validate.Struct(form)
    require.Error(t, err)
    var valErrs validator.ValidationErrors
    require.ErrorAs(t, err, &valErrs)
    assert.Len(t, valErrs, 2,
        "both required violations must be reported simultaneously")
}

// E98: Exactly-max-length name (50) passes; 51 fails.
func TestValidate_MaxBoundary_PassAndFail(t *testing.T) {
    passForm := ResourceForm{Name: strings.Repeat("A", 50), Path: "/p"}
    failForm := ResourceForm{Name: strings.Repeat("A", 51), Path: "/p"}

    assert.NoError(t, validate.Struct(passForm), "50-char name must pass")
    assert.Error(t,   validate.Struct(failForm), "51-char name must fail")
}

// E99: Exactly-max-length path (50) passes; 51 fails.
func TestValidate_MaxPathBoundary_PassAndFail(t *testing.T) {
    passForm := ResourceForm{Name: "Name", Path: strings.Repeat("p", 50)}
    failForm := ResourceForm{Name: "Name", Path: strings.Repeat("p", 51)}

    assert.NoError(t, validate.Struct(passForm), "50-char path must pass")
    assert.Error(t,   validate.Struct(failForm), "51-char path must fail")
}

// E100: Minimum-length name (1 char) passes; 0-char fails.
func TestValidate_MinBoundary_PassAndFail(t *testing.T) {
    passForm := ResourceForm{Name: "A", Path: "/p"}
    failForm := ResourceForm{Name: "", Path: "/p"}

    assert.NoError(t, validate.Struct(passForm), "1-char name must pass")
    assert.Error(t,   validate.Struct(failForm), "0-char name must fail")
}

// E101: Validation error carries the field name as reported — not the JSON tag.
func TestValidate_ErrorFieldName_IsStructFieldName(t *testing.T) {
    form := ResourceForm{Name: "", Path: "/p"}
    err  := validate.Struct(form)
    require.Error(t, err)
    var valErrs validator.ValidationErrors
    require.ErrorAs(t, err, &valErrs)
    assert.True(t, containsFieldError(valErrs, "Name", "required"),
        "error field name must be 'Name' (struct field), not 'name' (json tag)")
}
```

### Why This Matters
Positive validation tests document the exact acceptance boundaries so future developers
know the contract. The boundary tests at E98–E100 catch off-by-one errors in constraint
definitions that would otherwise only surface in production with real client data.

---

## 8. Event Publisher Layer (P102–P105, N106, E107)

### What We Follow

Mock the Redis client interface. Use `mock.MatchedBy` to inspect the published JSON payload
and verify `EventType`, `EntityType`, and `EntityID` are correct for each operation.
Test all three event types and the distinctness invariant.

### How To Implement

```go
// publisher_test.go
package publisher_test

import (
    "context"
    "encoding/json"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/require"
)

// MockRedisClient mocks the Redis Publish call.
type MockRedisClient struct {
    mock.Mock
}

func (m *MockRedisClient) Publish(ctx context.Context, channel string, message interface{}) error {
    return m.Called(ctx, channel, message).Error(0)
}

// P102: PublishCreate publishes CREATE event with correct fields.
func TestPublishCreate_CorrectEventType(t *testing.T) {
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.AnythingOfType("string"),
        mock.MatchedBy(func(msg string) bool {
            var event CacheEvent
            if err := json.Unmarshal([]byte(msg), &event); err != nil {
                return false
            }
            return event.EventType == "CREATE" && event.EntityType == "RESOURCE"
        }),
    ).Return(nil)

    pub := NewCacheEventPublisher(redisClient)
    err := pub.PublishCreate(context.Background(), 0)

    require.NoError(t, err)
    redisClient.AssertExpectations(t)
}

// P103: PublishCreate with null entityId (0) publishes EntityID=0.
func TestPublishCreate_NullEntityID_PublishesZero(t *testing.T) {
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.Anything,
        mock.MatchedBy(func(msg string) bool {
            var event CacheEvent
            _ = json.Unmarshal([]byte(msg), &event)
            return event.EventType == "CREATE" && event.EntityID == 0
        }),
    ).Return(nil)

    pub := NewCacheEventPublisher(redisClient)
    _ = pub.PublishCreate(context.Background(), 0)
    redisClient.AssertExpectations(t)
}

// P104: PublishUpdate publishes UPDATE event with correct EntityID.
func TestPublishUpdate_CorrectTypeAndID(t *testing.T) {
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.Anything,
        mock.MatchedBy(func(msg string) bool {
            var event CacheEvent
            _ = json.Unmarshal([]byte(msg), &event)
            return event.EventType == "UPDATE" && event.EntityID == 1
        }),
    ).Return(nil)

    pub := NewCacheEventPublisher(redisClient)
    err := pub.PublishUpdate(context.Background(), 1)

    require.NoError(t, err)
    redisClient.AssertExpectations(t)
}

// P105: PublishDelete publishes DELETE event with correct EntityID.
func TestPublishDelete_CorrectTypeAndID(t *testing.T) {
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.Anything,
        mock.MatchedBy(func(msg string) bool {
            var event CacheEvent
            _ = json.Unmarshal([]byte(msg), &event)
            return event.EventType == "DELETE" && event.EntityID == 1
        }),
    ).Return(nil)

    pub := NewCacheEventPublisher(redisClient)
    err := pub.PublishDelete(context.Background(), 1)

    require.NoError(t, err)
    redisClient.AssertExpectations(t)
}

// N106: Redis Publish error is propagated to the caller.
func TestPublishCreate_RedisError_Propagated(t *testing.T) {
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.Anything, mock.Anything).
        Return(errors.New("redis: connection refused"))

    pub := NewCacheEventPublisher(redisClient)
    err := pub.PublishCreate(context.Background(), 1)

    assert.Error(t, err)
    assert.ErrorContains(t, err, "redis")
}

// E107: All three event types produce distinct EventType strings.
func TestPublish_AllEventTypes_Distinct(t *testing.T) {
    var published []CacheEvent
    redisClient := new(MockRedisClient)
    redisClient.On("Publish", mock.Anything, mock.Anything, mock.Anything).
        Run(func(args mock.Arguments) {
            msg, _ := args.String(2), struct{}{}
            var event CacheEvent
            if err := json.Unmarshal([]byte(msg), &event); err == nil {
                published = append(published, event)
            }
        }).Return(nil)

    pub := NewCacheEventPublisher(redisClient)
    _ = pub.PublishCreate(context.Background(), 0)
    _ = pub.PublishUpdate(context.Background(), 1)
    _ = pub.PublishDelete(context.Background(), 1)

    types := make(map[string]bool)
    for _, e := range published {
        types[e.EventType] = true
    }
    assert.Len(t, types, 3,
        "CREATE, UPDATE, DELETE must all be distinct event type strings")
}
```

### Why This Matters
Incorrect event type or wrong EntityID causes the cache consumer to invalidate the wrong
key or ignore the event entirely. Both are invisible without this test — the application
runs but serves stale data after every mutation.

---

## 9. Mocking Strategy Reference

| Layer | Go Strategy | Key Tool | Why |
|-------|-------------|----------|-----|
| Bootstrap | Function-variable override (`var listenAndServe`) | Build tags / test doubles | Prevents real port binding in tests |
| Config | Direct constant access or `os.Setenv` | None | Constants are plain package-level vars |
| Handler | `httptest.NewRecorder` + mock service interface | testify/mock | Tests full HTTP path without a server |
| Service | Mock repo + mock publisher interfaces | testify/mock or gomock | Isolates business logic from I/O |
| Entity | Struct literal initialisation | None | Structs are value types; no mocking needed |
| Error Handler | `httptest.NewRecorder` | testify/assert | Pure error→HTTP mapping |
| Validation | `validator.New().Struct(form)` directly | go-playground/validator/v10 | No framework needed |
| Event Publisher | Mock Redis client interface | testify/mock | No real Redis process required |

---

## 10. Cross-Cutting Patterns (7 Patterns)

### Pattern 1: ApiResponse Envelope Consistency

Every endpoint — success and error — returns the same `ApiResponse[T]` structure.
`Success=true` on success with non-nil `Data`. `Success=false` on error with nil `Data`
and non-empty `Message`. HTTP status code matches `body.Status`.

```go
// cross_cutting_test.go
package handler_test

// CC-1a: Success response has Success=true, non-nil Data, non-empty Message.
func TestApiResponseConsistency_SuccessResponse(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("Add", mock.Anything, mock.Anything).
        Return(&ResourceDTO{ID: 1, Name: "N", Path: "/p"}, nil)

    h   := NewResourceHandler(mockSvc)
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"N","path":"/p"}`))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    h.Create(rec, req)

    var body ApiResponse[ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.True(t, body.Success)
    assert.NotEmpty(t, body.Message)
    assert.Equal(t, rec.Code, body.Status)
}

// CC-1b: Error response has Success=false, empty Data, non-empty Message.
func TestApiResponseConsistency_ErrorResponse(t *testing.T) {
    errHandler := NewErrorHandler()
    rec := httptest.NewRecorder()

    errHandler.Handle(rec, ErrDuplicateResource)

    var body ApiResponse[*ResourceDTO]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
    assert.NotEmpty(t, body.Message)
    assert.Nil(t, body.Data)
    assert.Equal(t, rec.Code, body.Status)
}
```

### Pattern 2: Idempotent Delete

DELETE on a non-existent resource must not return an error. The service layer absorbs
`ErrNotFound` for delete operations and treats it as success.

```go
// CC-2: Delete is idempotent — no error when resource does not exist.
func TestDelete_Idempotent(t *testing.T) {
    repo := new(MockResourceRepository)
    pub  := new(MockCachePublisher)
    repo.On("DeleteByID", mock.Anything, int64(999)).Return(nil)
    pub.On("PublishDelete", mock.Anything, int64(999)).Return(nil)

    svc := NewResourceService(repo, pub)
    err := svc.Delete(context.Background(), 999)
    assert.NoError(t, err)
}
```

### Pattern 3: Case-Insensitive Duplicate Checking

Duplicate detection must be case-insensitive at both name and path levels. Upper-case,
lower-case, and mixed-case variants of an existing name or path must all be rejected.

```go
// CC-3: Case-insensitive duplicate — any casing of existing name is rejected.
func TestAdd_CaseInsensitivity_AllVariants(t *testing.T) {
    cases := []string{"test", "TEST", "Test", "tEsT"}
    for _, name := range cases {
        repo := new(MockResourceRepository)
        repo.On("ExistsByNameILike", mock.Anything, name).Return(true, nil)

        svc := NewResourceService(repo, nil)
        _, err := svc.Add(context.Background(), ResourceForm{Name: name, Path: "/new"})

        assert.ErrorIs(t, err, ErrDuplicateResource,
            "case variant %q must trigger duplicate error", name)
    }
}
```

### Pattern 4: Sort Contract

`GetAll` must always query the repository with `SortField="id"` and `SortDir="asc"`.
This is a sorting contract, not an implementation detail — clients depend on stable ordering.

```go
// CC-4: GetAll always requests id ASC sort.
func TestGetAll_SortContract_AlwaysIDAsc(t *testing.T) {
    repo := new(MockResourceRepository)
    repo.On("FindAll", mock.Anything, mock.MatchedBy(func(opts QueryOptions) bool {
        return opts.SortField == "id" && opts.SortDir == "asc"
    })).Return([]ResourceEntity{}, nil)

    svc := NewResourceService(repo, nil)
    _, err := svc.GetAll(context.Background())

    require.NoError(t, err)
    repo.AssertExpectations(t)
}
```

### Pattern 5: Cache Event Publishing on Every Mutation

Every mutation (Add, Update, Delete) must publish a cache invalidation event. The event
must carry the correct `EventType` and the `EntityID` of the affected entity.

```go
// CC-5: Every mutation publishes a cache event — verified via mock.AssertCalled.
func TestMutationEvents_AllThreeOperations(t *testing.T) {
    t.Run("Add publishes CREATE", func(t *testing.T) {
        repo, pub := new(MockResourceRepository), new(MockCachePublisher)
        repo.On("ExistsByNameILike", mock.Anything, mock.Anything).Return(false, nil)
        repo.On("ExistsByPathILike", mock.Anything, mock.Anything).Return(false, nil)
        repo.On("Save", mock.Anything, mock.Anything).
            Return(&ResourceEntity{ID: 1, Name: "N", Path: "/p"}, nil)
        pub.On("PublishCreate", mock.Anything, int64(1)).Return(nil)

        svc := NewResourceService(repo, pub)
        _, _ = svc.Add(context.Background(), ResourceForm{Name: "N", Path: "/p"})

        pub.AssertCalled(t, "PublishCreate", mock.Anything, int64(1))
    })

    t.Run("Update publishes UPDATE", func(t *testing.T) {
        repo, pub := new(MockResourceRepository), new(MockCachePublisher)
        entity := &ResourceEntity{ID: 2, Name: "Old", Path: "/old"}
        repo.On("FindByID", mock.Anything, int64(2)).Return(entity, nil)
        repo.On("ExistsByNameILikeAndIDNot", mock.Anything, mock.Anything, int64(2)).Return(false, nil)
        repo.On("ExistsByPathILikeAndIDNot", mock.Anything, mock.Anything, int64(2)).Return(false, nil)
        repo.On("Save", mock.Anything, mock.Anything).Return(entity, nil)
        pub.On("PublishUpdate", mock.Anything, int64(2)).Return(nil)

        svc := NewResourceService(repo, pub)
        _, _ = svc.Update(context.Background(), 2, ResourceForm{Name: "New", Path: "/new"})

        pub.AssertCalled(t, "PublishUpdate", mock.Anything, int64(2))
    })

    t.Run("Delete publishes DELETE", func(t *testing.T) {
        repo, pub := new(MockResourceRepository), new(MockCachePublisher)
        repo.On("DeleteByID", mock.Anything, int64(3)).Return(nil)
        pub.On("PublishDelete", mock.Anything, int64(3)).Return(nil)

        svc := NewResourceService(repo, pub)
        _ = svc.Delete(context.Background(), 3)

        pub.AssertCalled(t, "PublishDelete", mock.Anything, int64(3))
    })
}
```

### Pattern 6: No Stack Trace Leakage

HTTP error responses must never contain a Go goroutine dump, panic trace, or raw internal
error text. The error handler must sanitise all internal details before writing to the
response body.

```go
// CC-6: No internal error text leaks in HTTP response body.
func TestErrorHandler_NoLeakage_AllSentinelErrors(t *testing.T) {
    h    := NewErrorHandler()
    errs := []error{ErrDuplicateResource, ErrDuplicatePath, ErrNotFound,
                    errors.New("db: connection refused: FATAL: role 'app' does not exist")}

    for _, e := range errs {
        rec := httptest.NewRecorder()
        h.Handle(rec, e)
        body := rec.Body.String()
        assert.NotContains(t, body, "goroutine",  "goroutine dump must not leak")
        assert.NotContains(t, body, "runtime/",   "runtime path must not leak")
        assert.NotContains(t, body, "FATAL:",      "raw DB error must not leak")
    }
}
```

### Pattern 7: Validation Errors Are Returned Simultaneously

When a form has multiple validation errors, all errors must be reported in the same
response. The handler must not return the first error and stop — clients need all
violations to fix the form in one round trip.

```go
// CC-7: All validation errors are reported simultaneously (not one at a time).
func TestValidation_MultipleErrors_AllReported(t *testing.T) {
    form := ResourceForm{Name: "", Path: ""}
    err  := validate.Struct(form)
    require.Error(t, err)
    var valErrs validator.ValidationErrors
    require.ErrorAs(t, err, &valErrs)
    assert.GreaterOrEqual(t, len(valErrs), 2,
        "both Name and Path violations must be returned together")
}
```

---

## 11. Go-Specific Testing Patterns

### Table-Driven Tests

Table-driven tests are the canonical Go pattern. Prefer them for any scenario set that
shares the same test logic with varying inputs:

```go
// Table-driven example — applies to service, validation, and entity tests.
func TestValidate_BoundaryValues(t *testing.T) {
    tests := []struct {
        name    string
        form    ResourceForm
        wantErr bool
    }{
        {"min valid name",  ResourceForm{Name: "A",                         Path: "/p"}, false},
        {"max valid name",  ResourceForm{Name: strings.Repeat("A", 50),    Path: "/p"}, false},
        {"over max name",   ResourceForm{Name: strings.Repeat("A", 51),    Path: "/p"}, true},
        {"empty name",      ResourceForm{Name: "",                          Path: "/p"}, true},
        {"min valid path",  ResourceForm{Name: "Name",                      Path: "p"},  false},
        {"max valid path",  ResourceForm{Name: "Name",  Path: strings.Repeat("p", 50)}, false},
        {"over max path",   ResourceForm{Name: "Name",  Path: strings.Repeat("p", 51)}, true},
        {"empty path",      ResourceForm{Name: "Name",                      Path: ""},   true},
    }

    for _, tt := range tests {
        tt := tt
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            err := validate.Struct(tt.form)
            if tt.wantErr {
                assert.Error(t, err, "expected validation error for %q", tt.name)
            } else {
                assert.NoError(t, err, "expected no validation error for %q", tt.name)
            }
        })
    }
}
```

### Subtests for Layer Grouping

Use `t.Run` to group tests within the same service:

```go
func TestResourceService(t *testing.T) {
    t.Run("Add", func(t *testing.T) {
        t.Run("valid form returns DTO", TestAdd_ValidResource_ReturnsDTO)
        t.Run("duplicate name returns error", TestAdd_DuplicateName_ReturnsError)
    })
    t.Run("Update", func(t *testing.T) {
        t.Run("valid form returns updated DTO", TestUpdate_ValidForm_ReturnsUpdatedDTO)
        t.Run("not found returns error", TestUpdate_NotFound_ReturnsError)
    })
    t.Run("Delete", func(t *testing.T) {
        t.Run("existing ID publishes event", TestDelete_PublishesDeleteEvent)
        t.Run("non-existent ID is idempotent", TestDelete_NonExistentID_NoError)
    })
}
```

### t.Parallel() for Independent Tests

Mark tests as parallel when they do not share state:

```go
func TestResourceEntity_EqualWhenSameData(t *testing.T) {
    t.Parallel()
    e1 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    e2 := ResourceEntity{ID: 1, Name: "N", Path: "/p"}
    assert.Equal(t, e1, e2)
}
```

### require vs assert

Use `require` when subsequent assertions would panic on nil values. Use `assert` when
a failure should be recorded but the test should continue to collect all failures:

```go
// require: stops test immediately if JSON decode fails (body would be zero-value)
require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))

// assert: records failure but continues — collects all field violations
assert.True(t, body.Success)
assert.NotEmpty(t, body.Message)
assert.Equal(t, rec.Code, body.Status)
```

---

## 12. Anti-Patterns

```go
// ANTI-PATTERN 1: Testing implementation details (internal struct fields) instead of
// observable behaviour. Test what the method returns, not how it computed it.

// WRONG — couples test to private state
func TestBad_InternalCounter(t *testing.T) {
    svc := &resourceServiceImpl{callCount: 0}
    svc.Add(ctx, form)
    assert.Equal(t, 1, svc.callCount) // private field: couples test to impl
}

// CORRECT — test observable output
func TestGood_AddReturnsDTO(t *testing.T) {
    dto, err := svc.Add(ctx, form)
    require.NoError(t, err)
    assert.NotNil(t, dto)
}

// ANTI-PATTERN 2: Using mock.Anything for arguments that carry the business contract.
// WRONG
mockRepo.On("FindAll", mock.Anything, mock.Anything).Return(...)
// CORRECT — verify sort contract explicitly
mockRepo.On("FindAll", mock.Anything,
    mock.MatchedBy(func(opts QueryOptions) bool {
        return opts.SortField == "id" && opts.SortDir == "asc"
    })).Return(...)

// ANTI-PATTERN 3: Starting a real HTTP server in handler tests.
// WRONG
go http.ListenAndServe(":8081", handler)
resp, _ := http.Get("http://localhost:8081/api/v1/resources")
// CORRECT
rec := httptest.NewRecorder()
req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
handler.GetAll(rec, req)

// ANTI-PATTERN 4: Sharing mock instances across tests without t.Cleanup.
// WRONG
var sharedMock = new(MockResourceService) // package-level: state leaks between tests
// CORRECT — create a new mock per test function
func TestCreateResource_Returns201(t *testing.T) {
    mockSvc := new(MockResourceService) // scoped to this test only
    ...
}

// ANTI-PATTERN 5: Using real Redis or real database in unit tests.
// WRONG
client := redis.NewClient(&redis.Options{Addr: "localhost:6379"})
// CORRECT
redisClient := new(MockRedisClient)
redisClient.On("Publish", ...).Return(nil)

// ANTI-PATTERN 6: Not asserting mock expectations after the test.
// WRONG
mockSvc.On("Add", ...).Return(dto, nil)
h.Create(rec, req)
// (missing AssertExpectations — mock call count never verified)
// CORRECT
mockSvc.AssertExpectations(t)
```

---

**ENFORCEMENT:** Every PR introducing a new handler, service, entity, error handler,
validator, or publisher must include all corresponding scenarios from this catalog before
the coverage gate runs. Missing scenarios will cause branch/method coverage failures
under `go test -cover` enforcement.

---

## Layer 9 — Security Tests (SEC1–SEC8)

Use `net/http/httptest` + `testify/assert`. All security tests live in `handler_security_test.go`.

### Why This Matters

Security tests verify that the HTTP surface rejects unauthenticated access, sanitises
malicious input, and never leaks internal state (stack traces, goroutine dumps, file
paths) through error responses. A 500 response to an injection payload or an unchecked
JWT means the handler is cooperating with an attacker.

```go
// SEC1: Authenticated request with valid Bearer token → 200 OK.
func TestSEC1_ValidBearerToken_Returns200(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetAll", mock.Anything).Return([]ResourceDTO{{ID: 1, Name: "r"}}, nil)
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
    req.Header.Set("Authorization", "Bearer valid-test-token")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
    mockSvc.AssertExpectations(t)
}

// SEC2: Health endpoint accessible without authentication → 200.
// Health probes must not require auth; Kubernetes liveness/readiness depends on this.
func TestSEC2_HealthEndpoint_NoAuthRequired_Returns200(t *testing.T) {
    req := httptest.NewRequest(http.MethodGet, "/health", nil)
    rec := httptest.NewRecorder()
    healthHandler(rec, req)

    assert.Equal(t, http.StatusOK, rec.Code)
}

// SEC3: Missing Authorization header → 401, body.Success = false.
// CORRECT
func TestSEC3_MissingAuthHeader_Returns401(t *testing.T) {
    handler := NewResourceHandler(new(MockResourceService))

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
    // No Authorization header set
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusUnauthorized, rec.Code)
    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
    assert.False(t, body.Success)
}

// WRONG — checking only status code without verifying body contract
// func TestSEC3_Wrong(t *testing.T) {
//     ...
//     assert.Equal(t, http.StatusUnauthorized, rec.Code)
//     // Missing: body.Success must be false; body must be valid JSON
// }

// SEC4: Malformed or expired JWT → 401, error message does NOT contain goroutine
//       dumps or internal file paths.
func TestSEC4_MalformedJWT_Returns401_NoStackTrace(t *testing.T) {
    handler := NewResourceHandler(new(MockResourceService))

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
    req.Header.Set("Authorization", "Bearer this.is.not.a.valid.jwt")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusUnauthorized, rec.Code)

    body := rec.Body.String()
    assert.NotContains(t, body, "goroutine",
        "response must not contain goroutine dumps")
    assert.NotContains(t, body, ".go:",
        "response must not contain internal file paths")
}

// SEC5: SQL injection payload in name field → 400 or rejected, NOT 500.
// The handler must validate / reject before passing to the service layer.
func TestSEC5_SQLInjectionInName_Returns400NotPanic(t *testing.T) {
    mockSvc := new(MockResourceService)
    // Service should never be called when the payload is malicious
    handler := NewResourceHandler(mockSvc)

    payload := `{"name": "'; DROP TABLE resources; --", "path": "/test"}`
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(payload))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    // Must be 400, not 500 (which would imply the DB was hit with raw input)
    assert.Equal(t, http.StatusBadRequest, rec.Code,
        "SQL injection payload must be rejected at the handler layer")
    mockSvc.AssertNotCalled(t, "Add", mock.Anything, mock.Anything)
}

// WRONG — accepting any non-500 without verifying service was not called
// func TestSEC5_Wrong(t *testing.T) {
//     ...
//     assert.NotEqual(t, http.StatusInternalServerError, rec.Code)
//     // Missing: service should not have been called at all
// }

// SEC6: XSS payload in name field → stored or rejected, but NEVER 500.
// The handler must not panic when processing script tags in string fields.
func TestSEC6_XSSPayloadInName_NotPanic_Not500(t *testing.T) {
    mockSvc := new(MockResourceService)
    // If the handler passes the payload through to the service, the service
    // must also not panic (configure mock to return normally or a validation error).
    mockSvc.On("Add", mock.Anything, mock.Anything).
        Return(nil, errors.New("validation error")).Maybe()
    handler := NewResourceHandler(mockSvc)

    payload := `{"name": "<script>alert(1)</script>", "path": "/test"}`
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(payload))
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()

    // Must not panic — test framework recovers panics and marks test as failed
    assert.NotPanics(t, func() { handler.ServeHTTP(rec, req) })
    assert.NotEqual(t, http.StatusInternalServerError, rec.Code,
        "XSS payload must not cause 500; handler should validate or sanitise")
}

// SEC7: Oversized body (10 MB) → 413 or 400, NOT 500.
// Requires http.MaxBytesReader to be applied in the handler middleware.
func TestSEC7_OversizedBody_Returns413Or400(t *testing.T) {
    handler := NewResourceHandler(new(MockResourceService))

    // Generate a 10 MB body
    largeBody := strings.NewReader(strings.Repeat("x", 10*1024*1024))
    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources", largeBody)
    req.Header.Set("Content-Type", "application/json")
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Contains(t, []int{http.StatusRequestEntityTooLarge, http.StatusBadRequest},
        rec.Code,
        "10 MB body must be rejected with 413 or 400, not 500")
}

// WRONG — not enforcing http.MaxBytesReader in production middleware means this
// test passes trivially because the handler reads the entire body into memory,
// causing OOM in production under load.
//
// CORRECT pattern in middleware:
//   r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1 MB limit
//   defer r.Body.Close()

// SEC8: Missing Content-Type header → 415 or 400, NOT 500.
func TestSEC8_MissingContentType_Returns415Or400(t *testing.T) {
    handler := NewResourceHandler(new(MockResourceService))

    req := httptest.NewRequest(http.MethodPost, "/api/v1/resources",
        strings.NewReader(`{"name":"test","path":"/t"}`))
    // Content-Type deliberately omitted
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Contains(t, []int{http.StatusUnsupportedMediaType, http.StatusBadRequest},
        rec.Code,
        "missing Content-Type must be rejected with 415 or 400")
}
```

---

## Path Parameter Edge Cases (PP1–PP4)

These tests verify that the URL routing layer rejects structurally invalid path
parameters before they reach the service or database. Failing to reject them allows
error amplification: a badly-routed request may hit the database with a nonsense query,
producing a different (potentially information-leaking) error response.

```go
// PP1: Non-numeric path parameter → 400 Bad Request.
func TestGetResource_NonNumericID_Returns400(t *testing.T) {
    handler := NewResourceHandler(new(MockResourceService))

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/abc", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusBadRequest, rec.Code)
}

// PP2: Negative ID → 400 Bad Request or 404 Not Found.
// Both are acceptable; the key requirement is that the service is not called with -1.
func TestGetResource_NegativeID_Returns400Or404(t *testing.T) {
    mockSvc := new(MockResourceService)
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/-1", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Contains(t, []int{http.StatusBadRequest, http.StatusNotFound}, rec.Code,
        "negative ID must be rejected before reaching the service")
    mockSvc.AssertNotCalled(t, "GetByID", mock.Anything, int64(-1))
}

// PP3: Zero ID → 400 Bad Request or 404 Not Found.
// ID=0 is never a valid primary key; the handler must reject it explicitly.
func TestGetResource_ZeroID_Returns400Or404(t *testing.T) {
    mockSvc := new(MockResourceService)
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/0", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Contains(t, []int{http.StatusBadRequest, http.StatusNotFound}, rec.Code,
        "zero ID must be rejected before reaching the service")
    mockSvc.AssertNotCalled(t, "GetByID", mock.Anything, int64(0))
}

// PP4: Overflow int64 path parameter → 400 Bad Request.
// strconv.ParseInt overflows silently on some implementations; the handler must
// return 400 rather than wrapping to a negative int64 and hitting the database.
func TestGetResource_OverflowID_Returns400(t *testing.T) {
    mockSvc := new(MockResourceService)
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet,
        "/api/v1/resources/99999999999999999999", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusBadRequest, rec.Code,
        "int64 overflow ID must produce 400, not a wrapped negative ID query")
    mockSvc.AssertNotCalled(t, "GetByID", mock.Anything, mock.Anything)
}
```

---

## Internal Error Structure (ERR1–ERR3)

These tests verify that when the application encounters an unexpected error it returns
a structured JSON response and never leaks runtime internals (goroutine stack dumps,
source file paths, package names) to the caller. Leaking stack traces is an information
disclosure vulnerability (OWASP A05 Security Misconfiguration).

```go
// ERR1: Unhandled service panic/error produces a structured JSON response with
//       status 500 and body.Success = false.
func TestUnhandledPanic_ReturnsStructuredJSON(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetByID", mock.Anything, int64(1)).
        Return(nil, errors.New("unexpected internal error"))
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/1", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusInternalServerError, rec.Code)

    var body ApiResponse[any]
    require.NoError(t, json.NewDecoder(rec.Body).Decode(&body),
        "500 response must be valid JSON, not a plain-text stack trace")
    assert.False(t, body.Success,
        "500 response body.Success must be false")
}

// WRONG — catching the status code but not validating JSON structure
// func TestERR1_Wrong(t *testing.T) {
//     ...
//     assert.Equal(t, http.StatusInternalServerError, rec.Code)
//     // Missing: JSON decode check; body might be a raw Go panic dump
// }

// ERR2: Internal server error response body does NOT contain goroutine dumps or
//       Go source file paths.
func TestInternalError_NoStackTrace(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetByID", mock.Anything, int64(1)).
        Return(nil, errors.New("db connection refused"))
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/1", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    body := rec.Body.String()
    assert.NotContains(t, body, "goroutine",
        "500 body must not contain a goroutine dump")
    assert.NotContains(t, body, ".go:",
        "500 body must not contain Go source file references")
    assert.NotContains(t, body, "runtime/debug",
        "500 body must not contain Go runtime package paths")
}

// ERR3: Internal server error response Content-Type is application/json.
// A plain-text or HTML 500 response breaks all client JSON parsers.
func TestInternalError_ContentTypeJSON(t *testing.T) {
    mockSvc := new(MockResourceService)
    mockSvc.On("GetByID", mock.Anything, int64(1)).
        Return(nil, errors.New("unexpected"))
    handler := NewResourceHandler(mockSvc)

    req := httptest.NewRequest(http.MethodGet, "/api/v1/resources/1", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Equal(t, http.StatusInternalServerError, rec.Code)
    ct := rec.Header().Get("Content-Type")
    assert.Contains(t, ct, "application/json",
        "500 response Content-Type must be application/json")
}
```

---

**SEE ALSO:**
- `40-universal-test-patterns-abstract.md` — language-agnostic source of truth for all 107 scenario IDs
- `35-positive-testing-standards.md` — Spring Boot positive scenarios (Java reference implementation)
- `36-negative-testing-standards.md` — Spring Boot negative scenarios (Java reference implementation)
- `37-edge-case-testing-standards.md` — Spring Boot edge case scenarios (Java reference implementation)
- `41-testing-standards-python-fastapi.md` — Python/FastAPI implementation
- `42-testing-standards-nodejs-express.md` — Node.js/TypeScript implementation
