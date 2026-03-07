# Feature Spec: TypeScript APCore Client

## Goal

Create a TypeScript `APCore` class in the `apcore-typescript` SDK that provides feature parity with the Python APCore client, adapted to TypeScript idioms (async-only `call()`, options objects, no decorator syntax).

## Files to Modify

- `/Users/tercelyi/Workspace/aipartnerup/apcore-typescript/src/client.ts` -- create new file with APCore class
- `/Users/tercelyi/Workspace/aipartnerup/apcore-typescript/src/index.ts` -- export APCore
- `/Users/tercelyi/Workspace/aipartnerup/apcore-typescript/tests/test-client.test.ts` -- create new test file

## Implementation Steps

### Step 1: Create `src/client.ts`

```typescript
/**
 * High-level client for apcore to simplify interaction.
 */

import type { Config } from './config.js';
import { Context } from './context.js';
import { Executor } from './executor.js';
import type { Middleware } from './middleware/index.js';
import { Registry } from './registry/registry.js';

export interface APCoreOptions {
  registry?: Registry;
  executor?: Executor;
  config?: Config;
}

export class APCore {
  readonly registry: Registry;
  readonly executor: Executor;
  readonly config: Config | undefined;

  constructor(options?: APCoreOptions) {
    this.config = options?.config;
    this.registry = options?.registry ?? new Registry();
    this.executor = options?.executor ?? new Executor(this.registry, this.config);
  }

  register(moduleId: string, module: unknown): void {
    this.registry.register(moduleId, module);
  }

  async call(
    moduleId: string,
    inputs?: Record<string, unknown> | null,
    context?: Context | null,
  ): Promise<Record<string, unknown>> {
    return this.executor.call(moduleId, inputs ?? undefined, context ?? undefined);
  }

  use(middleware: Middleware): APCore {
    this.executor.use(middleware);
    return this;
  }

  async discover(path?: string): Promise<number> {
    if (path !== undefined) {
      const tempRegistry = new Registry({ extensionsDir: path, config: this.config });
      const count = await tempRegistry.discover();
      for (const [moduleId, moduleObj] of tempRegistry.iter()) {
        this.registry.register(moduleId, moduleObj);
      }
      return count;
    }
    return this.registry.discover();
  }

  listModules(options?: { tags?: string[]; prefix?: string }): string[] {
    return this.registry.list(options);
  }
}
```

### Step 2: Adapt to actual TypeScript SDK interfaces

Before finalizing, verify the exact constructor signatures of `Registry` and `Executor` in the TypeScript SDK:

- `Registry` constructor: Check if it accepts `{ extensionsDir?, config? }` or positional args. Adjust accordingly.
- `Executor` constructor: Check if it accepts `(registry, config?)` or an options object. Adjust accordingly.
- `Registry.iter()`: Verify this method exists and its return type. If it doesn't exist, use `registry.list()` + `registry.get()` loop instead.

### Step 3: Export from `index.ts`

Add to `/Users/tercelyi/Workspace/aipartnerup/apcore-typescript/src/index.ts`:

```typescript
// Client
export { APCore } from './client.js';
export type { APCoreOptions } from './client.js';
```

### Step 4: Write tests in `tests/test-client.test.ts`

```typescript
import { describe, it, expect } from 'vitest';
import { APCore } from '../src/client.js';
import { Registry } from '../src/registry/registry.js';
import { Executor } from '../src/executor.js';

describe('APCore', () => {
  it('creates default registry and executor', () => { ... });
  it('accepts custom registry and executor', () => { ... });
  it('register() adds module to registry', () => { ... });
  it('call() executes module and returns result', async () => { ... });
  it('call() throws ModuleNotFoundError for unknown module', async () => { ... });
  it('use() adds middleware and returns self for chaining', () => { ... });
  it('discover() delegates to registry.discover()', async () => { ... });
  it('listModules() returns sorted module IDs', () => { ... });
  it('listModules() filters by tags', () => { ... });
  it('listModules() filters by prefix', () => { ... });
});
```

### Step 5: Verify build and tests

Run:
- `npx tsc --noEmit`
- `npx vitest run`

## Test Cases

| Test Case | Verifies |
|-----------|----------|
| `creates default registry and executor` | `new APCore()` creates internal Registry and Executor |
| `accepts custom registry and executor` | Injected instances are used |
| `register() adds module to registry` | `client.register("id", module)` makes module available via `registry.get("id")` |
| `call() executes module and returns result` | End-to-end async call with input/output |
| `call() throws ModuleNotFoundError` | Error on unknown module ID |
| `use() adds middleware and returns self` | Chainable middleware registration |
| `discover() delegates to registry` | Calls `registry.discover()` |
| `listModules() returns sorted IDs` | Lists registered modules in order |
| `listModules() filters by tags` | Tag filter works |
| `listModules() filters by prefix` | Prefix filter works |

## Acceptance Criteria

- [ ] `APCore` class is exported from `apcore-typescript/src/index.ts`
- [ ] Constructor accepts optional `registry`, `executor`, and `config`
- [ ] `register(moduleId, module)` proxies to `registry.register()`
- [ ] `call(moduleId, inputs?, context?)` proxies to `executor.call()` and is async
- [ ] `use(middleware)` proxies to `executor.use()` and returns `this`
- [ ] `discover(path?)` proxies to `registry.discover()` and is async
- [ ] `listModules({ tags?, prefix? })` proxies to `registry.list()`
- [ ] All public methods have full TypeScript type annotations
- [ ] `tsc --noEmit` passes with zero errors
- [ ] `vitest run` passes with all tests green
- [ ] Public API surface matches Python APCore (adjusted for TS idioms: async-only call, no decorator pattern, options objects)
