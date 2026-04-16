### Problem
The `Context` class had two overlapping pairs of serialization methods: `to_dict`/`from_dict` and `serialize`/`deserialize`. These pairs were silently inconsistent: `to_dict` always included `redacted_inputs` even if `None`, whereas `serialize` omitted it. Additionally, `serialize` included a `_context_version` field that `to_dict` lacked, making the resulting dictionaries incompatible.

### Why
`to_dict`/`from_dict` were legacy methods implemented before the formal APCore Context Serialization protocol (AC-003/004/005) was defined. When the spec-compliant `serialize`/`deserialize` methods were added in v0.16.0, the legacy methods were kept for backward compatibility, leading to confusion and divergent data formats.

### Solution
Removed the legacy `to_dict` and `from_dict` methods in v0.18.0. All serialization must now use the spec-compliant `serialize()` and `deserialize()` methods. The `executor` parameter was also removed from `deserialize`; users should now assign the executor directly to the returned `Context` instance.

### Verification
Migrated 11 test sites across 3 test files (including `tests/test_context_serialization.py`) to use the new methods and verified that the context state remains consistent across serialization round-trips.
