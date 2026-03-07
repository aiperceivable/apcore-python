"""Unit tests for APCore client class."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from apcore.client import APCore
from apcore.context import Context
from apcore.decorator import FunctionModule
from apcore.errors import ModuleNotFoundError
from apcore.executor import Executor
from apcore.middleware import Middleware
from apcore.registry import Registry


# ---------------------------------------------------------------------------
# T2: Decorator tests
# ---------------------------------------------------------------------------


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
        assert isinstance(add.apcore_module, FunctionModule)  # type: ignore[attr-defined]

    def test_preserves_function_name(self) -> None:
        client = APCore()

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        assert add.__name__ == "add"

    def test_with_description_only(self) -> None:
        """Verify decorator works with explicit id but no description override."""
        client = APCore()

        @client.module(id="util.identity", description="identity function")
        def my_func(x: int) -> int:
            return x

        assert client.registry.count == 1
        assert callable(my_func)
        assert my_func(42) == 42
        assert my_func.apcore_module.description == "identity function"  # type: ignore[attr-defined]

    def test_custom_metadata(self) -> None:
        client = APCore()

        @client.module(
            id="math.add",
            description="Add two numbers",
            tags=["math"],
            version="2.0.0",
        )
        def add(a: int, b: int) -> int:
            return a + b

        fm = add.apcore_module  # type: ignore[attr-defined]
        assert fm.description == "Add two numbers"
        assert fm.tags == ["math"]
        assert fm.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_async_function(self) -> None:
        client = APCore()

        @client.module(id="async.greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}"

        assert callable(greet)
        result = await greet("World")
        assert result == "Hello, World"

    def test_global_module_decorator_returns_function(self) -> None:
        import apcore

        module_id = "global.test.add"

        @apcore.module(id=module_id)
        def add(a: int, b: int) -> int:
            return a + b

        try:
            assert callable(add)
            assert not isinstance(add, FunctionModule)
            assert add(3, 4) == 7
        finally:
            apcore._default_client.registry.unregister(module_id)


# ---------------------------------------------------------------------------
# T3: Construction tests
# ---------------------------------------------------------------------------


class TestAPCoreConstruction:
    def test_default_construction(self) -> None:
        client = APCore()
        assert isinstance(client.registry, Registry)
        assert isinstance(client.executor, Executor)
        assert client.config is None

    def test_custom_registry(self) -> None:
        registry = Registry()
        client = APCore(registry=registry)
        assert client.registry is registry

    def test_custom_executor(self) -> None:
        registry = Registry()
        executor = Executor(registry=registry)
        client = APCore(registry=registry, executor=executor)
        assert client.executor is executor

    def test_config_passed_through(self) -> None:
        from apcore.config import Config

        config = Config({"extensions": {"root": "/tmp"}})
        client = APCore(config=config)
        assert client.config is config


# ---------------------------------------------------------------------------
# T3: Register tests
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_class_module(self) -> None:
        client = APCore()

        class AddInput(BaseModel):
            a: int
            b: int

        class AddOutput(BaseModel):
            result: int

        class AddModule:
            input_schema = AddInput
            output_schema = AddOutput
            description = "Add two numbers"

            def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
                return {"result": inputs["a"] + inputs["b"]}

        client.register("math.add", AddModule())
        assert client.registry.has("math.add")

        result = client.call("math.add", {"a": 10, "b": 5})
        assert result == {"result": 15}


# ---------------------------------------------------------------------------
# T3: Call tests
# ---------------------------------------------------------------------------


class TestCall:
    def test_call_sync(self) -> None:
        client = APCore()

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        result = client.call("math.add", {"a": 10, "b": 5})
        assert result == {"result": 15}

    @pytest.mark.asyncio
    async def test_call_async(self) -> None:
        client = APCore()

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        result = await client.call_async("math.add", {"a": 10, "b": 5})
        assert result == {"result": 15}

    def test_call_not_found(self) -> None:
        client = APCore()
        with pytest.raises(ModuleNotFoundError):
            client.call("nonexistent.module", {"a": 1})


# ---------------------------------------------------------------------------
# T3: Use (middleware) tests
# ---------------------------------------------------------------------------


class TestUse:
    def test_use_returns_self(self) -> None:
        client = APCore()
        mw = _TrackingMiddleware()
        result = client.use(mw)
        assert result is client

    def test_use_chaining(self) -> None:
        client = APCore()
        mw1 = _TrackingMiddleware()
        mw2 = _TrackingMiddleware()
        result = client.use(mw1).use(mw2)
        assert result is client

    def test_use_middleware_fires(self) -> None:
        client = APCore()
        mw = _TrackingMiddleware()
        client.use(mw)

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        client.call("math.add", {"a": 1, "b": 2})
        assert mw.before_called
        assert mw.after_called


# ---------------------------------------------------------------------------
# T4: Discover tests
# ---------------------------------------------------------------------------


class TestDiscover:
    def test_discover_delegates_to_registry(self) -> None:
        """Verify discover() proxies to registry.discover()."""
        client = APCore()
        # Calling discover() should delegate to registry.discover().
        # Without a valid extensions dir, this raises ConfigNotFoundError.
        from apcore.errors import ConfigNotFoundError

        with pytest.raises(ConfigNotFoundError):
            client.discover()


# ---------------------------------------------------------------------------
# T4: ListModules tests
# ---------------------------------------------------------------------------


class TestListModules:
    def test_empty(self) -> None:
        client = APCore()
        assert client.list_modules() == []

    def test_with_entries(self) -> None:
        client = APCore()

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        @client.module(id="greet.hello")
        def hello(name: str) -> str:
            return f"Hello, {name}"

        modules = client.list_modules()
        assert modules == ["greet.hello", "math.add"]

    def test_filter_prefix(self) -> None:
        client = APCore()

        @client.module(id="math.add")
        def add(a: int, b: int) -> int:
            return a + b

        @client.module(id="greet.hello")
        def hello(name: str) -> str:
            return f"Hello, {name}"

        modules = client.list_modules(prefix="math")
        assert modules == ["math.add"]

    def test_filter_tags(self) -> None:
        client = APCore()

        @client.module(id="math.add", tags=["math", "core"])
        def add(a: int, b: int) -> int:
            return a + b

        @client.module(id="greet.hello", tags=["greet"])
        def hello(name: str) -> str:
            return f"Hello, {name}"

        modules = client.list_modules(tags=["math"])
        assert modules == ["math.add"]


# ---------------------------------------------------------------------------
# T4: Global convenience functions
# ---------------------------------------------------------------------------


class TestGlobalConvenience:
    def test_global_list_modules(self) -> None:
        import apcore

        assert hasattr(apcore, "list_modules")
        assert callable(apcore.list_modules)

    def test_global_discover(self) -> None:
        import apcore

        assert hasattr(apcore, "discover")
        assert callable(apcore.discover)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _TrackingMiddleware(Middleware):
    """Simple middleware that records whether before/after were called."""

    def __init__(self) -> None:
        self.before_called = False
        self.after_called = False

    def before(self, module_id: str, inputs: dict[str, Any], context: Context) -> None:
        self.before_called = True

    def after(
        self,
        module_id: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        context: Context,
    ) -> None:
        self.after_called = True
