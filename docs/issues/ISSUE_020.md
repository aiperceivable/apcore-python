### Problem
Modules disabled via `apcore.disable()` or `ToggleFeatureModule` were still executable if called directly through the `Executor`. The `is_disabled()` check was implemented in the `ToggleState` singleton but was never actually wired into the execution pipeline.

### Why
The module-disabled feature was added to the public API but missed the integration step in the transition to the Pipeline v2 architecture. The `BuiltinModuleLookup` step only checked for module existence in the registry, ignoring the toggle state.

### Solution
Wired the `is_disabled()` check into the `BuiltinModuleLookup` step. If a module is found in the registry but is marked as disabled in the `ToggleState`, the step now raises a `ModuleDisabledError` (corresponding to the `MODULE_DISABLED` error code).

### Verification
Added `tests/test_module_disabled_pipeline.py` which registers a module, disables it, and verifies that `executor.call()` raises `ModuleDisabledError`. Re-enabling the module allows execution to proceed normally.
