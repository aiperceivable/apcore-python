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
    ErrorCodeCollisionError,
    ErrorCodeRegistry,
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
from apcore.decorator import FunctionModule, module
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
)

# Trace Context
from apcore.trace_context import TraceContext, TraceParent

__version__ = "0.8.0"

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
    "ErrorCodeCollisionError",
    "ErrorCodeRegistry",
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
    # Trace Context
    "TraceContext",
    "TraceParent",
    # Version
    "VersionIncompatibleError",
    "negotiate_version",
]
