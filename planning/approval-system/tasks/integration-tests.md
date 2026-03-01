# Task: End-to-End Integration Tests

## Goal

Write comprehensive integration tests that exercise the approval system through the full executor pipeline, verifying correct interaction with ACL, middleware, and extension systems.

## Files Involved

- `tests/test_approval_integration.py` -- New file with integration tests

## Steps

### 1. Write integration tests

Create tests for:
- **Sync approved flow**: Module with `requires_approval=True` + `AutoApproveHandler` -> executes successfully
- **Sync denied flow**: Module with `requires_approval=True` + `AlwaysDenyHandler` -> `ApprovalDeniedError`
- **No handler configured**: Module with `requires_approval=True` + no handler -> gate skipped, executes normally
- **No requires_approval**: Module without annotation + handler configured -> gate skipped, executes normally
- **ACL + Approval ordering**: ACL deny fires before approval gate (approval handler never called)
- **Middleware + Approval**: Middleware before/after still executes when approval passes; middleware not invoked on denial
- **Callback handler with identity**: `CallbackApprovalHandler` receives correct identity from context
- **Conditional callback**: Callback approves based on module_id pattern
- **Phase B pending-then-resume**: Handler returns pending, re-call with `_approval_token` invokes `check_approval`
- **ExtensionManager wiring**: Handler registered via extension manager is wired to executor
- **Public API imports**: All 10 new types importable from `apcore`

### 2. Verify all tests pass

Run full suite `pytest tests/ -v` and confirm all 1172 tests pass.

## Acceptance Criteria

- [x] 11 integration tests covering all major interaction scenarios
- [x] ACL-before-approval ordering verified
- [x] Middleware interaction verified
- [x] Phase B resume flow verified end-to-end
- [x] Extension wiring verified
- [x] All tests pass with zero ruff/black/pyright warnings

## Dependencies

- `public-exports` -- All types must be exported
- `extension-point` -- Extension wiring must be implemented

## Estimated Time

2 hours
