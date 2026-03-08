# Task: system.health.module — Detailed Single Module Health (PRD F4)

## Goal

Implement the `system.health.module` sys module that returns detailed health information for a single specified module, including call statistics, latency percentiles, and recent error history.

## Files Involved

- `src/apcore/sys_modules/health.py` -- Add `HealthModuleModule` class (same file as summary)
- `tests/sys_modules/test_health.py` -- Add tests (same file as summary tests)

## Steps

### 1. Write failing tests (TDD)

Add to `tests/sys_modules/test_health.py`:

- **test_health_module_requires_module_id**: Call with empty inputs (no `module_id`); verify error raised or returned indicating `module_id` is required
- **test_health_module_not_found_error**: Call with `module_id` for a non-existent module; verify `MODULE_NOT_FOUND` error
- **test_health_module_returns_basic_info**: Register module, simulate metrics; call with valid `module_id`; verify output includes `module_id`, `status`, `total_calls`, `error_count`, `error_rate`
- **test_health_module_returns_latency_metrics**: Verify output includes `avg_latency_ms` and `p99_latency_ms`
- **test_health_module_returns_recent_errors**: Module with errors in ErrorHistory; verify `recent_errors` array with `code`, `message`, `ai_guidance`, `count`, `first_occurred`, `last_occurred`
- **test_health_module_error_limit_default**: Verify default `error_limit=10`; record 15 errors; verify only 10 returned
- **test_health_module_custom_error_limit**: Pass `error_limit=5`; record 15 errors; verify only 5 returned
- **test_health_module_status_healthy**: Module with error_rate < 1%; verify `status="healthy"`
- **test_health_module_status_degraded**: Module with error_rate between 1-10%; verify `status="degraded"`
- **test_health_module_status_error**: Module with error_rate >= 10%; verify `status="error"`
- **test_health_module_status_unknown**: Module with 0 calls; verify `status="unknown"`
- **test_health_module_annotations**: Verify `readonly=True`, `idempotent=True`

### 2. Implement HealthModuleModule

Add to `src/apcore/sys_modules/health.py`:

```python
class HealthModuleModule:
    description = "Detailed health information for a single module"
    annotations = ModuleAnnotations(readonly=True, idempotent=True)

    def __init__(
        self,
        registry: Registry,
        metrics_collector: MetricsCollector,
        error_history: ErrorHistory,
    ) -> None:
        ...

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        module_id = inputs.get("module_id")
        if not module_id:
            raise InvalidInputError(message="module_id is required")

        if not registry.has(module_id):
            raise ModuleNotFoundError(module_id=module_id)

        error_limit = inputs.get("error_limit", 10)

        # Compute metrics from MetricsCollector snapshot
        # Get recent errors from ErrorHistory
        # Return detailed output
```

- Output shape:
  ```python
  {
      "module_id": str,
      "status": str,  # healthy/degraded/error/unknown
      "total_calls": int,
      "error_count": int,
      "error_rate": float,
      "avg_latency_ms": float,
      "p99_latency_ms": float,
      "recent_errors": [
          {
              "code": str,
              "message": str,
              "ai_guidance": str | None,
              "count": int,
              "first_occurred": str,
              "last_occurred": str,
          }
      ],
  }
  ```

### 3. Extract shared helper for status classification

Create a shared `_classify_status(error_rate: float, total_calls: int) -> str` helper in `health.py` that both `HealthSummaryModule` and `HealthModuleModule` use:

- `total_calls == 0` -> `"unknown"`
- `error_rate < 0.01` -> `"healthy"`
- `error_rate < 0.10` -> `"degraded"`
- `error_rate >= 0.10` -> `"error"`

### 4. Verify tests pass

Run `pytest tests/sys_modules/test_health.py -k "module" -v`.

## Acceptance Criteria

- [ ] Module registered as `system.health.module` with `readonly=True`, `idempotent=True`
- [ ] Input requires `module_id` (str); accepts optional `error_limit` (int, default 10)
- [ ] Raises `MODULE_NOT_FOUND` error if module does not exist
- [ ] Output includes `module_id`, `status`, `total_calls`, `error_count`, `error_rate`
- [ ] Output includes `avg_latency_ms` and `p99_latency_ms`
- [ ] Output includes `recent_errors` array with full error details from ErrorHistory
- [ ] `error_limit` controls maximum number of recent_errors returned
- [ ] Status classification matches: healthy (< 1%), degraded (1-10%), error (>= 10%), unknown (0 calls)
- [ ] Shared `_classify_status` helper used by both summary and module health
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage

## Dependencies

- `apcore.registry.Registry`
- `apcore.observability.metrics.MetricsCollector`
- `apcore.observability.error_history.ErrorHistory` (Task 1)
- `apcore.errors.ModuleNotFoundError`, `InvalidInputError`

## Estimated Time

2 hours
