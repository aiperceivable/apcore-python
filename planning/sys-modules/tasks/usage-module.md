# Task: system.usage.module — Single Module Detailed Usage (PRD F15)

## Goal

Implement the `system.usage.module` sys-module that returns detailed usage statistics for a single module, including per-caller breakdown, hourly distribution, and p99 latency. Returns `MODULE_NOT_FOUND` error for non-existent modules.

## Files Involved

- `src/apcore/sys_modules/usage.py` -- `usage_module` handler function (same file as usage_summary)
- `tests/sys_modules/test_usage.py` -- Unit tests for usage_module (same file as usage_summary tests)

## Steps

### 1. Write failing tests (TDD)

Add to `tests/sys_modules/test_usage.py` tests for:

- **test_usage_module_success**: Query an existing module; verify output contains `module_id`, `period`, `call_count`, `error_count`, `avg_latency_ms`, `p99_latency_ms`, `trend`
- **test_usage_module_not_found**: Query a non-existent module_id; verify `MODULE_NOT_FOUND` error is raised
- **test_usage_module_default_period**: Call with only `module_id`; verify default `period="24h"` is used
- **test_usage_module_callers_array**: Record calls from multiple callers; verify `callers` array contains per-caller entries
- **test_usage_module_caller_fields**: Each caller entry contains `caller_id`, `call_count`, `error_count`, `avg_latency_ms`
- **test_usage_module_hourly_distribution**: Verify `hourly_distribution` contains 24 entries with `hour`, `call_count`, `error_count`
- **test_usage_module_hourly_distribution_counts**: Record calls at specific hours; verify the corresponding hourly buckets have correct counts
- **test_usage_module_p99_latency**: Record known latencies; verify `p99_latency_ms` is approximately the 99th percentile
- **test_usage_module_avg_latency**: Record known latencies; verify `avg_latency_ms` is the arithmetic mean
- **test_usage_module_trend**: Verify trend calculation matches expected value based on usage patterns
- **test_usage_module_period_1h**: Specify `period="1h"`; verify only last hour's data is returned
- **test_usage_module_period_7d**: Specify `period="7d"`; verify full 7-day data is returned
- **test_usage_module_no_usage_data**: Query a registered module with no calls; verify zero counts and empty callers

### 2. Implement usage_module handler

Add to `src/apcore/sys_modules/usage.py`:

- Input schema: `module_id: str` (required), `period: str = "24h"` (optional)
- Output schema: `module_id: str`, `period: str`, `call_count: int`, `error_count: int`, `avg_latency_ms: float`, `p99_latency_ms: float`, `trend: str`, `callers: list[CallerUsage]`, `hourly_distribution: list[HourlyBucket]`
- `CallerUsage` dataclass: `caller_id: str`, `call_count: int`, `error_count: int`, `avg_latency_ms: float`
- `HourlyBucket` dataclass: `hour: str`, `call_count: int`, `error_count: int`
- Implementation:
  - Validate `module_id` exists; raise `MODULE_NOT_FOUND` if not
  - Call `UsageCollector.get_module(module_id, period)` for detailed data
  - Compute `p99_latency_ms` from raw latency records (99th percentile)
  - Build `callers` array from per-caller breakdown
  - Build `hourly_distribution` with 24 entries (pad missing hours with zeros)
  - Return structured output
- Full type annotations on all functions and parameters
- Functions <= 50 lines

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_usage.py -k "usage_module" -v`.

## Acceptance Criteria

- [ ] Input: `module_id` (str, required), `period` (str, optional, default `"24h"`)
- [ ] Output: `module_id`, `period`, `call_count`, `error_count`, `avg_latency_ms`, `p99_latency_ms`, `trend`
- [ ] `callers` array: each with `caller_id`, `call_count`, `error_count`, `avg_latency_ms`
- [ ] `hourly_distribution`: 24 entries with `hour`, `call_count`, `error_count`
- [ ] Raises `MODULE_NOT_FOUND` error for non-existent module_id
- [ ] Delegates to `UsageCollector.get_module()` for raw data
- [ ] `p99_latency_ms` computed from actual latency records
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of usage_module code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.observability.usage.UsageCollector` -- `get_module()` for detailed usage data
- Task 14 (usage-collector) -- must be implemented first
- Task 15 (usage-summary) -- shares `src/apcore/sys_modules/usage.py`

## Estimated Time

3 hours
