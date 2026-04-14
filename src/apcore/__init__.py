"""apcore - Schema-driven module standard."""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from typing import Any

# Core
from apcore.approval import (
    AlwaysDenyHandler,
    ApprovalHandler,
    ApprovalRequest,
    ApprovalResult,
    AutoApproveHandler,
    CallbackApprovalHandler,
)
from apcore.cancel import CancelToken, ExecutionCancelledError
from apcore.context import Context, ContextFactory, Identity
from apcore.context_key import ContextKey
from apcore.context_keys import (
    LOGGING_START,
    METRICS_STARTS,
    REDACTED_OUTPUT,
    RETRY_COUNT_BASE,
    TRACING_SAMPLED,
    TRACING_SPANS,
)
from apcore.registry import Registry
from apcore.registry.registry import Discoverer, ModuleValidator
from apcore.client import APCore
from apcore.registry.types import DependencyInfo, DiscoveredModule, ModuleDescriptor
from apcore.executor import Executor
from apcore.utils.redaction import REDACTED_VALUE, redact_sensitive

# Module types
from apcore.module import (
    DEFAULT_ANNOTATIONS,
    Module,
    ModuleAnnotations,
    ModuleExample,
    PreflightCheckResult,
    PreflightResult,
    ValidationResult,
)

# Config
from apcore.config import Config, discover_config_file

# Error Formatter
from apcore.error_formatter import ErrorFormatter, ErrorFormatterRegistry

# Errors
from apcore.errors import (
    ACLDeniedError,
    ACLRuleError,
    ApprovalDeniedError,
    ApprovalError,
    ApprovalPendingError,
    ApprovalTimeoutError,
    BindingCallableNotFoundError,
    BindingFileInvalidError,
    BindingInvalidTargetError,
    BindingModuleNotFoundError,
    BindingNotCallableError,
    BindingSchemaMissingError,
    CallDepthExceededError,
    CallFrequencyExceededError,
    CircularCallError,
    CircularDependencyError,
    ConfigBindError,
    ConfigEnvMapConflictError,
    ConfigEnvPrefixConflictError,
    ConfigError,
    ConfigMountError,
    ConfigNamespaceDuplicateError,
    ConfigNamespaceReservedError,
    ConfigNotFoundError,
    ErrorCodeCollisionError,
    ErrorCodeRegistry,
    ErrorCodes,
    ErrorFormatterDuplicateError,
    FRAMEWORK_ERROR_CODE_PREFIXES,
    FuncMissingReturnTypeError,
    FuncMissingTypeHintError,
    InternalError,
    InvalidInputError,
    ModuleDisabledError,
    ModuleError,
    ModuleExecuteError,
    ModuleLoadError,
    ModuleNotFoundError,
    ModuleTimeoutError,
    ReloadFailedError,
    SchemaCircularRefError,
    SchemaNotFoundError,
    SchemaParseError,
    SchemaValidationError,
)

# ACL
from apcore.acl import ACL, ACLRule, AuditEntry

# Middleware
from apcore.middleware import (
    AfterMiddleware,
    BeforeMiddleware,
    ErrorHistoryMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareChainError,
    MiddlewareManager,
    PlatformNotifyMiddleware,
    RetryConfig,
    RetryMiddleware,
)

# Decorators
from apcore.decorator import FunctionModule
from apcore._docstrings import parse_docstring as parse_docstring

# Extensions
from apcore.extensions import ExtensionManager, ExtensionPoint

# Async tasks
from apcore.async_task import AsyncTaskManager, TaskInfo, TaskStatus

# Bindings
from apcore.bindings import BindingLoader

# Schema
from apcore.schema import (
    ExportProfile as ExportProfile,
    SchemaLoader as SchemaLoader,
    SchemaStrategy as SchemaStrategy,
    SchemaValidator as SchemaValidator,
    SchemaExporter as SchemaExporter,
    RefResolver as RefResolver,
    to_strict_schema as to_strict_schema,
)

# Version negotiation (A14)
from apcore.version import VersionIncompatibleError as VersionIncompatibleError
from apcore.version import negotiate_version as negotiate_version

# Utilities
from apcore.utils import match_pattern as match_pattern
from apcore.utils.call_chain import guard_call_chain as guard_call_chain
from apcore.utils.call_chain import DEFAULT_MAX_CALL_DEPTH as DEFAULT_MAX_CALL_DEPTH
from apcore.utils.call_chain import DEFAULT_MAX_MODULE_REPEAT as DEFAULT_MAX_MODULE_REPEAT
from apcore.utils.error_propagation import propagate_error as propagate_error
from apcore.utils.normalize import normalize_to_canonical_id as normalize_to_canonical_id
from apcore.utils.pattern import calculate_specificity as calculate_specificity

# Observability
from apcore.observability import (
    ContextLogger,
    ErrorEntry,
    ErrorHistory,
    InMemoryExporter,
    MetricsCollector,
    MetricsMiddleware,
    ObsLoggingMiddleware,
    OTLPExporter,
    Span,
    SpanExporter,
    StdoutExporter,
    TracingMiddleware,
    UsageCollector,
    UsageMiddleware,
    create_span,
)
from apcore.observability.metrics import (
    METRIC_CALLS_TOTAL,
    METRIC_DURATION_SECONDS,
)

# Events
from apcore.events import A2ASubscriber, ApCoreEvent, EventEmitter, EventSubscriber, WebhookSubscriber

# Pipeline
from apcore.pipeline import (
    BaseStep,
    ExecutionStrategy,
    PipelineAbortError,
    PipelineContext,
    PipelineEngine,
    PipelineTrace,
    Step,
    StepNameDuplicateError,
    StepNotFoundError,
    StepNotRemovableError,
    StepNotReplaceableError,
    StepResult,
    StepTrace,
    StrategyInfo,
    StrategyNotFoundError,
)

# Pipeline Configuration
from apcore.pipeline_config import (
    build_strategy_from_config,
    register_step_type,
    registered_step_types,
    unregister_step_type,
)

# Pipeline Preset Builders (parity with apcore-typescript and apcore-rust)
from apcore.builtin_steps import (
    BuiltinACLCheck,
    BuiltinApprovalGate,
    BuiltinCallChainGuard,
    BuiltinContextCreation,
    BuiltinExecute,
    BuiltinInputValidation,
    BuiltinMiddlewareAfter,
    BuiltinMiddlewareBefore,
    BuiltinModuleLookup,
    BuiltinOutputValidation,
    BuiltinReturnResult,
    build_internal_strategy,
    build_minimal_strategy,
    build_performance_strategy,
    build_standard_strategy,
    build_testing_strategy,
)

# Trace Context
from apcore.trace_context import TraceContext, TraceParent

# System Modules
from apcore.sys_modules.registration import (
    SysModulesContext,
    register_subscriber_type,
    register_sys_modules,
    reset_subscriber_registry,
    unregister_subscriber_type,
)
from apcore.sys_modules.health import (
    HealthModule,
    HealthModuleModule,  # backward-compat alias
    HealthSummaryModule,
    classify_health_status,
)
from apcore.sys_modules.manifest import (
    ManifestFullModule,
    ManifestModule,
    ManifestModuleModule,  # backward-compat alias
)
from apcore.sys_modules.usage import (
    UsageModule,
    UsageModuleModule,  # backward-compat alias
    UsageSummaryModule,
)
from apcore.sys_modules.control import (
    ReloadModule,
    ReloadModuleModule,  # backward-compat alias
    ToggleFeatureModule,
    ToggleState,
    UpdateConfigModule,
)

# ---------------------------------------------------------------------------
# Default client for simplified global access
# ---------------------------------------------------------------------------

# Module-level convenience wrappers — Python SDK only.
# These forward to a default APCore singleton. TypeScript and Rust SDKs
# do not provide equivalent top-level functions; users in those languages
# must construct an APCore instance explicitly.
_default_client = APCore()


def call(
    module_id: str,
    inputs: dict[str, Any] | None = None,
    context: Context | None = None,
    version_hint: str | None = None,
) -> dict[str, Any]:
    """Global convenience for _default_client.call()."""
    return _default_client.call(module_id, inputs, context, version_hint=version_hint)


async def call_async(
    module_id: str,
    inputs: dict[str, Any] | None = None,
    context: Context | None = None,
    version_hint: str | None = None,
) -> dict[str, Any]:
    """Global convenience for _default_client.call_async()."""
    return await _default_client.call_async(module_id, inputs, context, version_hint=version_hint)


def module(
    id: str | None = None,  # noqa: A002
    description: str | None = None,
    documentation: str | None = None,
    annotations: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    version: str = "1.0.0",
    metadata: dict[str, Any] | None = None,
    examples: list[Any] | None = None,
    registry: Any = None,
) -> Any:
    """Global decorator that uses the default client (if no registry is provided)."""
    if registry is not None:
        from apcore.decorator import module as original_module

        return original_module(
            id=id,
            description=description,
            documentation=documentation,
            annotations=annotations,
            tags=tags,
            version=version,
            metadata=metadata,
            examples=examples,
            registry=registry,
        )
    return _default_client.module(
        id=id,
        description=description,
        documentation=documentation,
        annotations=annotations,
        tags=tags,
        version=version,
        metadata=metadata,
        examples=examples,
    )


async def stream(
    module_id: str,
    inputs: dict[str, Any] | None = None,
    context: Context | None = None,
    version_hint: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Global convenience for _default_client.stream()."""
    async for chunk in _default_client.stream(module_id, inputs, context, version_hint=version_hint):
        yield chunk


def validate(module_id: str, inputs: dict[str, Any] | None = None, context: Context | None = None) -> PreflightResult:
    """Global convenience for _default_client.validate()."""
    return _default_client.validate(module_id, inputs, context)


def register(module_id: str, module_obj: Any) -> None:
    """Global convenience for _default_client.register()."""
    _default_client.register(module_id, module_obj)


def describe(module_id: str) -> str:
    """Global convenience for _default_client.describe()."""
    return _default_client.describe(module_id)


def use(middleware: Any) -> APCore:
    """Global convenience for _default_client.use()."""
    return _default_client.use(middleware)


def use_before(callback: Any) -> APCore:
    """Global convenience for _default_client.use_before()."""
    return _default_client.use_before(callback)


def use_after(callback: Any) -> APCore:
    """Global convenience for _default_client.use_after()."""
    return _default_client.use_after(callback)


def remove(middleware: Any) -> bool:
    """Global convenience for _default_client.remove()."""
    return _default_client.remove(middleware)


def discover() -> int:
    """Global convenience for _default_client.discover()."""
    return _default_client.discover()


def list_modules(tags: list[str] | None = None, prefix: str | None = None) -> list[str]:
    """Global convenience for _default_client.list_modules()."""
    return _default_client.list_modules(tags=tags, prefix=prefix)


def on(event_type: str, handler: Any) -> EventSubscriber:
    """Global convenience for _default_client.on()."""
    return _default_client.on(event_type, handler)


def off(subscriber: EventSubscriber) -> None:
    """Global convenience for _default_client.off()."""
    _default_client.off(subscriber)


def disable(module_id: str, reason: str = "Disabled via APCore client") -> dict[str, Any]:
    """Global convenience for _default_client.disable()."""
    return _default_client.disable(module_id, reason)


def enable(module_id: str, reason: str = "Enabled via APCore client") -> dict[str, Any]:
    """Global convenience for _default_client.enable()."""
    return _default_client.enable(module_id, reason)


try:
    __version__ = _get_version("apcore")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    # Core
    "CancelToken",
    "ExecutionCancelledError",
    "Context",
    "ContextFactory",
    "ContextKey",
    "TRACING_SPANS",
    "TRACING_SAMPLED",
    "METRICS_STARTS",
    "LOGGING_START",
    "REDACTED_OUTPUT",
    "RETRY_COUNT_BASE",
    "Identity",
    "Registry",
    "Executor",
    "APCore",
    "call",
    "call_async",
    "stream",
    "validate",
    "register",
    "describe",
    "use",
    "use_before",
    "use_after",
    "remove",
    "discover",
    "list_modules",
    "on",
    "off",
    "disable",
    "enable",
    # Approval
    "ApprovalHandler",
    "ApprovalRequest",
    "ApprovalResult",
    "AlwaysDenyHandler",
    "AutoApproveHandler",
    "CallbackApprovalHandler",
    # Module types
    "DEFAULT_ANNOTATIONS",
    "Module",
    "ModuleAnnotations",
    "ModuleExample",
    "ValidationResult",
    "PreflightCheckResult",
    "PreflightResult",
    # Registry types
    "ModuleDescriptor",
    "DiscoveredModule",
    "DependencyInfo",
    # Config
    "Config",
    "discover_config_file",
    # Error Formatter
    "ErrorFormatter",
    "ErrorFormatterRegistry",
    # Registry protocols
    "Discoverer",
    "ModuleValidator",
    # Errors
    "ErrorCodes",
    "ModuleError",
    "ACLDeniedError",
    "ACLRuleError",
    "ApprovalError",
    "ApprovalDeniedError",
    "ApprovalTimeoutError",
    "ApprovalPendingError",
    "BindingCallableNotFoundError",
    "BindingFileInvalidError",
    "BindingInvalidTargetError",
    "BindingModuleNotFoundError",
    "BindingNotCallableError",
    "BindingSchemaMissingError",
    "CallDepthExceededError",
    "CallFrequencyExceededError",
    "CircularCallError",
    "CircularDependencyError",
    "ConfigBindError",
    "ConfigEnvMapConflictError",
    "ConfigEnvPrefixConflictError",
    "ConfigError",
    "ConfigMountError",
    "ConfigNamespaceDuplicateError",
    "ConfigNamespaceReservedError",
    "ConfigNotFoundError",
    "ErrorFormatterDuplicateError",
    "ErrorCodeCollisionError",
    "ErrorCodeRegistry",
    "FRAMEWORK_ERROR_CODE_PREFIXES",
    "FuncMissingReturnTypeError",
    "FuncMissingTypeHintError",
    "InternalError",
    "InvalidInputError",
    "ModuleDisabledError",
    "ModuleExecuteError",
    "ModuleLoadError",
    "ModuleNotFoundError",
    "ReloadFailedError",
    "ModuleTimeoutError",
    "SchemaCircularRefError",
    "SchemaNotFoundError",
    "SchemaParseError",
    "SchemaValidationError",
    # ACL
    "ACL",
    "ACLRule",
    "AuditEntry",
    # Middleware
    "Middleware",
    "MiddlewareManager",
    "BeforeMiddleware",
    "AfterMiddleware",
    "LoggingMiddleware",
    "MiddlewareChainError",
    "RetryConfig",
    "RetryMiddleware",
    "ErrorHistoryMiddleware",
    "PlatformNotifyMiddleware",
    # Decorators
    "module",
    "FunctionModule",
    # NOTE: parse_docstring is intentionally NOT in __all__ — it is an
    #       implementation detail importable via apcore._docstrings.
    # Extensions
    "ExtensionManager",
    "ExtensionPoint",
    # Async tasks
    "AsyncTaskManager",
    "TaskStatus",
    "TaskInfo",
    # Bindings
    "BindingLoader",
    # Schema
    "SchemaStrategy",
    "ExportProfile",
    "SchemaLoader",
    "SchemaValidator",
    "SchemaExporter",
    "RefResolver",
    "to_strict_schema",
    # Utilities
    "match_pattern",
    "guard_call_chain",
    "DEFAULT_MAX_CALL_DEPTH",
    "DEFAULT_MAX_MODULE_REPEAT",
    "normalize_to_canonical_id",
    "calculate_specificity",
    "propagate_error",
    "redact_sensitive",
    "REDACTED_VALUE",
    # Observability
    "TracingMiddleware",
    "ContextLogger",
    "ObsLoggingMiddleware",
    "MetricsMiddleware",
    "METRIC_CALLS_TOTAL",
    "METRIC_DURATION_SECONDS",
    "MetricsCollector",
    "Span",
    "StdoutExporter",
    "InMemoryExporter",
    "OTLPExporter",
    "SpanExporter",
    "create_span",
    "ErrorEntry",
    "ErrorHistory",
    "UsageCollector",
    "UsageMiddleware",
    # Events
    "ApCoreEvent",
    "EventEmitter",
    "EventSubscriber",
    "WebhookSubscriber",
    "A2ASubscriber",
    # Trace Context
    "TraceContext",
    "TraceParent",
    # Version
    "VersionIncompatibleError",
    "negotiate_version",
    # Pipeline
    "Step",
    "BaseStep",
    "StepResult",
    "PipelineContext",
    "PipelineEngine",
    "PipelineTrace",
    "StepTrace",
    "ExecutionStrategy",
    "StrategyInfo",
    "PipelineAbortError",
    "StepNotFoundError",
    "StepNotRemovableError",
    "StepNotReplaceableError",
    "StepNameDuplicateError",
    "StrategyNotFoundError",
    # Pipeline Configuration
    "register_step_type",
    "unregister_step_type",
    "registered_step_types",
    "build_strategy_from_config",
    # Pipeline Preset Builders (parity with apcore-typescript / apcore-rust)
    "build_standard_strategy",
    "build_internal_strategy",
    "build_testing_strategy",
    "build_performance_strategy",
    "build_minimal_strategy",
    # Builtin Pipeline Steps (parity with apcore-typescript / apcore-rust)
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
    # System Modules
    "register_sys_modules",
    "register_subscriber_type",
    "unregister_subscriber_type",
    "reset_subscriber_registry",
    "SysModulesContext",
    # System Module Implementations
    "HealthSummaryModule",
    "HealthModule",
    "HealthModuleModule",  # backward-compat alias
    "classify_health_status",
    "ManifestFullModule",
    "ManifestModule",
    "ManifestModuleModule",  # backward-compat alias
    "UsageSummaryModule",
    "UsageModule",
    "UsageModuleModule",  # backward-compat alias
    "UpdateConfigModule",
    "ReloadModule",
    "ReloadModuleModule",  # backward-compat alias
    "ToggleFeatureModule",
    "ToggleState",
]
