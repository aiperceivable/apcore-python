# Feature Spec: Fix @client.module() Return Value

## Goal

Fix the P0 bug where `@client.module()` returns a `FunctionModule` object instead of the original function, making the decorated function uncallable as a normal Python function.

## Files to Modify

- `/Users/tercelyi/Workspace/aipartnerup/apcore-python/src/apcore/client.py` -- fix the `module()` method

## Implementation Steps

1. **Open `src/apcore/client.py`, method `module()` (lines 38-71).**

2. **Replace the `decorator` inner function** (lines 57-69) with the following logic:

   ```python
   def decorator(func: Callable) -> Callable:
       inner_decorator = decorator_module(
           id=id,
           description=description,
           documentation=documentation,
           annotations=annotations,
           tags=tags,
           version=version,
           metadata=metadata,
           examples=examples,
           registry=self.registry,
       )
       return inner_decorator(func)
   ```

3. **Verify the fix does not change the decorator.py contract.** The change is confined to how `client.py` calls `decorator_module`. By omitting `func` as the first positional argument, the code path in `decorator.py` lines 292-294 is taken, which calls `_wrap(func, return_module=False)`. This returns the original function with `func.apcore_module` attached as an attribute.

4. **Run `ruff check --fix .` and `mypy .`** to verify no type or lint issues.

## Test Cases

| Test Function | Verifies |
|--------------|----------|
| `test_module_decorator_returns_function` | `@client.module(id="math.add") def add(...)` -- assert `add` is callable and `add(1, 2) == 3` |
| `test_module_decorator_not_function_module` | `assert not isinstance(add, FunctionModule)` |
| `test_module_decorator_registers_in_registry` | `assert client.registry.has("math.add")` |
| `test_module_decorator_attaches_apcore_module` | `assert isinstance(add.apcore_module, FunctionModule)` |
| `test_module_decorator_preserves_function_name` | `assert add.__name__ == "add"` |
| `test_module_decorator_async_function` | Async decorated function remains awaitable and returns correct result |
| `test_global_module_decorator_returns_function` | Global `@module(id="x")` from `__init__.py` also returns original function |

## Acceptance Criteria

- [ ] `@client.module(id="x") def f(...): ...` returns the original function `f`, not a `FunctionModule`
- [ ] `f(args)` works as a normal function call after decoration
- [ ] `f.apcore_module` is a `FunctionModule` instance
- [ ] The module is registered in `client.registry` under the given ID
- [ ] All existing tests pass without modification
- [ ] `ruff check` and `mypy` report zero errors
- [ ] Global convenience `@module()` decorator in `__init__.py` also works correctly (it delegates to `client.module()`)
