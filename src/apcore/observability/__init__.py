"""apcore observability package.

Re-exports all public observability classes for convenient access::

    from apcore.observability import (
        Span, TracingMiddleware, StdoutExporter, InMemoryExporter,
        ContextLogger, ObsLoggingMiddleware,
        MetricsCollector, MetricsMiddleware,
    )

Recommended middleware registration order (outermost to innermost):
    1. TracingMiddleware  -- captures total wall-clock time
    2. MetricsMiddleware  -- captures execution timing
    3. ObsLoggingMiddleware  -- logs with timing already set up
"""

from apcore.observability.context_logger import ContextLogger, ObsLoggingMiddleware
from apcore.observability.error_history import ErrorEntry, ErrorHistory
from apcore.observability.metrics import MetricsCollector, MetricsMiddleware
from apcore.observability.tracing import (
    InMemoryExporter,
    OTLPExporter,
    Span,
    SpanExporter,
    StdoutExporter,
    TracingMiddleware,
    create_span,
)

__all__ = [
    "ContextLogger",
    "ErrorEntry",
    "ErrorHistory",
    "InMemoryExporter",
    "MetricsCollector",
    "MetricsMiddleware",
    "ObsLoggingMiddleware",
    "OTLPExporter",
    "Span",
    "SpanExporter",
    "StdoutExporter",
    "TracingMiddleware",
    "create_span",
]
