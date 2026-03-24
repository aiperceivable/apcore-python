"""Middleware base class for apcore."""

from __future__ import annotations

from typing import Any, TypeAlias

Context: TypeAlias = Any


class Middleware:
    """Base middleware class with default no-op implementations.

    Subclass and override the methods you need. All methods return None by
    default, which signals 'no modification' to the middleware pipeline.

    Attributes:
        priority: Execution priority (0-1000). Higher priority executes first.
            Middlewares with equal priority preserve registration order.
            Defaults to 0 for backward compatibility.
    """

    priority: int = 0

    def __init__(self, *, priority: int = 0) -> None:
        if not (0 <= priority <= 1000):
            raise ValueError(f"priority must be between 0 and 1000, got {priority}")
        self.priority = priority

    def before(self, module_id: str, inputs: dict[str, Any], context: Context) -> dict[str, Any] | None:
        """Called before module execution. Return modified inputs or None."""
        return None

    def after(
        self,
        module_id: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        context: Context,
    ) -> dict[str, Any] | None:
        """Called after module execution. Return modified output or None."""
        return None

    def on_error(
        self,
        module_id: str,
        inputs: dict[str, Any],
        error: Exception,
        context: Context,
    ) -> dict[str, Any] | None:
        """Called when an error occurs. Return recovery dict or None."""
        return None
