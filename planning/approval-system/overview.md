# Feature: Approval System

## Overview

Runtime approval gate at Executor Step 4.5 (after ACL, before Input Validation) that enforces the `requires_approval` annotation. When a module declares `requires_approval=true` and an `ApprovalHandler` is configured, the handler is invoked for human or automated sign-off before execution proceeds. Supports both synchronous (Phase A: block until decision) and asynchronous (Phase B: pending status with `_approval_token` resume) approval flows. Fully backward compatible -- when no handler is configured, the gate is skipped entirely.

## Scope

### Included

- `ApprovalRequest` frozen dataclass with module_id, arguments, context, annotations, description, tags
- `ApprovalResult` frozen dataclass with status, approved_by, reason, approval_id, metadata
- `ApprovalHandler` runtime-checkable Protocol with `request_approval()` and `check_approval()` async methods
- Built-in handlers: `AlwaysDenyHandler`, `AutoApproveHandler`, `CallbackApprovalHandler`
- Error hierarchy: `ApprovalError(ModuleError)` base with `ApprovalDeniedError`, `ApprovalTimeoutError`, `ApprovalPendingError`
- Executor integration at Step 4.5 in `call()`, `call_async()`, and `stream()`
- Dual annotation form handling (both `ModuleAnnotations` dataclass and `dict`)
- Phase B `_approval_token` pop-and-resume mechanism
- `approval_handler` extension point in `ExtensionManager`

### Excluded

- Approval history / audit log persistence
- UI components for approval workflows
- Multi-approver consensus or quorum logic

## Technology Stack

- **Language**: Python 3.10+
- **Dependencies**: stdlib (`dataclasses`, `logging`)
- **Internal**: `apcore.context.Context`, `apcore.module.ModuleAnnotations`, `apcore.errors.ModuleError`, `apcore.executor.Executor`, `apcore.extensions.ExtensionManager`
- **Testing**: pytest, pytest-asyncio

## Task Execution Order

| # | Task File | Description | Status |
|---|-----------|-------------|--------|
| 1 | [error-types](./tasks/error-types.md) | Approval error classes and error codes in `errors.py` | completed |
| 2 | [approval-core](./tasks/approval-core.md) | `ApprovalHandler` protocol, data types, and built-in handlers in `approval.py` | completed |
| 3 | [executor-integration](./tasks/executor-integration.md) | Approval gate at Step 4.5 in `Executor.call()`, `call_async()`, `stream()` | completed |
| 4 | [public-exports](./tasks/public-exports.md) | Export all new public types from `__init__.py` | completed |
| 5 | [extension-point](./tasks/extension-point.md) | `approval_handler` extension point in `ExtensionManager` | completed |
| 6 | [integration-tests](./tasks/integration-tests.md) | End-to-end tests through full executor pipeline | completed |

## Progress

| Total | Completed | In Progress | Pending |
|-------|-----------|-------------|---------|
| 6     | 6         | 0           | 0       |

## Reference Documents

- [Approval System Feature Specification](../../docs/features/approval-system.md)
