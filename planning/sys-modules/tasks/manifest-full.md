# Task: system.manifest.full — Complete System Manifest with Filtering (PRD F12)

## Goal

Implement the `system.manifest.full` sys-module that returns a complete system manifest containing project info and all registered modules with their schemas, annotations, tags, and dependencies. Supports filtering by prefix and/or tags. Annotated with `readonly=true, idempotent=true`. Self-reflective: sys.* modules appear in their own manifest output.

## Files Involved

- `src/apcore/sys_modules/manifest.py` -- `manifest_full` handler function (extend existing file)
- `tests/sys_modules/test_manifest.py` -- Unit tests for manifest_full (add tests)

## Steps

### 1. Write failing tests (TDD)

Add to `tests/sys_modules/test_manifest.py` tests for:

- **test_manifest_full_returns_all_modules**: Register multiple modules; verify output contains all of them in `modules` array
- **test_manifest_full_project_info**: Verify output includes project info fields (name, version, etc.) and `module_count`
- **test_manifest_full_module_fields**: Verify each module entry contains `module_id`, `description`, `documentation`, `source_path`, `input_schema`, `output_schema`, `annotations`, `tags`, `dependencies`, `metadata`
- **test_manifest_full_include_schemas_true**: With `include_schemas=true` (default), verify `input_schema` and `output_schema` are populated
- **test_manifest_full_include_schemas_false**: With `include_schemas=false`, verify `input_schema` and `output_schema` are omitted or null
- **test_manifest_full_include_source_paths_true**: With `include_source_paths=true` (default), verify `source_path` is populated
- **test_manifest_full_include_source_paths_false**: With `include_source_paths=false`, verify `source_path` is omitted or null
- **test_manifest_full_filter_by_prefix**: Register modules with different prefixes; filter by `prefix="payment"`; verify only matching modules returned
- **test_manifest_full_filter_by_tags**: Register modules with tags; filter by `tags=["billing"]`; verify only tagged modules returned
- **test_manifest_full_filter_by_prefix_and_tags**: Apply both prefix and tags filters; verify intersection semantics
- **test_manifest_full_no_filters_returns_all**: With no prefix or tags, verify all modules returned
- **test_manifest_full_self_reflective**: Verify sys.* modules (including `system.manifest.full` itself) appear in the output
- **test_manifest_full_module_count_matches**: Verify `module_count` equals the length of the `modules` array
- **test_manifest_full_annotations**: Verify module annotations include `readonly=true` and `idempotent=true`
- **test_manifest_full_empty_registry**: With no modules registered, verify empty `modules` array and `module_count=0`

### 2. Implement manifest_full handler

Extend `src/apcore/sys_modules/manifest.py`:

- Annotations: `readonly=true`, `idempotent=true`
- Input schema: `include_schemas: bool = True`, `include_source_paths: bool = True`, `prefix: str | None = None`, `tags: list[str] | None = None`
- Output schema: project info + `module_count: int` + `modules: list[ModuleManifestEntry]`
- `ModuleManifestEntry` dataclass: `module_id`, `description`, `documentation`, `source_path`, `input_schema`, `output_schema`, `annotations`, `tags`, `dependencies`, `metadata`
- Implementation:
  - Use `Registry.list()` to get all module IDs
  - Use `Registry.get_definition()` to get full definition for each module
  - Apply prefix filter: `module_id.startswith(prefix)`
  - Apply tags filter: module tags intersect requested tags
  - Optionally include/exclude schemas and source_paths based on input flags
  - Include sys.* modules (self-reflective)
  - Return project info from Config, module_count, and filtered modules array
- Full type annotations on all functions and parameters
- Functions <= 50 lines

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_manifest.py -k "manifest_full" -v`.

## Acceptance Criteria

- [ ] `system.manifest.full` registered with `readonly=true`, `idempotent=true`
- [ ] Input: `include_schemas` (bool, default true), `include_source_paths` (bool, default true), `prefix` (str, nullable), `tags` (list, nullable)
- [ ] Output: project info + `module_count` + `modules` array
- [ ] Each module entry: `module_id`, `description`, `documentation`, `source_path`, `input_schema`, `output_schema`, `annotations`, `tags`, `dependencies`, `metadata`
- [ ] Filters by prefix (startswith) and/or tags (intersection)
- [ ] sys.* modules are self-reflective (included in manifest)
- [ ] `include_schemas=false` omits schema fields; `include_source_paths=false` omits source_path
- [ ] Uses `Registry.list()` + `get_definition()` for module data
- [ ] Full type annotations on all functions and parameters
- [ ] Tests achieve >= 90% coverage of manifest_full code paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- `apcore.registry.Registry` -- `list()`, `get_definition()` for module enumeration
- `apcore.config.Config` -- for project info fields
- Task 9 (manifest-module) -- extends the same `manifest.py` file

## Estimated Time

3 hours
