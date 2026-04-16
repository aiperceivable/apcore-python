### Problem
The codebase had accumulated 31 static type errors across `executor.py`, `config.py`, `registry.py`, `builtin_steps.py`, and `acl.py`. These errors hindered developer productivity and masked potential runtime bugs.

### Why
Rapid development of Pipeline v2 and new configuration features led to several type-hint inconsistencies, especially around complex `dict` transformations, optional dependencies (like `aiohttp`), and Pydantic v1/v2 compatibility.

### Solution
Performed a comprehensive type-fixing pass to achieve zero errors in `pyright`. Key fixes included: (1) Correcting the `ApprovalDeniedError` constructor signature, (2) Adding `@overload` signatures to `ContextKey.get()` to improve inference, (3) Narrowing `dict` types in registry metadata, and (4) Properly guarding optional imports with `# type: ignore`.

### Verification
Verified by running `pyright src/apcore` and confirming 0 errors.
