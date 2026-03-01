# Task: Export New Public Types from __init__.py

## Goal

Add all 10 new approval-related types to `src/apcore/__init__.py` imports and `__all__` list, making them importable from the `apcore` package.

## Files Involved

- `src/apcore/__init__.py` -- Add imports and `__all__` entries
- `tests/test_public_api.py` -- Update expected names set

## Steps

### 1. Write failing tests (TDD)

Update `tests/test_public_api.py` to include all new types in `EXPECTED_NAMES`:
- From `approval.py`: `ApprovalHandler`, `ApprovalRequest`, `ApprovalResult`, `AlwaysDenyHandler`, `AutoApproveHandler`, `CallbackApprovalHandler`
- From `errors.py`: `ApprovalError`, `ApprovalDeniedError`, `ApprovalTimeoutError`, `ApprovalPendingError`

### 2. Add imports and exports

Add to `__init__.py`:
- Import all 6 types from `apcore.approval`
- Import all 4 error types from `apcore.errors`
- Add all 10 to `__all__`

### 3. Verify tests pass

Run `pytest tests/test_public_api.py -v` and confirm public API test passes.

## Acceptance Criteria

- [x] All 10 new types importable via `from apcore import ...`
- [x] All 10 types listed in `__all__`
- [x] `test_public_api.py` updated with new expected names

## Dependencies

- `executor-integration` -- All types must be implemented first

## Estimated Time

0.5 hours
