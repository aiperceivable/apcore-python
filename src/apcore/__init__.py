"""apcore - Schema-driven module development framework."""

from __future__ import annotations

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
from apcore.module import Module, ModuleAnnotations, ModuleExample, ValidationResult

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
    ErrorCodes,
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
from apcore.acl import ACL, ACLRule

# Middleware
from apcore.middleware import (
    AfterMiddleware,
    BeforeMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareChainError,
    MiddlewareManager,
)

# Decorators
from apcore.decorator import FunctionModule, module

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

# Utilities (pattern matching)
from apcore.utils import match_pattern as match_pattern

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
)

# Trace Context
from apcore.trace_context import TraceContext, TraceParent

__version__ = "0.7.1"

__all__ = [
    # Core
    "CancelToken",
    "ExecutionCancelledError",
    "Context",
    "ContextFactory",
    "Identity",
    "Registry",
    "Executor",
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
    # Middleware
    "Middleware",
    "MiddlewareManager",
    "BeforeMiddleware",
    "AfterMiddleware",
    "LoggingMiddleware",
    "MiddlewareChainError",
    # Decorators
    "module",
    "FunctionModule",
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
    # Trace Context
    "TraceContext",
    "TraceParent",
]
