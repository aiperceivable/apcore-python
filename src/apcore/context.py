"""Execution context, identity, and context logger."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from apcore.cancel import CancelToken

if TYPE_CHECKING:
    from apcore.observability.context_logger import ContextLogger
    from apcore.trace_context import TraceParent


__all__ = ["Context", "Identity", "ContextFactory"]


@dataclass(frozen=True)
class Identity:
    """Caller identity (human/service/AI generic)."""

    id: str
    type: str = "user"
    roles: tuple[str, ...] = field(default_factory=tuple)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Context:
    """Module execution context."""

    trace_id: str
    caller_id: str | None = None
    call_chain: list[str] = field(default_factory=list)
    executor: Any = None
    identity: Identity | None = None
    redacted_inputs: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)
    cancel_token: CancelToken | None = None

    @classmethod
    def create(
        cls,
        executor: Any = None,
        identity: Identity | None = None,
        data: dict[str, Any] | None = None,
        trace_parent: TraceParent | None = None,
    ) -> Context:
        """Create a new top-level Context with a generated UUID v4 trace_id.

        When *trace_parent* is provided, its ``trace_id`` (32 hex chars) is
        converted to UUID format (8-4-4-4-12) and used as the context's
        ``trace_id`` instead of generating a new one.
        """
        if trace_parent is not None:
            hex_id = trace_parent.trace_id
            trace_id = f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}" f"-{hex_id[16:20]}-{hex_id[20:]}"
        else:
            trace_id = str(uuid.uuid4())
        return cls(
            trace_id=trace_id,
            caller_id=None,
            call_chain=[],
            executor=executor,
            identity=identity,
            data=data if data is not None else {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to a dictionary. Omits executor (non-serializable/transient)."""
        result: dict[str, Any] = {
            "trace_id": self.trace_id,
            "caller_id": self.caller_id,
            "call_chain": list(self.call_chain),
        }
        if self.identity is not None:
            result["identity"] = {
                "id": self.identity.id,
                "type": self.identity.type,
                "roles": list(self.identity.roles),
                "attrs": dict(self.identity.attrs),
            }
        else:
            result["identity"] = None
        if self.redacted_inputs is not None:
            result["redacted_inputs"] = dict(self.redacted_inputs)
        else:
            result["redacted_inputs"] = None
        public_data = {k: v for k, v in self.data.items() if not k.startswith("_")}
        result["data"] = public_data
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any], executor: Any = None) -> Context:
        """Deserialize context from a dictionary. Executor must be re-injected."""
        identity = None
        if data.get("identity") is not None:
            identity = Identity(
                id=data["identity"]["id"],
                type=data["identity"].get("type", "user"),
                roles=tuple(data["identity"].get("roles", ())),
                attrs=data["identity"].get("attrs", {}),
            )
        return cls(
            trace_id=data["trace_id"],
            caller_id=data.get("caller_id"),
            call_chain=list(data.get("call_chain", [])),
            executor=executor,
            identity=identity,
            redacted_inputs=data.get("redacted_inputs"),
            data=data.get("data", {}),
        )

    @property
    def logger(self) -> ContextLogger:
        """Return a ContextLogger with this context's trace_id and caller_id."""
        from apcore.observability.context_logger import ContextLogger

        return ContextLogger.from_context(self, name=self.caller_id or "unknown")

    def child(self, target_module_id: str) -> Context:
        """Create a child Context for calling a target module.

        The ``data`` dict is intentionally shared (not copied) between parent
        and child contexts.  Middleware such as TracingMiddleware and
        MetricsMiddleware rely on this shared reference to maintain span and
        timing stacks across nested module-to-module calls.
        """
        return Context(
            trace_id=self.trace_id,
            caller_id=self.call_chain[-1] if self.call_chain else None,
            call_chain=[*self.call_chain, target_module_id],
            executor=self.executor,
            identity=self.identity,
            data=self.data,
            cancel_token=self.cancel_token,
        )


@runtime_checkable
class ContextFactory(Protocol):
    """Protocol for creating Context from framework-specific requests.

    Web framework integrations should implement this to extract Identity
    from HTTP requests (e.g., Django request.user, JWT tokens, API keys).

    Example:
        class DjangoContextFactory:
            def create_context(self, request: HttpRequest) -> Context:
                identity = Identity(
                    id=str(request.user.id),
                    type="user",
                    roles=list(request.user.groups.values_list("name", flat=True)),
                )
                return Context.create(identity=identity)
    """

    def create_context(self, request: Any) -> Context: ...
