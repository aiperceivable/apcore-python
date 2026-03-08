# Task: system.control.apply_hotfix — Runtime Patching with Sandbox + Rollback (PRD F20)

## Goal

Implement the `system.control.apply_hotfix` sys-module that applies a unified diff patch to a module at runtime with sandbox validation, automatic rollback on error rate increase, and full audit trail. Annotated with `requires_approval=true, destructive=true`. Rate limited to 1 hotfix per module per hour.

## Files Involved

- `src/apcore/sys_modules/control.py` -- `apply_hotfix` handler function (extend existing file)
- `tests/sys_modules/test_control_hotfix.py` -- Unit tests for apply_hotfix

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_control_hotfix.py` with tests for:

**Input validation:**
- **test_hotfix_input_requires_module_id**: Verify error when `module_id` is missing
- **test_hotfix_input_requires_patch**: Verify error when `patch` (unified diff) is missing
- **test_hotfix_input_requires_reason**: Verify error when `reason` is missing
- **test_hotfix_default_rollback_timeout**: Verify default `rollback_timeout_ms=300000` (5 minutes)
- **test_hotfix_annotations**: Verify module annotations include `requires_approval=true` and `destructive=true`

**Sandbox validation:**
- **test_hotfix_sandbox_pass_applies_patch**: Provide a valid patch; sandbox passes; verify patch is applied via reload
- **test_hotfix_sandbox_fail_returns_error**: Provide a patch that fails sandbox validation; verify `HOTFIX_VALIDATION_FAILED` error and original module unchanged
- **test_hotfix_sandbox_runs_validation**: Verify the sandbox applies the patch in isolation and runs module validation checks
- **test_hotfix_sandbox_does_not_affect_live_module**: During sandbox validation, verify the live module continues to serve requests normally

**Application and monitoring:**
- **test_hotfix_applies_via_reload**: After sandbox passes, verify the patch is applied by reloading the module
- **test_hotfix_monitors_error_rate**: After application, verify error rate is monitored during rollback_timeout window
- **test_hotfix_auto_rollback_on_error_increase**: Simulate increased error rate after patch; verify automatic rollback occurs and `HOTFIX_ROLLED_BACK` status is returned
- **test_hotfix_no_rollback_on_stable_errors**: Apply patch with stable error rate; verify no rollback occurs
- **test_hotfix_module_not_found**: Attempt hotfix on non-existent module; verify `MODULE_NOT_FOUND` error

**Rate limiting:**
- **test_hotfix_rate_limit_one_per_module_per_hour**: Apply hotfix, then immediately try another for same module; verify rate limit error
- **test_hotfix_rate_limit_different_modules_ok**: Apply hotfix to module A, then module B; verify both succeed (rate limit is per-module)
- **test_hotfix_rate_limit_resets_after_hour**: Apply hotfix, advance time by 1 hour, apply again; verify second succeeds

**Audit trail:**
- **test_hotfix_audit_trail_records_who**: Verify audit log includes caller identity
- **test_hotfix_audit_trail_records_what**: Verify audit log includes module_id, patch summary, reason
- **test_hotfix_audit_trail_records_when**: Verify audit log includes timestamp
- **test_hotfix_audit_trail_records_sandbox_results**: Verify audit log includes sandbox validation outcome
- **test_hotfix_audit_trail_records_outcome**: Verify audit log includes final outcome (applied, rolled back, failed)

### 2. Implement sandbox validation

Add to `src/apcore/sys_modules/control.py`:

- `_validate_in_sandbox(module_id: str, patch: str) -> SandboxResult` dataclass
  - Create temporary copy of module source file
  - Apply unified diff patch to the copy
  - Attempt to load/import the patched module in isolation
  - Run any module-level validation checks
  - Return `SandboxResult` with `success: bool`, `errors: list[str]`, `warnings: list[str]`
- On failure: raise `HOTFIX_VALIDATION_FAILED` with sandbox errors
- Full type annotations; functions <= 50 lines

### 3. Implement apply_hotfix handler

Add to `src/apcore/sys_modules/control.py`:

- Annotations: `requires_approval=true`, `destructive=true`
- Input schema: `module_id: str`, `patch: str` (unified diff), `reason: str`, `rollback_timeout_ms: int = 300000`
- Output schema: `success: bool`, `module_id: str`, `sandbox_result: dict`, `outcome: str` (applied, rolled_back, validation_failed), `audit: dict`
- Implementation:
  - Validate `module_id` exists; raise `MODULE_NOT_FOUND` if not
  - Check rate limit: 1 hotfix per module per hour; raise error if exceeded
  - Run sandbox validation; if fails → return `HOTFIX_VALIDATION_FAILED`
  - Apply patch to actual source file
  - Reload module via `system.control.reload_module` logic
  - Record pre-patch error rate baseline
  - Monitor error rate during `rollback_timeout_ms` window
  - If error rate worsens → auto rollback (restore original source, reload) → return `HOTFIX_ROLLED_BACK`
  - Record full audit trail
  - Return success output
- Full type annotations; functions <= 50 lines

### 4. Implement rate limiting

- `_hotfix_timestamps: dict[str, datetime]` — tracks last hotfix time per module_id
- Check: if last hotfix for module_id was < 1 hour ago, reject with rate limit error
- Thread-safe access

### 5. Implement audit trail

- `HotfixAuditEntry` dataclass: `timestamp: str`, `caller_id: str`, `module_id: str`, `patch_summary: str`, `reason: str`, `sandbox_result: dict`, `outcome: str`
- Store audit entries (in-memory list, same lifecycle as runtime)
- Log at INFO level for each hotfix attempt

### 6. Verify tests pass

Run `pytest tests/sys_modules/test_control_hotfix.py -v`.

## Acceptance Criteria

- [ ] `system.control.apply_hotfix` registered with `requires_approval=true`, `destructive=true`
- [ ] Input: `module_id`, `patch` (unified diff), `reason`, `rollback_timeout_ms` (default 300000)
- [ ] Pre-flight sandbox validation: applies patch in isolation, runs validation checks
- [ ] `HOTFIX_VALIDATION_FAILED` error when sandbox fails; original module unchanged
- [ ] Successful sandbox → apply patch via reload; monitor error rate
- [ ] Auto rollback if error rate worsens → `HOTFIX_ROLLED_BACK` outcome
- [ ] Rate limit: 1 hotfix per module per hour
- [ ] Audit trail: who, what, when, sandbox results, outcome
- [ ] `MODULE_NOT_FOUND` error for non-existent module_id
- [ ] `SandboxResult` dataclass with `success`, `errors`, `warnings`
- [ ] `HotfixAuditEntry` dataclass with full audit fields
- [ ] Full type annotations on all functions and parameters
- [ ] Functions <= 50 lines
- [ ] Tests achieve >= 90% coverage of apply_hotfix code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.registry.Registry` -- for module existence checks and reload
- `apcore.events.emitter.EventEmitter` -- for event emission
- `apcore.observability.metrics.MetricsCollector` -- for error rate monitoring
- Task 11 (control-reload) -- reuses reload logic for applying patches
- Task 20 (control-toggle) -- shares disabled state awareness
- Task 1 (error-history) -- for error rate baseline comparison

## Estimated Time

6 hours
