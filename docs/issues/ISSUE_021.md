### Problem
The `Registry.register_internal()` method, used primarily for system modules, bypassed all validation checks, including empty IDs, EBNF pattern matching, length limits, and duplicate ID checks. This created an inconsistency where "internal" modules could have IDs that violated core framework invariants.

### Why
`register_internal()` was originally designed as a privileged escape hatch for system modules to use the `system.*` prefix (which is reserved for the framework). However, bypassing *all* validation allowed for potential bugs and inconsistent registry state.

### Solution
Extracted a shared `_validate_module_id()` helper and applied it to both `register()` and `register_internal()`. The internal path still skips the "reserved word" check for the `system` prefix but now strictly enforces empty, pattern, length, and duplicate ID checks.

### Verification
Added a `TestRegisterInternalValidation` suite in `tests/registry/test_registry.py` covering empty rejection, pattern rejection, and duplicate rejection for internal registrations.
