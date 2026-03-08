# Task: system.control.update_config — Runtime Config Update with Validation (PRD F11)

## Goal

Implement the `system.control.update_config` sys-module that updates a runtime configuration value by dot-path key, validates the new value, emits a `config_changed` event, and logs the change for audit. Annotated with `requires_approval=true, destructive=false`. Changes are runtime-only and not persisted to YAML.

## Files Involved

- `src/apcore/sys_modules/control.py` -- `update_config` handler function (same file as reload_module)
- `tests/sys_modules/test_control.py` -- Unit tests for update_config (same file as reload_module tests)

## Steps

### 1. Write failing tests (TDD)

Add to `tests/sys_modules/test_control.py` tests for:

- **test_update_config_success**: Update a valid key; verify output contains `success=True`, `key`, `old_value`, `new_value`
- **test_update_config_returns_old_value**: Verify `old_value` reflects the value before the update
- **test_update_config_applies_change**: After update, verify `Config.get(key)` returns the new value
- **test_update_config_emits_config_changed_event**: Verify `EventEmitter.emit()` is called with a `config_changed` event containing key, old_value, new_value
- **test_update_config_restricted_key_sys_modules_enabled**: Attempt to update `sys_modules.enabled`; verify `CONFIG_KEY_RESTRICTED` error is raised
- **test_update_config_invalid_value_rejected**: Set a value that fails post-set validation; verify error and value is rolled back
- **test_update_config_audit_logging**: Verify INFO-level log contains key, old_value, new_value, and reason
- **test_update_config_input_validation_missing_key**: Verify error when `key` is empty or missing
- **test_update_config_input_validation_missing_reason**: Verify error when `reason` is empty or missing
- **test_update_config_annotations**: Verify module annotations include `requires_approval=true` and `destructive=false`
- **test_update_config_runtime_only_not_persisted**: Verify no file write occurs (Config YAML file is not modified)
- **test_update_config_dot_path_nested_key**: Update a nested config key like `observability.metrics.enabled`; verify it works correctly

### 2. Implement update_config handler

Add to `src/apcore/sys_modules/control.py`:

- Annotations: `requires_approval=true`, `destructive=false`
- Input schema: `key: str` (dot-path), `value: Any`, `reason: str`
- Output schema: `success: bool`, `key: str`, `old_value: Any`, `new_value: Any`
- Implementation:
  - Validate `key` is not empty
  - Check restricted keys list: `sys_modules.enabled` cannot be changed at runtime; raise `CONFIG_KEY_RESTRICTED`
  - Read `old_value` via `Config.get(key)`
  - Call `Config.set(key, value)`
  - Post-set validation: if invalid, roll back to `old_value` and raise error
  - Emit `config_changed` event via `EventEmitter` with key, old_value, new_value
  - Log at INFO level: key, old_value, new_value, reason
  - Return success output
- Full type annotations on all functions and parameters
- Functions <= 50 lines

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_control.py -k "update_config" -v`.

## Acceptance Criteria

- [ ] `system.control.update_config` registered with `requires_approval=true`, `destructive=false`
- [ ] Input: `key` (dot-path str), `value` (any), `reason` (str, required for audit)
- [ ] Output: `success`, `key`, `old_value`, `new_value`
- [ ] Uses `Config.set(key, value)` for runtime-only updates (not persisted to YAML)
- [ ] Post-set validation rejects invalid values and rolls back
- [ ] Restricted key `sys_modules.enabled` raises `CONFIG_KEY_RESTRICTED` error
- [ ] Emits `config_changed` event via EventEmitter with key, old_value, new_value
- [ ] Audit logging at INFO level includes key, old_value, new_value, reason
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of update_config code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.config.Config` -- `get()`, `set()` for reading and writing config values
- `apcore.events.emitter.EventEmitter` -- for emitting `config_changed` event
- Task 11 (control-reload) -- shares `src/apcore/sys_modules/control.py`

## Estimated Time

3 hours
