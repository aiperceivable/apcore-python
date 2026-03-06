"""Module protocol and related data types."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import BaseModel

    from apcore.context import Context

__all__ = [
    "Module",
    "ModuleAnnotations",
    "ModuleExample",
    "PreflightCheckResult",
    "PreflightResult",
    "ValidationResult",
]


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


@dataclass(frozen=True)
class PreflightCheckResult:
    """Result of a single preflight check.

    Attributes:
        check: Check name ("module_id", "module_lookup", "call_chain", "acl", "approval", "schema").
        passed: Whether this check passed.
        error: Error details when passed is False; None when passed is True.
    """

    check: str
    passed: bool
    error: dict[str, Any] | None = None


@dataclass
class PreflightResult:
    """Result of Executor.validate() preflight check.

    Duck-type compatible with ValidationResult: has ``valid`` and ``errors``
    properties so existing consumers continue to work.

    Attributes:
        valid: True only if all checks passed.
        checks: Per-step check results.
        requires_approval: True if the module has requires_approval annotation.
    """

    valid: bool
    checks: list[PreflightCheckResult] = field(default_factory=list)
    requires_approval: bool = False

    @property
    def errors(self) -> list[dict[str, Any]]:
        """All failed check errors, compatible with ValidationResult.errors."""
        return [c.error for c in self.checks if not c.passed and c.error is not None]
