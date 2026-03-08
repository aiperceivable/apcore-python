# Task: system.health.summary Sys Module (PRD F3)

## Goal

Implement the `system.health.summary` sys module that provides an aggregated health overview of all registered modules, including status classification, error rates, and top errors from ErrorHistory.

## Files Involved

- `src/apcore/sys_modules/__init__.py` -- Package init
- `src/apcore/sys_modules/health.py` -- `HealthSummaryModule` class
- `tests/sys_modules/__init__.py` -- Package init
- `tests/sys_modules/test_health.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_health.py` with tests for:

- **test_health_summary_module_annotations**: Verify module has `annotations` with `readonly=True`, `idempotent=True`
- **test_health_summary_has_execute_method**: Verify module has `execute(inputs, context)` method
- **test_health_summary_returns_project_info**: Call with no modules registered; verify output includes `project` section with `name`
- **test_health_summary_returns_summary_counts**: Register 3 modules; simulate metrics; verify output includes `total_modules`, `healthy`, `degraded`, `error`, `unknown` counts
- **test_health_summary_status_healthy**: Module with error_rate < 1% is classified as `"healthy"`
- **test_health_summary_status_degraded**: Module with error_rate between 1% and 10% is `"degraded"`
- **test_health_summary_status_error**: Module with error_rate >= 10% is `"error"`
- **test_health_summary_status_unknown**: Module with 0 total calls is `"unknown"`
- **test_health_summary_modules_array**: Verify output `modules` array contains entries with `module_id`, `status`, `error_rate`, `top_error`
- **test_health_summary_top_error_from_error_history**: Module with errors in ErrorHistory; verify `top_error` includes `code`, `message`, `ai_guidance`, `count`
- **test_health_summary_custom_error_rate_threshold**: Pass `error_rate_threshold=0.05` in input; verify status thresholds shift accordingly
- **test_health_summary_include_healthy_false**: Pass `include_healthy=False`; verify healthy modules are excluded from `modules` array
- **test_health_summary_include_healthy_true**: Pass `include_healthy=True`; verify all modules included
- **test_health_summary_no_modules_registered**: Call with empty registry; verify output with zero counts

### 2. Implement HealthSummaryModule

Create `src/apcore/sys_modules/health.py`:

```python
class HealthSummaryModule:
    description = "Aggregated health overview of all registered modules"
    annotations = ModuleAnnotations(readonly=True, idempotent=True)

    def __init__(
        self,
        registry: Registry,
        metrics_collector: MetricsCollector,
        error_history: ErrorHistory,
        config: Config | None = None,
    ) -> None:
        ...

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        ...
```

- Extract `error_rate_threshold` from inputs (default from config or 0.01 for healthy boundary)
- Extract `include_healthy` from inputs (default `True`)
- For each registered module:
  - Compute `error_rate` from MetricsCollector (errors / total calls)
  - Classify status: `healthy` (< 1%), `degraded` (1-10%), `error` (>= 10%), `unknown` (0 calls)
  - Get top error from ErrorHistory
- Build output with `project`, `summary`, and `modules` array

### 3. Create package __init__.py files

- `src/apcore/sys_modules/__init__.py`
- `tests/sys_modules/__init__.py`

### 4. Verify tests pass

Run `pytest tests/sys_modules/test_health.py -k "summary" -v`.

## Acceptance Criteria

- [ ] Module registered as `system.health.summary` with `readonly=True`, `idempotent=True` annotations
- [ ] Input accepts optional `error_rate_threshold` (float) and `include_healthy` (boolean)
- [ ] Output includes `project` info with project name
- [ ] Output includes `summary` with `total_modules`, `healthy`, `degraded`, `error`, `unknown` counts
- [ ] Output includes `modules` array with per-module `module_id`, `status`, `error_rate`, `top_error`
- [ ] Status classification: healthy (< 1%), degraded (1-10%), error (>= 10%), unknown (no calls)
- [ ] `top_error` sourced from ErrorHistory with `code`, `message`, `ai_guidance`, `count`
- [ ] `include_healthy=False` excludes healthy modules from output
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage

## Dependencies

- `apcore.registry.Registry`
- `apcore.observability.metrics.MetricsCollector`
- `apcore.observability.error_history.ErrorHistory` (Task 1)
- `apcore.config.Config`

## Estimated Time

3 hours
