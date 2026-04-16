### Problem
Module annotations provided via YAML companion files (`*_meta.yaml`) were being silently ignored or incorrectly merged, causing them to be lost at registration time. Specifically, if a YAML file only defined one annotation field (e.g., `readonly: true`), it would overwrite the entire annotation object from the code, dropping other fields like `description` or `tags`.

### Why
There were two underlying bugs: (1) `registry/metadata.py` performed a shallow replacement of the `annotations` dict instead of a field-level merge, and (2) the `get_definition()` method in the registry was reading annotations directly from the module class attribute, bypassing the merged metadata stored in the registry.

### Solution
Wired the `merge_annotations` and `merge_examples` utilities into the registry's discovery pipeline. Updated `Registry.get_definition()` to prioritize the merged metadata stored in `_module_meta`. This ensures compliance with PROTOCOL_SPEC §4.13, where YAML overlays are merged into code-defined defaults.

### Verification
Added 5 regression tests in `tests/registry/test_metadata.py` covering field-level merge, YAML-only overlays, and end-to-end `discover() -> get_definition()` round-trips.
