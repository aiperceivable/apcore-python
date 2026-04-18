"""Executor — the module execution engine for apcore.

Resolves a module by ID, validates inputs against its schema, enforces ACL
and approval policies, runs the middleware chain, and returns the result.
Supports sync, async, and streaming execution modes.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

from apcore.acl import ACL
from apcore.approval import ApprovalHandler
from apcore.cancel import ExecutionCancelledError
from apcore.config import Config
from apcore.context import Context
from apcore.errors import (
    ACLDeniedError,
    InvalidInputError,
    ModuleError,
    ModuleExecuteError,
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
    PipelineAbortError,
    PipelineContext,
    PipelineEngine,
    PipelineTrace,
    StrategyInfo,
    StrategyNotFoundError,
)
from apcore.registry import MODULE_ID_PATTERN, Registry


__all__ = ["Executor"]
# NOTE: redact_sensitive and REDACTED_VALUE are kept importable from this module
# for backward compatibility but their canonical path is apcore.utils.redaction.

_logger = logging.getLogger(__name__)

# Map pipeline step names to PreflightResult check names
_STEP_TO_CHECK: dict[str, str] = {
    "context_creation": "context",
    "call_chain_guard": "call_chain",
    "module_lookup": "module_lookup",
    "acl_check": "acl",
    "approval_gate": "approval",
    "middleware_before": "middleware",
    "input_validation": "schema",
}


def _trace_to_checks(trace: PipelineTrace) -> list[PreflightCheckResult]:
    """Convert PipelineTrace steps to PreflightCheckResult list."""
    checks: list[PreflightCheckResult] = []
    for st in trace.steps:
        if st.skipped:
            continue
        check_name = _STEP_TO_CHECK.get(st.name, st.name)
        passed = st.result.action != "abort"
        error = None
        if not passed and st.result.explanation:
            error = {
                "code": f"STEP_{st.name.upper()}_FAILED",
                "message": st.result.explanation,
            }
        checks.append(
            PreflightCheckResult(check=check_name, passed=passed, error=error)
        )
    return checks


_MAX_MERGE_DEPTH = 32


def _deep_merge(
    base: dict[str, Any], override: dict[str, Any], *, _depth: int = 0
) -> None:
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
                "testing", "performance", "minimal"), or None (defaults to
                standard).
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

        if middlewares:
            for mw in middlewares:
                self._middleware_manager.add(mw)

        # Resolve strategy (pass middleware_manager and executor for production parity)
        strategy_kwargs: dict[str, Any] = {
            "registry": registry,
            "config": config,
            "acl": acl,
            "approval_handler": approval_handler,
            "middlewares": middlewares,
            "middleware_manager": self._middleware_manager,
            "executor": self,
        }
        if strategy is None:
            from apcore.builtin_steps import build_standard_strategy

            self._strategy = build_standard_strategy(**strategy_kwargs)
        elif isinstance(strategy, str):
            self._strategy = self._resolve_strategy_name(strategy, **strategy_kwargs)
        else:
            self._strategy = strategy

        self._pipeline_engine = PipelineEngine()

        if config is not None:
            val = config.get("executor.default_timeout")
            self._default_timeout: int = (
                val
                if val is not None
                else Config.get_default("executor.default_timeout")
            )
            val = config.get("executor.global_timeout")
            self._global_timeout: int = (
                val
                if val is not None
                else Config.get_default("executor.global_timeout")
            )
            val = config.get("executor.max_call_depth")
            self._max_call_depth: int = (
                val
                if val is not None
                else Config.get_default("executor.max_call_depth")
            )
            val = config.get("executor.max_module_repeat")
            self._max_module_repeat: int = (
                val
                if val is not None
                else Config.get_default("executor.max_module_repeat")
            )
        else:
            self._default_timeout = Config.get_default("executor.default_timeout")
            self._global_timeout = Config.get_default("executor.global_timeout")
            self._max_call_depth = Config.get_default("executor.max_call_depth")
            self._max_module_repeat = Config.get_default("executor.max_module_repeat")

        if self._default_timeout < 0:
            raise InvalidInputError(
                message=f"Negative default_timeout: {self._default_timeout}",
            )

        # Cached event loop for sync call() to avoid asyncio.run() overhead.
        # Callers that create many short-lived Executors should call
        # close() (or use the `async with` context-manager form) so the loop
        # is released deterministically rather than waiting for the GC finalizer.
        self._sync_loop: asyncio.AbstractEventLoop | None = None

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

        Updates both the executor field and the strategy's ``acl_check`` step
        via its public :meth:`BuiltinACLCheck.set_acl` setter when present.
        Custom user-supplied ACL steps without that setter are silently
        skipped — callers should re-register the strategy if they need to
        replace a custom step's ACL provider.

        Args:
            acl: The ACL instance to use for access control enforcement.
        """
        self._acl = acl
        for step in self._strategy.steps:
            if step.name != "acl_check":
                continue
            setter = getattr(step, "set_acl", None)
            if callable(setter):
                setter(acl)
            break

    def set_approval_handler(self, handler: ApprovalHandler) -> None:
        """Set the approval handler for Step 5 gate.

        Updates both the executor field and the strategy's ``approval_gate``
        step via its public :meth:`BuiltinApprovalGate.set_handler` setter
        when present. Custom user-supplied approval steps without that
        setter are silently skipped — callers should re-register the
        strategy if they need to replace a custom step's handler.

        Args:
            handler: The ApprovalHandler instance to use for approval enforcement.
        """
        self._approval_handler = handler
        for step in self._strategy.steps:
            if step.name != "approval_gate":
                continue
            setter = getattr(step, "set_handler", None)
            if callable(setter):
                setter(handler)
            break

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

    def close(self) -> None:
        """Release the cached sync event loop, if any.

        Safe to call multiple times. After ``close()``, a subsequent sync
        ``call()`` will lazily create a fresh loop — this method is the
        explicit teardown hook for short-lived Executors; long-lived
        singletons typically never call it.
        """
        loop = self._sync_loop
        self._sync_loop = None
        if loop is not None and not loop.is_closed():
            try:
                loop.close()
            except Exception as e:
                _logger.warning("Executor._sync_loop.close() raised: %s", e)

    def __enter__(self) -> Executor:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> Executor:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def call(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> dict[str, Any]:
        """Execute a module through the execution pipeline.

        Sync wrapper around :meth:`call_async`. Routes through a cached event
        loop when no loop is active and uses a thread bridge when called from
        inside a running loop.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Returns:
            The module output dict, possibly modified by middleware.
        """
        return self._run_async_in_sync(
            self.call_async(module_id, inputs, context, version_hint),
            module_id,
        )

    def _run_async_in_sync(self, coro: Any, module_id: str) -> Any:
        """Execute a coroutine from sync context using a cached loop or thread bridge.

        Centralizes the loop-detection logic shared by ``call``, ``validate``,
        and ``call_with_trace``. Inside an existing event loop, dispatches to a
        background thread; otherwise uses (and creates if needed) the cached
        ``_sync_loop``.
        """
        try:
            asyncio.get_running_loop()
            inside_loop = True
        except RuntimeError:
            inside_loop = False

        if inside_loop:
            return self._run_in_new_thread(coro, module_id, None)

        if self._sync_loop is None or self._sync_loop.is_closed():
            self._sync_loop = asyncio.new_event_loop()
        if self._sync_loop.is_running():
            return self._run_in_new_thread(coro, module_id, None)
        return self._sync_loop.run_until_complete(coro)

    def validate(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> PreflightResult:
        """Non-destructive preflight check using pipeline dry_run mode.

        Runs all pure steps (context creation, call chain guard, module lookup,
        ACL, input validation). Steps with pure=False (approval, middleware,
        execute) are automatically skipped. User-added pure steps are included.

        Args:
            module_id: The module to validate against.
            inputs: Input data to validate. None is treated as {}.
            context: Optional context for call-chain checks.

        Returns:
            PreflightResult with per-check status.
        """
        return self._run_async_in_sync(
            self._validate_async(module_id, inputs, context),
            module_id,
        )

    async def _validate_async(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
    ) -> PreflightResult:
        """Async implementation of validate()."""
        if inputs is None:
            inputs = {}

        checks: list[PreflightCheckResult] = []

        # Check 0: module_id format (before pipeline)
        try:
            self._validate_module_id(module_id)
            checks.append(PreflightCheckResult(check="module_id", passed=True))
        except InvalidInputError as e:
            checks.append(
                PreflightCheckResult(check="module_id", passed=False, error=e.to_dict())
            )
            return PreflightResult(valid=False, checks=checks)

        # Run pipeline in dry_run mode — pure=False steps are skipped
        pipe_ctx = PipelineContext(
            module_id=module_id,
            inputs=inputs,
            context=context,
            dry_run=True,
        )

        trace = None
        try:
            _, trace = await self._pipeline_engine.run(self._strategy, pipe_ctx)
        except PipelineAbortError as e:
            trace = e.pipeline_trace
        except Exception as e:
            # Step raised an error (e.g., ModuleNotFoundError, ACLDeniedError)
            # Convert to a failed check using the error's own code/dict
            error_dict: dict[str, Any] = {"code": type(e).__name__, "message": str(e)}
            to_dict_fn = getattr(e, "to_dict", None)
            if callable(to_dict_fn):
                produced = to_dict_fn()
                if isinstance(produced, dict):
                    error_dict = produced
            code = getattr(e, "code", type(e).__name__)

            # Determine which check failed based on error type
            if code == "MODULE_NOT_FOUND":
                check_name = "module_lookup"
            elif code == "ACL_DENIED":
                check_name = "acl"
            elif code in ("SCHEMA_VALIDATION_ERROR", "INVALID_INPUT"):
                check_name = "schema"
            elif code in (
                "CALL_DEPTH_EXCEEDED",
                "CIRCULAR_CALL",
                "CALL_FREQUENCY_EXCEEDED",
            ):
                check_name = "call_chain"
            else:
                check_name = "unknown"

            checks.append(
                PreflightCheckResult(check=check_name, passed=False, error=error_dict)
            )

        # Convert pipeline trace to PreflightResult checks
        if trace is not None:
            checks.extend(_trace_to_checks(trace))

        # Detect requires_approval (preflight reports, does not enforce)
        requires_approval = False
        if pipe_ctx.module is not None:
            annotations = getattr(pipe_ctx.module, "annotations", None)
            if isinstance(annotations, ModuleAnnotations):
                requires_approval = annotations.requires_approval
            elif isinstance(annotations, dict):
                requires_approval = bool(annotations.get("requires_approval", False))

        # Module-level preflight (optional)
        if (
            pipe_ctx.module is not None
            and hasattr(pipe_ctx.module, "preflight")
            and callable(pipe_ctx.module.preflight)
        ):
            try:
                preflight_warnings = pipe_ctx.module.preflight(inputs, pipe_ctx.context)
                if isinstance(preflight_warnings, list) and preflight_warnings:
                    checks.append(
                        PreflightCheckResult(
                            check="module_preflight",
                            passed=True,
                            warnings=preflight_warnings,
                        )
                    )
                else:
                    checks.append(
                        PreflightCheckResult(check="module_preflight", passed=True)
                    )
            except Exception as exc:
                checks.append(
                    PreflightCheckResult(
                        check="module_preflight",
                        passed=True,
                        warnings=[f"preflight() raised {type(exc).__name__}: {exc}"],
                    )
                )

        valid = all(c.passed for c in checks)
        return PreflightResult(
            valid=valid, checks=checks, requires_approval=requires_approval
        )

    @staticmethod
    def _validate_module_id(module_id: str) -> None:
        """Validate module_id format at public entry points."""
        if not module_id or not MODULE_ID_PATTERN.match(module_id):
            raise InvalidInputError(
                message=f"Invalid module ID: '{module_id}'. Must match pattern: {MODULE_ID_PATTERN.pattern}"
            )

    def _translate_abort(self, abort: PipelineAbortError) -> ModuleError:
        """Translate PipelineAbortError into the appropriate ModuleError subclass.

        Maps pipeline step abort explanations back to the error types callers expect.
        """
        explanation = abort.explanation or ""
        step = abort.step

        if step == "module_lookup" and "not found" in explanation.lower():
            # Extract module_id from explanation
            return ModuleNotFoundError(
                module_id=explanation.split(": ")[-1] if ": " in explanation else ""
            )
        if step == "acl_check" and "denied" in explanation.lower():
            # Parse "Access denied: {caller} -> {target}" from BuiltinACLCheck
            caller_id = ""
            target_id = ""
            if " -> " in explanation:
                parts = explanation.split(": ", 1)[-1]
                pair = parts.split(" -> ", 1)
                if len(pair) == 2:
                    caller_id, target_id = pair[0].strip(), pair[1].strip()
            return ACLDeniedError(caller_id=caller_id, target_id=target_id)
        # Note: there is no `approval_gate` branch here. BuiltinApprovalGate
        # raises typed Approval{Denied,Timeout,Pending}Error subclasses
        # *directly* (see builtin_steps.BuiltinApprovalGate.execute), so the
        # error never reaches this translation path. Custom user-supplied
        # approval steps MUST follow the same contract: raise the typed
        # Approval*Error subclass with a real ApprovalResult — do NOT abort
        # via StepResult(action="abort", explanation="...rejected...").
        if step == "input_validation" and "validation failed" in explanation.lower():
            return SchemaValidationError(message=explanation)
        if step == "output_validation" and "validation failed" in explanation.lower():
            return SchemaValidationError(message=explanation)
        if step == "execute":
            if "cancelled" in explanation.lower():
                from apcore.cancel import ExecutionCancelledError

                return ExecutionCancelledError()
            if "deadline" in explanation.lower() or "timed out" in explanation.lower():
                return ModuleTimeoutError(module_id="", timeout_ms=0)

        # Fallback: return as ModuleError
        return ModuleError(code="PIPELINE_ABORT", message=explanation)

    def _run_in_new_thread(
        self, coro: Any, module_id: str, timeout_s: float | None
    ) -> Any:
        """Run coroutine in a new thread with its own event loop.

        Bounds the outer ``thread.join()`` by ``self._global_timeout`` (ms) so a
        dead-locked coroutine cannot indefinitely hang the sync caller. The
        daemon thread is left running (process exit remains clean); the caller
        receives ``ModuleTimeoutError`` naming the module that blocked.

        The per-call ``timeout_s`` still applies inside the thread via
        ``asyncio.wait_for``; the outer bound is a strictly-looser safety
        net for the case where the coroutine swallows cancellation.
        """
        result_holder: dict[str, Any] = {}
        exception_holder: dict[str, Exception] = {}

        def thread_target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if timeout_s is not None:
                    result_holder["output"] = loop.run_until_complete(
                        asyncio.wait_for(coro, timeout=timeout_s)
                    )
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
        outer_budget_s = max(self._global_timeout, self._default_timeout) / 1000.0 + 1.0
        thread.join(timeout=outer_budget_s)
        if thread.is_alive():
            raise ModuleTimeoutError(
                module_id=module_id,
                timeout_ms=int(outer_budget_s * 1000),
            )

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
        """Async module execution — delegates to PipelineEngine.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Returns:
            The module output dict, possibly modified by middleware.
        """
        self._validate_module_id(module_id)

        pipe_ctx = PipelineContext(
            module_id=module_id,
            inputs=inputs or {},
            context=context,
            version_hint=version_hint,
        )
        try:
            output, _trace = await self._pipeline_engine.run(self._strategy, pipe_ctx)
        except PipelineAbortError as e:
            raise self._translate_abort(e) from e
        except ExecutionCancelledError:
            raise
        except Exception as exc:
            return await self._recover_from_call_error(exc, pipe_ctx, module_id)
        return output

    async def _recover_from_call_error(
        self,
        exc: Exception,
        pipe_ctx: PipelineContext,
        module_id: str,
    ) -> dict[str, Any]:
        """Run A11 error propagation + middleware on_error recovery.

        Returns the recovery dict from the first middleware that provides one.
        If no middleware recovers, raises the wrapped error (or wraps a
        ``MiddlewareChainError`` into ``ModuleExecuteError`` first). Never
        returns ``None`` — callers can rely on the fact that a return value is
        always a valid recovery dict.
        """
        ctx_obj = pipe_ctx.context
        wrapped = propagate_error(exc, module_id, ctx_obj) if ctx_obj else exc
        executed_mw = pipe_ctx.executed_middlewares
        if executed_mw:
            recovery = await self._middleware_manager.execute_on_error_async(
                module_id, pipe_ctx.inputs, wrapped, ctx_obj, executed_mw
            )
            if recovery is not None:
                return recovery
        if isinstance(exc, MiddlewareChainError):
            raise ModuleExecuteError(module_id=module_id, message=str(exc)) from exc
        raise wrapped from exc

    async def stream(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async generator that streams module output chunks.

        Phase 1: Pipeline runs steps 1-7 (context, guard, lookup, ACL, approval,
        middleware_before, input_validation). Step 8 (execute) sets up the stream
        or falls back to single-chunk mode.
        Phase 2: After streaming, runs output_validation + middleware_after on
        accumulated output.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context. Auto-created if None.
            version_hint: Optional semver hint for version negotiation.

        Yields:
            Dict chunks from the module's stream() or a single call_async() result.
        """
        self._validate_module_id(module_id)

        pipe_ctx = PipelineContext(
            module_id=module_id,
            inputs=inputs or {},
            context=context,
            version_hint=version_hint,
            stream=True,
        )

        # Phase 1: Run pipeline up to execute step.
        # BuiltinExecute detects ctx.stream=True and checks for module.stream().
        try:
            output, _trace = await self._pipeline_engine.run(self._strategy, pipe_ctx)
        except PipelineAbortError as e:
            raise self._translate_abort(e) from e
        except ExecutionCancelledError:
            raise
        except Exception as exc:
            yield await self._recover_from_call_error(exc, pipe_ctx, module_id)
            return

        # If module has no stream(), pipeline already executed and set ctx.output
        if pipe_ctx.output_stream is None:
            yield pipe_ctx.output or {}
            return

        # Phase 2: Iterate stream, accumulate chunks
        # Per streaming.md §4, respect ctx.context.global_deadline during
        # iteration: raise ModuleTimeoutError between chunks if the deadline
        # passes, so long-running streams cannot silently outrun their budget.
        accumulated: dict[str, Any] = {}
        global_deadline = getattr(pipe_ctx.context, "global_deadline", None)
        try:
            async for chunk in pipe_ctx.output_stream:
                if global_deadline is not None and time.monotonic() > global_deadline:
                    raise ModuleTimeoutError(
                        module_id=module_id,
                        timeout_ms=self._global_timeout,
                    )
                _deep_merge(accumulated, chunk)
                yield chunk
        except ExecutionCancelledError:
            raise
        except Exception as exc:
            yield await self._recover_from_call_error(exc, pipe_ctx, module_id)
            return

        # Phase 3: Output validation + middleware_after on accumulated result
        pipe_ctx.output = accumulated
        post_steps = [
            s
            for s in self._strategy.steps
            if s.name in ("output_validation", "middleware_after", "return_result")
        ]
        if post_steps:
            post_strategy = ExecutionStrategy("post_stream", post_steps)
            try:
                await self._pipeline_engine.run(post_strategy, pipe_ctx)
            except Exception:
                # Non-fatal for the caller: chunks have already been yielded,
                # so a failed post-stream validation/middleware run cannot
                # retroactively change the observable output. Logged at
                # WARNING (not DEBUG) so the failure is visible in default
                # production observability — unvalidated output that reached
                # a consumer is worth investigating even if it can't be
                # un-sent.
                _logger.warning(
                    "Post-stream validation/middleware failed for module %s",
                    module_id,
                    exc_info=True,
                )

    # _execute_async removed in v0.17 (replaced by BuiltinExecute pipeline step)

    # -------------------------------------------------------------------------
    # Strategy resolution
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_strategy_name(name: str, **kwargs: Any) -> ExecutionStrategy:
        """Resolve a strategy name to an ExecutionStrategy instance.

        Checks preset names first, then the class-level registered strategies.

        Args:
            name: Strategy name ("standard", "internal", "testing", "performance",
                "minimal", or a previously registered name).
            **kwargs: Forwarded to preset builder functions.

        Returns:
            The resolved ExecutionStrategy.

        Raises:
            StrategyNotFoundError: If the name is not recognized.
        """
        from apcore.builtin_steps import (
            build_internal_strategy,
            build_minimal_strategy,
            build_performance_strategy,
            build_standard_strategy,
            build_testing_strategy,
        )

        preset_builders: dict[str, Any] = {
            "standard": build_standard_strategy,
            "internal": build_internal_strategy,
            "testing": build_testing_strategy,
            "performance": build_performance_strategy,
            "minimal": build_minimal_strategy,
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

        Sync wrapper around :meth:`call_async_with_trace`. Runs the module
        through the pipeline engine and returns both the output and the full
        pipeline trace for introspection.

        Args:
            module_id: The module to execute.
            inputs: Input data dict. None is treated as {}.
            context: Optional execution context.
            strategy: Override strategy for this call.

        Returns:
            A tuple of (result dict, PipelineTrace).
        """
        return self._run_async_in_sync(
            self.call_async_with_trace(module_id, inputs, context, strategy=strategy),
            module_id,
        )

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
        output and the full pipeline trace for introspection. Errors flow
        through the same A11 propagation + middleware ``on_error`` recovery
        path as :meth:`call_async`; if a middleware recovers, the recovery
        dict is returned alongside the trace captured up to the failure.

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
            return await engine.run(effective_strategy, pipe_ctx)
        except PipelineAbortError as e:
            raise self._translate_abort(e) from e
        except ExecutionCancelledError:
            raise
        except Exception as exc:
            # If a middleware ``on_error`` recovers, return the recovery dict.
            # The full pipeline trace was held inside ``engine.run`` and is not
            # accessible here, so callers receive a sentinel trace marking the
            # strategy and module — sufficient for routing/observability but
            # without per-step detail. Callers needing the partial trace
            # should use ``call_async`` (which discards the trace) or attach
            # a tracing middleware.
            recovery = await self._recover_from_call_error(exc, pipe_ctx, module_id)
            return recovery, PipelineTrace(
                module_id=module_id, strategy_name=effective_strategy.name
            )

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

    def describe_pipeline(self) -> StrategyInfo:
        """Return an AI-introspectable description of the current pipeline.

        Returns:
            A StrategyInfo dataclass with name, step_count, step_names, and
            a human-readable description string.
        """
        return self._strategy.info()
