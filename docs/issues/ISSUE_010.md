### Problem
The package-level global convenience functions `apcore.call()`, `apcore.call_async()`, and `apcore.stream()` were missing the `version_hint` parameter. This prevented users of the zero-setup API from performing semver-based module negotiation, a core feature of the apcore specification.

### Why
These wrappers were implemented early in the development cycle before the `version_hint` requirement was fully integrated into the `APCore` unified client. They only forwarded `(module_id, inputs, context)` to the underlying executor, silently dropping any additional parameters.

### Solution
Updated the signatures of `call`, `call_async`, and `stream` in `apcore/__init__.py` to include `version_hint: str | None = None`. These parameters are now correctly forwarded to the default `APCore` client instance.

### Verification
Added regression tests in `tests/test_public_api.py` that call these global functions with a `version_hint` and verify that the hint reaches the registry's resolution logic.
