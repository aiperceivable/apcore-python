### Problem
Middleware components were using fragile, hardcoded string keys (e.g., `_metrics_starts`, `_tracing_spans`) to store state in the `Context.data` dictionary. This created a high risk of key collisions between different middleware implementations or between core framework and user extensions.

### Why
The early implementation of middleware relied on a flat `dict` for state sharing, as a more formal mechanism for typed, namespaced context storage had not yet been developed.

### Solution
In v0.16.0, the `ContextKey[T]` typed accessor system was introduced. All core middleware components were migrated to use namespaced keys following the `_apcore.mw.*` convention. This ensures type safety, provides a clear namespace for framework-internal data, and prevents accidental collisions.

### Verification
Verified that all built-in middleware (Metrics, Tracing, Logging) correctly store and retrieve their state using `ContextKey` instances and that manual dictionary injection with legacy names no longer affects middleware behavior.
