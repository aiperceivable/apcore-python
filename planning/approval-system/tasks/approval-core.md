# Task: ApprovalHandler Protocol, Data Types, and Built-in Handlers

## Goal

Create `src/apcore/approval.py` with the `ApprovalHandler` protocol, `ApprovalRequest`/`ApprovalResult` frozen dataclasses, and three built-in handler implementations.

## Files Involved

- `src/apcore/approval.py` -- New file with all approval types and handlers
- `tests/test_approval.py` -- Unit tests for types and handlers

## Steps

### 1. Write failing tests (TDD)

Create tests for:
- **`ApprovalRequest`**: Fields (module_id, arguments, context, annotations, description, tags), frozen immutability, default values
- **`ApprovalResult`**: Fields (status, approved_by, reason, approval_id, metadata), frozen immutability, default values
- **`ApprovalHandler`**: Protocol with `request_approval` and `check_approval` async methods, `runtime_checkable`
- **`AlwaysDenyHandler`**: `request_approval` returns `status="rejected"`, `check_approval` returns `status="rejected"`
- **`AutoApproveHandler`**: `request_approval` returns `status="approved"`, `approved_by="auto"`
- **`CallbackApprovalHandler`**: Delegates to callback function, `check_approval` returns `status="rejected"` by default

### 2. Implement approval module

- `ApprovalRequest` -- `@dataclass(frozen=True)` with `module_id: str`, `arguments: dict[str, Any]`, `context: Context`, `annotations: ModuleAnnotations`, `description: str | None = None`, `tags: list[str] = field(default_factory=list)`
- `ApprovalResult` -- `@dataclass(frozen=True)` with `status: str`, `approved_by: str | None = None`, `reason: str | None = None`, `approval_id: str | None = None`, `metadata: dict[str, Any] | None = None`
- `ApprovalHandler` -- `@runtime_checkable Protocol` with two async methods
- Three built-in handlers implementing the protocol

### 3. Verify tests pass

Run `pytest tests/test_approval.py -v` and confirm all type and handler tests pass.

## Acceptance Criteria

- [x] `ApprovalRequest` frozen dataclass with all required fields and defaults
- [x] `ApprovalResult` frozen dataclass with all required fields and defaults
- [x] `ApprovalHandler` is `runtime_checkable` Protocol
- [x] `AlwaysDenyHandler` always returns rejected status
- [x] `AutoApproveHandler` always returns approved status with `approved_by="auto"`
- [x] `CallbackApprovalHandler` delegates to provided callback, rejects on `check_approval`

## Dependencies

- None (standalone, but logically follows error-types)

## Estimated Time

1 hour
