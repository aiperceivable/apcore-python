### Problem
When deserializing `ModuleAnnotations`, there was a precedence conflict between top-level overflow keys and nested keys in the `extra` object. According to PROTOCOL_SPEC §4.4.1 rule 7, nested values should take precedence, but the Python implementation allowed top-level keys to overwrite nested ones.

### Why
The `from_dict` implementation in `apcore/schema/annotations.py` processed top-level keys after the `extra` dict was populated, causing any matching keys at the top level to overwrite the ones already in `extra`.

### Solution
Inverted the precedence logic in `ModuleAnnotations.from_dict` so that keys already present in the `extra` dict are preserved. Top-level keys are still merged into `extra` if they don't conflict, maintaining backward compatibility while adhering to the spec's precedence rules.

### Verification
Added a conformance test case in `tests/schema/test_annotations.py` with an input dict containing both forms of the same key, asserting that the nested value wins.
