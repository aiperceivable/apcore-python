# Task: system.manifest.module — Module Manifest with Source Path (PRD F5)

## Goal

Implement the `system.manifest.module` sys module that returns the full manifest (metadata, schemas, annotations, source path) for a single registered module.

## Files Involved

- `src/apcore/sys_modules/manifest.py` -- `ManifestModuleModule` class
- `tests/sys_modules/test_manifest.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_manifest.py` with tests for:

- **test_manifest_module_requires_module_id**: Call with no `module_id`; verify error
- **test_manifest_module_not_found_error**: Call with non-existent `module_id`; verify `MODULE_NOT_FOUND` error
- **test_manifest_module_returns_basic_fields**: Register module; call; verify output has `module_id`, `description`, `documentation`
- **test_manifest_module_returns_source_path**: Config has `project.source_root="src/modules"`; module path is `extensions/math/add.py`; verify `source_path="src/modules/math/add.py"`
- **test_manifest_module_source_path_null_when_not_configured**: Config has no `project.source_root`; verify `source_path` is `None`
- **test_manifest_module_returns_input_schema**: Module with input_schema; verify `input_schema` in output
- **test_manifest_module_returns_output_schema**: Module with output_schema; verify `output_schema` in output
- **test_manifest_module_returns_annotations**: Module with annotations; verify `annotations` in output
- **test_manifest_module_returns_tags**: Module with tags; verify `tags` in output
- **test_manifest_module_returns_dependencies**: Module with dependencies metadata; verify `dependencies` in output
- **test_manifest_module_returns_metadata**: Module with extra metadata; verify `metadata` in output
- **test_manifest_module_annotations_readonly_idempotent**: Verify module has `readonly=True`, `idempotent=True` annotations

### 2. Implement ManifestModuleModule

Create `src/apcore/sys_modules/manifest.py`:

```python
class ManifestModuleModule:
    description = "Full manifest for a registered module including source path"
    annotations = ModuleAnnotations(readonly=True, idempotent=True)

    def __init__(
        self,
        registry: Registry,
        config: Config | None = None,
    ) -> None:
        self._registry = registry
        self._config = config

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        module_id = inputs.get("module_id")
        if not module_id:
            raise InvalidInputError(message="module_id is required")

        descriptor = self._registry.get_definition(module_id)
        if descriptor is None:
            raise ModuleNotFoundError(module_id=module_id)

        source_root = self._config.get("project.source_root", "") if self._config else ""
        # Compute source_path from source_root + relative module path
        source_path = self._compute_source_path(module_id, source_root)

        return {
            "module_id": descriptor.module_id,
            "description": descriptor.description,
            "documentation": descriptor.documentation,
            "source_path": source_path,
            "input_schema": descriptor.input_schema,
            "output_schema": descriptor.output_schema,
            "annotations": ...,  # from module annotations
            "tags": descriptor.tags,
            "dependencies": ...,  # from metadata
            "metadata": descriptor.metadata,
        }
```

- `source_path` computation:
  - If `source_root` is empty or not configured: return `None`
  - Otherwise: `source_root + "/" + relative_path` (derived from module's file path relative to extensions dir)
- Uses `registry.get_definition()` for module descriptor

### 3. Verify tests pass

Run `pytest tests/sys_modules/test_manifest.py -v`.

## Acceptance Criteria

- [ ] Module registered as `system.manifest.module` with `readonly=True`, `idempotent=True`
- [ ] Input requires `module_id` (str)
- [ ] Raises `MODULE_NOT_FOUND` error if module does not exist
- [ ] Output includes: `module_id`, `description`, `documentation`, `source_path`, `input_schema`, `output_schema`, `annotations`, `tags`, `dependencies`, `metadata`
- [ ] `source_path = project.source_root + "/" + relative_path` when source_root is configured
- [ ] `source_path = None` when `project.source_root` is not configured or empty
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage

## Dependencies

- `apcore.registry.Registry` and `ModuleDescriptor`
- `apcore.config.Config`
- `apcore.errors.ModuleNotFoundError`, `InvalidInputError`

## Estimated Time

2 hours
