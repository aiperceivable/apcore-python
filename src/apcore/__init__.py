"""apcore - Schema-driven module development framework."""

from __future__ import annotations

from collections.abc import AsyncIterator
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
from apcore.registry import Registry
from apcore.client import APCore
from apcore.registry.registry import (
    MAX_MODULE_ID_LENGTH,
    MODULE_ID_PATTERN,
    REGISTRY_EVENTS,
    RESERVED_WORDS,
    Discoverer,
    ModuleValidator,
)
from apcore.registry.types import DependencyInfo, DiscoveredModule, ModuleDescriptor
from apcore.executor import Executor, redact_sensitive, REDACTED_VALUE

# Module types
from apcore.module import (
    Module,
    ModuleAnnotations,
    ModuleExample,
    PreflightCheckResult,
    PreflightResult,
    ValidationResult,
)

# Config
from apcore.config import Config

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
    ConfigError,
    ConfigNotFoundError,
    DependencyNotFoundError,
    ErrorCodeCollisionError,
    ErrorCodeRegistry,
    ErrorCodes,
    FeatureNotImplementedError,
    FuncMissingReturnTypeError,
    FuncMissingTypeHintError,
    InternalError,
    InvalidInputError,
    ModuleError,
    ModuleExecuteError,
    ModuleLoadError,
    ModuleNotFoundError,
    ModuleTimeoutError,
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
    LoggingMiddleware,
    Middleware,
    MiddlewareChainError,
    MiddlewareManager,
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
    SchemaLoader as SchemaLoader,
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
from apcore.utils.error_propagation import propagate_error as propagate_error
from apcore.utils.normalize import normalize_to_canonical_id as normalize_to_canonical_id
from apcore.utils.pattern import calculate_specificity as calculate_specificity

# Observability
from apcore.observability import (
    ContextLogger,
    InMemoryExporter,
    MetricsCollector,
    MetricsMiddleware,
    ObsLoggingMiddleware,
    OTLPExporter,
    Span,
    SpanExporter,
    StdoutExporter,
    TracingMiddleware,
    create_span,
)

# Trace Context
from apcore.trace_context import TraceContext, TraceParent

# ---------------------------------------------------------------------------
# Default client for simplified global access
# ---------------------------------------------------------------------------

_default_client = APCore()


def call(module_id: str, inputs: dict[str, Any] | None = None, context: Context | None = None) -> dict[str, Any]:
    """Global convenience for _default_client.call()."""
    return _default_client.call(module_id, inputs, context)


async def call_async(
    module_id: str, inputs: dict[str, Any] | None = None, context: Context | None = None
) -> dict[str, Any]:
    """Global convenience for _default_client.call_async()."""
    return await _default_client.call_async(module_id, inputs, context)


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
    module_id: str, inputs: dict[str, Any] | None = None, context: Context | None = None
) -> AsyncIterator[dict[str, Any]]:
    """Global convenience for _default_client.stream()."""
    async for chunk in _default_client.stream(module_id, inputs, context):
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


__version__ = "0.10.0"

__all__ = [
    # Core
    "CancelToken",
    "ExecutionCancelledError",
    "Context",
    "ContextFactory",
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
    # Approval
    "ApprovalHandler",
    "ApprovalRequest",
    "ApprovalResult",
    "AlwaysDenyHandler",
    "AutoApproveHandler",
    "CallbackApprovalHandler",
    # Module types
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
    # Registry constants
    "REGISTRY_EVENTS",
    "MODULE_ID_PATTERN",
    "MAX_MODULE_ID_LENGTH",
    "RESERVED_WORDS",
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
    "ConfigError",
    "ConfigNotFoundError",
    "DependencyNotFoundError",
    "ErrorCodeCollisionError",
    "ErrorCodeRegistry",
    "FeatureNotImplementedError",
    "FuncMissingReturnTypeError",
    "FuncMissingTypeHintError",
    "InternalError",
    "InvalidInputError",
    "ModuleExecuteError",
    "ModuleLoadError",
    "ModuleNotFoundError",
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
    # Decorators
    "module",
    "FunctionModule",
    # Docstring parsing
    "parse_docstring",
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
    "SchemaLoader",
    "SchemaValidator",
    "SchemaExporter",
    "RefResolver",
    "to_strict_schema",
    # Utilities
    "match_pattern",
    "guard_call_chain",
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
    "MetricsCollector",
    "Span",
    "StdoutExporter",
    "InMemoryExporter",
    "OTLPExporter",
    "SpanExporter",
    "create_span",
    # Trace Context
    "TraceContext",
    "TraceParent",
    # Version
    "VersionIncompatibleError",
    "negotiate_version",
]
