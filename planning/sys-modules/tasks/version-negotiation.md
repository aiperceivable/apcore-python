# Task: Module Version Negotiation (PRD F18)

## Goal

Implement module version negotiation so that modules can declare a semver version and compatible version ranges, callers can specify a `version_hint` when calling, and the executor selects the appropriate version. Includes deprecation metadata with warnings. Extends PROTOCOL_SPEC section 13.3 to module level.

## Files Involved

- `src/apcore/registry/registry.py` -- Modify to support versioned module registration and lookup
- `src/apcore/executor.py` -- Modify `call()` to accept `version_hint` parameter
- `tests/registry/test_version_negotiation.py` -- Unit tests for version negotiation
- `docs/PROTOCOL_SPEC.md` -- Update section 13.3 with module-level version negotiation

## Steps

### 1. Write failing tests (TDD)

Create `tests/registry/test_version_negotiation.py` with tests for:

- **test_module_declares_version**: Register a module with `version="1.2.0"`; verify version is stored in definition
- **test_module_declares_compatible_versions**: Register a module with `metadata.x-compatible-versions=[">=1.0.0", "<2.0.0"]`; verify it is stored
- **test_module_declares_deprecation**: Register with `metadata.x-deprecation` containing `deprecated_since`, `sunset_version`, `migration_guide`; verify stored
- **test_call_with_version_hint_selects_matching**: Register v1.0.0 and v2.0.0 of same module; call with `version_hint="1.0.0"`; verify v1.0.0 is invoked
- **test_call_without_version_hint_selects_latest**: Register v1.0.0 and v2.0.0; call without `version_hint`; verify v2.0.0 (latest) is invoked
- **test_call_with_semver_range_hint**: Call with `version_hint=">=1.0.0,<2.0.0"`; verify compatible version is selected
- **test_call_version_hint_no_match**: Call with `version_hint="3.0.0"` when only v1 and v2 exist; verify appropriate error or fallback to latest
- **test_deprecated_module_logs_warning**: Call a module with `x-deprecation` metadata; verify deprecation warning is logged
- **test_deprecated_module_includes_migration_guide**: Verify deprecation warning includes `migration_guide` text
- **test_multiple_versions_registered**: Register 3 versions; verify all are accessible via version_hint
- **test_version_hint_partial_match**: Call with `version_hint="1"` (major only); verify best matching version is selected
- **test_module_without_version_defaults**: Register a module without explicit version; verify it defaults gracefully (e.g., `"0.0.0"` or latest)
- **test_compatible_versions_validation**: Verify `x-compatible-versions` ranges are validated against registered versions
- **test_version_negotiation_thread_safe**: Concurrent calls with different version_hints from multiple threads; verify correct routing

### 2. Implement version support in Registry

Modify `src/apcore/registry/registry.py`:

- Extend module definition to include optional `version: str` (semver)
- Extend `metadata` to support `x-compatible-versions: list[str]` and `x-deprecation: dict`
- Internal storage: support multiple versions per module_id (e.g., `dict[str, dict[str, ModuleDefinition]]` keyed by module_id then version)
- `register()`: Accept versioned modules; store by module_id + version
- `get_definition(module_id, version_hint=None)`: Resolve version:
  - If `version_hint` provided: find best matching version using semver comparison
  - If no hint: return latest version (highest semver)
- `list()`: Return unique module_ids (not per-version entries)
- Deprecation check on `get_definition()`: if module has `x-deprecation`, log warning with `deprecated_since`, `sunset_version`, `migration_guide`
- Full type annotations; functions <= 50 lines

### 3. Implement version_hint in Executor

Modify `src/apcore/executor.py`:

- Add `version_hint: str | None = None` parameter to `call()` method
- Pass `version_hint` to `Registry.get_definition()` for version resolution
- Log deprecation warnings when calling deprecated modules

### 4. Update PROTOCOL_SPEC

Add module-level version negotiation to section 13.3:

- Module version field (semver string)
- `x-compatible-versions` metadata for declaring compatibility ranges
- `x-deprecation` metadata for deprecation lifecycle
- Caller `version_hint` behavior and resolution algorithm
- Fallback to latest when no hint or no match

### 5. Verify tests pass

Run `pytest tests/registry/test_version_negotiation.py -v`.

## Acceptance Criteria

- [ ] Module definition supports optional `version` field (semver string)
- [ ] `metadata.x-compatible-versions` declares compatibility ranges
- [ ] `metadata.x-deprecation` with `deprecated_since`, `sunset_version`, `migration_guide`
- [ ] `executor.call()` accepts `version_hint` parameter
- [ ] Multiple versions of same module can be registered simultaneously
- [ ] `version_hint` provided: selects matching version via semver comparison
- [ ] No `version_hint`: selects latest version (highest semver)
- [ ] Deprecated modules log warnings with migration guide
- [ ] PROTOCOL_SPEC section 13.3 extended with module-level version negotiation
- [ ] Thread-safe version resolution
- [ ] Full type annotations on all modified functions and parameters
- [ ] Tests achieve >= 90% coverage of version negotiation code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.registry.Registry` -- modified to support versioned storage and lookup
- `apcore.executor.Executor` -- modified to accept `version_hint`
- A semver comparison library or lightweight implementation

## Estimated Time

5 hours
