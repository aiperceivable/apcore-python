# Task: Approval Error Classes and Error Codes

## Goal

Add four approval-specific error classes and three error codes to `src/apcore/errors.py`, following existing error patterns (e.g., `ACLDeniedError`).

## Files Involved

- `src/apcore/errors.py` -- Add error classes and error codes
- `tests/test_approval.py` -- Unit tests for error classes

## Steps

### 1. Write failing tests (TDD)

Create tests for:
- **`ApprovalError`**: Base class inherits from `ModuleError`, carries `result` attribute
- **`ApprovalDeniedError`**: Has code `APPROVAL_DENIED`, message includes module_id, carries result
- **`ApprovalTimeoutError`**: Has code `APPROVAL_TIMEOUT`, carries result
- **`ApprovalPendingError`**: Has code `APPROVAL_PENDING`, carries result with `approval_id`
- **Error codes**: `ErrorCodes.APPROVAL_DENIED`, `APPROVAL_TIMEOUT`, `APPROVAL_PENDING` exist as string constants

### 2. Implement error classes

- `ApprovalError(ModuleError)` -- Base with `result: Any` parameter (typed as `Any` to avoid circular import with `approval.py`)
- `ApprovalDeniedError(ApprovalError)` -- Default code `APPROVAL_DENIED`
- `ApprovalTimeoutError(ApprovalError)` -- Default code `APPROVAL_TIMEOUT`
- `ApprovalPendingError(ApprovalError)` -- Default code `APPROVAL_PENDING`
- Add three constants to `ErrorCodes` class

### 3. Verify tests pass

Run `pytest tests/test_approval.py -v -k error` and confirm all error tests pass.

## Acceptance Criteria

- [x] `ApprovalError` inherits from `ModuleError` and stores `result` attribute
- [x] Three specific subclasses with correct default error codes
- [x] `ErrorCodes` has `APPROVAL_DENIED`, `APPROVAL_TIMEOUT`, `APPROVAL_PENDING` constants
- [x] All four classes exported in `errors.py` `__all__`

## Dependencies

- None (standalone)

## Estimated Time

0.5 hours
