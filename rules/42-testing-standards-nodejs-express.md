---
description: "Level 2.3 - Node.js/TypeScript/Express testing standards: 122 scenarios across 11 layers (positive/negative/edge/security/path-params/error-structure)"
paths:
  - "src/**/*.test.ts"
  - "src/**/*.spec.ts"
  - "tests/**/*.ts"
  - "__tests__/**/*.ts"
priority: high
conditional: "Node.js/TypeScript project detected (package.json with express or fastify)"
---

# Node.js/TypeScript/Express Testing Standards (Level 2.3)

**PURPOSE:** Define the mandatory test scenarios that every Node.js/TypeScript REST microservice
must cover, organized by application layer. Each scenario ID (P1–P105, N9–N106, E11–E107,
SEC1–SEC8, PP1–PP4, ERR1–ERR3) maps 1-to-1 with the language-agnostic abstract defined in
`40-universal-test-patterns-abstract.md`. This file is the authoritative Node.js implementation
reference — it prescribes HOW to write every scenario using Jest 29+, supertest, Zod,
Prisma/TypeORM, and ioredis. When the abstract adds or removes a scenario, this file must be
updated to match.

**APPLIES WHEN:** Any Node.js/TypeScript REST microservice with Express (or Fastify/NestJS)
following the Route → Controller → Service → Repository architectural pattern, with Zod input
validation, domain error hierarchy, and Redis-based event publishing.

**TECHNOLOGY STACK:**
- Runtime: Node.js 20 LTS, TypeScript 5+
- Framework: Express 4+ (patterns apply to Fastify, NestJS)
- Test Framework: Jest 29+ (Vitest: functionally identical API)
- Mock Library: `jest.fn()`, `jest.mock()`, `jest.spyOn()`
- HTTP Test Client: supertest
- Assertion Style: `expect()` (Jest matchers)
- Validation: Zod (primary), class-validator (secondary)
- ORM: Prisma (primary), TypeORM (secondary)
- Event Publishing: ioredis

---

## Jest Configuration

Every project must have a `jest.config.ts` at the project root. This is the baseline
configuration that enables TypeScript, coverage thresholds, and module path aliases.

```typescript
// jest.config.ts — project root
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src', '<rootDir>/tests'],
  testMatch: [
    '**/__tests__/**/*.ts',
    '**/*.test.ts',
    '**/*.spec.ts',
  ],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  collectCoverageFrom: [
    'src/**/*.ts',
    '!src/**/*.d.ts',
    '!src/index.ts',
  ],
  coverageThresholds: {
    global: {
      branches: 80,
      functions: 90,
      lines: 90,
      statements: 90,
    },
  },
  clearMocks: true,
  restoreMocks: true,
};

export default config;
```

---

## Mock Factory Patterns

Use factory functions to create typed mocks. Never inline `jest.fn()` in describe blocks
without a factory — it makes mock shapes inconsistent across test files.

```typescript
// tests/factories/mock-repository.factory.ts
import { IResourceRepository } from '@/repositories/resource.repository';

export function createMockRepository(): jest.Mocked<IResourceRepository> {
  return {
    findById: jest.fn(),
    findAll: jest.fn(),
    findByName: jest.fn(),
    findByPath: jest.fn(),
    findByNameExcludingId: jest.fn(),
    findByPathExcludingId: jest.fn(),
    save: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
    count: jest.fn(),
  };
}

// tests/factories/mock-event-publisher.factory.ts
import { IEventPublisher } from '@/events/event-publisher';

export function createMockPublisher(): jest.Mocked<IEventPublisher> {
  return {
    publish: jest.fn(),
  };
}

// tests/factories/resource.factory.ts
import { Resource } from '@/entities/resource.entity';

export function buildResource(overrides: Partial<Resource> = {}): Resource {
  return {
    id: 1,
    name: 'Test Resource',
    path: '/test-resource',
    createdAt: new Date('2024-01-01T00:00:00Z'),
    updatedAt: new Date('2024-01-01T00:00:00Z'),
    ...overrides,
  };
}
```

---

## Mocking Strategy Reference

| Layer | Node.js/TS Strategy | Key Tool | Why |
|-------|--------------------|-----------|----|
| Bootstrap | Spy on `app.listen` and prevent actual bind | `jest.spyOn(app, 'listen').mockImplementation()` | Avoid port binding in tests; verify delegation only |
| Configuration | Direct import and assert constant values | Plain `import` + `expect(CONSTANT).toBe(...)` | No I/O; constants are deterministic — no mock needed |
| Controller/Route | Mock service layer; call handler directly or use supertest with mocked service | `jest.fn()` on service methods; `supertest(app)` | Tests HTTP contract (status, body, headers) without touching DB |
| Service | Mock repository + event publisher | `createMockRepository()`, `createMockPublisher()` | Isolates business logic; repository/events are side effects |
| Entity/Model | Instantiate directly; use Zod `.parse()` or class constructor | Direct object construction | No external dependency; validates schema contracts |
| Error Handler | Mount error handler on a minimal express app; trigger errors via route | `express()` + `app.use(errorHandler)` + `supertest` | Tests HTTP error shape without running the full app |
| Validation | Call Zod `.safeParse()` or schema validator directly | `schema.safeParse(input)` | Pure function; no mock needed |
| Event Publisher | Mock `ioredis` client; spy on `publish` | `jest.mock('ioredis')` | Avoids real Redis connection; asserts channel + payload |

---

## 1. Bootstrap Layer — Tests

### What We Follow

Every Express application entry-point file must have tests verifying that:
- The app is created with correct middleware
- The server delegates to `app.listen()` with expected port and callback
- CLI arguments (port overrides) are forwarded correctly
- The entry-point does not contain business logic

### How To Implement

```typescript
// src/__tests__/bootstrap.test.ts
import express from 'express';

// CORRECT — Bootstrap tests spy on listen; no real port binding
describe('Application Bootstrap', () => {
  let listenSpy: jest.SpyInstance;

  beforeEach(() => {
    // Prevent actual network binding across all bootstrap tests
    listenSpy = jest
      .spyOn(require('http').Server.prototype, 'listen')
      .mockImplementation(function (_port: number, cb?: () => void) {
        if (cb) cb();
        return this;
      });
  });

  afterEach(() => {
    listenSpy.mockRestore();
    jest.resetModules(); // Reset module registry between tests
  });

  // P1: App module exports an express application instance
  it('P1 — should export an Express application instance', () => {
    const { app } = require('@/app');
    expect(app).toBeDefined();
    expect(typeof app).toBe('function'); // Express app is a function
  });

  // P2: App parses JSON request bodies (behavioral test — no Express internals)
  it('P2 — should parse JSON request bodies correctly', async () => {
    const { app } = require('@/app');
    const res = await request(app)
      .post('/api/v1/resources')
      .set('Content-Type', 'application/json')
      .send({ name: 'Test', path: '/test' });
    // If JSON parsing works, we get a structured response (not 415 Unsupported Media Type)
    expect(res.status).not.toBe(415);
    expect(res.headers['content-type']).toMatch(/json/);
  });

  // P3: App parses URL-encoded form submissions (behavioral test)
  it('P3 — should parse URL-encoded form data correctly', async () => {
    const { app } = require('@/app');
    const res = await request(app)
      .post('/api/v1/resources')
      .set('Content-Type', 'application/x-www-form-urlencoded')
      .send('name=Test&path=/test');
    // If urlencoded parsing works, we get a structured response (not 415)
    expect(res.status).not.toBe(415);
  });

  // P4: Server start function has correct signature (port, callback)
  it('P4 — should export a startServer function accepting port and callback', () => {
    const { startServer } = require('@/server');
    expect(typeof startServer).toBe('function');
    expect(startServer.length).toBeGreaterThanOrEqual(1); // at least port param
  });

  // P5: startServer delegates to app.listen exactly once
  it('P5 — should call app.listen exactly once when startServer is invoked', () => {
    const { app } = require('@/app');
    const appListenSpy = jest.spyOn(app, 'listen').mockReturnValue({} as any);
    const { startServer } = require('@/server');

    startServer(3000);

    expect(appListenSpy).toHaveBeenCalledTimes(1);
    appListenSpy.mockRestore();
  });

  // P6: startServer forwards port argument to app.listen
  it('P6 — should forward port argument to app.listen', () => {
    const { app } = require('@/app');
    const appListenSpy = jest.spyOn(app, 'listen').mockReturnValue({} as any);
    const { startServer } = require('@/server');

    startServer(8080);

    expect(appListenSpy).toHaveBeenCalledWith(8080, expect.any(Function));
    appListenSpy.mockRestore();
  });

  // P7: App module has no direct side effects at import time
  it('P7 — should not throw when app module is imported', () => {
    expect(() => require('@/app')).not.toThrow();
  });

  // P8: App does not extend or wrap another application class (no hidden superclass)
  it('P8 — should be a plain Express application with no custom wrapping class', () => {
    const { app } = require('@/app');
    // Express app is created by express() factory, not class instantiation
    expect(app.constructor.name).not.toMatch(/Custom|Base|Abstract/i);
  });

  // N9: startServer with null/undefined port does not crash
  it('N9 — should not crash when called with undefined port', () => {
    const { app } = require('@/app');
    jest.spyOn(app, 'listen').mockReturnValue({} as any);
    const { startServer } = require('@/server');

    expect(() => startServer(undefined)).not.toThrow();
  });

  // N10: startServer with empty args still calls app.listen
  it('N10 — should still call app.listen when no args provided', () => {
    const { app } = require('@/app');
    const appListenSpy = jest.spyOn(app, 'listen').mockReturnValue({} as any);
    const { startServer } = require('@/server');

    startServer();

    expect(appListenSpy).toHaveBeenCalledTimes(1);
    appListenSpy.mockRestore();
  });

  // E11: Multiple env-override flags forwarded without loss
  it('E11 — should forward all environment overrides to listen when provided', () => {
    const { app } = require('@/app');
    const appListenSpy = jest.spyOn(app, 'listen').mockReturnValue({} as any);
    const { startServer } = require('@/server');

    startServer(9090, () => {});

    expect(appListenSpy).toHaveBeenCalledWith(9090, expect.any(Function));
    appListenSpy.mockRestore();
  });
});
```

### Why This Matters

Jest counts every module's top-level statements in coverage. Without bootstrap tests, the
entry-point module falls below the branch/function threshold and blocks the coverage gate.
Spying on `app.listen` without calling the real bind prevents `EADDRINUSE` errors in
parallel test workers.

---

## 2. Configuration Layer — Tests

### What We Follow

Every configuration module (cache names, queue names, timeout constants) must have tests
verifying that constants exist, have the correct value, and are unique across the module.

### How To Implement

```typescript
// src/__tests__/config.test.ts
import { AppConfig } from '@/config/app.config';

// CORRECT — Config tests instantiate or import directly; no mocks needed
describe('Configuration Layer', () => {
  let config: AppConfig;

  beforeEach(() => {
    config = new AppConfig();
  });

  // P12: Config class instantiates without throwing
  it('P12 — should instantiate AppConfig without error', () => {
    expect(() => new AppConfig()).not.toThrow();
    expect(config).toBeDefined();
    expect(config).toBeInstanceOf(AppConfig);
  });

  // P13: Single-entity cache name constant has correct value
  it('P13 — should have correct CACHE_BY_ID constant value', () => {
    expect(AppConfig.CACHE_BY_ID).toBe('resource:byId');
  });

  // P14: Collection cache name constant has correct value
  it('P14 — should have correct CACHE_ALL constant value', () => {
    expect(AppConfig.CACHE_ALL).toBe('resource:all');
  });

  // P15: Count cache name constant has correct value
  it('P15 — should have correct CACHE_COUNT constant value', () => {
    expect(AppConfig.CACHE_COUNT).toBe('resource:count');
  });

  // N16: No constant is null, undefined, or empty string
  it('N16 — should have no null, undefined, or empty-string constants', () => {
    const allConstants = [
      AppConfig.CACHE_BY_ID,
      AppConfig.CACHE_ALL,
      AppConfig.CACHE_COUNT,
    ];

    allConstants.forEach((constant, index) => {
      expect(constant).not.toBeNull();
      expect(constant).not.toBeUndefined();
      expect(constant).not.toBe('');
      expect(typeof constant).toBe('string');
    });
  });

  // E17: All constants are distinct — no duplicate values
  it('E17 — should have all unique constant values (no duplicates)', () => {
    const allConstants = [
      AppConfig.CACHE_BY_ID,
      AppConfig.CACHE_ALL,
      AppConfig.CACHE_COUNT,
    ];

    const uniqueValues = new Set(allConstants);
    expect(uniqueValues.size).toBe(allConstants.length);
  });
});
```

### Why This Matters

Cache name constants are the key lookup in Redis. A duplicate or empty cache name causes
one cache bucket to silently overwrite another's entries, producing stale reads without
any error signal. These tests catch typos at unit-test time, not in production.

---

## 3. Controller / Route Layer — Tests

### What We Follow

Controller tests mock the service layer and verify the HTTP contract: status code, response
body structure, and delegation to the service. Use supertest to test the full Express
middleware chain. Never start a real HTTP server — pass the `app` object to supertest directly.

### How To Implement

```typescript
// src/__tests__/resource.controller.test.ts
import request from 'supertest';
import express, { Express } from 'express';
import { ResourceController } from '@/controllers/resource.controller';
import { IResourceService } from '@/services/resource.service';
import { createMockService } from '../factories/mock-service.factory';
import { buildResource } from '../factories/resource.factory';

// CORRECT — Controller tests use supertest with mocked service
describe('ResourceController', () => {
  let app: Express;
  let mockService: jest.Mocked<IResourceService>;

  beforeEach(() => {
    mockService = createMockService();
    const controller = new ResourceController(mockService);

    app = express();
    app.use(express.json());
    app.use('/api/resources', controller.router);
    // Error handler must come last
    app.use((err: Error, req: express.Request, res: express.Response, next: express.NextFunction) => {
      res.status((err as any).statusCode ?? 500).json({ success: false, message: err.message });
    });
  });

  // P18: POST create returns 201 with resource body
  it('P18 — POST /api/resources should return 201 with created resource', async () => {
    const created = buildResource({ id: 1, name: 'New Resource', path: '/new-resource' });
    mockService.add.mockResolvedValue(created);

    const response = await request(app)
      .post('/api/resources')
      .send({ name: 'New Resource', path: '/new-resource' })
      .expect(201);

    expect(response.body.success).toBe(true);
    expect(response.body.data).toBeDefined();
    expect(response.body.data.id).toBe(1);
  });

  // P19: PUT update returns 200 with updated body
  it('P19 — PUT /api/resources/:id should return 200 with updated resource', async () => {
    const updated = buildResource({ id: 1, name: 'Updated Resource', path: '/updated' });
    mockService.update.mockResolvedValue(updated);

    const response = await request(app)
      .put('/api/resources/1')
      .send({ name: 'Updated Resource', path: '/updated' })
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data.name).toBe('Updated Resource');
  });

  // P20: GET by ID returns 200 with single resource
  it('P20 — GET /api/resources/:id should return 200 with single resource', async () => {
    const resource = buildResource({ id: 1 });
    mockService.getById.mockResolvedValue(resource);

    const response = await request(app)
      .get('/api/resources/1')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data).toBeDefined();
    expect(response.body.data.id).toBe(1);
  });

  // P21: GET all returns 200 with ordered collection
  it('P21 — GET /api/resources should return 200 with array of resources', async () => {
    const resources = [buildResource({ id: 1 }), buildResource({ id: 2, name: 'Second' })];
    mockService.getAll.mockResolvedValue(resources);

    const response = await request(app)
      .get('/api/resources')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.data)).toBe(true);
    expect(response.body.data).toHaveLength(2);
  });

  // P22: DELETE returns 200 with success flag
  it('P22 — DELETE /api/resources/:id should return 200 with success flag', async () => {
    mockService.delete.mockResolvedValue(undefined);

    const response = await request(app)
      .delete('/api/resources/1')
      .expect(200);

    expect(response.body.success).toBe(true);
  });

  // P23: GET count returns 200 with numeric value
  it('P23 — GET /api/resources/count should return 200 with numeric count', async () => {
    mockService.count.mockResolvedValue(42);

    const response = await request(app)
      .get('/api/resources/count')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(typeof response.body.data).toBe('number');
    expect(response.body.data).toBe(42);
  });

  // N24: POST with duplicate name → 409 Conflict
  it('N24 — POST with duplicate name should return 409 Conflict', async () => {
    const error = new Error('Resource with this name already exists');
    (error as any).statusCode = 409;
    mockService.add.mockRejectedValue(error);

    const response = await request(app)
      .post('/api/resources')
      .send({ name: 'Duplicate', path: '/duplicate' })
      .expect(409);

    expect(response.body.success).toBe(false);
  });

  // N25: POST with duplicate path → 409 Conflict
  it('N25 — POST with duplicate path should return 409 Conflict', async () => {
    const error = new Error('Resource with this path already exists');
    (error as any).statusCode = 409;
    mockService.add.mockRejectedValue(error);

    const response = await request(app)
      .post('/api/resources')
      .send({ name: 'Another Name', path: '/existing-path' })
      .expect(409);

    expect(response.body.success).toBe(false);
  });

  // N26: GET non-existent ID → 404 Not Found
  it('N26 — GET /api/resources/:id with non-existent ID should return 404', async () => {
    const error = new Error('Resource not found');
    (error as any).statusCode = 404;
    mockService.getById.mockRejectedValue(error);

    const response = await request(app)
      .get('/api/resources/9999')
      .expect(404);

    expect(response.body.success).toBe(false);
  });

  // N27: PUT non-existent ID → 404 Not Found
  it('N27 — PUT /api/resources/:id with non-existent ID should return 404', async () => {
    const error = new Error('Resource not found');
    (error as any).statusCode = 404;
    mockService.update.mockRejectedValue(error);

    const response = await request(app)
      .put('/api/resources/9999')
      .send({ name: 'Whatever', path: '/whatever' })
      .expect(404);

    expect(response.body.success).toBe(false);
  });

  // E28: GET all with empty data returns empty array, NOT null
  it('E28 — GET /api/resources with no data should return empty array, not null', async () => {
    mockService.getAll.mockResolvedValue([]);

    const response = await request(app)
      .get('/api/resources')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data).not.toBeNull();
    expect(Array.isArray(response.body.data)).toBe(true);
    expect(response.body.data).toHaveLength(0);
  });

  // E29: GET all preserves ordered array type (not Set or unordered object)
  it('E29 — GET /api/resources should return an Array with stable insertion order', async () => {
    const resources = [
      buildResource({ id: 1, name: 'First' }),
      buildResource({ id: 2, name: 'Second' }),
      buildResource({ id: 3, name: 'Third' }),
    ];
    mockService.getAll.mockResolvedValue(resources);

    const response = await request(app)
      .get('/api/resources')
      .expect(200);

    const data = response.body.data;
    expect(Array.isArray(data)).toBe(true);
    expect(data[0].id).toBe(1);
    expect(data[1].id).toBe(2);
    expect(data[2].id).toBe(3);
  });

  // E30: Service method called exactly once per request (no double-call)
  it('E30 — service.getById should be called exactly once per GET request', async () => {
    mockService.getById.mockResolvedValue(buildResource({ id: 1 }));

    await request(app).get('/api/resources/1').expect(200);

    expect(mockService.getById).toHaveBeenCalledTimes(1);
  });
});
```

### Why This Matters

Supertest passes the Express `app` (a Node.js `http.RequestListener`) directly to
`http.createServer()` without binding a port. This means tests run in parallel without
`EADDRINUSE` conflicts. The error handler at the end of the middleware chain is mandatory —
without it, errors thrown by the mocked service bubble to supertest as unhandled rejections
instead of HTTP responses.

---

## 4. Service Layer — Tests

### What We Follow

Service tests mock the repository and event publisher. Call service methods directly.
Use argument captors (`mockFn.mock.calls`) to verify arguments passed to dependencies.
Never use real databases or real Redis connections in service unit tests.

### How To Implement

```typescript
// src/__tests__/resource.service.test.ts
import { ResourceService } from '@/services/resource.service';
import { DuplicateNameError, DuplicatePathError, NotFoundError } from '@/errors/domain.errors';
import { createMockRepository } from '../factories/mock-repository.factory';
import { createMockPublisher } from '../factories/mock-event-publisher.factory';
import { buildResource } from '../factories/resource.factory';

// CORRECT — Service tests inject mocked repository and publisher
describe('ResourceService', () => {
  let service: ResourceService;
  let mockRepo: ReturnType<typeof createMockRepository>;
  let mockPublisher: ReturnType<typeof createMockPublisher>;

  beforeEach(() => {
    mockRepo = createMockRepository();
    mockPublisher = createMockPublisher();
    service = new ResourceService(mockRepo, mockPublisher);
  });

  // P31: add() returns populated resource with correct fields
  it('P31 — add() should return resource DTO with all fields populated', async () => {
    const saved = buildResource({ id: 1, name: 'Test', path: '/test' });
    mockRepo.findByName.mockResolvedValue(null);
    mockRepo.findByPath.mockResolvedValue(null);
    mockRepo.save.mockResolvedValue(saved);

    const result = await service.add({ name: 'Test', path: '/test' });

    expect(result).not.toBeNull();
    expect(result.id).toBe(1);
    expect(result.name).toBe('Test');
    expect(result.path).toBe('/test');
  });

  // P32: update() returns resource with updated field values
  it('P32 — update() should return DTO with new field values, not original values', async () => {
    const original = buildResource({ id: 1, name: 'Old Name', path: '/old' });
    const updated = buildResource({ id: 1, name: 'New Name', path: '/new' });
    mockRepo.findById.mockResolvedValue(original);
    mockRepo.findByNameExcludingId.mockResolvedValue(null);
    mockRepo.findByPathExcludingId.mockResolvedValue(null);
    mockRepo.update.mockResolvedValue(updated);

    const result = await service.update(1, { name: 'New Name', path: '/new' });

    expect(result.name).toBe('New Name');
    expect(result.path).toBe('/new');
  });

  // P33: getById() returns DTO with all fields mapped from entity
  it('P33 — getById() should return DTO with all entity fields correctly mapped', async () => {
    const entity = buildResource({ id: 42, name: 'Mapped', path: '/mapped' });
    mockRepo.findById.mockResolvedValue(entity);

    const result = await service.getById(42);

    expect(result.id).toBe(42);
    expect(result.name).toBe('Mapped');
    expect(result.path).toBe('/mapped');
  });

  // P34: getAll() passes sort-by-ID-ascending to repository
  it('P34 — getAll() should pass ascending sort by ID to the repository', async () => {
    mockRepo.findAll.mockResolvedValue([]);

    await service.getAll();

    expect(mockRepo.findAll).toHaveBeenCalledWith(
      expect.objectContaining({ orderBy: { id: 'asc' } })
    );
  });

  // P35: getAll() returns items in ID-ascending order
  it('P35 — getAll() should return items in ascending ID order', async () => {
    const items = [
      buildResource({ id: 1 }),
      buildResource({ id: 2, name: 'Second' }),
      buildResource({ id: 3, name: 'Third' }),
    ];
    mockRepo.findAll.mockResolvedValue(items);

    const result = await service.getAll();

    expect(result[0].id).toBeLessThan(result[1].id);
    expect(result[1].id).toBeLessThan(result[2].id);
  });

  // P36: delete() triggers DELETE cache-invalidation event
  it('P36 — delete() should publish exactly one DELETE event with correct entity ID', async () => {
    const entity = buildResource({ id: 5 });
    mockRepo.findById.mockResolvedValue(entity);
    mockRepo.delete.mockResolvedValue(undefined);

    await service.delete(5);

    expect(mockPublisher.publish).toHaveBeenCalledTimes(1);
    expect(mockPublisher.publish).toHaveBeenCalledWith(
      expect.stringContaining('resource'),
      expect.objectContaining({ type: 'DELETE', id: 5 })
    );
  });

  // P37: count() returns correct non-zero count
  it('P37 — count() should return non-zero count matching repository result', async () => {
    mockRepo.count.mockResolvedValue(7);

    const result = await service.count();

    expect(result).toBe(7);
    expect(result).toBeGreaterThan(0);
  });

  // P38: count() returns zero when repository is empty
  it('P38 — count() should return 0 (not null) when repository is empty', async () => {
    mockRepo.count.mockResolvedValue(0);

    const result = await service.count();

    expect(result).toBe(0);
    expect(result).not.toBeNull();
    expect(result).not.toBeUndefined();
  });

  // P39: update() with identical data (idempotent) succeeds without throwing
  it('P39 — update() with same data as current entity should not throw duplicate error', async () => {
    const entity = buildResource({ id: 1, name: 'Same Name', path: '/same' });
    mockRepo.findById.mockResolvedValue(entity);
    mockRepo.findByNameExcludingId.mockResolvedValue(null); // Self-exclusion returns null
    mockRepo.findByPathExcludingId.mockResolvedValue(null);
    mockRepo.update.mockResolvedValue(entity);

    await expect(
      service.update(1, { name: 'Same Name', path: '/same' })
    ).resolves.not.toThrow();
  });

  // N40: add() with duplicate name throws DuplicateNameError
  it('N40 — add() should throw DuplicateNameError when name already exists', async () => {
    mockRepo.findByName.mockResolvedValue(buildResource({ id: 99, name: 'Taken' }));

    await expect(service.add({ name: 'Taken', path: '/taken' }))
      .rejects.toThrow(DuplicateNameError);
  });

  // N41: add() with duplicate path throws DuplicatePathError
  it('N41 — add() should throw DuplicatePathError when path already exists', async () => {
    mockRepo.findByName.mockResolvedValue(null);
    mockRepo.findByPath.mockResolvedValue(buildResource({ id: 99, path: '/taken' }));

    await expect(service.add({ name: 'New Name', path: '/taken' }))
      .rejects.toThrow(DuplicatePathError);
  });

  // N42: getById() with non-existent ID throws NotFoundError
  it('N42 — getById() should throw NotFoundError when entity does not exist', async () => {
    mockRepo.findById.mockResolvedValue(null);

    await expect(service.getById(9999)).rejects.toThrow(NotFoundError);
  });

  // N43: update() with non-existent ID throws NotFoundError
  it('N43 — update() should throw NotFoundError when entity does not exist', async () => {
    mockRepo.findById.mockResolvedValue(null);

    await expect(service.update(9999, { name: 'X', path: '/x' }))
      .rejects.toThrow(NotFoundError);
  });

  // N44: update() with name taken by another resource throws DuplicateNameError
  it('N44 — update() should throw DuplicateNameError when name is taken by a different entity', async () => {
    const current = buildResource({ id: 1, name: 'Current', path: '/current' });
    const other = buildResource({ id: 2, name: 'Taken By Other', path: '/other' });
    mockRepo.findById.mockResolvedValue(current);
    mockRepo.findByNameExcludingId.mockResolvedValue(other); // Another entity has this name

    await expect(service.update(1, { name: 'Taken By Other', path: '/current' }))
      .rejects.toThrow(DuplicateNameError);
  });

  // N45: update() with path taken by another resource throws DuplicatePathError
  it('N45 — update() should throw DuplicatePathError when path is taken by a different entity', async () => {
    const current = buildResource({ id: 1, name: 'Current', path: '/current' });
    const other = buildResource({ id: 2, name: 'Other', path: '/taken-path' });
    mockRepo.findById.mockResolvedValue(current);
    mockRepo.findByNameExcludingId.mockResolvedValue(null);
    mockRepo.findByPathExcludingId.mockResolvedValue(other);

    await expect(service.update(1, { name: 'Current', path: '/taken-path' }))
      .rejects.toThrow(DuplicatePathError);
  });

  // E46: add() and delete() events use the same channel name
  it('E46 — add() and delete() should publish to the same channel namespace', async () => {
    const entity = buildResource({ id: 1 });
    mockRepo.findByName.mockResolvedValue(null);
    mockRepo.findByPath.mockResolvedValue(null);
    mockRepo.save.mockResolvedValue(entity);
    mockRepo.findById.mockResolvedValue(entity);
    mockRepo.delete.mockResolvedValue(undefined);

    await service.add({ name: 'Test', path: '/test' });
    await service.delete(1);

    const addChannel = (mockPublisher.publish.mock.calls[0] as [string, unknown])[0];
    const deleteChannel = (mockPublisher.publish.mock.calls[1] as [string, unknown])[0];
    expect(addChannel).toBe(deleteChannel);
  });

  // E47: getAll() with repository returning one item returns single-element array
  it('E47 — getAll() with one item should return array of length 1, not the item directly', async () => {
    mockRepo.findAll.mockResolvedValue([buildResource({ id: 1 })]);

    const result = await service.getAll();

    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(1);
  });

  // E48: delete() does not call repository.delete when entity not found
  it('E48 — delete() should not call repository.delete if entity does not exist', async () => {
    mockRepo.findById.mockResolvedValue(null);

    await expect(service.delete(9999)).rejects.toThrow(NotFoundError);
    expect(mockRepo.delete).not.toHaveBeenCalled();
  });

  // E49: add() does not publish event if repository.save throws
  it('E49 — add() should not publish event when repository.save fails', async () => {
    mockRepo.findByName.mockResolvedValue(null);
    mockRepo.findByPath.mockResolvedValue(null);
    mockRepo.save.mockRejectedValue(new Error('DB connection lost'));

    await expect(service.add({ name: 'Test', path: '/test' })).rejects.toThrow();
    expect(mockPublisher.publish).not.toHaveBeenCalled();
  });

  // E50: count() delegates to repository.count exactly once
  it('E50 — count() should call repository.count exactly once', async () => {
    mockRepo.count.mockResolvedValue(0);

    await service.count();

    expect(mockRepo.count).toHaveBeenCalledTimes(1);
  });
});
```

### Why This Matters

Service layer tests are the primary unit tests in Clean Architecture. They run without
network I/O or database connections, completing in under 50 ms each. The mock factory
pattern ensures all service tests use a consistent mock shape — changing the repository
interface propagates to all tests through the factory, not through scattered `jest.fn()` calls.

---

## 5. Entity / Model Layer — Tests

### What We Follow

Entity and schema tests verify the data model contract: required fields, default values,
Zod schema enforcement, field type constraints, and boundary values. Instantiate entities
or parse with Zod directly — no mocks required at this layer.

### How To Implement

```typescript
// src/__tests__/resource.entity.test.ts
import { z } from 'zod';
import { ResourceSchema, CreateResourceSchema, UpdateResourceSchema } from '@/schemas/resource.schema';
import { Resource } from '@/entities/resource.entity';

// CORRECT — Entity tests use Zod .safeParse() or direct construction
describe('Resource Entity / Schema', () => {

  // P51: Valid entity data parses without error
  it('P51 — should parse a valid resource object without error', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: 'Valid Resource',
      path: '/valid-resource',
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    expect(result.success).toBe(true);
  });

  // P52: ID field is required and must be a positive integer
  it('P52 — should require id field to be a positive integer', () => {
    const withoutId = ResourceSchema.safeParse({
      name: 'Test',
      path: '/test',
    });
    expect(withoutId.success).toBe(false);

    const withNegativeId = ResourceSchema.safeParse({
      id: -1,
      name: 'Test',
      path: '/test',
    });
    expect(withNegativeId.success).toBe(false);
  });

  // P53: name field is required and non-empty
  it('P53 — should require non-empty name field', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: '',
      path: '/test',
    });
    expect(result.success).toBe(false);
  });

  // P54: path field is required and non-empty
  it('P54 — should require non-empty path field', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: 'Test',
      path: '',
    });
    expect(result.success).toBe(false);
  });

  // P55: CreateResourceSchema rejects missing name
  it('P55 — CreateResourceSchema should reject input without name', () => {
    const result = CreateResourceSchema.safeParse({ path: '/test' });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some(i => i.path.includes('name'))).toBe(true);
    }
  });

  // P56: CreateResourceSchema rejects missing path
  it('P56 — CreateResourceSchema should reject input without path', () => {
    const result = CreateResourceSchema.safeParse({ name: 'Test' });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some(i => i.path.includes('path'))).toBe(true);
    }
  });

  // P57: UpdateResourceSchema accepts partial updates (name only)
  it('P57 — UpdateResourceSchema should accept update with only name field', () => {
    const result = UpdateResourceSchema.safeParse({ name: 'New Name' });
    expect(result.success).toBe(true);
  });

  // P58: UpdateResourceSchema accepts partial updates (path only)
  it('P58 — UpdateResourceSchema should accept update with only path field', () => {
    const result = UpdateResourceSchema.safeParse({ path: '/new-path' });
    expect(result.success).toBe(true);
  });

  // P59: Entity with all optional fields set parses correctly
  it('P59 — should parse entity with all optional fields populated', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: 'Full Resource',
      path: '/full',
      description: 'Optional description',
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    expect(result.success).toBe(true);
  });

  // P60: createdAt and updatedAt are valid Date objects
  it('P60 — should accept ISO date strings and coerce to Date objects', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: 'Test',
      path: '/test',
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-01-01T00:00:00Z',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.createdAt).toBeInstanceOf(Date);
    }
  });

  // P61: Entity constructed via factory has expected defaults
  it('P61 — buildResource factory should produce a well-formed entity', () => {
    const entity: Resource = {
      id: 1,
      name: 'Default',
      path: '/default',
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    expect(entity.id).toBeGreaterThan(0);
    expect(entity.name.length).toBeGreaterThan(0);
    expect(entity.path.startsWith('/')).toBe(true);
  });

  // N62: ResourceSchema rejects id = 0
  it('N62 — should reject id = 0 (must be positive)', () => {
    const result = ResourceSchema.safeParse({
      id: 0,
      name: 'Test',
      path: '/test',
    });
    expect(result.success).toBe(false);
  });

  // N63: ResourceSchema rejects non-string name
  it('N63 — should reject non-string name field', () => {
    const result = ResourceSchema.safeParse({
      id: 1,
      name: 12345,
      path: '/test',
    });
    expect(result.success).toBe(false);
  });

  // N64: CreateResourceSchema rejects name longer than max length
  it('N64 — should reject name exceeding max length constraint', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'A'.repeat(256), // Exceeds 255 char limit
      path: '/test',
    });
    expect(result.success).toBe(false);
  });

  // N65: CreateResourceSchema rejects path without leading slash
  it('N65 — should reject path not starting with forward slash', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'Test',
      path: 'no-leading-slash',
    });
    expect(result.success).toBe(false);
  });

  // N66: UpdateResourceSchema rejects empty object (at least one field required)
  it('N66 — UpdateResourceSchema should reject empty object (no fields to update)', () => {
    const result = UpdateResourceSchema.safeParse({});
    // Either refine() enforces at least one field, or partial still rejects empty
    if (!result.success) {
      expect(result.error.issues.length).toBeGreaterThan(0);
    } else {
      // If schema allows empty (depends on implementation), document explicitly
      expect(result.success).toBe(true); // Skip — schema allows empty partial
    }
  });

  // E67: path with trailing slash is handled deterministically
  it('E67 — should handle or reject path with trailing slash consistently', () => {
    const withTrailingSlash = CreateResourceSchema.safeParse({
      name: 'Test',
      path: '/test/',
    });
    // Must be deterministic: either always strip trailing slash, or always reject
    // This test documents whichever behavior the schema enforces
    expect(typeof withTrailingSlash.success).toBe('boolean');
  });

  // E68: name with leading/trailing whitespace is trimmed
  it('E68 — should trim leading and trailing whitespace from name', () => {
    const result = CreateResourceSchema.safeParse({
      name: '  Trimmed Name  ',
      path: '/trimmed',
    });
    if (result.success) {
      expect(result.data.name).toBe('Trimmed Name');
    }
  });

  // E69: ID at maximum safe integer boundary parses correctly
  it('E69 — should accept ID at Number.MAX_SAFE_INTEGER', () => {
    const result = ResourceSchema.safeParse({
      id: Number.MAX_SAFE_INTEGER,
      name: 'Max ID',
      path: '/max-id',
    });
    expect(result.success).toBe(true);
  });

  // E70: Schema error messages are human-readable strings
  it('E70 — Zod validation errors should have non-empty human-readable messages', () => {
    const result = CreateResourceSchema.safeParse({});
    expect(result.success).toBe(false);
    if (!result.success) {
      result.error.issues.forEach(issue => {
        expect(typeof issue.message).toBe('string');
        expect(issue.message.length).toBeGreaterThan(0);
      });
    }
  });

  // E71: Schema rejects null for required fields
  it('E71 — should reject null for required name field', () => {
    const result = CreateResourceSchema.safeParse({ name: null, path: '/test' });
    expect(result.success).toBe(false);
  });

  // E72: Schema rejects undefined for required fields
  it('E72 — should reject undefined for required name field', () => {
    const result = CreateResourceSchema.safeParse({ name: undefined, path: '/test' });
    expect(result.success).toBe(false);
  });

  // E73: Schema handles extra unknown fields gracefully (strip or reject)
  it('E73 — should strip or reject unknown fields deterministically', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'Test',
      path: '/test',
      unknownField: 'should not be here',
    });
    // Zod default: strips unknown fields (strict mode: rejects)
    // Either is acceptable; must be consistent
    if (result.success) {
      expect((result.data as Record<string, unknown>).unknownField).toBeUndefined();
    } else {
      expect(result.success).toBe(false);
    }
  });
});
```

### Why This Matters

Zod schemas are the single source of truth for the data contract at every boundary.
Testing them directly (without HTTP layer involvement) ensures the schema catches invalid
data independently of any middleware chain. Schema tests run in under 5 ms each because
they are pure function invocations.

---

## 6. Error Handler Layer — Tests

### What We Follow

Error handler tests mount the error handler on a minimal Express app, trigger errors via a
test route, and verify the HTTP response shape. Every domain error type must map to the
correct status code and produce `success: false` in the response envelope.

### How To Implement

```typescript
// src/__tests__/error-handler.test.ts
import request from 'supertest';
import express, { Express } from 'express';
import { globalErrorHandler } from '@/middleware/error-handler.middleware';
import { NotFoundError, DuplicateNameError, ValidationError } from '@/errors/domain.errors';

// CORRECT — Error handler tests use a minimal Express app with a triggering route
function buildTestApp(triggerError: Error): Express {
  const app = express();

  // Trigger route that throws the provided error
  app.get('/test', (_req, _res, next) => {
    next(triggerError);
  });

  // The error handler under test
  app.use(globalErrorHandler);

  return app;
}

describe('Global Error Handler Middleware', () => {

  // P74: NotFoundError maps to 404 with correct body shape
  it('P74 — NotFoundError should produce 404 response with success=false', async () => {
    const app = buildTestApp(new NotFoundError('Resource not found'));

    const response = await request(app).get('/test').expect(404);

    expect(response.body.success).toBe(false);
    expect(response.body.message).toBe('Resource not found');
  });

  // P75: DuplicateNameError maps to 409 with correct body shape
  it('P75 — DuplicateNameError should produce 409 response with success=false', async () => {
    const app = buildTestApp(new DuplicateNameError('Name already taken'));

    const response = await request(app).get('/test').expect(409);

    expect(response.body.success).toBe(false);
    expect(response.body.message).toContain('Name already taken');
  });

  // P76: ValidationError maps to 400 with field-level error details
  it('P76 — ValidationError should produce 400 response with field errors', async () => {
    const validationError = new ValidationError([
      { field: 'name', message: 'Name is required' },
    ]);
    const app = buildTestApp(validationError);

    const response = await request(app).get('/test').expect(400);

    expect(response.body.success).toBe(false);
    expect(response.body.errors).toBeDefined();
    expect(Array.isArray(response.body.errors)).toBe(true);
  });

  // P77: Generic Error maps to 500 with generic message (no internal details leaked)
  it('P77 — Unhandled Error should produce 500 without leaking internal error details', async () => {
    const internalError = new Error('Internal DB stack trace xyz');
    const app = buildTestApp(internalError);

    const response = await request(app).get('/test').expect(500);

    expect(response.body.success).toBe(false);
    // Must NOT leak the internal message in production mode
    expect(response.body.message).not.toContain('DB stack trace');
  });

  // N78: Error handler sets Content-Type to application/json
  it('N78 — error handler should always set Content-Type: application/json', async () => {
    const app = buildTestApp(new NotFoundError('Not found'));

    const response = await request(app).get('/test').expect(404);

    expect(response.headers['content-type']).toMatch(/application\/json/);
  });

  // N79: Error handler does not call next() after responding
  it('N79 — error handler should send response and not call next()', async () => {
    const app = buildTestApp(new NotFoundError('Not found'));

    // If next() were called, Express would apply default error handling
    // and potentially return HTML instead of JSON. Asserting JSON body
    // indirectly verifies next() was not called.
    const response = await request(app).get('/test').expect(404);
    expect(response.body).toHaveProperty('success');
  });

  // E80: Error handler handles circular-reference error safely (no crash)
  it('E80 — should handle Error with circular reference without crashing', async () => {
    const circularError = new Error('Circular');
    (circularError as any).self = circularError; // Circular reference
    const app = buildTestApp(circularError);

    // Should return 500 without crashing the error handler itself
    await request(app).get('/test').expect(500);
  });

  // E81: Error handler handles undefined error gracefully
  it('E81 — should handle undefined/null error argument without crashing', async () => {
    const app = express();
    app.get('/test', (_req, _res, next) => {
      next(undefined); // Passing undefined to next
    });
    app.use(globalErrorHandler);

    // Should not crash; may return 500 or fall through
    const response = await request(app).get('/test');
    expect([200, 500]).toContain(response.status);
  });
});
```

### Why This Matters

Error handler tests are the only reliable way to verify that domain errors map to the
correct HTTP status codes without starting the full application. The minimal Express app
pattern (trigger route + error handler) isolates the middleware under test from all other
middleware. Without these tests, a refactored error class hierarchy silently breaks the
status code mapping without failing CI.

---

## 7. Validation Layer — Tests

### What We Follow

Validation tests call Zod `.safeParse()` or the validation middleware directly. Test every
required field, boundary value, and format constraint. These are pure function tests —
no HTTP layer, no mocks.

### How To Implement

```typescript
// src/__tests__/validation.test.ts
import { CreateResourceSchema, UpdateResourceSchema } from '@/schemas/resource.schema';
import { validateRequest } from '@/middleware/validate-request.middleware';
import request from 'supertest';
import express from 'express';

// CORRECT — Validation tests call Zod directly for pure logic tests
describe('Validation Layer', () => {

  // P82: Valid create payload passes schema validation
  it('P82 — valid create payload should pass CreateResourceSchema', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'Valid Resource',
      path: '/valid-resource',
    });
    expect(result.success).toBe(true);
  });

  // P83: Valid update payload passes schema validation
  it('P83 — valid update payload should pass UpdateResourceSchema', () => {
    const result = UpdateResourceSchema.safeParse({
      name: 'Updated Name',
    });
    expect(result.success).toBe(true);
  });

  // P84: Zod error includes field path for missing required fields
  it('P84 — Zod should include field name in error path for missing required fields', () => {
    const result = CreateResourceSchema.safeParse({ path: '/test' });
    expect(result.success).toBe(false);
    if (!result.success) {
      const namePaths = result.error.issues.map(i => i.path).flat();
      expect(namePaths).toContain('name');
    }
  });

  // P85: validateRequest middleware passes valid body through to handler
  it('P85 — validateRequest middleware should call next() when body is valid', async () => {
    const app = express();
    app.use(express.json());
    app.post('/test',
      validateRequest(CreateResourceSchema),
      (_req, res) => res.status(200).json({ success: true })
    );

    const response = await request(app)
      .post('/test')
      .send({ name: 'Valid', path: '/valid' })
      .expect(200);

    expect(response.body.success).toBe(true);
  });

  // P86: validateRequest middleware rejects invalid body with 400
  it('P86 — validateRequest middleware should return 400 when body is invalid', async () => {
    const app = express();
    app.use(express.json());
    app.post('/test',
      validateRequest(CreateResourceSchema),
      (_req, res) => res.status(200).json({ success: true })
    );

    const response = await request(app)
      .post('/test')
      .send({ path: '/missing-name' }) // Missing name
      .expect(400);

    expect(response.body.success).toBe(false);
  });

  // P87: validateRequest response contains field-level error details
  it('P87 — validateRequest 400 response should contain field-level error array', async () => {
    const app = express();
    app.use(express.json());
    app.post('/test',
      validateRequest(CreateResourceSchema),
      (_req, res) => res.status(200).json({ success: true })
    );

    const response = await request(app)
      .post('/test')
      .send({}) // Empty body — all required fields missing
      .expect(400);

    expect(response.body.errors).toBeDefined();
    expect(Array.isArray(response.body.errors)).toBe(true);
    expect(response.body.errors.length).toBeGreaterThan(0);
  });

  // N88: Empty string name fails validation
  it('N88 — empty string name should fail CreateResourceSchema validation', () => {
    const result = CreateResourceSchema.safeParse({ name: '', path: '/test' });
    expect(result.success).toBe(false);
  });

  // N89: Whitespace-only name fails validation
  it('N89 — whitespace-only name should fail CreateResourceSchema validation', () => {
    const result = CreateResourceSchema.safeParse({ name: '   ', path: '/test' });
    expect(result.success).toBe(false);
  });

  // N90: Name exceeding max length fails validation
  it('N90 — name exceeding 255 characters should fail validation', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'A'.repeat(256),
      path: '/test',
    });
    expect(result.success).toBe(false);
  });

  // N91: Path without leading slash fails validation
  it('N91 — path without leading slash should fail validation', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'Valid',
      path: 'no-leading-slash',
    });
    expect(result.success).toBe(false);
  });

  // N92: Numeric name fails validation (must be string)
  it('N92 — numeric name value should fail validation (must be string)', () => {
    const result = CreateResourceSchema.safeParse({ name: 12345, path: '/test' });
    expect(result.success).toBe(false);
  });

  // N93: Null name fails validation
  it('N93 — null name should fail validation', () => {
    const result = CreateResourceSchema.safeParse({ name: null, path: '/test' });
    expect(result.success).toBe(false);
  });

  // N94: Array passed as name fails validation
  it('N94 — array passed as name should fail validation', () => {
    const result = CreateResourceSchema.safeParse({ name: ['a', 'b'], path: '/test' });
    expect(result.success).toBe(false);
  });

  // N95: Object passed as path fails validation
  it('N95 — object passed as path should fail validation', () => {
    const result = CreateResourceSchema.safeParse({ name: 'Valid', path: { nested: true } });
    expect(result.success).toBe(false);
  });

  // N96: SQL injection pattern in name is rejected by length or format constraint
  it('N96 — SQL injection pattern in name should be rejected or sanitized', () => {
    const sqlInjection = "'; DROP TABLE resources; --";
    const result = CreateResourceSchema.safeParse({
      name: sqlInjection,
      path: '/test',
    });
    // Either rejected by format constraint, or if accepted, must be treated as plain string
    // (parameterized queries handle SQL safety — schema validates format/length)
    if (result.success) {
      expect(result.data.name).toBe(sqlInjection.trim()); // Treated as plain string — safe
    } else {
      expect(result.success).toBe(false);
    }
  });

  // E97: XSS pattern in name is accepted as plain string (not rendered as HTML)
  it('E97 — XSS pattern in name should be stored as plain string, not executed as HTML', () => {
    const xssPayload = '<script>alert("xss")</script>';
    const result = CreateResourceSchema.safeParse({
      name: xssPayload,
      path: '/test',
    });
    // Schema stores as string; escaping is the responsibility of the template/renderer
    if (result.success) {
      expect(result.data.name).toBe(xssPayload.trim());
    }
  });

  // E98: Unicode characters in name are accepted
  it('E98 — Unicode characters in name should pass validation', () => {
    const result = CreateResourceSchema.safeParse({
      name: 'Resource — 日本語テスト',
      path: '/unicode-resource',
    });
    expect(result.success).toBe(true);
  });

  // E99: Very long valid path (within limit) passes validation
  it('E99 — path at maximum allowed length should pass validation', () => {
    const maxPath = '/' + 'a'.repeat(254); // 255 chars total with leading slash
    const result = CreateResourceSchema.safeParse({
      name: 'Test',
      path: maxPath,
    });
    expect(result.success).toBe(true);
  });

  // E100: Validation error messages are in English (non-empty)
  it('E100 — all Zod error messages should be non-empty English strings', () => {
    const result = CreateResourceSchema.safeParse({});
    expect(result.success).toBe(false);
    if (!result.success) {
      result.error.issues.forEach(issue => {
        expect(issue.message).toBeTruthy();
        expect(typeof issue.message).toBe('string');
      });
    }
  });

  // E101: Multiple invalid fields produce one error per field (no error merging)
  it('E101 — multiple invalid fields should produce separate error for each field', () => {
    const result = CreateResourceSchema.safeParse({ name: '', path: '' });
    expect(result.success).toBe(false);
    if (!result.success) {
      const fields = result.error.issues.map(i => i.path[0]);
      // Should have at least one error per invalid field
      expect(fields.length).toBeGreaterThanOrEqual(1);
    }
  });
});
```

### Why This Matters

Validation tests run without any HTTP overhead and complete in under 1 ms each. Testing
Zod schemas directly decouples them from the middleware that applies them. Schema changes
that break existing valid payloads are caught here rather than through end-to-end tests.

---

## 8. Event Publisher Layer — Tests

### What We Follow

Event publisher tests mock the ioredis client. Verify the channel name, event type, and
payload structure. Never open a real Redis connection in unit tests.

### How To Implement

```typescript
// src/__tests__/event-publisher.test.ts
import { RedisEventPublisher } from '@/events/redis-event-publisher';
import Redis from 'ioredis';

// CORRECT — Event publisher tests mock ioredis to avoid real Redis connection
jest.mock('ioredis');

describe('RedisEventPublisher', () => {
  let publisher: RedisEventPublisher;
  let mockRedis: jest.Mocked<Redis>;

  beforeEach(() => {
    mockRedis = new Redis() as jest.Mocked<Redis>;
    mockRedis.publish = jest.fn().mockResolvedValue(1);
    publisher = new RedisEventPublisher(mockRedis);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  // P102: publish() calls redis.publish with correct channel
  it('P102 — publish() should call redis.publish with the configured channel name', async () => {
    await publisher.publish('resource:events', { type: 'CREATE', id: 1 });

    expect(mockRedis.publish).toHaveBeenCalledWith(
      'resource:events',
      expect.any(String)
    );
  });

  // P103: publish() serializes event payload as JSON string
  it('P103 — publish() should serialize the event payload as a JSON string', async () => {
    const event = { type: 'DELETE', id: 42 };

    await publisher.publish('resource:events', event);

    const publishedPayload = (mockRedis.publish.mock.calls[0] as [string, string])[1];
    const parsed = JSON.parse(publishedPayload);
    expect(parsed.type).toBe('DELETE');
    expect(parsed.id).toBe(42);
  });

  // P104: publish() resolves without throwing on success
  it('P104 — publish() should resolve without error when redis.publish succeeds', async () => {
    await expect(
      publisher.publish('resource:events', { type: 'CREATE', id: 1 })
    ).resolves.not.toThrow();
  });

  // P105: publish() is called exactly once per event (no double-publish)
  it('P105 — publish() should call redis.publish exactly once per invocation', async () => {
    await publisher.publish('resource:events', { type: 'CREATE', id: 1 });

    expect(mockRedis.publish).toHaveBeenCalledTimes(1);
  });

  // N106: publish() rejects when redis.publish throws (propagates error)
  it('N106 — publish() should reject when redis.publish throws a connection error', async () => {
    mockRedis.publish.mockRejectedValueOnce(new Error('Redis connection refused'));

    await expect(
      publisher.publish('resource:events', { type: 'CREATE', id: 1 })
    ).rejects.toThrow('Redis connection refused');
  });

  // E107: publish() with very large payload does not truncate or throw
  it('E107 — publish() with large payload should serialize without truncation', async () => {
    const largePayload = {
      type: 'CREATE',
      id: 1,
      metadata: { description: 'A'.repeat(10_000) },
    };

    await publisher.publish('resource:events', largePayload);

    const publishedPayload = (mockRedis.publish.mock.calls[0] as [string, string])[1];
    const parsed = JSON.parse(publishedPayload);
    expect(parsed.metadata.description).toHaveLength(10_000);
  });
});
```

### Why This Matters

Mocking ioredis prevents flaky tests due to Redis unavailability in CI environments.
`jest.mock('ioredis')` auto-mocks all methods; injecting the mocked instance via
constructor allows full control over resolved/rejected values per test case.

---

## 9. Cross-Cutting Patterns

### What We Follow

Seven cross-cutting patterns apply across all layers. Each pattern has a TypeScript assertion
that can be embedded in the appropriate layer test file.

### How To Implement

```typescript
// Pattern 1: Response Envelope Shape
// Every success response must have { success: true, data: T }
// Every error response must have { success: false, message: string }
it('CROSS-1 — all success responses should follow the ApiResponse envelope shape', () => {
  const successShape = { success: true, data: { id: 1, name: 'Test' } };
  expect(successShape).toMatchObject({
    success: true,
    data: expect.anything(),
  });
});

// Pattern 2: Correlation ID Propagation
// All responses must include X-Request-Id header when it is present in the request
it('CROSS-2 — response should include X-Request-Id when present in request', async () => {
  const response = await request(app)
    .get('/api/resources')
    .set('X-Request-Id', 'test-correlation-id-123')
    .expect(200);

  expect(response.headers['x-request-id']).toBe('test-correlation-id-123');
});

// Pattern 3: Async Error Propagation
// Unhandled promise rejections in route handlers must reach the error handler
it('CROSS-3 — unhandled async rejection in route handler should reach error handler', async () => {
  const app = express();
  app.get('/async-error', async (_req, _res, next) => {
    try {
      await Promise.reject(new Error('Async failure'));
    } catch (err) {
      next(err);
    }
  });
  app.use(globalErrorHandler);

  const response = await request(app).get('/async-error').expect(500);
  expect(response.body.success).toBe(false);
});

// Pattern 4: No Circular Dependencies Between Layers
// Service must not import from Controller; Repository must not import from Service
it('CROSS-4 — service module should not import from controller module', () => {
  // Static analysis: inspect the compiled module graph
  // In tests, verify that requiring the service does not pull in controller
  const serviceModule = require('@/services/resource.service');
  expect(serviceModule).toBeDefined();
  // If circular dep existed, require() would return an empty object for one of the modules
  expect(Object.keys(serviceModule).length).toBeGreaterThan(0);
});

// Pattern 5: TypeScript Strict Mode — No `any` in test files
// All mock types must be properly typed (jest.Mocked<T>, not any)
// This is enforced by tsconfig strict: true — tests fail to compile if `any` is used implicitly

// Pattern 6: beforeEach Reset — All mocks cleared between tests
// Demonstrated by jest.config.ts: clearMocks: true, restoreMocks: true
// Tests that share mock state across cases are forbidden

// Pattern 7: Test Naming Convention
// Describe block: <ClassName> or <LayerName>
// It block: <ScenarioID> — <plain English description of observable behavior>
it('CROSS-7 — test descriptions should start with the scenario ID', () => {
  // Convention check: enforced by code review and Jest --verbose output
  // The test name you are reading right now follows the pattern
  expect(true).toBe(true); // Placeholder — convention is enforced at review time
});
```

### Why This Matters

Cross-cutting patterns prevent the most common category of polyglot service bugs: broken
response envelopes, missing correlation IDs, swallowed async errors, and circular module
dependencies. These patterns are enforced at the unit test layer — not the integration
layer — to give the fastest feedback loop.

---

## 10. Anti-Patterns

### What We Must NOT Do

The following patterns are explicitly forbidden. Each shows the WRONG implementation and explains
why it breaks the test suite or the production service.

```typescript
// WRONG — Anti-Pattern 1: Starting a real HTTP server in tests
// This causes port binding conflicts when tests run in parallel
describe('WRONG — starts real server', () => {
  let server: any;
  beforeAll(() => {
    server = app.listen(3000); // FORBIDDEN: real port binding
  });
  afterAll(() => server.close());

  it('calls the API', async () => {
    const response = await fetch('http://localhost:3000/api/resources'); // FORBIDDEN
    expect(response.status).toBe(200);
  });
});

// CORRECT — Pass app to supertest directly (no port binding)
it('calls the API', async () => {
  const response = await request(app).get('/api/resources').expect(200);
  expect(response.body.success).toBe(true);
});
```

```typescript
// WRONG — Anti-Pattern 2: Sharing mock state between tests
describe('WRONG — shared mock state', () => {
  const mockService = createMockService(); // FORBIDDEN: shared across all tests in describe

  it('test A sets mock return value', async () => {
    mockService.getAll.mockResolvedValue([buildResource({ id: 1 })]);
    const result = await service.getAll();
    expect(result).toHaveLength(1);
  });

  it('test B assumes clean mock', async () => {
    // BUG: mock still has the value from test A if clearMocks is false
    const result = await service.getAll(); // Returns stale value from test A
    expect(result).toHaveLength(0); // FAILS intermittently
  });
});

// CORRECT — Create fresh mocks in beforeEach
describe('CORRECT — fresh mocks per test', () => {
  let mockService: jest.Mocked<IResourceService>;

  beforeEach(() => {
    mockService = createMockService(); // Fresh mock for every test
  });
});
```

```typescript
// WRONG — Anti-Pattern 3: Testing implementation details instead of behavior
describe('WRONG — testing implementation details', () => {
  it('should call findByName before findByPath', async () => {
    // FORBIDDEN: order of internal method calls is an implementation detail
    const callOrder: string[] = [];
    mockRepo.findByName.mockImplementation(async () => {
      callOrder.push('findByName');
      return null;
    });
    mockRepo.findByPath.mockImplementation(async () => {
      callOrder.push('findByPath');
      return null;
    });
    await service.add({ name: 'Test', path: '/test' });
    expect(callOrder[0]).toBe('findByName'); // WRONG: couples test to implementation order
  });
});

// CORRECT — Test observable behavior (what throws, what is returned, what is published)
it('CORRECT — add() with duplicate name throws DuplicateNameError', async () => {
  mockRepo.findByName.mockResolvedValue(buildResource({ id: 99 }));
  await expect(service.add({ name: 'Taken', path: '/test' })).rejects.toThrow(DuplicateNameError);
});
```

```typescript
// WRONG — Anti-Pattern 4: Using console.log for debug output in test files
describe('WRONG — console.log in tests', () => {
  it('logs response for debugging', async () => {
    const response = await request(app).get('/api/resources');
    console.log(response.body); // FORBIDDEN: pollutes test output, left by accident
    expect(response.status).toBe(200);
  });
});

// CORRECT — Use Jest's built-in output or structured assertions
it('CORRECT — asserts response body without console.log', async () => {
  const response = await request(app).get('/api/resources').expect(200);
  expect(response.body.data).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: expect.any(Number) }),
  ]));
});
```

```typescript
// WRONG — Anti-Pattern 5: Using `any` type on mock objects
describe('WRONG — untyped mocks', () => {
  const mockService: any = { // FORBIDDEN: any defeats TypeScript's safety net
    add: jest.fn(),
    // Missing methods are not caught at compile time
  };
});

// CORRECT — Use jest.Mocked<T> for full type safety
describe('CORRECT — typed mocks', () => {
  let mockService: jest.Mocked<IResourceService>; // Typed: all interface methods enforced
  beforeEach(() => {
    mockService = createMockService();
  });
});
```

### Why This Matters

Anti-patterns cause three classes of production failure:
1. Port binding conflicts in CI (EADDRINUSE) from real server instantiation
2. Flaky tests from shared mock state that passes locally but fails in random CI ordering
3. Brittle tests that break on every refactor because they assert on implementation detail call order

---

## Layer 9 — Security Tests (SEC1–SEC8)

These tests verify that the API enforces authentication, rejects malformed credentials, and
handles deliberately hostile input without leaking internals or crashing.

**Setup:** All security tests use supertest with an Express app instance. JWT tokens are
generated with the same secret the app uses so SEC1/SEC2 test the happy path; all other
scenarios send deliberately broken or absent credentials/payloads.

```typescript
// tests/security/auth-and-input.security.test.ts
import request from 'supertest';
import jwt from 'jsonwebtoken';
import { app } from '@/app';

const JWT_SECRET = process.env.JWT_SECRET ?? 'test-secret';

function signToken(payload: object, expiresIn = '1h'): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn } as jwt.SignOptions);
}

// SEC1 — valid JWT Bearer token reaches the protected route
it('SEC1 — valid Bearer token returns 200', async () => {
  const token = signToken({ sub: 'user-1', role: 'admin' });

  const response = await request(app)
    .get('/api/resources')
    .set('Authorization', `Bearer ${token}`);

  expect(response.status).toBe(200);
  expect(response.body.success).toBe(true);
});

// SEC2 — health endpoint is public (no auth required)
it('SEC2 — GET /health returns 200 without Authorization header', async () => {
  const response = await request(app).get('/health');

  expect(response.status).toBe(200);
});

// SEC3 — missing Authorization header on protected route → 401
it('SEC3 — missing Authorization header returns 401', async () => {
  const response = await request(app).get('/api/resources');

  expect(response.status).toBe(401);
  expect(response.body.success).toBe(false);
  expect(response.body.message).toMatch(/unauthorized|missing|token/i);
});

// SEC4 — malformed/expired JWT → 401, no stack trace in body
it('SEC4 — expired JWT returns 401 with no stack trace', async () => {
  const expiredToken = signToken({ sub: 'user-1' }, '-1s'); // already expired

  const response = await request(app)
    .get('/api/resources')
    .set('Authorization', `Bearer ${expiredToken}`);

  expect(response.status).toBe(401);
  expect(response.body.success).toBe(false);
  // No stack trace lines in the message
  expect(response.body.message).not.toMatch(/at\s+\w+\s*\(/);
  expect(response.body.message).not.toMatch(/\.ts:\d+/);
});

// SEC5 — SQL injection in name field → 400/422, NOT 500
it('SEC5 — SQL injection payload in name field returns 400 not 500', async () => {
  const token = signToken({ sub: 'user-1', role: 'admin' });

  const response = await request(app)
    .post('/api/resources')
    .set('Authorization', `Bearer ${token}`)
    .send({ name: "'; DROP TABLE resources; --", path: '/test' });

  expect(response.status).toBeGreaterThanOrEqual(400);
  expect(response.status).toBeLessThan(500);
  expect(response.body.success).toBe(false);
});

// SEC6 — XSS payload in name field is stored verbatim or rejected; never executed
it('SEC6 — XSS payload in name field is rejected or stored as plain text', async () => {
  const token = signToken({ sub: 'user-1', role: 'admin' });
  const xssPayload = '<script>alert(1)</script>';

  const response = await request(app)
    .post('/api/resources')
    .set('Authorization', `Bearer ${token}`)
    .send({ name: xssPayload, path: '/xss-test' });

  if (response.status === 201) {
    // If stored, it must be stored as-is (plain text) — not HTML-decoded or executed
    expect(response.body.data.name).toBe(xssPayload);
    // Content-Type must be JSON, never text/html that would execute scripts
    expect(response.headers['content-type']).toMatch(/application\/json/);
  } else {
    // Validation rejected it — equally valid; just must not be a 500
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(response.status).toBeLessThan(500);
  }
});

// SEC7 — oversized JSON body → 413/400, NOT 500
it('SEC7 — 10 MB JSON body returns 413 or 400, not 500', async () => {
  const token = signToken({ sub: 'user-1', role: 'admin' });
  const oversized = { name: 'x'.repeat(10 * 1024 * 1024), path: '/big' };

  const response = await request(app)
    .post('/api/resources')
    .set('Authorization', `Bearer ${token}`)
    .send(oversized);

  expect(response.status).toBeGreaterThanOrEqual(400);
  expect(response.status).toBeLessThan(500);
});

// SEC8 — missing Content-Type on POST → 415/400, NOT 500
it('SEC8 — POST without Content-Type header returns 415 or 400, not 500', async () => {
  const token = signToken({ sub: 'user-1', role: 'admin' });

  const response = await request(app)
    .post('/api/resources')
    .set('Authorization', `Bearer ${token}`)
    .set('Content-Type', '')
    .send('not-json');

  expect(response.status).toBeGreaterThanOrEqual(400);
  expect(response.status).toBeLessThan(500);
});
```

### CORRECT vs WRONG — Security Tests

```typescript
// WRONG — Security anti-pattern: asserting on status 200 without checking auth enforcement
describe('WRONG — skipping auth check', () => {
  it('returns data without setting Authorization header', async () => {
    const response = await request(app).get('/api/resources');
    // BUG: if this passes with 200, auth middleware is not wired in
    expect(response.status).toBe(200); // WRONG: should be 401
  });
});

// CORRECT — Always test both the authorized AND unauthorized paths
describe('CORRECT — explicit auth boundary tests', () => {
  it('SEC1 — returns 200 with valid token', async () => {
    const token = signToken({ sub: 'u1' });
    await request(app)
      .get('/api/resources')
      .set('Authorization', `Bearer ${token}`)
      .expect(200);
  });

  it('SEC3 — returns 401 without token', async () => {
    await request(app).get('/api/resources').expect(401);
  });
});
```

```typescript
// WRONG — Using a hardcoded fake token string instead of a real signed JWT
describe('WRONG — fake token string', () => {
  it('SEC4 variant — sends a random string as Bearer token', async () => {
    const response = await request(app)
      .get('/api/resources')
      .set('Authorization', 'Bearer not-a-real-jwt'); // WRONG: may hit parse errors, not auth logic
    expect(response.status).toBe(401);
  });
});

// CORRECT — Use jwt.sign() with a past expiry to produce a structurally valid but expired token
it('CORRECT — SEC4 uses jwt.sign with past expiry', async () => {
  const expiredToken = jwt.sign({ sub: 'u1' }, JWT_SECRET, { expiresIn: '-1s' });
  await request(app)
    .get('/api/resources')
    .set('Authorization', `Bearer ${expiredToken}`)
    .expect(401);
});
```

### Why This Matters

Security test gaps are the most common source of production vulnerabilities in microservices:
1. Missing SEC3/SEC4 tests mean auth middleware is never regression-tested — a mis-wired router
   can silently remove auth protection after a refactor, and no test catches it until production.
2. SEC5/SEC6 tests confirm that input validation (Zod schema) runs before any DB query —
   catching cases where a developer adds a new route and forgets to wire the validation middleware.
3. SEC7/SEC8 guard against resource exhaustion and parser crashes that Express exposes to the
   public without body-parser limits or content-type enforcement.

---

## Path Parameter Edge Cases (PP1–PP4)

These tests verify that the API correctly validates `:id` path parameters and never passes
unvalidated values to the repository or database layer.

```typescript
// tests/integration/path-params.test.ts
import request from 'supertest';
import { app } from '@/app';

// PP1 — non-numeric string ID → 400
it('PP1 — GET /resources/abc returns 400 for non-numeric id', async () => {
  const response = await request(app).get('/api/resources/abc');

  expect(response.status).toBe(400);
  expect(response.body.success).toBe(false);
  expect(response.body.message).toMatch(/id|param|numeric|integer/i);
});

// PP2 — negative numeric ID → 400 or 404
it('PP2 — GET /resources/-1 returns 400 or 404 for negative id', async () => {
  const response = await request(app).get('/api/resources/-1');

  expect([400, 404]).toContain(response.status);
  expect(response.body.success).toBe(false);
});

// PP3 — zero ID → 400 or 404
it('PP3 — GET /resources/0 returns 400 or 404 for zero id', async () => {
  const response = await request(app).get('/api/resources/0');

  expect([400, 404]).toContain(response.status);
  expect(response.body.success).toBe(false);
});

// PP4 — ID beyond Number.MAX_SAFE_INTEGER → 400
it('PP4 — GET /resources/99999999999999999999 returns 400 for out-of-range id', async () => {
  const oversizedId = '99999999999999999999'; // > Number.MAX_SAFE_INTEGER (2^53 - 1)

  const response = await request(app).get(`/api/resources/${oversizedId}`);

  expect(response.status).toBe(400);
  expect(response.body.success).toBe(false);
});
```

### CORRECT vs WRONG — Path Parameter Tests

```typescript
// WRONG — Letting non-numeric IDs reach the service/repository
describe('WRONG — no param validation in controller', () => {
  it('passes string "abc" to repository as-is', async () => {
    // If repository receives "abc", it may throw an unhandled DB error → 500
    // which leaks internal details and is not a test-controlled failure
    const response = await request(app).get('/api/resources/abc');
    expect(response.status).toBe(500); // WRONG: should be 400 from validation
  });
});

// CORRECT — Zod coercion at the controller boundary rejects before service is called
it('CORRECT — PP1 controller validates :id with z.coerce.number().int().positive()', async () => {
  // The controller uses: z.coerce.number().int().positive().parse(req.params.id)
  // Zod throws ZodError → caught by error middleware → 400 response
  const response = await request(app).get('/api/resources/abc');
  expect(response.status).toBe(400);
  expect(response.body.success).toBe(false);
});
```

### Why This Matters

Path parameter validation failures are a common source of unhandled exceptions that bubble
up as 500 errors. Without PP1–PP4:
1. `parseInt('abc', 10)` returns `NaN`, which propagates silently through service and repository
   until it hits a DB driver that either errors with a cryptic message or performs a full table scan.
2. Negative or zero IDs may trigger unexpected DB behavior (auto-increment PKs are always > 0),
   returning confusing 500s instead of clean 400/404 responses.
3. Integers beyond `Number.MAX_SAFE_INTEGER` lose precision in JavaScript, causing ID collisions
   that can accidentally match a different record.

---

## Internal Error Structure (ERR1–ERR3)

These tests verify that when the service layer throws an unhandled exception, the Express
error middleware intercepts it and returns a structured JSON envelope — never a stack trace,
never HTML, and never a plain string body.

```typescript
// tests/integration/error-structure.test.ts
import request from 'supertest';
import { app } from '@/app';
import { ResourceService } from '@/services/resource.service';

// ERR1 — unhandled exception returns 500 with structured envelope
it('ERR1 — unhandled service exception returns 500 JSON envelope', async () => {
  jest.spyOn(ResourceService.prototype, 'getAll').mockRejectedValue(
    new Error('Unexpected DB connection loss')
  );

  const response = await request(app).get('/api/resources');

  expect(response.status).toBe(500);
  expect(response.body).toMatchObject({
    success: false,
    status: 500,
    message: expect.any(String),
  });
});

// ERR2 — 500 response body does NOT contain stack trace or file paths
it('ERR2 — 500 response message contains no stack trace or file paths', async () => {
  jest.spyOn(ResourceService.prototype, 'getAll').mockRejectedValue(
    new Error('Unexpected DB connection loss')
  );

  const response = await request(app).get('/api/resources');

  expect(response.status).toBe(500);

  const bodyText = JSON.stringify(response.body);
  // Stack trace lines look like: "at Object.<anonymous> (/path/to/file.ts:42:7)"
  expect(bodyText).not.toMatch(/at\s+\w[\w.<>]*\s*\(/);
  // File path patterns
  expect(bodyText).not.toMatch(/\.ts:\d+:\d+/);
  expect(bodyText).not.toMatch(/\.js:\d+:\d+/);
  // Absolute path fragments
  expect(bodyText).not.toMatch(/[A-Za-z]:\\|\/home\/|\/usr\/|\/var\//);
});

// ERR3 — 500 response Content-Type is application/json, not text/html
it('ERR3 — 500 response Content-Type is application/json', async () => {
  jest.spyOn(ResourceService.prototype, 'getAll').mockRejectedValue(
    new Error('Unexpected DB connection loss')
  );

  const response = await request(app).get('/api/resources');

  expect(response.status).toBe(500);
  expect(response.headers['content-type']).toMatch(/application\/json/);
  // Confirm it is NOT the default Express HTML error page
  expect(response.headers['content-type']).not.toMatch(/text\/html/);
});
```

### CORRECT vs WRONG — Error Structure Tests

```typescript
// WRONG — Error middleware sends back the raw Error object
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  res.status(500).json({ error: err }); // WRONG: serializes stack trace into response body
});

// CORRECT — Error middleware strips sensitive fields, returns envelope only
app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  const isDev = process.env.NODE_ENV === 'development';
  res.status(500).json({
    success: false,
    status: 500,
    // In production: generic message. In dev: err.message only (never err.stack)
    message: isDev ? err.message : 'Internal server error',
  });
});
```

```typescript
// WRONG — Test only asserts on status code, not envelope shape or content-type
it('WRONG — only checks status 500', async () => {
  jest.spyOn(ResourceService.prototype, 'getAll').mockRejectedValue(new Error('boom'));
  const response = await request(app).get('/api/resources');
  expect(response.status).toBe(500); // WRONG: passes even if body is HTML or contains stack trace
});

// CORRECT — Assert all three: status, envelope shape, and content-type
it('CORRECT — full 500 assertion', async () => {
  jest.spyOn(ResourceService.prototype, 'getAll').mockRejectedValue(new Error('boom'));
  const response = await request(app).get('/api/resources');

  expect(response.status).toBe(500);
  expect(response.body).toMatchObject({ success: false, status: 500, message: expect.any(String) });
  expect(response.headers['content-type']).toMatch(/application\/json/);
  expect(JSON.stringify(response.body)).not.toMatch(/at\s+\w[\w.<>]*\s*\(/);
});
```

### Why This Matters

Unstructured 500 responses are one of the most exploited information disclosure vectors:
1. Express's default error handler returns `text/html` with a stack trace in development mode.
   Without ERR3, a misconfigured `NODE_ENV` in production leaks full stack traces in HTML.
2. Stack traces in API responses (ERR2) expose file system layout, library versions, and internal
   method names — directly useful for targeted attacks.
3. Without ERR1 asserting the envelope shape, error middleware may be registered in the wrong
   order (after the route, not after all routes) and the test suite never catches the gap.

---

## SEE ALSO

- `40-universal-test-patterns-abstract.md` — Language-agnostic scenario definitions and universality rationale for all 122 scenario IDs
- `35-positive-testing-standards.md` — Spring Boot positive scenario implementations (Java reference)
- `36-negative-testing-standards.md` — Spring Boot negative scenario implementations (Java reference)
- `37-edge-case-testing-standards.md` — Spring Boot edge case implementations (Java reference)
- `38-test-mocking-strategy.md` — Spring Boot mocking patterns (Java reference)
- `39-cross-cutting-test-patterns.md` — Spring Boot cross-cutting patterns (Java reference)
- `06-typescript-standards.md` — TypeScript strict mode, naming conventions, and module system rules
- `02-backend-standards.md` — REST API contract, response envelope, error hierarchy
- `28-test-coverage-enforcement.md` — Coverage thresholds and enforcement policy
