# TypeScript Coding Standards

> Auto-loaded by Level 2 Standards System

---

## 1. Strict Mode and Compiler Configuration

### Rule 1.1: Always Enable Strict Mode
- Enable `"strict": true` in tsconfig.json - this enables all strict type checks
- Do NOT disable individual strict flags unless you have a documented reason
- Recommended additional flags: `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`

```json
// GOOD - tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true
  }
}
```

```json
// BAD - disabling strict checks
{
  "compilerOptions": {
    "strict": false,
    "noImplicitAny": false
  }
}
```

---

## 2. Type Safety - No `any`

### Rule 2.1: Never Use `any` in Production Code
- `any` disables all type checking - it is a type system escape hatch, not a type
- Use `unknown` when the type is truly unknown - it forces you to narrow before use
- Use generics when the type is variable but constrained
- Use `never` for exhaustive checks in switch statements

```typescript
// BAD - any disables type checking
function processData(data: any): any {
  return data.value;
}

// GOOD - unknown forces type narrowing
function processData(data: unknown): string {
  if (typeof data === "object" && data !== null && "value" in data) {
    return String((data as { value: unknown }).value);
  }
  throw new Error("Invalid data shape");
}

// GOOD - generic preserves type information
function identity<T>(value: T): T {
  return value;
}
```

### Rule 2.2: No `@ts-ignore` Without Explanation
- `@ts-ignore` suppresses errors on the next line - it hides real bugs
- If you must use it, use `@ts-expect-error` instead (fails if the error disappears)
- Always add a comment explaining why it is needed

```typescript
// BAD
// @ts-ignore
const result = legacyLib.doSomething(data);

// ACCEPTABLE - with explanation and expect-error
// @ts-expect-error - legacyLib typings are incorrect for v2 API, filed in issue #123
const result = legacyLib.doSomething(data);
```

---

## 3. Interface vs Type

### Rule 3.1: Use `interface` for Object Shapes, `type` for Aliases and Unions
- `interface` is for describing object shapes that may be extended or implemented
- `type` is for unions, intersections, mapped types, conditional types, and primitive aliases
- Both can be used for object shapes - consistency within a codebase matters most

```typescript
// GOOD - interface for extendable object shapes
interface User {
  id: string;
  name: string;
  email: string;
}

interface AdminUser extends User {
  permissions: string[];
}

// GOOD - type for unions and computed types
type Status = "active" | "inactive" | "pending";
type ApiResponse<T> = { data: T; error: null } | { data: null; error: string };
type UserKeys = keyof User;

// BAD - type alias where interface would be clearer
type IUser = {
  id: string;
  name: string;
};
```

### Rule 3.2: Never Use `{}` or `Object` as a Type
- `{}` means "any non-null value" - it is not an empty object type
- `Object` is similar and rarely what you mean
- Use `Record<string, unknown>` for unknown object shapes

```typescript
// BAD
function log(value: {}): void { console.log(value); }
function process(obj: Object): void { }

// GOOD
function log(value: unknown): void { console.log(value); }
function process(obj: Record<string, unknown>): void { }
```

---

## 4. Generics

### Rule 4.1: Constrain Generics When Possible
- Unconstrained generics (`<T>`) accept anything - add constraints to express intent
- Use `extends` to constrain generic parameters
- Name generic parameters descriptively for complex generics: `TEntity`, `TKey`, `TValue`

```typescript
// BAD - T is completely unconstrained
function getProperty<T>(obj: T, key: string): unknown {
  return (obj as Record<string, unknown>)[key];
}

// GOOD - constrained generic preserves type safety
function getProperty<TObj, TKey extends keyof TObj>(
  obj: TObj,
  key: TKey
): TObj[TKey] {
  return obj[key];
}

// GOOD - constrained with meaningful name
interface Repository<TEntity extends { id: string }> {
  findById(id: string): Promise<TEntity | null>;
  save(entity: TEntity): Promise<TEntity>;
}
```

### Rule 4.2: Avoid Generic Abuse
- Do not add a generic parameter if the type is always the same
- Do not use generics when a union type is clearer

```typescript
// BAD - unnecessary generic
function wrapInArray<T>(value: T): T[] {
  // This is fine if T varies, but if it is always string just type it as string
  return [value];
}

// BAD - generic when union is clearer
function formatId<T extends string | number>(id: T): string {
  return String(id);
}

// GOOD - union type is simpler and more readable
function formatId(id: string | number): string {
  return String(id);
}
```

---

## 5. Null Handling

### Rule 5.1: Use Optional Chaining and Nullish Coalescing
- Use `?.` for optional property access instead of manual null checks
- Use `??` for null/undefined fallbacks instead of `||` (which also catches falsy values)
- Use `!` (non-null assertion) only when you are certain - prefer type narrowing

```typescript
// BAD - verbose manual null checks
const city = user && user.address && user.address.city;
const name = user.name || "Anonymous";

// GOOD - concise and correct
const city = user?.address?.city;
const name = user.name ?? "Anonymous";

// BAD - non-null assertion hides potential bugs
const length = maybeString!.length;

// GOOD - explicit narrowing is safer
const length = maybeString != null ? maybeString.length : 0;
```

### Rule 5.2: Return `null` for Absent Domain Values, `undefined` for Missing Config
- `null` means "this value exists but has no data" (e.g., `findById` returns `User | null`)
- `undefined` means "this property was never set" (e.g., optional config fields)
- Be consistent within a codebase; document the convention

```typescript
// GOOD - null for domain absence
async function findUser(id: string): Promise<User | null> {
  const row = await db.query("SELECT * FROM users WHERE id = $1", [id]);
  return row ?? null;
}

// GOOD - undefined for optional config
interface Config {
  timeout?: number;     // undefined when not provided
  retries?: number;
}
```

---

## 6. Async/Await Patterns

### Rule 6.1: Always Await Promises - Never Fire and Forget Without Handling
- Unawaited promises swallow errors silently
- If you intentionally want fire-and-forget, log errors explicitly

```typescript
// BAD - fire and forget, errors are silently swallowed
function handleRequest(req: Request): void {
  processOrder(req.body);  // unawaited Promise
}

// BAD - missing await in async function
async function saveUser(user: User): Promise<void> {
  repository.save(user);  // missing await
}

// GOOD - always await or handle the promise
async function handleRequest(req: Request): Promise<void> {
  await processOrder(req.body);
}

// ACCEPTABLE - intentional fire-and-forget with error handling
function triggerAnalytics(event: string): void {
  analyticsService.track(event).catch((err) => {
    logger.warn("Analytics event failed", { event, error: err });
  });
}
```

### Rule 6.2: Handle Async Errors Explicitly
- Do not let async errors propagate without context
- Wrap `await` calls in try/catch at the boundary where you can provide context

```typescript
// BAD - error loses context when propagated
async function processOrder(orderId: string): Promise<Order> {
  const order = await orderRepository.findById(orderId);
  return order;
}

// GOOD - add context at the boundary
async function processOrder(orderId: string): Promise<Order> {
  try {
    const order = await orderRepository.findById(orderId);
    if (!order) throw new NotFoundError(`Order ${orderId} not found`);
    return order;
  } catch (err) {
    if (err instanceof NotFoundError) throw err;
    throw new Error(`Failed to process order ${orderId}`, { cause: err });
  }
}
```

---

## 7. Error Handling with Result Types

### Rule 7.1: Use Discriminated Unions for Expected Errors
- Throwing exceptions for expected business errors forces callers to know what to catch
- Use Result/Either types for operations that can fail in predictable ways

```typescript
// BAD - caller must know to catch PaymentDeclinedError
async function chargeCard(amount: number, token: string): Promise<void> {
  if (!isValidToken(token)) throw new PaymentDeclinedError("Invalid card");
}

// GOOD - failure is explicit in the return type
type PaymentResult =
  | { success: true; transactionId: string }
  | { success: false; reason: "declined" | "invalid_card" | "network_error" };

async function chargeCard(
  amount: number,
  token: string
): Promise<PaymentResult> {
  if (!isValidToken(token)) {
    return { success: false, reason: "invalid_card" };
  }
  // ...
  return { success: true, transactionId: "txn-123" };
}

// Caller handles both cases without try/catch
const result = await chargeCard(2999, token);
if (result.success) {
  console.log("Charged:", result.transactionId);
} else {
  console.warn("Payment failed:", result.reason);
}
```

---

## 8. ESLint Rules

### Rule 8.1: Required ESLint Rules for TypeScript Projects
- Use `@typescript-eslint/eslint-plugin` for TypeScript-specific rules
- Enforce no-explicit-any, no-unused-vars, no-floating-promises

```json
// .eslintrc.json - minimum required rules
{
  "extends": [
    "@typescript-eslint/recommended",
    "@typescript-eslint/recommended-requiring-type-checking"
  ],
  "rules": {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
    "@typescript-eslint/no-floating-promises": "error",
    "@typescript-eslint/await-thenable": "error",
    "@typescript-eslint/no-misused-promises": "error",
    "no-console": ["warn", { "allow": ["warn", "error"] }]
  }
}
```

---

## 9. Import Organization

### Rule 9.1: Group and Order Imports Consistently
- Order: external packages first, then internal modules, then relative imports
- Use `@` path aliases for src-relative imports to avoid `../../../` chains
- Import types with `import type` to avoid side effects and enable better tree-shaking

```typescript
// BAD - mixed import order
import { processOrder } from "./services/order";
import React from "react";
import { User } from "@/types/user";
import axios from "axios";
import path from "path";

// GOOD - organized imports
import path from "path";         // 1. Node built-ins

import axios from "axios";       // 2. External packages
import React from "react";

import type { User } from "@/types/user";    // 3. Internal types (type imports)
import { processOrder } from "@/services/order"; // 4. Internal modules

import { formatDate } from "./utils";       // 5. Relative imports
```

### Rule 9.2: Use `import type` for Type-Only Imports
- `import type` is erased at compile time and cannot cause circular dependencies at runtime
- Use it for all imports that are only used in type positions

```typescript
// BAD - runtime import for type-only usage
import { User } from "./user.model";
function greet(user: User): string { return `Hello ${user.name}`; }

// GOOD - type import
import type { User } from "./user.model";
function greet(user: User): string { return `Hello ${user.name}`; }
```

---

## 10. React Component Patterns (When Applicable)

### Rule 10.1: Use Function Components with Explicit Return Types
- Do not use `React.FC` - it adds implicit children prop and complicates generics
- Annotate the return type explicitly as `JSX.Element` or `ReactNode`

```typescript
// BAD - React.FC adds implicit children, hides issues
const UserCard: React.FC<{ user: User }> = ({ user }) => {
  return <div>{user.name}</div>;
};

// GOOD - explicit props type and return type
interface UserCardProps {
  user: User;
  onSelect?: (id: string) => void;
}

function UserCard({ user, onSelect }: UserCardProps): JSX.Element {
  return (
    <div onClick={() => onSelect?.(user.id)}>
      {user.name}
    </div>
  );
}
```

### Rule 10.2: Type Event Handlers Precisely
- Do not use `any` for event types - React provides specific types

```typescript
// BAD
const handleChange = (event: any) => {
  setValue(event.target.value);
};

// GOOD
const handleChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
  setValue(event.target.value);
};

const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
  event.preventDefault();
  submitForm();
};
```

---

## 11. Exhaustive Checks

### Rule 11.1: Use `never` for Exhaustive Switch Statements
- When switching on a discriminated union, use a `never` assertion to catch unhandled cases
- This causes a compile error if you add a new union member without handling it

```typescript
type Shape = { kind: "circle"; radius: number } | { kind: "square"; side: number };

// BAD - adding a new shape type silently breaks this
function area(shape: Shape): number {
  if (shape.kind === "circle") return Math.PI * shape.radius ** 2;
  if (shape.kind === "square") return shape.side ** 2;
  return 0;  // silent fallthrough
}

// GOOD - exhaustive check with never
function area(shape: Shape): number {
  switch (shape.kind) {
    case "circle":
      return Math.PI * shape.radius ** 2;
    case "square":
      return shape.side ** 2;
    default: {
      const _exhaustive: never = shape;
      throw new Error(`Unhandled shape kind: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
```

---

## 12. Common LLM Mistakes to Avoid

- Generating `any` types when the actual type is derivable from context
- Forgetting `await` before async function calls, especially in loops
- Using `||` for null fallback when `??` is correct (0 and "" are valid values)
- Writing `interface Foo {}` and `type Foo = {}` interchangeably without understanding the difference
- Forgetting `import type` for type-only imports (causes circular dependency issues)
- Using `as SomeType` (type assertion) instead of proper type narrowing
- Generating catch blocks with `catch (e: any)` instead of `catch (e: unknown)` and narrowing
- Not annotating async function return types (TypeScript infers `Promise<any>` when the body has `any`)
