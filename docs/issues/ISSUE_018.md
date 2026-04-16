### Problem
The `BuiltinApprovalGate` step was tightly coupled with the `Executor` class, relying on the `Executor` to perform approval checks via private methods like `_check_approval_async`. The gate had to use `hasattr()` to probe the executor for these methods, which violated modularity and made the gate difficult to test or reuse in custom strategies.

### Why
The approval logic was originally implemented as an inline feature of the `Executor`. When the Pipeline v2 refactor introduced the `BuiltinApprovalGate` step, the logic was only partially moved, leaving the gate as a shell that reached back into the `Executor`'s private internals.

### Solution
Consolidated all approval orchestration logic into `BuiltinApprovalGate`. The gate now self-contains the construction of `ApprovalRequest`, audit log emission, and status-to-error mapping. The `executor` parameter was removed from the gate's constructor as it is no longer required for approval logic.

### Verification
Verified that `tests/test_approval.py` and `tests/test_approval_executor.py` still pass with the new self-contained gate. Audit log emission was verified by checking the `apcore.builtin_steps` logger instead of `apcore.executor`.
