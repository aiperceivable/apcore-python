# Task: Approval Gate at Step 4.5 in Executor

## Goal

Integrate the approval gate into `src/apcore/executor.py` at Step 4.5 (between ACL and Input Validation) in all three execution paths: `call()`, `call_async()`, and `stream()`.

## Files Involved

- `src/apcore/executor.py` -- Add approval handler support and Step 4.5 gate
- `src/apcore/approval.py` -- Imported for `ApprovalHandler`, `ApprovalRequest`, `ApprovalResult`
- `src/apcore/errors.py` -- Imported for approval error classes
- `src/apcore/module.py` -- `ModuleAnnotations` for annotation type checking
- `tests/test_approval_executor.py` -- Unit tests for executor approval gate

## Steps

### 1. Write failing tests (TDD)

Create tests for:
- **Gate skipping**: No handler configured, no `requires_approval`, `requires_approval=False`, no annotations
- **Sync `call()`**: Handler rejects -> `ApprovalDeniedError`, handler approves -> execution proceeds
- **Async `call_async()`**: Same behavior as sync
- **`stream()`**: Same behavior as sync
- **Timeout**: Handler returns `status="timeout"` -> `ApprovalTimeoutError`
- **Pending (Phase B)**: Handler returns `status="pending"` -> `ApprovalPendingError` with `approval_id`
- **Phase B resume**: `_approval_token` in arguments -> popped, `check_approval` called instead of `request_approval`
- **Dict annotations**: `{"requires_approval": True}` triggers gate correctly
- **Dataclass annotations**: `ModuleAnnotations(requires_approval=True)` triggers gate correctly
- **Unknown status**: Warning logged, falls through to `ApprovalDeniedError`
- **Handler exception**: Propagated without wrapping
- **`set_approval_handler()`**: Works correctly

### 2. Implement executor changes

- **Constructor**: Add `approval_handler: ApprovalHandler | None = None`, store as `self._approval_handler`
- **`set_approval_handler(handler)`**: Public setter method
- **`from_registry()`**: Add `approval_handler` parameter, pass through
- **Private helpers**:
  - `_needs_approval(module) -> bool`: Check annotations (both `ModuleAnnotations` and `dict` forms)
  - `_build_approval_request(module, arguments, context) -> ApprovalRequest`: Build request, convert dict annotations using `dataclasses.fields()`
  - `_handle_approval_result(result, module_id)`: Map status to continue/error with unknown status warning
  - `_emit_approval_event(result, module_id, context)`: Emit audit event (logging.info + span event if tracing active)
  - `_check_approval_sync(module, arguments, context)`: Sync bridge via `_run_async_in_sync()`
  - `_check_approval_async(module, arguments, context)`: Async implementation
- **`call()`**: Insert `_check_approval_sync()` between Step 4 and Step 5
- **`call_async()`**: Insert `await _check_approval_async()` between Step 4 and Step 5
- **`stream()`**: Insert `await _check_approval_async()` between Step 4 and Step 5

### 3. Verify tests pass

Run `pytest tests/test_approval_executor.py -v` and confirm all executor gate tests pass.

## Acceptance Criteria

- [x] `approval_handler=None` default preserves all existing behavior
- [x] Gate skipped when: no handler, no annotations, `requires_approval` not true
- [x] Gate fires in all three paths: `call()`, `call_async()`, `stream()`
- [x] Correct error mapping: approved -> continue, rejected/timeout/pending -> specific errors
- [x] Phase B `_approval_token` pop-and-resume via `check_approval`
- [x] Both `ModuleAnnotations` and `dict` annotation forms handled
- [x] Unknown status logs warning and raises `ApprovalDeniedError` (fail-closed)
- [x] Sync path uses `_run_async_in_sync()` for async handler bridging
- [x] Audit events emitted: `logging.info` for all decisions + span event when tracing active (Level 3)

## Dependencies

- `error-types` -- Approval error classes must exist
- `approval-core` -- `ApprovalHandler`, `ApprovalRequest`, `ApprovalResult` must exist

## Estimated Time

3 hours
