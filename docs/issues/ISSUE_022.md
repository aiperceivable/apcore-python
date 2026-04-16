### Problem
Several built-in system module classes were incorrectly named with a double "Module" suffix (e.g., `ReloadModuleModule`, `HealthModuleModule`, `ManifestModuleModule`, `UsageModuleModule`). This redundant naming pattern was aesthetically inconsistent and deviate from common Python naming conventions.

### Why
The original naming scheme was based on a misunderstanding of the nomenclature, where "Module" was added both to the specific feature name and the generic class suffix. This occurred during the initial implementation of system modules in v0.11.0.

### Solution
Renamed the offending classes in v0.18.0:
- `ReloadModuleModule` → `ReloadModule`
- `HealthModuleModule` → `HealthModule`
- `ManifestModuleModule` → `ManifestModule`
- `UsageModuleModule` → `UsageModule`
For backward compatibility, aliases using the original names were added.

### Verification
Verified that `tests/sys_modules/` still pass using the new class names and that importing the old names still works without raising an `ImportError`.
