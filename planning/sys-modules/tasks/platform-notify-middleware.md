# Task: PlatformNotifyMiddleware — Threshold Sensor (PRD F8)

## Goal

Implement `PlatformNotifyMiddleware` that monitors error rates and latency from `MetricsCollector`, emits threshold-exceeded events via `EventEmitter`, and supports hysteresis to prevent alert storms.

## Files Involved

- `src/apcore/middleware/platform_notify.py` -- `PlatformNotifyMiddleware` class
- `tests/test_platform_notify_middleware.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/test_platform_notify_middleware.py` with tests for:

- **test_on_error_emits_error_threshold_exceeded**: Set error_rate_threshold=0.1; mock MetricsCollector to return error_rate=0.15; call `on_error()`; verify `EventEmitter.emit()` called with `event_type="error_threshold_exceeded"`
- **test_on_error_no_emit_below_threshold**: Mock error_rate=0.05 (below 0.1 threshold); call `on_error()`; verify no emit
- **test_on_error_hysteresis_no_re_alert**: Trigger error threshold once; call `on_error()` again with same high rate; verify emit called only once (hysteresis)
- **test_on_error_returns_none**: Verify `on_error()` always returns `None`
- **test_after_emits_latency_threshold_exceeded**: Set latency_p99_threshold_ms=5000; mock MetricsCollector snapshot showing p99 > 5000; call `after()`; verify emit with `event_type="latency_threshold_exceeded"`
- **test_after_no_emit_below_latency_threshold**: Mock p99 below threshold; verify no emit
- **test_after_emits_recovery_event**: Previously alerted on error rate; now error_rate drops below threshold * 0.5; call `after()`; verify emit with `event_type="module_health_changed"` and alert cleared
- **test_after_recovery_clears_alert_flag**: After recovery event, a new threshold breach should emit again (alert flag was cleared)
- **test_after_returns_none**: Verify `after()` always returns `None`
- **test_before_returns_none**: Verify `before()` returns `None`
- **test_constructor_accepts_dependencies**: Verify constructor accepts `EventEmitter`, `MetricsCollector`, `error_rate_threshold`, `latency_p99_threshold_ms`

### 2. Implement PlatformNotifyMiddleware

Create `src/apcore/middleware/platform_notify.py`:

- Constructor:
  ```python
  def __init__(
      self,
      event_emitter: EventEmitter,
      metrics_collector: MetricsCollector,
      error_rate_threshold: float = 0.1,
      latency_p99_threshold_ms: float = 5000.0,
  ) -> None:
  ```
- Internal state: `_alerted: dict[str, set[str]]` mapping module_id to set of active alert types
- `on_error()`:
  - Compute error_rate from MetricsCollector snapshot for the module
  - If error_rate >= threshold AND "error_rate" not in `_alerted[module_id]`:
    - Emit `error_threshold_exceeded` event
    - Add "error_rate" to `_alerted[module_id]`
  - Return `None`
- `after()`:
  - Compute p99 latency from MetricsCollector snapshot for the module
  - If p99 >= latency threshold AND "latency" not in `_alerted[module_id]`:
    - Emit `latency_threshold_exceeded` event
    - Add "latency" to `_alerted[module_id]`
  - Check recovery: if error_rate < threshold * 0.5 AND "error_rate" in `_alerted[module_id]`:
    - Emit `module_health_changed` event with `data={"status": "recovered"}`
    - Remove "error_rate" from `_alerted[module_id]`
  - Return `None`

### 3. Verify tests pass

Run `pytest tests/test_platform_notify_middleware.py -v`.

## Acceptance Criteria

- [ ] `PlatformNotifyMiddleware` extends `Middleware`
- [ ] `on_error()` checks error rate and emits `error_threshold_exceeded` when threshold exceeded
- [ ] `after()` checks p99 latency and emits `latency_threshold_exceeded` when threshold exceeded
- [ ] `after()` detects recovery (error_rate < threshold * 0.5) and emits `module_health_changed`
- [ ] Hysteresis prevents re-alerting until recovery
- [ ] Recovery clears alert flag, allowing future re-alerting
- [ ] All methods return `None`
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage

## Dependencies

- `apcore.events.emitter.EventEmitter` (Task 4)
- `apcore.observability.metrics.MetricsCollector`
- `apcore.middleware.base.Middleware`

## Estimated Time

3 hours
