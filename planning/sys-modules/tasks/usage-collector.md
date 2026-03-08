# Task: UsageCollector + UsageMiddleware — Time-Windowed Usage Tracking (PRD F13)

## Goal

Implement a thread-safe `UsageCollector` that stores per-module usage records in hourly buckets with configurable retention, and a `UsageMiddleware` that automatically records call usage (caller_id, latency, success) in the middleware pipeline. Supports summary and per-module queries with trend analysis.

## Files Involved

- `src/apcore/observability/usage.py` -- `UsageRecord` dataclass, `UsageCollector` class, `UsageMiddleware` class
- `tests/observability/test_usage.py` -- Unit tests for UsageCollector and UsageMiddleware

## Steps

### 1. Write failing tests (TDD)

Create `tests/observability/test_usage.py` with tests for:

**UsageRecord dataclass:**
- **test_usage_record_fields**: Verify `timestamp`, `caller_id`, `latency_ms`, `success` fields are present and correctly typed

**UsageCollector:**
- **test_collector_default_retention**: Verify default `retention_hours=168` (7 days)
- **test_collector_record_stores_entry**: Record a usage entry; verify it is stored
- **test_collector_record_hourly_buckets**: Record entries at different hours; verify they are stored in separate hourly buckets
- **test_collector_get_summary_24h**: Record entries over 24h; verify `get_summary(period="24h")` returns `list[ModuleUsageSummary]` with `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
- **test_collector_get_summary_1h**: Verify `get_summary(period="1h")` only includes last hour's data
- **test_collector_get_summary_7d**: Verify `get_summary(period="7d")` includes full 7 days of data
- **test_collector_get_module_detail**: Verify `get_module(module_id, period="24h")` returns `ModuleUsageDetail` with per-caller breakdown and hourly distribution
- **test_collector_get_module_per_caller_breakdown**: Record calls from multiple callers; verify per-caller stats
- **test_collector_get_module_hourly_distribution**: Verify hourly_distribution has entries with `hour`, `call_count`, `error_count`
- **test_collector_trend_rising**: Previous period has fewer calls than current; verify `trend="rising"`
- **test_collector_trend_declining**: Previous period has more calls than current; verify `trend="declining"`
- **test_collector_trend_stable**: Similar call counts; verify `trend="stable"`
- **test_collector_trend_new**: No previous period data; verify `trend="new"`
- **test_collector_trend_inactive**: No current period data; verify `trend="inactive"`
- **test_collector_auto_cleanup_expired_buckets**: Set short retention; record old entries; verify expired buckets are cleaned up
- **test_collector_thread_safety**: Spawn multiple threads recording concurrently; verify no exceptions and consistent state
- **test_collector_unique_callers_count**: Record calls from 3 different callers; verify `unique_callers=3`
- **test_collector_avg_latency_calculation**: Record known latencies; verify `avg_latency_ms` is correct

**UsageMiddleware:**
- **test_middleware_records_on_after**: Verify `UsageMiddleware` records a successful call in `after()` using `Context.caller_id` and elapsed time
- **test_middleware_records_on_error**: Verify `UsageMiddleware` records a failed call in `on_error()` with `success=False`
- **test_middleware_uses_caller_id_from_context**: Verify `caller_id` is extracted from `Context`
- **test_middleware_calculates_elapsed_time**: Verify `latency_ms` reflects elapsed time between `before()` and `after()`

### 2. Implement UsageRecord dataclass

Create `src/apcore/observability/usage.py`:

- `UsageRecord` as a `@dataclass` with fields:
  - `timestamp: str` (ISO 8601)
  - `caller_id: str`
  - `latency_ms: float`
  - `success: bool`
- Full type annotations on all fields

### 3. Implement UsageCollector class

- Constructor: `__init__(retention_hours: int = 168)`
- Internal storage: `dict[str, dict[str, list[UsageRecord]]]` keyed by `module_id` then hourly bucket key
- `_lock: threading.Lock` for thread safety
- `record(module_id: str, caller_id: str, latency_ms: float, success: bool, timestamp: str | None = None) -> None`:
  - Create `UsageRecord`, compute hourly bucket key, store under `module_id`
  - Trigger cleanup of expired buckets
- `get_summary(period: str = "24h") -> list[ModuleUsageSummary]`:
  - Parse period to timedelta
  - Aggregate per-module: `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
  - Trend: compare current period vs previous equal-length period
- `get_module(module_id: str, period: str = "24h") -> ModuleUsageDetail`:
  - Per-caller breakdown: `caller_id`, `call_count`, `error_count`, `avg_latency_ms`
  - Hourly distribution: list of `hour`, `call_count`, `error_count`
- `ModuleUsageSummary` dataclass: `module_id`, `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
- `ModuleUsageDetail` dataclass: extends summary with `callers` list and `hourly_distribution` list
- `_cleanup_expired(module_id: str) -> None`: Remove hourly buckets older than retention
- Functions <= 50 lines

### 4. Implement UsageMiddleware class

- `UsageMiddleware(collector: UsageCollector)`
- `before(context: Context) -> Context`: Store start time in context
- `after(context: Context, result: Any) -> Any`: Compute elapsed, call `collector.record()` with `success=True`
- `on_error(context: Context, error: Exception) -> None`: Compute elapsed, call `collector.record()` with `success=False`
- Uses `Context.caller_id` for caller identification

### 5. Verify tests pass

Run `pytest tests/observability/test_usage.py -v`.

## Acceptance Criteria

- [ ] `UsageRecord` dataclass with `timestamp`, `caller_id`, `latency_ms`, `success` fields
- [ ] `UsageCollector(retention_hours=168)` with 7-day default retention
- [ ] `record()` stores entries in hourly buckets keyed by module_id
- [ ] `get_summary(period)` returns `list[ModuleUsageSummary]` with call_count, error_count, avg_latency_ms, unique_callers, trend
- [ ] `get_module(module_id, period)` returns `ModuleUsageDetail` with per-caller breakdown and hourly distribution
- [ ] Trend calculation: compares current vs previous period (rising >20%, declining >20%, stable, new, inactive)
- [ ] Auto-cleanup of expired hourly buckets beyond retention window
- [ ] Thread-safe via `threading.Lock` on all mutating and reading operations
- [ ] `UsageMiddleware` records in `after()` and `on_error()` using `Context.caller_id` and elapsed time
- [ ] Full type annotations on all functions and parameters
- [ ] Prefer `dataclass` and `Protocol` patterns
- [ ] Tests achieve >= 90% coverage of `usage.py`
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.middleware.base` -- Middleware protocol for `before()`, `after()`, `on_error()`
- `apcore.executor.Context` -- for `caller_id` and timing

## Estimated Time

5 hours
