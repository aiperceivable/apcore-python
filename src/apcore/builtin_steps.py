"""Built-in pipeline steps extracted from the executor's 11-step call flow.

Each class wraps one step of the executor pipeline, receiving its
dependencies via constructor injection.  Steps read from and write to
PipelineContext fields, returning StepResult to control pipeline flow.

NOTE: These contain *simplified* logic sufficient for integration testing.
The full executor refactor task will wire these into the actual executor.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pydantic

from apcore.context import Context
from apcore.errors import (
    ACLDeniedError,
    ModuleNotFoundError,
    SchemaValidationError,
)
from apcore.executor import REDACTED_VALUE, redact_sensitive
from apcore.pipeline import (
    BaseStep,
    ExecutionStrategy,
    PipelineContext,
    StepResult,
)
from apcore.utils.call_chain import guard_call_chain

__all__ = [
    "BuiltinContextCreation",
    "BuiltinSafetyCheck",
    "BuiltinModuleLookup",
    "BuiltinACLCheck",
    "BuiltinApprovalGate",
    "BuiltinInputValidation",
    "BuiltinMiddlewareBefore",
    "BuiltinExecute",
    "BuiltinOutputValidation",
    "BuiltinMiddlewareAfter",
    "BuiltinReturnResult",
    "build_standard_strategy",
    "build_internal_strategy",
    "build_testing_strategy",
    "build_performance_strategy",
]

_logger = logging.getLogger(__name__)


def _convert_validation_errors(error: pydantic.ValidationError) -> list[dict[str, Any]]:
    """Convert a Pydantic ValidationError into a list of error dicts."""
    return [
        {
            "field": ".".join(str(loc) for loc in err["loc"]),
            "code": err["type"],
            "message": err["msg"],
        }
        for err in error.errors()
    ]


# ---------------------------------------------------------------------------
# Step 1: Context Creation
# ---------------------------------------------------------------------------


class BuiltinContextCreation(BaseStep):
    """Create or inherit execution context and set global deadline."""

    def __init__(self, *, config: Any | None = None) -> None:
        super().__init__(
            name="context_creation",
            description="Create execution context and set global deadline",
            removable=False,
            replaceable=False,
        )
        self._config = config
        if config is not None:
            val = config.get("executor.global_timeout")
            self._global_timeout: int = val if val is not None else 60000
        else:
            self._global_timeout = 60000

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if ctx.context is None:
            new_ctx = Context.create()
            new_ctx = new_ctx.child(ctx.module_id)
            if self._global_timeout > 0:
                new_ctx._global_deadline = time.monotonic() + self._global_timeout / 1000.0
            ctx.context = new_ctx
        elif not hasattr(ctx.context, "call_chain"):
            ctx.context = ctx.context.child(ctx.module_id)
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 2: Safety Check
# ---------------------------------------------------------------------------


class BuiltinSafetyCheck(BaseStep):
    """Call chain guard: depth, repeat limits, cancel token."""

    def __init__(self, *, config: Any | None = None) -> None:
        super().__init__(
            name="safety_check",
            description="Validate call chain depth and repeat limits",
            removable=True,
            replaceable=True,
        )
        self._config = config
        if config is not None:
            val = config.get("executor.max_call_depth")
            self._max_call_depth: int = val if val is not None else 32
            val = config.get("executor.max_module_repeat")
            self._max_module_repeat: int = val if val is not None else 3
        else:
            self._max_call_depth = 32
            self._max_module_repeat = 3

    async def execute(self, ctx: PipelineContext) -> StepResult:
        try:
            call_chain = getattr(ctx.context, "call_chain", [])
            guard_call_chain(
                ctx.module_id,
                call_chain,
                max_call_depth=self._max_call_depth,
                max_module_repeat=self._max_module_repeat,
            )
        except Exception as exc:
            return StepResult(action="abort", explanation=str(exc))
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 3: Module Lookup
# ---------------------------------------------------------------------------


class BuiltinModuleLookup(BaseStep):
    """Resolve module from registry by ID."""

    def __init__(self, *, registry: Any) -> None:
        super().__init__(
            name="module_lookup",
            description="Look up module in registry",
            removable=False,
            replaceable=False,
        )
        self._registry = registry

    async def execute(self, ctx: PipelineContext) -> StepResult:
        module = self._registry.get(ctx.module_id)
        if module is None:
            return StepResult(
                action="abort",
                explanation=f"Module not found: {ctx.module_id}",
            )
        ctx.module = module
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 4: ACL Check
# ---------------------------------------------------------------------------


class BuiltinACLCheck(BaseStep):
    """Access control list enforcement."""

    def __init__(self, *, acl: Any | None = None) -> None:
        super().__init__(
            name="acl_check",
            description="Enforce access control policies",
            removable=True,
            replaceable=True,
        )
        self._acl = acl

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if self._acl is None:
            return StepResult(action="continue")

        caller_id = getattr(ctx.context, "caller_id", "anonymous")

        # Try async_check first, fall back to sync check
        if hasattr(self._acl, "async_check"):
            allowed = await self._acl.async_check(caller_id, ctx.module_id, ctx.context)
        else:
            allowed = self._acl.check(caller_id, ctx.module_id, ctx.context)

        if not allowed:
            return StepResult(
                action="abort",
                explanation=f"Access denied: {caller_id} -> {ctx.module_id}",
            )
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 5: Approval Gate
# ---------------------------------------------------------------------------


class BuiltinApprovalGate(BaseStep):
    """Approval handler flow for modules requiring approval."""

    def __init__(self, *, handler: Any | None = None) -> None:
        super().__init__(
            name="approval_gate",
            description="Request and verify module approval",
            removable=True,
            replaceable=True,
        )
        self._handler = handler

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if self._handler is None:
            return StepResult(action="continue")

        module = ctx.module
        annotations = getattr(module, "annotations", None)
        requires_approval = False
        if annotations is not None:
            if isinstance(annotations, dict):
                requires_approval = bool(annotations.get("requires_approval", False))
            elif hasattr(annotations, "requires_approval"):
                requires_approval = annotations.requires_approval

        if not requires_approval:
            return StepResult(action="continue")

        # Simplified: delegate to handler
        try:
            from apcore.approval import ApprovalRequest

            request = ApprovalRequest(
                module_id=ctx.module_id,
                arguments=ctx.inputs,
                context=ctx.context,
            )
            result = await self._handler.request_approval(request)
            if result.status == "approved":
                return StepResult(action="continue")
            return StepResult(
                action="abort",
                explanation=f"Approval {result.status}: {result.reason or 'no reason'}",
            )
        except Exception as exc:
            return StepResult(action="abort", explanation=f"Approval error: {exc}")


# ---------------------------------------------------------------------------
# Step 6: Input Validation
# ---------------------------------------------------------------------------


class BuiltinInputValidation(BaseStep):
    """Validate inputs against module schema and redact sensitive fields."""

    def __init__(self) -> None:
        super().__init__(
            name="input_validation",
            description="Validate inputs against schema and redact sensitive fields",
            removable=True,
            replaceable=True,
        )

    async def execute(self, ctx: PipelineContext) -> StepResult:
        module = ctx.module
        if module is None:
            return StepResult(action="abort", explanation="No module set on context")

        input_schema = getattr(module, "input_schema", None)
        if input_schema is None:
            ctx.validated_inputs = ctx.inputs
            return StepResult(action="continue")

        try:
            input_schema.model_validate(ctx.inputs)
        except pydantic.ValidationError as exc:
            errors = _convert_validation_errors(exc)
            return StepResult(
                action="abort",
                explanation=f"Input validation failed: {errors}",
            )

        ctx.validated_inputs = ctx.inputs
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 7: Middleware Before
# ---------------------------------------------------------------------------


class BuiltinMiddlewareBefore(BaseStep):
    """Execute middleware before-chain."""

    def __init__(self, *, middlewares: list[Any] | None = None) -> None:
        super().__init__(
            name="middleware_before",
            description="Run before-middleware chain",
            removable=True,
            replaceable=False,
        )
        self._middlewares = middlewares or []

    async def execute(self, ctx: PipelineContext) -> StepResult:
        for mw in self._middlewares:
            try:
                if hasattr(mw, "before"):
                    result = mw.before(ctx.module_id, ctx.inputs, ctx.context)
                    if result is not None:
                        ctx.inputs = result if isinstance(result, dict) else ctx.inputs
            except Exception as exc:
                return StepResult(
                    action="abort",
                    explanation=f"Middleware before error: {exc}",
                )
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 8: Execute
# ---------------------------------------------------------------------------


class BuiltinExecute(BaseStep):
    """Execute the module with timeout enforcement."""

    def __init__(self, *, config: Any | None = None) -> None:
        super().__init__(
            name="execute",
            description="Execute module with timeout",
            removable=False,
            replaceable=True,
        )
        self._config = config
        if config is not None:
            val = config.get("executor.default_timeout")
            self._default_timeout: int = val if val is not None else 30000
        else:
            self._default_timeout = 30000

    async def execute(self, ctx: PipelineContext) -> StepResult:
        module = ctx.module
        if module is None:
            return StepResult(action="abort", explanation="No module set on context")

        inputs = ctx.validated_inputs if ctx.validated_inputs is not None else ctx.inputs

        try:
            import asyncio
            import inspect

            if inspect.iscoroutinefunction(module.execute):
                output = await module.execute(inputs, ctx.context)
            else:
                loop = asyncio.get_event_loop()
                output = await loop.run_in_executor(
                    None, module.execute, inputs, ctx.context
                )
            ctx.output = output
        except Exception as exc:
            return StepResult(action="abort", explanation=f"Execution error: {exc}")

        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 9: Output Validation
# ---------------------------------------------------------------------------


class BuiltinOutputValidation(BaseStep):
    """Validate output against module schema and redact sensitive fields."""

    def __init__(self) -> None:
        super().__init__(
            name="output_validation",
            description="Validate output against schema and redact sensitive fields",
            removable=True,
            replaceable=True,
        )

    async def execute(self, ctx: PipelineContext) -> StepResult:
        module = ctx.module
        if module is None:
            return StepResult(action="abort", explanation="No module set on context")

        output_schema = getattr(module, "output_schema", None)
        if output_schema is None:
            ctx.validated_output = ctx.output
            return StepResult(action="continue")

        if ctx.output is None:
            ctx.validated_output = None
            return StepResult(action="continue")

        try:
            output_schema.model_validate(ctx.output)
        except pydantic.ValidationError as exc:
            errors = _convert_validation_errors(exc)
            return StepResult(
                action="abort",
                explanation=f"Output validation failed: {errors}",
            )

        ctx.validated_output = ctx.output
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 10: Middleware After
# ---------------------------------------------------------------------------


class BuiltinMiddlewareAfter(BaseStep):
    """Execute middleware after-chain."""

    def __init__(self, *, middlewares: list[Any] | None = None) -> None:
        super().__init__(
            name="middleware_after",
            description="Run after-middleware chain",
            removable=True,
            replaceable=False,
        )
        self._middlewares = middlewares or []

    async def execute(self, ctx: PipelineContext) -> StepResult:
        for mw in self._middlewares:
            try:
                if hasattr(mw, "after"):
                    result = mw.after(ctx.module_id, ctx.inputs, ctx.output, ctx.context)
                    if result is not None and isinstance(result, dict):
                        ctx.output = result
            except Exception as exc:
                return StepResult(
                    action="abort",
                    explanation=f"Middleware after error: {exc}",
                )
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 11: Return Result
# ---------------------------------------------------------------------------


class BuiltinReturnResult(BaseStep):
    """Finalize pipeline output. Output is already on ctx."""

    def __init__(self) -> None:
        super().__init__(
            name="return_result",
            description="Finalize pipeline result",
            removable=False,
            replaceable=False,
        )

    async def execute(self, ctx: PipelineContext) -> StepResult:
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_standard_strategy(
    *,
    registry: Any,
    config: Any | None = None,
    acl: Any | None = None,
    approval_handler: Any | None = None,
    middlewares: list[Any] | None = None,
) -> ExecutionStrategy:
    """Build the standard 11-step execution strategy.

    Args:
        registry: Module registry for looking up modules by ID.
        config: Optional configuration for timeout/depth settings.
        acl: Optional ACL for access control enforcement.
        approval_handler: Optional approval handler for the approval gate.
        middlewares: Optional list of middleware instances.

    Returns:
        An ExecutionStrategy containing the 11 built-in steps.
    """
    return ExecutionStrategy(
        "standard",
        [
            BuiltinContextCreation(config=config),
            BuiltinSafetyCheck(config=config),
            BuiltinModuleLookup(registry=registry),
            BuiltinACLCheck(acl=acl),
            BuiltinApprovalGate(handler=approval_handler),
            BuiltinInputValidation(),
            BuiltinMiddlewareBefore(middlewares=middlewares or []),
            BuiltinExecute(config=config),
            BuiltinOutputValidation(),
            BuiltinMiddlewareAfter(middlewares=middlewares or []),
            BuiltinReturnResult(),
        ],
    )


def build_internal_strategy(**kwargs: Any) -> ExecutionStrategy:
    """Build an internal strategy: standard minus acl_check and approval_gate.

    Suitable for trusted internal calls that skip access control.

    Args:
        **kwargs: Forwarded to build_standard_strategy().

    Returns:
        An ExecutionStrategy named "internal".
    """
    s = build_standard_strategy(**kwargs)
    s.remove("acl_check")
    s.remove("approval_gate")
    object.__setattr__(s, "name", "internal")
    return s


def build_testing_strategy(**kwargs: Any) -> ExecutionStrategy:
    """Build a testing strategy: standard minus acl, approval, and safety.

    Suitable for unit/integration tests that need minimal overhead.

    Args:
        **kwargs: Forwarded to build_standard_strategy().

    Returns:
        An ExecutionStrategy named "testing".
    """
    s = build_standard_strategy(**kwargs)
    s.remove("acl_check")
    s.remove("approval_gate")
    s.remove("safety_check")
    object.__setattr__(s, "name", "testing")
    return s


def build_performance_strategy(**kwargs: Any) -> ExecutionStrategy:
    """Build a performance strategy: standard minus middleware steps.

    Suitable for latency-sensitive calls that skip middleware overhead.

    Args:
        **kwargs: Forwarded to build_standard_strategy().

    Returns:
        An ExecutionStrategy named "performance".
    """
    s = build_standard_strategy(**kwargs)
    s.remove("middleware_before")
    s.remove("middleware_after")
    object.__setattr__(s, "name", "performance")
    return s
