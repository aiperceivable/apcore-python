# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-03-06

### Added

#### Enhanced Executor.validate() Preflight
- **`PreflightCheckResult`** — New frozen dataclass representing a single preflight check result with `check`, `passed`, and `error` fields.
- **`PreflightResult`** — New dataclass returned by `Executor.validate()`, containing per-check results and `requires_approval` flag. Duck-type compatible with `ValidationResult` via `.valid` and `.errors` properties.
- **Full 6-check preflight** — `validate()` now runs Steps 1–6 of the pipeline (module_id format, module lookup, call chain safety, ACL, approval detection, schema validation) without executing module code or middleware.

### Changed

#### Executor Pipeline
- **Step renumbering** — Approval Gate renumbered from Step 4.5 to Step 5; all subsequent steps shifted +1 (now 11 clean steps).
- **`validate()` return type** — Changed from `ValidationResult` to `PreflightResult`. Backward compatible: `.valid` and `.errors` still work identically for existing consumers (e.g., apcore-mcp router).
- **`validate()` signature** — Added optional `context` parameter for call-chain checks; `inputs` now defaults to `{}`.

#### Public API
- Exported `PreflightCheckResult` and `PreflightResult` from `apcore` top-level package.

## [0.8.0] - 2026-03-05

### Added

#### Executor Enhancements
- **Dual-timeout model** — Global deadline enforcement (`executor.global_timeout`) alongside per-module timeout. The shorter of the two is applied, preventing nested call chains from exceeding the global budget.
- **Cooperative cancellation** — On module timeout, the executor sends `CancelToken.cancel()` and waits a 5-second grace period before raising `ModuleTimeoutError`. Modules that check `cancel_token` can clean up gracefully.
- **Error propagation (Algorithm A11)** — All execution paths (sync, async, stream) now wrap exceptions via `propagate_error()`, ensuring middleware always receives `ModuleError` instances with trace context.
- **Deep merge for streaming** — Streaming chunk accumulation uses recursive deep merge (depth-capped at 32) instead of shallow merge, correctly handling nested response structures.

#### Error System
- **ErrorCodeRegistry** — Custom module error codes are validated against framework prefixes and other modules to prevent collisions. Raises `ErrorCodeCollisionError` on conflict.
- **VersionIncompatibleError** — New error class for SDK/config version mismatches with `negotiate_version()` utility.
- **MiddlewareChainError** — Now explicitly `_default_retryable = False` per PROTOCOL_SPEC §8.6.

#### Utilities
- **`guard_call_chain()`** — Standalone Algorithm A20 implementation for call chain safety checks (depth, circular, frequency). Executor delegates to this utility.
- **`propagate_error()`** — Standalone Algorithm A11 implementation for error wrapping and trace context attachment.
- **`normalize_to_canonical_id()`** — Cross-language module ID normalization (Python snake_case, Go PascalCase, etc.).
- **`calculate_specificity()`** — ACL pattern specificity scoring for deterministic rule ordering.
- **`parse_docstring()`** — Docstring parser for extracting parameter descriptions from function docstrings.

#### ACL Enhancements
- **Audit logging** — `ACL` constructor accepts optional `audit_logger` callback. All access decisions emit `AuditEntry` with timestamp, caller/target IDs, matched rule, identity, and trace context.
- **Condition-based rules** — ACL rules support `conditions` for identity type, role, and call depth filtering.

#### Config System
- **Full validation** — `Config.validate()` checks schema structure, value types, and range constraints.
- **Hot reload** — `Config.reload()` re-reads the YAML source and re-validates.
- **Environment overrides** — `APCORE_*` environment variables override config values (e.g., `APCORE_EXECUTOR_DEFAULT_TIMEOUT=5000`).
- **`Config.from_defaults()`** — Factory method for default configuration.

#### Middleware
- **RetryMiddleware** — Configurable retry with exponential/fixed backoff, jitter, and max delay. Only retries errors marked `retryable=True`.

#### Registry Enhancements
- **ID conflict detection** — Registry detects and prevents registration of conflicting module IDs.
- **Safe unregister** — `safe_unregister()` with drain timeout for graceful module removal.

#### Context
- **Generic `services` typing** — `Context[T]` supports typed dependency injection via the `services` field.

#### Testing
- **Conformance test suite** — JSON fixture-driven tests for error codes, call chain safety, ACL evaluation, pattern matching, specificity, ID normalization, and version negotiation.
- **New unit tests** — 17 new test files covering all added features.

### Changed

#### Executor Internals
- `_check_safety()` now delegates to standalone `guard_call_chain()` instead of inline logic.
- Error handling wraps exceptions with `propagate_error()` and re-raises with `raise wrapped from exc`.
- Global deadline set on root call only, propagated to child contexts via `Context._global_deadline`.

#### Public API
- Expanded `__all__` in `apcore.__init__` with new exports: `RetryMiddleware`, `RetryConfig`, `ErrorCodeRegistry`, `ErrorCodeCollisionError`, `VersionIncompatibleError`, `negotiate_version`, `guard_call_chain`, `propagate_error`, `normalize_to_canonical_id`, `calculate_specificity`, `AuditEntry`, `parse_docstring`.

## [0.7.1] - 2026-03-04

### Added

#### Public API Extensions
- **Module Protocol** — Introduced `Module` protocol in `apcore.module` for standardized module typing.
- **Schema System** — Exposed schema APIs (`SchemaLoader`, `SchemaValidator`, `SchemaExporter`, `RefResolver`, `to_strict_schema`) to the top-level `apcore` exports.
- **Utilities** — Exposed `match_pattern` utility to the top-level `apcore` exports.

## [0.7.0] - 2026-03-01

### Added

#### Approval System (PROTOCOL_SPEC §7)
- **ApprovalHandler Protocol** - Async protocol for pluggable approval handlers with `request_approval()` and `check_approval()` methods
- **ApprovalRequest / ApprovalResult** - Frozen dataclasses carrying invocation context and handler decisions with `Literal` status typing
- **Phase A (synchronous)** - Handler blocks until approval decision; denied/timeout raise immediately
- **Phase B (asynchronous)** - `pending` status returns `_approval_token` for async resume via `check_approval()`
- **Built-in handlers** - `AlwaysDenyHandler` (safe default), `AutoApproveHandler` (testing), `CallbackApprovalHandler` (custom logic)
- **Approval errors** - `ApprovalError`, `ApprovalDeniedError`, `ApprovalTimeoutError`, `ApprovalPendingError` with `result`, `module_id`, and `reason` properties
- **Audit events (Level 3)** - Dual-channel emission: `logging.info()` always + span events when tracing is active
- **Extension point** - `approval_handler` registered as a built-in extension point in `ExtensionManager`
- **ErrorCodes** - Added `APPROVAL_DENIED`, `APPROVAL_TIMEOUT`, `APPROVAL_PENDING` constants

#### Executor Integration
- **Step 4.5 approval gate** - Inserted between ACL (Step 4) and input validation (Step 5) in `call()`, `call_async()`, and `stream()`
- **Executor.set_approval_handler()** - Runtime handler configuration
- **Executor.from_registry()** - Added `approval_handler` parameter
- **Dict and dataclass annotations** - Both `ModuleAnnotations` and dict-style `requires_approval` supported
- **Unknown status fail-closed** - Unrecognized approval statuses treated as denied with warning log

### Changed

#### Structural Alignment
- Approval errors re-exported from `apcore.approval` for multi-language SDK consistency; canonical definitions remain in `errors.py`
- `ApprovalResult.status` typed as `Literal["approved", "rejected", "timeout", "pending"]` per PROTOCOL_SPEC §7.3.2

## [0.6.0] - 2026-02-23

### Added

#### Extension System
- **ExtensionManager / ExtensionPoint** - Added a unified extension-point framework for `discoverer`, `middleware`, `acl`, `span_exporter`, and `module_validator`
- **Extension wiring** - Added `apply()` support to connect registered extensions into `Registry` and `Executor`

#### Async Task & Cancellation
- **AsyncTaskManager** - Added background task orchestration with status tracking, cancellation, concurrency limits, shutdown, and cleanup
- **TaskStatus / TaskInfo** - Added task lifecycle enum and metadata dataclass for async task management
- **CancelToken / ExecutionCancelledError** - Added cooperative cancellation primitives and integrated cancellation checks into executor flows

#### Trace Context & Observability
- **TraceContext / TraceParent** - Added W3C Trace Context utilities for `inject()`, `extract()`, and strict parsing via `from_traceparent()`
- **Context.create(trace_parent=...)** - Added distributed-tracing entry support by accepting inbound trace context
- **OTLPExporter top-level export** - Added OTLP exporter re-exports in observability and top-level public API

#### Registry Enhancements
- **Custom discoverer/validator hooks** - Added `set_discoverer()` and `set_validator()` integration paths
- **Module describe support** - Added `Registry.describe()` for human-readable module descriptions
- **Hot-reload APIs** - Added `watch()`, `unwatch()`, and file-change handling helpers for extension directories
- **Validation constants/protocols** - Added `MAX_MODULE_ID_LENGTH`, `RESERVED_WORDS`, `Discoverer`, and `ModuleValidator` exports

### Changed

#### Public API Surface
- Expanded top-level `apcore` exports to include cancellation, extensions, async task types, trace context types, additional registry protocols/constants, and new error classes

#### Error System
- Added `ModuleExecuteError` and `InternalError` to the framework error hierarchy and exports
- Extended `ErrorCodes` with additional constants used by newer execution/extension paths

### Fixed

#### Execution & Redaction
- **executor** - Added recursive `_secret_` key redaction for nested dictionaries
- **executor** - Preserved explicit cancellation semantics by re-raising `ExecutionCancelledError`

#### Import Graph Robustness
- Reduced import-coupling risk across middleware/observability/trace typing paths while preserving existing runtime behavior and public interfaces

## [0.5.0] - 2026-02-22

### Changed

#### API Naming
- **decorator** - Renamed `_generate_input_model` / `_generate_output_model` to `generate_input_model` / `generate_output_model` as public API
- **context_logger** - Renamed `format` parameter to `output_format` to avoid shadowing Python builtin
- **registry** - Renamed `_write_lock` to `_lock` for clearer intent

#### Type Annotations
- **decorator** - Replaced bare `dict` with `dict[str, Any]` in `_normalize_result`, `annotations`, `metadata`, `_async_execute`, `_sync_execute`
- **bindings** - Fixed `_build_model_from_json_schema` parameter type from `dict` to `dict[str, Any]`
- **scanner** - Fixed `roots` parameter type from `list[dict]` to `list[dict[str, Any]]`
- **metrics** - Fixed `snapshot` return type from `dict` to `dict[str, Any]`
- **executor** - Removed redundant string-quoted forward references in `from_registry`; fixed `middlewares` parameter type to `list[Middleware] | None`

#### Code Quality
- **executor** - Extracted `_convert_validation_errors()` helper to eliminate 6 duplicated validation error conversion patterns
- **executor** - Refactored `call_async()` and `stream()` to use new async middleware manager methods
- **executor** - Removed internal `_execute_on_error_async` method (replaced by `MiddlewareManager.execute_on_error_async`)
- **loader** - Use `self._resolver.clear_cache()` instead of accessing private `_file_cache` directly
- **tracing** - Replaced `print()` with `sys.stdout.write()` in `StdoutExporter`
- **acl / loader** - Changed hardcoded logger names to `logging.getLogger(__name__)`

### Added

#### Level 2 Conformance (Phase 1)
- **ExtensionManager** and **ExtensionPoint** for unified extension point management (discoverer, middleware, acl, span_exporter, module_validator) with `register()`, `get()`, `get_all()`, `unregister()`, `apply()`, `list_points()` methods
- **AsyncTaskManager**, **TaskStatus**, **TaskInfo** for async task execution with status tracking (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED), cancellation, and concurrency limiting
- **TraceContext** and **TraceParent** for W3C Trace Context support with `inject()`, `extract()`, and `from_traceparent()` methods
- `Context.create()` now accepts optional `trace_parent` parameter for distributed trace propagation

#### Async Middleware
- **MiddlewareManager** - Added `execute_before_async()`, `execute_after_async()`, `execute_on_error_async()` for proper async middleware dispatch with `inspect.iscoroutinefunction` detection
- **RefResolver** - Added `clear_cache()` public method for cache management
- **Executor** - Added `clear_async_cache()` public method
#### Schema Export
- **SchemaExporter** - Added `streaming` hint to `export_mcp()` annotations from `ModuleAnnotations`

### Fixed

#### Memory Safety
- **context** - Changed `Identity.roles` from mutable `list[str]` to immutable `tuple[str, ...]` in frozen dataclass

#### Observability
- **context_logger / metrics** - Handle cases where `before()` was never called in `ObsLoggingMiddleware` and `MetricsMiddleware`

#### Security
- **acl** - Added explicit `encoding="utf-8"` to YAML file open


## [0.4.0] - 2026-02-20

### Added

#### Streaming Support
- **Executor.stream()** - New async generator method for streaming module execution
  - Implements same 6-step pipeline as `call_async()` (context, safety, lookup, ACL, input validation, middleware before)
  - Falls back to `call_async()` yielding single chunk for non-streaming modules
  - For streaming modules, iterates `module.stream()` and yields each chunk
  - Accumulates chunks via shallow merge for output validation and after-middleware
  - Full error handling with middleware recovery
- **ModuleAnnotations.streaming** - New `streaming: bool = False` field to indicate if a module supports streaming execution
- **Test coverage** - Added 5 comprehensive tests in `test_executor_stream.py`:
  - Fallback behavior for non-streaming modules
  - Multi-chunk streaming
  - Module not found error handling
  - Before/after middleware integration
  - Disjoint key accumulation via shallow merge


## [0.3.0] - 2026-02-20

### Added

#### Public API Extensions
- **ErrorCodes** - New `ErrorCodes` class with all framework error code constants; replaces hardcoded error strings
- **ContextFactory Protocol** - New `ContextFactory` protocol for creating Context from framework-specific requests (e.g., Django, FastAPI)
- **Registry constants** - Exported `REGISTRY_EVENTS` dict and `MODULE_ID_PATTERN` regex for consistent module ID validation
- **Executor.from_registry()** - Convenience factory method for creating an Executor from a Registry with optional middlewares, ACL, and config

#### Schema System
- **Comprehensive schema system** - Full implementation with loading, validation, and export capabilities
  - Schema loading from JSON/YAML files
  - Runtime schema validation
  - Schema export functionality

### Fixed
- **ErrorCodes class** - Prevent attribute deletion to ensure error code constants remain immutable
- **Planning documentation** - Updated progress bar style in overview.md


## [0.2.3] - 2026-02-20

### Added

#### Public API
- **ContextFactory Protocol** - New `ContextFactory` protocol for creating Context from framework-specific requests (e.g., Django, FastAPI)
- **ErrorCodes** - New `ErrorCodes` class with all framework error code constants; replaces hardcoded error strings
- **Registry constants** - Exported `REGISTRY_EVENTS` dict and `MODULE_ID_PATTERN` regex for consistent module ID validation
- **Executor.from_registry()** - Convenience factory method for creating an Executor from a Registry with optional middlewares, ACL, and config

### Changed

#### Core Improvements
- **Module ID validation** - Strengthened to enforce lowercase letters, digits, underscores, and dots only; no hyphens allowed. Pattern: `^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$`
- **Registry events** - Replaced hardcoded event strings with `REGISTRY_EVENTS` constant dict
- **Test fixtures** - Updated registry test module IDs to comply with new module ID pattern

#### Configuration
- **.code-forge.json** - Updated directory mappings: `base` from `planning/` to `./`; `input` from `features/` to `../apcore/docs/features`

### Improved
- Better type hints and protocol definitions for framework integration
- Consistent error handling with standardized error codes


## [0.2.2] - 2026-02-16

### Removed

#### Planning & Documentation
- **planning/features/** - Moved all feature specifications to `apcore/docs/features/` for better organization with documentation
- **planning/implementation/** - Restructured implementation planning to consolidate with overall project architecture

### Changed

#### Planning & Documentation Structure
- **Implementation planning** - Reorganized implementation plans to streamline project structure and improve maintainability



## [0.2.1] - 2026-02-14

### Added

#### Planning & Documentation Infrastructure
- **code-forge integration** - Added `.code-forge.json` configuration (v0.2.0 spec) with `_tool` metadata, directory mappings, and execution settings
- **Feature specifications** - 7 feature documents in `planning/features/` covering all core modules: core-executor, schema-system, registry-system, middleware-system, acl-system, observability, decorator-bindings
- **Implementation plans** - Complete implementation plans in `planning/implementation/` for all 7 features, each containing `overview.md`, `plan.md`, `tasks/*.md`, and `state.json`
- **Project-level overview** - Auto-generated `planning/implementation/overview.md` with module dependency graph, progress tracking, and phased implementation order
- **Task breakdown** - 42 task files with TDD-oriented steps, acceptance criteria, dependency tracking, and time estimates (~91 hours total estimated effort)

## [0.2.0] - 2026-02-14

### Fixed

#### Thread Safety
- **MiddlewareManager** - Added internal locking and snapshot pattern; `add()`, `remove()`, `execute_before()`, `execute_after()` are now thread-safe
- **Executor** - Added lock to async module cache; use `snapshot()` for middleware iteration in `call_async()` and `middlewares` property
- **ACL** - Internally synchronized; `check()`, `add_rule()`, `remove_rule()`, `reload()` are now safe for concurrent use
- **Registry** - Extended existing `RLock` to cover all read paths (`get`, `has`, `count`, `module_ids`, `list`, `iter`, `get_definition`, `on`, `_trigger_event`, `clear_cache`)

#### Memory Leak
- **InMemoryExporter** - Replaced unbounded `list` with `collections.deque(maxlen=10_000)` and added `threading.Lock` for thread-safe access

#### Robustness
- **TracingMiddleware** - Added empty span stack guard in `after()` and `on_error()` to log a warning instead of raising `IndexError`
- **Executor** - Set `daemon=True` on timeout and async bridge threads to prevent blocking process exit

### Added

#### Development Tooling
- **apdev integration** - Added `apdev[dev]` as development dependency for code quality checks and project tooling
- **pip install support** - Moved dev dependencies to `[project.optional-dependencies]` so `pip install -e ".[dev]"` works alongside `uv sync --group dev`
- **pre-commit hooks** - Fixed `check-chars` and `check-imports` hooks to run as local hooks via `apdev` instead of incorrectly nesting under `ruff-pre-commit` repo

### Changed

- **Context.child()** - Added docstring clarifying that `data` is intentionally shared between parent and child for middleware state propagation

## [0.1.0] - 2026-02-13

### Added

#### Core Framework
- **Schema-driven modules** - Define modules with Pydantic input/output schemas and automatic validation
- **@module decorator** - Zero-boilerplate decorator to turn functions into schema-aware modules
- **Executor** - 10-step execution pipeline with comprehensive safety and security checks
- **Registry** - Module registration and discovery system with metadata support

#### Security & Safety
- **Access Control (ACL)** - Pattern-based, first-match-wins rule system with wildcard support
- **Call depth limits** - Prevent infinite recursion and stack overflow
- **Circular call detection** - Detect and prevent circular module calls
- **Frequency throttling** - Rate limit module execution
- **Timeout support** - Configure execution timeouts per module

#### Middleware System
- **Composable pipeline** - Before/after hooks for request/response processing
- **Error recovery** - Graceful error handling and recovery in middleware chain
- **LoggingMiddleware** - Structured logging for all module calls
- **TracingMiddleware** - Distributed tracing with span support for observability

#### Bindings & Configuration
- **YAML bindings** - Register modules declaratively without modifying source code
- **Configuration system** - Centralized configuration management
- **Environment support** - Environment-based configuration override

#### Observability
- **Tracing** - Span-based distributed tracing integration
- **Metrics** - Built-in metrics collection for execution monitoring
- **Context logging** - Structured logging with execution context propagation

#### Async Support
- **Sync/Async modules** - Seamless support for both synchronous and asynchronous execution
- **Async executor** - Non-blocking execution for async-first applications

#### Developer Experience
- **Type safety** - Full type annotations across the framework (Python 3.11+)
- **Comprehensive tests** - 90%+ test coverage with unit and integration tests
- **Documentation** - Quick start guide, examples, and API documentation
- **Examples** - Sample modules demonstrating decorator-based and class-based patterns

### Dependencies

- **pydantic** >= 2.0 - Schema validation and serialization
- **pyyaml** >= 6.0 - YAML binding support

### Supported Python Versions

- Python 3.11+

---

[0.9.0]: https://github.com/aipartnerup/apcore-python/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/aipartnerup/apcore-python/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/aipartnerup/apcore-python/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/aipartnerup/apcore-python/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/aipartnerup/apcore-python/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/aipartnerup/apcore-python/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/aipartnerup/apcore-python/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/aipartnerup/apcore-python/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/aipartnerup/apcore-python/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/aipartnerup/apcore-python/releases/tag/v0.2.1
[0.2.0]: https://github.com/aipartnerup/apcore-python/releases/tag/v0.2.0
[0.1.0]: https://github.com/aipartnerup/apcore-python/releases/tag/v0.1.0