# Task: ErrorHistory — Thread-Safe Ring Buffer for Error Tracking (PRD F1)

## Goal

Implement a thread-safe `ErrorHistory` class that stores recent `ErrorEntry` records per module in a ring buffer. Supports deduplication by `(code, message)`, merged counts, and retrieval of recent errors per module or globally.

## Files Involved

- `src/apcore/observability/error_history.py` -- `ErrorEntry` dataclass and `ErrorHistory` class
- `tests/observability/test_error_history.py` -- Unit tests for ErrorHistory

## Steps

### 1. Write failing tests (TDD)

Create `tests/observability/test_error_history.py` with tests for:

- **ErrorEntry dataclass**: Verify fields `module_id`, `code`, `message`, `ai_guidance` (nullable), `timestamp`, `count`, `first_occurred`, `last_occurred` are present and correctly typed
- **test_record_single_error**: Record one error, verify it appears in `get(module_id)`
- **test_record_dedup_merges_count**: Record same `(code, message)` twice for same module; verify `count=2`, `first_occurred` unchanged, `last_occurred` updated
- **test_record_dedup_different_codes**: Record errors with different codes; verify they are stored separately
- **test_record_preserves_ai_guidance**: Record error with `ai_guidance`; verify it is stored
- **test_get_returns_newest_first**: Record multiple errors; verify `get()` returns newest `last_occurred` first
- **test_get_with_limit**: Record 5 errors; `get(module_id, limit=3)` returns only 3
- **test_get_unknown_module_returns_empty**: `get("nonexistent")` returns `[]`
- **test_get_all_returns_newest_first**: Record errors for multiple modules; `get_all()` returns newest first across all modules
- **test_get_all_with_limit**: Record many errors; `get_all(limit=5)` returns only 5
- **test_max_entries_per_module_eviction**: Set `max_entries_per_module=3`; record 5 unique errors for one module; verify only 3 remain (oldest evicted)
- **test_max_total_entries_eviction**: Set `max_total_entries=5`; record 8 errors across modules; verify total count does not exceed 5
- **test_thread_safety_concurrent_records**: Spawn 10 threads each recording 100 errors; verify no exceptions and consistent state
- **test_default_limits**: Verify default `max_entries_per_module=50` and `max_total_entries=1000`

### 2. Implement ErrorEntry dataclass

Create `src/apcore/observability/error_history.py`:

- `ErrorEntry` as a `@dataclass` with fields:
  - `module_id: str`
  - `code: str`
  - `message: str`
  - `ai_guidance: str | None`
  - `timestamp: str` (ISO 8601)
  - `count: int` (default 1)
  - `first_occurred: str` (ISO 8601)
  - `last_occurred: str` (ISO 8601)
- Full type annotations on all fields

### 3. Implement ErrorHistory class

- Constructor: `__init__(max_entries_per_module: int = 50, max_total_entries: int = 1000)`
- Internal storage: `dict[str, list[ErrorEntry]]` keyed by `module_id`
- `_lock: threading.Lock` for thread safety
- `record(module_id: str, error: ModuleError) -> None`:
  - Dedup key: `(error.code, error.message)`
  - If match found in module's list: increment `count`, update `last_occurred`
  - If no match: create new `ErrorEntry`, append to module's list
  - Enforce `max_entries_per_module` by evicting oldest (by `last_occurred`)
  - Enforce `max_total_entries` by evicting globally oldest entry
- `get(module_id: str, limit: int = 10) -> list[ErrorEntry]`:
  - Return entries for module sorted by `last_occurred` descending, up to `limit`
- `get_all(limit: int = 50) -> list[ErrorEntry]`:
  - Flatten all modules' entries, sort by `last_occurred` descending, up to `limit`

### 4. Verify tests pass

Run `pytest tests/observability/test_error_history.py -v`.

## Acceptance Criteria

- [ ] `ErrorEntry` dataclass with all specified fields and full type annotations
- [ ] `ErrorHistory` constructor with configurable `max_entries_per_module` and `max_total_entries`
- [ ] `record()` deduplicates by `(code, message)` per module, merging `count` and updating `last_occurred`
- [ ] `record()` enforces per-module and total entry limits via eviction of oldest entries
- [ ] `get(module_id, limit)` returns entries newest-first, respecting limit
- [ ] `get_all(limit)` returns entries across all modules newest-first, respecting limit
- [ ] Thread safety via `threading.Lock` on all mutating and reading operations
- [ ] Tests achieve >= 90% coverage of `error_history.py`
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.errors.ModuleError` -- for extracting `code`, `message`, `ai_guidance`

## Estimated Time

3 hours
