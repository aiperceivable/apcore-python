### Problem
The hot-reload mechanism in the Registry was using a fragile and non-deterministic method to discover module classes after a file change. It relied on `dir(mod)` and took the first attribute with an `execute` method, which could lead to incorrect class selection if a module contained multiple classes or imported other modules with `execute` methods.

### Why
The `_handle_file_change` implementation bypassed the canonical `resolve_entry_point()` logic used during initial discovery. It also used a synthetic module name (`_hot_reload`) that broke the `cls.__module__` invariant enforced by the duck-type checker.

### Solution
Refactored `_handle_file_change` to use the canonical `resolve_entry_point()` logic. This ensures that hot-reloading follows the exact same rules as initial registration, including proper duck-type checking and module name verification.

### Verification
Fixed 2 pyright errors related to unreachable branches in hot-reload logic and verified that `tests/test_safe_reload.py` correctly handles modules with multiple `execute`-capable attributes by selecting the one defined in the file.
