# Task: approval_handler Extension Point in ExtensionManager

## Goal

Add `approval_handler` as a non-multiple built-in extension point in `src/apcore/extensions.py` and wire it to `executor.set_approval_handler()` in the `apply()` method.

## Files Involved

- `src/apcore/extensions.py` -- Add extension point and wiring
- `tests/test_extensions.py` -- Update extension point count and expected names
- `tests/test_approval_integration.py` -- Integration test for extension wiring

## Steps

### 1. Write failing tests (TDD)

- Update `tests/test_extensions.py`: extension point count from 5 to 6, add `"approval_handler"` to expected names set
- Add integration test: register `ApprovalHandler` via `ExtensionManager`, verify wired to executor

### 2. Implement extension point

- Import `ApprovalHandler` from `apcore.approval`
- Add `"approval_handler"` to `_built_in_points()` as non-multiple (`multiple=False`)
- In `apply()`: retrieve registered approval handler and call `executor.set_approval_handler(handler)`

### 3. Verify tests pass

Run `pytest tests/test_extensions.py tests/test_approval_integration.py -v` and confirm all pass.

## Acceptance Criteria

- [x] `approval_handler` extension point registered as non-multiple
- [x] `apply()` wires handler to `executor.set_approval_handler()`
- [x] Extension point count and names tests updated
- [x] Docstrings updated to reflect new count

## Dependencies

- `executor-integration` -- `set_approval_handler()` must exist on Executor

## Estimated Time

1 hour
