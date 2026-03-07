"""High-level client for apcore to simplify interaction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Callable

from apcore.config import Config
from apcore.context import Context
from apcore.decorator import module as decorator_module
from apcore.executor import Executor
from apcore.module import PreflightResult
from apcore.registry import Registry


class APCore:
    """A high-level client that manages Registry and Executor.

    This class provides a unified entry point for apcore, making it easier
    for beginners to get started without manually managing multiple objects.
    """

    def __init__(
        self,
        registry: Registry | None = None,
        executor: Executor | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialize the APCore client.

        Args:
            registry: Optional Registry instance. Creates a new one if None.
            executor: Optional Executor instance. Creates a new one if None.
            config: Optional Config instance.
        """
        self.registry = registry or Registry()
        self.config = config
        self.executor = executor or Executor(registry=self.registry, config=config)

    def module(
        self,
        id: str | None = None,  # noqa: A002
        description: str | None = None,
        documentation: str | None = None,
        annotations: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
        examples: list[Any] | None = None,
    ) -> Callable:
        """Decorator to register a function as a module in this client's registry.

        Usage:
            @client.module(id="math.add")
            def add(a: int, b: int) -> int:
                return a + b
        """

        def decorator(func: Callable) -> Callable:
            inner = decorator_module(
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
            return inner(func)

        return decorator

    def register(self, module_id: str, module_obj: Any) -> None:
        """Register a module object directly.

        Args:
            module_id: The ID to register the module under.
            module_obj: The module instance (Class or FunctionModule).
        """
        self.registry.register(module_id, module_obj)

    def call(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> dict[str, Any]:
        """Execute a module call.

        Args:
            module_id: The ID of the module to call.
            inputs: Input arguments for the module.
            context: Optional execution context.

        Returns:
            The module output.
        """
        return self.executor.call(module_id, inputs, context)

    async def call_async(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> dict[str, Any]:
        """Execute an asynchronous module call.

        Args:
            module_id: The ID of the module to call.
            inputs: Input arguments for the module.
            context: Optional execution context.

        Returns:
            The module output.
        """
        return await self.executor.call_async(module_id, inputs, context)

    async def stream(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream module output chunk by chunk.

        Args:
            module_id: The ID of the module to stream.
            inputs: Input arguments for the module.
            context: Optional execution context.

        Yields:
            Dict chunks from the module's stream() or a single call result.
        """
        async for chunk in self.executor.stream(module_id, inputs, context):
            yield chunk

    def validate(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> PreflightResult:
        """Non-destructive preflight check without execution.

        Args:
            module_id: The module to validate against.
            inputs: Input data to validate.
            context: Optional context for call-chain checks.

        Returns:
            PreflightResult with per-check status.
        """
        return self.executor.validate(module_id, inputs, context)

    def describe(self, module_id: str) -> str:
        """Get module description info (for AI/LLM use).

        Args:
            module_id: The module to describe.

        Returns:
            Human-readable description of the module.
        """
        return self.registry.describe(module_id)

    def use(self, middleware: Any) -> APCore:
        """Add class-based middleware. Returns self for chaining."""
        self.executor.use(middleware)
        return self

    def use_before(self, callback: Callable) -> APCore:
        """Add before function middleware. Returns self for chaining."""
        self.executor.use_before(callback)
        return self

    def use_after(self, callback: Callable) -> APCore:
        """Add after function middleware. Returns self for chaining."""
        self.executor.use_after(callback)
        return self

    def remove(self, middleware: Any) -> bool:
        """Remove middleware by identity. Returns True if found and removed."""
        return self.executor.remove(middleware)

    def discover(self) -> int:
        """Discover and register modules from configured extension directories.

        Returns:
            Number of modules discovered.
        """
        return self.registry.discover()

    def list_modules(
        self,
        tags: list[str] | None = None,
        prefix: str | None = None,
    ) -> list[str]:
        """Return sorted list of registered module IDs, optionally filtered.

        Args:
            tags: Only include modules with all specified tags.
            prefix: Only include modules whose ID starts with this prefix.

        Returns:
            Sorted list of module ID strings.
        """
        return self.registry.list(tags=tags, prefix=prefix)
