# Task: system.usage.summary — All Modules Usage Overview (PRD F14)

## Goal

Implement the `system.usage.summary` sys-module that returns a usage overview for all registered modules, including call counts, error rates, average latency, unique callers, and trend detection. Annotated with `readonly=true, idempotent=true`. Results sorted by call_count descending.

## Files Involved

- `src/apcore/sys_modules/usage.py` -- `usage_summary` handler function
- `tests/sys_modules/test_usage.py` -- Unit tests for usage_summary

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_usage.py` with tests for:

- **test_usage_summary_default_period**: Call with no input; verify default `period="24h"` is used
- **test_usage_summary_returns_period**: Verify output contains the requested `period` field
- **test_usage_summary_total_calls**: Record known calls; verify `total_calls` matches expected total
- **test_usage_summary_total_errors**: Record known errors; verify `total_errors` matches expected total
- **test_usage_summary_modules_array**: Verify `modules` array contains an entry per module with usage data
- **test_usage_summary_module_fields**: Each module entry contains `module_id`, `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
- **test_usage_summary_sorted_by_call_count_desc**: Verify modules are sorted by `call_count` descending
- **test_usage_summary_period_1h**: Specify `period="1h"`; verify only last hour's data is included
- **test_usage_summary_period_7d**: Specify `period="7d"`; verify 7 days of data is included
- **test_usage_summary_trend_rising**: Module with >20% increase from previous period; verify `trend="rising"`
- **test_usage_summary_trend_stable**: Module with similar counts; verify `trend="stable"`
- **test_usage_summary_trend_declining**: Module with >20% decrease; verify `trend="declining"`
- **test_usage_summary_trend_new**: Module with no previous period data; verify `trend="new"`
- **test_usage_summary_trend_inactive**: Module with no current period data; verify `trend="inactive"`
- **test_usage_summary_empty_no_usage**: With no usage data, verify empty `modules` array and `total_calls=0`
- **test_usage_summary_annotations**: Verify module annotations include `readonly=true` and `idempotent=true`

### 2. Implement usage_summary handler

Create `src/apcore/sys_modules/usage.py`:

- Annotations: `readonly=true`, `idempotent=true`
- Input schema: `period: str = "24h"` (supports `"1h"`, `"24h"`, `"7d"`)
- Output schema: `period: str`, `total_calls: int`, `total_errors: int`, `modules: list[ModuleUsageEntry]`
- `ModuleUsageEntry`: `module_id`, `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
- Implementation:
  - Call `UsageCollector.get_summary(period)` to get per-module summaries
  - Compute `total_calls` and `total_errors` as sums across modules
  - Sort modules by `call_count` descending
  - Return structured output
- Full type annotations on all functions and parameters
- Functions <= 50 lines

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_usage.py -k "summary" -v`.

## Acceptance Criteria

- [ ] `system.usage.summary` registered with `readonly=true`, `idempotent=true`
- [ ] Input: `period` (str, default `"24h"`, supports `"1h"`, `"24h"`, `"7d"`)
- [ ] Output: `period`, `total_calls`, `total_errors`, `modules` array sorted by `call_count` descending
- [ ] Each module entry: `module_id`, `call_count`, `error_count`, `avg_latency_ms`, `unique_callers`, `trend`
- [ ] Trend values: `"rising"` (>20% increase), `"stable"`, `"declining"` (>20% decrease), `"new"`, `"inactive"`
- [ ] Delegates to `UsageCollector.get_summary()` for data aggregation
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of usage_summary code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.observability.usage.UsageCollector` -- `get_summary()` for aggregated usage data
- Task 14 (usage-collector) -- must be implemented first

## Estimated Time

3 hours
