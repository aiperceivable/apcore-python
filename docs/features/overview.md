# APCore Unified Client Enhancement -- Feature Overview

## Summary

This initiative improves the developer experience for the `apcore` framework by fixing bugs in and enhancing the `APCore` unified client class. The client acts as a Facade over Registry and Executor, providing a single entry point for module registration, discovery, and execution.

## Technical Design Document

- [Full Technical Design](/Users/tercelyi/Workspace/aipartnerup/apcore-python/docs/apcore-unified-client/tech-design.md)

## Feature Specs

| # | Spec | Priority | Description |
|---|------|----------|-------------|
| 1 | [fix-decorator-bug.md](./fix-decorator-bug.md) | P0 | Fix `@client.module()` to return the original function instead of FunctionModule |
| 2 | [client-unit-tests.md](./client-unit-tests.md) | P0 | Create comprehensive unit test suite for APCore client (>=90% coverage) |
| 3 | [client-discover-list.md](./client-discover-list.md) | P1 | Add `discover()` and `list_modules()` convenience methods |
| 4 | [typescript-apcore-client.md](./typescript-apcore-client.md) | P1 | Create TypeScript APCore class with feature parity |
| 5 | Result Unwrapping (deferred) | P2 | Design-only in tech design doc; implementation deferred pending team review |

## Implementation Order

```
Phase 1 (P0): fix-decorator-bug -> client-unit-tests
Phase 2 (P1): client-discover-list (depends on Phase 1)
Phase 3 (P1): typescript-apcore-client (can parallel Phases 1-2)
Phase 4 (P2): Result unwrapping design review
```

## Key Design Decisions

1. **Facade pattern** -- APCore is a thin wrapper; no business logic duplication.
2. **Decorator fix in client.py, not decorator.py** -- avoids changing the decorator's public contract for direct callers.
3. **`discover(path?)` accepts optional path** -- quick one-off scanning without reconfiguring extension roots.
4. **`list_modules()` returns IDs, not descriptors** -- keeps API simple; use `registry.get_definition()` for full metadata.
5. **TypeScript uses async-only `call()`** -- matches TS SDK convention (no sync Executor).
6. **Result unwrapping is opt-in and deferred** -- avoids breaking change to return type.

## Files Impacted

### Python SDK (`apcore-python/`)

| File | Action |
|------|--------|
| `src/apcore/client.py` | Modify (fix decorator, add discover/list_modules) |
| `src/apcore/__init__.py` | Modify (add global discover/list_modules) |
| `tests/test_client.py` | Create (full test suite) |

### TypeScript SDK (`apcore-typescript/`)

| File | Action |
|------|--------|
| `src/client.ts` | Create (APCore class) |
| `src/index.ts` | Modify (export APCore) |
| `tests/test-client.test.ts` | Create (full test suite) |
