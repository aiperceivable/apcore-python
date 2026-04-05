"""Built-in pipeline steps for the v0.17 Pipeline v2 execution model.

Each class wraps one step of the executor pipeline, receiving its
dependencies via constructor injection.  Steps read from and write to
PipelineContext fields, returning StepResult to control pipeline flow.

Pipeline v2 steps raise domain errors directly instead of returning
abort results, enabling the executor to propagate typed exceptions.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any

import pydantic

from apcore.cancel import ExecutionCancelledError
from apcore.context import Context
from apcore.context_keys import REDACTED_OUTPUT
from apcore.errors import (
    ACLDeniedError,
    ApprovalDeniedError,
    ApprovalPendingError,
    InvalidInputError,
    ModuleNotFoundError,
    ModuleTimeoutError,
    SchemaValidationError,
)
from apcore.pipeline import (
    BaseStep,
    ExecutionStrategy,
    PipelineContext,
    StepResult,
)
from apcore.utils.call_chain import guard_call_chain

__all__ = [
    "BuiltinContextCreation",
    "BuiltinCallChainGuard",
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

    def __init__(
        self,
        *,
        config: Any | None = None,
        executor: Any | None = None,
    ) -> None:
        super().__init__(
            name="context_creation",
            description="Create execution context and set global deadline",
            removable=False,
            replaceable=False,
            pure=True,
        )
        self._config = config
        self._executor = executor
        if config is not None:
            val = config.get("executor.global_timeout")
            self._global_timeout: int = val if val is not None else 60000
        else:
            self._global_timeout = 60000

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if ctx.context is None:
            new_ctx = Context.create(executor=self._executor)
            new_ctx = new_ctx.child(ctx.module_id)
            if self._global_timeout > 0:
                new_ctx._global_deadline = time.monotonic() + self._global_timeout / 1000.0
            ctx.context = new_ctx
        else:
            # Derive child context to add module_id to call chain
            child = ctx.context.child(ctx.module_id)
            ctx.context = child
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 2: Call Chain Guard
# ---------------------------------------------------------------------------


class BuiltinCallChainGuard(BaseStep):
    """Call chain guard: depth, repeat limits, cancel token."""

    def __init__(self, *, config: Any | None = None) -> None:
        super().__init__(
            name="call_chain_guard",
            description="Validate call chain depth and repeat limits",
            removable=True,
            replaceable=True,
            pure=True,
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
        call_chain = getattr(ctx.context, "call_chain", [])
        guard_call_chain(
            ctx.module_id,
            call_chain,
            max_call_depth=self._max_call_depth,
            max_module_repeat=self._max_module_repeat,
        )
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 3: Module Lookup
# ---------------------------------------------------------------------------


class BuiltinModuleLookup(BaseStep):
    """Resolve module from registry by ID with optional version hint."""

    def __init__(self, *, registry: Any) -> None:
        super().__init__(
            name="module_lookup",
            description="Look up module in registry",
            removable=False,
            replaceable=False,
            pure=True,
        )
        self._registry = registry

    async def execute(self, ctx: PipelineContext) -> StepResult:
        version_hint = getattr(ctx, "version_hint", None)
        if version_hint is not None:
            module = self._registry.get(ctx.module_id, version_hint=version_hint)
        else:
            module = self._registry.get(ctx.module_id)
        if module is None:
            raise ModuleNotFoundError(module_id=ctx.module_id)
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
            pure=True,
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
            raise ACLDeniedError(caller_id=caller_id, target_id=ctx.module_id)
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 5: Approval Gate
# ---------------------------------------------------------------------------


class BuiltinApprovalGate(BaseStep):
    """Approval handler flow for modules requiring approval."""

    def __init__(
        self,
        *,
        handler: Any | None = None,
        executor: Any | None = None,
    ) -> None:
        super().__init__(
            name="approval_gate",
            description="Request and verify module approval",
            removable=True,
            replaceable=True,
            pure=False,
        )
        self._handler = handler
        self._executor = executor

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

        # Phase B token support: if inputs contain _approval_token, delegate
        if "_approval_token" in ctx.inputs:
            token = ctx.inputs.pop("_approval_token")
            result = await self._handler.check_approval(token)
        elif self._executor is not None and hasattr(self._executor, "_check_approval_async"):
            await self._executor._check_approval_async(
                module, ctx.module_id, ctx.inputs, ctx.context,
            )
            return StepResult(action="continue")
        else:
            from apcore.approval import ApprovalRequest

            request = ApprovalRequest(
                module_id=ctx.module_id,
                arguments=ctx.inputs,
                context=ctx.context,
            )
            result = await self._handler.request_approval(request)

        if result.status == "approved":
            return StepResult(action="continue")
        if result.status == "pending":
            raise ApprovalPendingError(
                message=f"Approval pending: {result.reason or 'awaiting review'}",
            )
        raise ApprovalDeniedError(
            message=f"Approval {result.status}: {result.reason or 'no reason'}",
        )


# ---------------------------------------------------------------------------
# Step 6: Middleware Before
# ---------------------------------------------------------------------------


class BuiltinMiddlewareBefore(BaseStep):
    """Execute middleware before-chain."""

    def __init__(
        self,
        *,
        middlewares: list[Any] | None = None,
        middleware_manager: Any | None = None,
    ) -> None:
        super().__init__(
            name="middleware_before",
            description="Run before-middleware chain",
            removable=True,
            replaceable=False,
            pure=False,
        )
        self._middlewares = middlewares or []
        self._middleware_manager = middleware_manager

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if self._middleware_manager is not None:
            from apcore.middleware.manager import MiddlewareChainError

            try:
                if hasattr(self._middleware_manager, "execute_before_async"):
                    inputs, executed = await self._middleware_manager.execute_before_async(
                        ctx.module_id, ctx.inputs, ctx.context,
                    )
                else:
                    inputs, executed = self._middleware_manager.execute_before(
                        ctx.module_id, ctx.inputs, ctx.context,
                    )
                ctx.inputs = inputs
                ctx.executed_middlewares = list(executed)
            except MiddlewareChainError as exc:
                # Store executed middlewares for the executor's on_error recovery
                ctx.executed_middlewares = list(exc.executed_middlewares)
                raise
            except Exception as exc:
                # on_error recovery for non-chain errors
                if hasattr(self._middleware_manager, "execute_on_error_async"):
                    recovery = await self._middleware_manager.execute_on_error_async(
                        ctx.module_id, ctx.inputs, exc, ctx.context, ctx.executed_middlewares,
                    )
                elif hasattr(self._middleware_manager, "execute_on_error"):
                    recovery = self._middleware_manager.execute_on_error(
                        ctx.module_id, ctx.inputs, exc, ctx.context, ctx.executed_middlewares,
                    )
                else:
                    recovery = None
                # Clear executed_middlewares after on_error to prevent double invocation
                ctx.executed_middlewares = []
                if recovery is not None:
                    ctx.output = recovery
                    return StepResult(action="skip_to", skip_to="return_result")
                raise
            return StepResult(action="continue")

        executed: list[Any] = []
        for mw in self._middlewares:
            try:
                if hasattr(mw, "before"):
                    result = mw.before(ctx.module_id, ctx.inputs, ctx.context)
                    if result is not None:
                        ctx.inputs = result if isinstance(result, dict) else ctx.inputs
                    executed.append(mw)
            except Exception as exc:
                ctx.executed_middlewares = executed
                for recovery_mw in reversed(executed):
                    if hasattr(recovery_mw, "on_error"):
                        try:
                            recovery = recovery_mw.on_error(ctx.module_id, ctx.inputs, exc, ctx.context)
                            if recovery is not None:
                                ctx.output = recovery
                                return StepResult(action="skip_to", skip_to="return_result")
                        except Exception:
                            pass
                ctx.executed_middlewares = []  # Clear to prevent double on_error in executor
                raise
        ctx.executed_middlewares = executed
        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 7: Input Validation
# ---------------------------------------------------------------------------


class BuiltinInputValidation(BaseStep):
    """Validate inputs against module schema and redact sensitive fields."""

    def __init__(self) -> None:
        super().__init__(
            name="input_validation",
            description="Validate inputs against schema and redact sensitive fields",
            removable=True,
            replaceable=True,
            pure=True,
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
            raise SchemaValidationError(
                message=f"Input validation failed: {errors}",
                errors=errors,
            ) from exc

        ctx.validated_inputs = ctx.inputs

        # Redact sensitive fields after successful validation
        schema_dict_fn = getattr(input_schema, "model_json_schema", None)
        if schema_dict_fn is not None and callable(schema_dict_fn):
            from apcore.executor import redact_sensitive

            schema = schema_dict_fn()
            redacted = redact_sensitive(ctx.inputs, schema)
            if ctx.context is not None and hasattr(ctx.context, "redacted_inputs"):
                ctx.context.redacted_inputs = redacted

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
            pure=False,
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

        # Check cancel token
        cancel_token = getattr(ctx.context, "cancel_token", None)
        if cancel_token is not None and cancel_token.is_cancelled:
            raise ExecutionCancelledError()

        # Check global deadline
        global_deadline = getattr(ctx.context, "_global_deadline", None)
        if global_deadline is not None and time.monotonic() > global_deadline:
            timeout_ms = int(self._default_timeout)
            raise ModuleTimeoutError(module_id=ctx.module_id, timeout_ms=timeout_ms)

        inputs = ctx.validated_inputs if ctx.validated_inputs is not None else ctx.inputs

        # Stream mode: set up output_stream if module has stream()
        if ctx.stream and hasattr(module, "stream") and callable(module.stream):
            ctx.output_stream = module.stream(inputs, ctx.context)
            return StepResult(action="skip_to", skip_to="return_result")

        # Determine per-module timeout
        module_timeout_ms = getattr(module, "timeout_ms", None)
        if module_timeout_ms is not None:
            if module_timeout_ms < 0:
                raise InvalidInputError(
                    message=f"Negative timeout: {module_timeout_ms}",
                )
            timeout_s = module_timeout_ms / 1000.0
        elif self._default_timeout > 0:
            timeout_s = self._default_timeout / 1000.0
        else:
            timeout_s = None

        # Clamp to global deadline if set
        if global_deadline is not None:
            remaining = global_deadline - time.monotonic()
            if remaining <= 0:
                raise ModuleTimeoutError(module_id=ctx.module_id, timeout_ms=int(self._default_timeout))
            if timeout_s is None or remaining < timeout_s:
                timeout_s = remaining

        # Stream mode: set output_stream and skip to return_result (no execution)
        if getattr(ctx, "stream", False) and hasattr(module, "stream") and module.stream is not None:
            ctx.output_stream = module.stream(inputs, ctx.context)
            return StepResult(action="skip_to", skip_to="return_result")

        try:
            if inspect.iscoroutinefunction(module.execute):
                coro = module.execute(inputs, ctx.context)
            else:
                loop = asyncio.get_event_loop()
                coro = loop.run_in_executor(None, module.execute, inputs, ctx.context)

            if timeout_s is not None:
                output = await asyncio.wait_for(coro, timeout=timeout_s)
            else:
                output = await coro
            ctx.output = output
        except asyncio.TimeoutError:
            timeout_ms = int((timeout_s or 0) * 1000)
            raise ModuleTimeoutError(
                module_id=ctx.module_id, timeout_ms=timeout_ms,
            ) from None
        except (ExecutionCancelledError, ModuleTimeoutError, InvalidInputError):
            raise
        except Exception:
            raise

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
            pure=True,
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
            raise SchemaValidationError(
                message=f"Output validation failed: {errors}",
                errors=errors,
            ) from exc

        ctx.validated_output = ctx.output

        # Store redacted output in context
        if ctx.context is not None and hasattr(ctx.context, "data"):
            schema_dict_fn = getattr(output_schema, "model_json_schema", None)
            if schema_dict_fn is not None and callable(schema_dict_fn):
                from apcore.executor import redact_sensitive

                schema = schema_dict_fn()
                redacted = redact_sensitive(ctx.output, schema)
                ctx.context.data[REDACTED_OUTPUT.name] = redacted

        return StepResult(action="continue")


# ---------------------------------------------------------------------------
# Step 10: Middleware After
# ---------------------------------------------------------------------------


class BuiltinMiddlewareAfter(BaseStep):
    """Execute middleware after-chain."""

    def __init__(
        self,
        *,
        middlewares: list[Any] | None = None,
        middleware_manager: Any | None = None,
    ) -> None:
        super().__init__(
            name="middleware_after",
            description="Run after-middleware chain",
            removable=True,
            replaceable=False,
            pure=False,
        )
        self._middlewares = middlewares or []
        self._middleware_manager = middleware_manager

    async def execute(self, ctx: PipelineContext) -> StepResult:
        if self._middleware_manager is not None:
            if hasattr(self._middleware_manager, "execute_after_async"):
                output = await self._middleware_manager.execute_after_async(
                    ctx.module_id, ctx.inputs, ctx.output or {}, ctx.context,
                )
            else:
                output = self._middleware_manager.execute_after(
                    ctx.module_id, ctx.inputs, ctx.output or {}, ctx.context,
                )
            ctx.output = output
            return StepResult(action="continue")

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
            pure=True,
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
    middleware_manager: Any | None = None,
    executor: Any | None = None,
) -> ExecutionStrategy:
    """Build the standard 11-step execution strategy.

    Args:
        registry: Module registry for looking up modules by ID.
        config: Optional configuration for timeout/depth settings.
        acl: Optional ACL for access control enforcement.
        approval_handler: Optional approval handler for the approval gate.
        middlewares: Optional list of middleware instances.
        middleware_manager: Optional MiddlewareManager for production parity.
        executor: Optional executor reference for context creation and approval.

    Returns:
        An ExecutionStrategy containing the 11 built-in steps.
    """
    return ExecutionStrategy(
        "standard",
        [
            BuiltinContextCreation(config=config, executor=executor),
            BuiltinCallChainGuard(config=config),
            BuiltinModuleLookup(registry=registry),
            BuiltinACLCheck(acl=acl),
            BuiltinApprovalGate(handler=approval_handler, executor=executor),
            BuiltinMiddlewareBefore(
                middlewares=middlewares or [],
                middleware_manager=middleware_manager,
            ),
            BuiltinInputValidation(),
            BuiltinExecute(config=config),
            BuiltinOutputValidation(),
            BuiltinMiddlewareAfter(
                middlewares=middlewares or [],
                middleware_manager=middleware_manager,
            ),
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
    """Build a testing strategy: standard minus acl, approval, and call chain guard.

    Suitable for unit/integration tests that need minimal overhead.

    Args:
        **kwargs: Forwarded to build_standard_strategy().

    Returns:
        An ExecutionStrategy named "testing".
    """
    s = build_standard_strategy(**kwargs)
    s.remove("acl_check")
    s.remove("approval_gate")
    s.remove("call_chain_guard")
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
