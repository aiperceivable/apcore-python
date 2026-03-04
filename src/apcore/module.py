"""Module protocol and related data types."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import BaseModel

    from apcore.context import Context

__all__ = ["Module", "ModuleAnnotations", "ModuleExample", "ValidationResult"]


@runtime_checkable
class Module(Protocol):
    """Protocol for apcore modules.

    Any class with ``input_schema``, ``output_schema``, ``description``,
    and an ``execute(inputs, context)`` method satisfies this protocol.
    Inheriting from ``Module`` is optional but provides IDE autocompletion.

    At runtime, ``@runtime_checkable`` only checks attribute existence.
    Static type checkers (pyright) will verify the full signature.
    """

    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    description: str

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModuleAnnotations:
    """Behavioral annotations for a module.

    Attributes:
        readonly: Whether the module only reads data (no side effects).
        destructive: Whether the module may irreversibly modify data.
        idempotent: Whether repeated calls produce the same result.
        requires_approval: Whether human approval is needed before execution.
        open_world: Whether the module interacts with external systems.
        streaming: Whether the module supports streaming execution.
    """

    readonly: bool = False
    destructive: bool = False
    idempotent: bool = False
    requires_approval: bool = False
    open_world: bool = True
    streaming: bool = False


@dataclass
class ModuleExample:
    """An example invocation of a module.

    Attributes:
        title: Short title for the example.
        inputs: Example input data dict.
        output: Expected output data dict.
        description: Optional description of the example.
    """

    title: str
    inputs: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


@dataclass
class ValidationResult:
    """Result of input validation.

    Attributes:
        valid: Whether validation passed.
        errors: List of error dicts, each with 'field', 'code', 'message' keys.
    """

    valid: bool
    errors: list[dict[str, str]] = field(default_factory=list)
