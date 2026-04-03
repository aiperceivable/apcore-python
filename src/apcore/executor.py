"""Executor — the module execution engine for apcore.

Resolves a module by ID, validates inputs against its schema, enforces ACL
and approval policies, runs the middleware chain, and returns the result.
Supports sync, async, and streaming execution modes.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import inspect
import logging
import threading
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

import pydantic

from apcore.acl import ACL
from apcore.context_keys import REDACTED_OUTPUT
from apcore.approval import ApprovalHandler, ApprovalRequest, ApprovalResult
from apcore.cancel import ExecutionCancelledError
from apcore.config import Config
from apcore.context import Context
from apcore.errors import (
    ACLDeniedError,
    ApprovalDeniedError,
    ApprovalPendingError,
    ApprovalTimeoutError,
    InvalidInputError,
    ModuleError,
    ModuleNotFoundError,
    ModuleTimeoutError,
    SchemaValidationError,
)
from apcore.utils.error_propagation import propagate_error
from apcore.middleware import AfterMiddleware, BeforeMiddleware, Middleware
from apcore.middleware.manager import MiddlewareChainError, MiddlewareManager
from apcore.module import ModuleAnnotations, PreflightCheckResult, PreflightResult
from apcore.pipeline import (
    ExecutionStrategy,
    PipelineContext,
    PipelineEngine,
    PipelineTrace,
    StrategyInfo,
    StrategyNotFoundError,
)
from apcore.registry import MODULE_ID_PATTERN, Registry
from apcore.utils.call_chain import guard_call_chain

__all__ = ["redact_sensitive", "REDACTED_VALUE", "Executor"]

REDACTED_VALUE: str = "***REDACTED***"

_logger = logging.getLogger(__name__)


_MAX_MERGE_DEPTH = 32


def _deep_merge(base: dict[str, Any], override: dict[str, Any], *, _depth: int = 0) -> None:
    """Recursively merge *override* into *base* in-place.

    Nested dicts are merged recursively; all other values (including lists)
    are replaced by the override value. Recursion is capped at
    ``_MAX_MERGE_DEPTH`` to guard against malicious or extremely nested
    streaming chunks.
    """
    if _depth >= _MAX_MERGE_DEPTH:
        return
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value, _depth=_depth + 1)
        else:
            base[key] = value


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


# =============================================================================
# Redaction utilities (from section-05)
# =============================================================================


def redact_sensitive(data: dict[str, Any], schema_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact fields marked with x-sensitive in the schema.

    Implements Algorithm A13 from PROTOCOL_SPEC section 9.5.
    Returns a deep copy of data with sensitive values replaced by "***REDACTED***".
    Also redacts any keys starting with "_secret_" regardless of schema.

    Args:
        data: The data dict to redact.
        schema_dict: A JSON Schema dict that may contain "x-sensitive": true
            on individual properties.

    Returns:
        A new dict with sensitive values replaced. Original data is not modified.
    """
    redacted = copy.deepcopy(data)
    _redact_fields(redacted, schema_dict)
    _redact_secret_prefix(redacted)
    return redacted


def _redact_fields(data: dict[str, Any], schema_dict: dict[str, Any]) -> None:
    """In-place redaction based on schema x-sensitive markers."""
    properties = schema_dict.get("properties")
    if not properties:
        return

    for field_name, field_schema in properties.items():
        if field_name not in data:
            continue

        value = data[field_name]

        # x-sensitive: true on this property
        if field_schema.get("x-sensitive") is True:
            if value is not None:
                data[field_name] = REDACTED_VALUE
            continue

        # Nested object: recurse
        if field_schema.get("type") == "object" and "properties" in field_schema and isinstance(value, dict):
            _redact_fields(value, field_schema)
            continue

        # Array: redact items
        if field_schema.get("type") == "array" and "items" in field_schema and isinstance(value, list):
            items_schema = field_schema["items"]
            if items_schema.get("x-sensitive") is True:
                for i, item in enumerate(value):
                    if item is not None:
                        value[i] = REDACTED_VALUE
            elif items_schema.get("type") == "object" and "properties" in items_schema:
                for item in value:
                    if isinstance(item, dict):
                        _redact_fields(item, items_schema)


def _redact_secret_prefix(data: dict[str, Any]) -> None:
    """In-place redaction of keys starting with _secret_."""
    for key in data:
        value = data[key]
        if key.startswith("_secret_") and value is not None:
            data[key] = REDACTED_VALUE
        elif isinstance(value, dict):
            _redact_secret_prefix(value)


# =============================================================================
# Executor class (section-06)
# =============================================================================


class Executor:
    """Central execution engine that orchestrates the module call pipeline.

    The Executor implements a robust execution flow: context creation, safety checks,
    module lookup, ACL enforcement, approval gate, input validation with
    redaction, middleware before chain, module execution, output validation,
    middleware after chain, and result return.
    """

    _registered_strategies: dict[str, ExecutionStrategy] = {}

    def __init__(
        self,
        registry: Registry,
        *,
        strategy: ExecutionStrategy | str | None = None,
        middlewares: list[Middleware] | None = None,
        acl: ACL | None = None,
        config: Config | None = None,
        approval_handler: ApprovalHandler | None = None,
    ) -> None:
        """Initialize the Executor.

        Args:
            registry: Module registry for looking up modules by ID.
            strategy: Optional execution strategy. Can be an ExecutionStrategy
                instance, a preset name string ("standard", "internal",
                "testing", "performance"), or None (defaults to standard).
            middlewares: Optional list of middleware instances to register.
            acl: Optional ACL for access control enforcement.
            config: Optional configuration for timeout/depth settings.
            approval_handler: Optional approval handler for Step 5 gate.
        """
        self._registry = registry
        self._middleware_manager = MiddlewareManager()
        self._acl = acl
        self._config = config
        self._approval_handler = approval_handler

        # Resolve strategy
        strategy_kwargs = dict(
            registry=registry,
            config=config,
            acl=acl,
            approval_handler=approval_handler,
            middlewares=middlewares,
        )
        if strategy is None:
            from apcore.builtin_steps import build_standard_strategy

            self._strategy = build_standard_strategy(**strategy_kwargs)
        elif isinstance(strategy, str):
            self._strategy = self._resolve_strategy_name(strategy, **strategy_kwargs)
        else:
            self._strategy = strategy

        if middlewares:
            for mw in middlewares:
                self._middleware_manager.add(mw)

        if config is not None:
            val = config.get("executor.default_timeout")
            self._default_timeout: int = val if val is not None else 30000
            val = config.get("executor.global_timeout")
            self._global_timeout: int = val if val is not None else 60000
            val = config.get("executor.max_call_depth")
            self._max_call_depth: int = val if val is not None else 32
            val = config.get("executor.max_module_repeat")
            self._max_module_repeat: int = val if val is not None else 3
        else:
            self._default_timeout = 30000
            self._global_timeout = 60000
            self._max_call_depth = 32
            self._max_module_repeat = 3

        self._async_cache: dict[str, bool] = {}
        self._async_cache_lock = threading.Lock()

    @classmethod
    def from_registry(
        cls,
        registry: Registry,
        *,
        strategy: ExecutionStrategy | str | None = None,
        middlewares: list[Middleware] | None = None,
        acl: ACL | None = None,
        config: Config | None = None,
        approval_handler: ApprovalHandler | None = None,
    ) -> Executor:
        """Convenience factory for creating an Executor from a Registry.

        Args:
            registry: The module registry.
            strategy: Optional execution strategy or preset name.
            middlewares: Optional middleware list.
            acl: Optional access control list.
            config: Optional configuration.
            approval_handler: Optional approval handler.

        Returns:
            A configured Executor instance.
        """
        return cls(
            registry=registry,
            strategy=strategy,
            middlewares=middlewares,
            acl=acl,
            config=config,
            approval_handler=approval_handler,
        )

    @property
    def registry(self) -> Registry:
        """Return the Registry instance."""
        return self._registry

    @property
    def middlewares(self) -> list[Middleware]:
        """Return a copy of the current middleware list."""
        return self._middleware_manager.snapshot()

    def set_acl(self, acl: ACL) -> None:
        """Set the access control provider.

        Args:
            acl: The ACL instance to use for access control enforcement.
        """
        self._acl = acl

    def set_approval_handler(self, handler: ApprovalHandler) -> None:
        """Set the approval handler for Step 5 gate.

        Args:
            handler: The ApprovalHandler instance to use for approval enforcement.
        """
        self._approval_handler = handler

    def use(self, middleware: Middleware) -> Executor:
        """Add class-based middleware and return self for chaining."""
        self._middleware_manager.add(middleware)
        return self

    def use_before(self, callback: Callable[..., Any]) -> Executor:
        """Wrap callback in BeforeMiddleware adapter and add it."""
        self._middleware_manager.add(BeforeMiddleware(callback))
        return self

    def use_after(self, callback: Callable[..., Any]) -> Executor:
        """Wrap callback in AfterMiddleware adapter and add it."""
        self._middleware_manager.add(AfterMiddleware(callback))
        return self

    def remove(self, middleware: Middleware) -> bool:
        """Remove middleware by identity. Returns True if found and removed."""
        return self._middleware_manager.remove(middleware)

    def call(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> dict[str, Any]:
        """Execute a module through the execution pipeline.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Returns:
            The module output dict, possibly modified by middleware.
        """
        self._validate_module_id(module_id)

        if inputs is None:
            inputs = {}

        # Step 1 -- Context
        if context is None:
            ctx = Context.create(executor=self)
            ctx = ctx.child(module_id)
            if self._global_timeout > 0:
                ctx._global_deadline = time.monotonic() + self._global_timeout / 1000.0
        else:
            ctx = context.child(module_id)

        # Step 2 -- Safety Checks
        self._check_safety(module_id, ctx)

        # Step 3 -- Lookup (with version negotiation)
        module = self._registry.get(module_id, version_hint=version_hint)
        if module is None:
            raise ModuleNotFoundError(module_id=module_id)

        # Step 4 -- ACL
        if self._acl is not None:
            allowed = self._acl.check(ctx.caller_id, module_id, ctx)
            if not allowed:
                raise ACLDeniedError(caller_id=ctx.caller_id, target_id=module_id)

        # Step 5 -- Approval Gate
        self._check_approval_sync(module, module_id, inputs, ctx)

        # Step 6 -- Input Validation and Redaction
        if hasattr(module, "input_schema") and module.input_schema is not None:
            try:
                module.input_schema.model_validate(inputs)
            except pydantic.ValidationError as e:
                raise SchemaValidationError(
                    message="Input validation failed",
                    errors=_convert_validation_errors(e),
                ) from e

            ctx.redacted_inputs = redact_sensitive(inputs, module.input_schema.model_json_schema())

        executed_middlewares: list[Middleware] = []

        try:
            # Step 7 -- Middleware Before
            try:
                inputs, executed_middlewares = self._middleware_manager.execute_before(module_id, inputs, ctx)
            except MiddlewareChainError as mce:
                executed_middlewares = mce.executed_middlewares
                recovery = self._middleware_manager.execute_on_error(
                    module_id, inputs, mce.original, ctx, executed_middlewares
                )
                if recovery is not None:
                    return recovery
                executed_middlewares = []  # Prevent double on_error in outer except
                raise mce.original from mce

            # Cancel check before execution
            if ctx.cancel_token is not None:
                ctx.cancel_token.check()

            # Step 8 -- Execute with timeout
            output = self._execute_with_timeout(module, module_id, inputs, ctx)

            # Step 9 -- Output Validation and Redaction
            if hasattr(module, "output_schema") and module.output_schema is not None:
                try:
                    module.output_schema.model_validate(output)
                except pydantic.ValidationError as e:
                    raise SchemaValidationError(
                        message="Output validation failed",
                        errors=_convert_validation_errors(e),
                    ) from e

                REDACTED_OUTPUT.set(ctx, redact_sensitive(output, module.output_schema.model_json_schema()))

            # Step 10 -- Middleware After
            output = self._middleware_manager.execute_after(module_id, inputs, output, ctx)

        except ExecutionCancelledError:
            raise
        except Exception as exc:
            # Error handling (A11): wrap and propagate
            wrapped = propagate_error(exc, module_id, ctx)
            if executed_middlewares:
                recovery = self._middleware_manager.execute_on_error(
                    module_id, inputs, wrapped, ctx, executed_middlewares
                )
                if recovery is not None:
                    return recovery
            raise wrapped from exc

        # Step 11 -- Return
        return output

    def validate(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> PreflightResult:
        """Non-destructive preflight check through Steps 1-6 without execution.

        Runs context creation, safety checks, module lookup, ACL enforcement,
        approval detection (report only), and input schema validation.
        All check failures are collected rather than thrown.

        Args:
            module_id: The module to validate against.
            inputs: Input data to validate. None is treated as {}.
            context: Optional context for call-chain checks.

        Returns:
            PreflightResult with per-check status. Duck-type compatible
            with the old ValidationResult (.valid and .errors).
        """
        if inputs is None:
            inputs = {}

        checks: list[PreflightCheckResult] = []
        requires_approval = False

        # Check 1: module_id format
        try:
            self._validate_module_id(module_id)
            checks.append(PreflightCheckResult(check="module_id", passed=True))
        except InvalidInputError as e:
            checks.append(PreflightCheckResult(check="module_id", passed=False, error=e.to_dict()))
            return PreflightResult(valid=False, checks=checks)

        # Check 2: module lookup
        module = self._registry.get(module_id)
        if module is None:
            checks.append(
                PreflightCheckResult(
                    check="module_lookup",
                    passed=False,
                    error={"code": "MODULE_NOT_FOUND", "message": f"Module not found: {module_id}"},
                )
            )
            return PreflightResult(valid=False, checks=checks)
        checks.append(PreflightCheckResult(check="module_lookup", passed=True))

        # Check 3: call chain safety
        if context is not None:
            ctx = context.child(module_id)
        else:
            ctx = Context.create(executor=self).child(module_id)
        try:
            self._check_safety(module_id, ctx)
            checks.append(PreflightCheckResult(check="call_chain", passed=True))
        except ModuleError as e:
            checks.append(PreflightCheckResult(check="call_chain", passed=False, error=e.to_dict()))

        # Check 4: ACL
        if self._acl is not None:
            allowed = self._acl.check(ctx.caller_id, module_id, ctx)
            if not allowed:
                checks.append(
                    PreflightCheckResult(
                        check="acl",
                        passed=False,
                        error={"code": "ACL_DENIED", "message": f"Access denied: {ctx.caller_id} -> {module_id}"},
                    )
                )
            else:
                checks.append(PreflightCheckResult(check="acl", passed=True))
        else:
            checks.append(PreflightCheckResult(check="acl", passed=True))

        # Check 5: approval detection (report only, no handler invocation)
        if self._needs_approval(module):
            requires_approval = True
        checks.append(PreflightCheckResult(check="approval", passed=True))

        # Check 6: input schema validation
        if hasattr(module, "input_schema") and module.input_schema is not None:
            try:
                module.input_schema.model_validate(inputs)
                checks.append(PreflightCheckResult(check="schema", passed=True))
            except pydantic.ValidationError as e:
                checks.append(
                    PreflightCheckResult(
                        check="schema",
                        passed=False,
                        error={"code": "SCHEMA_VALIDATION_ERROR", "errors": _convert_validation_errors(e)},
                    )
                )
        else:
            checks.append(PreflightCheckResult(check="schema", passed=True))

        # Check 7: module-level preflight (optional)
        if hasattr(module, "preflight") and callable(module.preflight):
            try:
                preflight_warnings = module.preflight(inputs, ctx)
                if isinstance(preflight_warnings, list) and preflight_warnings:
                    checks.append(
                        PreflightCheckResult(
                            check="module_preflight",
                            passed=True,
                            warnings=preflight_warnings,
                        )
                    )
                else:
                    checks.append(PreflightCheckResult(check="module_preflight", passed=True))
            except Exception as exc:
                # preflight() should not raise, but handle gracefully if it does
                checks.append(
                    PreflightCheckResult(
                        check="module_preflight",
                        passed=True,
                        warnings=[f"preflight() raised {type(exc).__name__}: {exc}"],
                    )
                )

        valid = all(c.passed for c in checks)
        return PreflightResult(valid=valid, checks=checks, requires_approval=requires_approval)

    def _needs_approval(self, module: Any) -> bool:
        """Check if a module requires approval, handling both dict and dataclass annotations."""
        annotations = getattr(module, "annotations", None)
        if annotations is None:
            return False
        if isinstance(annotations, ModuleAnnotations):
            return annotations.requires_approval
        if isinstance(annotations, dict):
            return bool(annotations.get("requires_approval", False))
        return False

    def _build_approval_request(
        self, module: Any, module_id: str, inputs: dict[str, Any], ctx: Context
    ) -> ApprovalRequest:
        """Build an ApprovalRequest from module metadata."""
        annotations = getattr(module, "annotations", None)
        if isinstance(annotations, ModuleAnnotations):
            ann = annotations
        elif isinstance(annotations, dict):
            valid_fields = {f.name for f in dataclasses.fields(ModuleAnnotations)}
            ann = ModuleAnnotations(**{k: v for k, v in annotations.items() if k in valid_fields})
        else:
            ann = ModuleAnnotations()

        return ApprovalRequest(
            module_id=module_id,
            arguments=inputs,
            context=ctx,
            annotations=ann,
            description=getattr(module, "description", None),
            tags=getattr(module, "tags", None) or [],
        )

    def _handle_approval_result(self, result: ApprovalResult, module_id: str) -> None:
        """Map an ApprovalResult status to the appropriate action or error."""
        if result.status == "approved":
            return
        if result.status == "rejected":
            raise ApprovalDeniedError(result=result, module_id=module_id)
        if result.status == "timeout":
            raise ApprovalTimeoutError(result=result, module_id=module_id)
        if result.status == "pending":
            raise ApprovalPendingError(result=result, module_id=module_id)
        _logger.warning("Unknown approval status '%s' for module %s, treating as denied", result.status, module_id)
        raise ApprovalDeniedError(result=result, module_id=module_id)

    def _emit_approval_event(self, result: ApprovalResult, module_id: str, ctx: Context) -> None:
        """Emit an audit event for the approval decision (logging + span event)."""
        _logger.info(
            "Approval decision: module=%s status=%s approved_by=%s reason=%s",
            module_id,
            result.status,
            result.approved_by,
            result.reason,
        )
        spans_stack: list[Any] = ctx.data.get("_apcore.mw.tracing.spans", [])
        if spans_stack:
            spans_stack[-1].events.append(
                {
                    "name": "approval_decision",
                    "module_id": module_id,
                    "status": result.status,
                    "approved_by": result.approved_by or "",
                    "reason": result.reason or "",
                    "approval_id": result.approval_id or "",
                }
            )

    def _check_approval_sync(self, module: Any, module_id: str, inputs: dict[str, Any], ctx: Context) -> None:
        """Step 5: Approval gate (sync path). Bridges to async handler."""
        if self._approval_handler is None:
            return
        if not self._needs_approval(module):
            return

        # Phase B resume: pop _approval_token and check
        if "_approval_token" in inputs:
            token = inputs.pop("_approval_token")
            coro = self._approval_handler.check_approval(token)
        else:
            request = self._build_approval_request(module, module_id, inputs, ctx)
            coro = self._approval_handler.request_approval(request)

        result = self._run_async_in_sync(coro, module_id, 0)
        self._emit_approval_event(result, module_id, ctx)
        self._handle_approval_result(result, module_id)

    async def _check_approval_async(self, module: Any, module_id: str, inputs: dict[str, Any], ctx: Context) -> None:
        """Step 5: Approval gate (async path)."""
        if self._approval_handler is None:
            return
        if not self._needs_approval(module):
            return

        # Phase B resume: pop _approval_token and check
        if "_approval_token" in inputs:
            token = inputs.pop("_approval_token")
            result = await self._approval_handler.check_approval(token)
        else:
            request = self._build_approval_request(module, module_id, inputs, ctx)
            result = await self._approval_handler.request_approval(request)

        self._emit_approval_event(result, module_id, ctx)
        self._handle_approval_result(result, module_id)

    @staticmethod
    def _validate_module_id(module_id: str) -> None:
        """Validate module_id format at public entry points."""
        if not module_id or not MODULE_ID_PATTERN.match(module_id):
            raise InvalidInputError(
                message=f"Invalid module ID: '{module_id}'. Must match pattern: {MODULE_ID_PATTERN.pattern}"
            )

    def _check_safety(self, module_id: str, ctx: Context) -> None:
        """Run call chain safety checks (step 2).

        Delegates to the standalone ``guard_call_chain`` algorithm (A20).
        """
        guard_call_chain(
            module_id,
            ctx.call_chain,
            max_call_depth=self._max_call_depth,
            max_module_repeat=self._max_module_repeat,
        )

    def _is_async_module(self, module_id: str, module: Any) -> bool:
        """Check if a module's execute method is async, with caching."""
        with self._async_cache_lock:
            if module_id in self._async_cache:
                return self._async_cache[module_id]
            is_async = inspect.iscoroutinefunction(module.execute)
            self._async_cache[module_id] = is_async
            return is_async

    #: Grace period (ms) for cooperative cancellation before giving up.
    _GRACE_PERIOD_MS: int = 5000

    def _execute_with_timeout(
        self, module: Any, module_id: str, inputs: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        """Execute module with timeout enforcement (Algorithm A22, sync path).

        Steps:
        1. If timeout_ms == 0 → execute without timeout.
        2. Run module in thread with timeout.
        3. On timeout → send cooperative cancel via CancelToken.
        4. Wait grace period (5s) for module to respond to cancel.
        5. If still alive → log warning (Python cannot force-kill threads).
        6. Raise ModuleTimeoutError.
        """
        timeout_ms = self._default_timeout

        if timeout_ms < 0:
            raise InvalidInputError(message=f"Negative timeout: {timeout_ms}ms")

        # Global deadline enforcement (dual-timeout model)
        if ctx._global_deadline is not None:
            remaining_ms = max(0, (ctx._global_deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                raise ModuleTimeoutError(module_id=module_id, timeout_ms=self._global_timeout)
            if timeout_ms == 0 or remaining_ms < timeout_ms:
                timeout_ms = int(remaining_ms)

        # Async module in sync context: bridge to async
        if self._is_async_module(module_id, module):
            return self._run_async_in_sync(module.execute(inputs, ctx), module_id, timeout_ms)

        if timeout_ms == 0:
            _logger.warning("Timeout disabled for module %s", module_id)
            return module.execute(inputs, ctx)

        result_holder: dict[str, Any] = {}
        exception_holder: dict[str, Exception] = {}

        def run_module() -> None:
            try:
                result_holder["output"] = module.execute(inputs, ctx)
            except Exception as e:
                exception_holder["error"] = e

        thread = threading.Thread(target=run_module, daemon=True)
        thread.start()
        thread.join(timeout=timeout_ms / 1000.0)

        if thread.is_alive():
            # Step 3: Cooperative cancellation via CancelToken
            cancel_token = getattr(ctx, "cancel_token", None)
            if cancel_token is not None:
                cancel_token.cancel()
                # Step 4: Wait grace period
                thread.join(timeout=self._GRACE_PERIOD_MS / 1000.0)
                if not thread.is_alive():
                    # Module responded to cancellation
                    if "error" in exception_holder:
                        raise exception_holder["error"]
                    if "output" in result_holder:
                        return result_holder["output"]

            # Step 5: Thread still alive — cannot force-kill in Python
            if thread.is_alive():
                _logger.warning(
                    "Module '%s' timeout after %dms + %dms grace period; " "thread cannot be force-killed in Python",
                    module_id,
                    timeout_ms,
                    self._GRACE_PERIOD_MS,
                )
            raise ModuleTimeoutError(module_id=module_id, timeout_ms=timeout_ms)

        if "error" in exception_holder:
            raise exception_holder["error"]

        return result_holder["output"]

    def _run_async_in_sync(self, coro: Any, module_id: str, timeout_ms: int) -> Any:
        """Run an async coroutine from a sync context."""
        timeout_s = timeout_ms / 1000.0 if timeout_ms > 0 else None

        try:
            asyncio.get_running_loop()
            has_loop = True
        except RuntimeError:
            has_loop = False

        if not has_loop:
            if timeout_s is not None:
                wrapped = asyncio.wait_for(coro, timeout=timeout_s)
            else:
                wrapped = coro
            try:
                return asyncio.run(wrapped)
            except asyncio.TimeoutError:
                raise ModuleTimeoutError(module_id=module_id, timeout_ms=timeout_ms)
        else:
            return self._run_in_new_thread(coro, module_id, timeout_s)

    def _run_in_new_thread(self, coro: Any, module_id: str, timeout_s: float | None) -> Any:
        """Run coroutine in a new thread with its own event loop."""
        result_holder: dict[str, Any] = {}
        exception_holder: dict[str, Exception] = {}

        def thread_target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if timeout_s is not None:
                    result_holder["output"] = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout_s))
                else:
                    result_holder["output"] = loop.run_until_complete(coro)
            except asyncio.TimeoutError:
                exception_holder["error"] = ModuleTimeoutError(
                    module_id=module_id, timeout_ms=int((timeout_s or 0) * 1000)
                )
            except Exception as e:
                exception_holder["error"] = e
            finally:
                loop.close()

        thread = threading.Thread(target=thread_target, daemon=True)
        thread.start()
        thread.join()

        if "error" in exception_holder:
            raise exception_holder["error"]
        return result_holder["output"]

    async def call_async(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> dict[str, Any]:
        """Async counterpart to call(). Supports async modules natively.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Returns:
            The module output dict, possibly modified by middleware.
        """
        self._validate_module_id(module_id)

        if inputs is None:
            inputs = {}

        # Step 1 -- Context
        if context is None:
            ctx = Context.create(executor=self)
            ctx = ctx.child(module_id)
            if self._global_timeout > 0:
                ctx._global_deadline = time.monotonic() + self._global_timeout / 1000.0
        else:
            ctx = context.child(module_id)

        # Step 2 -- Safety Checks
        self._check_safety(module_id, ctx)

        # Step 3 -- Lookup
        module = self._registry.get(module_id, version_hint=version_hint)
        if module is None:
            raise ModuleNotFoundError(module_id=module_id)

        # Step 4 -- ACL
        if self._acl is not None:
            allowed = self._acl.check(ctx.caller_id, module_id, ctx)
            if not allowed:
                raise ACLDeniedError(caller_id=ctx.caller_id, target_id=module_id)

        # Step 5 -- Approval Gate
        await self._check_approval_async(module, module_id, inputs, ctx)

        # Step 6 -- Input Validation and Redaction
        if hasattr(module, "input_schema") and module.input_schema is not None:
            try:
                module.input_schema.model_validate(inputs)
            except pydantic.ValidationError as e:
                raise SchemaValidationError(
                    message="Input validation failed",
                    errors=_convert_validation_errors(e),
                ) from e
            ctx.redacted_inputs = redact_sensitive(inputs, module.input_schema.model_json_schema())

        executed_middlewares: list[Middleware] = []

        try:
            # Step 7 -- Middleware Before (async-aware)
            try:
                inputs, executed_middlewares = await self._middleware_manager.execute_before_async(
                    module_id, inputs, ctx
                )
            except MiddlewareChainError as mce:
                executed_middlewares = mce.executed_middlewares
                recovery = await self._middleware_manager.execute_on_error_async(
                    module_id, inputs, mce.original, ctx, executed_middlewares
                )
                if recovery is not None:
                    return recovery
                executed_middlewares = []
                raise mce.original from mce

            # Cancel check before execution
            if ctx.cancel_token is not None:
                ctx.cancel_token.check()

            # Step 8 -- Execute (async)
            output = await self._execute_async(module, module_id, inputs, ctx)

            # Step 9 -- Output Validation and Redaction
            if hasattr(module, "output_schema") and module.output_schema is not None:
                try:
                    module.output_schema.model_validate(output)
                except pydantic.ValidationError as e:
                    raise SchemaValidationError(
                        message="Output validation failed",
                        errors=_convert_validation_errors(e),
                    ) from e

                REDACTED_OUTPUT.set(ctx, redact_sensitive(output, module.output_schema.model_json_schema()))

            # Step 10 -- Middleware After (async-aware)
            output = await self._middleware_manager.execute_after_async(module_id, inputs, output, ctx)

        except ExecutionCancelledError:
            raise
        except Exception as exc:
            # Error handling (A11): wrap and propagate
            wrapped = propagate_error(exc, module_id, ctx)
            if executed_middlewares:
                recovery = await self._middleware_manager.execute_on_error_async(
                    module_id, inputs, wrapped, ctx, executed_middlewares
                )
                if recovery is not None:
                    return recovery
            raise wrapped from exc

        # Step 11 -- Return
        return output

    async def stream(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async generator that streams module output chunks.

        Steps 1-6 are identical to call_async(). If the module has no stream()
        method, falls back to call_async() and yields a single chunk. If the
        module has stream(), iterates it, yields each chunk, and accumulates
        results via shallow merge. After all chunks, validates accumulated
        output and runs after-middleware.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Yields:
            Dict chunks from the module's stream() or a single call_async() result.
        """
        self._validate_module_id(module_id)

        effective_inputs: dict[str, Any] = dict(inputs) if inputs is not None else {}

        # Step 1 -- Context
        if context is None:
            ctx = Context.create(executor=self)
            ctx = ctx.child(module_id)
            if self._global_timeout > 0:
                ctx._global_deadline = time.monotonic() + self._global_timeout / 1000.0
        else:
            ctx = context.child(module_id)

        # Step 2 -- Safety Checks
        self._check_safety(module_id, ctx)

        # Step 3 -- Lookup
        module = self._registry.get(module_id, version_hint=version_hint)
        if module is None:
            raise ModuleNotFoundError(module_id=module_id)

        # Step 4 -- ACL
        if self._acl is not None:
            allowed = self._acl.check(ctx.caller_id, module_id, ctx)
            if not allowed:
                raise ACLDeniedError(caller_id=ctx.caller_id, target_id=module_id)

        # Step 5 -- Approval Gate
        await self._check_approval_async(module, module_id, effective_inputs, ctx)

        # Step 6 -- Input Validation and Redaction
        if hasattr(module, "input_schema") and module.input_schema is not None:
            try:
                module.input_schema.model_validate(effective_inputs)
            except pydantic.ValidationError as e:
                raise SchemaValidationError(
                    message="Input validation failed",
                    errors=_convert_validation_errors(e),
                ) from e
            ctx.redacted_inputs = redact_sensitive(effective_inputs, module.input_schema.model_json_schema())

        executed_middlewares: list[Middleware] = []

        try:
            # Step 7 -- Middleware Before (async-aware)
            try:
                effective_inputs, executed_middlewares = await self._middleware_manager.execute_before_async(
                    module_id, effective_inputs, ctx
                )
            except MiddlewareChainError as mce:
                executed_middlewares = mce.executed_middlewares
                recovery = await self._middleware_manager.execute_on_error_async(
                    module_id, effective_inputs, mce.original, ctx, executed_middlewares
                )
                if recovery is not None:
                    yield recovery
                    return
                executed_middlewares = []
                raise mce.original from mce

            # Cancel check before execution
            if ctx.cancel_token is not None:
                ctx.cancel_token.check()

            # Step 8 -- Stream or fallback
            if not hasattr(module, "stream") or module.stream is None:
                # Fallback: delegate to _execute_async, yield single chunk
                output = await self._execute_async(module, module_id, effective_inputs, ctx)

                # Step 9 -- Output Validation and Redaction
                if hasattr(module, "output_schema") and module.output_schema is not None:
                    try:
                        module.output_schema.model_validate(output)
                    except pydantic.ValidationError as e:
                        raise SchemaValidationError(
                            message="Output validation failed",
                            errors=_convert_validation_errors(e),
                        ) from e

                    REDACTED_OUTPUT.set(ctx, redact_sensitive(output, module.output_schema.model_json_schema()))

                # Step 10 -- Middleware After (async-aware)
                output = await self._middleware_manager.execute_after_async(module_id, effective_inputs, output, ctx)

                yield output
            else:
                # Streaming path: iterate module.stream(), accumulate via deep merge
                accumulated: dict[str, Any] = {}
                async for chunk in module.stream(effective_inputs, ctx):
                    _deep_merge(accumulated, chunk)
                    yield chunk

                # Step 9 -- Output Validation and Redaction on accumulated result
                if hasattr(module, "output_schema") and module.output_schema is not None:
                    try:
                        module.output_schema.model_validate(accumulated)
                    except pydantic.ValidationError as e:
                        raise SchemaValidationError(
                            message="Output validation failed",
                            errors=_convert_validation_errors(e),
                        ) from e

                    REDACTED_OUTPUT.set(ctx, redact_sensitive(accumulated, module.output_schema.model_json_schema()))

                # Step 10 -- Middleware After on accumulated result (async-aware)
                accumulated = await self._middleware_manager.execute_after_async(
                    module_id, effective_inputs, accumulated, ctx
                )

        except ExecutionCancelledError:
            raise
        except Exception as exc:
            # Error handling (A11): wrap and propagate
            wrapped = propagate_error(exc, module_id, ctx)
            if executed_middlewares:
                recovery = await self._middleware_manager.execute_on_error_async(
                    module_id,
                    effective_inputs,
                    wrapped,
                    ctx,
                    executed_middlewares,
                )
                if recovery is not None:
                    yield recovery
                    return
            raise wrapped from exc

    async def _execute_async(self, module: Any, module_id: str, inputs: dict[str, Any], ctx: Context) -> dict[str, Any]:
        """Execute module asynchronously with timeout."""
        timeout_ms = self._default_timeout

        if timeout_ms < 0:
            raise InvalidInputError(message=f"Negative timeout: {timeout_ms}ms")

        # Global deadline enforcement (dual-timeout model)
        if ctx._global_deadline is not None:
            remaining_ms = max(0, (ctx._global_deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                raise ModuleTimeoutError(module_id=module_id, timeout_ms=self._global_timeout)
            if timeout_ms == 0 or remaining_ms < timeout_ms:
                timeout_ms = int(remaining_ms)

        timeout_s = timeout_ms / 1000.0 if timeout_ms > 0 else None
        is_async = self._is_async_module(module_id, module)

        if is_async:
            coro = module.execute(inputs, ctx)
        else:
            coro = asyncio.to_thread(module.execute, inputs, ctx)

        if timeout_s is not None:
            try:
                return await asyncio.wait_for(coro, timeout=timeout_s)
            except asyncio.TimeoutError:
                raise ModuleTimeoutError(module_id=module_id, timeout_ms=timeout_ms)
        else:
            if timeout_ms == 0:
                _logger.warning("Timeout disabled for module %s", module_id)
            return await coro

    def clear_async_cache(self) -> None:
        """Clear the async module detection cache."""
        with self._async_cache_lock:
            self._async_cache.clear()

    # -------------------------------------------------------------------------
    # Strategy resolution
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_strategy_name(name: str, **kwargs: Any) -> ExecutionStrategy:
        """Resolve a strategy name to an ExecutionStrategy instance.

        Checks preset names first, then the class-level registered strategies.

        Args:
            name: Strategy name ("standard", "internal", "testing", "performance",
                or a previously registered name).
            **kwargs: Forwarded to preset builder functions.

        Returns:
            The resolved ExecutionStrategy.

        Raises:
            StrategyNotFoundError: If the name is not recognized.
        """
        from apcore.builtin_steps import (
            build_internal_strategy,
            build_performance_strategy,
            build_standard_strategy,
            build_testing_strategy,
        )

        preset_builders: dict[str, Any] = {
            "standard": build_standard_strategy,
            "internal": build_internal_strategy,
            "testing": build_testing_strategy,
            "performance": build_performance_strategy,
        }

        if name in preset_builders:
            return preset_builders[name](**kwargs)

        if name in Executor._registered_strategies:
            return Executor._registered_strategies[name]

        raise StrategyNotFoundError(
            message=f"Strategy '{name}' not found. "
            f"Available: {sorted(set(list(preset_builders) + list(Executor._registered_strategies)))}"
        )

    # -------------------------------------------------------------------------
    # call_with_trace / call_async_with_trace
    # -------------------------------------------------------------------------

    def call_with_trace(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Any | None = None,
        *,
        strategy: ExecutionStrategy | str | None = None,
    ) -> tuple[dict[str, Any], PipelineTrace]:
        """Sync call that returns (result, trace).

        Runs the module through the pipeline engine and returns both the
        output and the full pipeline trace for introspection.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context.
            strategy: Override strategy for this call.

        Returns:
            A tuple of (result dict, PipelineTrace).
        """
        effective_strategy = self._effective_strategy(strategy)
        pipe_ctx = PipelineContext(
            module_id=module_id,
            inputs=inputs or {},
            context=context,
            strategy=effective_strategy,
        )
        engine = PipelineEngine()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            return asyncio.run(engine.run(effective_strategy, pipe_ctx))
        return self._run_in_new_thread(engine.run(effective_strategy, pipe_ctx), module_id, None)

    async def call_async_with_trace(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Any | None = None,
        *,
        strategy: ExecutionStrategy | str | None = None,
    ) -> tuple[dict[str, Any], PipelineTrace]:
        """Async call that returns (result, trace).

        Runs the module through the pipeline engine and returns both the
        output and the full pipeline trace for introspection.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context.
            strategy: Override strategy for this call.

        Returns:
            A tuple of (result dict, PipelineTrace).
        """
        effective_strategy = self._effective_strategy(strategy)
        pipe_ctx = PipelineContext(
            module_id=module_id,
            inputs=inputs or {},
            context=context,
            strategy=effective_strategy,
        )
        engine = PipelineEngine()
        return await engine.run(effective_strategy, pipe_ctx)

    def _effective_strategy(
        self,
        strategy: ExecutionStrategy | str | None,
    ) -> ExecutionStrategy:
        """Return the strategy to use for a call, resolving strings."""
        if strategy is None:
            return self._strategy
        if isinstance(strategy, str):
            return self._resolve_strategy_name(
                strategy,
                registry=self._registry,
                config=self._config,
                acl=self._acl,
                approval_handler=self._approval_handler,
                middlewares=self._middleware_manager.snapshot(),
            )
        return strategy

    # -------------------------------------------------------------------------
    # Introspection
    # -------------------------------------------------------------------------

    @classmethod
    def register_strategy(cls, name: str, strategy: ExecutionStrategy) -> None:
        """Register a named strategy for resolution by string name.

        Args:
            name: The name to register under.
            strategy: The ExecutionStrategy instance.
        """
        cls._registered_strategies[name] = strategy

    def list_strategies(self) -> list[StrategyInfo]:
        """Return StrategyInfo for the current strategy and all registered strategies.

        Returns:
            A list of StrategyInfo, starting with the current strategy.
        """
        seen: set[str] = set()
        result: list[StrategyInfo] = []

        # Current strategy first
        info = self._strategy.info()
        result.append(info)
        seen.add(info.name)

        # Registered strategies
        for name, strat in sorted(self._registered_strategies.items()):
            if name not in seen:
                result.append(strat.info())
                seen.add(name)

        return result

    @property
    def current_strategy(self) -> ExecutionStrategy:
        """Return the current execution strategy."""
        return self._strategy

    def describe_pipeline(self) -> str:
        """Return a human-readable description of the current pipeline.

        Returns:
            A string like "11-step pipeline: step1 -> step2 -> ...".
        """
        names = self._strategy.step_names()
        return f"{len(names)}-step pipeline: " + " \u2192 ".join(names)
