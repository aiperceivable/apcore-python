# Task: ErrorHistoryMiddleware — Record ModuleErrors into ErrorHistory (PRD F2)

## Goal

Implement `ErrorHistoryMiddleware` that intercepts `on_error()` calls in the middleware pipeline and records `ModuleError` instances into `ErrorHistory`. Generic exceptions are ignored. The middleware never recovers (always returns `None`).

## Files Involved

- `src/apcore/middleware/error_history.py` -- `ErrorHistoryMiddleware` class
- `tests/test_error_history_middleware.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/test_error_history_middleware.py` with tests for:

- **test_on_error_records_module_error**: Call `on_error()` with a `ModuleError`; verify `ErrorHistory.record()` is called with the correct `module_id` and error
- **test_on_error_ignores_generic_exception**: Call `on_error()` with a plain `Exception`; verify `ErrorHistory.record()` is NOT called
- **test_on_error_ignores_module_error_subclass**: Call `on_error()` with a `ModuleError` subclass (e.g., `ModuleNotFoundError`); verify it IS recorded (subclasses of ModuleError are still ModuleError)
- **test_on_error_returns_none**: Verify `on_error()` always returns `None` regardless of error type
- **test_before_returns_none**: Verify `before()` returns `None` (no-op)
- **test_after_returns_none**: Verify `after()` returns `None` (no-op)
- **test_middleware_inherits_base**: Verify `ErrorHistoryMiddleware` is a subclass of `Middleware`

### 2. Implement ErrorHistoryMiddleware

Create `src/apcore/middleware/error_history.py`:

```python
class ErrorHistoryMiddleware(Middleware):
    def __init__(self, error_history: ErrorHistory) -> None:
        self._error_history = error_history

    def on_error(
        self,
        module_id: str,
        inputs: dict[str, Any],
        error: Exception,
        context: Context,
    ) -> dict[str, Any] | None:
        if isinstance(error, ModuleError):
            self._error_history.record(module_id, error)
        return None
```

- Full type annotations
- Import `ErrorHistory` from `apcore.observability.error_history`
- Import `ModuleError` from `apcore.errors`
- Import `Middleware` from `apcore.middleware.base`

### 3. Verify tests pass

Run `pytest tests/test_error_history_middleware.py -v`.

## Acceptance Criteria

- [ ] `ErrorHistoryMiddleware` extends `Middleware`
- [ ] `on_error()` records only `ModuleError` instances (including subclasses) into `ErrorHistory`
- [ ] `on_error()` ignores generic `Exception` instances
- [ ] `on_error()` always returns `None`
- [ ] `before()` and `after()` are no-ops returning `None`
- [ ] Full type annotations on all methods
- [ ] Tests achieve >= 90% coverage

## Dependencies

- `apcore.observability.error_history.ErrorHistory` (Task 1)
- `apcore.middleware.base.Middleware`
- `apcore.errors.ModuleError`

## Estimated Time

1 hour
