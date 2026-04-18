"""Tests for Executor.stream() async generator."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

import pytest
from pydantic import BaseModel

from apcore.context import Context
from apcore.errors import ModuleNotFoundError, ModuleTimeoutError
from apcore.executor import Executor
from apcore.middleware import Middleware
from apcore.registry import Registry


class SimpleInput(BaseModel):
    name: str


class SimpleOutput(BaseModel):
    greeting: str


class CountInput(BaseModel):
    count: int


class CountOutput(BaseModel):
    value: int = 0


class MockModule:
    def __init__(self) -> None:
        self.input_schema = SimpleInput
        self.output_schema = SimpleOutput

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {"greeting": f"Hello, {inputs['name']}!"}


class StreamingModule:
    def __init__(self) -> None:
        self.input_schema = CountInput
        self.output_schema = CountOutput

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {"value": inputs["count"]}

    async def stream(self, inputs: dict[str, Any], context: Context) -> AsyncIterator[dict[str, Any]]:
        for i in range(1, inputs["count"] + 1):
            yield {"value": i}


class DisjointKeyModule:
    """Module that yields chunks with different keys."""

    def __init__(self) -> None:
        self.input_schema = None
        self.output_schema = None

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {"a": "val_a", "b": "val_b"}

    async def stream(self, inputs: dict[str, Any], context: Context) -> AsyncIterator[dict[str, Any]]:
        yield {"a": "val_a"}
        yield {"b": "val_b"}


def _make_executor(
    module: Any = None,
    module_id: str = "test.module",
    middlewares: list[Middleware] | None = None,
) -> Executor:
    reg = Registry()
    if module is not None:
        reg.register(module_id, module)
    return Executor(registry=reg, middlewares=middlewares)


class TestExecutorStream:
    async def test_fallback_single_chunk_when_no_stream(self) -> None:
        mod = MockModule()
        ex = _make_executor(module=mod)

        chunks: list[dict[str, Any]] = []
        async for chunk in ex.stream("test.module", {"name": "Alice"}):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == {"greeting": "Hello, Alice!"}

    async def test_yields_multiple_chunks(self) -> None:
        mod = StreamingModule()
        ex = _make_executor(module=mod, module_id="counter")

        chunks: list[dict[str, Any]] = []
        async for chunk in ex.stream("counter", {"count": 3}):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0] == {"value": 1}
        assert chunks[1] == {"value": 2}
        assert chunks[2] == {"value": 3}

    async def test_module_not_found(self) -> None:
        ex = _make_executor()

        with pytest.raises(ModuleNotFoundError):
            async for _ in ex.stream("nonexistent"):
                pass

    async def test_before_and_after_middleware(self) -> None:
        mod = StreamingModule()
        log: list[str] = []

        class TrackingMiddleware(Middleware):
            def before(
                self,
                module_id: str,
                inputs: dict[str, Any],
                context: Context,
            ) -> dict[str, Any] | None:
                log.append("before")
                return None

            def after(
                self,
                module_id: str,
                inputs: dict[str, Any],
                output: dict[str, Any],
                context: Context,
            ) -> dict[str, Any] | None:
                log.append("after")
                return None

        ex = _make_executor(module=mod, module_id="counter", middlewares=[TrackingMiddleware()])

        chunks: list[dict[str, Any]] = []
        async for chunk in ex.stream("counter", {"count": 2}):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert log == ["before", "after"]

    async def test_accumulates_disjoint_keys(self) -> None:
        mod = DisjointKeyModule()

        after_output: dict[str, Any] = {}

        class CaptureAfter(Middleware):
            def after(
                self,
                module_id: str,
                inputs: dict[str, Any],
                output: dict[str, Any],
                context: Context,
            ) -> dict[str, Any] | None:
                nonlocal after_output
                after_output = dict(output)
                return None

        ex = _make_executor(module=mod, module_id="disjoint", middlewares=[CaptureAfter()])

        chunks: list[dict[str, Any]] = []
        async for chunk in ex.stream("disjoint", {}):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0] == {"a": "val_a"}
        assert chunks[1] == {"b": "val_b"}
        # After-middleware receives the merged result
        assert after_output == {"a": "val_a", "b": "val_b"}

    async def test_deep_merge_preserves_nested_keys(self) -> None:
        """Chunks with overlapping nested dicts should merge recursively."""

        class NestedStreamModule:
            def __init__(self) -> None:
                self.input_schema = None
                self.output_schema = None

            def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
                return {"user": {"name": "Alice", "age": 30}}

            async def stream(self, inputs: dict[str, Any], context: Context) -> AsyncIterator[dict[str, Any]]:
                yield {"user": {"name": "Alice", "email": "alice@example.com"}}
                yield {"user": {"age": 30}}

        after_output: dict[str, Any] = {}

        class CaptureAfter(Middleware):
            def after(
                self,
                module_id: str,
                inputs: dict[str, Any],
                output: dict[str, Any],
                context: Context,
            ) -> dict[str, Any] | None:
                nonlocal after_output
                after_output = output
                return None

        ex = _make_executor(module=NestedStreamModule(), module_id="nested", middlewares=[CaptureAfter()])

        chunks: list[dict[str, Any]] = []
        async for chunk in ex.stream("nested", {}):
            chunks.append(chunk)

        assert len(chunks) == 2
        # Deep merge: name + email from chunk 1, age from chunk 2 — all preserved
        assert after_output == {"user": {"name": "Alice", "email": "alice@example.com", "age": 30}}


class SlowStreamingModule:
    """Emits chunks with a sleep between each, enough to cross a short deadline."""

    def __init__(self) -> None:
        self.input_schema = None
        self.output_schema = None

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {}

    async def stream(self, inputs: dict[str, Any], context: Context) -> AsyncIterator[dict[str, Any]]:
        for i in range(10):
            await asyncio.sleep(0.05)
            yield {"chunk": i}


class TestStreamGlobalDeadline:
    """Executor.stream() must raise ModuleTimeoutError when global_deadline elapses mid-iteration."""

    @pytest.mark.asyncio
    async def test_stream_raises_on_deadline_elapsed(self) -> None:
        ex = _make_executor(module=SlowStreamingModule(), module_id="slow")
        ctx = Context.create()
        ctx.global_deadline = time.monotonic() + 0.1  # 100ms budget

        collected: list[dict[str, Any]] = []
        with pytest.raises(ModuleTimeoutError):
            async for chunk in ex.stream("slow", {}, context=ctx):
                collected.append(chunk)
        # At least one chunk produced before deadline hit.
        assert len(collected) >= 1
        assert len(collected) < 10  # Did not run to completion.
