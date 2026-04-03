"""Typed key for type-safe access to context.data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from apcore.context import Context

T = TypeVar("T")

_MISSING = object()


@dataclass(frozen=True)
class ContextKey(Generic[T]):
    """Typed key for context.data with namespace isolation.

    Provides type-safe get/set/delete/exists operations on a named slot
    within ``Context.data``.  Immutable (frozen dataclass).
    """

    name: str

    def get(self, ctx: Context, default: T | None = None) -> T | None:  # type: ignore[type-var]
        """Return the value for this key, or *default* if absent."""
        value = ctx.data.get(self.name, _MISSING)
        return default if value is _MISSING else value  # type: ignore[return-value]

    def set(self, ctx: Context, value: T) -> None:
        """Store *value* under this key in context.data."""
        ctx.data[self.name] = value

    def delete(self, ctx: Context) -> None:
        """Remove this key from context.data (no-op if absent)."""
        ctx.data.pop(self.name, None)

    def exists(self, ctx: Context) -> bool:
        """Return True if this key is present in context.data."""
        return self.name in ctx.data

    def scoped(self, suffix: str) -> ContextKey[T]:
        """Create a sub-key with ``{name}.{suffix}``."""
        return ContextKey(f"{self.name}.{suffix}")
