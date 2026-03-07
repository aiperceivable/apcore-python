# Feature Spec: Comprehensive Test Suite for APCore Client

## Goal

Create a comprehensive unit test suite for the Python `APCore` client class, achieving >=90% code coverage on `src/apcore/client.py`.

## Files to Modify

- `/Users/tercelyi/Workspace/aipartnerup/apcore-python/tests/test_client.py` -- create new test file

## Implementation Steps

### Step 1: Create test file `tests/test_client.py`

```python
"""Unit tests for APCore client class."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from apcore.client import APCore
from apcore.context import Context
from apcore.decorator import FunctionModule
from apcore.errors import ModuleNotFoundError
from apcore.middleware import Middleware
from apcore.registry import Registry
from apcore.executor import Executor
```

### Step 2: Implement construction tests

```python
class TestAPCoreConstruction:
    def test_default_construction(self) -> None:
        """APCore() creates its own Registry and Executor."""
        client = APCore()
        assert isinstance(client.registry, Registry)
        assert isinstance(client.executor, Executor)
        assert client.config is None

    def test_custom_registry(self) -> None:
        """APCore accepts a custom Registry."""
        registry = Registry()
        client = APCore(registry=registry)
        assert client.registry is registry

    def test_custom_executor(self) -> None:
        """APCore accepts a custom Executor."""
        registry = Registry()
        executor = Executor(registry=registry)
        client = APCore(registry=registry, executor=executor)
        assert client.executor is executor

    def test_config_passed_through(self) -> None:
        """Config is stored and passed to auto-created Executor."""
        from apcore.config import Config
        config = Config({"extensions": {"root": "/tmp"}})
        client = APCore(config=config)
        assert client.config is config
```

### Step 3: Implement decorator tests (most critical -- validates the P0 fix)

```python
class TestModuleDecorator:
    def test_returns_original_function(self) -> None:
        client = APCore()
        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b
        assert callable(add)
        assert add(1, 2) == 3

    def test_not_function_module(self) -> None:
        client = APCore()
        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b
        assert not isinstance(add, FunctionModule)

    def test_registers_in_registry(self) -> None:
        client = APCore()
        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b
        assert client.registry.has("math.add")

    def test_attaches_apcore_module(self) -> None:
        client = APCore()
        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b
        assert hasattr(add, "apcore_module")
        assert isinstance(add.apcore_module, FunctionModule)

    def test_preserves_function_name(self) -> None:
        client = APCore()
        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b
        assert add.__name__ == "add"

    def test_auto_id_when_omitted(self) -> None:
        client = APCore()
        @client.module()
        def my_func(x: int) -> int:
            return x
        # Should auto-generate ID and register
        assert client.registry.count >= 1

    def test_custom_metadata(self) -> None:
        client = APCore()
        @client.module(id="math.add", description="Add two numbers", tags=["math"], version="2.0.0")
        def add(a: int, b: int) -> int:
            return a + b
        fm = add.apcore_module
        assert fm.description == "Add two numbers"
        assert fm.tags == ["math"]
        assert fm.version == "2.0.0"

    def test_async_function(self) -> None:
        client = APCore()
        @client.module(id="async.greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}"
        assert callable(greet)
        result = asyncio.get_event_loop().run_until_complete(greet("World"))
        assert result == "Hello, World"
```

### Step 4: Implement register, call, use tests

```python
class TestRegister:
    def test_register_class_module(self) -> None:
        # Create a minimal module-like object
        ...

class TestCall:
    def test_call_sync(self) -> None:
        ...
    def test_call_async(self) -> None:
        ...
    def test_call_not_found(self) -> None:
        ...

class TestUse:
    def test_use_returns_self(self) -> None:
        ...
    def test_use_middleware_fires(self) -> None:
        ...
```

### Step 5: Implement discover and list_modules tests

```python
class TestDiscover:
    def test_discover_delegates(self) -> None:
        ...
    def test_discover_with_path(self) -> None:
        ...

class TestListModules:
    def test_empty(self) -> None:
        ...
    def test_with_entries(self) -> None:
        ...
    def test_filter_tags(self) -> None:
        ...
    def test_filter_prefix(self) -> None:
        ...
```

### Step 6: Run tests and check coverage

```bash
pytest tests/test_client.py -v --cov=apcore.client --cov-report=term-missing
```

Ensure >=90% coverage on `src/apcore/client.py`.

## Test Cases

| Test Function | Verifies |
|--------------|----------|
| `test_default_construction` | Default Registry/Executor creation |
| `test_custom_registry` | Injected Registry is used |
| `test_custom_executor` | Injected Executor is used |
| `test_config_passed_through` | Config is stored and forwarded |
| `test_returns_original_function` | Decorator returns callable, not FunctionModule |
| `test_not_function_module` | Return type is NOT FunctionModule |
| `test_registers_in_registry` | Module appears in registry |
| `test_attaches_apcore_module` | `func.apcore_module` attribute exists |
| `test_preserves_function_name` | `__name__` is preserved |
| `test_auto_id_when_omitted` | Auto-generated ID works |
| `test_custom_metadata` | description, tags, version are set |
| `test_async_function` | Async decorated functions work |
| `test_register_class_module` | Class-based module registration |
| `test_call_sync` | Synchronous call returns result |
| `test_call_async` | Async call returns result |
| `test_call_not_found` | ModuleNotFoundError raised |
| `test_use_returns_self` | Chaining works |
| `test_use_middleware_fires` | Middleware executes during call |
| `test_discover_delegates` | Proxies to registry.discover() |
| `test_discover_with_path` | Scans specific directory |
| `test_list_modules_empty` | Returns [] when empty |
| `test_list_modules_with_entries` | Returns sorted IDs |
| `test_list_modules_filter_tags` | Tag filtering works |
| `test_list_modules_filter_prefix` | Prefix filtering works |

## Acceptance Criteria

- [ ] Test file `tests/test_client.py` exists with all listed test functions
- [ ] All tests pass with `pytest tests/test_client.py -v`
- [ ] Code coverage on `src/apcore/client.py` is >=90%
- [ ] Tests do not depend on filesystem or network (use mocks where needed)
- [ ] Tests cover both sync and async code paths
- [ ] Tests cover error cases (ModuleNotFoundError, invalid inputs)
- [ ] `ruff check tests/test_client.py` reports zero errors
