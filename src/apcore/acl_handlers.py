"""Built-in ACL condition handlers and handler protocols.

Defines the ACLConditionHandler protocol (sync and async variants),
three basic handlers (identity_types, roles, max_call_depth), and
two compound operators ($or, $not).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, Union, runtime_checkable

from apcore.context import Context

__all__ = [
    "SyncACLConditionHandler",
    "AsyncACLConditionHandler",
    "ACLConditionHandler",
]


@runtime_checkable
class SyncACLConditionHandler(Protocol):
    """Sync condition handler protocol."""

    def evaluate(self, value: Any, context: Context) -> bool: ...


@runtime_checkable
class AsyncACLConditionHandler(Protocol):
    """Async condition handler protocol."""

    async def evaluate(self, value: Any, context: Context) -> bool: ...


ACLConditionHandler = Union[SyncACLConditionHandler, AsyncACLConditionHandler]

# Type alias for the recursive evaluation function used by compound handlers.
_EvalFn = Callable[[dict[str, Any], Context], bool]


# ---------------------------------------------------------------------------
# Basic handlers
# ---------------------------------------------------------------------------


class _IdentityTypesHandler:
    """Check context.identity.type is in the allowed list."""

    def evaluate(self, value: Any, context: Context) -> bool:
        if not isinstance(value, list) or context.identity is None:
            return False
        return context.identity.type in value


class _RolesHandler:
    """Check at least one role overlaps between identity and required roles."""

    def evaluate(self, value: Any, context: Context) -> bool:
        if not isinstance(value, list) or context.identity is None:
            return False
        return bool(set(context.identity.roles) & set(value))


class _MaxCallDepthHandler:
    """Check call chain length does not exceed threshold."""

    def evaluate(self, value: Any, context: Context) -> bool:
        if not isinstance(value, int):
            return False
        return len(context.call_chain) <= value


# ---------------------------------------------------------------------------
# Compound handlers
# ---------------------------------------------------------------------------


class _OrHandler:
    """$or: list of condition dicts. Returns True if ANY sub-set passes."""

    def __init__(self, evaluate_fn: _EvalFn) -> None:
        self._evaluate = evaluate_fn

    def evaluate(self, value: Any, context: Context) -> bool:
        if not isinstance(value, list):
            return False
        for sub in value:
            if not isinstance(sub, dict):
                continue
            if self._evaluate(sub, context):
                return True
        return False


class _NotHandler:
    """$not: single condition dict. Returns True if the sub-set FAILS."""

    def __init__(self, evaluate_fn: _EvalFn) -> None:
        self._evaluate = evaluate_fn

    def evaluate(self, value: Any, context: Context) -> bool:
        if not isinstance(value, dict):
            return False
        return not self._evaluate(value, context)
