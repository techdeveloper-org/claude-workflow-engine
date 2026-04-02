---
description: "Level 2.1 - Frontend package structure, folder taxonomy, and code patterns (Angular/React/Node.js)"
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
  - "src/**/*.js"
  - "src/**/*.jsx"
  - "app/**/*.ts"
  - "app/**/*.tsx"
  - "pages/**/*.tsx"
  - "controllers/**/*.ts"
priority: high
conditional: "Frontend or Node.js project detected (package.json with angular/react/express/nestjs)"
---

# Frontend Package Structure (Level 2.1 - Angular/React/Node.js)

**PURPOSE:** Enforce consistent folder taxonomy, code patterns, and separation of concerns across Angular, React, and Node.js projects. This rule defines WHAT folders to create, WHEN to create them, and HOW code inside them should be structured.

**EXTENDS:** rule-04 (Frontend Standards) with specific package structure and cross-cutting code patterns.

---

## 1. Canonical Folder Structure

Angular naming is canonical. React and Node.js equivalents are shown in Section 2.

```
src/app/
|-- components/                        [MANDATORY] All UI components organized by role
|   |-- admin/                         [CONDITIONAL: admin portal exists]
|   |   |-- dashboard/
|   |   |-- {entity}-list/             CRUD list pages
|   |   |-- add-{entity}/              Create pages
|   |   |-- edit-{entity}/             Edit pages
|   |   |-- dialogs/                   [CONDITIONAL: Material/modal dialogs used]
|   |   |   +-- {entity}-dialog/
|   |   +-- Charts/                    [CONDITIONAL: analytics dashboard exists]
|   |       +-- {metric}-chart/
|   |-- user/                          [CONDITIONAL: customer-facing portal exists]
|   |   |-- navbar/
|   |   |-- footer/
|   |   |-- home/
|   |   |-- cart/
|   |   |-- checkout/
|   |   |-- profile/
|   |   +-- dialogs/                   [CONDITIONAL: Material/modal dialogs used]
|   +-- (flat components if single-role app)
|-- core/                              [MANDATORY] Infrastructure (session, config, app init)
|   +-- services/
|       +-- session-timer.service.ts
|-- services/                          [MANDATORY] API integration and business logic
|   |-- auth.interceptor.ts            [CONDITIONAL: JWT/token auth enabled]
|   |-- shared/                        [MANDATORY] Cross-role services
|   |   |-- http.service.ts            Base HTTP wrapper (Pattern 1)
|   |   |-- {entity}.service.ts        Domain services with dedup (Pattern 2)
|   |   +-- nav-menu.service.ts
|   |-- admin/                         [CONDITIONAL: admin-specific API calls]
|   +-- user/                          [CONDITIONAL: customer-specific API calls]
|       |-- auth.service.ts            BehaviorSubject state (Pattern 3)
|       |-- cart.service.ts
|       +-- cart-sync.service.ts
|-- guards/                            [CONDITIONAL: route-level auth exists]
|   |-- auth.guard.ts                  Functional guard (Pattern 5)
|   +-- admin.guard.ts
|-- dto/                               [MANDATORY] Pure TypeScript interfaces for API contracts
|   |-- shared/                        Cross-app DTOs
|   |   |-- api-response-dto.ts        Generic wrapper: ApiResponseDto<T>
|   |   |-- {entity}-dto.ts            Entity response DTOs
|   |   +-- auth-dto.ts
|   +-- admin/                         [CONDITIONAL: admin-specific response shapes]
|-- forms/                             [MANDATORY] Form interfaces -- NEVER mix with dto/
|   |-- shared/
|   |-- admin/                         [CONDITIONAL: admin create/edit forms]
|   +-- user/                          [CONDITIONAL: user forms]
|-- pipes/                             [CONDITIONAL: custom template transforms needed]
|   +-- safe-image-url.pipe.ts
|-- constants/                         [MANDATORY] Centralized app-wide constants
|   +-- api-endpoints.ts               Parameterized endpoint functions (Pattern 4)
+-- shared/                            [MANDATORY] Reusable cross-feature components
    +-- components/
        +-- session-warning-modal/
```

---

## 2. Cross-Framework Mapping

| Angular (canonical) | React | Express | NestJS | Notes |
|---------------------|-------|---------|--------|-------|
| `components/` | `components/` + `pages/` | `controllers/` | `*.controller.ts` | Route handlers / UI components |
| `services/` | `services/` or `api/` | `services/` | `*.service.ts` | Business logic layer |
| `dto/` | `types/` or `interfaces/` | `dto/` | `dto/` | Pure interfaces for API contracts |
| `forms/` | `schemas/` (Zod/Yup) | `validators/` | `pipes/` + class-validator | Request/form validation |
| `guards/` | `guards/` (wrapper components) | `middleware/` | `guards/` | Auth/role protection |
| `interceptors/` | Axios interceptors | `middleware/` | `interceptors/` | Request/response transforms |
| `pipes/` | `shared/utils/` | N/A | `pipes/` | Data transforms (Angular/NestJS native) |
| `constants/` | `constants/` | `constants/` | `constants/` | Identical across all |
| `core/` | `core/` or `lib/` | `config/` | `config/` | Infrastructure, app init |
| `shared/` | `shared/` or `common/` | `shared/` or `utils/` | `common/` | Reusable utilities |
| N/A | `hooks/` | N/A | N/A | React-only: custom hooks |
| N/A | `context/` | N/A | N/A | React-only: Context providers |

---

## 3. DTO and Form Interface Separation

### What We Follow
DTOs define API response shapes. Form interfaces define what the user fills in. These are NEVER the same type.

### How To Implement

```typescript
// dto/shared/api-response-dto.ts
export interface ApiResponseDto<T> {
  readonly success: boolean;
  readonly message: string;
  readonly data: T;
  readonly status: number;
}

// dto/shared/product-dto.ts -- API response shape
export interface ProductDto {
  readonly id: number;
  readonly name: string;
  readonly description: string;
  readonly price: number;
  readonly categoryId: number;
  readonly createdAt: string;
  readonly updatedAt: string;
}

// forms/admin/product-form.ts -- form input shape (NO id, timestamps)
export interface ProductForm {
  name: string;
  description: string;
  price: number;
  categoryId: number;
}
```

React equivalent: `types/shared/product.types.ts` for DTO, `schemas/product.schema.ts` for Zod schema:

```typescript
// schemas/product.schema.ts (React with Zod)
import { z } from 'zod';
export const productFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  price: z.number().positive(),
});
export type ProductFormValues = z.infer<typeof productFormSchema>;
```

### Why This Matters
Mixing them causes server-generated fields (`id`, `createdAt`) to appear in create forms. The backend rejects or corrupts data when `id: null` is submitted on create requests.

**See also:** rule-15 (Java backend DTO/Form separation equivalent)

---

## 4. Service Layer Patterns

### Pattern 1: Base HTTP Wrapper

Every domain service delegates HTTP calls to a centralized typed wrapper. Never inject `HttpClient`/`axios` directly in domain services.

```typescript
// Angular: services/shared/http.service.ts
@Injectable({ providedIn: 'root' })
export class HttpService {
  constructor(private readonly http: HttpClient) {}

  private headers(): HttpHeaders {
    const token = localStorage.getItem('token') ?? '';
    return new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'X-Project-Name': environment.projectName,
    });
  }

  get<T>(url: string): Observable<T> {
    return this.http.get<T>(url, { headers: this.headers() });
  }

  post<T>(url: string, body: unknown): Observable<T> {
    return this.http.post<T>(url, body, { headers: this.headers() });
  }
}
```

React equivalent: Axios instance with interceptors in `services/shared/apiClient.ts`.

### Pattern 2: Request Deduplication (Angular)

Domain services that fire the same HTTP call from multiple components must deduplicate concurrent requests using `finalize()` + `shareReplay()`.

```typescript
// services/shared/category.service.ts
@Injectable({ providedIn: 'root' })
export class CategoryService {
  private inFlight$: Observable<ApiResponseDto<CategoryDto[]>> | undefined;

  constructor(private readonly httpService: HttpService) {}

  getCategoryList(): Observable<ApiResponseDto<CategoryDto[]>> {
    if (!this.inFlight$) {
      this.inFlight$ = this.httpService
        .get<ApiResponseDto<CategoryDto[]>>(API_ENDPOINTS.CATEGORIES)
        .pipe(
          finalize(() => { this.inFlight$ = undefined; }),
          shareReplay({ bufferSize: 1, refCount: true }),
        );
    }
    return this.inFlight$;
  }
}
```

React equivalent: TanStack Query handles deduplication automatically per query key.

### Pattern 3: BehaviorSubject State Management (Angular)

Services holding reactive state expose read-only `Observable` from private `BehaviorSubject`. State persists to `localStorage`.

```typescript
// services/user/auth.service.ts
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly _loggedIn$ = new BehaviorSubject<boolean>(!!localStorage.getItem('token'));
  private readonly _currentUser$ = new BehaviorSubject<CustomerDto | null>(null);

  readonly loggedIn$ = this._loggedIn$.asObservable();
  readonly currentUser$ = this._currentUser$.asObservable();

  setSession(token: string, user: CustomerDto): void {
    localStorage.setItem('token', token);
    this._loggedIn$.next(true);
    this._currentUser$.next(user);
  }

  logout(): void {
    localStorage.clear();
    this._loggedIn$.next(false);
    this._currentUser$.next(null);
  }
}
```

React equivalent: `Context + useReducer` or Zustand store in `context/AuthContext.tsx`.

### Pattern 4: Constants with Parameterized Functions

All API URLs live in one file. Path parameters are typed functions, never inline string concatenation.

```typescript
// constants/api-endpoints.ts
const BASE_URL = '/api/v1';

export const API_ENDPOINTS = {
  CATEGORIES:            `${BASE_URL}/categories`,
  CATEGORY_BY_ID:        (id: number) => `${BASE_URL}/categories/${id}`,
  PRODUCTS_BY_CATEGORY:  (categoryId: number) => `${BASE_URL}/products/by/category/${categoryId}`,
  PRODUCT_IMAGE:         (productId: number, filename: string) =>
    `${BASE_URL}/products/images/${productId}/${encodeURIComponent(filename)}`,
} as const;
```

### Pattern 5: Functional Guards (Angular 17+)

Route guards must use the functional `CanActivateFn` pattern. Class-based guards are deprecated.

```typescript
// guards/auth.guard.ts
export const authGuard: CanActivateFn = (_route, _state) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  return authService.loggedIn$.pipe(
    map(loggedIn => loggedIn ? true : router.createUrlTree(['/login'])),
  );
};
```

React equivalent: wrapper component `<AuthGuard>` that checks `useAuth()` and renders `<Navigate>`.

Express equivalent: `authMiddleware` function checking `req.headers.authorization`.

NestJS equivalent: `@Injectable() class AuthGuard implements CanActivate`.

### Pattern 6: Auth Interceptor with Token Refresh Queue

HTTP interceptors must skip auth-free URLs (login, refresh, logout), attach `Authorization` + custom headers, and handle 401 with a single-flight token refresh queue so concurrent requests wait for the new token instead of each triggering a separate refresh.

```typescript
// Angular: services/auth.interceptor.ts
const SKIP_URLS = ['/auth/login', '/auth/refresh', '/auth/logout'];

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (SKIP_URLS.some(url => req.url.includes(url))) return next(req);

  const authService = inject(AuthService);
  const token = localStorage.getItem('accessToken');
  const authReq = req.clone({
    setHeaders: {
      Authorization: `Bearer ${token}`,
      'X-Project-Name': environment.projectName,
    },
  });

  return next(authReq).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status === 401) {
        return authService.refreshToken().pipe(
          switchMap(newToken => {
            const retry = req.clone({
              setHeaders: { Authorization: `Bearer ${newToken}` },
            });
            return next(retry);
          }),
        );
      }
      return throwError(() => err);
    }),
  );
};
```

React equivalent: Axios response interceptor with `axios.interceptors.response.use()` calling refresh on 401.

Express equivalent: `auth.middleware.ts` verifying JWT and calling `next()` or returning 401.

### Pattern 7: `core/` vs `services/` Distinction

`core/` holds **infrastructure** that the app needs to function (session management, app initializer, global config). `services/` holds **business logic** and API calls. Never mix them.

```
core/                               INFRASTRUCTURE — app plumbing
  services/
    session-timer.service.ts         JWT expiry countdown (RxJS interval)
    app-initializer.service.ts       Startup bootstrap (load config, check auth)
    error-tracking.service.ts        Global error reporter (Sentry/LogRocket)

services/                            BUSINESS LOGIC — domain API calls
  shared/
    http.service.ts                  Base HTTP wrapper
    product.service.ts               Product CRUD
    order.service.ts                 Order CRUD
  user/
    auth.service.ts                  Login/logout/refresh
    cart.service.ts                  Cart state
```

Rule of thumb: if it talks to a **business API endpoint**, it goes in `services/`. If it manages **app-level plumbing** (timers, config, error tracking), it goes in `core/`.

### Pattern 8: Environment Configuration

Typed environment config with all external URLs centralized. Never hardcode URLs or keys in services.

```typescript
// Angular: environments/environment.ts
export const environment = {
  production: false,
  apiBaseUrl: '',                              // relative (uses proxy in dev)
  projectName: 'my-app',
  authEndpoints: {
    login: '/api/v1/auth/login',
    refresh: '/api/v1/auth/refresh',
    logout: '/api/v1/auth/logout',
  },
  razorpayKeyId: 'rzp_test_xxx',              // public key only, never secret
};

// React: .env + typed config
// VITE_API_URL=https://api.example.com
// config/env.ts
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_URL,
  projectName: import.meta.env.VITE_PROJECT_NAME ?? 'my-app',
} as const;

// Node.js: config/env.ts (Zod-validated)
const envSchema = z.object({
  PORT: z.coerce.number().default(3000),
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
});
export const env = envSchema.parse(process.env);
```

**See also:** rule-18 (Java backend service layer conventions equivalent)

---

## 5. Node.js Backend Equivalents

### Express Folder Structure

```
src/
|-- controllers/         [maps to: components/] Thin route handlers
|   |-- admin/
|   +-- user/
|-- services/            [same] Business logic
|   |-- shared/
|   |-- admin/
|   +-- user/
|-- middleware/           [maps to: guards/ + interceptors/]
|   |-- auth.middleware.ts
|   +-- error-handler.middleware.ts
|-- dto/                 [same] Pure TypeScript interfaces
|-- validators/          [maps to: forms/] Zod/Joi request validation
|-- routes/              Route definitions
|-- constants/           [same]
|-- config/              [maps to: core/] Env validation, DB config
+-- shared/              [same] Reusable utilities
```

### NestJS Folder Structure

NestJS mirrors Angular naturally -- modules, services, guards align 1:1.

```
src/
|-- modules/{domain}/    Each domain: module.ts + controller.ts + service.ts + dto/
|-- common/              [maps to: shared/] dto/, guards/, interceptors/, pipes/, filters/, decorators/
|-- config/              [maps to: core/]
+-- constants/           [same]
```

---

## 6. Decision Tree: When To Create Which Folder

- **Always create:** `components/`, `services/shared/`, `dto/shared/`, `forms/`, `constants/`, `shared/`, `core/`
- **Does the project have authentication?**
  - YES -> create `guards/`, `services/user/auth.service.ts`, add `auth.interceptor.ts`
  - NO -> skip guards/ entirely
- **Does the project have admin + customer portals?**
  - YES -> create `components/admin/`, `components/user/`, `services/admin/`, `services/user/`, `dto/admin/`
  - NO -> put components flat under `components/`, services flat under `services/shared/`
- **Does the project use Material dialogs or modals?**
  - YES -> create `dialogs/` subdirectory under the relevant role folder
  - NO -> skip dialogs/
- **Does the project have a dashboard with charts?**
  - YES -> create `Charts/` subdirectory under `components/admin/`
  - NO -> skip Charts/
- **Does the project use Angular pipes or NestJS pipes?**
  - YES -> create `pipes/`
  - NO -> use `shared/utils/` for transform functions (React/Express)
- **Is the app a Node.js backend (not frontend)?**
  - YES -> rename `components/` to `controllers/`, `forms/` to `validators/`, `core/` to `config/`

---

## 7. Anti-Patterns

❌ **NEVER mix DTOs and form interfaces in the same file or folder:**
```
WRONG: models/Product.ts (used for both API response and form input)
RIGHT: dto/shared/product-dto.ts + forms/admin/product-form.ts
```

❌ **NEVER put all services in a flat folder without role/domain grouping:**
```
WRONG: services/authService.ts, services/cartService.ts, services/analyticsService.ts (20+ files flat)
RIGHT: services/shared/, services/admin/, services/user/
```

❌ **NEVER hardcode API endpoints in components or services:**
```
WRONG: this.http.get(`/api/v1/categories/${id}`)
RIGHT: this.httpService.get(API_ENDPOINTS.CATEGORY_BY_ID(id))
```

❌ **NEVER use classes instead of interfaces for DTOs:**
```
WRONG: export class ProductDto { constructor(public id: number, ...) {} }
RIGHT: export interface ProductDto { readonly id: number; ... }
```

❌ **NEVER duplicate HTTP logic in every domain service:**
```
WRONG: Each service creates its own HttpHeaders, reads localStorage for token
RIGHT: Single HttpService wrapper; domain services call httpService.get<T>()
```

❌ **NEVER use class-based guards (Angular 17+):**
```
WRONG: @Injectable() export class AuthGuard implements CanActivate { ... }
RIGHT: export const authGuard: CanActivateFn = () => { ... }
```

❌ **NEVER create empty conditional folders preemptively:**
```
WRONG: Empty guards/, pipes/, Charts/ folders "just in case"
RIGHT: Create folders only when the first file belongs there (see Decision Tree)
```

❌ **NEVER put business services in core/ or infrastructure in services/:**
```
WRONG: core/services/product.service.ts (business logic in core)
WRONG: services/shared/session-timer.service.ts (infrastructure in services)
RIGHT: core/ = infrastructure (session, config), services/ = business API calls
```

❌ **NEVER hardcode URLs or API keys directly in services or components:**
```
WRONG: const BASE = 'https://api.example.com/v1'; (in product.service.ts)
RIGHT: Import from environment.ts or .env config (Pattern 8)
```

❌ **NEVER trigger multiple token refreshes on concurrent 401 errors:**
```
WRONG: Each 401 independently calls /auth/refresh (5 concurrent = 5 refresh calls)
RIGHT: Single-flight refresh queue — first 401 refreshes, others wait (Pattern 6)
```

---

**ENFORCEMENT:** Level 2 loading -- code review checklist. Folder structure validated during Step 7 (Final Prompt Generation) when standards are injected into coding prompts.

**SEE ALSO:**
- 04-frontend-standards.md -- component patterns, state management, API integration
- 06-typescript-standards.md -- TypeScript type safety and naming conventions
- 15-dto-form-separation.md -- Java backend equivalent of DTO/Form separation
- 18-service-layer-conventions.md -- Java backend equivalent of service layer patterns
- 24-constants-organization.md -- Java backend equivalent of constants organization
