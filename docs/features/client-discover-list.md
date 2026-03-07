# Feature Spec: Add discover() and list_modules() Methods to APCore

## Goal

Add `discover()` and `list_modules()` convenience methods to the `APCore` client class so that beginners can discover and list modules without directly accessing the Registry.

## Files to Modify

- `/Users/tercelyi/Workspace/aipartnerup/apcore-python/src/apcore/client.py` -- add two new methods
- `/Users/tercelyi/Workspace/aipartnerup/apcore-python/src/apcore/__init__.py` -- expose global `discover()` and `list_modules()` convenience functions

## Implementation Steps

### Step 1: Add `discover()` to `APCore` in `client.py`

Add the following method after the `use()` method:

```python
def discover(self, path: str | None = None) -> int:
    """Discover modules from extension directories.

    Args:
        path: Optional single directory path to scan. If None, uses
              the extension roots configured on the underlying Registry.

    Returns:
        Number of modules successfully discovered and registered.
    """
    if path is not None:
        temp_registry = Registry(extensions_dir=path, config=self.config)
        count = temp_registry.discover()
        for module_id, module_obj in temp_registry.iter():
            self.registry.register(module_id, module_obj)
        return count
    return self.registry.discover()
```

### Step 2: Add `list_modules()` to `APCore` in `client.py`

Add the following method after `discover()`:

```python
def list_modules(
    self,
    tags: list[str] | None = None,
    prefix: str | None = None,
) -> list[str]:
    """List registered module IDs, optionally filtered.

    Args:
        tags: Filter to modules that have all specified tags.
        prefix: Filter to modules whose ID starts with this prefix.

    Returns:
        Sorted list of matching module IDs.
    """
    return self.registry.list(tags=tags, prefix=prefix)
```

### Step 3: Add import for `Registry` in `client.py`

The `Registry` import already exists in `client.py` (line 11). No change needed.

### Step 4: Update `__init__.py` with global convenience functions

Add after the existing `call_async` function:

```python
def discover(path: str | None = None) -> int:
    """Global convenience for _default_client.discover()."""
    return _default_client.discover(path)

def list_modules(
    tags: list[str] | None = None,
    prefix: str | None = None,
) -> list[str]:
    """Global convenience for _default_client.list_modules()."""
    return _default_client.list_modules(tags=tags, prefix=prefix)
```

Add `"discover"` and `"list_modules"` to the `__all__` list.

### Step 5: Run linters

Run `ruff check --fix .` and `mypy .` to verify correctness.

## Test Cases

| Test Function | Verifies |
|--------------|----------|
| `test_discover_delegates_to_registry` | `client.discover()` calls `registry.discover()` and returns its result |
| `test_discover_with_path_creates_temp_registry` | `client.discover("/some/path")` scans the given path and registers found modules into the client's registry |
| `test_discover_returns_count` | Return value is the number of modules discovered |
| `test_list_modules_empty` | Returns `[]` when no modules are registered |
| `test_list_modules_returns_sorted_ids` | Returns sorted list after registering multiple modules |
| `test_list_modules_filter_by_tags` | Only returns modules matching all specified tags |
| `test_list_modules_filter_by_prefix` | Only returns modules whose ID starts with the prefix |
| `test_list_modules_combined_filters` | Tags and prefix filters work together |

## Acceptance Criteria

- [ ] `client.discover()` delegates to `registry.discover()` and returns module count
- [ ] `client.discover(path="/some/dir")` scans the specified directory
- [ ] `client.list_modules()` returns a sorted list of all registered module IDs
- [ ] `client.list_modules(tags=["math"])` filters by tags
- [ ] `client.list_modules(prefix="math.")` filters by prefix
- [ ] Global `apcore.discover()` and `apcore.list_modules()` work as convenience functions
- [ ] Both methods have full type annotations
- [ ] All new methods are covered by unit tests
- [ ] `ruff check` and `mypy` report zero errors
