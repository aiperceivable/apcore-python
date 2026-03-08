# Task: system.control.reload_module — Hot-Reload via Safe Unregister + Re-Discover (PRD F10)

## Goal

Implement the `system.control.reload_module` sys-module that hot-reloads a module by safely unregistering it (with drain), re-discovering its source file, and re-registering it. Annotated with `requires_approval=true, destructive=false`. Emits a `config_changed` event after successful reload and provides full audit output including version tracking and reload duration.

## Files Involved

- `src/apcore/sys_modules/control.py` -- `reload_module` handler function
- `tests/sys_modules/test_control.py` -- Unit tests for reload_module

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_control.py` with tests for:

- **test_reload_module_success**: Reload an existing module; verify output contains `success=True`, `module_id`, `previous_version`, `new_version`, `reload_duration_ms`
- **test_reload_module_not_found**: Attempt to reload a non-existent module_id; verify `MODULE_NOT_FOUND` error is raised
- **test_reload_module_calls_safe_unregister**: Verify `Registry.safe_unregister()` (Algorithm A21) is called with the correct module_id and drain enabled
- **test_reload_module_calls_discover**: Verify the module file is re-discovered after unregistration
- **test_reload_module_calls_register**: Verify the module is re-registered after re-discovery
- **test_reload_module_emits_config_changed_event**: Verify `EventEmitter.emit()` is called with a `config_changed` event after successful reload
- **test_reload_module_no_event_on_failure**: Verify no event is emitted when reload fails
- **test_reload_module_reload_failed_error**: Simulate re-discover or re-register failure; verify `RELOAD_FAILED` error with descriptive message
- **test_reload_module_input_validation**: Verify `module_id` and `reason` are required string inputs
- **test_reload_module_annotations**: Verify module annotations include `requires_approval=true` and `destructive=false`
- **test_reload_module_audit_includes_reason**: Verify the `reason` parameter is logged at INFO level for audit trail
- **test_reload_module_duration_tracking**: Verify `reload_duration_ms` reflects actual elapsed time (not zero)

### 2. Implement reload_module handler

Create `src/apcore/sys_modules/control.py`:

- Define module with `@module` decorator or equivalent registration pattern
- Annotations: `requires_approval=true`, `destructive=false`
- Input schema: `module_id: str`, `reason: str`
- Output schema: `success: bool`, `module_id: str`, `previous_version: str`, `new_version: str`, `reload_duration_ms: float`
- Implementation:
  - Validate `module_id` exists in Registry; raise `MODULE_NOT_FOUND` if not
  - Record `previous_version` from current module definition
  - Call `Registry.safe_unregister(module_id)` with drain
  - Re-discover module file via `discover()` or equivalent scanner
  - Re-register discovered module
  - Record `new_version` from re-registered module definition
  - Measure elapsed time for `reload_duration_ms`
  - Emit `config_changed` event via `EventEmitter`
  - Log reason at INFO level for audit
  - On any failure during re-discover/re-register: raise `RELOAD_FAILED` error
- Full type annotations on all functions and parameters
- Functions <= 50 lines

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_control.py -k "reload" -v`.

## Acceptance Criteria

- [ ] `system.control.reload_module` registered with `requires_approval=true`, `destructive=false`
- [ ] Input: `module_id` (str, required), `reason` (str, required for audit)
- [ ] Output: `success`, `module_id`, `previous_version`, `new_version`, `reload_duration_ms`
- [ ] Uses `Registry.safe_unregister()` (Algorithm A21) with drain before re-discovery
- [ ] Re-discovers and re-registers module after unregistration
- [ ] Raises `MODULE_NOT_FOUND` error for non-existent module_id
- [ ] Raises `RELOAD_FAILED` error when re-discover or re-register fails
- [ ] Emits `config_changed` event via EventEmitter after successful reload
- [ ] Audit logging at INFO level includes `reason` parameter
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of reload_module code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.registry.Registry` -- `safe_unregister()`, `get_definition()`, `register()`
- `apcore.registry.scanner` -- `discover()` for re-discovering module files
- `apcore.events.emitter.EventEmitter` -- for emitting `config_changed` event

## Estimated Time

4 hours
