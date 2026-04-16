### Problem
The `ErrorCodes` class was using a broken and misleading method to enforce immutability. It had `__setattr__` and `__delattr__` traps that raised a `TypeError`, but these traps only fired when an instance was mutated (`ErrorCodes().X = ...`), not when the class was accessed directly (`ErrorCodes.X = ...`).

### Why
In Python, attribute access at the class level bypasses instance methods. To properly enforce immutability at the class level, a metaclass or a `typing.Final[str]` annotation would be required. The existing instance traps provided a false sense of security without actually preventing class-level mutation.

### Solution
Dropped the ineffective `__setattr__` and `__delattr__` traps from the `ErrorCodes` class. Replaced them with a comment explaining that immutability is not strictly enforced at runtime and pointing toward proper alternatives if true immutability is needed in the future.

### Verification
Verified empirically by attempting to assign a new value to `ErrorCodes.MODULE_NOT_FOUND`. Previously, this would succeed without a trap; after removal, it still succeeds, but the codebase no longer contains the misleading "trap" code.
