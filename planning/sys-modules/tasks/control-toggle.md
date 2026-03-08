# Task: system.control.toggle_feature — Disable/Enable Modules (PRD F19)

## Goal

Implement the `system.control.toggle_feature` sys-module that disables or enables a module without unloading it from the Registry. A disabled module remains registered but returns `MODULE_DISABLED` error on any call. Re-enabling resumes normal operation. Toggle state survives module reload. Annotated with `requires_approval=true`.

## Files Involved

- `src/apcore/sys_modules/control.py` -- `toggle_feature` handler function (extend existing file)
- `tests/sys_modules/test_control.py` -- Unit tests for toggle_feature (add to existing file)

## Steps

### 1. Write failing tests (TDD)

Add to `tests/sys_modules/test_control.py` tests for:

- **test_toggle_feature_disable_success**: Disable an existing module; verify output contains `success=True`, `module_id`, `enabled=False`
- **test_toggle_feature_enable_success**: Re-enable a disabled module; verify `enabled=True`
- **test_toggle_feature_disabled_module_returns_error**: After disabling, call the disabled module; verify `MODULE_DISABLED` error is returned
- **test_toggle_feature_enabled_module_resumes**: After re-enabling, call the module; verify it executes normally
- **test_toggle_feature_module_not_found**: Attempt to toggle a non-existent module_id; verify `MODULE_NOT_FOUND` error
- **test_toggle_feature_emits_module_health_changed**: Verify `EventEmitter.emit()` is called with `module_health_changed` event on toggle
- **test_toggle_feature_survives_reload**: Disable a module, then reload it; verify it remains disabled after reload
- **test_toggle_feature_annotations**: Verify module annotations include `requires_approval=true`
- **test_toggle_feature_reason_logged**: Verify the `reason` parameter is logged at INFO level for audit trail
- **test_toggle_feature_disable_already_disabled**: Disable an already-disabled module; verify idempotent success (no error)
- **test_toggle_feature_enable_already_enabled**: Enable an already-enabled module; verify idempotent success
- **test_toggle_feature_disabled_module_stays_in_registry**: After disabling, verify `Registry.list()` still includes the module
- **test_toggle_feature_disabled_module_in_manifest**: After disabling, verify `system.manifest.full` still shows the module (with a disabled annotation or status)

### 2. Implement toggle state storage

Add to `src/apcore/sys_modules/control.py`:

- `_disabled_modules: set[str]` — module-level set tracking disabled module IDs
- Thread-safe access via lock
- Persistence across reload: store disabled state outside Registry (survives safe_unregister + re-register cycle)

### 3. Implement toggle_feature handler

Add to `src/apcore/sys_modules/control.py`:

- Annotations: `requires_approval=true`
- Input schema: `module_id: str`, `enabled: bool`, `reason: str`
- Output schema: `success: bool`, `module_id: str`, `enabled: bool`
- Implementation:
  - Validate `module_id` exists in Registry; raise `MODULE_NOT_FOUND` if not
  - Add/remove `module_id` from `_disabled_modules` set
  - Emit `module_health_changed` event via EventEmitter
  - Log at INFO level with `reason`
  - Return success output
- Full type annotations; functions <= 50 lines

### 4. Implement MODULE_DISABLED check in Executor

- Before module execution, check if `module_id` is in `_disabled_modules`
- If disabled, return `MODULE_DISABLED` error immediately without invoking the handler
- This check integrates with the existing executor call path (middleware or pre-execution hook)

### 5. Verify tests pass

Run `pytest tests/sys_modules/test_control.py -k "toggle" -v`.

## Acceptance Criteria

- [ ] `system.control.toggle_feature` registered with `requires_approval=true`
- [ ] Input: `module_id` (str), `enabled` (bool), `reason` (str)
- [ ] Output: `success`, `module_id`, `enabled`
- [ ] Disabled module stays in Registry but calls return `MODULE_DISABLED` error
- [ ] Re-enabling resumes normal operation
- [ ] Toggle state survives module reload (persisted outside Registry)
- [ ] Emits `module_health_changed` event on toggle
- [ ] Idempotent: disabling an already-disabled module succeeds without error
- [ ] Audit logging at INFO level includes `reason`
- [ ] `MODULE_NOT_FOUND` error for non-existent module_id
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of toggle_feature code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.registry.Registry` -- `list()`, `get_definition()` for module existence checks
- `apcore.events.emitter.EventEmitter` -- for emitting `module_health_changed` event
- `apcore.executor.Executor` -- modified to check disabled state before execution
- Task 11 (control-reload) -- shares `src/apcore/sys_modules/control.py`

## Estimated Time

4 hours
