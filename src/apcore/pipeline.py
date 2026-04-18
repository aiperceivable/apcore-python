"""Execution pipeline types for configurable step-based module invocation."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from apcore.errors import ModuleError
from apcore.utils.pattern import match_pattern

_logger = logging.getLogger(__name__)


def _any_match(patterns: tuple[str, ...], module_id: str) -> bool:
    """Return True if any glob pattern matches the module_id (Algorithm A09)."""
    return any(match_pattern(p, module_id) for p in patterns)


@runtime_checkable
class Step(Protocol):
    """Protocol for pipeline steps."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def removable(self) -> bool: ...

    @property
    def replaceable(self) -> bool: ...

    async def execute(self, ctx: PipelineContext) -> StepResult: ...


class BaseStep(ABC):
    """Convenience base class for pipeline steps."""

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        removable: bool = True,
        replaceable: bool = True,
        match_modules: tuple[str, ...] | None = None,
        ignore_errors: bool = False,
        pure: bool = False,
        timeout_ms: int = 0,
        requires: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.description = description
        self.removable = removable
        self.replaceable = replaceable
        self.match_modules = match_modules
        self.ignore_errors = ignore_errors
        self.pure = pure
        self.timeout_ms = timeout_ms
        self.requires = requires
        self.provides = provides

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> StepResult: ...


@dataclass
class StepResult:
    """Result returned by a pipeline step execution."""

    action: str  # "continue", "skip_to", "abort"
    skip_to: str | None = None
    explanation: str | None = None
    confidence: float | None = None
    alternatives: list[str] | None = None


@dataclass
class PipelineContext:
    """Holds all state flowing through the pipeline."""

    module_id: str
    inputs: dict[str, Any]
    context: Any  # Context object
    module: Any | None = None
    validated_inputs: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    validated_output: dict[str, Any] | None = None
    stream: bool = False
    output_stream: Any | None = None
    strategy: ExecutionStrategy | None = None
    trace: PipelineTrace | None = None
    # New in v0.17
    dry_run: bool = False
    version_hint: str | None = None
    executed_middlewares: list[Any] = field(default_factory=list)


@dataclass
class StepTrace:
    """Records execution details for a single step."""

    name: str
    duration_ms: float
    result: StepResult
    skipped: bool = False
    decision_point: bool = False
    skip_reason: str | None = None


@dataclass
class PipelineTrace:
    """Records execution details for the entire pipeline run."""

    module_id: str
    strategy_name: str
    steps: list[StepTrace] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = False


@dataclass
class StrategyInfo:
    """AI-introspectable description of an execution strategy."""

    name: str
    step_count: int
    step_names: list[str]
    description: str

    def __str__(self) -> str:
        return f"{self.step_count}-step pipeline: " + " \u2192 ".join(self.step_names)


class ExecutionStrategy:
    """An ordered sequence of steps that defines how a module is executed."""

    def __init__(self, name: str, steps: list[Step]) -> None:
        self.name = name
        self.steps = list(steps)
        # Validate unique step names
        names = [s.name for s in self.steps]
        if len(names) != len(set(names)):
            dupes = [n for n in names if names.count(n) > 1]
            raise StepNameDuplicateError(f"Duplicate step names: {set(dupes)}")
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        """Warn if any step's requires are not provided by a preceding step."""
        provided: set[str] = set()
        for step in self.steps:
            requires: tuple[str, ...] = getattr(step, "requires", ())
            missing = set(requires) - provided
            if missing:
                _logger.warning(
                    "Step '%s' requires %s, but no preceding step provides them. " "This may cause runtime errors.",
                    step.name,
                    missing,
                )
            provides: tuple[str, ...] = getattr(step, "provides", ())
            provided.update(provides)

    def insert_after(self, anchor: str, step: Step) -> None:
        """Insert a step after the named anchor step."""
        if any(s.name == step.name for s in self.steps):
            raise StepNameDuplicateError(f"Step '{step.name}' already exists")
        for i, s in enumerate(self.steps):
            if s.name == anchor:
                self.steps.insert(i + 1, step)
                self._validate_dependencies()
                return
        raise StepNotFoundError(f"Anchor step '{anchor}' not found")

    def insert_before(self, anchor: str, step: Step) -> None:
        """Insert a step before the named anchor step."""
        if any(s.name == step.name for s in self.steps):
            raise StepNameDuplicateError(f"Step '{step.name}' already exists")
        for i, s in enumerate(self.steps):
            if s.name == anchor:
                self.steps.insert(i, step)
                self._validate_dependencies()
                return
        raise StepNotFoundError(f"Anchor step '{anchor}' not found")

    def remove(self, step_name: str) -> None:
        """Remove a step by name. Raises if the step is not removable."""
        for i, s in enumerate(self.steps):
            if s.name == step_name:
                if not s.removable:
                    raise StepNotRemovableError(f"Step '{step_name}' is not removable")
                self.steps.pop(i)
                return
        raise StepNotFoundError(f"Step '{step_name}' not found")

    def replace(self, step_name: str, new_step: Step) -> None:
        """Replace a step by name. Raises if the step is not replaceable."""
        for i, s in enumerate(self.steps):
            if s.name == step_name:
                if not s.replaceable:
                    raise StepNotReplaceableError(f"Step '{step_name}' is not replaceable")
                self.steps[i] = new_step
                return
        raise StepNotFoundError(f"Step '{step_name}' not found")

    def step_names(self) -> list[str]:
        """Return the ordered list of step names."""
        return [s.name for s in self.steps]

    def info(self) -> StrategyInfo:
        """Return an AI-introspectable description of this strategy."""
        return StrategyInfo(
            name=self.name,
            step_count=len(self.steps),
            step_names=self.step_names(),
            description=" \u2192 ".join(self.step_names()),
        )


class PipelineEngine:
    """Executes a pipeline strategy step by step."""

    async def run(
        self,
        strategy: ExecutionStrategy,
        ctx: PipelineContext,
    ) -> tuple[Any, PipelineTrace]:
        """Run all steps in the strategy, returning the final output and trace."""
        trace = PipelineTrace(
            module_id=ctx.module_id,
            strategy_name=strategy.name,
        )
        start = time.monotonic()
        steps = strategy.steps
        i = 0

        # Index-based loop (not for-each) to support skip_to.
        while i < len(steps):
            step = steps[i]

            # ── Read declarative metadata (getattr for backward compat) ──
            match_modules = getattr(step, "match_modules", None)
            ignore_errors = getattr(step, "ignore_errors", False)
            pure = getattr(step, "pure", False)
            timeout_ms = getattr(step, "timeout_ms", 0)

            # (1) match_modules filter
            if match_modules is not None and not _any_match(match_modules, ctx.module_id):
                trace.steps.append(
                    StepTrace(
                        name=step.name,
                        duration_ms=0,
                        result=StepResult(action="continue"),
                        skipped=True,
                        skip_reason="no_match",
                    )
                )
                i += 1
                continue

            # (2) dry_run filter: skip impure steps
            if getattr(ctx, "dry_run", False) and not pure:
                trace.steps.append(
                    StepTrace(
                        name=step.name,
                        duration_ms=0,
                        result=StepResult(action="continue"),
                        skipped=True,
                        skip_reason="dry_run",
                    )
                )
                i += 1
                continue

            # (3) Execute with optional per-step timeout
            step_start = time.monotonic()
            try:
                if timeout_ms > 0:
                    result = await asyncio.wait_for(
                        step.execute(ctx),
                        timeout=timeout_ms / 1000,
                    )
                else:
                    result = await step.execute(ctx)
            except asyncio.TimeoutError:
                duration = (time.monotonic() - step_start) * 1000
                if ignore_errors:
                    _logger.warning(
                        "Step '%s' timed out after %dms (ignored)",
                        step.name,
                        timeout_ms,
                    )
                    trace.steps.append(
                        StepTrace(
                            name=step.name,
                            duration_ms=duration,
                            result=StepResult(
                                action="continue",
                                explanation=f"Timeout after {timeout_ms}ms (ignored)",
                            ),
                            skip_reason="error_ignored",
                        )
                    )
                    i += 1
                    continue
                trace.steps.append(
                    StepTrace(
                        name=step.name,
                        duration_ms=duration,
                        result=StepResult(
                            action="abort",
                            explanation=f"Step timed out after {timeout_ms}ms",
                        ),
                    )
                )
                trace.total_duration_ms = (time.monotonic() - start) * 1000
                raise PipelineAbortError(
                    step=step.name,
                    explanation=f"Step timed out after {timeout_ms}ms",
                    trace=trace,
                    abort_reason=AbortReason.MODULE_TIMEOUT,
                )
            except Exception as exc:
                duration = (time.monotonic() - step_start) * 1000
                # (4) ignore_errors: log and continue
                if ignore_errors:
                    _logger.warning("Step '%s' failed (ignored): %s", step.name, exc)
                    trace.steps.append(
                        StepTrace(
                            name=step.name,
                            duration_ms=duration,
                            result=StepResult(
                                action="continue",
                                explanation=str(exc),
                            ),
                            skip_reason="error_ignored",
                        )
                    )
                    i += 1
                    continue
                # Not ignored: record and raise
                trace.steps.append(
                    StepTrace(
                        name=step.name,
                        duration_ms=duration,
                        result=StepResult(action="abort", explanation=str(exc)),
                    )
                )
                trace.total_duration_ms = (time.monotonic() - start) * 1000
                raise

            # (5) Record successful step trace
            step_trace = StepTrace(
                name=step.name,
                duration_ms=(time.monotonic() - step_start) * 1000,
                result=result,
                decision_point=result.confidence is not None,
            )
            trace.steps.append(step_trace)

            if result.action == "abort":
                trace.total_duration_ms = (time.monotonic() - start) * 1000
                raise PipelineAbortError(
                    step=step.name,
                    explanation=result.explanation,
                    alternatives=result.alternatives,
                    trace=trace,
                )
            elif result.action == "skip_to":
                target = result.skip_to
                target_idx = None
                for j in range(i + 1, len(steps)):
                    if steps[j].name == target:
                        target_idx = j
                        break
                    # Record skipped steps in trace
                    trace.steps.append(
                        StepTrace(
                            name=steps[j].name,
                            duration_ms=0,
                            result=StepResult(action="continue"),
                            skipped=True,
                            decision_point=False,
                        )
                    )
                if target_idx is None:
                    raise StepNotFoundError(
                        f"skip_to target '{target}' not found",
                    )
                i = target_idx
                continue

            i += 1

        trace.success = True
        trace.total_duration_ms = (time.monotonic() - start) * 1000
        # Use ctx.output — it's the most up-to-date (middleware_after may modify it)
        return ctx.output, trace


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class AbortReason(str, Enum):
    """Stable, typed discriminator for why a pipeline step aborted.

    Prefer this over inspecting ``PipelineAbortError.explanation`` strings:
    the explanation is user-facing text that may change between releases,
    while ``AbortReason`` is a committed contract consumed by the executor
    when translating aborts back to typed errors.
    """

    MODULE_NOT_FOUND = "module_not_found"
    ACL_DENIED = "acl_denied"
    INPUT_VALIDATION_FAILED = "input_validation_failed"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"
    MODULE_CANCELLED = "module_cancelled"
    MODULE_TIMEOUT = "module_timeout"
    OTHER = "other"


class PipelineAbortError(ModuleError):
    """Raised when a pipeline is aborted at a step."""

    def __init__(
        self,
        step: str,
        explanation: str | None = None,
        alternatives: list[str] | None = None,
        trace: PipelineTrace | None = None,
        abort_reason: AbortReason | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            code="PIPELINE_ABORT",
            message=f"Pipeline aborted at step '{step}': {explanation or 'no explanation'}",
            **kwargs,
        )
        self.step = step
        self.explanation = explanation
        self.alternatives = alternatives
        self.pipeline_trace = trace
        self.abort_reason: AbortReason = abort_reason or AbortReason.OTHER


class StepNotFoundError(ModuleError):
    """Raised when a referenced step does not exist."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        super().__init__(code="STEP_NOT_FOUND", message=message, **kwargs)


class StepNotRemovableError(ModuleError):
    """Raised when attempting to remove a non-removable step."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        super().__init__(code="STEP_NOT_REMOVABLE", message=message, **kwargs)


class StepNotReplaceableError(ModuleError):
    """Raised when attempting to replace a non-replaceable step."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        super().__init__(code="STEP_NOT_REPLACEABLE", message=message, **kwargs)


class StepNameDuplicateError(ModuleError):
    """Raised when a step name already exists in the strategy."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        super().__init__(code="STEP_NAME_DUPLICATE", message=message, **kwargs)


class StrategyNotFoundError(ModuleError):
    """Raised when a referenced strategy does not exist."""

    def __init__(self, message: str = "", **kwargs: Any) -> None:
        super().__init__(code="STRATEGY_NOT_FOUND", message=message, **kwargs)
